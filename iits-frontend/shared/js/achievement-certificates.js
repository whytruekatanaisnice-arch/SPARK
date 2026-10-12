(function () {
  const escapeHtml = value => String(value == null ? "" : value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const badgeClass = status => ({
    pending: "badge-yellow",
    approved: "badge-green",
    rejected: "badge-red",
  }[status] || "badge-yellow");
  const formatDate = value => value ? new Date(value).toLocaleDateString() : "—";

  function userPath(studentId) {
    return document.body.dataset.role === "parent"
      ? `/api/parent/children/${encodeURIComponent(studentId)}/achievement-certificates`
      : "/api/student/achievement-certificates";
  }

  function updateScorePreview(guide) {
    const level = document.getElementById("competition-level").value;
    const participation = document.getElementById("participation-type").value;
    const placement = document.getElementById("placement").value;
    const engagement = guide.engagement[level] && guide.engagement[level][participation];
    const achievement = placement ? guide.achievement[level] && guide.achievement[level][placement] : 0;
    const preview = document.getElementById("score-preview");
    if (engagement == null || achievement == null) {
      preview.textContent = "Choose a level and participation type to preview points.";
      return;
    }
    preview.textContent = `Participation: ${engagement} pts · Placement: ${achievement} pts · Total: ${engagement + achievement} pts`;
  }

  function applyOcrSuggestions(suggestions, guide) {
    const fields = {
      event_name: "event-name",
      organizer: "organizer",
      awardee_name: "awardee-name",
      event_date: "event-date",
      competition_level: "competition-level",
      participation_type: "participation-type",
      placement: "placement",
    };
    const applied = [];
    Object.entries(fields).forEach(([key, id]) => {
      const value = suggestions && suggestions[key];
      const field = document.getElementById(id);
      if (!value || !field || field.value) return;
      if (field instanceof HTMLSelectElement && ![...field.options].some(option => option.value === value)) return;
      field.value = value;
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.dispatchEvent(new Event("change", { bubbles: true }));
      applied.push(field.labels && field.labels[0] ? field.labels[0].textContent : field.name);
    });
    updateScorePreview(guide);
    return applied;
  }

  function renderSubmissions(submissions) {
    const list = document.getElementById("submission-list");
    list.innerHTML = submissions.length ? submissions.map(item => `
      <article class="card" style="margin-bottom:10px;">
        <div class="flex between" style="gap:10px;">
          <strong>${escapeHtml(item.event_name || "Certificate submission")}</strong>
          <span class="badge ${badgeClass(item.status)}">${escapeHtml(item.status)}</span>
        </div>
        <p class="muted" style="margin-top:8px;">${escapeHtml(item.competition_level || "—")} · ${escapeHtml(formatDate(item.event_date))}</p>
        ${item.score != null ? `<p style="margin-top:6px;">${item.score} PAJSK points (${item.engagement_score} participation + ${item.achievement_score} placement)</p>` : ""}
        ${item.review_note ? `<p class="muted" style="margin-top:6px;">School note: ${escapeHtml(item.review_note)}</p>` : ""}
      </article>`).join("") : `<div class="card empty-state">No submitted competition certificates yet.</div>`;
  }

  async function initSubmissionPage() {
    const parentMode = document.body.dataset.role === "parent";
    const childSelect = document.getElementById("certificate-child");
    const status = document.getElementById("ocr-status");
    const form = document.getElementById("achievement-certificate-form");
    let studentId = null;
    let draftId = null;
    let guide;

    try {
      guide = await IITS.api("/api/achievement-certificate-scoring");
      const level = document.getElementById("competition-level");
      Object.entries(guide.levels).forEach(([value, label]) => {
        level.add(new Option(label, value));
      });
      Object.entries(guide.participation_types).forEach(([value, label]) => {
        document.getElementById("participation-type").add(new Option(`${value} — ${label}`, value));
      });
      document.getElementById("placement").add(new Option("Participation only / no ranking", ""));
      Object.entries(guide.placements).forEach(([value, label]) => {
        document.getElementById("placement").add(new Option(label, value));
      });
    } catch (error) {
      IITS.toast(`Could not load the PAJSK scoring guide: ${error.message}`, "error");
      return;
    }

    async function loadStudentData() {
      if (!studentId) return;
      form.dataset.draftScope = studentId;
      IITS.restoreAutoSaveDraftFields(studentId);
      draftId = null;
      document.getElementById("draft-id").value = "";
      document.getElementById("ocr-text").textContent = "Upload a certificate and run OCR to review its text.";
      status.textContent = "";
      updateScorePreview(guide);
      try {
        const [drafts, submissions] = await Promise.all([
          IITS.api(`${userPath(studentId)}/drafts`),
          IITS.api(userPath(studentId)),
        ]);
        if (drafts.length) {
          const latest = drafts[0];
          draftId = latest.draft_id;
          document.getElementById("draft-id").value = draftId;
          document.getElementById("ocr-text").textContent = latest.ocr_text;
          const autofilled = applyOcrSuggestions(latest.suggested_fields, guide);
          status.textContent = autofilled.length
            ? `Restored OCR draft. Auto-filled: ${autofilled.join(", ")}. Check every value against the certificate.`
            : `Restored OCR draft from ${formatDate(latest.created_at)}. No fields could be confidently auto-filled; enter them from the certificate.`;
        }
        renderSubmissions(submissions);
      } catch (error) {
        IITS.toast(`Could not load certificate records: ${error.message}`, "error");
      }
    }

    if (parentMode) {
      try {
        const children = await IITS.api("/api/parent/children");
        if (!children.length) {
          childSelect.innerHTML = `<option value="">No linked children</option>`;
          document.getElementById("certificate-child-wrap").hidden = false;
          document.getElementById("certificate-form-content").hidden = true;
          document.getElementById("submission-list").innerHTML =
            `<div class="card empty-state">Ask your school admin to link your account to your child's profile.</div>`;
          return;
        }
        childSelect.replaceChildren(...children.map(child => new Option(child.full_name, child.student_id)));
        document.getElementById("certificate-child-wrap").hidden = false;
        await new Promise(resolve => window.requestAnimationFrame(resolve));
        studentId = childSelect.value;
        childSelect.addEventListener("change", () => {
          form.reset();
          studentId = childSelect.value;
          form.dataset.draftScope = studentId;
          loadStudentData();
        });
      } catch (error) {
        IITS.toast(`Could not load linked children: ${error.message}`, "error");
        return;
      }
    } else {
      studentId = IITS.getUser() && IITS.getUser().id;
      if (!studentId) {
        try {
          const user = await IITS.api("/api/auth/me");
          IITS.setUser(user);
          studentId = user.id;
        } catch (error) {
          IITS.toast(error.message, "error");
          return;
        }
      }
    }

    ["competition-level", "participation-type", "placement"].forEach(id => {
      document.getElementById(id).addEventListener("change", () => updateScorePreview(guide));
    });
    const detailsConfirmation = document.getElementById("confirmed-details");
    const privacyConfirmation = document.getElementById("ocr-consent");
    function resetDetailsConfirmation() {
      if (!detailsConfirmation.checked) return;
      detailsConfirmation.checked = false;
      detailsConfirmation.dispatchEvent(new Event("change", { bubbles: true }));
    }
    form.addEventListener("input", event => {
      if (event.target.id !== "confirmed-details" && event.target.id !== "ocr-consent") {
        resetDetailsConfirmation();
      }
    });
    form.addEventListener("change", event => {
      if (event.target.id !== "confirmed-details" && event.target.id !== "ocr-consent") {
        resetDetailsConfirmation();
      }
      if (event.target.id === "certificate-file" && privacyConfirmation.checked) {
        privacyConfirmation.checked = false;
        privacyConfirmation.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    document.getElementById("run-ocr").addEventListener("click", async () => {
      const file = document.getElementById("certificate-file").files[0];
      if (!document.getElementById("ocr-consent").checked) {
        IITS.toast("Confirm that you understand the certificate will be processed by OCR.space.", "error");
        return;
      }
      if (!file) {
        IITS.toast("Choose a certificate before running OCR.", "error");
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        IITS.toast("The certificate must be 10 MB or smaller.", "error");
        return;
      }
      const upload = new FormData();
      upload.append("file", file);
      const button = document.getElementById("run-ocr");
      button.disabled = true;
      status.textContent = "Uploading securely and asking OCR.space to read the certificate…";
      try {
        const result = await IITS.api(`${userPath(studentId)}/ocr`, {
          method: "POST", body: upload, isForm: true, skipAutoSaveClear: true,
        });
        draftId = result.draft_id;
        document.getElementById("draft-id").value = draftId;
        document.getElementById("ocr-text").textContent = result.ocr_text;
        const autofilled = applyOcrSuggestions(result.suggested_fields, guide);
        status.textContent = autofilled.length
          ? `OCR complete. Auto-filled: ${autofilled.join(", ")}. Check every value against the original certificate.`
          : "OCR complete, but no fields could be confidently auto-filled. Enter them from the original certificate.";
      } catch (error) {
        status.textContent = "";
        IITS.toast(`OCR failed: ${error.message}`, "error");
      } finally {
        button.disabled = false;
      }
    });

    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (!draftId) {
        IITS.toast("Run OCR first so the certificate is stored for review.", "error");
        return;
      }
      const submitButton = form.querySelector('button[type="submit"]');
      submitButton.disabled = true;
      const payload = {
        event_name: document.getElementById("event-name").value.trim(),
        organizer: document.getElementById("organizer").value.trim(),
        awardee_name: document.getElementById("awardee-name").value.trim(),
        event_date: document.getElementById("event-date").value,
        competition_level: document.getElementById("competition-level").value,
        participation_type: document.getElementById("participation-type").value,
        placement: document.getElementById("placement").value || null,
        confirmed_details: document.getElementById("confirmed-details").checked,
      };
      try {
        const query = new URLSearchParams({ event_name: payload.event_name, event_date: payload.event_date });
        const duplicate = await IITS.api(`${userPath(studentId)}/${encodeURIComponent(draftId)}/duplicate-check?${query}`);
        if (duplicate.duplicate) {
          IITS.toast("A submission for this event and date already exists for this student.", "error");
          return;
        }
        await IITS.api(`${userPath(studentId)}/${encodeURIComponent(draftId)}/submit`, {
          method: "POST", body: payload,
        });
        draftId = null;
        form.reset();
        IITS.toast("Certificate submitted. Points will count after staff approval.", "success");
        await loadStudentData();
      } catch (error) {
        IITS.toast(`Could not submit certificate: ${error.message}`, "error");
      } finally {
        submitButton.disabled = false;
      }
    });

    updateScorePreview(guide);
    await loadStudentData();
  }

  async function initReviewPage() {
    const list = document.getElementById("review-list");
    const filter = document.getElementById("review-status");
    async function loadReviews() {
      list.innerHTML = `<div class="loading-row"><span class="spinner"></span> Loading submissions…</div>`;
      try {
        const query = filter.value ? `?status=${encodeURIComponent(filter.value)}` : "";
        const reviews = await IITS.api(`/api/coach/certificate-submissions${query}`);
        list.innerHTML = reviews.length ? reviews.map(item => `
          <article class="card" data-review-id="${escapeHtml(item.id)}" style="margin-bottom:14px;">
            <div class="flex between" style="gap:10px;flex-wrap:wrap;">
              <div><h2>${escapeHtml(item.event_name || "Certificate")}</h2><p class="muted">${escapeHtml(item.student_name)} · ${escapeHtml(item.student_email)}</p></div>
              <span class="badge ${badgeClass(item.status)}">${escapeHtml(item.status)}</span>
            </div>
            <div class="grid grid-2" style="margin-top:12px;">
              <div><strong>Student on certificate:</strong> ${escapeHtml(item.awardee_name || "—")}</div>
              <div><strong>Organizer:</strong> ${escapeHtml(item.organizer || "—")}</div>
              <div><strong>Event date:</strong> ${escapeHtml(formatDate(item.event_date))}</div>
              <div><strong>Level / participation:</strong> ${escapeHtml(item.competition_level || "—")} / ${escapeHtml(item.participation_type || "—")}</div>
              <div><strong>Placement:</strong> ${escapeHtml(item.placement || "Participation only")}</div>
              <div><strong>PAJSK score:</strong> ${item.score == null ? "—" : `${item.score} (${item.engagement_score} + ${item.achievement_score})`}</div>
            </div>
            ${item.review_note ? `<p class="muted" style="margin-top:10px;">Review note: ${escapeHtml(item.review_note)}</p>` : ""}
            <details style="margin-top:12px;">
              <summary>OCR-extracted text</summary>
              <pre style="white-space:pre-wrap;max-height:220px;overflow:auto;">${escapeHtml(item.ocr_text)}</pre>
            </details>
            <div class="flex gap-12" style="margin-top:14px;flex-wrap:wrap;">
              <button class="btn btn-secondary btn-sm" type="button" data-action="file" data-id="${escapeHtml(item.id)}">Get private certificate link</button>
              <a hidden class="btn btn-secondary btn-sm" data-file-link target="_blank" rel="noopener noreferrer">Open certificate (temporary link)</a>
            </div>
            ${item.status === "pending" ? `
              <div class="field" style="margin-top:14px;"><label for="note-${escapeHtml(item.id)}">Review note (optional)</label><textarea id="note-${escapeHtml(item.id)}" maxlength="2000" rows="2"></textarea></div>
              <div class="flex gap-12">
                <button class="btn btn-primary btn-sm" type="button" data-action="approve" data-id="${escapeHtml(item.id)}">Approve and count points</button>
                <button class="btn btn-secondary btn-sm" type="button" data-action="reject" data-id="${escapeHtml(item.id)}">Reject submission</button>
              </div>` : ""}
          </article>`).join("") : `<div class="card empty-state">No submissions match this filter.</div>`;
      } catch (error) {
        list.innerHTML = `<div class="card empty-state">Could not load submissions.</div>`;
        IITS.toast(`Could not load reviews: ${error.message}`, "error");
      }
    }

    filter.addEventListener("change", loadReviews);
    list.addEventListener("click", async event => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const action = button.dataset.action;
      try {
        if (action === "file") {
          const result = await IITS.api(`/api/coach/certificate-submissions/${encodeURIComponent(button.dataset.id)}/file`);
          const card = button.closest("[data-review-id]");
          const link = card.querySelector("[data-file-link]");
          link.href = result.url;
          link.hidden = false;
          return;
        }
        const status = action === "approve" ? "approved" : "rejected";
        const note = document.getElementById(`note-${button.dataset.id}`);
        await IITS.api(`/api/coach/certificate-submissions/${encodeURIComponent(button.dataset.id)}`, {
          method: "PATCH",
          body: { status, review_note: note ? note.value.trim() || null : null },
        });
        IITS.toast(`Certificate ${status}.`, "success");
        await loadReviews();
      } catch (error) {
        IITS.toast(`Could not update submission: ${error.message}`, "error");
      }
    });
    await loadReviews();
  }

  document.addEventListener("iits:shell-ready", () => {
    if (document.body.dataset.certificateWorkflow === "review") initReviewPage();
    else initSubmissionPage();
  });
})();
