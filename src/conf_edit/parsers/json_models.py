from __future__ import annotations

from dataclasses import dataclass
import json
import textwrap

from conf_edit.domain.errors import DomainError


_JSON_WHITESPACE = " \t\r\n"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class JsonEntry:
    key: str
    raw: str
    span: SourceSpan
    field_count: int


@dataclass(frozen=True, slots=True)
class JsonDocument:
    source: str
    entries: tuple[JsonEntry, ...]
    newline: str
    indent: str
    opening_bracket: int
    closing_bracket: int
    multiline: bool


@dataclass(frozen=True, slots=True)
class JsonDraft:
    key: str
    raw: str
    field_count: int


def _skip_whitespace(source: str, cursor: int) -> int:
    while cursor < len(source) and source[cursor] in _JSON_WHITESPACE:
        cursor += 1
    return cursor


def _error(
    code: str,
    message: str,
    source: str,
    offset: int = 0,
    *,
    status: int = 400,
) -> DomainError:
    safe_offset = min(max(offset, 0), len(source))
    line = source.count("\n", 0, safe_offset) + 1
    last_newline = source.rfind("\n", 0, safe_offset)
    column = safe_offset - last_newline
    return DomainError(
        code,
        message,
        details={"line": line, "column": column},
        status=status,
    )


def _object_key(
    value: dict,
    source: str,
    offset: int,
) -> str:
    if "objectName" not in value:
        raise _error(
            "object_name_missing",
            "对象必须包含 objectName",
            source,
            offset,
        )
    key = value["objectName"]
    if not isinstance(key, str):
        raise _error(
            "object_name_invalid",
            "objectName 必须是字符串",
            source,
            offset,
        )
    if not key.strip():
        raise _error(
            "object_name_empty",
            "objectName 不能为空",
            source,
            offset,
        )
    return key


def parse_json_document(source: str) -> JsonDocument:
    decoder = json.JSONDecoder()
    cursor = _skip_whitespace(source, 0)
    if cursor >= len(source) or source[cursor] != "[":
        raise _error(
            "json_root_not_array",
            "JSON 顶层必须是数组",
            source,
            cursor,
        )
    opening_bracket = cursor
    cursor += 1
    entries: list[JsonEntry] = []
    seen: set[str] = set()

    while True:
        cursor = _skip_whitespace(source, cursor)
        if cursor >= len(source):
            raise _error(
                "json_unclosed_array",
                "JSON 数组没有结束符",
                source,
                cursor,
            )
        if source[cursor] == "]":
            closing_bracket = cursor
            cursor += 1
            break

        start = cursor
        try:
            value, end = decoder.raw_decode(source, cursor)
        except json.JSONDecodeError as exc:
            raise _error(
                "json_syntax",
                f"JSON 语法错误：{exc.msg}",
                source,
                exc.pos,
            ) from exc
        if not isinstance(value, dict):
            raise _error(
                "json_item_not_object",
                "数组元素必须是 JSON 对象",
                source,
                start,
            )
        key = _object_key(value, source, start)
        if key in seen:
            raise _error(
                "object_name_duplicate",
                f"objectName 重复：{key}",
                source,
                start,
            )
        seen.add(key)
        entries.append(
            JsonEntry(
                key=key,
                raw=source[start:end],
                span=SourceSpan(start=start, end=end),
                field_count=len(value),
            )
        )

        cursor = _skip_whitespace(source, end)
        if cursor >= len(source):
            raise _error(
                "json_unclosed_array",
                "JSON 数组没有结束符",
                source,
                cursor,
            )
        if source[cursor] == ",":
            cursor = _skip_whitespace(source, cursor + 1)
            if cursor < len(source) and source[cursor] == "]":
                raise _error(
                    "json_trailing_comma",
                    "JSON 数组不允许尾随逗号",
                    source,
                    cursor - 1,
                )
            continue
        if source[cursor] == "]":
            closing_bracket = cursor
            cursor += 1
            break
        raise _error(
            "json_array_separator",
            "对象之间必须使用逗号分隔",
            source,
            cursor,
        )

    trailing = _skip_whitespace(source, cursor)
    if trailing != len(source):
        raise _error(
            "json_trailing_content",
            "数组结束后存在多余内容",
            source,
            trailing,
        )

    newline = "\r\n" if "\r\n" in source else "\n"
    multiline = "\n" in source[opening_bracket : closing_bracket + 1]
    indent = "  "
    if entries:
        line_start = source.rfind("\n", 0, entries[0].span.start) + 1
        candidate = source[line_start : entries[0].span.start]
        if candidate and not candidate.strip(" \t"):
            indent = candidate

    return JsonDocument(
        source=source,
        entries=tuple(entries),
        newline=newline,
        indent=indent,
        opening_bracket=opening_bracket,
        closing_bracket=closing_bracket,
        multiline=multiline,
    )


