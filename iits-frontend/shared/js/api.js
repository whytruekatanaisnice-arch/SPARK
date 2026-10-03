/* Fetch wrapper: attaches JWT, handles 401/403, parses JSON, surfaces errors. */
window.IITS = window.IITS || {};

(function () {
  const TOKEN_KEY = "iits_token";
  const USER_KEY = "iits_user";

  const IITS = window.IITS;

  IITS.getToken = () => localStorage.getItem(TOKEN_KEY);
  IITS.setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
  IITS.clearToken = () => localStorage.removeItem(TOKEN_KEY);

  IITS.getUser = () => {
    try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch (e) { return null; }
  };
  IITS.setUser = (u) => localStorage.setItem(USER_KEY, JSON.stringify(u));
  IITS.clearUser = () => localStorage.removeItem(USER_KEY);

  IITS.logout = () => {
    IITS.clearToken();
    IITS.clearUser();
    window.location.href = "/login.html";
  };

  /**
   * IITS.api(path, { method, body, isForm })
   * - body: plain object (auto JSON-encoded) or FormData (for uploads)
   * - Automatically redirects to /login.html on 401 and /403.html on 403
   * - Returns parsed JSON, or the raw Response for non-JSON (e.g. CSV download)
   */
  IITS.api = async function (path, options = {}) {
    const { method = "GET", body, isForm = false, rawResponse = false } = options;
    const headers = {};
    const token = IITS.getToken();
    if (token) headers["Authorization"] = "Bearer " + token;

    let fetchBody;
    if (isForm) {
      fetchBody = body; // FormData sets its own content-type boundary
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      fetchBody = JSON.stringify(body);
    }

    let res;
    try {
      res = await fetch(window.IITS_API_BASE + path, { method, headers, body: fetchBody });
    } catch (networkErr) {
      IITS.toast("Could not reach the server. Check your connection.", "error");
      throw networkErr;
    }

    if (res.status === 401) {
      IITS.clearToken();
      IITS.clearUser();
      if (!location.pathname.endsWith("login.html")) window.location.href = "/login.html";
      throw new Error("Not authenticated");
    }
    if (res.status === 403) {
      window.location.href = "/403.html";
      throw new Error("Forbidden");
    }

    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      try {
        const errBody = await res.json();
        if (errBody && errBody.detail) detail = typeof errBody.detail === "string" ? errBody.detail : JSON.stringify(errBody.detail);
      } catch (e) { /* ignore parse failure */ }
      throw new Error(detail);
    }

    if (rawResponse) return res;

    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) return res.json();
    return res;
  };

  /** Convenience: trigger a browser download from an API endpoint that streams a file. */
  IITS.downloadFile = async function (path, filename) {
    const res = await IITS.api(path, { rawResponse: true });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };
})();
