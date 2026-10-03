/*
 * App shell: sidebar nav, topbar, mobile bottom nav, auth guard.
 * Each page's <body data-role="..." data-active="..." data-title="...">
 * should contain only a <div id="page-root"> with that page's real content;
 * this script wraps it in the full shell on load.
 */
(function () {
  const IITS = window.IITS;

  const ICONS = {
    home: '<polyline points="3,10 10,4 17,10"/><rect x="5" y="10" width="10" height="7"/>',
    users: '<circle cx="7" cy="8" r="3"/><circle cx="14.5" cy="9" r="2.3"/><polyline points="3,17 3,15 7,13 11,15 11,17"/><polyline points="12,17 12,15.6 14.5,14.6 17,15.6 17,17"/>',
    flag: '<line x1="5" y1="3" x2="5" y2="17"/><polygon points="5,3 16,3 13,7 16,11 5,11"/>',
    pin: '<circle cx="10" cy="7.5" r="4.5"/><polygon points="7,11 13,11 10,17"/>',
    megaphone: '<rect x="3" y="8" width="4" height="4"/><polygon points="7,6 14,3 14,17 7,14"/>',
    chart: '<rect x="4" y="9" width="3" height="8"/><rect x="9" y="5" width="3" height="12"/><rect x="14" y="11" width="3" height="6"/>',
    trophy: '<rect x="7" y="3" width="6" height="6" rx="1"/><circle cx="5" cy="5" r="2"/><circle cx="15" cy="5" r="2"/><line x1="10" y1="9" x2="10" y2="13"/><line x1="7" y1="13" x2="13" y2="13"/><line x1="8" y1="17" x2="12" y2="17"/>',
    chat: '<circle cx="10" cy="9" r="6"/><polygon points="7,14 7,17.2 10.4,14"/>',
    calendar: '<rect x="3" y="5" width="14" height="12" rx="1.5"/><line x1="3" y1="9" x2="17" y2="9"/><line x1="7" y1="3" x2="7" y2="6.5"/><line x1="13" y1="3" x2="13" y2="6.5"/>',
    clipboard: '<rect x="5" y="4" width="10" height="13" rx="1.5"/><rect x="7.5" y="2" width="5" height="3" rx="1"/><polyline points="7.3,10.2 9.2,12.1 12.8,8"/>',
    star: '<polygon points="10,2 12.4,7.4 18,8 13.6,11.7 15,17.5 10,14.3 5,17.5 6.4,11.7 2,8 7.6,7.4"/>',
    book: '<rect x="2" y="5" width="8" height="11" rx="1"/><rect x="10" y="5" width="8" height="11" rx="1"/><line x1="10" y1="5" x2="10" y2="16"/>',
    user: '<circle cx="10" cy="6.3" r="3.2"/><polyline points="4,17 4,15.2 10,12.6 16,15.2 16,17"/>',
    bell: '<polyline points="6,12 6,7.5 10,4.3 14,7.5 14,12"/><line x1="4" y1="14" x2="16" y2="14"/><rect x="8.4" y="15.2" width="3.2" height="2" rx="1"/>',
    logout: '<rect x="3" y="3" width="8" height="14" rx="1.5"/><line x1="8" y1="10" x2="17" y2="10"/><polyline points="13,6 17,10 13,14"/>',
    menu: '<line x1="3" y1="5" x2="17" y2="5"/><line x1="3" y1="10" x2="17" y2="10"/><line x1="3" y1="15" x2="17" y2="15"/>',
    qr: '<rect x="3" y="3" width="6" height="6"/><rect x="11" y="3" width="6" height="6"/><rect x="3" y="11" width="6" height="6"/><rect x="12" y="12" width="2" height="2"/><rect x="15" y="12" width="2" height="2"/><rect x="12" y="15" width="2" height="2"/><rect x="15" y="15" width="2" height="2"/>',
  };

  function icon(name, cls) {
    const inner = ICONS[name] || ICONS.home;
    return `<svg class="${cls || ''}" width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
  }
  IITS.icon = icon;

  const NAV = {
    admin: [
      { label: "Dashboard", href: "/admin/dashboard.html", key: "dashboard", icon: "home" },
      { label: "Users", href: "/admin/users.html", key: "users", icon: "users" },
      { label: "Clubs", href: "/admin/clubs.html", key: "clubs", icon: "flag" },
      { label: "Venues", href: "/admin/venues.html", key: "venues", icon: "pin" },
      { label: "Announcements", href: "/admin/announcements.html", key: "announcements", icon: "megaphone" },
      { label: "Reports", href: "/admin/reports.html", key: "reports", icon: "chart" },
      { label: "Gamification", href: "/admin/gamification.html", key: "gamification", icon: "trophy" },
      { label: "Messages", href: "/admin/conversation.html", key: "conversation", icon: "chat" },
    ],
    coach: [
      { label: "Dashboard", href: "/coach/dashboard.html", key: "dashboard", icon: "home" },
      { label: "Attendance", href: "/coach/attendance.html", key: "attendance", icon: "qr" },
      { label: "AJK Roles", href: "/coach/roles.html", key: "roles", icon: "users" },
      { label: "Achievements", href: "/coach/achievements.html", key: "achievements", icon: "star" },
      { label: "Tasks", href: "/coach/tasks.html", key: "tasks", icon: "clipboard" },
      { label: "Feedback", href: "/coach/feedback.html", key: "feedback", icon: "chat" },
      { label: "Notifications", href: "/coach/notifications.html", key: "notifications", icon: "bell" },
    ],
    student: [
      { label: "Dashboard", href: "/student/dashboard.html", key: "dashboard", icon: "home" },
      { label: "My Clubs", href: "/student/clubs.html", key: "clubs", icon: "flag" },
      { label: "Tasks", href: "/student/tasks.html", key: "tasks", icon: "clipboard" },
      { label: "PAJSK", href: "/student/pajsk.html", key: "pajsk", icon: "chart" },
      { label: "NILAM", href: "/student/nilam.html", key: "nilam", icon: "book" },
      { label: "Profile", href: "/student/profile.html", key: "profile", icon: "user" },
    ],
    parent: [
      { label: "Dashboard", href: "/parent/dashboard.html", key: "dashboard", icon: "home" },
      { label: "Attendance", href: "/parent/attendance.html", key: "attendance", icon: "calendar" },
      { label: "PAJSK Report", href: "/parent/reports.html", key: "reports", icon: "chart" },
      { label: "Notifications", href: "/parent/notifications.html", key: "notifications", icon: "bell" },
    ],
  };

  const BRAND_SUB = {
    admin: "School Admin", coach: "Coach Portal", student: "Student Portal", parent: "Parent Portal",
  };

  function initials(name) {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase();
  }

  function buildSidebar(role, active, user) {
    const items = NAV[role] || [];
    const navHtml = items.map(i =>
      `<a class="nav-item ${i.key === active ? "active" : ""}" href="${i.href}">${icon(i.icon)}<span>${i.label}</span></a>`
    ).join("");

    return `
      <aside class="sidebar" id="sidebar">
        <div class="sidebar-brand">
          <div class="mark">I</div>
          <div><div class="name">IITS</div><div class="sub">${BRAND_SUB[role] || ""}</div></div>
        </div>
        <nav class="sidebar-nav">${navHtml}</nav>
        <div class="sidebar-footer">
          <div class="sidebar-user">
            <div class="avatar">${initials(user.full_name)}</div>
            <div>
              <div class="u-name">${user.full_name}</div>
              <div class="u-role">${user.role}</div>
            </div>
          </div>
          <button class="logout-btn" id="logout-btn">${icon("logout")}<span>Log out</span></button>
        </div>
      </aside>`;
  }

  function buildBottomNav(role, active) {
    const items = (NAV[role] || []).slice(0, 5);
    return `<nav class="bottom-nav" id="bottom-nav">${items.map(i =>
      `<a class="nav-item ${i.key === active ? "active" : ""}" href="${i.href}">${icon(i.icon)}<span>${i.label.split(" ")[0]}</span></a>`
    ).join("")}</nav>`;
  }

  function buildTopbar(title) {
    return `
      <header class="topbar">
        <div class="flex gap-12">
          <button class="menu-toggle" id="menu-toggle" aria-label="Open menu">${icon("menu")}</button>
          <h1 style="font-size:1.15rem;margin:0;">${title || ""}</h1>
        </div>
        <div id="topbar-right"></div>
      </header>`;
  }

  async function initShell() {
    const body = document.body;
    const role = body.dataset.role;
    const active = body.dataset.active || "";
    const title = body.dataset.title || "";

    if (!IITS.getToken()) { window.location.href = "/login.html"; return; }

    let user = IITS.getUser();
    // Optimistically render with cached user, then confirm with the server.
    if (!user) user = { full_name: "...", role: role || "" };

    // Preserve the ENTIRE original body (page-root content + any modals that are
    // siblings of it, e.g. #user-modal), not just #page-root — modals declared
    // outside #page-root would otherwise be silently dropped when we rebuild
    // the shell below, leaving page scripts calling addEventListener on null.
    const pageContentHtml = document.body.innerHTML.replace(/<script[\s\S]*?<\/script>/gi, "");

    document.body.innerHTML = `
      <div class="app-shell">
        ${buildSidebar(role, active, user)}
        <div class="sidebar-backdrop" id="sidebar-backdrop"></div>
        <div class="main-col">
          ${buildTopbar(title)}
          <main class="page-content" id="page-content">${pageContentHtml}</main>
        </div>
        ${buildBottomNav(role, active)}
      </div>`;

    document.getElementById("logout-btn").addEventListener("click", IITS.logout);
    const toggle = document.getElementById("menu-toggle");
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    toggle.addEventListener("click", () => { sidebar.classList.toggle("open"); backdrop.classList.toggle("open"); });
    backdrop.addEventListener("click", () => { sidebar.classList.remove("open"); backdrop.classList.remove("open"); });

    // Confirm identity + role against the server; re-render sidebar if the cached name/role was stale.
    try {
      const freshUser = await IITS.api("/api/auth/me");
      IITS.setUser(freshUser);
      if (role && freshUser.role !== role) { window.location.href = "/403.html"; return; }
      document.getElementById("sidebar").outerHTML = buildSidebar(role, active, freshUser);
      document.getElementById("logout-btn").addEventListener("click", IITS.logout);
      const newSidebar = document.getElementById("sidebar");
      toggle.addEventListener("click", () => { newSidebar.classList.toggle("open"); backdrop.classList.toggle("open"); });
    } catch (e) { /* IITS.api already redirects on 401/403 */ }

    document.dispatchEvent(new CustomEvent("iits:shell-ready"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initShell);
  } else {
    initShell();
  }
})();
