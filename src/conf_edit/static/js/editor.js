(() => {
  const dialog = document.querySelector("#editor-drawer");
  const editorState = {
    kind: null,
    key: null,
    revision: null,
    origin: null,
    editors: {},
    initialSignature: "",
    validatedSignature: null,
    loading: false,
    creating: false,
    repairing: false,
  };

  function activeFile() {
    return window.confEditState.activeFile;
  }

  function currentDraft() {
    if (editorState.repairing) {
      return {source: editorState.editors.file?.getValue() || ""};
    }
    if (editorState.kind === "sql") {
      return {
        createSql: editorState.editors.create?.getValue() || "",
        insertSql: editorState.editors.insert?.getValue() || "",
      };
    }
    return {raw: editorState.editors.json?.getValue() || ""};
  }

  function draftSignature(draft = currentDraft()) {
    return JSON.stringify(draft);
  }

  function isDirty() {
    if (!Object.keys(editorState.editors).length) return false;
    return draftSignature() !== editorState.initialSignature;
  }

  function setValidation(message, tone = "neutral", details = null) {
    const panel = dialog.querySelector("#editor-validation");
    if (!panel) return;
    panel.className = `editor-validation validation-${tone}`;
    panel.replaceChildren();
    const messageNode = document.createElement("span");
    messageNode.textContent = message;
    panel.append(messageNode);
    if (details?.line || details?.column || details?.statement) {
      const location = document.createElement("span");
      location.className = "validation-location";
      const values = [];
      if (details.statement) values.push(`第 ${details.statement} 条语句`);
      if (details.line) values.push(`第 ${details.line} 行`);
      if (details.column) values.push(`第 ${details.column} 列`);
      location.textContent = values.join("，");
      panel.append(location);
    }
  }

  function invalidateValidation() {
    editorState.validatedSignature = null;
    const saveButton = dialog.querySelector("#editor-save");
    if (saveButton) saveButton.disabled = true;
    setValidation("内容变化后需要重新校验");
  }

  function disposeEditors() {
    for (const editor of Object.values(editorState.editors)) {
      editor?.toTextArea?.();
    }
    editorState.editors = {};
  }

  function closeDrawer({force = false} = {}) {
    if (!force && !editorState.loading && isDirty()) {
      const discard = window.confirm("当前修改尚未保存，确定关闭编辑器吗？");
      if (!discard) return;
    }
    dialog.close();
    const origin = editorState.origin;
    disposeEditors();
    editorState.kind = null;
    editorState.key = null;
    editorState.revision = null;
    editorState.initialSignature = "";
    editorState.validatedSignature = null;
    editorState.creating = false;
    editorState.repairing = false;
    origin?.focus?.();
  }

  function jsonEditorMarkup() {
    return `
      <div class="editor-heading">
        <span id="json-editor-label">JSON 对象</span>
        <button id="json-format" class="button button-inline" type="button">格式化 JSON</button>
      </div>
      <textarea id="json-source" aria-hidden="true"></textarea>
    `;
  }

  function sqlEditorMarkup() {
    return `
      <div class="editor-tabs" role="tablist" aria-label="SQL 编辑区">
        <button id="sql-create-tab" class="editor-tab" type="button" role="tab"
          aria-selected="true" aria-controls="sql-create-panel">建表语句</button>
        <button id="sql-insert-tab" class="editor-tab" type="button" role="tab"
          aria-selected="false" aria-controls="sql-insert-panel" tabindex="-1">初始化语句</button>
      </div>
      <section id="sql-create-panel" class="editor-panel" role="tabpanel"
        aria-labelledby="sql-create-tab">
        <span id="sql-create-label" class="visually-hidden">建表语句</span>
        <textarea id="sql-create-source" aria-hidden="true"></textarea>
      </section>
      <section id="sql-insert-panel" class="editor-panel" role="tabpanel"
        aria-labelledby="sql-insert-tab" hidden>
        <span id="sql-insert-label" class="visually-hidden">初始化语句</span>
        <textarea id="sql-insert-source" aria-hidden="true"></textarea>
      </section>
    `;
  }

  function repairEditorMarkup(isSql) {
    const label = isSql ? "完整 SQL 文件" : "完整 JSON 文件";
    return `
      <div class="editor-heading">
        <span id="repair-editor-label">${label}</span>
      </div>
      <textarea id="repair-source" aria-hidden="true"></textarea>
    `;
  }

  function renderShell(key, {creating = false} = {}) {
    const isSql = editorState.kind === "sql";
    const repairing = editorState.repairing;
    dialog.innerHTML = `
      <div class="drawer-shell">
        <header class="drawer-header">
          <div>
            <p class="context-line"></p>
            <h2 id="editor-title"></h2>
          </div>
          <button class="icon-button drawer-close" type="button" aria-label="关闭编辑器">×</button>
        </header>
        <div class="drawer-body ${isSql && !repairing ? "drawer-body-sql" : ""}">
          ${repairing
            ? repairEditorMarkup(isSql)
            : isSql
              ? sqlEditorMarkup()
              : jsonEditorMarkup()}
          <div id="editor-validation" class="editor-validation validation-neutral" role="status" aria-live="polite">
            等待加载对象
          </div>
          <label class="note-field" for="editor-note">
            <span>修改备注（可选）</span>
            <input id="editor-note" type="text" maxlength="200" placeholder="例如：补充字段说明">
          </label>
        </div>
        <footer class="drawer-footer">
          <button id="editor-delete" class="button button-danger" type="button"></button>
          <button id="editor-validate" class="button button-secondary" type="button">校验</button>
          <button id="editor-save" class="button button-primary" type="button" disabled>保存</button>
        </footer>
      </div>
    `;
    dialog.querySelector(".context-line").textContent = repairing
      ? isSql
        ? "MySQL 整文件修复"
        : "JSON 整文件修复"
      : isSql
        ? "MySQL 表对象"
        : "JSON 模型对象";
    dialog.querySelector("#editor-title").textContent = repairing
      ? `修复 ${activeFile()?.displayName || "当前文件"}`
      : creating
        ? isSql
          ? "新增 MySQL 表"
          : "新增 JSON 对象"
        : `编辑 ${key}`;
    const deleteButton = dialog.querySelector("#editor-delete");
    deleteButton.textContent = isSql ? "删除表" : "删除对象";
    deleteButton.hidden = creating || repairing;
    deleteButton.addEventListener("click", remove);
    dialog.querySelector("#editor-validate").textContent = repairing
      ? "校验完整文件"
      : "校验";
    dialog.querySelector("#editor-save").textContent = repairing
      ? "保存修复"
      : "保存";
    dialog.querySelector(".drawer-close").addEventListener("click", () => {
      closeDrawer();
    });
    dialog.querySelector("#editor-validate").addEventListener("click", validate);
    dialog.querySelector("#editor-save").addEventListener("click", save);
    if (isSql && !repairing) {
      dialog.querySelector("#sql-create-tab").addEventListener("click", () => {
        activateSqlTab("create");
      });
      dialog.querySelector("#sql-insert-tab").addEventListener("click", () => {
        activateSqlTab("insert");
      });
      dialog.querySelector(".editor-tabs").addEventListener(
        "keydown",
        handleSqlTabKeydown
      );
    } else if (!repairing) {
      dialog.querySelector("#json-format").addEventListener("click", formatJson);
    }
  }

  function handleSqlTabKeydown(event) {
    const order = ["create", "insert"];
    const current = event.target.id === "sql-insert-tab" ? 1 : 0;
    let next = null;
    if (event.key === "ArrowRight") next = (current + 1) % order.length;
    if (event.key === "ArrowLeft") {
      next = (current - 1 + order.length) % order.length;
    }
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = order.length - 1;
    if (next === null) return;
    event.preventDefault();
    const name = order[next];
    activateSqlTab(name, {focus: false});
    dialog.querySelector(`#sql-${name}-tab`).focus();
  }

  function formatJson() {
    const editor = editorState.editors.json;
    if (!editor) return;
    try {
      editor.setValue(JSON.stringify(JSON.parse(editor.getValue()), null, 2));
    } catch (error) {
      setValidation(`无法格式化：${error.message}`, "error");
    }
  }

  function draftText(draft = currentDraft()) {
    if (editorState.repairing) return draft.source;
    if (editorState.kind === "sql") {
      const blocks = [`-- 建表语句\n${draft.createSql}`];
      if (draft.insertSql.trim()) {
        blocks.push(`-- 初始化语句\n${draft.insertSql}`);
      }
      return blocks.join("\n\n");
    }
    return draft.raw;
  }

  function payloadDraft(payload) {
    if (editorState.repairing) return {source: payload.source};
    return editorState.kind === "sql"
      ? {createSql: payload.createSql, insertSql: payload.insertSql}
      : {raw: payload.raw};
  }

  async function copyText(value) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (_error) {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.setAttribute("readonly", "");
      textarea.className = "clipboard-fallback";
      document.body.append(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) throw new Error("copy_failed");
    }
  }

  function showConflict(error) {
    setValidation(error.message, "error", error.details);
    dialog.querySelector("#editor-save").disabled = true;
    dialog.querySelector("#conflict-panel")?.remove();
    const panel = document.createElement("section");
    panel.id = "conflict-panel";
    panel.className = "conflict-panel";
    panel.setAttribute("aria-labelledby", "conflict-title");
    panel.innerHTML = `
      <div class="conflict-heading">
        <h3 id="conflict-title">先保留编辑，再处理磁盘变化</h3>
        <p>不会强制覆盖文件。你可以复制草稿、比较差异，或确认后重新加载。</p>
      </div>
      <div class="conflict-actions">
        <button class="button button-secondary conflict-copy" type="button">复制我的编辑内容</button>
        <button class="button button-secondary conflict-compare-button" type="button">查看差异</button>
        <button class="button button-secondary conflict-reload" type="button">重新加载磁盘版本</button>
      </div>
      <div class="conflict-detail" aria-live="polite"></div>
    `;
    dialog.querySelector("#editor-validation").after(panel);
    panel.querySelector(".conflict-copy").addEventListener("click", async () => {
      try {
        await copyText(draftText());
        window.confEditApp.showToast("编辑内容已复制", "success");
      } catch (_copyError) {
        window.confEditApp.showToast("无法访问剪贴板，请手动复制编辑内容", "error");
      }
    });
    panel.querySelector(".conflict-compare-button").addEventListener(
      "click",
      viewDiskComparison
    );
    panel.querySelector(".conflict-reload").addEventListener(
      "click",
      reloadDiskVersion
    );
    panel.scrollIntoView({block: "nearest"});
  }

  async function loadDiskObject() {
    const file = activeFile();
    if (!file) throw new Error("当前文件不可用");
    if (editorState.repairing) {
      return window.confEditApi.request(
        `/api/files/${encodeURIComponent(file.id)}/source`
      );
    }
    if (!editorState.key) {
      throw new Error("新增对象尚无可重新加载的磁盘版本");
    }
    return window.confEditApi.request(
      `/api/files/${encodeURIComponent(file.id)}/object?key=${encodeURIComponent(editorState.key)}`
    );
  }

  async function viewDiskComparison(event) {
    const button = event.currentTarget;
    const detail = dialog.querySelector(".conflict-detail");
    button.disabled = true;
    detail.textContent = "正在读取磁盘版本…";
    try {
      const payload = await loadDiskObject();
      const comparison = document.createElement("div");
      comparison.className = "conflict-comparison";
      const local = document.createElement("section");
      local.className = "conflict-local";
      const localTitle = document.createElement("h4");
      localTitle.textContent = "我的内容";
      const localSource = document.createElement("pre");
      localSource.textContent = draftText();
      local.append(localTitle, localSource);

      const disk = document.createElement("section");
      disk.className = "conflict-disk";
      const diskTitle = document.createElement("h4");
      diskTitle.textContent = "磁盘内容";
      const diskSource = document.createElement("pre");
      diskSource.textContent = draftText(payloadDraft(payload));
      disk.append(diskTitle, diskSource);
      comparison.append(local, disk);
      detail.replaceChildren(comparison);
    } catch (error) {
      detail.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  async function reloadDiskVersion(event) {
    const confirmed = window.confirm(
      "重新加载会丢弃当前未保存的编辑内容，确定继续吗？"
    );
    if (!confirmed) return;
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const payload = await loadDiskObject();
      const draft = payloadDraft(payload);
      if (editorState.repairing) {
        editorState.editors.file.setValue(draft.source);
      } else if (editorState.kind === "sql") {
        editorState.editors.create.setValue(draft.createSql);
        editorState.editors.insert.setValue(draft.insertSql);
      } else {
        editorState.editors.json.setValue(draft.raw);
      }
      if (payload.key) editorState.key = payload.key;
      editorState.revision = payload.revision;
      editorState.initialSignature = draftSignature(draft);
      editorState.validatedSignature = null;
      editorState.creating = false;
      dialog.querySelector("#editor-save").disabled = true;
      dialog.querySelector("#conflict-panel")?.remove();
      setValidation("已加载磁盘版本");
    } catch (error) {
      button.disabled = false;
      dialog.querySelector(".conflict-detail").textContent = error.message;
      window.confEditApp.showToast(error.message, "error");
    }
  }

  function createCodeEditor({textareaId, labelId, label, value, mode}) {
    const textarea = dialog.querySelector(`#${textareaId}`);
    textarea.value = value;
    const editor = window.CodeMirror.fromTextArea(textarea, {
      mode,
      inputStyle: "contenteditable",
      lineNumbers: true,
      lineWrapping: true,
      matchBrackets: true,
      indentUnit: 2,
      tabSize: 2,
    });
    const input = editor.getInputField();
    textarea.setAttribute("aria-hidden", "true");
    input.setAttribute("role", "textbox");
    input.setAttribute("aria-multiline", "true");
    input.setAttribute("aria-label", label);
    input.setAttribute("aria-labelledby", labelId);
    editor.setSize("100%", "100%");
    editor.on("change", invalidateValidation);
    return editor;
  }

  function initializeDraft(draft, {focus = true} = {}) {
    if (editorState.kind === "sql") {
      editorState.editors.create = createCodeEditor({
        textareaId: "sql-create-source",
        labelId: "sql-create-label",
        label: "建表语句",
        value: draft.createSql,
        mode: "text/x-mysql",
      });
      editorState.editors.insert = createCodeEditor({
        textareaId: "sql-insert-source",
        labelId: "sql-insert-label",
        label: "初始化语句",
        value: draft.insertSql,
        mode: "text/x-mysql",
      });
      activateSqlTab("create", {focus});
    } else {
      editorState.editors.json = createCodeEditor({
        textareaId: "json-source",
        labelId: "json-editor-label",
        label: "JSON 对象",
        value: draft.raw,
        mode: {name: "javascript", json: true},
      });
      window.setTimeout(() => {
        editorState.editors.json?.refresh();
        if (focus) editorState.editors.json?.focus();
      }, 0);
    }
    editorState.initialSignature = draftSignature(draft);
  }

  function initializeRepair(source, {focus = true} = {}) {
    const isSql = editorState.kind === "sql";
    const label = isSql ? "完整 SQL 文件" : "完整 JSON 文件";
    const draft = {source};
    editorState.editors.file = createCodeEditor({
      textareaId: "repair-source",
      labelId: "repair-editor-label",
      label,
      value: source,
      mode: isSql ? "text/x-mysql" : {name: "javascript", json: true},
    });
    editorState.initialSignature = draftSignature(draft);
    window.setTimeout(() => {
      editorState.editors.file?.refresh();
      if (focus) editorState.editors.file?.focus();
    }, 0);
  }

  function activateSqlTab(name, {focus = true} = {}) {
    const names = ["create", "insert"];
    for (const item of names) {
      const selected = item === name;
      const tab = dialog.querySelector(`#sql-${item}-tab`);
      const panel = dialog.querySelector(`#sql-${item}-panel`);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panel.hidden = !selected;
    }
    window.setTimeout(() => {
      editorState.editors[name]?.refresh();
      if (focus) editorState.editors[name]?.focus();
    }, 0);
  }

  async function openExisting(key, origin) {
    const file = activeFile();
    if (!file) return;
    editorState.kind = file.kind;
    editorState.key = key;
    editorState.origin = origin;
    editorState.loading = true;
    editorState.creating = false;
    editorState.repairing = false;
    renderShell(key);
    dialog.showModal();
    try {
      const payload = await window.confEditApi.request(
        `/api/files/${encodeURIComponent(file.id)}/object?key=${encodeURIComponent(key)}`
      );
      editorState.revision = payload.revision;
      const draft = file.kind === "sql"
        ? {createSql: payload.createSql, insertSql: payload.insertSql}
        : {raw: payload.raw};
      initializeDraft(draft);
      setValidation(
        file.kind === "sql"
          ? "请先校验建表与初始化语句"
          : "请先校验当前 JSON 对象"
      );
    } catch (error) {
      setValidation(error.message, "error", error.details);
      window.confEditApp.showToast(error.message, "error");
    } finally {
      editorState.loading = false;
    }
  }

  function openCreate(origin) {
    const file = activeFile();
    if (!file) return;
    editorState.kind = file.kind;
    editorState.key = null;
    editorState.revision = window.confEditState.revision;
    editorState.origin = origin;
    editorState.loading = false;
    editorState.creating = true;
    editorState.repairing = false;
    renderShell("", {creating: true});
    dialog.showModal();
    const draft = file.kind === "sql"
      ? {
          createSql:
            "CREATE TABLE table_name (\n"
            + "  id bigint NOT NULL COMMENT '主键'\n"
            + ") COMMENT='表说明';",
          insertSql: "",
        }
      : {raw: '{\n  "objectName": ""\n}'};
    initializeDraft(draft);
    setValidation("请输入内容并完成校验");
  }

  async function openRepair(details, origin) {
    const file = activeFile();
    if (!file) return;
    editorState.kind = file.kind;
    editorState.key = null;
    editorState.revision = details?.revision || window.confEditState.revision;
    editorState.origin = origin;
    editorState.loading = true;
    editorState.creating = false;
    editorState.repairing = true;
    renderShell("");
    dialog.showModal();
    try {
      const payload = await window.confEditApi.request(
        `/api/files/${encodeURIComponent(file.id)}/source`
      );
      editorState.revision = payload.revision;
      initializeRepair(payload.source);
      setValidation("请修复完整文件并完成校验");
    } catch (error) {
      setValidation(error.message, "error", error.details);
      window.confEditApp.showToast(error.message, "error");
    } finally {
      editorState.loading = false;
    }
  }

  async function validate() {
    const file = activeFile();
    if (!file || !Object.keys(editorState.editors).length) return;
    const validateButton = dialog.querySelector("#editor-validate");
    validateButton.disabled = true;
    try {
      const draft = currentDraft();
      const body = editorState.repairing
        ? {scope: "file", source: draft.source}
        : {
            scope: "object",
            originalKey: editorState.key,
            draft,
          };
      await window.confEditApi.request(
        `/api/files/${encodeURIComponent(file.id)}/validate`,
        {
          method: "POST",
          body: JSON.stringify(body),
        }
      );
      editorState.validatedSignature = draftSignature(draft);
      dialog.querySelector("#editor-save").disabled = false;
      setValidation(
        editorState.repairing
          ? "文件校验通过"
          : file.kind === "sql"
            ? "SQL 校验通过"
            : "JSON 校验通过",
        "success"
      );
    } catch (error) {
      editorState.validatedSignature = null;
      dialog.querySelector("#editor-save").disabled = true;
      setValidation(error.message, "error", error.details);
    } finally {
      validateButton.disabled = false;
    }
  }

  async function save() {
    const file = activeFile();
    const draft = currentDraft();
    const signature = draftSignature(draft);
    if (!file || signature !== editorState.validatedSignature) return;
    const repairing = editorState.repairing;
    const saveButton = dialog.querySelector("#editor-save");
    saveButton.disabled = true;
    try {
      const note = dialog.querySelector("#editor-note").value.trim() || null;
      const path = repairing
        ? `/api/files/${encodeURIComponent(file.id)}/repair`
        : editorState.creating
          ? `/api/files/${encodeURIComponent(file.id)}/objects`
          : `/api/files/${encodeURIComponent(file.id)}/object`;
      const payload = repairing
        ? {
            source: draft.source,
            revision: editorState.revision,
            note,
          }
        : editorState.creating
          ? {draft, revision: editorState.revision, note}
          : {
              originalKey: editorState.key,
              draft,
              revision: editorState.revision,
              note,
            };
      await window.confEditApi.request(path, {
        method: editorState.creating && !repairing ? "POST" : "PUT",
        body: JSON.stringify(payload),
      });
      editorState.initialSignature = signature;
      closeDrawer({force: true});
      await window.confEditApp.selectFile(file.id);
      window.confEditApp.showToast(
        repairing ? "修复成功" : "保存成功",
        "success"
      );
    } catch (error) {
      if (error.status === 409) {
        showConflict(error);
      } else {
        setValidation(error.message, "error", error.details);
      }
      window.confEditApp.showToast(error.message, "error");
    }
  }

  async function remove() {
    const file = activeFile();
    if (!file || editorState.creating || !editorState.key) return;
    const label = file.kind === "sql" ? "表" : "";
    const confirmed = window.confirm(
      `确定删除${label}“${editorState.key}”吗？此操作会记录到历史。`
    );
    if (!confirmed) return;
    const deleteButton = dialog.querySelector("#editor-delete");
    deleteButton.disabled = true;
    try {
      await window.confEditApi.request(
        `/api/files/${encodeURIComponent(file.id)}/object`,
        {
          method: "DELETE",
          body: JSON.stringify({
            key: editorState.key,
            revision: editorState.revision,
            note: dialog.querySelector("#editor-note").value.trim() || null,
          }),
        }
      );
      editorState.initialSignature = draftSignature();
      closeDrawer({force: true});
      await window.confEditApp.selectFile(file.id);
      window.confEditApp.showToast("删除成功", "success");
    } catch (error) {
      deleteButton.disabled = false;
      if (error.status === 409) {
        showConflict(error);
      } else {
        setValidation(error.message, "error", error.details);
      }
      window.confEditApp.showToast(error.message, "error");
    }
  }

  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDrawer();
  });

  window.confEditEditor = {openExisting, openCreate, openRepair};
})();