def validate_json_object(
    raw: str,
    occupied_keys: set[str],
    original_key: str | None = None,
) -> JsonDraft:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _error(
            "json_syntax",
            f"JSON 语法错误：{exc.msg}",
            raw,
            exc.pos,
        ) from exc
    if not isinstance(value, dict):
        raise _error(
            "json_item_not_object",
            "编辑内容必须是 JSON 对象",
            raw,
        )
    key = _object_key(value, raw, 0)
    if key in occupied_keys and key != original_key:
        raise _error(
            "object_name_duplicate",
            f"objectName 重复：{key}",
            raw,
        )
    return JsonDraft(key=key, raw=raw.strip(), field_count=len(value))


def _normalized_lines(raw: str) -> list[str]:
    normalized = raw.strip().replace("\r\n", "\n").replace("\r", "\n")
    return textwrap.dedent(normalized).split("\n")


def _line_indent(source: str, offset: int, fallback: str) -> str:
    line_start = source.rfind("\n", 0, offset) + 1
    candidate = source[line_start:offset]
    return candidate if candidate and not candidate.strip(" \t") else fallback


def _replacement_text(
    raw: str,
    *,
    newline: str,
    continuation_indent: str,
) -> str:
    lines = _normalized_lines(raw)
    if len(lines) == 1:
        return lines[0]
    return lines[0] + newline + newline.join(
        continuation_indent + line for line in lines[1:]
    )


def replace_json_object(
    document: JsonDocument,
    original_key: str,
    raw: str,
) -> str:
    entry = next(
        (item for item in document.entries if item.key == original_key),
        None,
    )
    if entry is None:
        raise DomainError(
            "object_not_found",
            f"对象不存在：{original_key}",
            status=404,
        )
    validate_json_object(
        raw,
        {item.key for item in document.entries},
        original_key=original_key,
    )
    replacement = _replacement_text(
        raw,
        newline=document.newline,
        continuation_indent=_line_indent(
            document.source,
            entry.span.start,
            document.indent,
        ),
    )
    result = (
        document.source[: entry.span.start]
        + replacement
        + document.source[entry.span.end :]
    )
    parse_json_document(result)
    return result


def _inserted_text(document: JsonDocument, raw: str) -> str:
    lines = _normalized_lines(raw)
    if not document.multiline:
        return document.newline.join(lines)
    return document.newline.join(
        document.indent + line for line in lines
    )


def insert_json_object(document: JsonDocument, raw: str) -> str:
    validate_json_object(
        raw,
        {item.key for item in document.entries},
    )
    if document.entries:
        last = document.entries[-1]
        if document.multiline:
            insertion = "," + document.newline + _inserted_text(document, raw)
        else:
            insertion = ", " + raw.strip()
        result = (
            document.source[: last.span.end]
            + insertion
            + document.source[last.span.end :]
        )
    elif document.multiline:
        inner = document.source[
            document.opening_bracket + 1 : document.closing_bracket
        ]
        closing_indent = inner.rsplit(document.newline, 1)[-1]
        replacement = (
            document.newline
            + _inserted_text(document, raw)
            + document.newline
            + closing_indent
        )
        result = (
            document.source[: document.opening_bracket + 1]
            + replacement
            + document.source[document.closing_bracket :]
        )
    else:
        result = (
            document.source[: document.opening_bracket + 1]
            + raw.strip()
            + document.source[document.closing_bracket :]
        )
    parse_json_document(result)
    return result


def delete_json_object(document: JsonDocument, key: str) -> str:
    index = next(
        (
            position
            for position, item in enumerate(document.entries)
            if item.key == key
        ),
        -1,
    )
    if index < 0:
        raise DomainError(
            "object_not_found",
            f"对象不存在：{key}",
            status=404,
        )

    entry = document.entries[index]
    if len(document.entries) == 1:
        if document.multiline:
            inner = document.source[
                document.opening_bracket + 1 : document.closing_bracket
            ]
            closing_indent = inner.rsplit(document.newline, 1)[-1]
            replacement = document.newline + closing_indent
        else:
            replacement = ""
        result = (
            document.source[: document.opening_bracket + 1]
            + replacement
            + document.source[document.closing_bracket :]
        )
    elif index < len(document.entries) - 1:
        next_entry = document.entries[index + 1]
        result = (
            document.source[: entry.span.start]
            + document.source[next_entry.span.start :]
        )
    else:
        previous = document.entries[index - 1]
        result = (
            document.source[: previous.span.end]
            + document.source[entry.span.end :]
        )

    parse_json_document(result)
    return result
