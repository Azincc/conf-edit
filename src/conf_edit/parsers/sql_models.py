from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

import sqlglot
from sqlglot import exp

from conf_edit.domain.errors import DomainError
from conf_edit.parsers.json_models import SourceSpan


class SqlKind(StrEnum):
    CREATE_TABLE = "create_table"
    INSERT = "insert"
    UNMANAGED = "unmanaged"


@dataclass(frozen=True, slots=True)
class SqlStatement:
    raw: str
    span: SourceSpan
    kind: SqlKind = SqlKind.UNMANAGED
    table_name: str | None = None


@dataclass(frozen=True, slots=True)
class SqlTable:
    name: str
    normalized_name: str
    create_statement: SqlStatement
    insert_statements: tuple[SqlStatement, ...]
    field_count: int
    table_comment: str | None
    field_comments: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SqlDocument:
    source: str
    statements: tuple[SqlStatement, ...]
    tables: tuple[SqlTable, ...]
    unmanaged: tuple[SqlStatement, ...]
    newline: str


@dataclass(frozen=True, slots=True)
class SqlDraft:
    name: str
    normalized_name: str
    create_sql: str
    insert_sql: str


@dataclass(frozen=True, slots=True)
class _CreateInfo:
    name: str
    columns: tuple[str, ...]
    table_comment: str | None
    field_comments: tuple[tuple[str, str], ...]


def split_sql_statements(source: str) -> tuple[SqlStatement, ...]:
    statements: list[SqlStatement] = []
    start = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    cursor = 0

    while cursor < len(source):
        char = source[cursor]
        pair = source[cursor : cursor + 2]

        if line_comment:
            if char in "\r\n":
                line_comment = False
        elif block_comment:
            if pair == "*/":
                block_comment = False
                cursor += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif char == "\\" and quote in {"'", '"'}:
                escaped = True
            elif char == quote:
                if cursor + 1 < len(source) and source[cursor + 1] == quote:
                    cursor += 1
                else:
                    quote = None
        elif pair == "/*":
            block_comment = True
            cursor += 1
        elif char == "#":
            line_comment = True
        elif pair == "--" and (
            cursor + 2 >= len(source) or source[cursor + 2].isspace()
        ):
            line_comment = True
            cursor += 1
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == ";":
            end = cursor + 1
            raw = source[start:end]
            if raw.strip():
                statements.append(
                    SqlStatement(raw=raw, span=SourceSpan(start, end))
                )
            start = end
        cursor += 1

    if quote is not None or block_comment:
        raise DomainError(
            "sql_unclosed_token",
            "SQL 中存在未闭合的字符串、标识符或块注释",
        )

    tail = source[start:]
    if tail.strip():
        statements.append(
            SqlStatement(raw=tail, span=SourceSpan(start, len(source)))
        )
    return tuple(statements)


def _comment_only(raw: str) -> bool:
    value = re.sub(r"(?s)/\*.*?\*/", "", raw)
    value = re.sub(r"(?m)^\s*(?:--(?=\s|$)|#).*$", "", value)
    return not value.strip(" \t\r\n;")


def _leading_managed_keyword(raw: str) -> str | None:
    value = raw
    while True:
        stripped = value.lstrip()
        if stripped.startswith("/*"):
            end = stripped.find("*/", 2)
            if end < 0:
                return None
            value = stripped[end + 2 :]
            continue
        if stripped.startswith("#"):
            split = re.split(r"\r?\n", stripped, maxsplit=1)
            value = split[1] if len(split) == 2 else ""
            continue
        if stripped.startswith("--") and (
            len(stripped) == 2 or stripped[2].isspace()
        ):
            split = re.split(r"\r?\n", stripped, maxsplit=1)
            value = split[1] if len(split) == 2 else ""
            continue
        break
    match = re.match(r"(?is)(CREATE\s+TABLE|INSERT\s+INTO)\b", stripped)
    return match.group(1).upper() if match else None


