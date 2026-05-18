"""Extract structured control flow from Metal Shading Language source through ANTLR."""

from __future__ import annotations

import re
from dataclasses import dataclass

from antlr4 import CommonTokenStream, InputStream
from antlr4.Token import Token

from metala.domain.control_flow import (
    ActionFlowStep,
    ControlFlowDiagram,
    ControlFlowStep,
    ForInFlowStep,
    FunctionControlFlow,
    IfFlowStep,
    SwitchCaseFlowStep,
    SwitchFlowStep,
    WhileFlowStep,
)
from metala.domain.model import SourceUnit
from metala.domain.ports import MetalControlFlowExtractor
from metala.infrastructure.antlr.runtime import (
    load_generated_types,
    parse_code_block_text,
    parse_statement_text,
    parse_source_text,
)


@dataclass(frozen=True, slots=True)
class _ExtractorContext:
    token_stream: object

    def text(self, ctx) -> str:
        if ctx is None:
            return ""
        if isinstance(ctx, list):
            if not ctx:
                return ""
            return self.token_stream.getText(
                start=ctx[0].start.tokenIndex,
                stop=ctx[-1].stop.tokenIndex,
            )
        return self.token_stream.getText(
            start=ctx.start.tokenIndex,
            stop=ctx.stop.tokenIndex,
        )

    def compact(self, ctx, *, limit: int = 96) -> str:
        text = re.sub(r"\s+", " ", self.text(ctx)).strip()
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1]}..."


@dataclass(frozen=True, slots=True)
class _ContainerScope:
    name: str
    body_depth: int


@dataclass(frozen=True, slots=True)
class _PendingContainer:
    name: str


@dataclass(frozen=True, slots=True)
class _FunctionSlice:
    name: str
    signature: str
    container: str | None
    body_text: str


_MAX_STRUCTURED_PARSE_CHARS = 1400
_MAX_STRUCTURED_PARSE_TOKENS = 220
_MAX_STRUCTURED_PARSE_LINES = 24
_MAX_EXPANDED_BODY_CHARS = 1800
_MAX_EXPANDED_BODY_LINES = 36
_SUMMARY_LABEL_LIMIT = 96

_FUNCTION_QUALIFIER_TOKENS = frozenset({
    "Vertex", "Fragment", "Kernel", "Tile", "Visible",
    "Stitchable", "Intersection", "Object_qualifier", "Mesh",
})

_CONTAINER_KEYWORD_TOKENS = frozenset({
    "Struct", "Class", "Enum", "Namespace",
})


class AntlrMetalControlFlowExtractor(MetalControlFlowExtractor):
    def __init__(self) -> None:
        self._generated = load_generated_types()
        self._lexer_type = self._generated.lexer_type

    def extract(self, source_unit: SourceUnit) -> ControlFlowDiagram:
        try:
            function_slices = _scan_function_slices(source_unit.content, self._generated)
            functions = tuple(
                self._extract_function_slice(function_slice)
                for function_slice in function_slices
            )
            return ControlFlowDiagram(
                source_location=source_unit.location,
                functions=functions,
            )
        except Exception:
            # Fallback to the slower whole-file parser when the lightweight scanner
            # cannot safely isolate function bodies.
            return self._extract_via_full_parse(source_unit)

    def _extract_function_slice(self, function_slice: _FunctionSlice) -> FunctionControlFlow:
        quick_steps = _extract_lightweight_steps(
            function_slice.body_text,
            self._generated,
            self._generated.visitor_type,
            self._lexer_type,
        )
        if quick_steps is not None:
            return FunctionControlFlow(
                name=function_slice.name,
                signature=function_slice.signature,
                container=function_slice.container,
                steps=quick_steps,
            )

        parse_result = parse_code_block_text(function_slice.body_text, self._generated)
        visitor = _build_control_flow_visitor(
            self._generated.visitor_type,
            _ExtractorContext(token_stream=parse_result.token_stream),
        )()
        return FunctionControlFlow(
            name=function_slice.name,
            signature=function_slice.signature,
            container=function_slice.container,
            steps=visitor._extract_function_body(parse_result.tree),
        )

    def _extract_via_full_parse(self, source_unit: SourceUnit) -> ControlFlowDiagram:
        parse_result = parse_source_text(source_unit.content, self._generated)
        visitor = _build_control_flow_visitor(
            self._generated.visitor_type,
            _ExtractorContext(token_stream=parse_result.token_stream),
        )()
        visitor.visit(parse_result.tree)
        return ControlFlowDiagram(
            source_location=source_unit.location,
            functions=tuple(visitor.functions),
        )


