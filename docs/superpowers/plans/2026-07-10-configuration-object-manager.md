# Configuration Object Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 构建一个可打包为单个 Windows 可执行程序的局域网配置对象管理器，按对象安全编辑白名单 JSON 数组文件和 MySQL SQL 文件，并提供严格校验、冲突检测、历史差异与回滚。

**Architecture:** 单个 Python 进程在主线程运行 Tkinter 控制窗口，在后台线程运行 Waitress + Flask。领域层分别负责 JSON/SQL 源码范围解析，存储层通过 SQLite 两阶段修订日志、文件锁和同目录原子替换保证写入安全，原生网页使用内置 CodeMirror 静态资源提供文件列表、对象列表和右侧编辑抽屉。

**Tech Stack:** Python 3.12、Flask 3.1.3、Waitress 3.0.2、sqlglot 30.12.0、SQLite、Tkinter、原生 HTML/CSS/JavaScript、CodeMirror 5.65.18、pytest、Python Playwright、PyInstaller。

## Global Constraints

- 设计依据：docs/superpowers/specs/2026-07-10-configuration-object-manager-design.md。
- 运行平台为 Windows 10/11 x64；开发与打包基线为 Python 3.12。
- 最终用户只运行一个 EXE，不需要安装 Python、Node 或访问 CDN。
- Web 服务默认监听 0.0.0.0:8765，端口固定且可持久化配置。
- 不实现登录、账号或角色；任何能访问局域网地址的人具有同等编辑权限。
- 浏览器只能通过白名单文件 ID 操作文件，任何 API 都不得接受服务端路径。
- 文件必须是 UTF-8；JSON 必须是严格 JSON 数组，objectName 在单文件内大小写敏感且唯一。
- SQL 方言固定为 MySQL；只对 CREATE TABLE 和 INSERT INTO 提供结构化增删改。
- 更新必须只替换目标对象或目标语句范围，未修改源码应逐字节保持。
- 所有写入必须携带 SHA-256 修订号，先落 SQLite PENDING 修订，再原子替换文件，最后标记 APPLIED。
- SQLite 不可写、候选内容校验失败或修订号冲突时，源码文件不得改变。
- 修改请求必须经过同源、Host/Origin 与防伪令牌检查；不开放 CORS。
- 用户界面文案使用简体中文，并满足键盘操作、清晰焦点和 prefers-reduced-motion。
- 生产代码必须遵循 TDD：测试先失败，再写最小实现，再运行通过。
- 不修改或提交工作区中与本项目无关的 .codex-inspect-strings.py。

---

## Planned File Structure

~~~text
pyproject.toml
README.md
PRODUCT.md
DESIGN.md
conf-edit.spec
scripts/
  build.ps1
  vendor_codemirror.py
src/conf_edit/
  __init__.py
  __main__.py
  config.py
  logging_config.py
  domain/errors.py
  domain/models.py
  parsers/json_models.py
  parsers/sql_models.py
  storage/database.py
  storage/settings_repository.py
  storage/catalog_repository.py
  storage/revision_repository.py
  storage/file_gateway.py
  services/catalog_service.py
  services/editor_service.py
  services/history_service.py
  web/app.py
  web/security.py
  web/routes_files.py
  web/routes_history.py
  desktop/server.py
  desktop/controller.py
  desktop/view.py
  templates/index.html
  static/css/app.css
  static/js/api.js
  static/js/app.js
  static/js/editor.js
  static/js/history.js
  static/vendor/codemirror/
tests/
  conftest.py
  unit/
  storage/
  services/
  web/
  desktop/
  e2e/
~~~

### Task 1: Python Package, App Paths, and SQLite Schema

**Files:**
- Create: pyproject.toml
- Create: src/conf_edit/__init__.py
- Create: src/conf_edit/config.py
- Create: src/conf_edit/storage/__init__.py
- Create: src/conf_edit/storage/database.py
- Create: src/conf_edit/storage/settings_repository.py
- Create: tests/conftest.py
- Create: tests/unit/test_config.py
- Create: tests/storage/test_database.py
- Create: tests/storage/test_settings_repository.py

**Interfaces:**
- Produces: AppPaths.for_user(override_root: Path | None = None) -> AppPaths
- Produces: AppSettings(port: int = 8765, auto_start: bool = True)
- Produces: Database(path: Path).connect() -> sqlite3.Connection
- Produces: Database.initialize() -> None
- Produces: SettingsRepository.load() -> AppSettings
- Produces: SettingsRepository.save(settings: AppSettings) -> None

- [ ] **Step 1: Add dependency metadata**

~~~toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "conf-edit"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "Flask==3.1.3",
  "waitress==3.0.2",
  "sqlglot==30.12.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.4,<9",
  "pytest-cov>=6,<8",
  "playwright>=1.52,<2",
  "pyinstaller>=6.14,<7",
]

[project.scripts]
conf-edit = "conf_edit.__main__:main"

[tool.setuptools]
package-dir = {"" = "src"}
include-package-data = true

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
~~~

- [ ] **Step 2: Write failing path and schema tests**

~~~python
# tests/unit/test_config.py
from pathlib import Path
from conf_edit.config import AppPaths

def test_app_paths_use_override_root(tmp_path: Path) -> None:
    paths = AppPaths.for_user(tmp_path)
    assert paths.data_dir == tmp_path
    assert paths.db_path == tmp_path / "conf-edit.db"
    assert paths.log_dir == tmp_path / "logs"
    assert paths.log_dir.is_dir()

# tests/storage/test_database.py
from conf_edit.storage.database import Database

def test_initialize_creates_versioned_schema(tmp_path) -> None:
    db = Database(tmp_path / "app.db")
    db.initialize()
    with db.connect() as connection:
        names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert {"settings", "allowed_files", "revisions"} <= names
    assert version == 1
~~~

- [ ] **Step 3: Run tests and verify the package is missing**

Run: python -m pytest tests/unit/test_config.py tests/storage/test_database.py -v

Expected: collection fails with ModuleNotFoundError for conf_edit.

- [ ] **Step 4: Implement paths and settings**

~~~python
# src/conf_edit/config.py
from dataclasses import dataclass
from pathlib import Path
import os

@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    db_path: Path
    log_dir: Path

    @classmethod
    def for_user(cls, override_root: Path | None = None) -> "AppPaths":
        root = override_root
        if root is None:
            local = os.environ.get("LOCALAPPDATA")
            root = Path(local) / "ConfEdit" if local else Path.home() / ".conf-edit"
        root.mkdir(parents=True, exist_ok=True)
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return cls(root, root / "conf-edit.db", log_dir)

@dataclass(frozen=True, slots=True)
class AppSettings:
    port: int = 8765
    auto_start: bool = True
~~~

- [ ] **Step 5: Implement the version-1 schema**

