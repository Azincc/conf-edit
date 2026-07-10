(() => {
  const dialog = document.querySelector("#history-dialog");
  const historyState = {
    fileId: null,
    revision: null,
    origin: null,
    entries: [],
    selectedVersion: null,
  };

  const actionNames = {
    create: "新增",
    modify: "修改",
    delete: "删除",
    repair: "修复",
    rollback: "回滚",
  };

  const statusNames = {
    APPLIED: "已应用",
    PENDING: "待处理",
    FAILED: "失败",
    CONFLICTED: "冲突",
  };

  function activeFile() {
    return window.confEditState.activeFile;
  }

  function formatTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.valueOf())
      ? value
      : date.toLocaleString("zh-CN", {hour12: false});
  }

  function close() {
    dialog.close();
    historyState.origin?.focus?.();
    historyState.fileId = null;
    historyState.revision = null;
    historyState.entries = [];
    historyState.selectedVersion = null;
  }

  function renderShell() {
    const file = activeFile();
    dialog.innerHTML = `
      <div class="modal-shell history-shell">
        <header class="modal-header">
          <div>
            <p class="context-line">修改可追溯，回滚会创建新版本</p>
            <h2 id="history-title"></h2>
          </div>
          <button class="icon-button history-close" type="button" aria-label="关闭历史记录">×</button>
        </header>
        <div class="history-body">
          <div id="history-content" class="history-content" aria-live="polite">
            <div class="loading-state" aria-label="正在读取历史记录">
              <span class="loading-bar"></span>
              <span class="loading-bar"></span>
            </div>
          </div>
          <section id="history-detail" class="history-detail" aria-live="polite" hidden></section>
        </div>
      </div>
    `;
    dialog.querySelector("#history-title").textContent =
      `${file?.displayName || "当前文件"} · 历史记录`;
    dialog.querySelector(".history-close").addEventListener("click", close);
  }

  function entryLabel(entry) {
    const action = actionNames[entry.action] || entry.action;
    return entry.objectKey ? `${action} ${entry.objectKey}` : action;
  }

  function buildEntry(entry) {
    const item = document.createElement("article");
    item.className = "history-entry";

    const main = document.createElement("div");
    main.className = "history-entry-main";
    const title = document.createElement("strong");
    title.textContent = `v${entry.version} · ${entryLabel(entry)}`;
    const metadata = document.createElement("span");
    metadata.className = "history-entry-meta";
    const values = [formatTime(entry.createdAt)];
    if (entry.clientIp) values.push(entry.clientIp);
    metadata.textContent = values.join(" · ");
    main.append(title, metadata);

    if (entry.note) {
      const note = document.createElement("p");
      note.className = "history-note";
      note.textContent = entry.note;
      main.append(note);
    }

    const actions = document.createElement("div");
    actions.className = "history-entry-actions";
    const status = document.createElement("span");
    status.className = `history-status status-${entry.status.toLowerCase()}`;
    status.textContent = statusNames[entry.status] || entry.status;
    actions.append(status);
    if (entry.status === "APPLIED") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button button-inline history-diff-button";
      button.textContent = "查看差异";
      button.addEventListener("click", () => showDiff(entry));
      actions.append(button);
    }
    item.append(main, actions);
    return item;
  }

  function renderEntries() {
    const content = dialog.querySelector("#history-content");
    content.replaceChildren();
    if (!historyState.entries.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state history-empty";
      const title = document.createElement("h3");
      title.textContent = "还没有修改记录";
      const copy = document.createElement("p");
      copy.textContent = "保存、删除、修复或回滚后，版本会显示在这里。";
      empty.append(title, copy);
      content.append(empty);
      return;
    }

    const applied = historyState.entries
      .filter((entry) => entry.status === "APPLIED")
      .sort((left, right) => right.version - left.version);
    const diagnostic = historyState.entries
      .filter((entry) => entry.status !== "APPLIED")
      .sort((left, right) => right.version - left.version);

    const list = document.createElement("div");
    list.className = "history-list";
    for (const entry of applied) list.append(buildEntry(entry));
    content.append(list);

    if (diagnostic.length) {
      const disclosure = document.createElement("details");
      disclosure.className = "history-diagnostics";
      const summary = document.createElement("summary");
      summary.textContent = `${diagnostic.length} 条未应用诊断`;
      const diagnosticList = document.createElement("div");
      diagnosticList.className = "history-list";
      for (const entry of diagnostic) {
        diagnosticList.append(buildEntry(entry));
      }
      disclosure.append(summary, diagnosticList);
      content.append(disclosure);
    }
  }

  function renderDiffLines(container, diff) {
    const pre = document.createElement("pre");
    pre.className = "diff-view";
    for (const line of diff.split(/(?<=\n)/)) {
      const value = document.createElement("span");
      value.className = "diff-line";
      if (line.startsWith("+") && !line.startsWith("+++")) {
        value.classList.add("diff-add");
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        value.classList.add("diff-remove");
      } else if (line.startsWith("@@")) {
        value.classList.add("diff-range");
      }
      value.textContent = line || " ";
      pre.append(value);
    }
    container.append(pre);
  }

  async function showDiff(entry) {
    const detail = dialog.querySelector("#history-detail");
    historyState.selectedVersion = entry.version;
    detail.hidden = false;
    detail.textContent = "正在生成差异…";
    try {
      const payload = await window.confEditApi.request(
        `/api/files/${encodeURIComponent(historyState.fileId)}`
        + `/history/${entry.version}/diff`
      );
      detail.replaceChildren();
      const heading = document.createElement("div");
      heading.className = "history-detail-heading";
      const title = document.createElement("h3");
      title.textContent = `v${entry.version} · ${entryLabel(entry)}`;
      const rollbackButton = document.createElement("button");
      rollbackButton.type = "button";
      rollbackButton.className = "button button-secondary";
      rollbackButton.textContent = "回滚到此版本";
      rollbackButton.addEventListener("click", () => confirmRollback(entry));
      heading.append(title, rollbackButton);
      detail.append(heading);
      renderDiffLines(detail, payload.diff || "此版本没有文本差异。\n");
      detail.scrollIntoView({block: "nearest"});
    } catch (error) {
      detail.textContent = error.message;
      window.confEditApp.showToast(error.message, "error");
    }
  }

  function confirmRollback(entry) {
    const detail = dialog.querySelector("#history-detail");
    let confirmation = detail.querySelector(".rollback-confirmation");
    if (confirmation) {
      confirmation.querySelector("#rollback-confirm").focus();
      return;
    }
    confirmation = document.createElement("section");
    confirmation.className = "rollback-confirmation";
    confirmation.setAttribute("aria-label", "确认回滚");
    const message = document.createElement("p");
    message.textContent =
      `回滚到 v${entry.version} 会把该版本内容写成一个新的历史版本，`
      + "不会删除后续记录。";
    const actions = document.createElement("div");
    actions.className = "rollback-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "button button-secondary";
    cancel.textContent = "取消";
    cancel.addEventListener("click", () => confirmation.remove());
    const confirm = document.createElement("button");
    confirm.id = "rollback-confirm";
    confirm.type = "button";
    confirm.className = "button button-danger";
    confirm.textContent = "确认回滚";
    confirm.addEventListener("click", () => rollback(entry, confirm));
    actions.append(cancel, confirm);
    confirmation.append(message, actions);
    detail.append(confirmation);
    confirm.focus();
  }

  async function rollback(entry, button) {
    button.disabled = true;
    try {
      await window.confEditApi.request(
        `/api/files/${encodeURIComponent(historyState.fileId)}`
        + `/history/${entry.version}/rollback`,
        {
          method: "POST",
          body: JSON.stringify({revision: historyState.revision}),
        }
      );
      const fileId = historyState.fileId;
      close();
      await window.confEditApp.selectFile(fileId);
      window.confEditApp.showToast("回滚成功", "success");
    } catch (error) {
      button.disabled = false;
      window.confEditApp.showToast(error.message, "error");
    }
  }

  async function open(fileId, revision, origin) {
    historyState.fileId = fileId;
    historyState.revision = revision;
    historyState.origin = origin;
    renderShell();
    dialog.showModal();
    try {
      const payload = await window.confEditApi.request(
        `/api/files/${encodeURIComponent(fileId)}/history`
      );
      historyState.entries = payload.history || [];
      renderEntries();
    } catch (error) {
      dialog.querySelector("#history-content").textContent = error.message;
      window.confEditApp.showToast(error.message, "error");
    }
  }

  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });

  window.confEditHistory = {open};
})();