# ---------------------------------------------------------------------------
# Lightweight token-based function slicing
# ---------------------------------------------------------------------------

def _scan_function_slices(
    source_text: str,
    generated: object,
) -> tuple[_FunctionSlice, ...]:
    lexer = generated.lexer_type(InputStream(source_text))
    token_stream = CommonTokenStream(lexer)
    token_stream.fill()
    tokens = tuple(
        token
        for token in token_stream.tokens
        if token.type != Token.EOF and token.channel == Token.DEFAULT_CHANNEL
    )
    lexer_type = generated.lexer_type

    functions: list[_FunctionSlice] = []
    container_stack: list[_ContainerScope] = []
    pending_container: _PendingContainer | None = None
    brace_depth = 0
    index = 0

    while index < len(tokens):
        token = tokens[index]

        if token.type == lexer_type.LBrace:
            brace_depth += 1
            if pending_container is not None:
                container_stack.append(
                    _ContainerScope(name=pending_container.name, body_depth=brace_depth)
                )
                pending_container = None
            index += 1
            continue

        if token.type == lexer_type.RBrace:
            if container_stack and container_stack[-1].body_depth == brace_depth:
                container_stack.pop()
            brace_depth = max(brace_depth - 1, 0)
            index += 1
            continue

        if _token_name(token, lexer_type) in _CONTAINER_KEYWORD_TOKENS:
            pending_container = _PendingContainer(
                name=_extract_container_name(tokens, index + 1, lexer_type)
            )
            index += 1
            continue

        if _is_function_start(tokens, index, lexer_type):
            function_slice, next_index = _try_scan_function_slice(
                source_text,
                tokens,
                index,
                container_stack,
                lexer_type,
            )
            if function_slice is not None:
                functions.append(function_slice)
                index = next_index
                continue

        index += 1

    return tuple(functions)


def _token_name(token: object, lexer_type: object) -> str | None:
    """Return the symbolic name of *token* from *lexer_type*, or None."""
    if not hasattr(lexer_type, "symbolicNames"):
        return None
    names = lexer_type.symbolicNames
    if token.type < 0 or token.type >= len(names):
        return None
    return names[token.type]


def _is_function_start(
    tokens: tuple[object, ...],
    index: int,
    lexer_type: object,
) -> bool:
    """Heuristic: does the token at *index* begin a Metal function declaration?

    Metal functions start with zero or more function-qualifier tokens (vertex,
    fragment, kernel, ...) followed by a return type, a name, and then LParen.
    Since qualifiers and type names can overlap with regular identifiers, we
    scan forward looking for the pattern ``name LParen`` that is not inside
    angle brackets.
    """
    scan = index

    # Skip over function-qualifier tokens.
    while scan < len(tokens):
        name = _token_name(tokens[scan], lexer_type)
        if name in _FUNCTION_QUALIFIER_TOKENS:
            scan += 1
            continue
        break

    # Now we expect a return type (one or more tokens), then a name, then LParen.
    # We look for the first ``name LParen`` pair that is not inside angle brackets.
    angle_depth = 0
    paren_seen = False
    while scan < len(tokens):
        tok = tokens[scan]
        text = tok.text

        if text == "<":
            angle_depth += 1
            scan += 1
            continue
        if text == ">":
            angle_depth = max(angle_depth - 1, 0)
            scan += 1
            continue
        if angle_depth > 0:
            scan += 1
            continue

        if tok.type == lexer_type.LParen:
            paren_seen = True
            break
        if tok.type == lexer_type.RParen or tok.type == lexer_type.LBrace or tok.type == lexer_type.RBrace:
            break
        scan += 1

    if not paren_seen:
        return False

    # Walk back from the LParen: the token immediately before it should be the name.
    lparen_index = scan
    if lparen_index < 2:
        return False
    name_token = tokens[lparen_index - 1]
    if name_token.type == lexer_type.Identifier or _token_name(name_token, lexer_type) is not None:
        return True
    return False


def _extract_container_name(tokens: tuple[object, ...], start_index: int, lexer_type: object) -> str:
    if start_index >= len(tokens):
        return "anonymous"

    token = tokens[start_index]
    if token.type != lexer_type.Identifier:
        return "anonymous"

    parts = [token.text]
    index = start_index + 1
    while index + 1 < len(tokens):
        if tokens[index].text != "." or tokens[index + 1].type != lexer_type.Identifier:
            break
        parts.append(tokens[index].text)
        parts.append(tokens[index + 1].text)
        index += 2

    return "".join(parts)