~~~python
# src/conf_edit/storage/database.py
from pathlib import Path
import sqlite3

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS allowed_files (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN ('json', 'sql')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'APPLIED', 'FAILED', 'CONFLICTED')
    ),
    action TEXT NOT NULL,
    object_key TEXT,
    client_ip TEXT,
    note TEXT,
    before_content BLOB NOT NULL,
    after_content BLOB NOT NULL,
    before_sha256 TEXT NOT NULL,
    after_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(file_id, version)
);
CREATE INDEX IF NOT EXISTS ix_revisions_file_version
ON revisions(file_id, version DESC);
PRAGMA user_version = 1;
"""

class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA_V1)
~~~

- [ ] **Step 6: Add settings round-trip test and repository**

~~~python
# tests/storage/test_settings_repository.py
def test_settings_round_trip(tmp_path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    repository = SettingsRepository(database)
    assert repository.load() == AppSettings()
    repository.save(AppSettings(port=9000, auto_start=False))
    assert repository.load() == AppSettings(port=9000, auto_start=False)
~~~

SettingsRepository stores port and auto_start as rows in settings, validates port is between 1024 and 65535, and falls back to AppSettings defaults when rows are absent.

- [ ] **Step 7: Install and run focused tests**

Run:

~~~powershell
python -m pip install -e ".[dev]"
python -m pytest tests/unit/test_config.py tests/storage/test_database.py tests/storage/test_settings_repository.py -v
~~~

Expected: 3 tests pass.

- [ ] **Step 8: Commit**

~~~powershell
git add pyproject.toml src/conf_edit tests/conftest.py tests/unit/test_config.py tests/storage/test_database.py tests/storage/test_settings_repository.py
git commit -m "chore: bootstrap Python app and database"
~~~

### Task 2: Domain Errors and File Whitelist

**Files:**
- Create: src/conf_edit/domain/__init__.py
- Create: src/conf_edit/domain/errors.py
- Create: src/conf_edit/domain/models.py
- Create: src/conf_edit/storage/catalog_repository.py
- Create: src/conf_edit/services/__init__.py
- Create: src/conf_edit/services/catalog_service.py
- Create: tests/storage/test_catalog_repository.py
- Create: tests/services/test_catalog_service.py
- Modify: tests/conftest.py

**Interfaces:**
- Produces: FileKind, AllowedFile, FileAvailability, DomainError
- Produces: CatalogRepository.add/get/list_active/deactivate
- Produces: CatalogService.add_file/inspect

- [ ] **Step 1: Write failing whitelist tests**

~~~python
import json
from pathlib import Path
import pytest
from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import FileKind

def test_add_json_file_stores_canonical_path(catalog_service, tmp_path: Path) -> None:
    target = tmp_path / "models.json"
    target.write_text(json.dumps([{"objectName": "User"}]), encoding="utf-8")
    item = catalog_service.add_file(target, FileKind.JSON)
    assert item.path == target.resolve()
    assert item.display_name == "models"

def test_add_rejects_wrong_extension(catalog_service, tmp_path: Path) -> None:
    target = tmp_path / "models.txt"
    target.write_text("[]", encoding="utf-8")
    with pytest.raises(DomainError) as captured:
        catalog_service.add_file(target, FileKind.JSON)
    assert captured.value.code == "wrong_extension"

def test_invalid_syntax_can_still_be_whitelisted(catalog_service, tmp_path: Path) -> None:
    target = tmp_path / "broken.json"
    target.write_text("[", encoding="utf-8")
    assert catalog_service.add_file(target, FileKind.JSON).active
~~~

In tests/conftest.py add a catalog_service fixture that initializes a temporary Database, CatalogRepository, and CatalogService. Add a catalog_repository fixture for repository tests.

- [ ] **Step 2: Run and verify missing modules**

Run: python -m pytest tests/services/test_catalog_service.py -v

Expected: import failure.

- [ ] **Step 3: Implement domain types**

~~~python
# src/conf_edit/domain/errors.py
class DomainError(Exception):
    def __init__(
        self, code: str, message: str, *,
        details: dict | None = None, status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status

# src/conf_edit/domain/models.py
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

class FileKind(StrEnum):
    JSON = "json"
    SQL = "sql"

@dataclass(frozen=True, slots=True)
class AllowedFile:
    id: str
    display_name: str
    path: Path
    kind: FileKind
    active: bool

@dataclass(frozen=True, slots=True)
class FileAvailability:
    readable: bool
    writable: bool
    exists: bool
    error: str | None = None
~~~

- [ ] **Step 4: Implement repository**

CatalogRepository must:

- use UUID hex IDs and UTC ISO timestamps;
- reactivate an existing canonical path instead of inserting a duplicate;
- preserve history by setting active=0 on removal;
- raise KeyError when an ID does not exist;
- order active files by kind and display_name.

Implement the exact methods CatalogRepository(database), add(path, kind, display_name), get(file_id), list_active(), and deactivate(file_id), using the return types declared in the Interfaces block.

- [ ] **Step 5: Implement service validation**

~~~python
class CatalogService:
    EXTENSIONS = {FileKind.JSON: ".json", FileKind.SQL: ".sql"}

    def __init__(self, repository: CatalogRepository) -> None:
        self.repository = repository

    def add_file(
        self, path: Path, kind: FileKind, display_name: str | None = None
    ) -> AllowedFile:
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise DomainError("file_not_found", "所选文件不存在") from exc
        if not resolved.is_file():
            raise DomainError("not_regular_file", "只能添加普通文件")
        if resolved.suffix.lower() != self.EXTENSIONS[kind]:
            raise DomainError("wrong_extension", "文件扩展名与类型不匹配")
        try:
            resolved.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise DomainError("invalid_encoding", "文件必须使用 UTF-8 编码") from exc
        name = (display_name or resolved.stem).strip()
        if not name:
            raise DomainError("empty_display_name", "文件显示名不能为空")
        return self.repository.add(resolved, kind, name)
~~~

inspect() must return exists/readable/writable without attempting syntax parsing. Also implement get(file_id), remove(file_id), and list_local(); list_local() is for the Tkinter controller and may include canonical paths.

- [ ] **Step 6: Run repository and service tests**

Run: python -m pytest tests/storage/test_catalog_repository.py tests/services/test_catalog_service.py -v

Expected: add, reactivate, list, deactivate, extension, encoding, and invalid-syntax tests pass.

- [ ] **Step 7: Commit**

~~~powershell
git add src/conf_edit/domain src/conf_edit/storage/catalog_repository.py src/conf_edit/services tests/storage/test_catalog_repository.py tests/services/test_catalog_service.py
git commit -m "feat: manage whitelisted configuration files"
~~~

### Task 3: JSON Source-Range Parser and Object CRUD

**Files:**
- Create: src/conf_edit/parsers/__init__.py
- Create: src/conf_edit/parsers/json_models.py
- Create: tests/unit/test_json_models.py

**Interfaces:**
- Produces: parse_json_document(source: str) -> JsonDocument
- Produces: validate_json_object(raw, occupied_keys, original_key=None) -> JsonDraft
- Produces: insert_json_object, replace_json_object, delete_json_object

- [ ] **Step 1: Write failing validation tests**

~~~python
import pytest
from conf_edit.domain.errors import DomainError
from conf_edit.parsers.json_models import parse_json_document

def test_parse_returns_named_entries() -> None:
    doc = parse_json_document(
        '[\n  {"objectName":"User","enabled":true},\n'
        '  {"objectName":"Order","fields":[]}\n]'
    )
    assert [item.key for item in doc.entries] == ["User", "Order"]
    assert doc.entries[0].field_count == 2

@pytest.mark.parametrize("source,code", [
    ('{"objectName":"User"}', "json_root_not_array"),
    ('[1]', "json_item_not_object"),
    ('[{}]', "object_name_missing"),
    ('[{"objectName":" "}]', "object_name_empty"),
    ('[{"objectName":"User"},{"objectName":"User"}]', "object_name_duplicate"),
])
def test_invalid_model_file(source: str, code: str) -> None:
    with pytest.raises(DomainError) as captured:
        parse_json_document(source)
    assert captured.value.code == code
~~~

- [ ] **Step 2: Run and verify failure**

Run: python -m pytest tests/unit/test_json_models.py -v

Expected: missing json_models module.

- [ ] **Step 3: Implement strict raw_decode scanning**

Define:

~~~python
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
    closing_bracket: int
~~~

parse_json_document() must use json.JSONDecoder.raw_decode at each top-level array element, record exact start/end offsets, reject trailing content, and convert JSONDecodeError.pos into one-based line and column details.

- [ ] **Step 4: Add failing preservation tests**

~~~python
def test_replace_changes_only_target() -> None:
    source = '[\n  {"objectName":"A","x":1},\n  { "objectName": "B", "x": 2 }\n]\n'
    result = replace_json_object(
        parse_json_document(source), "A", '{"objectName":"A","x":9}'
    )
    assert '{ "objectName": "B", "x": 2 }' in result
    assert result.endswith("]\n")

def test_insert_and_delete_keep_crlf() -> None:
    source = '[\r\n  {"objectName":"A"}\r\n]\r\n'
    inserted = insert_json_object(
        parse_json_document(source), '{"objectName":"B","中文":true}'
    )
    assert "\r\n" in inserted
    deleted = delete_json_object(parse_json_document(inserted), "A")
    assert [item.key for item in parse_json_document(deleted).entries] == ["B"]
~~~

- [ ] **Step 5: Implement draft validation and mutations**

validate_json_object() must require a dictionary, a nonblank string objectName, and no occupied key except original_key. Mutation rules:

- replacement swaps only the target span;
- insertion occurs immediately before the closing bracket using detected newline and indent;
- deletion removes the target and exactly one adjacent comma;
- each operation reparses the full result before returning.

Implement the exact functions declared in this task's Interfaces block. validate_json_object returns JsonDraft; every mutation returns the complete candidate source string.

- [ ] **Step 6: Run all JSON tests**

Run: python -m pytest tests/unit/test_json_models.py -v

Expected: syntax, type, key, Unicode, CRLF, nested data, escaped quote, insert, replace, rename, and delete cases pass.

- [ ] **Step 7: Commit**

~~~powershell
git add src/conf_edit/parsers tests/unit/test_json_models.py
git commit -m "feat: parse and edit JSON model objects"
~~~

### Task 4: MySQL Statement Parser and Table CRUD

**Files:**
- Create: src/conf_edit/parsers/sql_models.py
- Create: tests/unit/test_sql_models.py
- Create: tests/fixtures/sql/valid_schema.sql
- Create: tests/fixtures/sql/invalid_insert.sql

**Interfaces:**
- Produces: split_sql_statements(source) -> tuple[SqlStatement, ...]
- Produces: parse_sql_document(source) -> SqlDocument
- Produces: validate_sql_draft(create_sql, insert_sql, occupied_names, original_name=None)
- Produces: insert_sql_table, replace_sql_table, delete_sql_table

- [ ] **Step 1: Write failing lexical splitter test**

~~~python
def test_splitter_ignores_semicolons_in_tokens() -> None:
    source = (
        "-- note; keep\n"
        "CREATE TABLE user_profile (name varchar(50) COMMENT 'A;B');\n"
        "/* init; */ INSERT INTO user_profile (name) VALUES ('C;D');"
    )
    statements = split_sql_statements(source)
    assert len(statements) == 2
    assert statements[0].raw.startswith("-- note")
    assert statements[1].raw.startswith("\n/* init")
~~~

- [ ] **Step 2: Run and verify failure**

Run: python -m pytest tests/unit/test_sql_models.py::test_splitter_ignores_semicolons_in_tokens -v

Expected: missing sql_models module.

- [ ] **Step 3: Implement source-preserving splitting**

The state machine must track:

- single and double quoted strings with backslash and doubled-quote escapes;
- backtick identifiers;
- MySQL # and -- line comments;
- block comments;
- semicolons only in neutral state.

Each SqlStatement stores raw text and SourceSpan. Unclosed strings/comments raise sql_unclosed_token.

- [ ] **Step 4: Add failing grouping and INSERT validation tests**

~~~python
def test_group_create_and_inserts() -> None:
    source = (
        "CREATE TABLE user_profile ("
        "id bigint COMMENT '主键', name varchar(50) COMMENT '名称'"
        ") COMMENT='用户资料';\n"
        "INSERT INTO user_profile (id, name) VALUES (1, 'A'), (2, 'B');"
    )
    document = parse_sql_document(source)
    table = document.tables[0]
    assert table.name == "user_profile"
    assert table.field_count == 2
    assert table.table_comment == "用户资料"
    assert len(table.insert_statements) == 1

def test_insert_value_count_must_match() -> None:
    with pytest.raises(DomainError) as captured:
        validate_sql_draft(
            "CREATE TABLE t (id bigint, name varchar(10));",
            "INSERT INTO t (id, name) VALUES (1);",
            set(),
        )
    assert captured.value.code == "insert_value_count"
~~~

- [ ] **Step 5: Implement sqlglot classification**

parse_sql_document() must:

1. reject DELIMITER before parsing;
2. parse every statement with sqlglot.parse_one(read="mysql");
3. classify exp.Create of kind TABLE, exp.Insert, or unmanaged;
4. normalize matching names with casefold while preserving original spelling;
5. reject duplicate creates and inserts without a create;
6. extract exp.ColumnDef names and table/column comments;
7. validate explicit INSERT fields and each VALUES row length; when no field list is present, compare each row with the CREATE column count;
8. retain every successfully parsed unmanaged statement unchanged.

Define immutable SqlDocument, SqlTable, SqlStatement, SqlDraft dataclasses. All parse errors must use stable DomainError codes and diagnostic details.

- [ ] **Step 6: Add failing range-preservation tests**

~~~python
def test_replace_preserves_other_table_text() -> None:
    source = (
        "CREATE TABLE a (id bigint);\n"
        "\n-- keep spacing\nCREATE TABLE b ( id int );\n"
        "INSERT INTO a (id) VALUES (1);\n"
    )
    result = replace_sql_table(
        parse_sql_document(source),
        "a",
        "CREATE TABLE a (id bigint, name varchar(20));",
        "INSERT INTO a (id, name) VALUES (1, 'A');",
    )
    assert "\n-- keep spacing\nCREATE TABLE b ( id int );" in result

def test_delete_removes_only_target_blocks() -> None:
    source = (
        "CREATE TABLE a (id int);\nINSERT INTO a VALUES (1);\n"
        "CREATE TABLE b (id int);\n"
    )
    result = delete_sql_table(parse_sql_document(source), "a")
    assert "CREATE TABLE b" in result
    assert "CREATE TABLE a" not in result
~~~

- [ ] **Step 7: Implement SQL range mutations**

- replace: replace the CREATE span, remove all existing INSERT spans for the target, and place submitted INSERT statements immediately after the new CREATE;
- insert: append one validated table block using the file newline style;
- delete: remove only the target CREATE and related INSERT spans;
- rename: validate that CREATE and every INSERT use the same new table name and that it does not collide with another table;
- reparse the entire candidate before returning.

- [ ] **Step 8: Run and commit**

Run: python -m pytest tests/unit/test_sql_models.py -v

Expected: split, AST grouping, comments, duplicate/orphan tables, INSERT fields/values, unmanaged statements, rename, CRUD, and unchanged-neighbor tests pass.

~~~powershell
git add src/conf_edit/parsers/sql_models.py tests/unit/test_sql_models.py tests/fixtures/sql
git commit -m "feat: parse and edit MySQL table objects"
~~~

### Task 5: Safe File Gateway and Recoverable Revisions

**Files:**
- Create: src/conf_edit/storage/file_gateway.py
- Create: src/conf_edit/storage/revision_repository.py
- Create: tests/unit/test_file_gateway.py
- Create: tests/storage/test_revision_repository.py
- Modify: tests/conftest.py

**Interfaces:**
- Produces: FileSnapshot(content, sha256, writable)
- Produces: FileGateway.read/replace
- Produces: FileLockRegistry.hold(file_id)
- Produces: RevisionRepository.ensure_baseline/prepare/mark_status/list_for_file/list_pending/has_unresolved_conflict
- Produces: SafeWriter.read/write/recover_pending/acknowledge_current

- [ ] **Step 1: Write failing conflict and failed-write tests**

~~~python
def test_stale_revision_is_rejected(safe_writer, allowed_json) -> None:
    snapshot = safe_writer.read(allowed_json)
    allowed_json.path.write_text('[{"objectName":"External"}]', encoding="utf-8")
    with pytest.raises(DomainError) as captured:
        safe_writer.write(
            allowed_json,
            expected_sha256=snapshot.sha256,
            new_content='[{"objectName":"Mine"}]',
            action="modify",
            object_key="Mine",
            client_ip="127.0.0.1",
            note=None,
        )
    assert captured.value.code == "revision_conflict"
    assert "External" in allowed_json.path.read_text(encoding="utf-8")

def test_failed_replace_never_becomes_applied(
    safe_writer, revision_repository, allowed_json, monkeypatch
) -> None:
    before = safe_writer.read(allowed_json)
    monkeypatch.setattr(
        "conf_edit.storage.file_gateway.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("disk")),
    )
    with pytest.raises(DomainError):
        safe_writer.write(
            allowed_json, before.sha256, "[]", "modify",
            "User", "127.0.0.1", None,
        )
    applied = revision_repository.list_applied(allowed_json.id)
    assert [item.action for item in applied] == ["baseline"]
    assert revision_repository.list_failed(allowed_json.id)
~~~

Extend tests/conftest.py with allowed_json, revision_repository, FileGateway, FileLockRegistry, and safe_writer fixtures, all scoped to tmp_path.

- [ ] **Step 2: Run and verify missing storage classes**

Run: python -m pytest tests/unit/test_file_gateway.py tests/storage/test_revision_repository.py -v

Expected: import failures.

- [ ] **Step 3: Implement UTF-8 reads, hashing, locks, and atomic replacement**

~~~python
@dataclass(frozen=True, slots=True)
class FileSnapshot:
    content: str
    sha256: str
    writable: bool

def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

class FileGateway:
    def read(self, file: AllowedFile) -> FileSnapshot:
        resolved = file.path.resolve(strict=True)
        if resolved != file.path or not resolved.is_file():
            raise DomainError("file_identity_changed", "白名单文件路径已发生变化")
        try:
            content = resolved.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise DomainError("invalid_encoding", "文件必须使用 UTF-8 编码") from exc
        except OSError as exc:
            raise DomainError("file_read_failed", "读取文件失败", status=503) from exc
        return FileSnapshot(content, sha256_text(content), os.access(resolved, os.W_OK))

    def replace(self, file: AllowedFile, content: str) -> None:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=file.path.parent, delete=False, prefix=".conf-edit-"
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(content.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, file.path)
        except OSError as exc:
            raise DomainError("file_write_failed", "写入文件失败", status=503) from exc
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
~~~

FileLockRegistry must create one threading.Lock per file ID, wait at most two seconds, and raise file_locked with HTTP status 423 on timeout.

- [ ] **Step 4: Implement compressed revision persistence**

RevisionRepository.prepare() must:

- allocate the next per-file integer version inside the SQLite transaction;
- zlib-compress before and after UTF-8 content;
- insert status PENDING before any file mutation;
- store hashes, action, object key, client IP, note, and UTC time.

Implement prepare, ensure_baseline, mark_status, get_by_version, list_for_file, list_pending, list_applied, list_failed, and has_unresolved_conflict with the types declared in the Interfaces block. ensure_baseline creates APPLIED version 0 once, with identical before/after content and action baseline.

- [ ] **Step 5: Implement SafeWriter**

~~~python
class SafeWriter:
    def __init__(self, gateway, locks, revisions) -> None:
        self.gateway = gateway
        self.locks = locks
        self.revisions = revisions

    def read(self, file):
        return self.gateway.read(file)

    def write(
        self, file, expected_sha256, new_content, action,
        object_key, client_ip, note,
    ):
        with self.locks.hold(file.id):
            if self.revisions.has_unresolved_conflict(file.id):
                raise DomainError(
                    "recovery_conflict",
                    "文件存在未处理的启动恢复冲突，请在本机控制窗口确认磁盘版本",
                    status=423,
                )
            before = self.gateway.read(file)
            if before.sha256 != expected_sha256:
                raise DomainError(
                    "revision_conflict",
                    "文件已被其他人或外部程序修改",
                    details={"expected": expected_sha256, "actual": before.sha256},
                    status=409,
                )
            after_sha256 = sha256_text(new_content)
            self.revisions.ensure_baseline(
                file.id, before.content, before.sha256
            )
            revision = self.revisions.prepare(
                file_id=file.id,
                action=action,
                object_key=object_key,
                client_ip=client_ip,
                note=note,
                before_content=before.content,
                after_content=new_content,
                before_sha256=before.sha256,
                after_sha256=after_sha256,
            )
            try:
                self.gateway.replace(file, new_content)
            except Exception:
                self.revisions.mark_status(revision.id, "FAILED")
                raise
            self.revisions.mark_status(revision.id, "APPLIED")
            return self.gateway.read(file)
~~~

acknowledge_current(file) is only exposed to the local controller. It acquires the file lock, reads the current disk content, creates an APPLIED conflict_resolution revision whose before/after content and hashes are identical, and thereby establishes a newer trusted state without rewriting the source file.

- [ ] **Step 6: Add pending-recovery tests**

Cover three startup outcomes:

- disk hash equals after_sha256 -> APPLIED;
- disk hash equals before_sha256 -> FAILED;
- disk hash equals neither -> CONFLICTED and file is reported read-only.

Add a fourth test proving ordinary writes remain blocked after CONFLICTED until acknowledge_current() records a newer APPLIED state.

- [ ] **Step 7: Run and commit**

Run: python -m pytest tests/unit/test_file_gateway.py tests/storage/test_revision_repository.py -v

Expected: hashing, canonical identity, UTF-8 errors, stale revisions, lock timeout, replacement failure, compression, ordering, and recovery pass.

~~~powershell
git add src/conf_edit/storage/file_gateway.py src/conf_edit/storage/revision_repository.py tests/unit/test_file_gateway.py tests/storage/test_revision_repository.py
git commit -m "feat: add recoverable file revision writes"
~~~

### Task 6: Editor and History Services

**Files:**
- Create: src/conf_edit/services/editor_service.py
- Create: src/conf_edit/services/history_service.py
- Modify: tests/conftest.py
- Create: tests/services/test_editor_service.py
- Create: tests/services/test_history_service.py

**Interfaces:**
- Produces: EditorService.list_files/list_objects/get_object/validate_draft/create/update/delete/repair
- Produces: HistoryService.list/diff/rollback
- Consumes: catalog, parsers, SafeWriter, RevisionRepository

- [ ] **Step 1: Write failing JSON and SQL dispatch tests**

~~~python
def test_list_json_objects_returns_revision(editor_service, json_file) -> None:
    result = editor_service.list_objects(json_file.id)
    assert result["kind"] == "json"
    assert result["revision"]
    assert result["objects"][0] == {
        "key": "User", "fieldCount": 2, "valid": True
    }

def test_sql_object_has_create_and_insert_editors(editor_service, sql_file) -> None:
    result = editor_service.get_object(sql_file.id, "user_profile")
    assert result["createSql"].lstrip().startswith("CREATE TABLE")
    assert result["insertSql"].lstrip().startswith("INSERT INTO")
~~~

Extend tests/conftest.py with json_file, sql_file, editor_service, and history_service fixtures. Each fixture must use its own tmp_path files and the real repositories/gateway rather than mocks.

- [ ] **Step 2: Run and verify missing services**

Run: python -m pytest tests/services/test_editor_service.py -v

Expected: import failure.

- [ ] **Step 3: Implement read models and parser dispatch**

EditorService.list_files() combines CatalogService.list_local(), FileAvailability, parser validation, object count, and unresolved recovery-conflict state, then returns web-safe summaries containing only id, displayName, kind, status, writable, objectCount, and error.

EditorService.list_objects() returns:

~~~python
{
    "fileId": file.id,
    "displayName": file.display_name,
    "kind": file.kind.value,
    "revision": snapshot.sha256,
    "writable": snapshot.writable,
    "objects": object_summaries,
    "unmanagedCount": unmanaged_count,
}
~~~

JSON summaries contain key, fieldCount, valid. SQL summaries contain key, fieldCount, insertCount, comment, valid. get_object() returns raw for JSON, or createSql, insertSql, tableComment, and a list of fieldComments for SQL. No result contains file.path.

If parsing the existing file fails, catch the parser DomainError, add fileId, kind, revision, and writable to its details, and re-raise it. This lets repair mode retain the correct stale-write guard even though no object list can be produced.

- [ ] **Step 4: Implement validation and mutation orchestration**

Every mutation must:

1. fetch an active whitelist record;
2. read and compare the submitted revision;
3. parse the current source;
4. call exactly one parser mutation;
5. parse the candidate full source;
6. call SafeWriter.write;
7. return a fresh list_objects result.

Implement create, update, delete, and repair with the exact argument names and return type declared in this task's Interfaces block.

validate_draft() performs parser validation only and never calls SafeWriter. Its request has scope="object" with draft/originalKey, or scope="file" with source; file scope validates an entire repair candidate.

- [ ] **Step 5: Write failing history tests**

~~~python
def test_history_diff_and_rollback(
    history_service, editor_service, json_file
) -> None:
    before = editor_service.list_objects(json_file.id)
    editor_service.update(
        json_file.id,
        "User",
        {"raw": '{"objectName":"User","enabled":false}'},
        before["revision"],
        "10.0.0.2",
        "disable",
    )
    middle = editor_service.list_objects(json_file.id)
    editor_service.update(
        json_file.id,
        "User",
        {"raw": '{"objectName":"User","enabled":true,"version":2}'},
        middle["revision"],
        "10.0.0.2",
        "second change",
    )
    versions = history_service.list(json_file.id)
    version_one = next(item for item in versions if item["version"] == 1)
    assert version_one["action"] == "modify"
    assert "enabled" in history_service.diff(json_file.id, 1)
    current = editor_service.list_objects(json_file.id)
    result = history_service.rollback(
        json_file.id,
        1,
        current["revision"],
        "10.0.0.2",
    )
    assert result["revision"] != current["revision"]
~~~

- [ ] **Step 6: Implement history**

HistoryService.list() returns version, status, action, objectKey, clientIp, note, createdAt. Version 0 is the APPLIED baseline. diff() uses difflib.unified_diff on before_content and after_content. rollback():

- accepts only APPLIED revisions;
- validates the target after_content through the correct parser;
- requires the current revision hash;
- writes target after_content as a new rollback revision;
- returns fresh object data.

- [ ] **Step 7: Run and commit**

Run: python -m pytest tests/services -v

Expected: JSON and SQL read, validate, CRUD, rename, repair, stale revision, history, diff, rollback, and inactive-file tests pass.

~~~powershell
git add src/conf_edit/services tests/conftest.py tests/services
git commit -m "feat: orchestrate object editing and history"
~~~

### Task 7: Flask App and Security Boundary

**Files:**
- Create: src/conf_edit/web/__init__.py
- Create: src/conf_edit/web/security.py
- Create: src/conf_edit/web/app.py
- Create: src/conf_edit/web/routes_files.py
- Create: src/conf_edit/web/routes_history.py
- Create: tests/web/test_security.py
- Create: tests/web/test_files_api.py
- Create: tests/web/test_history_api.py
- Create: tests/web/conftest.py

**Interfaces:**
- Produces: WebContainer(catalog, editor, history, security)
- Produces: create_app(container: WebContainer) -> Flask
- Produces stable JSON error shape
- Requires X-Conf-Edit-Token on mutation requests
- Never serializes absolute paths

- [ ] **Step 1: Write failing security contract tests**

~~~python
def test_mutation_requires_token(client) -> None:
    response = client.post("/api/files/file-1/validate", json={"raw": "{}"})
    assert response.status_code == 403
    assert response.json["error"]["code"] == "csrf_invalid"

def test_cross_origin_is_rejected(client) -> None:
    response = client.get(
        "/api/status", headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert "Access-Control-Allow-Origin" not in response.headers

def test_domain_error_shape(client, services) -> None:
    services.editor.list_objects.side_effect = DomainError(
        "json_syntax", "JSON 错误", details={"line": 3, "column": 9}
    )
    response = client.get("/api/files/id/objects")
    assert response.json == {
        "error": {
            "code": "json_syntax",
            "message": "JSON 错误",
            "details": {"line": 3, "column": 9},
        }
    }
~~~

tests/web/conftest.py must build WebContainer with real CatalogService and lightweight service doubles, create RequestSecurity with a fixed test token and localhost allowlist, then expose app, client, services, and mutation_headers fixtures.

- [ ] **Step 2: Run and verify failure**

Run: python -m pytest tests/web/test_security.py -v

Expected: missing web app.

- [ ] **Step 3: Implement request security**

RequestSecurity must:

- generate a 32-byte URL-safe token per process;
- enumerate localhost, machine hostname, and local IPv4 addresses at the configured port;
- reject any Host outside that exact set;
- reject an Origin whose netloc differs from request.host;
- require X-Conf-Edit-Token for POST, PUT, PATCH, and DELETE;
- never emit Access-Control-Allow-Origin.

- [ ] **Step 4: Implement app factory and error mapping**

~~~python
@dataclass(frozen=True, slots=True)
class WebContainer:
    catalog: CatalogService
    editor: EditorService
    history: HistoryService
    security: RequestSecurity

def create_app(container: WebContainer) -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    security = container.security

    @app.before_request
    def enforce_boundary():
        g.request_id = uuid4().hex
        security.validate(request)

    @app.errorhandler(DomainError)
    def domain_error(error):
        return jsonify(error={
            "code": error.code,
            "message": error.message,
            "details": error.details,
        }), error.status

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception("Unhandled request error")
        return jsonify(error={
            "code": "internal_error",
            "message": "服务器内部错误",
            "details": {"requestId": g.request_id},
        }), 500
~~~

Import g and request from Flask plus uuid4 from uuid. Add GET /, GET /api/status, and blueprints. The index route passes container.security.token into the template.

- [ ] **Step 5: Implement file/object routes**

Required routes:

- GET /api/files
- GET /api/files/{id}/objects
- GET /api/files/{id}/object?key={objectKey}
- POST /api/files/{id}/validate
- POST /api/files/{id}/objects
- PUT /api/files/{id}/object
- DELETE /api/files/{id}/object
- PUT /api/files/{id}/repair

GET /api/files calls EditorService.list_files(), not CatalogService, so syntax and recovery-conflict states are included without exposing paths. POST validate accepts JSON object validation as {"scope":"object","draft":{"raw":"{\"objectName\":\"User\"}"},"originalKey":"User"}, SQL object validation as {"scope":"object","draft":{"createSql":"CREATE TABLE t (id int);","insertSql":""},"originalKey":"t"}, or repair validation as {"scope":"file","source":"[]"}. Mutation JSON fields must match the EditorService signatures exactly. Missing/invalid body fields return request_invalid, not a raw KeyError.

- [ ] **Step 6: Implement history routes**

Required routes:

- GET /api/files/{id}/history
- GET /api/files/{id}/history/{version}/diff
- POST /api/files/{id}/history/{version}/rollback

- [ ] **Step 7: Add path-redaction and 409 tests**

Serialize every file-related response and assert neither the temporary directory nor a drive-letter pattern appears. Verify DomainError status 409 is preserved with expected and actual hashes.

- [ ] **Step 8: Run and commit**

Run: python -m pytest tests/web -v

Expected: token, Host, Origin, status, list, JSON/SQL CRUD, repair, history, rollback, invalid bodies, path redaction, and 409 tests pass.

~~~powershell
git add src/conf_edit/web tests/web
git commit -m "feat: expose secured configuration APIs"
~~~

### Task 8: Frontend Workspace and Editor Drawer

**Required UI skill before implementation:** invoke impeccable, run its setup, read the product register, and preserve the approved “对象列表 + 编辑抽屉” layout.

**Files:**
- Create or update through impeccable init: PRODUCT.md
- Create or update through impeccable init: DESIGN.md
- Create: scripts/vendor_codemirror.py
- Create: src/conf_edit/templates/index.html
- Create: src/conf_edit/static/css/app.css
- Create: src/conf_edit/static/js/api.js
- Create: src/conf_edit/static/js/app.js
- Create: src/conf_edit/static/js/editor.js
- Create: src/conf_edit/static/vendor/codemirror/
- Create: tests/e2e/test_web_workflows.py
- Create: tests/e2e/conftest.py

**Interfaces:**
- Produces: window.confEditApi.request
- Produces: window.confEditEditor.open
- DOM anchors: file-list, object-list, editor-drawer, toast-region

- [ ] **Step 1: Write a failing browser workflow**

~~~python
def test_json_object_can_be_edited_from_drawer(
    page, running_app, json_file
) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()
    page.get_by_role("textbox", name="JSON 对象").fill(
        '{"objectName":"User","enabled":false}'
    )
    page.get_by_role("button", name="校验").click()
    page.get_by_text("JSON 校验通过").wait_for()
    page.get_by_role("button", name="保存").click()
    page.get_by_text("保存成功").wait_for()
    assert '"enabled":false' in json_file.read_text(encoding="utf-8")
~~~

tests/e2e/conftest.py must start the real Flask app through a temporary Waitress server on a free localhost port, create temporary whitelisted JSON/SQL files, expose running_app.url, and stop the server after each test session.

- [ ] **Step 2: Run and verify missing UI**

Run: python -m pytest tests/e2e/test_web_workflows.py::test_json_object_can_be_edited_from_drawer -v

Expected: page controls are absent.

- [ ] **Step 3: Vendor CodeMirror with Python only**

scripts/vendor_codemirror.py downloads from https://cdn.jsdelivr.net/npm/codemirror@5.65.18/ and verifies this exact path -> SHA-256 mapping:

- lib/codemirror.min.js -> 9eb3d93e642327e5f350342a60e6810aa1543644ba003e41bad2f372ead3b372
- lib/codemirror.min.css -> d8fddcfca0ccaeea67ddd557d22340530a1daae8a09843e8f4c25d7def06efa8
- mode/javascript/javascript.min.js -> b96dd971a4c0b083fd65bf361ab5958a74010bafb629eaa1592e20797f53995b
- mode/sql/sql.min.js -> 74a69758a1555997dcbcb8f8ab5d0cb1d7d80ccdcdde7af223186921a021c2af
- addon/edit/matchbrackets.min.js -> 3c9e6befa28b77612e4541effc48988137505070cda12ee7644749afb4db070f
- addon/dialog/dialog.min.css -> 94ecb2e6f83cad6ec25b6f27651983e9e94cd52b4e9ce13cc96999914c9cf67e
- LICENSE -> 168a4becc968f5001e2ee2e0291b6e4daabafc1894a11ade1e11d56e96096e07

The script exits non-zero on mismatch and writes only under static/vendor/codemirror. Run it once and commit the assets.

- [ ] **Step 4: Create semantic HTML**

The page must include:

- skip link;
- header with product name, file status, and history button;
- nav file sidebar grouped by JSON/SQL;
- main object toolbar with file title, count, search, and add;
- live object list;
- dialog editor drawer;
- polite toast region;
- CSRF token meta element;
- local CodeMirror and application scripts only.

- [ ] **Step 5: Implement API client**

~~~javascript
(() => {
  const token = document.querySelector(
    'meta[name="conf-edit-token"]'
  ).content;

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body) headers.set("Content-Type", "application/json");
    const method = (options.method || "GET").toUpperCase();
    if (!["GET", "HEAD"].includes(method)) {
      headers.set("X-Conf-Edit-Token", token);
    }
    const response = await fetch(path, {...options, headers});
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(payload.error?.message || "请求失败");
      error.code = payload.error?.code;
      error.details = payload.error?.details || {};
      error.status = response.status;
      throw error;
    }
    return payload;
  }
  window.confEditApi = {request};
})();
~~~

- [ ] **Step 6: Implement file/object state**

app.js owns exactly one state object containing files, activeFile, objects, revision, and search query. Implement loadFiles(), selectFile(), renderFiles(), renderObjects(), empty/error states, search filtering, and refresh. Rows are buttons with accessible names such as “编辑 User”; no absolute path enters the DOM.

- [ ] **Step 7: Implement JSON and SQL drawers**

editor.js creates CodeMirror lazily:

- JSON mode has one “JSON 对象” editor and format action;
- SQL mode has “建表语句” and “初始化语句” tabs;
- both support optional modification note, validate, save, delete, dirty-close confirmation, and line/column diagnostics;
- delete is available only for existing objects and requires a confirmation naming the object or table;
- save is disabled until the current content has passed validation;
- dialog focus is trapped by native dialog and restored to the originating row.

- [ ] **Step 8: Implement the product visual system**

app.css must use OKLCH tokens, a restrained light theme, deep blue-gray header, one blue action color, body contrast at least 4.5:1, 240px sidebar, fluid center, min(620px, 100vw) drawer, visible focus, no nested cards, no gradient text, no glassmorphism, no accent side stripes, a full-screen drawer below 900px, and reduced-motion overrides.

- [ ] **Step 9: Run browser tests and commit**

Run:

~~~powershell
python -m playwright install chromium
python -m pytest tests/e2e/test_web_workflows.py -k "json or sql or keyboard" -v
~~~

Expected: selection, search, JSON/SQL CRUD, validation gating, focus restoration, empty states, and responsive drawer pass.

~~~powershell
git add PRODUCT.md DESIGN.md scripts/vendor_codemirror.py src/conf_edit/templates src/conf_edit/static tests/e2e
git commit -m "feat: add browser object management workspace"
~~~

### Task 9: History, Repair, and Conflict UX

**Files:**
- Create: src/conf_edit/static/js/history.js
- Modify: src/conf_edit/templates/index.html
- Modify: src/conf_edit/static/css/app.css
- Modify: src/conf_edit/static/js/api.js
- Modify: src/conf_edit/static/js/app.js
- Modify: src/conf_edit/static/js/editor.js
- Modify: tests/e2e/test_web_workflows.py

**Interfaces:**
- Produces: window.confEditHistory.open(fileId, revision)
- Consumes revision_conflict details
- Produces a full-file repair dialog

- [ ] **Step 1: Add failing conflict and rollback browser tests**

~~~python
def test_conflict_preserves_unsaved_text(page, running_app, json_file) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="用户模型").click()
    page.get_by_role("button", name="编辑 User").click()
    editor = page.get_by_role("textbox", name="JSON 对象")
    editor.fill('{"objectName":"User","enabled":false}')
    json_file.write_text('[{"objectName":"External"}]', encoding="utf-8")
    page.get_by_role("button", name="校验").click()
    page.get_by_role("button", name="保存").click()
    page.get_by_text("文件已被其他人或外部程序修改").wait_for()
    assert "enabled" in editor.input_value()

def test_history_version_can_be_rolled_back(page, running_app) -> None:
    page.goto(running_app.url)
    page.get_by_role("button", name="历史记录").click()
    page.get_by_role("button", name="查看差异").first.click()
    page.get_by_role("button", name="回滚到此版本").click()
    page.get_by_role("button", name="确认回滚").click()
    page.get_by_text("回滚成功").wait_for()
~~~

- [ ] **Step 2: Run and verify missing workflows**

Run: python -m pytest tests/e2e/test_web_workflows.py -k "conflict or history" -v

Expected: controls are absent.

- [ ] **Step 3: Implement history dialog**

The dialog must show action, object key, client IP, note, time, and status. APPLIED versions appear first; FAILED and CONFLICTED revisions appear in a diagnostic disclosure. Unified diff renders in a pre element, and additions/removals use both color and visible plus/minus prefixes. Rollback explains that it creates a new version and requires confirmation.

- [ ] **Step 4: Implement conflict actions**

When an API error has status 409:

- keep the drawer and editor content open;
- show “复制我的编辑内容” with Clipboard API and textarea fallback;
- fetch the current disk object through GET object without replacing the editor, then show “查看差异” as a side-by-side comparison of “我的内容” and “磁盘内容”;
- show “重新加载磁盘版本” behind confirmation;
- never show a force-overwrite action.

- [ ] **Step 5: Implement invalid-file repair**

When list_objects returns a parse diagnostic:

- show line, column, statement index, and context if available;
- replace the list with an error panel;
- open a full-source CodeMirror dialog;
- call validate before enabling repair save;
- send the original revision and use the normal 409 flow.

- [ ] **Step 6: Run resilience workflows**

Run: python -m pytest tests/e2e/test_web_workflows.py -k "history or conflict or repair" -v

Expected: diff, rollback, stale edit preservation, copy/reload choices, JSON repair, SQL repair, and confirmation tests pass.

- [ ] **Step 7: Commit**

~~~powershell
git add src/conf_edit/templates/index.html src/conf_edit/static tests/e2e/test_web_workflows.py
git commit -m "feat: add history repair and conflict workflows"
~~~

### Task 10: Windows Controller and Waitress Lifecycle

**Files:**
- Create: src/conf_edit/desktop/__init__.py
- Create: src/conf_edit/desktop/server.py
- Create: src/conf_edit/desktop/controller.py
- Create: src/conf_edit/desktop/view.py
- Create: src/conf_edit/logging_config.py
- Create: src/conf_edit/__main__.py
- Create: tests/desktop/test_server.py
- Create: tests/desktop/test_controller.py

**Interfaces:**
- Produces: WaitressServer.start/stop/running
- Produces: ControllerState(status, urls, files, error)
- Produces: DesktopController start/stop/add/remove/acknowledge_conflict/open_browser

- [ ] **Step 1: Write failing controller tests**

~~~python
def test_controller_transitions(fake_server, catalog_service) -> None:
    controller = DesktopController(fake_server, catalog_service, port=8765)
    controller.start()
    assert controller.state.status == "running"
    assert any(url.endswith(":8765") for url in controller.state.urls)
    controller.stop()
    assert controller.state.status == "stopped"

def test_controller_surfaces_port_error(fake_server, catalog_service) -> None:
    fake_server.start.side_effect = OSError("address in use")
    controller = DesktopController(fake_server, catalog_service, port=8765)
    controller.start()
    assert controller.state.status == "failed"
    assert "8765" in controller.state.error
~~~

- [ ] **Step 2: Run and verify missing desktop package**

Run: python -m pytest tests/desktop -v

Expected: import failures.

- [ ] **Step 3: Implement stoppable Waitress server**

~~~python
class WaitressServer:
    def __init__(self, app, host: str, port: int) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._server = None
        self._thread = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._server = create_server(
            self._app, host=self._host, port=self._port, threads=8
        )
        self._thread = threading.Thread(
            target=self._server.run,
            name="conf-edit-web",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self._server.close()
        self._thread.join(timeout=5)
        self._server = None
        self._thread = None
~~~

Because create_server runs synchronously inside start(), bind errors are raised before ControllerState changes to running. Add an HTTP readiness probe before reporting the final running state.

- [ ] **Step 4: Implement controller state**

ControllerState fields are status, urls, files, and error. local_urls(port) enumerates 127.0.0.1 plus local IPv4 addresses. DesktopController:

- transitions stopped -> starting -> running or failed;
- uses CatalogService for add/remove/refresh;
- exposes acknowledge_conflict(file_id) only after a local confirmation and delegates to SafeWriter.acknowledge_current;
- exposes open_browser and copyable URLs;
- never performs Tkinter widget operations.

- [ ] **Step 5: Build Tkinter view**

view.py must:

- show status using icon/shape plus text, never color alone;
- show an editable port field enabled only while stopped, validate 1024-65535, and persist it through SettingsRepository;
- show local/LAN URLs with copy/open buttons;
- show a Treeview with display name, type, status, and full local path;
- use filedialog.askopenfilename with JSON and SQL filters;
- prompt for display name;
- confirm removal and shutdown;
- show a “确认当前磁盘版本” action only for recovery-conflicted files, with an explicit warning that it discards the interrupted revision as the source of truth;
- show the latest 200 log lines in a collapsible read-only text area;
- use root.after for background callbacks.

- [ ] **Step 6: Wire application startup**

logging_config.py must configure a UTF-8 RotatingFileHandler at logs/app.log with 2 MiB per file and five backups. Log request IDs, action, file ID, object key, status, and exception traces; never log source content, CSRF tokens, or browser request bodies.

__main__.py must:

1. create AppPaths and rolling logs;
2. initialize SQLite;
3. load AppSettings through SettingsRepository;
4. build repositories/services;
5. recover PENDING revisions before writes are enabled;
6. build RequestSecurity, WebContainer, Flask, and Waitress with the persisted port;
7. build controller and view;
8. auto-start if configured and save later port/auto-start changes;
9. enter mainloop;
10. stop server in finally.

- [ ] **Step 7: Run and commit**

Run: python -m pytest tests/desktop -v

Expected: readiness, idempotent start, stop, port error, URL enumeration, add/remove callbacks, thread-safe view scheduling, and pending recovery pass.

~~~powershell
git add src/conf_edit/desktop src/conf_edit/logging_config.py src/conf_edit/__main__.py tests/desktop
git commit -m "feat: add Windows service controller"
~~~

### Task 11: Packaging, Documentation, and Full Verification

**Files:**
- Create: conf-edit.spec
- Create: scripts/build.ps1
- Create: README.md
- Modify: .gitignore
- Modify: pyproject.toml
- Modify: tests/e2e/test_web_workflows.py

**Interfaces:**
- Produces: dist/ConfEdit.exe
- Produces: operator and developer documentation

- [ ] **Step 1: Add failing package-resource test**

~~~python
def test_frontend_resources_are_packaged() -> None:
    from importlib.resources import files
    root = files("conf_edit")
    assert (root / "templates" / "index.html").is_file()
    assert (root / "static" / "css" / "app.css").is_file()
    assert (
        root / "static" / "vendor" / "codemirror"
        / "lib" / "codemirror.min.js"
    ).is_file()
~~~

- [ ] **Step 2: Configure package data**

Add:

~~~toml
[tool.setuptools.package-data]
conf_edit = [
  "templates/*.html",
  "static/css/*.css",
  "static/js/*.js",
  "static/vendor/codemirror/**/*.js",
  "static/vendor/codemirror/**/*.css",
  "static/vendor/codemirror/**/LICENSE",
]
~~~

- [ ] **Step 3: Configure PyInstaller**

conf-edit.spec must:

- use src/conf_edit/__main__.py;
- name the executable ConfEdit;
- set console=False;
- collect templates and static directories;
- collect sqlglot submodules;
- avoid embedding tests, source fixtures, database files, logs, or whitelist paths.

- [ ] **Step 4: Add deterministic build script**

~~~powershell
$ErrorActionPreference = "Stop"
$python = if (Test-Path ".venv\Scripts\python.exe") {
    ".venv\Scripts\python.exe"
} else {
    "python"
}
& $python -m pip install -e ".[dev]"
& $python -m pytest -q
& $python -m PyInstaller --clean --noconfirm conf-edit.spec
if (-not (Test-Path "dist\ConfEdit.exe")) {
    throw "dist\ConfEdit.exe was not produced"
}
~~~

- [ ] **Step 5: Write README**

README.md must document:

- supported JSON and SQL formats;
- launching ConfEdit.exe;
- equal permissions and Windows firewall/LAN warning;
- adding/removing files in the controller;
- JSON/SQL editing, validation, conflict handling, history, and rollback;
- unsupported SQL features;
- LOCALAPPDATA database/log locations;
- Python 3.12 development setup;
- unit/API/E2E commands;
- EXE build command.

- [ ] **Step 6: Run full automated verification**

Run:

~~~powershell
python -m pytest -q
python -m pytest --cov=conf_edit --cov-report=term-missing
git diff --check
~~~

Expected:

- all tests pass;
- parser, storage, services, and API modules reach at least 85% line coverage;
- git diff --check has no output;
- tests write only under temporary directories.

- [ ] **Step 7: Perform browser visual QA**

Verify at 1440x900, 1024x768, and 768x900:

- no unintended horizontal overflow;
- selected file/object and validation state are obvious;
- focus enters and leaves dialogs correctly;
- contrast and keyboard focus are visible;
- invalid save is impossible;
- reduced-motion removes sliding animation;
- Chinese text, long object names, empty states, unavailable files, and conflicts remain readable.

- [ ] **Step 8: Build and smoke-test EXE**

Run:

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
Start-Process -FilePath "dist\ConfEdit.exe"
~~~

Verify the Tkinter window opens without a console, service reaches running, Windows picker accepts JSON/SQL, a second LAN browser can load the URL, closing stops the service, and the EXE launches on a Windows machine without Python.

- [ ] **Step 9: Commit**

~~~powershell
git status --short
git add .gitignore pyproject.toml conf-edit.spec scripts README.md src tests
git commit -m "build: package and document ConfEdit"
~~~

## Final Acceptance Checklist

- [ ] JSON syntax, root type, item type, non-empty objectName, and single-file uniqueness are enforced.
- [ ] JSON CRUD preserves every untouched object source range.
- [ ] MySQL CREATE/INSERT parsing, grouping, comments, validation, CRUD, and unmanaged-statement preservation work.
- [ ] Whitelist IDs are the only browser-visible file identifiers; absolute paths never leave the controller.
- [ ] Every mutation uses revision matching, a PENDING history row, atomic replace, and APPLIED/FAILED recovery.
- [ ] History diff and rollback work, with rollback recorded as a new version.
- [ ] Browser UI matches the approved list + drawer design and works by keyboard.
- [ ] Tkinter controller manages service state and Windows file selection.
- [ ] Full automated tests pass and core coverage is at least 85%.
- [ ] dist/ConfEdit.exe runs without Python or Node installed.
