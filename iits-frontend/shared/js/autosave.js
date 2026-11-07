/*
 * Autosave utilities (every field, every role).
 *
 * 1) IITS.autosave({...})  — for EXISTING records (profile, edit forms, notes).
 *    Changes are sent to the server shortly after editing and kept locally
 *    until the server confirms them. Failed saves remain available for retry.
 *
 * 2) IITS.draft.start(form, key) — for NEW records ("create" forms) that have no
 *    server record to save into yet. Field values are kept in localStorage while
 *    editing and restored if the page is reloaded/closed by accident.
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
   *   exclude:  array of field ids/names not to persist
   * returns { flush(), markClean(), stop(), isDirty() }
   */
  IITS.autosave = function (opts) {
    const els = opts.fields.map(f => $(f)).filter(Boolean);
    const indicator = makeIndicator($(opts.anchor) || els[els.length - 1]);
    let saved = {};
    let saving = false;
    let stopped = false;
    let debounceTimer = null;
    const user = IITS.getUser();
    const recoveryKey = `iits_autosave:${user ? user.id : "anon"}:${location.pathname}:${els.map(keyOf).join(",")}`;

    function snapshot() { const s = {}; els.forEach(el => s[keyOf(el)] = valueOf(el)); return s; }
    function changedKeys(now) { return Object.keys(now).filter(k => now[k] !== saved[k]); }
    function validEls() { return els.filter(el => !el.checkValidity || el.checkValidity()); }

    function storeRecovery() {
      try {
        const metadata = typeof opts.getRecoveryMetadata === "function" ? opts.getRecoveryMetadata() : {};
        localStorage.setItem(recoveryKey, JSON.stringify({ fields: snapshot(), metadata }));
      } catch (error) {
        setStatus(indicator, "error", `Could not save local recovery data (${error.message})`);
      }
    }
    function clearRecovery() {
      try {
        localStorage.removeItem(recoveryKey);
      } catch (error) {
        setStatus(indicator, "error", `Could not clear local recovery data (${error.message})`);
      }
    }
    function markClean() {
      saved = snapshot();
      clearRecovery();
      setStatus(indicator, "idle", "Changes save automatically");
    }

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
        if (!stillDirty) clearRecovery();
        setStatus(indicator, stillDirty ? "dirty" : "saved", stillDirty ? "Unsaved changes…" : "All changes saved · " + clock());
      } catch (e) {
        storeRecovery();
        setStatus(indicator, "error", "Couldn't save (" + (e.message || "error") + ") — retrying");
      } finally {
        saving = false;
        if (!stopped && changedKeys(snapshot()).length) scheduleFlush();
      }
    }

    function scheduleFlush() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(flush, opts.debounce || 800);
    }

    const initial = snapshot();
    try {
      const raw = localStorage.getItem(recoveryKey);
      if (raw) {
        const recovery = JSON.parse(raw);
        if (recovery && typeof recovery === "object" && !Array.isArray(recovery)) {
          const fields = recovery.fields && typeof recovery.fields === "object" ? recovery.fields : recovery;
          els.forEach(el => {
            const key = keyOf(el);
            if (!(key in fields)) return;
            if (el.type === "checkbox") el.checked = !!fields[key];
            else if (fields[key] == null || ["string", "number"].includes(typeof fields[key])) {
              el.value = String(fields[key] ?? "");
            }
          });
          if (typeof opts.restoreRecoveryMetadata === "function") {
            opts.restoreRecoveryMetadata(recovery.metadata && typeof recovery.metadata === "object" ? recovery.metadata : {});
          }
          if (IITS.toast && JSON.stringify(initial) !== JSON.stringify(snapshot())) {
            IITS.toast("Restored unsaved changes", "success");
          }
        } else {
          clearRecovery();
        }
      }
    } catch (error) {
      clearRecovery();
      IITS.toast(`Could not restore local recovery data: ${error.message}`, "error");
    }

    function onEdit() {
      storeRecovery();
      if (indicator.dataset.state !== "saving") setStatus(indicator, "dirty", "Unsaved changes… saving shortly");
      scheduleFlush();
    }
    els.forEach(el => {
      el.addEventListener("input", onEdit);
      el.addEventListener("change", onEdit);
    });

    saved = initial;
    if (changedKeys(snapshot()).length) scheduleFlush();
    const timer = setInterval(flush, opts.interval || INTERVAL_MS);
    const onHide = () => {
      if (document.visibilityState === "hidden") {
        storeRecovery();
        flush();
      }
    };
    document.addEventListener("visibilitychange", onHide);

    return {
      flush, markClean,
      isDirty: () => changedKeys(snapshot()).length > 0,
      stop() {
        stopped = true;
        clearTimeout(debounceTimer);
        clearInterval(timer);
        document.removeEventListener("visibilitychange", onHide);
        els.forEach(el => {
          el.removeEventListener("input", onEdit);
          el.removeEventListener("change", onEdit);
        });
        indicator.remove();
      },
    };
  };

  /* ---------- Drafts for "create" forms (localStorage) ---------- */
  IITS.draft = {
    start(form, key, opts) {
      form = $(form);
      const user = IITS.getUser();
      const storeKey = `iits_draft:${user ? user.id : "anon"}:${key}`;
      const getFields = () => [...form.querySelectorAll("input, textarea, select")]
        .filter(el => el.type !== "file" && el.type !== "password" && el.type !== "hidden"
          && el.dataset.noDraft !== "true" && (el.dataset.key || el.id || el.name)
          && !excluded.has(id(el)));
      const id = el => el.dataset.key || el.id || el.name;
      const excluded = new Set((opts && opts.exclude) || []);
      let debounceTimer = null;

      // Restore a previous draft, if any.
      try {
        const raw = localStorage.getItem(storeKey);
        if (raw) {
          const data = JSON.parse(raw);
          if (opts && typeof opts.restore === "function") opts.restore(data, form);
          let restored = 0;
          getFields().forEach(el => {
            if (!(id(el) in data)) return;
            if (el.type === "checkbox") el.checked = !!data[id(el)]; else el.value = data[id(el)];
            if (data[id(el)] !== "" && data[id(el)] !== false) restored++;
            el.dispatchEvent(new Event("change", { bubbles: true }));
          });
          if (restored && IITS.toast) IITS.toast("Restored your unsaved draft", "success");
        }
      } catch (error) {
        try { localStorage.removeItem(storeKey); } catch (storageError) {
          IITS.toast(`Could not clear a damaged draft: ${storageError.message}`, "error");
        }
        IITS.toast(`Could not restore your draft: ${error.message}`, "error");
      }

      function store() {
        try {
          const data = {};
          getFields().forEach(el => data[id(el)] = el.type === "checkbox" ? el.checked : el.value);
          const hasContent = Object.values(data).some(v => v !== "" && v !== false);
          if (hasContent) localStorage.setItem(storeKey, JSON.stringify(data)); else localStorage.removeItem(storeKey);
        } catch (error) {
          IITS.toast(`Could not save your draft: ${error.message}`, "error");
        }
      }

      function scheduleStore() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(store, (opts && opts.debounce) || 400);
      }
      form.addEventListener("input", scheduleStore);
      form.addEventListener("change", scheduleStore);
      const timer = setInterval(store, (opts && opts.interval) || INTERVAL_MS);
      const onPageHide = () => store();
      window.addEventListener("pagehide", onPageHide);
      let cleared = false;
      return {
        // stop(): final save of whatever is typed before the form is hidden or reset
        stop() {
          clearTimeout(debounceTimer);
          clearInterval(timer);
          window.removeEventListener("pagehide", onPageHide);
          form.removeEventListener("input", scheduleStore);
          form.removeEventListener("change", scheduleStore);
          if (!cleared) store();
        },
        // clear(): call after a successful submit — drops the draft for good
        clear() {
          cleared = true;
          clearTimeout(debounceTimer);
          clearInterval(timer);
          window.removeEventListener("pagehide", onPageHide);
          form.removeEventListener("input", scheduleStore);
          form.removeEventListener("change", scheduleStore);
          try { localStorage.removeItem(storeKey); } catch (error) {
            IITS.toast(`Could not clear your saved draft: ${error.message}`, "error");
          }
        },
      };
    },
  };
})();