def _try_scan_function_slice(
    source_text: str,
    tokens: tuple[object, ...],
    start_index: int,
    container_stack: list[_ContainerScope],
    lexer_type: object,
) -> tuple[_FunctionSlice | None, int]:
    # Advance past any function-qualifier tokens to locate the name.
    scan = start_index
    while scan < len(tokens):
        name = _token_name(tokens[scan], lexer_type)
        if name in _FUNCTION_QUALIFIER_TOKENS:
            scan += 1
            continue
        break

    # Find the name token (the identifier just before LParen at the top level).
    name, lparen_index = _find_function_name_and_lparen(tokens, scan, lexer_type)
    if name is None:
        return None, start_index + 1

    body_open_index = _find_function_body_open(tokens, lparen_index, lexer_type)
    if body_open_index is None:
        return None, start_index + 1

    body_close_index = _find_matching_brace(tokens, body_open_index, lexer_type)
    if body_close_index is None:
        return None, start_index + 1

    signature_text = source_text[tokens[start_index].start : tokens[body_open_index].start]
    body_text = source_text[
        tokens[body_open_index].start : tokens[body_close_index].stop + 1
    ]
    container = ".".join(scope.name for scope in container_stack) or None

    return (
        _FunctionSlice(
            name=name,
            signature=_compact_source_text(signature_text),
            container=container,
            body_text=body_text,
        ),
        body_close_index + 1,
    )


