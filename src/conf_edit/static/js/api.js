(() => {
  const token = document.querySelector(
    'meta[name="conf-edit-token"]'
  ).content;

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body) {
      headers.set("Content-Type", "application/json");
    }
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
