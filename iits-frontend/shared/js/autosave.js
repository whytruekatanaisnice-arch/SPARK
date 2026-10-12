/*
 * Autosave utilities (every field, every role).
 *
 * 1) IITS.autosave({...})  — for EXISTING records (profile, edit forms, notes).
 *    Every 10 seconds, if any watched field changed since the last successful
 *    save, the changes are sent to the server. Failed saves stay "dirty" and
 *    are retried on the next tick. A status line shows what's happening.
 *
 * 2) IITS.draft.start(form, key) — for NEW records ("create" forms) that have no
 *    server record to save into yet. Field values are kept in localStorage every
 *    10 seconds and restored if the page is reloaded/closed by accident.
 *    Call .clear() after a successful submit.
 */
(function () {
  const IITS = window.IITS;
  const INTERVAL_MS = 10000;

  function $(ref, root) {
    return typeof ref === "string" ? (root || document).querySelector(ref) : ref;
  }
  function valueOf(el) {
    if (el.type === "checkbox") return el.checked;
    if (el.type === "number") return el.value === "" ? null : Number(el.value);
    return el.value;
  }
  function keyOf(el) { return el.dataset.key || el.name || el.id; }
  function clock() { return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }

  function makeIndicator(anchorEl) {
    const el = document.createElement("div");
    el.className = "autosave-status";
    el.setAttribute("aria-live", "polite");
    anchorEl.insertAdjacentElement("afterend", el);
    return el;
  }
  function setStatus(el, state, text) {
    if (!el) return;
    el.dataset.state = state;
    el.textContent = text;
  }

  /**
   * opts:
   *   fields:   array of selectors/elements to watch
   *   save:     async (payload) => void   — payload = changed fields keyed by data-key/name/id
   *   sendAll:  true => payload contains ALL watched fields whenever anything changed
   *   anchor:   element/selector after which the status line is inserted
   *   interval: ms (default 10000)
   * returns { flush(), markClean(), stop(), isDirty() }
   */
  IITS.autosave = function (opts) {
    const els = opts.fields.map(f => $(f)).filter(Boolean);
    const indicator = makeIndicator($(opts.anchor) || els[els.length - 1]);
    let saved = {};
    let saving = false;
    let stopped = false;

    function snapshot() { const s = {}; els.forEach(el => s[keyOf(el)] = valueOf(el)); return s; }
    function changedKeys(now) { return Object.keys(now).filter(k => now[k] !== saved[k]); }
    function validEls() { return els.filter(el => !el.checkValidity || el.checkValidity()); }

    function markClean() { saved = snapshot(); setStatus(indicator, "idle", "Changes save automatically"); }

    async function flush() {
      if (stopped || saving) return;
      const now = snapshot();
      let keys = changedKeys(now);
      if (!keys.length) return;

      // Don't send fields that fail validation (e.g. empty required name) — wait until fixed.
      const validKeys = new Set(validEls().map(keyOf));
      keys = keys.filter(k => validKeys.has(k));
      if (!keys.length) { setStatus(indicator, "warn", "Fill in required fields to autosave"); return; }

      const payload = {};
      (opts.sendAll ? Object.keys(now).filter(k => validKeys.has(k)) : keys).forEach(k => payload[k] = now[k]);

      saving = true;
      setStatus(indicator, "saving", "Saving…");
      try {
        await opts.save(payload);
        keys.forEach(k => saved[k] = now[k]);        // only mark what we actually sent as clean
        const stillDirty = changedKeys(snapshot()).length > 0;
        setStatus(indicator, stillDirty ? "dirty" : "saved", stillDirty ? "Unsaved changes…" : "All changes saved · " + clock());
      } catch (e) {
        setStatus(indicator, "error", "Couldn't save (" + (e.message || "error") + ") — retrying in 10s");
      } finally { saving = false; }
    }

    els.forEach(el => {
      const onEdit = () => { if (indicator.dataset.state !== "saving") setStatus(indicator, "dirty", "Unsaved changes… saving within 10s"); };
      el.addEventListener("input", onEdit);
      el.addEventListener("change", onEdit);
    });

    markClean();
    const timer = setInterval(flush, opts.interval || INTERVAL_MS);
    const onHide = () => { if (document.visibilityState === "hidden") flush(); };
    document.addEventListener("visibilitychange", onHide);

    return {
      flush, markClean,
      isDirty: () => changedKeys(snapshot()).length > 0,
      stop() { stopped = true; clearInterval(timer); document.removeEventListener("visibilitychange", onHide); indicator.remove(); },
    };
  };

  /* ---------- Drafts for "create" forms (localStorage) ---------- */
  IITS.draft = {
    start(form, key, opts) {
      form = $(form);
      const user = IITS.getUser();
      const storeKey = `iits_draft:${user ? user.id : "anon"}:${key}`;
      const fields = [...form.querySelectorAll("input, textarea, select")]
        .filter(el => el.type !== "file" && el.type !== "password" && el.type !== "hidden" && (el.id || el.name));
      const id = el => el.id || el.name;

      // Restore a previous draft, if any.
      try {
        const raw = localStorage.getItem(storeKey);
        if (raw) {
          const data = JSON.parse(raw);
          let restored = 0;
          fields.forEach(el => {
            if (!(id(el) in data)) return;
            if (el.type === "checkbox") el.checked = !!data[id(el)]; else el.value = data[id(el)];
            if (data[id(el)] !== "" && data[id(el)] !== false) restored++;
            el.dispatchEvent(new Event("change", { bubbles: true }));
          });
          if (restored && IITS.toast) IITS.toast("Restored your unsaved draft", "success");
        }
      } catch (e) { /* ignore corrupt drafts */ }

      function store() {
        try {
          const data = {};
          fields.forEach(el => data[id(el)] = el.type === "checkbox" ? el.checked : el.value);
          const hasContent = Object.values(data).some(v => v !== "" && v !== false);
          if (hasContent) localStorage.setItem(storeKey, JSON.stringify(data)); else localStorage.removeItem(storeKey);
        } catch (e) { /* storage full/blocked — draft just won't persist */ }
      }

      const timer = setInterval(store, (opts && opts.interval) || INTERVAL_MS);
      let cleared = false;
      return {
        // stop(): final save of whatever is typed (so closing a modal never loses the last <10s)
        stop() { clearInterval(timer); if (!cleared) store(); },
        // clear(): call after a successful submit — drops the draft for good
        clear() { cleared = true; clearInterval(timer); try { localStorage.removeItem(storeKey); } catch (e) {} },
      };
    },
  };
})();
