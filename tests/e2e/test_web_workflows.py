import re

from playwright.sync_api import expect


def _replace_editor_text(editor, value: str) -> None:
    editor.evaluate(
        "(node, content) => "
        "node.closest('.CodeMirror').CodeMirror.setValue(content)",
        value,
    )


def _editor_value(editor) -> str:
    return editor.evaluate(
        "node => node.closest('.CodeMirror').CodeMirror.getValue()"
    )


def test_workspace_lists_files_and_objects(page, running_app) -> None:
    page.goto(running_app.url)

    expect(page).to_have_title("配置对象管理器")
    expect(page.get_by_role("button", name="用户模型")).to_be_visible()
    expect(page.get_by_role("button", name="基础表")).to_be_visible()

    page.get_by_role("button", name="用户模型").click()

    expect(page.get_by_role("heading", name="用户模型")).to_be_visible()
    expect(page.get_by_role("button", name="编辑 User")).to_be_visible()


def test_json_object_can_be_edited_from_drawer(
    page, running_app, json_file
) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()

    editor = page.get_by_role("textbox", name="JSON 对象")
    _replace_editor_text(
        editor,
        '{"objectName":"User","enabled":false}',
    )
    page.get_by_role("button", name="校验").click()

    expect(page.get_by_text("JSON 校验通过")).to_be_visible()
    page.get_by_role("button", name="保存").click()

    expect(page.get_by_text("保存成功")).to_be_visible()
    assert '"enabled":false' in json_file.read_text(encoding="utf-8")


def test_json_object_can_be_created(page, running_app, json_file) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="新增对象").click()

    editor = page.get_by_role("textbox", name="JSON 对象")
    _replace_editor_text(
        editor,
        '{"objectName":"Order","fields":[]}',
    )
    page.get_by_role("button", name="校验").click()
    expect(page.get_by_text("JSON 校验通过")).to_be_visible()
    page.get_by_role("button", name="保存").click()

    expect(page.get_by_text("保存成功")).to_be_visible()
    expect(page.get_by_role("button", name="编辑 Order")).to_be_visible()
    assert '"objectName":"Order"' in json_file.read_text(encoding="utf-8")


def test_json_object_can_be_formatted(page, running_app) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()

    editor = page.get_by_role("textbox", name="JSON 对象")
    _replace_editor_text(
        editor,
        '{"objectName":"User","profile":{"enabled":true}}',
    )
    page.get_by_role("button", name="格式化 JSON").click()

    assert _editor_value(editor) == (
        '{\n  "objectName": "User",\n  "profile": {\n'
        '    "enabled": true\n  }\n}'
    )


def test_invalid_json_cannot_be_saved(page, running_app, json_file) -> None:
    original = json_file.read_text(encoding="utf-8")
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()

    editor = page.get_by_role("textbox", name="JSON 对象")
    _replace_editor_text(editor, '{"objectName":')
    save_button = page.get_by_role("button", name="保存")
    expect(save_button).to_be_disabled()
    page.get_by_role("button", name="校验").click()

    expect(page.get_by_text(re.compile("JSON 语法错误"))).to_be_visible()
    expect(save_button).to_be_disabled()
    assert json_file.read_text(encoding="utf-8") == original


def test_dirty_drawer_confirms_and_restores_focus(page, running_app) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    origin = page.get_by_role("button", name="编辑 User")
    origin.click()

    editor = page.get_by_role("textbox", name="JSON 对象")
    expect(editor).to_be_focused()
    _replace_editor_text(editor, '{"objectName":"User","changed":true}')
    messages = []

    def accept_close(dialog) -> None:
        messages.append(dialog.message)
        dialog.accept()

    page.on("dialog", accept_close)
    page.get_by_role("button", name="关闭编辑器").click()

    expect(origin).to_be_focused()
    assert messages == ["当前修改尚未保存，确定关闭编辑器吗？"]


def test_drawer_is_full_screen_on_narrow_viewport(page, running_app) -> None:
    page.set_viewport_size({"width": 768, "height": 900})
    page.goto(running_app.url)
    page.evaluate(
        "document.documentElement.style.overflowY = 'scroll';"
        "document.documentElement.style.scrollbarGutter = 'stable'"
    )
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()
    expect(page.get_by_role("textbox", name="JSON 对象")).to_be_visible()

    drawer = page.locator("#editor-drawer")
    drawer.evaluate(
        "async node => await Promise.all("
        "node.getAnimations().map(animation => animation.finished))"
    )
    bounds = drawer.bounding_box()
    assert bounds is not None
    client_width = page.evaluate(
        "document.body.getBoundingClientRect().width"
    )
    assert bounds["x"] == 0
    assert bounds["width"] == client_width
    assert page.evaluate("document.documentElement.scrollWidth") <= 768
    close_bounds = page.get_by_role(
        "button", name="关闭编辑器"
    ).bounding_box()
    save_bounds = page.get_by_role("button", name="保存").bounding_box()
    assert close_bounds is not None and close_bounds["height"] >= 44
    assert save_bounds is not None and save_bounds["height"] >= 44