def _find_function_name_and_lparen(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> tuple[str | None, int | None]:
    """Return ``(function_name, lparen_index)`` scanning forward from *start_index*.

    Skips the return type (which may contain angle brackets for template types)
    and stops at the first LParen at zero angle-bracket depth.  The name is
    taken as the token immediately before that LParen.
    """
    angle_depth = 0
    index = start_index

    while index < len(tokens):
        tok = tokens[index]
        text = tok.text

        if text == "<":
            angle_depth += 1
            index += 1
            continue
        if text == ">":
            angle_depth = max(angle_depth - 1, 0)
            index += 1
            continue
        if angle_depth > 0:
            index += 1
            continue

        if tok.type == lexer_type.LParen:
            # Name is the token right before the LParen.
            if index == 0:
                return None, None
            name_tok = tokens[index - 1]
            if name_tok.type == lexer_type.Identifier:
                return name_tok.text, index
            # Some Metal keywords can also be names per the grammar.
            sym = _token_name(name_tok, lexer_type)
            if sym is not None:
                return name_tok.text, index
            return None, None

        if tok.type in {lexer_type.RParen, lexer_type.LBrace, lexer_type.RBrace}:
            return None, None

        index += 1

    return None, None


def _find_function_body_open(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> int | None:
    paren_depth = 0
    square_depth = 0
    angle_depth = 0
    index = start_index

    while index < len(tokens):
        token = tokens[index]
        text = token.text

        if token.type == lexer_type.LParen:
            paren_depth += 1
        elif token.type == lexer_type.RParen:
            paren_depth = max(paren_depth - 1, 0)
        elif token.type == lexer_type.LBrack:
            square_depth += 1
        elif token.type == lexer_type.RBrack:
            square_depth = max(square_depth - 1, 0)
        elif text == "<":
            angle_depth += 1
        elif text == ">":
            angle_depth = max(angle_depth - 1, 0)
        elif (
            token.type == lexer_type.LBrace
            and paren_depth == square_depth == angle_depth == 0
        ):
            return index
        elif (
            token.type == lexer_type.RBrace
            and paren_depth == square_depth == angle_depth == 0
        ):
            return None

        index += 1

    return None


def _find_matching_brace(
    tokens: tuple[object, ...],
    open_index: int,
    lexer_type: object,
) -> int | None:
    depth = 1
    index = open_index + 1
    while index < len(tokens):
        token = tokens[index]
        if token.type == lexer_type.LBrace:
            depth += 1
        elif token.type == lexer_type.RBrace:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _compact_source_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Lightweight step extraction (token-based)
# ---------------------------------------------------------------------------

def _extract_lightweight_steps(
    body_text: str,
    generated: object,
    visitor_type: type,
    lexer_type: object,
) -> tuple[ControlFlowStep, ...] | None:
    statement_spans = _split_top_level_statement_spans(body_text, lexer_type)
    if statement_spans is None:
        return None

    steps: list[ControlFlowStep] = []
    structured_starters = _structured_token_types(lexer_type)

    for statement_text, tokens, base_offset in statement_spans:
        if not tokens:
            continue

        if tokens[0].type in structured_starters:
            if _should_summarize_structured_statement(statement_text, tokens):
                steps.append(
                    _build_summarized_structured_step(
                        statement_text,
                        tokens,
                        base_offset,
                        lexer_type,
                    )
                )
                continue
            parse_result = parse_statement_text(statement_text, generated)
            visitor = _build_control_flow_visitor(
                visitor_type,
                _ExtractorContext(token_stream=parse_result.token_stream),
            )()
            extracted = visitor._extract_statement(parse_result.tree)
            if extracted is not None:
                steps.append(extracted)
            continue

        steps.append(ActionFlowStep(_compact_source_text(statement_text.strip().removesuffix(";"))))

    return tuple(steps)


def _should_summarize_structured_statement(
    statement_text: str,
    tokens: tuple[object, ...],
) -> bool:
    return (
        len(statement_text) > _MAX_STRUCTURED_PARSE_CHARS
        or len(tokens) > _MAX_STRUCTURED_PARSE_TOKENS
        or statement_text.count("\n") > _MAX_STRUCTURED_PARSE_LINES
    )


def _should_summarize_body(body_text: str) -> bool:
    return (
        len(body_text) > _MAX_EXPANDED_BODY_CHARS
        or body_text.count("\n") > _MAX_EXPANDED_BODY_LINES
    )


def _summarize_body_steps(
    body_text: str,
    lexer_type: object,
) -> tuple[ControlFlowStep, ...]:
    statement_spans = _split_top_level_statement_spans(body_text, lexer_type)
    if statement_spans is None:
        label = _compact_label_text(body_text.strip().strip("{}"))
        return (ActionFlowStep(label),) if label else ()

    steps: list[ControlFlowStep] = []
    structured_starters = _structured_token_types(lexer_type)

    for statement_text, tokens, _base_offset in statement_spans:
        if not tokens:
            continue
        if tokens[0].type in structured_starters:
            steps.append(
                _build_summarized_structured_step(
                    statement_text,
                    tokens,
                    tokens[0].start,
                    lexer_type,
                )
            )
            continue
        label = _compact_label_text(statement_text.strip().removesuffix(";"))
        if label:
            steps.append(ActionFlowStep(label))

    return tuple(steps)


# ---------------------------------------------------------------------------
# Summarized structured-step builders (token-based, no full parse)
# ---------------------------------------------------------------------------

def _build_summarized_structured_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    if not tokens:
        return ActionFlowStep(_compact_label_text(statement_text))

    starter = tokens[0].text
    if starter == "if":
        return _build_summarized_if_step(statement_text, tokens, base_offset, lexer_type)
    if starter == "for":
        return _build_summarized_for_step(statement_text, tokens, base_offset, lexer_type)
    if starter == "while":
        return _build_summarized_while_step(statement_text, tokens, base_offset, lexer_type)
    if starter == "do":
        return _build_summarized_do_while_step(statement_text, tokens, base_offset, lexer_type)
    if starter == "switch":
        return _build_summarized_switch_step(statement_text, tokens, base_offset, lexer_type)
    return ActionFlowStep(_summarize_structured_header(statement_text, tokens, base_offset, lexer_type))


def _build_summarized_if_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    block_range = _find_top_level_code_block(tokens, 1, lexer_type)
    if block_range is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip().removesuffix(";")))

    open_index, close_index = block_range
    condition = _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 1, open_index - 1)
    )
    then_steps = _summarize_body_steps(
        _slice_token_text(statement_text, tokens, base_offset, open_index, close_index),
        lexer_type,
    )

    else_steps: tuple[ControlFlowStep, ...] = ()
    else_index = close_index + 1
    if else_index < len(tokens) and tokens[else_index].text == "else":
        next_index = else_index + 1
        if next_index < len(tokens) and tokens[next_index].text == "if":
            nested_text = _slice_token_text(
                statement_text,
                tokens,
                base_offset,
                next_index,
                len(tokens) - 1,
            )
            else_steps = (
                _build_summarized_structured_step(
                    nested_text,
                    tokens[next_index:],
                    tokens[next_index].start,
                    lexer_type,
                ),
            )
        else:
            else_block = _find_top_level_code_block(tokens, next_index, lexer_type)
            if else_block is not None:
                else_open, else_close = else_block
                else_steps = _summarize_body_steps(
                    _slice_token_text(
                        statement_text,
                        tokens,
                        base_offset,
                        else_open,
                        else_close,
                    ),
                    lexer_type,
                )

    return IfFlowStep(
        condition=condition or "condition",
        then_steps=then_steps,
        else_steps=else_steps,
    )


