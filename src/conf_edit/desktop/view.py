from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from conf_edit.config import AppSettings
from conf_edit.desktop.controller import ControllerState, DesktopController
from conf_edit.domain.errors import DomainError
from conf_edit.domain.models import FileKind
from conf_edit.storage.settings_repository import SettingsRepository


def infer_file_kind(path: Path) -> FileKind:
    suffix = path.suffix.casefold()
    if suffix == ".json":
        return FileKind.JSON
    if suffix == ".sql":
        return FileKind.SQL
    raise ValueError("只支持 .json 和 .sql 文件")


def tail_lines(path: Path, limit: int = 200) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]


@dataclass(slots=True)
class TkDispatcher:
    root: tk.Misc

    def submit(self, callback: Callable, *args) -> None:
        self.root.after(0, lambda: callback(*args))


class DesktopView:
    STATUS = {
        "stopped": ("○", "服务已停止", "#475569"),
        "starting": ("◐", "服务启动中", "#1d4ed8"),
        "running": ("●", "服务运行中", "#15803d"),
        "failed": ("!", "服务启动失败", "#b4232f"),
    }
    FILE_STATUS = {
        "ready": "可编辑",
        "readonly": "只读",
        "missing": "文件缺失",
        "unreadable": "不可读取",
        "conflicted": "恢复冲突",
    }

    def __init__(
        self,
        root: tk.Tk,
        controller: DesktopController,
        settings_repository: SettingsRepository,
        settings: AppSettings,
        log_path: Path,
    ) -> None:
        self.root = root
        self.controller = controller
        self.settings_repository = settings_repository
        self.log_path = log_path
        self.dispatcher = TkDispatcher(root)
        self._unsubscribe: Callable[[], None] | None = None

        self.port_var = tk.StringVar(value=str(settings.port))
        self.auto_start_var = tk.BooleanVar(value=settings.auto_start)
        self.status_var = tk.StringVar(value="○ 服务已停止")
        self.error_var = tk.StringVar(value="")
        self.show_logs_var = tk.BooleanVar(value=False)

        self._configure_root()
        self._build()
        self._unsubscribe = controller.subscribe(self._schedule_state)

    def _configure_root(self) -> None:
        self.root.title("ConfEdit 控制窗口")
        self.root.minsize(760, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        header = ttk.Frame(container)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.status_label = tk.Label(
            header,
            textvariable=self.status_var,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        self.start_button = ttk.Button(
            header,
            text="启动服务",
            command=self.start_service,
        )
        self.start_button.grid(row=0, column=1, padx=(8, 0))
        self.stop_button = ttk.Button(
            header,
            text="停止服务",
            command=self.stop_service,
        )
        self.stop_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(
            container,
            textvariable=self.error_var,
            foreground="#b4232f",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 8))

        settings_frame = ttk.LabelFrame(container, text="服务设置", padding=10)
        settings_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        settings_frame.columnconfigure(5, weight=1)
        ttk.Label(settings_frame, text="端口").grid(row=0, column=0, sticky="w")
        self.port_entry = ttk.Entry(
            settings_frame,
            textvariable=self.port_var,
            width=8,
        )
        self.port_entry.grid(row=0, column=1, padx=(6, 16))
        ttk.Checkbutton(
            settings_frame,
            text="下次启动自动开启服务",
            variable=self.auto_start_var,
        ).grid(row=0, column=2, sticky="w")
        self.save_settings_button = ttk.Button(
            settings_frame,
            text="保存设置",
            command=self._save_settings,
        )
        self.save_settings_button.grid(row=0, column=3, padx=(16, 0))

        content = ttk.Panedwindow(container, orient="vertical")
        content.grid(row=3, column=0, sticky="nsew")

        upper = ttk.Frame(content)
        upper.columnconfigure(0, weight=1)
        upper.rowconfigure(1, weight=1)
        content.add(upper, weight=4)

        self.url_frame = ttk.LabelFrame(upper, text="访问地址", padding=8)
        self.url_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.url_frame.columnconfigure(0, weight=1)

        files_frame = ttk.LabelFrame(upper, text="允许访问的文件", padding=8)
        files_frame.grid(row=1, column=0, sticky="nsew")
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(0, weight=1)
        columns = ("name", "kind", "status", "path")
        self.files_tree = ttk.Treeview(
            files_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.files_tree.heading("name", text="显示名")
        self.files_tree.heading("kind", text="类型")
        self.files_tree.heading("status", text="状态")
        self.files_tree.heading("path", text="本机路径")
        self.files_tree.column("name", width=150, minwidth=100)
        self.files_tree.column("kind", width=70, minwidth=60, stretch=False)
        self.files_tree.column("status", width=90, minwidth=80, stretch=False)
        self.files_tree.column("path", width=390, minwidth=180)
        self.files_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            files_frame,
            orient="vertical",
            command=self.files_tree.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.files_tree.configure(yscrollcommand=scrollbar.set)
        self.files_tree.bind("<<TreeviewSelect>>", self._selection_changed)

        file_actions = ttk.Frame(files_frame)
        file_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(file_actions, text="添加文件", command=self._add_file).pack(
            side="left"
        )
        ttk.Button(file_actions, text="移除文件", command=self._remove_file).pack(
            side="left", padx=(8, 0)
        )
        self.conflict_button = ttk.Button(
            file_actions,
            text="确认当前磁盘版本",
            command=self._acknowledge_conflict,
        )
        self.conflict_button.pack(side="left", padx=(8, 0))
        self.conflict_button.state(["disabled"])

        logs_frame = ttk.LabelFrame(content, text="运行日志", padding=8)
        logs_frame.columnconfigure(0, weight=1)
        logs_frame.rowconfigure(1, weight=1)
        content.add(logs_frame, weight=2)
        ttk.Checkbutton(
            logs_frame,
            text="显示最近 200 行",
            variable=self.show_logs_var,
            command=self._toggle_logs,
        ).grid(row=0, column=0, sticky="w")
        self.log_text = tk.Text(
            logs_frame,
            height=8,
            wrap="none",
            state="disabled",
            font=("Cascadia Mono", 9),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.log_text.grid_remove()

    def _schedule_state(self, state: ControllerState) -> None:
        self.dispatcher.submit(self._render_state, state)

    def _render_state(self, state: ControllerState) -> None:
        symbol, text, color = self.STATUS.get(
            state.status,
            ("?", state.status, "#475569"),
        )
        self.status_var.set(f"{symbol} {text}")
        self.status_label.configure(foreground=color)
        self.error_var.set(state.error or "")
        stopped = state.status in {"stopped", "failed"}
        self.port_entry.configure(state="normal" if stopped else "disabled")
        self.save_settings_button.configure(
            state="normal" if stopped else "disabled"
        )
        self.start_button.configure(
            state="normal" if stopped else "disabled"
        )
        self.stop_button.configure(
            state="normal" if state.status == "running" else "disabled"
        )
        self._render_urls(state)
        self._render_files(state)
        if self.show_logs_var.get():
            self._refresh_logs()

    def _render_urls(self, state: ControllerState) -> None:
        for child in self.url_frame.winfo_children():
            child.destroy()
        for row, url in enumerate(state.urls):
            ttk.Label(self.url_frame, text=url).grid(
                row=row,
                column=0,
                sticky="w",
                pady=2,
            )
            ttk.Button(
                self.url_frame,
                text="复制",
                command=lambda value=url: self._copy_url(value),
            ).grid(row=row, column=1, padx=(8, 4))
            ttk.Button(
                self.url_frame,
                text="打开",
                command=lambda value=url: self._open_url(value),
            ).grid(row=row, column=2)

    def _render_files(self, state: ControllerState) -> None:
        selected = self._selected_file_id()
        self.files_tree.delete(*self.files_tree.get_children())
        for file in state.files:
            self.files_tree.insert(
                "",
                "end",
                iid=file.id,
                values=(
                    file.display_name,
                    file.kind.value.upper(),
                    self.FILE_STATUS.get(file.status, file.status),
                    str(file.path),
                ),
            )
        if selected and self.files_tree.exists(selected):
            self.files_tree.selection_set(selected)
        self._selection_changed()

    def _run_async(self, action: Callable[[], None]) -> None:
        def run() -> None:
            try:
                action()
            except Exception as exc:  # controller errors are surfaced locally
                message = str(exc)
                self.dispatcher.submit(
                    lambda value=message: messagebox.showerror(
                        "操作失败",
                        value,
                        parent=self.root,
                    )
                )

        threading.Thread(target=run, name="conf-edit-control", daemon=True).start()

    def start_service(self) -> None:
        self._run_async(self.controller.start)

    def stop_service(self) -> None:
        self._run_async(self.controller.stop)

    def _save_settings(self) -> None:
        try:
            port = int(self.port_var.get().strip())
            self.controller.set_port(port)
            self.settings_repository.save(
                AppSettings(
                    port=port,
                    auto_start=self.auto_start_var.get(),
                )
            )
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("设置无效", str(exc), parent=self.root)

    def _add_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="选择 JSON 或 SQL 文件",
            filetypes=(
                ("配置文件", "*.json *.sql"),
                ("JSON 文件", "*.json"),
                ("SQL 文件", "*.sql"),
            ),
        )
        if not selected:
            return
        path = Path(selected)
        try:
            kind = infer_file_kind(path)
        except ValueError as exc:
            messagebox.showerror("文件类型不支持", str(exc), parent=self.root)
            return
        display_name = simpledialog.askstring(
            "文件显示名",
            "请输入同事在网页中看到的文件名称：",
            initialvalue=path.stem,
            parent=self.root,
        )
        if display_name is None:
            return
        try:
            self.controller.add_file(path, kind, display_name)
        except DomainError as exc:
            messagebox.showerror("无法添加文件", exc.message, parent=self.root)

    def _selected_file_id(self) -> str | None:
        selected = self.files_tree.selection()
        return selected[0] if selected else None

    def _remove_file(self) -> None:
        file_id = self._selected_file_id()
        if not file_id:
            return
        values = self.files_tree.item(file_id, "values")
        name = values[0] if values else file_id
        if not messagebox.askyesno(
            "移除文件",
            f"确定停止向同事开放“{name}”吗？不会删除磁盘文件。",
            parent=self.root,
        ):
            return
        self.controller.remove_file(file_id)

    def _selection_changed(self, _event=None) -> None:
        file_id = self._selected_file_id()
        conflicted = any(
            file.id == file_id and file.status == "conflicted"
            for file in self.controller.state.files
        )
        self.conflict_button.state(["!disabled"] if conflicted else ["disabled"])

    def _acknowledge_conflict(self) -> None:
        file_id = self._selected_file_id()
        if not file_id:
            return
        confirmed = messagebox.askyesno(
            "确认当前磁盘版本",
            "此操作会把当前磁盘内容设为可信版本，并放弃中断修订作为恢复来源。继续吗？",
            icon="warning",
            parent=self.root,
        )
        if confirmed:
            self.controller.acknowledge_conflict(file_id, True)

    def _copy_url(self, url: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(url)

    def _open_url(self, url: str) -> None:
        self.controller.open_browser(url)

    def _toggle_logs(self) -> None:
        if self.show_logs_var.get():
            self.log_text.grid()
            self._refresh_logs()
        else:
            self.log_text.grid_remove()

    def _refresh_logs(self) -> None:
        value = "\n".join(tail_lines(self.log_path))
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", value)
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def _on_close(self) -> None:
        if self.controller.state.status == "running" and not messagebox.askyesno(
            "退出 ConfEdit",
            "退出会停止局域网编辑服务，确定继续吗？",
            parent=self.root,
        ):
            return
        self.controller.stop()
        if self._unsubscribe is not None:
            self._unsubscribe()
        self.root.destroy()
