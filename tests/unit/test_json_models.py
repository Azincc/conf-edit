import pytest

from conf_edit.domain.errors import DomainError
from conf_edit.parsers.json_models import (
    delete_json_object,
    insert_json_object,
    parse_json_document,
    replace_json_object,
    validate_json_object,
)


def test_parse_returns_named_entries_and_source_ranges() -> None:
    source = (
        '[\n'
        '  {"objectName":"User","enabled":true},\n'
        '  {"objectName":"Order","fields":[]}\n'
        ']'
    )

    document = parse_json_document(source)

    assert [item.key for item in document.entries] == ["User", "Order"]
    assert document.entries[0].field_count == 2
    assert source[
        document.entries[1].span.start : document.entries[1].span.end
    ] == '{"objectName":"Order","fields":[]}'
    assert document.newline == "\n"
    assert document.indent == "  "


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ('{"objectName":"User"}', "json_root_not_array"),
        ("[1]", "json_item_not_object"),
        ("[{}]", "object_name_missing"),
        ('[{"objectName":" "}]', "object_name_empty"),
        (
            '[{"objectName":"User"},{"objectName":"User"}]',
            "object_name_duplicate",
        ),
        ('[{"objectName":"User"},]', "json_trailing_comma"),
        ('[{"objectName":"User"}] trailing', "json_trailing_content"),
    ],
)
def test_invalid_model_file_reports_stable_code(
    source: str, code: str
) -> None:
    with pytest.raises(DomainError) as captured:
        parse_json_document(source)

    assert captured.value.code == code


def test_syntax_error_has_one_based_line_and_column() -> None:
    with pytest.raises(DomainError) as captured:
        parse_json_document('[\n  {"objectName": "User",}\n]')

    assert captured.value.code == "json_syntax"
    assert captured.value.details["line"] == 2
    assert captured.value.details["column"] > 1


def test_nested_values_escaped_quotes_and_case_sensitive_names_are_valid() -> None:
    source = (
        '[{"objectName":"User","nested":{"text":"brace } and \\"quote\\""}},'
        '{"objectName":"user","items":[{"x":1}]}]'
    )

    document = parse_json_document(source)

    assert [item.key for item in document.entries] == ["User", "user"]


def test_validate_object_rejects_duplicate_except_original_key() -> None:
    assert (
        validate_json_object(
            '{"objectName":"User","enabled":false}',
            {"User", "Order"},
            original_key="User",
        ).key
        == "User"
    )

    with pytest.raises(DomainError) as captured:
        validate_json_object(
            '{"objectName":"Order"}',
            {"User", "Order"},
            original_key="User",
        )

    assert captured.value.code == "object_name_duplicate"


def test_replace_changes_only_target_object_text() -> None:
    source = (
        '[\n'
        '  {"objectName":"A","x":1},\n'
        '  { "objectName": "B", "x": 2 }\n'
        ']\n'
    )

    result = replace_json_object(
        parse_json_document(source),
        "A",
        '{\n  "objectName": "A",\n  "x": 9\n}',
    )

    assert '{ "objectName": "B", "x": 2 }' in result
    assert result.endswith("]\n")
    assert '"x": 9' in result
    assert [item.key for item in parse_json_document(result).entries] == [
        "A",
        "B",
    ]


def test_insert_into_multiline_document_keeps_crlf() -> None:
    source = '[\r\n  {"objectName":"A"}\r\n]\r\n'

    result = insert_json_object(
        parse_json_document(source),
        '{"objectName":"B","中文":true}',
    )

    assert "\r\n" in result
    assert "\n" not in result.replace("\r\n", "")
    assert [item.key for item in parse_json_document(result).entries] == [
        "A",
        "B",
    ]


def test_insert_into_empty_single_line_document_keeps_single_line_style() -> None:
    result = insert_json_object(
        parse_json_document("[]"),
        '{"objectName":"Only"}',
    )

    assert result == '[{"objectName":"Only"}]'


@pytest.mark.parametrize("key", ["A", "B", "C"])
def test_delete_first_middle_or_last_object(key: str) -> None:
    source = (
        '[\n'
        '  {"objectName":"A","raw":"keep-a"},\n'
        '  {"objectName":"B","raw":"keep-b"},\n'
        '  {"objectName":"C","raw":"keep-c"}\n'
        ']\n'
    )

    result = delete_json_object(parse_json_document(source), key)
    document = parse_json_document(result)

    assert key not in [item.key for item in document.entries]
    for untouched in {"A", "B", "C"} - {key}:
        assert f'"raw":"keep-{untouched.lower()}"' in result


def test_delete_only_object_leaves_valid_empty_array() -> None:
    result = delete_json_object(
        parse_json_document('[\n  {"objectName":"Only"}\n]\n'),
        "Only",
    )

    assert parse_json_document(result).entries == ()


def test_missing_object_operations_return_not_found() -> None:
    document = parse_json_document('[{"objectName":"A"}]')

    with pytest.raises(DomainError) as captured:
        replace_json_object(document, "Missing", '{"objectName":"Missing"}')

    assert captured.value.code == "object_not_found"
    assert captured.value.status == 404