def _build_summarized_for_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    block_range = _find_top_level_code_block(tokens, 1, lexer_type)
    if block_range is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip().removesuffix(";")))

    open_index, close_index = block_range
    header = _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 1, open_index - 1)
    )
    return ForInFlowStep(
        header=header or "item in collection",
        body_steps=_summarize_body_steps(
            _slice_token_text(statement_text, tokens, base_offset, open_index, close_index),
            lexer_type,
        ),
    )


def _build_summarized_while_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    block_range = _find_top_level_code_block(tokens, 1, lexer_type)
    if block_range is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip().removesuffix(";")))

    open_index, close_index = block_range
    condition = _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 1, open_index - 1)
    )
    return WhileFlowStep(
        condition=condition or "condition",
        body_steps=_summarize_body_steps(
            _slice_token_text(statement_text, tokens, base_offset, open_index, close_index),
            lexer_type,
        ),
    )


def _build_summarized_do_while_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    block_range = _find_top_level_code_block(tokens, 1, lexer_type)
    if block_range is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip().removesuffix(";")))

    open_index, close_index = block_range
    while_index = close_index + 1
    condition = ""
    if while_index < len(tokens) and tokens[while_index].text == "while":
        condition = _compact_label_text(
            _slice_token_text(
                statement_text,
                tokens,
                base_offset,
                while_index + 1,
                len(tokens) - 1,
            ).removesuffix(";")
        )
    return WhileFlowStep(
        condition=condition or "condition",
        body_steps=_summarize_body_steps(
            _slice_token_text(statement_text, tokens, base_offset, open_index, close_index),
            lexer_type,
        ),
    )


def _build_summarized_switch_step(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> ControlFlowStep:
    # Switch grammar: Switch LParen expression RParen LBrace caseGroup* RBrace
    block_range = _find_top_level_code_block(tokens, 1, lexer_type)
    if block_range is None:
        return ActionFlowStep(_compact_label_text(statement_text.strip().removesuffix(";")))

    open_index, close_index = block_range
    expression = _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 1, open_index - 1)
    )

    body_text = _slice_token_text(
        statement_text, tokens, base_offset, open_index, close_index
    )
    cases = _summarize_switch_cases(body_text, lexer_type)

    return SwitchFlowStep(
        expression=expression or "expression",
        cases=tuple(cases),
    )


def _summarize_switch_cases(
    body_text: str,
    lexer_type: object,
) -> tuple[SwitchCaseFlow, ...]:
    """Extract case groups from a switch body using token scanning."""
    tokens = _lex_default_tokens(body_text, lexer_type)
    if not tokens or tokens[0].type != lexer_type.LBrace:
        return ()

    close_index = _find_matching_brace(tokens, 0, lexer_type)
    if close_index is None:
        return ()

    cases: list[SwitchCaseFlow] = []
    case_start: int | None = None
    case_label: str | None = None
    index = 1  # skip opening LBrace

    while index < close_index:
        tok = tokens[index]

        if tok.text in {"case", "default"}:
            # Flush previous case.
            if case_start is not None and case_label is not None:
                case_tokens = tokens[case_start:index]
                case_text = body_text[case_tokens[0].start : case_tokens[-1].stop + 1]
                cases.append(SwitchCaseFlow(
                    label=case_label,
                    steps=_summarize_body_steps(case_text, lexer_type),
                ))
            case_start = None
            case_label = None

            # Extract label text up to and including the Colon.
            label_end = index
            for scan in range(index, close_index):
                if tokens[scan].text == ":":
                    label_end = scan
                    break
            case_label = _compact_label_text(
                body_text[tok.start : tokens[label_end].stop + 1]
            )
            index = label_end + 1
            case_start = index
            continue

        index += 1

    # Flush final case.
    if case_start is not None and case_label is not None:
        case_tokens = tokens[case_start:close_index]
        if case_tokens:
            case_text = body_text[case_tokens[0].start : case_tokens[-1].stop + 1]
            cases.append(SwitchCaseFlow(
                label=case_label,
                steps=_summarize_body_steps(case_text, lexer_type),
            ))

    return tuple(cases)


def _summarize_structured_header(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    lexer_type: object,
) -> str:
    block_range = _find_top_level_code_block(tokens, 1, lexer_type)
    if block_range is None:
        return _compact_label_text(statement_text.strip().removesuffix(";"))
    open_index, _ = block_range
    return _compact_label_text(
        _slice_token_text(statement_text, tokens, base_offset, 0, open_index - 1)
    )


