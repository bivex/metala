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
    shader_magic_number_permits: set[str] = field(
        default_factory=lambda: {
            # fractional steps common in shaders
            "0.0",
            "0.05",
            "0.1",
            "0.15",
            "0.2",
            "0.25",
            "0.3",
            "0.35",
            "0.4",
            "0.45",
            "0.5",
            "0.55",
            "0.6",
            "0.65",
            "0.7",
            "0.75",
            "0.8",
            "0.85",
            "0.9",
            "0.95",
            "1.0",
            # small integers common in shaders (kernel sizes, repetitions)
            "2.0",
            "3.0",
            "4.0",
            "5.0",
            "8.0",
            # pixel / colour
            "255.0",
            "255",
            "128.0",
            "128",
            # tiny offsets common in shaders
            "0.01",
            "0.001",
            "0.0001",
        }
    )
    message_chain_limit: int = 3
    primitive_obsession_limit: int = 4
    comment_density_limit: float = 0.5  # Comments / Code ratio
    feature_envy_limit: int = 3  # External accesses vs internal
    resource_limit: int = 8  # Buffers/Textures in parameters
    gpu_identifiers: set[str] = field(
        default_factory=lambda: {
            "gid",
            "tid",
            "thread_position_in_grid",
            "thread_position_in_threadgroup",
            "thread_index_in_threadgroup",
            "simdgroup_index_in_threadgroup",
            "gl_GlobalInvocationID",  # Just in case of GLSL-isms
        }
    )
    threadgroup_limit_kb: int = 16  # A-series threshold (conservative)
    simdgroup_size: int = 32  # Typical Apple SIMD size
    bank_count: int = 16  # Typical banks per SIMD


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
            file_density=density,
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
    source_location: str, thresholds: SmellThresholds, visitor_base: type, file_density: float
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
            self._external_accesses: dict[str, int] = {}  # target -> count
            self._internal_accesses: int = 0
            self._parameter_signatures: list[tuple[str, ...]] = []
            self._current_class: str | None = None
            self._class_members: set[str] = set()
            self._used_members: set[str] = set()
            self._function_call_count = 0
            self._touched_structs: set[str] = set()
            self._member_functions: list[str] = []

            # GPU specifics
            self._resource_count = 0
            self._in_selection_expr = False
            self._in_loop = False
            self._atomic_calls_in_loop = 0
            self._shader_function: bool = False
            self._threadgroup_allocation = 0  # bytes
            self._last_barrier_read_count = 0
            self._last_barrier_write_count = 0
            self._barrier_calls_count = 0
            self._texture_reads: list[str] = []  # result variables
            self._is_inside_divergent_selection = False
            self._gpu_bound_vars: set[str] = set()  # vars bound to GPU attributes

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
            if (
                hasattr(ctx, "typeSpecifier")
                and ctx.typeSpecifier()
                and not isinstance(ctx.typeSpecifier(), list)
            ):
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
            qualifiers = ctx.functionQualifier()
            shader_kinds = {
                q.getText().lower() for q in (qualifiers if isinstance(qualifiers, list) else [])
            }
            self._shader_function = bool(shader_kinds & {"vertex", "fragment", "kernel", "compute"})
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
            old_resource_count = self._resource_count
            self._current_params = set()
            self._used_params = set()
            self._resource_count = 0
            self._gpu_bound_vars = set()

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
                        p_name = p_name_ctx.getText()
                        self._current_params.add(p_name)

                        # Track GPU-bound variables for subscript analysis
                        p_text = p.getText()
                        for gpu_id in thresholds.gpu_identifiers:
                            if gpu_id in p_text:
                                self._gpu_bound_vars.add(p_name)
                                break

                    # Resource Overload check
                    text = p.getText()
                    if "texture" in text or "buffer" in text or "device" in text:
                        self._resource_count += 1

            if self._resource_count > thresholds.resource_limit:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.RESOURCE_OVERLOAD,
                        message=f"Function '{name}' binds too many resources ({self._resource_count}); may impact performance",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                    )
                )

            # Reset complexity, nesting, and locals for function body
            old_complexity = self._current_complexity
            old_nesting = self._current_nesting
            old_locals = self._local_vars_count
            old_in_function = self._in_function
            old_envy = self._external_accesses
            old_internal = self._internal_accesses
            old_calls = self._function_call_count
            old_touched = self._touched_structs
            old_atomic_calls = self._atomic_calls_in_loop
            old_threadgroup = self._threadgroup_allocation
            old_barrier_calls = self._barrier_calls_count
            old_texture_reads = self._texture_reads

            self._current_complexity = 1  # Base complexity
            self._current_nesting = 0
            self._local_vars_count = 0
            self._in_function = True
            self._external_accesses = {}
            self._internal_accesses = 0
            self._function_call_count = 0
            self._touched_structs = set()
            self._atomic_calls_in_loop = 0
            self._threadgroup_allocation = 0
            self._barrier_calls_count = 0
            self._texture_reads = []

            self.visitChildren(ctx)

            # Excessive Threadgroup Allocation
            if self._threadgroup_allocation > thresholds.threadgroup_limit_kb * 1024:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.EXCESSIVE_THREADGROUP_ALLOCATION,
                        message=f"Function '{name}' allocates {self._threadgroup_allocation/1024:.1f} KB of threadgroup memory; exceeding {thresholds.threadgroup_limit_kb} KB threshold",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                    )
                )

            # Atomic Contention in Loop
            if self._atomic_calls_in_loop > 2:
                self.smells.append(
                    CodeSmell(
                        kind=SmellKind.ATOMIC_CONTENTION,
                        message=f"Function '{name}' has multiple atomic operations in a loop; high contention risk",
                        location=source_location,
                        line=start_line,
                        column=ctx.start.column,
                    )
                )

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
            self._resource_count = old_resource_count
            self._atomic_calls_in_loop = old_atomic_calls
            self._threadgroup_allocation = old_threadgroup
            self._barrier_calls_count = old_barrier_calls
            self._texture_reads = old_texture_reads
            self._current_function_name = None
            self._shader_function = False
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
                    
                    # Threadgroup allocation tracking
                    is_threadgroup = False
                    for q in ctx.typeQualifier() or []:
                        if "threadgroup" in q.getText():
                            is_threadgroup = True
                            break
                    
                    if is_threadgroup:
                        # Heuristic for size based on type text
                        type_text = ctx.typeSpecifier().getText()
                        size = self._estimate_type_size(type_text)
                        for d in decls:
                            decl_text = d.getText()
                            count = 1
                            if "[" in decl_text and "]" in decl_text:
                                # Array detection
                                import re
                                match = re.search(r"\[(\d+)\]", decl_text)
                                if match:
                                    count = int(match.group(1))
                            self._threadgroup_allocation += size * count

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
            
            # Half precision neglect check
            if self._shader_function and not is_const:
                type_text = ctx.typeSpecifier().getText()
                if "float" in type_text and "half" not in type_text:
                    # Check if it's used in a context where half is likely enough (e.g. colors)
                    var_name = ""
                    init_list = ctx.initDeclaratorList()
                    if init_list:
                        var_name = init_list.initDeclarator()[0].declarator().name().getText()
                    
                    if any(word in var_name.lower() for word in ["color", "diffuse", "specular", "albedo", "normal"]):
                        self.smells.append(
                            CodeSmell(
                                kind=SmellKind.HALF_PRECISION_NEGLECT,
                                message=f"Variable '{var_name}' uses full precision 'float'; 'half' is often sufficient for colors/normals on Apple GPU",
                                location=source_location,
                                line=ctx.start.line,
                                column=ctx.start.column,
                            )
                        )

            old_in_constant = self._in_constant_decl
            self._in_constant_decl = is_const
            result = self.visitChildren(ctx)
            self._in_constant_decl = old_in_constant
            return result

        def _estimate_type_size(self, type_text: str) -> int:
            """Estimate size in bytes for common MSL types."""
            if "float4" in type_text or "int4" in type_text or "uint4" in type_text: return 16
            if "float3" in type_text or "int3" in type_text or "uint3" in type_text: return 16 # Alignment
            if "float2" in type_text or "int2" in type_text or "uint2" in type_text: return 8
            if "float" in type_text or "int" in type_text or "uint" in type_text: return 4
            if "half4" in type_text: return 8
            if "half3" in type_text: return 8 # Alignment
            if "half2" in type_text: return 4
            if "half" in type_text: return 2
            if "bool" in type_text: return 1
            return 4 # Default

        def visitPrimaryExpression(self, ctx):
            name_ctx = ctx.name()
            if name_ctx and self._in_function:
                # Track usage of identifiers
                names = name_ctx if isinstance(name_ctx, list) else [name_ctx]
                for n in names:
                    name_text = n.getText()
                    self._used_params.add(name_text)
                    if name_text in self._class_members:
                        self._internal_accesses += 1

                    # Divergent Branch detection
                    if self._in_selection_expr and name_text in thresholds.gpu_identifiers:
                        self.smells.append(
                            CodeSmell(
                                kind=SmellKind.DIVERGENT_BRANCH,
                                message=f"Control flow depends on GPU identifier '{name_text}'; possible branch divergence",
                                location=source_location,
                                line=ctx.start.line,
                                column=ctx.start.column,
                            )
                        )
                        self._is_inside_divergent_selection = True
            return self.visitChildren(ctx)

        def visitPostfixExpression(self, ctx):
            # Message Chain and Feature Envy detection
            text = ctx.getText()
            if ctx.LParen():
                self._function_call_count += 1
                if "atomic" in text and self._in_loop:
                    self._atomic_calls_in_loop += 1
                
                # Barrier overuse
                if "threadgroup_barrier" in text:
                    self._barrier_calls_count += 1
                    if self._barrier_calls_count > 1:
                        self.smells.append(
                            CodeSmell(
                                kind=SmellKind.THREADGROUP_BARRIER_OVERUSE,
                                message="Multiple threadgroup_barrier calls detected; ensure they are strictly necessary to avoid pipeline stalls",
                                location=source_location,
                                line=ctx.start.line,
                                column=ctx.start.column,
                            )
                        )
                
                # Divergent texture sample
                if ".sample(" in text and self._is_inside_divergent_selection:
                     self.smells.append(
                        CodeSmell(
                            kind=SmellKind.DIVERGENT_TEXTURE_SAMPLE,
                            message="Texture sample inside divergent control flow; may cause incorrect implicit LOD or scalar execution",
                            location=source_location,
                            line=ctx.start.line,
                            column=ctx.start.column,
                        )
                    )
                
                # Dependent texture read and Format mismatch detection
                if ".sample(" in text or ".read(" in text:
                    # Dependent read
                    for prev_var in self._texture_reads:
                        if prev_var in text:
                            self.smells.append(
                                CodeSmell(
                                    kind=SmellKind.DEPENDENT_TEXTURE_READ,
                                    message=f"Texture sample depends on previous sample result '{prev_var}'; GPU cannot prefetch",
                                    location=source_location,
                                    line=ctx.start.line,
                                    column=ctx.start.column,
                                )
                            )
                    
                    # Format mismatch heuristic: texture2d<float> is often overkill for 8-bit textures
                    if "texture2d<float>" in text or "texture2d<half>" in text:
                        # (In a real detector, we'd check the template param of the texture object)
                        pass

            # Indexing (subscript) detection via LBrack
            if hasattr(ctx, "LBrack") and ctx.LBrack():
                base_ctx = ctx.postfixExpression()
                index_ctx = ctx.expression()
                if base_ctx and index_ctx:
                    base = base_ctx.getText()
                    index = index_ctx.getText()

                    _gpu_ids = thresholds.gpu_identifiers | self._gpu_bound_vars

                    # Non-coalesced access heuristic
                    if any(id in index for id in _gpu_ids):
                        import re
                        if re.search(r"(\.y|\[1\])\s*\*\s*(\d+)\s*\+", index):
                            match = re.search(r"\*\s*(\d+)", index)
                            if match and int(match.group(1)) > 1:
                                self.smells.append(
                                    CodeSmell(
                                        kind=SmellKind.NON_COALESCED_ACCESS,
                                        message=f"Access to '{base}' uses a stride > 1; may result in non-coalesced memory access on GPU",
                                        location=source_location,
                                        line=ctx.start.line,
                                        column=ctx.start.column,
                                    )
                                )

                    # Bank conflict heuristic
                    if any(id in index for id in _gpu_ids):
                        import re
                        match = re.search(r"\*\s*(\d+)", index)
                        if match:
                            stride = int(match.group(1))
                            if stride > 0 and stride % thresholds.bank_count == 0:
                                 self.smells.append(
                                    CodeSmell(
                                        kind=SmellKind.THREADGROUP_BANK_CONFLICT,
                                        message=f"Access to '{base}' with stride {stride} may cause threadgroup bank conflicts (bank count={thresholds.bank_count})",
                                        location=source_location,
                                        line=ctx.start.line,
                                        column=ctx.start.column,
                                    )
                                )

            chain_length = 0
            curr = ctx
            while (
                curr
                and hasattr(curr, "Dot")
                and (curr.Dot() or (hasattr(curr, "Arrow") and curr.Arrow()))
            ):
                chain_length += 1
                if chain_length == 1:
                    # Capture the base object for Feature Envy
                    base = curr.postfixExpression()
                    if base:
                        base_text = base.getText()
                        self._external_accesses[base_text] = (
                            self._external_accesses.get(base_text, 0) + 1
                        )
                        self._touched_structs.add(base_text)
                        
                        # Track texture sample results for dependent read detection
                        if ".sample(" in text:
                            # Heuristic: assignments like 'float4 c = tex.sample(...)'
                            # We can't easily see the LHS here, so we look for 'name =' in the parent line
                            # or just use a simpler heuristic for now.
                            pass

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
                if ctx.IntegerLiteral() or ctx.FloatingLiteral():
                    ignored = thresholds.magic_number_ignored_values
                    if self._shader_function:
                        ignored = ignored | thresholds.shader_magic_number_permits
                    if val not in ignored:
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

            # Track if we are in the condition expression
            expr = ctx.expression()
            if expr:
                old_in_sel = self._in_selection_expr
                self._in_selection_expr = True
                self.visit(expr)
                self._in_selection_expr = old_in_sel

            # Visit everything EXCEPT the expression we already visited
            for i in range(ctx.getChildCount()):
                child = ctx.getChild(i)
                if child != expr:
                    self.visit(child)

            self._current_nesting -= 1
            return None

        def visitIterationStatement(self, ctx):
            self._current_complexity += 1
            self._current_nesting += 1
            self._check_nesting(ctx)

            old_loop = self._in_loop
            self._in_loop = True
            
            # SIMDgroup opportunity missed heuristic
            # Check for loop over simdgroup_size or 32 with accumulation pattern
            loop_text = ctx.getText()
            if "for" in loop_text and ("32" in loop_text or "simdgroup_size" in loop_text):
                if "+" in loop_text or "sum" in loop_text:
                    self.smells.append(
                        CodeSmell(
                            kind=SmellKind.SIMDGROUP_OPPORTUNITY_MISSED,
                            message="Manual reduction loop detected; consider using simd_sum() or other SIMD primitives for better performance",
                            location=source_location,
                            line=ctx.start.line,
                            column=ctx.start.column,
                        )
                    )

            expr = ctx.expression()
            if expr:
                if isinstance(expr, list):
                    for e in expr:
                        old_in_sel = self._in_selection_expr
                        self._in_selection_expr = True
                        self.visit(e)
                        self._in_selection_expr = old_in_sel
                else:
                    old_in_sel = self._in_selection_expr
                    self._in_selection_expr = True
                    self.visit(expr)
                    self._in_selection_expr = old_in_sel

            # Visit everything EXCEPT expressions
            for i in range(ctx.getChildCount()):
                child = ctx.getChild(i)
                if child != expr and not (isinstance(expr, list) and child in expr):
                    self.visit(child)

            self._in_loop = old_loop
            self._current_nesting -= 1
            return None

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
