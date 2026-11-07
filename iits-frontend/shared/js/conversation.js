/* Shared direct-messaging UI for admin, coach, and parent portals. */
(function () {
  let currentConversationId = null;
  let availableContacts = [];
  let currentConversations = [];

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function contactLabel(contact) {
    return `${contact.full_name} (${contact.role[0].toUpperCase() + contact.role.slice(1)})`;
  }

  function timeAgo(iso) {
    if (!iso) return "";
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 60) return "now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  }

  async function loadContacts() {
    const select = document.getElementById("contact-select");
    try {
      availableContacts = await IITS.api("/api/messaging/contacts");
      select.innerHTML = `<option value="">Select a recipient…</option>` +
        availableContacts.map(c => `<option value="${c.id}">${escapeHtml(contactLabel(c))}</option>`).join("");
      select.disabled = availableContacts.length === 0;
      document.getElementById("new-conversation-btn").disabled = availableContacts.length === 0;
    } catch (e) {
      IITS.toast(e.message, "error");
    }
  }

  async function loadConversations(preserveSelection = true) {
    const list = document.getElementById("conv-list");
    try {
      const conversations = await IITS.api("/api/messaging/conversations");
      currentConversations = conversations;
      if (!conversations.length) {
        list.innerHTML = `<div class="empty-state"><div class="title">No conversations</div>Start a message using the recipient selector above.</div>`;
        return;
      }

      list.innerHTML = conversations.map(c => {
        const other = c.participants.find(p => p.id !== IITS.getUser()?.id) || c.participants[0];
        const title = other ? escapeHtml(other.full_name) : escapeHtml(c.subject || "Conversation");
        const preview = c.last_message ? escapeHtml(c.last_message.slice(0, 55)) : "Start a conversation";
        const unread = c.unread_count > 0 ? `<span class="conversation-unread">${c.unread_count > 99 ? "99+" : c.unread_count}</span>` : "";
        return `<div class="msg-list-item${c.id === currentConversationId ? " active" : ""}${c.unread_count > 0 ? " unread" : ""}" data-id="${c.id}"><div class="conversation-item-head"><strong>${title}</strong><span>${timeAgo(c.last_message_at)}</span></div><div class="conversation-preview">${preview}</div>${unread}</div>`;
      }).join("");

      list.querySelectorAll(".msg-list-item").forEach(el => {
        el.addEventListener("click", () => openConversation(el.dataset.id, el));
      });

      if (preserveSelection && currentConversationId) {
        const selected = conversations.find(c => c.id === currentConversationId);
        if (selected) openConversation(currentConversationId, null);
      } else if (!currentConversationId && conversations.length) {
        const first = list.querySelector(".msg-list-item");
        if (first) openConversation(first.dataset.id, first);
      }
    } catch (e) {
      IITS.toast(e.message, "error");
    }
  }

  async function openConversation(id, el) {
    currentConversationId = id;
    document.querySelectorAll(".msg-list-item").forEach(x => x.classList.remove("active"));
    if (el) el.classList.add("active");
    document.getElementById("msg-compose").style.display = "flex";

    try {
      const messages = await IITS.api(`/api/messaging/conversations/${id}/messages`);
      const bubbles = document.getElementById("msg-bubbles");
      const me = IITS.getUser();
      bubbles.innerHTML = messages.length
        ? messages.map(m => `<div class="bubble ${m.sender_id === me.id ? "mine" : ""}">${escapeHtml(m.body)}<span class="bubble-meta">${m.sent_at ? new Date(m.sent_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : ""}</span></div>`).join("")
        : `<div class="empty-state" style="margin:auto;"><div class="title">No messages yet</div>Send the first message below.</div>`;
      bubbles.scrollTop = bubbles.scrollHeight;
    } catch (e) {
      IITS.toast(e.message, "error");
    }
  }

  async function startConversation() {
    const recipientId = document.getElementById("contact-select").value;
    if (!recipientId) return;
    try {
      const conversation = await IITS.api("/api/messaging/conversations", {
        method: "POST",
        body: { participant_ids: [recipientId] }
      });
      currentConversationId = conversation.id;
      await loadConversations(false);
      await openConversation(conversation.id, null);
    } catch (e) {
      IITS.toast(e.message, "error");
    }
  }

  async function sendMessage() {
    const input = document.getElementById("msg-input");
    const body = input.value.trim();
    if (!body || !currentConversationId) return;
    try {
      await IITS.api(`/api/messaging/conversations/${currentConversationId}/messages?body=${encodeURIComponent(body)}`, { method: "POST" });
      input.value = "";
      await openConversation(currentConversationId);
      await loadConversations(true);
    } catch (e) {
      IITS.toast(e.message, "error");
    }
  }

  function setupSearch() {
    const list = document.getElementById("conv-list");
    const search = document.createElement("input");
    search.type = "search";
    search.id = "conversation-search";
    search.placeholder = "Search chats…";
    search.setAttribute("aria-label", "Search chats");
    search.style.cssText = "width:calc(100% - 24px);margin:12px;border:1px solid var(--border);border-radius:8px;padding:9px 10px;box-sizing:border-box;";
    list.parentElement.insertBefore(search, list);

    search.addEventListener("input", () => {
      const query = search.value.trim().toLowerCase();
      list.querySelectorAll(".msg-list-item").forEach(item => {
        item.style.display = !query || item.textContent.toLowerCase().includes(query) ? "block" : "none";
      });
    });

    const contactSelect = document.getElementById("contact-select");
    const contactSearch = document.createElement("input");
    contactSearch.type = "search";
    contactSearch.placeholder = "Search recipients…";
    contactSearch.setAttribute("aria-label", "Search recipients");
    contactSearch.style.cssText = "width:100%;border:1px solid var(--border);border-radius:8px;padding:7px 9px;box-sizing:border-box;margin-bottom:6px;";
    contactSelect.parentElement.parentElement.insertBefore(contactSearch, contactSelect.parentElement);

    contactSearch.addEventListener("input", () => {
      const query = contactSearch.value.trim().toLowerCase();
      const filtered = availableContacts.filter(c => `${c.full_name} ${c.email} ${c.role}`.toLowerCase().includes(query));
      contactSelect.innerHTML = `<option value="">Select a recipient…</option>` + filtered.map(c => `<option value="${c.id}">${escapeHtml(contactLabel(c))}</option>`).join("");
      contactSelect.disabled = filtered.length === 0;
      document.getElementById("new-conversation-btn").disabled = filtered.length === 0;
    });
  }

  window.SPARKConversation = {
    init() {
      setupSearch();
      document.getElementById("new-conversation-btn").addEventListener("click", startConversation);
      document.getElementById("send-btn").addEventListener("click", sendMessage);
      document.getElementById("msg-input").addEventListener("keydown", e => {
        if (e.key === "Enter") sendMessage();
      });
      loadContacts();
      loadConversations(false);
      window.setInterval(() => {
        loadConversations(true);
        if (currentConversationId) openConversation(currentConversationId);
      }, 5000);
    }
  };
})();
