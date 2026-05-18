"""Extract code smells from Metal source through ANTLR."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from antlr4 import CommonTokenStream, InputStream

from metala.domain.model import SourceUnit
from metala.domain.ports import MetalCodeSmellDetector
from metala.domain.smells import CodeSmell, SmellKind, SourceSmellReport
from metala.infrastructure.antlr.runtime import load_generated_types, parse_source_text


@dataclass
class SmellThresholds:
    long_function_lines: int = 50
    long_parameter_list: int = 5
    large_class_lines: int = 200
    deep_nesting: int = 3
    complex_flow: int = 10
    excessive_locals: int = 10
    magic_number_ignored_values: set[str] = field(
        default_factory=lambda: {"0", "1", "0.0", "1.0", "-1", "-1.0"}
    )


class AntlrMetalCodeSmellDetector(MetalCodeSmellDetector):
    def __init__(self, thresholds: SmellThresholds | None = None) -> None:
        self._generated = load_generated_types()
        self._thresholds = thresholds or SmellThresholds()

    def detect(self, source_unit: SourceUnit) -> SourceSmellReport:
        parse_result = parse_source_text(source_unit.content, self._generated)
        visitor = _SmellVisitor(
            source_location=source_unit.location,
            thresholds=self._thresholds,
            visitor_base=self._generated.visitor_type,
        )
        visitor.visit(parse_result.tree)
        return SourceSmellReport(
            source_location=source_unit.location,
            smells=tuple(visitor.smells),
        )


def _SmellVisitor(source_location: str, thresholds: SmellThresholds, visitor_base: type) -> Any:
    class MetalSmellVisitor(visitor_base):
        def __init__(self) -> None:
            super().__init__()
            self.smells: list[CodeSmell] = []
            self._current_nesting = 0
            self._current_complexity = 0
            self._in_function = False
            self._current_params: set[str] = set()
            self._used_params: set[str] = set()
            self._local_vars_count = 0
            self._in_constant_decl = False

        # -- Class/Struct analysis ----------------------------------------

        def visitStructDeclaration(self, ctx):
            self._check_large_class(ctx, "struct")
            return self.visitChildren(ctx)

        def visitClassDeclaration(self, ctx):
            self._check_large_class(ctx, "class")
            return self.visitChildren(ctx)

        def _check_large_class(self, ctx, kind: str):
            start_line = ctx.start.line
            stop_line = ctx.stop.line
            line_count = stop_line - start_line + 1
            if line_count > thresholds.large_class_lines:
                name_ctx = ctx.name()
                name = "anonymous"
                if name_ctx:
                    if isinstance(name_ctx, list):
                        name = name_ctx[0].getText() if name_ctx else "anonymous"
                    else:
                        name = name_ctx.getText()
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.LARGE_CLASS,
                        message=f"{kind.capitalize()} '{name}' is too large ({line_count} lines)",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                        context=f"{kind} {name}",
                    )
                )

        # -- Function analysis --------------------------------------------

        def visitFunctionDeclaration(self, ctx):
            if ctx.functionBody() is None:
                return None

            name_ctx = ctx.name()
            name = name_ctx.getText() if name_ctx else "function"
            start_line = ctx.start.line
            stop_line = ctx.stop.line
            line_count = stop_line - start_line + 1

            # Long Function
            if line_count > thresholds.long_function_lines:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.LONG_FUNCTION,
                        message=f"Function '{name}' is too long ({line_count} lines)",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                        context=f"function {name}",
                    )
                )

            # Parameters and Unused Parameters setup
            params = ctx.parameterList()
            old_params = self._current_params
            old_used = self._used_params
            self._current_params = set()
            self._used_params = set()
            
            if params:
                param_decls = params.parameterDeclaration()
                param_count = len(param_decls)
                # Long Parameter List
                if param_count > thresholds.long_parameter_list:
                    self.smells.append(
                        CodeSmell(
                            kind=SmellKind.LONG_PARAMETER_LIST,
                            message=f"Function '{name}' has too many parameters ({param_count})",
                            location=source_location,
                            line=start_line,
                            column=ctx.start.column,
                            context=f"function {name}",
                        )
                    )
                
                for p in param_decls:
                    p_name_ctx = p.name()
                    if p_name_ctx:
                        self._current_params.add(p_name_ctx.getText())

            # Reset complexity, nesting, and locals for function body
            old_complexity = self._current_complexity
            old_nesting = self._current_nesting
            old_locals = self._local_vars_count
            old_in_function = self._in_function
            
            self._current_complexity = 1  # Base complexity
            self._current_nesting = 0
            self._local_vars_count = 0
            self._in_function = True

            self.visitChildren(ctx)

            # Complex Flow (Cyclomatic Complexity)
            if self._current_complexity > thresholds.complex_flow:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.COMPLEX_FLOW,
                        message=f"Function '{name}' is too complex (CC={self._current_complexity})",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                        context=f"function {name}",
                    )
                )
            
            # Excessive Locals
            if self._local_vars_count > thresholds.excessive_locals:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.EXCESSIVE_LOCALS,
                        message=f"Function '{name}' has too many local variables ({self._local_vars_count})",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                        context=f"function {name}",
                    )
                )
            
            # Unused Parameters
            unused = self._current_params - self._used_params
            for p_name in sorted(unused):
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.UNUSED_PARAMETER,
                        message=f"Parameter '{p_name}' is unused in function '{name}'",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                        context=f"function {name}",
                    )
                )

            self._current_complexity = old_complexity
            self._current_nesting = old_nesting
            self._local_vars_count = old_locals
            self._in_function = old_in_function
            self._current_params = old_params
            self._used_params = old_used
            return None

        # -- Variable analysis --------------------------------------------

        def visitVariableDeclaration(self, ctx):
            if self._in_function:
                # Count only top-level variable declarations in the function
                # (actually, any declaration in function contributes to register pressure)
                init_list = ctx.initDeclaratorList()
                if init_list:
                    self._local_vars_count += len(init_list.initDeclarator())

            # Check if this is a constant declaration
            is_const = False
            for q in ctx.typeQualifier() or []:
                if q.Const() or q.Constexpr():
                    is_const = True
                    break
            
            old_in_constant = self._in_constant_decl
            self._in_constant_decl = is_const
            result = self.visitChildren(ctx)
            self._in_constant_decl = old_in_constant
            return result

        def visitPrimaryExpression(self, ctx):
            name_ctx = ctx.name()
            if name_ctx and self._in_function:
                # Track usage of identifiers
                if isinstance(name_ctx, list):
                    for n in name_ctx:
                        self._used_params.add(n.getText())
                else:
                    self._used_params.add(name_ctx.getText())
            return self.visitChildren(ctx)

        def visitLiteral(self, ctx):
            if not self._in_constant_decl:
                val = ctx.getText()
                if (ctx.IntegerLiteral() or ctx.FloatingLiteral()) and val not in thresholds.magic_number_ignored_values:
                    self.smells.append(
                        CodeSmell(
                            kind=SmellKind.MAGIC_NUMBER,
                            message=f"Magic number '{val}' detected",
                            location=source_location,
                            line=ctx.start.line,
                            column=ctx.start.column,
                        )
                    )
            return self.visitChildren(ctx)

        # -- Control flow analysis (Complexity & Nesting) -----------------

        def visitSelectionStatement(self, ctx):
            self._current_complexity += 1
            self._current_nesting += 1
            self._check_nesting(ctx)
            result = self.visitChildren(ctx)
            self._current_nesting -= 1
            return result

        def visitIterationStatement(self, ctx):
            self._current_complexity += 1
            self._current_nesting += 1
            self._check_nesting(ctx)
            result = self.visitChildren(ctx)
            self._current_nesting -= 1
            return result

        def visitCaseGroup(self, ctx):
            self._current_complexity += 1
            return self.visitChildren(ctx)

        def _check_nesting(self, ctx):
            if self._current_nesting > thresholds.deep_nesting:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.DEEP_NESTING,
                        message=f"Control structure is too deeply nested (depth={self._current_nesting})",
                        location=source_location,
                        line=ctx.start.line,
                        column=ctx.start.column,
                    )
                )

        def visitCompoundStatement(self, ctx):
            return self.visitChildren(ctx)

    return MetalSmellVisitor()