def _has_neutral_double_comma(raw: str) -> bool:
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    previous_significant: str | None = None
    cursor = 0
    while cursor < len(raw):
        char = raw[cursor]
        pair = raw[cursor : cursor + 2]
        if line_comment:
            if char in "\r\n":
                line_comment = False
        elif block_comment:
            if pair == "*/":
                block_comment = False
                cursor += 1
        elif quote is not None:
            if escaped:
                escaped = False
            elif char == "\\" and quote in {"'", '"'}:
                escaped = True
            elif char == quote:
                if cursor + 1 < len(raw) and raw[cursor + 1] == quote:
                    cursor += 1
                else:
                    quote = None
        elif pair == "/*":
            block_comment = True
            cursor += 1
        elif char == "#":
            line_comment = True
        elif pair == "--" and (
            cursor + 2 >= len(raw) or raw[cursor + 2].isspace()
        ):
            line_comment = True
            cursor += 1
        elif char in {"'", '"', "`"}:
            quote = char
        elif not char.isspace():
            if char == "," and previous_significant == ",":
                return True
            previous_significant = char
        cursor += 1
    return False


def _parse_tree(
    statement: SqlStatement,
    statement_number: int,
) -> exp.Expression | None:
    if _comment_only(statement.raw):
        return None
    keyword = _leading_managed_keyword(statement.raw)
    if keyword == "CREATE TABLE" and _has_neutral_double_comma(statement.raw):
        raise DomainError(
            "sql_syntax",
            "MySQL 语法错误：字段或约束之间存在空项",
            details={"statement": statement_number},
        )
    try:
        tree = sqlglot.parse_one(statement.raw, read="mysql")
    except sqlglot.errors.ParseError as exc:
        details: dict[str, int | str] = {"statement": statement_number}
        if exc.errors:
            first = exc.errors[0]
            if first.get("line") is not None:
                details["line"] = first["line"]
            if first.get("col") is not None:
                details["column"] = first["col"]
        raise DomainError(
            "sql_syntax",
            f"MySQL 语法错误：{exc}",
            details=details,
        ) from exc

    if keyword == "CREATE TABLE" and not (
        isinstance(tree, exp.Create)
        and str(tree.args.get("kind", "")).upper() == "TABLE"
    ):
        raise DomainError(
            "sql_syntax",
            "MySQL 建表语句无法识别",
            details={"statement": statement_number},
        )
    if keyword == "INSERT INTO" and not isinstance(tree, exp.Insert):
        raise DomainError(
            "sql_syntax",
            "MySQL INSERT 语句无法识别",
            details={"statement": statement_number},
        )
    return tree


def _table_name(tree: exp.Expression) -> str:
    table = tree.find(exp.Table)
    if table is None or not table.name:
        raise DomainError("sql_table_missing", "SQL 语句缺少表名")
    return table.name


def _literal_text(value: exp.Expression | None) -> str | None:
    if isinstance(value, exp.Literal):
        return str(value.this)
    return None


def _create_info(tree: exp.Create) -> _CreateInfo:
    name = _table_name(tree)
    schema = tree.this if isinstance(tree.this, exp.Schema) else None
    column_defs = (
        [
            item
            for item in schema.expressions
            if isinstance(item, exp.ColumnDef)
        ]
        if schema is not None
        else []
    )
    columns = tuple(column.name for column in column_defs)

    field_comments: list[tuple[str, str]] = []
    for column in column_defs:
        for constraint in column.args.get("constraints") or []:
            kind = constraint.args.get("kind")
            if isinstance(kind, exp.CommentColumnConstraint):
                comment = _literal_text(kind.this)
                if comment is not None:
                    field_comments.append((column.name, comment))

    table_comment = None
    properties = tree.args.get("properties")
    if isinstance(properties, exp.Properties):
        for property_item in properties.expressions:
            if isinstance(property_item, exp.SchemaCommentProperty):
                table_comment = _literal_text(property_item.this)
                break

    return _CreateInfo(
        name=name,
        columns=columns,
        table_comment=table_comment,
        field_comments=tuple(field_comments),
    )


def _insert_target_and_columns(
    tree: exp.Insert,
) -> tuple[str, tuple[str, ...]]:
    target = tree.this
    if isinstance(target, exp.Schema):
        table = target.this
        columns = tuple(item.name for item in target.expressions)
    else:
        table = target
        columns = ()
    if not isinstance(table, exp.Table) or not table.name:
        raise DomainError("sql_table_missing", "INSERT 语句缺少目标表")
    return table.name, columns