def test_json_object_can_be_deleted(page, running_app, json_file) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()

    messages = []

    def accept_delete(dialog) -> None:
        messages.append(dialog.message)
        dialog.accept()

    page.on("dialog", accept_delete)
    page.get_by_role("button", name="删除对象").click()

    expect(page.get_by_text("删除成功")).to_be_visible()
    expect(page.get_by_role("button", name="编辑 User")).not_to_be_visible()
    assert messages == ["确定删除“User”吗？此操作会记录到历史。"]
    assert "User" not in json_file.read_text(encoding="utf-8")


def test_sql_table_create_and_insert_can_be_edited(
    page, running_app, sql_file
) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="基础表").click()
    page.get_by_role("button", name="编辑 user_profile").click()

    create_editor = page.get_by_role("textbox", name="建表语句")
    _replace_editor_text(
        create_editor,
        "CREATE TABLE user_profile (\n"
        "  id bigint COMMENT '主键',\n"
        "  name varchar(50) COMMENT '名称'\n"
        ") COMMENT='用户档案';",
    )
    page.get_by_role("tab", name="初始化语句").click()
    insert_editor = page.get_by_role("textbox", name="初始化语句")
    _replace_editor_text(
        insert_editor,
        "INSERT INTO user_profile (id, name) VALUES (2, 'B');",
    )

    page.get_by_role("button", name="校验").click()
    expect(page.get_by_text("SQL 校验通过")).to_be_visible()
    page.get_by_role("button", name="保存").click()

    expect(page.get_by_text("保存成功")).to_be_visible()
    source = sql_file.read_text(encoding="utf-8")
    assert "用户档案" in source
    assert "VALUES (2, 'B')" in source


def test_sql_table_can_be_created(page, running_app, sql_file) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="基础表").click()
    page.get_by_role("button", name="新增对象").click()

    create_editor = page.get_by_role("textbox", name="建表语句")
    _replace_editor_text(
        create_editor,
        "CREATE TABLE audit_log (\n"
        "  id bigint COMMENT '主键'\n"
        ") COMMENT='审计日志';",
    )
    page.get_by_role("tab", name="初始化语句").click()
    insert_editor = page.get_by_role("textbox", name="初始化语句")
    _replace_editor_text(
        insert_editor,
        "INSERT INTO audit_log (id) VALUES (1);",
    )
    page.get_by_role("button", name="校验").click()
    expect(page.get_by_text("SQL 校验通过")).to_be_visible()
    page.get_by_role("button", name="保存").click()

    expect(page.get_by_text("保存成功")).to_be_visible()
    expect(page.get_by_role("button", name="编辑 audit_log")).to_be_visible()
    assert "CREATE TABLE audit_log" in sql_file.read_text(encoding="utf-8")


def test_sql_table_can_be_deleted(page, running_app, sql_file) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="基础表").click()
    page.get_by_role("button", name="编辑 user_profile").click()

    messages = []

    def accept_delete(dialog) -> None:
        messages.append(dialog.message)
        dialog.accept()

    page.on("dialog", accept_delete)
    page.get_by_role("button", name="删除表").click()

    expect(page.get_by_text("删除成功")).to_be_visible()
    assert messages == [
        "确定删除表“user_profile”吗？此操作会记录到历史。"
    ]
    assert "CREATE TABLE user_profile" not in sql_file.read_text(
        encoding="utf-8"
    )


def test_sql_tabs_support_arrow_key_navigation(page, running_app) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="基础表").click()
    page.get_by_role("button", name="编辑 user_profile").click()

    create_tab = page.get_by_role("tab", name="建表语句")
    insert_tab = page.get_by_role("tab", name="初始化语句")
    expect(page.get_by_role("textbox", name="建表语句")).to_be_visible()
    create_tab.focus()
    create_tab.press("ArrowRight")

    expect(insert_tab).to_be_focused()
    expect(insert_tab).to_have_attribute("aria-selected", "true")
    expect(page.get_by_role("textbox", name="初始化语句")).to_be_visible()


def test_conflict_preserves_unsaved_text_and_offers_safe_actions(
    page, running_app, json_file
) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()
    editor = page.get_by_role("textbox", name="JSON 对象")
    local_value = '{"objectName":"User","enabled":false}'
    _replace_editor_text(editor, local_value)
    json_file.write_text(
        '[{"objectName":"User","enabled":"external"}]',
        encoding="utf-8",
    )

    page.get_by_role("button", name="校验").click()
    page.get_by_role("button", name="保存").click()

    expect(
        page.get_by_text("文件已被其他人或外部程序修改").first
    ).to_be_visible()
    assert _editor_value(editor) == local_value
    page.get_by_role("button", name="复制我的编辑内容").click()
    expect(page.get_by_text("编辑内容已复制")).to_be_visible()
    page.get_by_role("button", name="查看差异").click()
    expect(page.get_by_role("heading", name="我的内容")).to_be_visible()
    expect(page.get_by_role("heading", name="磁盘内容")).to_be_visible()
    expect(page.locator(".conflict-disk")).to_contain_text("external")

    messages = []

    def accept_reload(dialog) -> None:
        messages.append(dialog.message)
        dialog.accept()

    page.on("dialog", accept_reload)
    page.get_by_role("button", name="重新加载磁盘版本").click()
    expect(page.get_by_text("已加载磁盘版本")).to_be_visible()
    assert _editor_value(editor) == (
        '{"objectName":"User","enabled":"external"}'
    )
    assert messages == ["重新加载会丢弃当前未保存的编辑内容，确定继续吗？"]


