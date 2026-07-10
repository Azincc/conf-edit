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
  };

  function activeFile() {
    return window.confEditState.activeFile;
  }

  function currentDraft() {
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

  function renderShell(key, {creating = false} = {}) {
    const isSql = editorState.kind === "sql";
    dialog.innerHTML = `
      <div class="drawer-shell">
        <header class="drawer-header">
          <div>
            <p class="context-line"></p>
            <h2 id="editor-title"></h2>
          </div>
          <button class="icon-button drawer-close" type="button" aria-label="关闭编辑器">×</button>
        </header>
        <div class="drawer-body ${isSql ? "drawer-body-sql" : ""}">
          ${isSql ? sqlEditorMarkup() : jsonEditorMarkup()}
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
    dialog.querySelector(".context-line").textContent = isSql
      ? "MySQL 表对象"
      : "JSON 模型对象";
    dialog.querySelector("#editor-title").textContent = creating
      ? isSql
        ? "新增 MySQL 表"
        : "新增 JSON 对象"
      : `编辑 ${key}`;
    const deleteButton = dialog.querySelector("#editor-delete");
    deleteButton.textContent = isSql ? "删除表" : "删除对象";
    deleteButton.hidden = creating;
    deleteButton.addEventListener("click", remove);
    dialog.querySelector(".drawer-close").addEventListener("click", () => {
      closeDrawer();
    });
    dialog.querySelector("#editor-validate").addEventListener("click", validate);
    dialog.querySelector("#editor-save").addEventListener("click", save);
    if (isSql) {
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
    } else {
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

  async function validate() {
    const file = activeFile();
    if (!file || !Object.keys(editorState.editors).length) return;
    const validateButton = dialog.querySelector("#editor-validate");
    validateButton.disabled = true;
    try {
      const draft = currentDraft();
      await window.confEditApi.request(
        `/api/files/${encodeURIComponent(file.id)}/validate`,
        {
          method: "POST",
          body: JSON.stringify({
            scope: "object",
            originalKey: editorState.key,
            draft,
          }),
        }
      );
      editorState.validatedSignature = draftSignature(draft);
      dialog.querySelector("#editor-save").disabled = false;
      setValidation(
        file.kind === "sql" ? "SQL 校验通过" : "JSON 校验通过",
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
    const saveButton = dialog.querySelector("#editor-save");
    saveButton.disabled = true;
    try {
      const note = dialog.querySelector("#editor-note").value.trim() || null;
      const path = editorState.creating
        ? `/api/files/${encodeURIComponent(file.id)}/objects`
        : `/api/files/${encodeURIComponent(file.id)}/object`;
      const payload = editorState.creating
        ? {draft, revision: editorState.revision, note}
        : {
            originalKey: editorState.key,
            draft,
            revision: editorState.revision,
            note,
          };
      await window.confEditApi.request(path, {
        method: editorState.creating ? "POST" : "PUT",
        body: JSON.stringify(payload),
      });
      editorState.initialSignature = signature;
      closeDrawer({force: true});
      await window.confEditApp.selectFile(file.id);
      window.confEditApp.showToast("保存成功", "success");
    } catch (error) {
      setValidation(error.message, "error", error.details);
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
      setValidation(error.message, "error", error.details);
      window.confEditApp.showToast(error.message, "error");
    }
  }

  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDrawer();
  });

  window.confEditEditor = {openExisting, openCreate};
})();