def _validate_insert(
    tree: exp.Insert,
    *,
    create_name: str,
    create_columns: tuple[str, ...],
) -> None:
    target_name, explicit_columns = _insert_target_and_columns(tree)
    if target_name.casefold() != create_name.casefold():
        raise DomainError(
            "insert_table_mismatch",
            "初始化 INSERT 的目标表与建表语句不一致",
        )
    columns = explicit_columns or create_columns
    normalized_columns = [name.casefold() for name in columns]
    if len(normalized_columns) != len(set(normalized_columns)):
        raise DomainError(
            "insert_duplicate_column",
            "INSERT 字段列表包含重复字段",
        )
    create_names = {name.casefold() for name in create_columns}
    for name in explicit_columns:
        if name.casefold() not in create_names:
            raise DomainError(
                "insert_unknown_column",
                f"INSERT 字段不存在：{name}",
            )

    values = tree.expression
    if not isinstance(values, exp.Values):
        raise DomainError(
            "insert_values_required",
            "初始化语句只支持 INSERT ... VALUES",
        )
    for row in values.expressions:
        expressions = row.expressions if isinstance(row, exp.Tuple) else [row]
        if len(expressions) != len(columns):
            raise DomainError(
                "insert_value_count",
                "INSERT 字段数量和值数量不一致",
            )


def parse_sql_document(source: str) -> SqlDocument:
    if re.search(r"(?im)^\s*DELIMITER\b", source):
        raise DomainError(
            "sql_delimiter_unsupported",
            "首版不支持 DELIMITER、存储过程或自定义分隔符",
        )
    raw_statements = split_sql_statements(source)
    classified: list[SqlStatement] = []
    trees: dict[int, exp.Expression] = {}
    create_info_by_name: dict[str, _CreateInfo] = {}
    create_statement_by_name: dict[str, SqlStatement] = {}
    create_order: list[str] = []
    unmanaged: list[SqlStatement] = []

    for number, statement in enumerate(raw_statements, start=1):
        tree = _parse_tree(statement, number)
        if tree is None:
            classified.append(statement)
            unmanaged.append(statement)
            continue
        trees[statement.span.start] = tree
        if isinstance(tree, exp.Create) and str(
            tree.args.get("kind", "")
        ).upper() == "TABLE":
            info = _create_info(tree)
            normalized = info.name.casefold()
            if normalized in create_info_by_name:
                raise DomainError(
                    "table_name_duplicate",
                    f"建表语句重复：{info.name}",
                    details={"statement": number},
                )
            item = SqlStatement(
                raw=statement.raw,
                span=statement.span,
                kind=SqlKind.CREATE_TABLE,
                table_name=info.name,
            )
            classified.append(item)
            create_info_by_name[normalized] = info
            create_statement_by_name[normalized] = item
            create_order.append(normalized)
        elif isinstance(tree, exp.Insert):
            name, _ = _insert_target_and_columns(tree)
            classified.append(
                SqlStatement(
                    raw=statement.raw,
                    span=statement.span,
                    kind=SqlKind.INSERT,
                    table_name=name,
                )
            )
        else:
            classified.append(statement)
            unmanaged.append(statement)

    inserts_by_name: dict[str, list[SqlStatement]] = {
        name: [] for name in create_order
    }
    for statement in classified:
        if statement.kind is not SqlKind.INSERT:
            continue
        normalized = (statement.table_name or "").casefold()
        if normalized not in create_info_by_name:
            raise DomainError(
                "insert_without_create",
                f"INSERT 找不到对应建表语句：{statement.table_name}",
            )
        tree = trees[statement.span.start]
        assert isinstance(tree, exp.Insert)
        info = create_info_by_name[normalized]
        _validate_insert(
            tree,
            create_name=info.name,
            create_columns=info.columns,
        )
        inserts_by_name[normalized].append(statement)

    tables = tuple(
        SqlTable(
            name=create_info_by_name[name].name,
            normalized_name=name,
            create_statement=create_statement_by_name[name],
            insert_statements=tuple(inserts_by_name[name]),
            field_count=len(create_info_by_name[name].columns),
            table_comment=create_info_by_name[name].table_comment,
            field_comments=create_info_by_name[name].field_comments,
        )
        for name in create_order
    )
    return SqlDocument(
        source=source,
        statements=tuple(classified),
        tables=tables,
        unmanaged=tuple(unmanaged),
        newline="\r\n" if "\r\n" in source else "\n",
    )


