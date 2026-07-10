(() => {
  const state = {
    files: [],
    activeFile: null,
    objects: [],
    revision: null,
    query: "",
  };

  const elements = {
    fileList: document.querySelector("#file-list"),
    fileStatus: document.querySelector("#file-status"),
    fileTitle: document.querySelector("#file-title"),
    fileKind: document.querySelector("#file-kind"),
    objectCount: document.querySelector("#object-count"),
    objectList: document.querySelector("#object-list"),
    objectSearch: document.querySelector("#object-search"),
    createButton: document.querySelector("#create-button"),
    historyButton: document.querySelector("#history-button"),
    refreshFiles: document.querySelector("#refresh-files"),
    toastRegion: document.querySelector("#toast-region"),
  };

  function showToast(message, tone = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${tone}`;
    toast.textContent = message;
    elements.toastRegion.replaceChildren(toast);
    window.setTimeout(() => toast.remove(), 3600);
  }

  function fileStatusText(file) {
    const names = {
      ready: "有效",
      readonly: "只读",
      invalid: "格式错误",
      missing: "文件缺失",
      unreadable: "不可读取",
      conflicted: "存在冲突",
    };
    return names[file.status] || file.status;
  }

  function renderFiles() {
    elements.fileList.replaceChildren();
    for (const kind of ["json", "sql"]) {
      const group = state.files.filter((file) => file.kind === kind);
      if (!group.length) continue;
      const section = document.createElement("section");
      section.className = "file-group";
      const heading = document.createElement("h3");
      heading.textContent = kind === "json" ? "JSON 模型" : "MySQL 脚本";
      section.append(heading);
      for (const file of group) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "file-row";
        button.dataset.fileId = file.id;
        button.setAttribute("aria-label", file.displayName);
        button.setAttribute(
          "aria-current",
          state.activeFile?.id === file.id ? "page" : "false"
        );
        const name = document.createElement("span");
        name.className = "file-row-name";
        name.textContent = file.displayName;
        const meta = document.createElement("span");
        meta.className = `file-row-meta status-${file.status}`;
        meta.textContent = `${kind.toUpperCase()} · ${fileStatusText(file)}`;
        button.append(name, meta);
        button.addEventListener("click", () => selectFile(file.id));
        section.append(button);
      }
      elements.fileList.append(section);
    }
    if (!state.files.length) {
      const empty = document.createElement("p");
      empty.className = "sidebar-empty";
      empty.textContent = "控制窗口尚未添加可访问文件。";
      elements.fileList.append(empty);
    }
  }

  function filteredObjects() {
    const query = state.query.trim().toLocaleLowerCase();
    if (!query) return state.objects;
    return state.objects.filter((item) =>
      item.key.toLocaleLowerCase().includes(query)
    );
  }

  function renderObjects() {
    elements.objectList.replaceChildren();
    const objects = filteredObjects();
    if (!state.activeFile) return;
    if (!objects.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("h2");
      title.textContent = state.query ? "没有匹配对象" : "文件中还没有对象";
      const copy = document.createElement("p");
      copy.textContent = state.query
        ? "调整搜索内容，或清空搜索框查看全部对象。"
        : "使用“新增对象”创建第一项配置。";
      empty.append(title, copy);
      elements.objectList.append(empty);
      return;
    }
    for (const item of objects) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "object-row";
      row.setAttribute("aria-label", `编辑 ${item.key}`);
      const identity = document.createElement("span");
      identity.className = "object-identity";
      const name = document.createElement("strong");
      name.textContent = item.key;
      const summary = document.createElement("span");
      summary.className = "object-summary";
      summary.textContent =
        state.activeFile.kind === "json"
          ? `${item.fieldCount} 个字段`
          : `${item.fieldCount} 个字段 · ${item.insertCount} 条初始化`;
      identity.append(name, summary);
      const status = document.createElement("span");
      status.className = "validation-chip";
      status.textContent = "✓ 有效";
      const affordance = document.createElement("span");
      affordance.className = "row-affordance";
      affordance.textContent = "编辑";
      row.append(identity, status, affordance);
      row.addEventListener("click", () => {
        window.confEditEditor?.openExisting?.(item.key, row);
      });
      elements.objectList.append(row);
    }
  }

  async function selectFile(fileId) {
    const file = state.files.find((item) => item.id === fileId);
    if (!file) return;
    state.activeFile = file;
    state.query = "";
    elements.objectSearch.value = "";
    renderFiles();
    elements.fileTitle.textContent = file.displayName;
    elements.fileKind.textContent =
      file.kind === "json" ? "JSON 模型对象" : "MySQL 表对象";
    elements.fileStatus.textContent = `${file.displayName} · 正在读取`;
    elements.objectList.innerHTML =
      '<div class="loading-state"><span class="loading-bar"></span><span class="loading-bar"></span></div>';
    try {
      const payload = await window.confEditApi.request(
        `/api/files/${encodeURIComponent(file.id)}/objects`
      );
      state.objects = payload.objects;
      state.revision = payload.revision;
      elements.fileStatus.textContent =
        `${file.displayName} · ${payload.writable ? "可编辑" : "只读"}`;
      elements.objectCount.textContent =
        `${payload.objects.length} 个对象` +
        (payload.unmanagedCount
          ? ` · ${payload.unmanagedCount} 段未管理语句`
          : "");
      elements.objectSearch.disabled = false;
      elements.createButton.disabled = !payload.writable;
      elements.historyButton.disabled = false;
      renderObjects();
    } catch (error) {
      state.objects = [];
      state.revision = error.details?.revision || null;
      elements.fileStatus.textContent = `${file.displayName} · 读取失败`;
      elements.objectCount.textContent = error.message;
      elements.objectSearch.disabled = true;
      elements.createButton.disabled = true;
      elements.historyButton.disabled = !state.revision;
      const panel = document.createElement("div");
      panel.className = "diagnostic-panel";
      const title = document.createElement("h2");
      title.textContent = "文件无法解析";
      const copy = document.createElement("p");
      copy.textContent = error.message;
      panel.append(title, copy);
      const locations = [];
      if (error.details?.statement) {
        locations.push(`第 ${error.details.statement} 条语句`);
      }
      if (error.details?.line) locations.push(`第 ${error.details.line} 行`);
      if (error.details?.column) {
        locations.push(`第 ${error.details.column} 列`);
      }
      if (locations.length) {
        const location = document.createElement("p");
        location.className = "diagnostic-location";
        location.textContent = locations.join("，");
        panel.append(location);
      }
      if (error.details?.context) {
        const context = document.createElement("pre");
        context.className = "diagnostic-context";
        context.textContent = error.details.context;
        panel.append(context);
      }
      if (state.revision && error.details?.writable) {
        const repair = document.createElement("button");
        repair.type = "button";
        repair.className = "button button-primary diagnostic-action";
        repair.textContent = "整文件修复";
        repair.addEventListener("click", () => {
          window.confEditEditor?.openRepair?.(error.details, repair);
        });
        panel.append(repair);
      }
      elements.objectList.replaceChildren(panel);
      showToast(error.message, "error");
    }
  }

  async function loadFiles() {
    elements.refreshFiles.disabled = true;
    try {
      const payload = await window.confEditApi.request("/api/files");
      state.files = payload.files;
      renderFiles();
    } catch (error) {
      elements.fileList.textContent = "无法读取文件列表。";
      showToast(error.message, "error");
    } finally {
      elements.refreshFiles.disabled = false;
    }
  }

  elements.objectSearch.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderObjects();
  });
  elements.refreshFiles.addEventListener("click", loadFiles);
  elements.historyButton.addEventListener("click", () => {
    if (!state.activeFile || !state.revision) return;
    window.confEditHistory?.open?.(
      state.activeFile.id,
      state.revision,
      elements.historyButton
    );
  });
  elements.createButton.addEventListener("click", () => {
    window.confEditEditor?.openCreate?.(elements.createButton);
  });

  window.confEditState = state;
  window.confEditApp = {
    loadFiles,
    selectFile,
    renderObjects,
    showToast,
  };
  loadFiles();
})();
