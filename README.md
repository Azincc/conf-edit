# ConfEdit 配置对象管理器

ConfEdit 是一个面向 Windows 局域网团队的小型配置维护工具。维护者在本机控制窗口中指定允许访问的文件，同事通过浏览器按对象查看和编辑 JSON 模型或 MySQL 初始化脚本。浏览器只接触白名单文件 ID，不会看到服务端绝对路径。

## 支持的文件格式

### JSON 模型文件

- 文件编码必须为 UTF-8。
- 顶层必须是 JSON 数组。
- 数组中的每一项必须是 JSON object。
- 每一项必须包含非空字符串 `objectName`。
- `objectName` 在单个文件内大小写敏感且唯一。
- 保存前必须通过完整 JSON 校验；错误内容无法写入文件。

示例：

```json
[
  {
    "objectName": "User",
    "enabled": true
  },
  {
    "objectName": "Order",
    "fields": []
  }
]
```

### MySQL SQL 文件

ConfEdit 按表聚合并管理：

- `CREATE TABLE` 建表语句；
- 指向该表的 `INSERT INTO` 初始化语句；
- 表备注与字段备注；
- 文件中未被结构化管理的合法语句会原样保留。

SQL 方言固定为 MySQL。结构化编辑器不支持把视图、存储过程、触发器、`UPDATE`、`DELETE` 或其他 DDL 当作表对象管理。无法解析的语句会使整个文件进入修复模式，避免在不完整语法上继续写入。

## 运行 ConfEdit.exe

1. 双击 `ConfEdit.exe`。
2. 在控制窗口中确认服务状态和端口，默认端口为 `8765`。
3. 点击“添加文件”，通过 Windows 文件选择器选择 `.json` 或 `.sql` 文件并设置显示名。
4. 启动服务。
5. 将控制窗口显示的局域网地址发给同事，例如 `http://192.168.1.20:8765`。

控制窗口可以停止/启动服务、复制或打开地址、移除白名单文件、查看本机完整路径和最近 200 行日志。移除白名单不会删除磁盘文件。

## 局域网与权限说明

ConfEdit 不实现账号、登录或角色。任何能够访问该局域网地址的人都拥有相同的查看和编辑权限。只应在可信办公网络中运行，并只开放确实需要协作维护的文件。

首次监听局域网地址时，Windows 防火墙可能要求授权。只允许“专用网络”通常更安全。不要把端口映射到公网，也不要通过不受信任的代理暴露服务。

## 浏览器操作

- 左侧选择维护者开放的 JSON 或 SQL 文件。
- 中间列表按 `objectName` 或 MySQL 表名展示对象，可搜索、增加、编辑和删除。
- JSON 编辑器支持格式化；SQL 编辑器分为“建表语句”和“初始化语句”标签。
- 每次保存前必须先点击“校验”。内容再次变化后，保存会重新禁用。
- 修改备注可选，会随历史版本保存。
- 删除会明确显示目标名称并要求确认。

## 冲突、历史和修复

每次读取都会计算 SHA-256 修订号。若文件被其他同事或外部程序修改，ConfEdit 不会强制覆盖：当前草稿会保留，并提供复制草稿、查看磁盘差异和确认后重新加载的操作。

每次新增、修改、删除、修复和回滚都写入本机 SQLite 历史。历史窗口可以查看统一差异；回滚会创建一个新版本，不会删除后续记录。

若 JSON 或 SQL 文件已经损坏，对象列表会显示具体诊断。使用“整文件修复”打开完整源码，修复内容通过全文件校验后才能保存。

若程序在写入过程中异常退出，下一次启动会恢复未完成修订。无法自动判断时，只能由本机控制窗口执行“确认当前磁盘版本”；此操作明确接受磁盘内容为准。

## 本机数据位置

默认数据目录为：

```text
%LOCALAPPDATA%\ConfEdit\
```

其中：

- `conf-edit.db`：白名单、设置和历史修订；
- `logs\app.log`：UTF-8 运行日志，单文件 2 MiB，保留 5 个备份。

日志不会记录 JSON/SQL 源码、浏览器请求正文或防伪令牌。

## Python 开发

要求 Windows 10/11 x64 和 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

运行覆盖率：

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=conf_edit --cov-report=term-missing
```

首次运行浏览器测试时安装 Chromium：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest tests\e2e -v
```

直接从源码启动：

```powershell
.\.venv\Scripts\python.exe -m conf_edit
```

## 构建单文件 EXE

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

脚本会安装开发依赖、运行全部测试、执行干净的 PyInstaller 构建并生成：

```text
dist\ConfEdit.exe
```

EXE 内含 Flask、Waitress、sqlglot、Tkinter 页面资源和本地 CodeMirror，不要求目标机器安装 Python 或 Node，也不会从 CDN 下载前端资源。