def validate_sql_draft(
    create_sql: str,
    insert_sql: str,
    occupied_names: set[str],
    original_name: str | None = None,
) -> SqlDraft:
    create_parts = split_sql_statements(create_sql)
    if len(create_parts) != 1:
        raise DomainError(
            "create_statement_required",
            "建表编辑器必须且只能包含一条 CREATE TABLE",
        )
    create_tree = _parse_tree(create_parts[0], 1)
    if not (
        isinstance(create_tree, exp.Create)
        and str(create_tree.args.get("kind", "")).upper() == "TABLE"
    ):
        raise DomainError(
            "create_statement_required",
            "建表编辑器必须包含 CREATE TABLE",
        )
    info = _create_info(create_tree)
    normalized = info.name.casefold()
    original_normalized = original_name.casefold() if original_name else None
    if normalized in {name.casefold() for name in occupied_names} and (
        normalized != original_normalized
    ):
        raise DomainError(
            "table_name_duplicate",
            f"表名重复：{info.name}",
        )

    if insert_sql.strip():
        for number, statement in enumerate(
            split_sql_statements(insert_sql),
            start=1,
        ):
            tree = _parse_tree(statement, number)
            if tree is None:
                continue
            if not isinstance(tree, exp.Insert):
                raise DomainError(
                    "insert_statement_required",
                    "初始化编辑器只允许 INSERT INTO 语句",
                    details={"statement": number},
                )
            _validate_insert(
                tree,
                create_name=info.name,
                create_columns=info.columns,
            )

    return SqlDraft(
        name=info.name,
        normalized_name=normalized,
        create_sql=create_sql.strip(),
        insert_sql=insert_sql.strip(),
    )


def _ensure_semicolon(value: str) -> str:
    stripped = value.rstrip()
    return stripped if stripped.endswith(";") else stripped + ";"


def _insert_block(insert_sql: str, newline: str) -> str:
    if not insert_sql.strip():
        return ""
    return newline.join(
        _ensure_semicolon(statement.raw.strip())
        for statement in split_sql_statements(insert_sql)
        if statement.raw.strip()
    )


def _apply_replacements(
    source: str,
    replacements: list[tuple[int, int, str]],
) -> str:
    result = source
    for start, end, value in sorted(
        replacements,
        key=lambda item: item[0],
        reverse=True,
    ):
        result = result[:start] + value + result[end:]
    return result


def replace_sql_table(
    document: SqlDocument,
    original_name: str,
    create_sql: str,
    insert_sql: str,
) -> str:
    target = next(
        (
            table
            for table in document.tables
            if table.normalized_name == original_name.casefold()
        ),
        None,
    )
    if target is None:
        raise DomainError(
            "table_not_found",
            f"表不存在：{original_name}",
            status=404,
        )
    draft = validate_sql_draft(
        create_sql,
        insert_sql,
        {table.normalized_name for table in document.tables},
        original_name=target.normalized_name,
    )
    block = _ensure_semicolon(draft.create_sql)
    inserts = _insert_block(draft.insert_sql, document.newline)
    if inserts:
        block += document.newline + inserts
    replacements = [
        (
            target.create_statement.span.start,
            target.create_statement.span.end,
            block,
        )
    ]
    replacements.extend(
        (statement.span.start, statement.span.end, "")
        for statement in target.insert_statements
    )
    result = _apply_replacements(document.source, replacements)
    parse_sql_document(result)
    return result


def insert_sql_table(
    document: SqlDocument,
    create_sql: str,
    insert_sql: str,
) -> str:
    draft = validate_sql_draft(
        create_sql,
        insert_sql,
        {table.normalized_name for table in document.tables},
    )
    block = _ensure_semicolon(draft.create_sql)
    inserts = _insert_block(draft.insert_sql, document.newline)
    if inserts:
        block += document.newline + inserts

    if not document.source:
        separator = ""
    elif document.source.endswith(document.newline * 2):
        separator = ""
    elif document.source.endswith(document.newline):
        separator = document.newline
    else:
        separator = document.newline * 2
    result = document.source + separator + block + document.newline
    parse_sql_document(result)
    return result


def delete_sql_table(document: SqlDocument, name: str) -> str:
    target = next(
        (
            table
            for table in document.tables
            if table.normalized_name == name.casefold()
        ),
        None,
    )
    if target is None:
        raise DomainError(
            "table_not_found",
            f"表不存在：{name}",
            status=404,
        )
    replacements = [
        (
            target.create_statement.span.start,
            target.create_statement.span.end,
            "",
        )
    ]
    replacements.extend(
        (statement.span.start, statement.span.end, "")
        for statement in target.insert_statements
    )
    result = _apply_replacements(document.source, replacements)
    parse_sql_document(result)
    return result
