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
    message_chain_limit: int = 3
    primitive_obsession_limit: int = 4
    comment_density_limit: float = 0.5  # Comments / Code ratio
    feature_envy_limit: int = 3  # External accesses vs internal


class AntlrMetalCodeSmellDetector(MetalCodeSmellDetector):
    def __init__(self, thresholds: SmellThresholds | None = None) -> None:
        self._generated = load_generated_types()
        self._thresholds = thresholds or SmellThresholds()

    def detect(self, source_unit: SourceUnit) -> SourceSmellReport:
        parse_result = parse_source_text(source_unit.content, self._generated)
        
        # Calculate comment density for the whole file
        comment_lines = source_unit.content.count("//") + source_unit.content.count("/*")
        total_lines = source_unit.content.count("\n") + 1
        density = comment_lines / total_lines if total_lines > 0 else 0
        
        visitor = _SmellVisitor(
            source_location=source_unit.location,
            thresholds=self._thresholds,
            visitor_base=self._generated.visitor_type,
            file_density=density
        )
        visitor.visit(parse_result.tree)
        
        # Post-process for file-level smells if any
        if density > self._thresholds.comment_density_limit:
            visitor.smells.append(
                CodeSmell(
                    kind=SmellKind.COMMENT_DENSITY,
                    message=f"High comment density ({density:.2f}) might indicate 'deodorant' comments",
                    location=source_unit.location,
                    line=1,
                    column=0,
                )
            )
            
        return SourceSmellReport(
            source_location=source_unit.location,
            smells=tuple(visitor.smells),
        )


