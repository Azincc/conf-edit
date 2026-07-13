from pathlib import Path

import pytest

from conf_edit.domain.errors import DomainError
from conf_edit.parsers.sql_models import (
    SqlKind,
    delete_sql_table,
    insert_sql_table,
    parse_sql_document,
    replace_sql_table,
    split_sql_statements,
    validate_sql_draft,
)


def test_splitter_ignores_semicolons_inside_mysql_tokens() -> None:
    source = (
        "-- note; keep\n"
        "CREATE TABLE `user;profile` (\n"
        "  name varchar(50) COMMENT 'A;B'\n"
        ") COMMENT='table;note';\n"
        "/* init; keep */ INSERT INTO `user;profile` (name) VALUES ('C;D');"
    )

    statements = split_sql_statements(source)

    assert len(statements) == 2
    assert statements[0].raw.startswith("-- note; keep")
    assert statements[1].raw.startswith("\n/* init; keep */")


@pytest.mark.parametrize(
    "source",
    [
        "CREATE TABLE t (name varchar(10) COMMENT 'open);",
        "CREATE TABLE t (id int); /* open",
        "CREATE TABLE `open (id int);",
    ],
)
def test_splitter_rejects_unclosed_tokens(source: str) -> None:
    with pytest.raises(DomainError) as captured:
        split_sql_statements(source)

    assert captured.value.code == "sql_unclosed_token"


def test_parse_groups_create_and_inserts_with_comments() -> None:
    source = Path("tests/fixtures/sql/valid_schema.sql").read_text(
        encoding="utf-8"
    )

    document = parse_sql_document(source)

    assert len(document.tables) == 1
    table = document.tables[0]
    assert table.name == "user_profile"
    assert table.normalized_name == "user_profile"
    assert table.field_count == 2
    assert table.table_comment == "用户资料"
    assert table.field_comments == (("id", "主键"), ("name", "显示名称"))
    assert len(table.insert_statements) == 1
    assert table.create_statement.kind is SqlKind.CREATE_TABLE
    assert table.insert_statements[0].kind is SqlKind.INSERT


@pytest.mark.parametrize(
    "leading_comment",
    [
        "-- 用户资料表",
        "# 用户资料表",
        "/* 用户资料表 */",
    ],
)
def test_parse_if_not_exists_keeps_leading_mysql_comments(
    leading_comment: str,
) -> None:
    create_sql = (
        f"{leading_comment}\n"
        "CREATE TABLE IF NOT EXISTS user_profile (\n"
        "  id bigint\n"
        ");"
    )
    source = "CREATE TABLE first_table (id int);\n\n" + create_sql

    document = parse_sql_document(source)

    assert [table.name for table in document.tables] == [
        "first_table",
        "user_profile",
    ]
    table = document.tables[1]
    assert table.create_statement.kind is SqlKind.CREATE_TABLE
    assert table.create_statement.raw.strip() == create_sql
    assert document.unmanaged == ()
    assert validate_sql_draft(
        table.create_statement.raw,
        "",
        {"first_table"},
    ).name == "user_profile"


def test_unmanaged_valid_statements_are_preserved() -> None:
    source = (
        "SET sql_mode = 'STRICT_ALL_TABLES';\n"
        "CREATE TABLE t (id int);\n"
    )

    document = parse_sql_document(source)

    assert len(document.unmanaged) == 1
    assert "SET sql_mode" in document.unmanaged[0].raw


def test_duplicate_create_is_case_insensitive() -> None:
    source = "CREATE TABLE UserTable (id int); CREATE TABLE usertable (id int);"

    with pytest.raises(DomainError) as captured:
        parse_sql_document(source)

    assert captured.value.code == "table_name_duplicate"


def test_orphan_insert_is_rejected() -> None:
    with pytest.raises(DomainError) as captured:
        parse_sql_document("INSERT INTO missing_table (id) VALUES (1);")

    assert captured.value.code == "insert_without_create"


def test_delimiter_is_explicitly_unsupported() -> None:
    with pytest.raises(DomainError) as captured:
        parse_sql_document(
            "DELIMITER $$\nCREATE PROCEDURE p() BEGIN SELECT 1; END$$"
        )

    assert captured.value.code == "sql_delimiter_unsupported"


