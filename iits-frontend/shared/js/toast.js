/* Minimal toast notifications. Usage: IITS.toast("Saved", "success") */
(function () {
  function ensureContainer() {
    let el = document.querySelector(".toast-container");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast-container";
      document.body.appendChild(el);
    }
    return el;
  }

  window.IITS = window.IITS || {};
  window.IITS.toast = function (message, kind) {
    const container = ensureContainer();
    const el = document.createElement("div");
    el.className = "toast" + (kind ? " " + kind : "");
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 3800);
  };
})();