def test_history_version_can_be_viewed_and_rolled_back(
    page, running_app
) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()
    editor = page.get_by_role("textbox", name="JSON 对象")
    _replace_editor_text(editor, '{"objectName":"User","enabled":false}')
    page.get_by_role("button", name="校验").click()
    page.get_by_role("button", name="保存").click()
    expect(page.get_by_text("保存成功")).to_be_visible()

    page.get_by_role("button", name="历史记录").click()
    expect(page.get_by_role("heading", name="用户模型 · 历史记录")).to_be_visible()
    page.get_by_role("button", name="查看差异").first.click()
    expect(page.get_by_text("v1-before", exact=False)).to_be_visible()
    page.get_by_role("button", name="回滚到此版本").click()
    page.get_by_role("button", name="确认回滚").click()

    expect(page.get_by_text("回滚成功")).to_be_visible()


def test_invalid_json_file_can_be_repaired(
    page, running_app, json_file
) -> None:
    page.goto(running_app.url)
    json_file.write_text(
        '[\n  {"objectName":"Broken",}\n]\n',
        encoding="utf-8",
    )
    page.get_by_role("button", name="用户模型").click()

    expect(page.get_by_role("heading", name="文件无法解析")).to_be_visible()
    expect(page.get_by_text(re.compile("第 2 行"))).to_be_visible()
    page.get_by_role("button", name="整文件修复").click()
    editor = page.get_by_role("textbox", name="完整 JSON 文件")
    assert "Broken" in _editor_value(editor)
    _replace_editor_text(editor, '[{"objectName":"Fixed"}]')

    save_button = page.get_by_role("button", name="保存修复")
    expect(save_button).to_be_disabled()
    page.get_by_role("button", name="校验完整文件").click()
    expect(page.get_by_text("文件校验通过")).to_be_visible()
    page.get_by_role("button", name="保存修复").click()

    expect(page.get_by_text("修复成功")).to_be_visible()
    expect(page.get_by_role("button", name="编辑 Fixed")).to_be_visible()
    assert json_file.read_text(encoding="utf-8") == (
        '[{"objectName":"Fixed"}]'
    )


def test_invalid_sql_file_can_be_repaired(page, running_app, sql_file) -> None:
    page.goto(running_app.url)
    sql_file.write_text(
        "CREATE TABLE broken (id int;\n",
        encoding="utf-8",
    )
    page.get_by_role("button", name="基础表").click()

    expect(page.get_by_role("heading", name="文件无法解析")).to_be_visible()
    page.get_by_role("button", name="整文件修复").click()
    editor = page.get_by_role("textbox", name="完整 SQL 文件")
    assert "broken" in _editor_value(editor)
    _replace_editor_text(
        editor,
        "CREATE TABLE fixed_table (\n"
        "  id bigint COMMENT '主键'\n"
        ") COMMENT='修复';\n",
    )

    page.get_by_role("button", name="校验完整文件").click()
    expect(page.get_by_text("文件校验通过")).to_be_visible()
    page.get_by_role("button", name="保存修复").click()

    expect(page.get_by_text("修复成功")).to_be_visible()
    expect(page.get_by_role("button", name="编辑 fixed_table")).to_be_visible()
    assert "CREATE TABLE fixed_table" in sql_file.read_text(encoding="utf-8")


def test_repair_conflict_keeps_full_file_draft(
    page, running_app, json_file
) -> None:
    page.goto(running_app.url)
    json_file.write_text("[", encoding="utf-8")
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="整文件修复").click()
    editor = page.get_by_role("textbox", name="完整 JSON 文件")
    local_value = '[{"objectName":"LocalFixed"}]'
    _replace_editor_text(editor, local_value)
    json_file.write_text(
        '[{"objectName":"DiskFixed"}]',
        encoding="utf-8",
    )

    page.get_by_role("button", name="校验完整文件").click()
    page.get_by_role("button", name="保存修复").click()

    expect(
        page.get_by_text("文件已被其他人或外部程序修改").first
    ).to_be_visible()
    assert _editor_value(editor) == local_value
    page.get_by_role("button", name="查看差异").click()
    expect(page.locator(".conflict-disk")).to_contain_text("DiskFixed")