# ---------------------------------------------------------------------------
# Token-level helpers
# ---------------------------------------------------------------------------

def _find_top_level_code_block(
    tokens: tuple[object, ...],
    start_index: int,
    lexer_type: object,
) -> tuple[int, int] | None:
    paren_depth = 0
    square_depth = 0

    for index in range(start_index, len(tokens)):
        token = tokens[index]
        if token.type == lexer_type.LParen:
            paren_depth += 1
        elif token.type == lexer_type.RParen:
            paren_depth = max(paren_depth - 1, 0)
        elif token.type == lexer_type.LBrack:
            square_depth += 1
        elif token.type == lexer_type.RBrack:
            square_depth = max(square_depth - 1, 0)
        elif token.type == lexer_type.LBrace and paren_depth == square_depth == 0:
            close_index = _find_matching_brace(tokens, index, lexer_type)
            if close_index is not None:
                return index, close_index
            return None

    return None


def _slice_token_text(
    statement_text: str,
    tokens: tuple[object, ...],
    base_offset: int,
    start_index: int,
    end_index: int,
) -> str:
    if start_index < 0 or end_index < start_index or end_index >= len(tokens):
        return ""
    start = tokens[start_index].start - base_offset
    end = tokens[end_index].stop + 1 - base_offset
    return statement_text[start:end]


def _compact_label_text(text: str, *, limit: int = _SUMMARY_LABEL_LIMIT) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}..."


def _split_top_level_statement_spans(
    body_text: str,
    lexer_type: object,
) -> tuple[tuple[str, tuple[object, ...], int], ...] | None:
    tokens = _lex_default_tokens(body_text, lexer_type)
    if not tokens or tokens[0].type != lexer_type.LBrace:
        return None

    close_index = _find_matching_brace(tokens, 0, lexer_type)
    if close_index is None:
        return None

    spans: list[tuple[str, tuple[object, ...], int]] = []
    brace_depth = 1
    paren_depth = 0
    square_depth = 0
    statement_start_index: int | None = None

    for index in range(1, close_index):
        token = tokens[index]
        if statement_start_index is None:
            statement_start_index = index

        if token.type == lexer_type.LParen:
            paren_depth += 1
        elif token.type == lexer_type.RParen:
            paren_depth = max(paren_depth - 1, 0)
        elif token.type == lexer_type.LBrack:
            square_depth += 1
        elif token.type == lexer_type.RBrack:
            square_depth = max(square_depth - 1, 0)
        elif token.type == lexer_type.LBrace:
            brace_depth += 1
        elif token.type == lexer_type.RBrace:
            brace_depth -= 1

        next_token = tokens[index + 1] if index + 1 < close_index else None
        at_statement_end = False

        if (
            token.text == ";"
            and brace_depth == 1
            and paren_depth == square_depth == 0
        ):
            at_statement_end = True
        elif (
            next_token is not None
            and brace_depth == 1
            and paren_depth == square_depth == 0
            and next_token.text != "else"
            and next_token.line > token.line
        ):
            at_statement_end = True
        elif next_token is None:
            at_statement_end = True

        if at_statement_end and statement_start_index is not None:
            statement_tokens = tokens[statement_start_index : index + 1]
            statement_text = body_text[
                statement_tokens[0].start : statement_tokens[-1].stop + 1
            ]
            if statement_text.strip():
                spans.append((statement_text, statement_tokens, statement_tokens[0].start))
            statement_start_index = None

    return tuple(spans)


def _structured_token_types(lexer_type: object) -> set[int]:
    return {
        token_type
        for token_type in {
            getattr(lexer_type, "If", None),
            getattr(lexer_type, "For", None),
            getattr(lexer_type, "While", None),
            getattr(lexer_type, "Do", None),
            getattr(lexer_type, "Switch", None),
        }
        if token_type is not None
    }


def _lex_default_tokens(source_text: str, lexer_type: object) -> tuple[object, ...]:
    lexer = lexer_type(InputStream(source_text))
    token_stream = CommonTokenStream(lexer)
    token_stream.fill()
    return tuple(
        token
        for token in token_stream.tokens
        if token.type != Token.EOF and token.channel == Token.DEFAULT_CHANNEL
    )


# ---------------------------------------------------------------------------
# Visitor-based extraction (ANTLR parse tree)
# ---------------------------------------------------------------------------