def test_invalid_mysql_syntax_reports_sql_syntax() -> None:
    with pytest.raises(DomainError) as captured:
        parse_sql_document("CREATE TABLE broken (id int,,);")

    assert captured.value.code == "sql_syntax"
    assert captured.value.details["statement"] == 1


def test_composite_primary_key_is_not_treated_as_empty_table_item() -> None:
    document = parse_sql_document(
        "-- ConfEdit MySQL 示例：部门表\n"
        "CREATE TABLE `demo_department` (\n"
        "  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '部门主键',\n"
        "  `department_code` VARCHAR(32) NOT NULL COMMENT '部门编码',\n"
        "  `department_name` VARCHAR(100) NOT NULL COMMENT '部门名称',\n"
        "  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用：1 是，0 否',\n"
        "  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',\n"
        "  `update_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',\n"
        "  PRIMARY KEY (`id`,`department_code`,`department_name`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='示例部门表';"
    )

    assert document.tables[0].name == "demo_department"


@pytest.mark.parametrize(
    ("insert_sql", "code"),
    [
        (
            "INSERT INTO t (id, name) VALUES (1);",
            "insert_value_count",
        ),
        (
            "INSERT INTO t (id, id) VALUES (1, 2);",
            "insert_duplicate_column",
        ),
        (
            "INSERT INTO t (id, missing) VALUES (1, 2);",
            "insert_unknown_column",
        ),
        (
            "INSERT INTO t VALUES (1);",
            "insert_value_count",
        ),
    ],
)
def test_validate_insert_against_create(
    insert_sql: str, code: str
) -> None:
    with pytest.raises(DomainError) as captured:
        validate_sql_draft(
            "CREATE TABLE t (id bigint, name varchar(10));",
            insert_sql,
            set(),
        )

    assert captured.value.code == code


def test_validate_rejects_insert_target_different_from_create() -> None:
    with pytest.raises(DomainError) as captured:
        validate_sql_draft(
            "CREATE TABLE t (id int);",
            "INSERT INTO other (id) VALUES (1);",
            set(),
        )

    assert captured.value.code == "insert_table_mismatch"


def test_replace_preserves_other_table_and_unmanaged_text() -> None:
    source = (
        "SET sql_mode = 'STRICT_ALL_TABLES';\n"
        "CREATE TABLE a (id bigint);\n"
        "\n-- keep spacing\nCREATE TABLE b ( id int );\n"
        "INSERT INTO a (id) VALUES (1);\n"
    )
    untouched = "\n-- keep spacing\nCREATE TABLE b ( id int );"

    result = replace_sql_table(
        parse_sql_document(source),
        "a",
        "CREATE TABLE a (id bigint, name varchar(20));",
        "INSERT INTO a (id, name) VALUES (1, 'A');",
    )

    assert untouched in result
    assert "SET sql_mode = 'STRICT_ALL_TABLES';" in result
    parsed = parse_sql_document(result)
    assert next(table for table in parsed.tables if table.name == "a").field_count == 2


def test_replace_can_rename_table_and_requires_matching_inserts() -> None:
    document = parse_sql_document(
        "CREATE TABLE old_name (id int);"
        "INSERT INTO old_name (id) VALUES (1);"
    )

    result = replace_sql_table(
        document,
        "old_name",
        "CREATE TABLE new_name (id int);",
        "INSERT INTO new_name (id) VALUES (1);",
    )

    assert [table.name for table in parse_sql_document(result).tables] == [
        "new_name"
    ]


def test_insert_and_delete_table_objects() -> None:
    source = "CREATE TABLE a (id int);\n"

    inserted = insert_sql_table(
        parse_sql_document(source),
        "CREATE TABLE b (id int, name varchar(20));",
        "INSERT INTO b (id, name) VALUES (1, 'B');",
    )
    assert [table.name for table in parse_sql_document(inserted).tables] == [
        "a",
        "b",
    ]

    deleted = delete_sql_table(parse_sql_document(inserted), "a")

    assert [table.name for table in parse_sql_document(deleted).tables] == [
        "b"
    ]
    assert "INSERT INTO b" in deleted


def test_delete_missing_table_returns_not_found() -> None:
    with pytest.raises(DomainError) as captured:
        delete_sql_table(
            parse_sql_document("CREATE TABLE a (id int);"),
            "missing",
        )

    assert captured.value.code == "table_not_found"
    assert captured.value.status == 404