def _SmellVisitor(
    source_location: str, 
    thresholds: SmellThresholds, 
    visitor_base: type,
    file_density: float
) -> Any:
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
            
            # Fowler specifics
            self._current_function_name: str | None = None
            self._external_accesses: dict[str, int] = {} # target -> count
            self._internal_accesses: int = 0
            self._parameter_signatures: list[tuple[str, ...]] = []
            self._current_class: str | None = None
            self._class_members: set[str] = set()
            self._used_members: set[str] = set()
            self._function_call_count = 0
            self._touched_structs: set[str] = set()
            self._member_functions: list[str] = []

        # -- Class/Struct analysis ----------------------------------------

        def visitStructDeclaration(self, ctx):
            self._check_large_class(ctx, "struct")
            name_ctx = ctx.name()
            name = "anonymous"
            if name_ctx:
                name = name_ctx[0].getText() if isinstance(name_ctx, list) else name_ctx.getText()
            
            old_class = self._current_class
            old_members = self._class_members
            old_member_funcs = self._member_functions
            self._current_class = name
            self._class_members = set()
            self._member_functions = []
            
            # Check for inheritance (Refused Bequest)
            if hasattr(ctx, "typeSpecifier") and ctx.typeSpecifier() and not isinstance(ctx.typeSpecifier(), list):
                # We have a base class
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.REFUSED_BEQUEST,
                        message=f"Struct '{name}' uses inheritance; check for Refused Bequest",
                        location=source_location,
                        line=ctx.start.line,
                        column=ctx.start.column,
                    )
                )
            
            result = self.visitChildren(ctx)
            
            # Primitive Obsession in Struct
            primitives = len(self._class_members)
            if primitives > thresholds.primitive_obsession_limit:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.PRIMITIVE_OBSESSION,
                        message=f"Struct '{name}' may be suffering from Primitive Obsession ({primitives} primitives)",
                        location=source_location,
                        line=ctx.start.line,
                        column=ctx.start.column,
                        context=f"struct {name}",
                    )
                )
            
            # Divergent Change / Large Class
            if len(self._member_functions) > 10:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.DIVERGENT_CHANGE,
                        message=f"Struct '{name}' has many member functions ({len(self._member_functions)}), likely Divergent Change",
                        location=source_location,
                        line=ctx.start.line,
                        column=ctx.start.column,
                    )
                )

            self._current_class = old_class
            self._class_members = old_members
            self._member_functions = old_member_funcs
            return result

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
                # Speculative Generality
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.SPECULATIVE_GENERALITY,
                        message=f"Function declaration without body might be Speculative Generality",
                        location=source_location,
                        line=ctx.start.line,
                        column=ctx.start.column,
                    )
                )
                return None

            name_ctx = ctx.name()
            name = name_ctx.getText() if name_ctx else "function"
            if self._current_class:
                self._member_functions.append(name)

            self._current_function_name = name
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
                
                # Data Clump detection
                sig = tuple(p.getText() for p in param_decls)
                for existing in self._parameter_signatures:
                    if len(set(sig) & set(existing)) >= 3:
                        self.smells.append(
                            CodeSmell(
                                kind=SmellKind.DATA_CLUMP,
                                message=f"Parameters in '{name}' look like a Data Clump",
                                location=source_location,
                                line=start_line,
                                column=ctx.start.column,
                            )
                        )
                self._parameter_signatures.append(sig)

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
            old_envy = self._external_accesses
            old_internal = self._internal_accesses
            old_calls = self._function_call_count
            old_touched = self._touched_structs
            
            self._current_complexity = 1  # Base complexity
            self._current_nesting = 0
            self._local_vars_count = 0
            self._in_function = True
            self._external_accesses = {}
            self._internal_accesses = 0
            self._function_call_count = 0
            self._touched_structs = set()

            self.visitChildren(ctx)

            # Middle Man check
            if self._function_call_count == 1 and line_count < 5:
                 self.smells.append(
                    CodeSmell(
                        kind=SmellKind.MIDDLE_MAN,
                        message=f"Function '{name}' looks like a Middle Man (only delegates)",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                    )
                )
            
            # Shotgun Surgery heuristic
            if len(self._touched_structs) > 3:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.SHOTGUN_SURGERY,
                        message=f"Function '{name}' touches {len(self._touched_structs)} different objects; check for Shotgun Surgery",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                    )
                )

            # Feature Envy check
            for target, count in self._external_accesses.items():
                if count > thresholds.feature_envy_limit and count > self._internal_accesses:
                    self.smells.append(
                        CodeSmell(
                            kind=SmellKind.FEATURE_ENVY,
                            message=f"Function '{name}' seems more interested in '{target}' than its own class",
                            location=source_location,
                            line=start_line,
                            column=ctx.start.column,
                        )
                    )

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
            self._external_accesses = old_envy
            self._internal_accesses = old_internal
            self._function_call_count = old_calls
            self._touched_structs = old_touched
            self._current_function_name = None
            return None

        # -- Variable analysis --------------------------------------------

        def visitStructMemberDeclaration(self, ctx):
            if self._current_class and not self._in_function:
                # Add to members for Primitive Obsession check
                m_list = ctx.memberDeclaratorList()
                if m_list:
                    for m in m_list.memberDeclarator():
                        self._class_members.add(m.name().getText())
            return self.visitChildren(ctx)

        def visitVariableDeclaration(self, ctx):
            if self._in_function:
                init_list = ctx.initDeclaratorList()
                if init_list:
                    decls = init_list.initDeclarator()
                    self._local_vars_count += len(decls)
                    # Temporary Field heuristic
                    if self._current_class:
                        for d in decls:
                            self.smells.append(
                                CodeSmell(
                                    kind=SmellKind.TEMPORARY_FIELD,
                                    message=f"Variable '{d.declarator().name().getText()}' might be a Temporary Field",
                                    location=source_location,
                                    line=ctx.start.line,
                                    column=ctx.start.column,
                                )
                            )
            
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
                        if n.getText() in self._class_members:
                            self._internal_accesses += 1
                else:
                    self._used_params.add(name_ctx.getText())
                    if name_ctx.getText() in self._class_members:
                        self._internal_accesses += 1
            return self.visitChildren(ctx)

        def visitPostfixExpression(self, ctx):
            # Message Chain and Feature Envy detection
            if ctx.LParen():
                self._function_call_count += 1

            chain_length = 0
            curr = ctx
            while curr and hasattr(curr, "Dot") and (curr.Dot() or (hasattr(curr, "Arrow") and curr.Arrow())):
                chain_length += 1
                if chain_length == 1:
                    # Capture the base object for Feature Envy
                    base = curr.postfixExpression()
                    if base:
                        base_text = base.getText()
                        self._external_accesses[base_text] = self._external_accesses.get(base_text, 0) + 1
                        self._touched_structs.add(base_text)
                
                curr = curr.postfixExpression()
            
            if chain_length > thresholds.message_chain_limit:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.MESSAGE_CHAIN,
                        message=f"Message chain too long ({chain_length})",
                        location=source_location,
                        line=ctx.start.line,
                        column=ctx.start.column,
                    )
                )
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
            if ctx.Switch():
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.SWITCH_STATEMENT,
                        message="Switch statement detected (Fowler recommends polymorphism)",
                        location=source_location,
                        line=ctx.start.line,
                        column=ctx.start.column,
                    )
                )
            
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