def _build_control_flow_visitor(visitor_base: type, context: _ExtractorContext) -> type:
    class MetalControlFlowVisitor(visitor_base):
        def __init__(self) -> None:
            super().__init__()
            self.functions: list[FunctionControlFlow] = []
            self._containers: list[str] = []

        # -- Container visitors -------------------------------------------

        def _get_name(self, ctx, default: str) -> str:
            name_ctx = ctx.name()
            if isinstance(name_ctx, list):
                return name_ctx[0].getText() if name_ctx else default
            return name_ctx.getText() if name_ctx is not None else default

        def visitStructDeclaration(self, ctx):
            name = self._get_name(ctx, "struct")
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitClassDeclaration(self, ctx):
            name = self._get_name(ctx, "class")
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitEnumDeclaration(self, ctx):
            name = self._get_name(ctx, "enum")
            return self._with_container(name, lambda: self.visitChildren(ctx))

        def visitNamespaceDefinition(self, ctx):
            name = self._get_name(ctx, "namespace")
            return self._with_container(name, lambda: self.visitChildren(ctx))

        # -- Function visitor ---------------------------------------------

        def visitFunctionDeclaration(self, ctx):
            if ctx.functionBody() is None:
                return None

            name = self._get_name(ctx, "function")
            signature = context.compact(ctx)
            self.functions.append(
                FunctionControlFlow(
                    name=name,
                    signature=signature,
                    container=".".join(self._containers) if self._containers else None,
                    steps=self._extract_function_body(ctx.functionBody()),
                )
            )
            return None

        # -- Helpers -------------------------------------------------------

        def _with_container(self, name: str, callback):
            self._containers.append(name)
            try:
                return callback()
            finally:
                self._containers.pop()

        def _extract_function_body(self, function_body_ctx) -> tuple[ControlFlowStep, ...]:
            if function_body_ctx is None:
                return ()
            # functionBody: LBrace statement* RBrace | ...
            if function_body_ctx.LBrace() is not None:
                steps: list[ControlFlowStep] = []
                for stmt_ctx in (function_body_ctx.statement() or []):
                    extracted = self._extract_statement(stmt_ctx)
                    if extracted is not None:
                        steps.append(extracted)
                return tuple(steps)
            return ()

        def _extract_compound_statement(self, compound_ctx) -> tuple[ControlFlowStep, ...]:
            if compound_ctx is None:
                return ()
            steps: list[ControlFlowStep] = []
            for stmt_ctx in compound_ctx.statement():
                extracted = self._extract_statement(stmt_ctx)
                if extracted is not None:
                    steps.append(extracted)
            return tuple(steps)

        def _extract_statement(self, statement_ctx) -> ControlFlowStep | None:
            if statement_ctx.selectionStatement() is not None:
                return self._extract_selection_statement(statement_ctx.selectionStatement())
            if statement_ctx.iterationStatement() is not None:
                return self._extract_iteration_statement(statement_ctx.iterationStatement())
            if statement_ctx.jumpStatement() is not None:
                return ActionFlowStep(context.compact(statement_ctx.jumpStatement()))
            if statement_ctx.compoundStatement() is not None:
                inner = self._extract_compound_statement(statement_ctx.compoundStatement())
                if inner:
                    return ActionFlowStep("{ ... }")
                return None
            if statement_ctx.declarationStatement() is not None:
                return ActionFlowStep(context.compact(statement_ctx.declarationStatement()))
            if statement_ctx.expressionStatement() is not None:
                expr_stmt = statement_ctx.expressionStatement()
                if expr_stmt.expression() is not None:
                    return ActionFlowStep(context.compact(expr_stmt))
                # Bare semicolon.
                return None
            if statement_ctx.labeledStatement() is not None:
                return self._extract_labeled_statement(statement_ctx.labeledStatement())
            return ActionFlowStep(context.compact(statement_ctx))

        # -- Selection (if / switch) --------------------------------------

        def _extract_selection_statement(self, sel_ctx) -> ControlFlowStep:
            # The grammar has two alternatives in selectionStatement:
            #   If LParen expression RParen statement (Else statement)?
            #   Switch LParen expression RParen LBrace caseGroup* RBrace
            if sel_ctx.If() is not None:
                return self._extract_if_like(sel_ctx)
            return self._extract_switch_like(sel_ctx)

        def _extract_if_like(self, sel_ctx) -> IfFlowStep:
            expr = sel_ctx.expression()
            statements = sel_ctx.statement()

            then_steps: tuple[ControlFlowStep, ...] = ()
            if statements and len(statements) >= 1:
                then_steps = self._extract_statement_as_tuple(statements[0])

            else_steps: tuple[ControlFlowStep, ...] = ()
            if sel_ctx.Else() is not None and len(statements) >= 2:
                else_steps = self._extract_statement_as_tuple(statements[1])

            return IfFlowStep(
                condition=context.compact(expr) if expr is not None else "condition",
                then_steps=then_steps,
                else_steps=else_steps,
            )

        def _extract_statement_as_tuple(self, stmt_ctx) -> tuple[ControlFlowStep, ...]:
            extracted = self._extract_statement(stmt_ctx)
            if extracted is None:
                return ()
            return (extracted,)

        def _extract_switch_like(self, sel_ctx) -> SwitchFlowStep:
            cases: list[SwitchCaseFlowStep] = []
            for case_group_ctx in (sel_ctx.caseGroup() or []):
                cases.append(self._extract_case_group(case_group_ctx))
            
            expr = sel_ctx.expression()
            cond_text = context.compact(expr) if expr is not None else "expression"
            return SwitchFlowStep(
                condition=f"switch ({cond_text})",
                cases=tuple(cases),
            )

        def _extract_case_group(self, case_group_ctx) -> SwitchCaseFlowStep:
            label_ctx = case_group_ctx.caseLabel()
            label = context.compact(label_ctx) if label_ctx is not None else "case"

            steps: tuple[ControlFlowStep, ...] = ()
            stmts = case_group_ctx.statement()
            if stmts:
                step_list: list[ControlFlowStep] = []
                for stmt_ctx in stmts:
                    extracted = self._extract_statement(stmt_ctx)
                    if extracted is not None:
                        step_list.append(extracted)
                steps = tuple(step_list)

            return SwitchCaseFlowStep(label=label, body_steps=steps)

        # -- Iteration (for / while / do-while) ---------------------------

        def _extract_iteration_statement(self, iter_ctx) -> ControlFlowStep:
            if iter_ctx.While() is not None:
                return self._extract_while_statement(iter_ctx)
            if iter_ctx.Do() is not None:
                return self._extract_do_while_statement(iter_ctx)
            return self._extract_for_statement(iter_ctx)

        def _extract_while_statement(self, iter_ctx) -> WhileFlowStep:
            stmt = iter_ctx.statement()
            body_steps = self._extract_statement_as_tuple(stmt) if stmt else ()
            cond_text = context.compact(iter_ctx.expression()) if iter_ctx.expression() is not None else "condition"
            return WhileFlowStep(
                condition=f"while ({cond_text})",
                body_steps=body_steps,
            )

        def _extract_do_while_statement(self, iter_ctx) -> WhileFlowStep:
            stmt = iter_ctx.statement()
            body_steps = self._extract_statement_as_tuple(stmt) if stmt else ()
            exprs = iter_ctx.expression()
            cond_text = "condition"
            if exprs:
                if isinstance(exprs, list):
                    cond_text = context.compact(exprs[-1]) if exprs else "condition"
                else:
                    cond_text = context.compact(exprs)
            return WhileFlowStep(
                condition=f"do {{ ... }} while ({cond_text})",
                body_steps=body_steps,
            )

        def _extract_for_statement(self, iter_ctx) -> ForInFlowStep:
            stmt = iter_ctx.statement()
            body_steps = self._extract_statement_as_tuple(stmt) if stmt else ()

            # Build header from compact text
            header = context.compact(iter_ctx).strip()
            # If header is too long, we might want to truncate, but for now just strip 'for'
            if header.startswith("for"):
                header = header[3:].strip()
            
            # If it contains the body, strip it
            if "{" in header:
                header = header.split("{")[0].strip()
            elif stmt:
                # If there's no brace but there is a statement, strip the statement text
                stmt_text = context.compact(stmt)
                if header.endswith(stmt_text):
                    header = header[:-len(stmt_text)].strip()

            if header.startswith("("):
                header = header[1:]
            if header.endswith(")"):
                header = header[:-1]

            return ForInFlowStep(
                header=header or "item in collection",
                body_steps=body_steps,
            )

        # -- Labeled statement --------------------------------------------

        def _extract_labeled_statement(self, labeled_ctx) -> ControlFlowStep:
            # labeledStatement: name Colon statement
            inner_stmts = labeled_ctx.statement()
            if inner_stmts:
                return self._extract_statement(inner_stmts[0]) or ActionFlowStep("label")
            return ActionFlowStep("label")

    return MetalControlFlowVisitor
