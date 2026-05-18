"""ANTLR-backed Metal parser adapter."""

from __future__ import annotations

from time import perf_counter

from metala.domain.model import (
    GrammarVersion,
    ParseOutcome,
    ParseStatistics,
    SourceUnit,
    StructuralElement,
    StructuralElementKind,
)
from metala.domain.ports import MetalSyntaxParser
from metala.infrastructure.antlr.runtime import (
    ANTLR_GRAMMAR_VERSION,
    load_generated_types,
    parse_source_text,
)


class AntlrMetalSyntaxParser(MetalSyntaxParser):
    def __init__(self) -> None:
        self._generated = load_generated_types()

    @property
    def grammar_version(self) -> GrammarVersion:
        return ANTLR_GRAMMAR_VERSION

    def parse(self, source_unit: SourceUnit) -> ParseOutcome:
        started_at = perf_counter()
        try:
            parse_result = parse_source_text(source_unit.content, self._generated)
            structure_visitor = _build_structure_visitor(self._generated.visitor_type)()
            structure_visitor.visit(parse_result.tree)

            elements = tuple(structure_visitor.elements)
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)

            return ParseOutcome.success(
                source_unit=source_unit,
                grammar_version=self.grammar_version,
                diagnostics=parse_result.diagnostics,
                structural_elements=elements,
                statistics=ParseStatistics(
                    token_count=len(parse_result.token_stream.tokens),
                    structural_element_count=len(elements),
                    diagnostic_count=len(parse_result.diagnostics),
                    elapsed_ms=elapsed_ms,
                ),
            )
        except Exception as error:
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            return ParseOutcome.technical_failure(
                source_unit=source_unit,
                grammar_version=self.grammar_version,
                message=str(error),
                elapsed_ms=elapsed_ms,
            )


def _build_structure_visitor(visitor_base: type) -> type:
    class MetalStructureVisitor(visitor_base):
        def __init__(self) -> None:
            super().__init__()
            self.elements: list[StructuralElement] = []
            self._containers: list[str] = []

        def _get_name(self, ctx, default: str) -> str:
            name_ctx = ctx.name()
            if isinstance(name_ctx, list):
                return name_ctx[0].getText() if name_ctx else default
            return name_ctx.getText() if name_ctx is not None else default

        def visitFunctionDeclaration(self, ctx):
            name = self._get_name(ctx, "")
            if not name:
                tid = ctx.templateId()
                name = tid.getText() if tid is not None else "function"
            qualifiers = " ".join(
                q.getText() for q in (ctx.functionQualifier() or [])
            )
            return_type = ctx.returnType().getText()
            signature = f"{qualifiers} {return_type} {name}".strip()
            self._append(
                StructuralElementKind.FUNCTION,
                name,
                ctx,
                signature=signature,
            )
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitStructDeclaration(self, ctx):
            name = self._get_name(ctx, "struct")
            self._append(StructuralElementKind.STRUCT, name, ctx, signature=f"struct {name}")
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitClassDeclaration(self, ctx):
            name = self._get_name(ctx, "class")
            self._append(StructuralElementKind.CLASS, name, ctx, signature=f"class {name}")
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitEnumDeclaration(self, ctx):
            name = self._get_name(ctx, "enum")
            self._append(StructuralElementKind.ENUM, name, ctx, signature=f"enum {name}")
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitNamespaceDefinition(self, ctx):
            name = self._get_name(ctx, "namespace")
            self._append(
                StructuralElementKind.NAMESPACE,
                name,
                ctx,
                signature=f"namespace {name}",
            )
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitTypeAliasDeclaration(self, ctx):
            text = ctx.getText().rstrip(";").strip()
            if text.startswith("typedef "):
                name = text.split()[-1] if text.split() else "alias"
            elif text.startswith("using "):
                parts = text.split("=", 1)
                name = parts[0].replace("using", "").strip()
            else:
                name = text
            self._append(
                StructuralElementKind.TYPE_ALIAS,
                name,
                ctx,
                signature=text,
            )
            return None

        def visitVariableDeclaration(self, ctx):
            for init_decl in (ctx.initDeclaratorList().initDeclarator() or []):
                decl = init_decl.declarator()
                if decl is not None:
                    name_ctx = decl.name()
                    if name_ctx is not None:
                        var_name = name_ctx.getText()
                        self._append(
                            StructuralElementKind.VARIABLE,
                            var_name,
                            ctx,
                            signature=ctx.getText().rstrip(";").strip(),
                        )
            return None

        def _append(self, kind, name: str, ctx, signature: str | None = None) -> None:
            container = ".".join(self._containers) if self._containers else None
            self.elements.append(
                StructuralElement(
                    kind=kind,
                    name=name,
                    line=ctx.start.line,
                    column=ctx.start.column,
                    container=container,
                    signature=signature,
                )
            )

        def _with_container(self, name: str, callback):
            self._containers.append(name)
            try:
                return callback()
            finally:
                self._containers.pop()

    return MetalStructureVisitor
