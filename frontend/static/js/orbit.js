// Orbit front-end: sidebar, Ctrl+K palette, live timer, markdown preview, kanban drag & drop, PWA.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const O = window.ORBIT;

  const post = (url, data) =>
    fetch(url, {
      method: "POST",
      headers: { "X-CSRFToken": O.csrf },
      body: new URLSearchParams(data),
    });

  // --- Toasts: the one place Orbit shows messages and asks for confirmation ---
  const ICONS = {
    success: '<path d="M5 12l5 5L20 7"/>',
    error: '<path d="M12 8v5M12 16.5v.5"/><circle cx="12" cy="12" r="9"/>',
    info: '<path d="M12 11v5M12 7.5v.5"/><circle cx="12" cy="12" r="9"/>',
    danger: '<path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"/>',
  };
  const stack = () => $("#toasts") || document.body.appendChild(Object.assign(document.createElement("div"), { id: "toasts", className: "toast-stack" }));
  const dismiss = (el) => { el.classList.add("leaving"); setTimeout(() => el.remove(), 150); };

  const buildToast = (kind, message, title) => {
    const el = document.createElement("div");
    el.className = `toast toast-${kind}`;
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    const icon = document.createElement("span");
    icon.className = "toast-icon";
    icon.innerHTML = `<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${ICONS[kind === "confirm" ? "info" : kind] || ICONS.info}</svg>`;
    const body = document.createElement("div");
    body.className = "min-w-0 flex-1";
    if (title) {
      const t = document.createElement("p");
      t.className = "font-semibold";
      t.textContent = title;
      body.append(t);
    }
    const m = document.createElement("p");
    m.className = title ? "mt-0.5 text-muted" : "";
    m.textContent = message; // textContent: messages can contain user input
    body.append(m);
    el.append(icon, body);
    return { el, body };
  };

  const toast = (message, kind = "info", { title = "", timeout = 4500 } = {}) => {
    const { el } = buildToast(kind, message, title);
    const close = document.createElement("button");
    close.className = "btn btn-ghost btn-sm btn-icon -mr-1 -mt-1";
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = '<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    close.addEventListener("click", () => dismiss(el));
    el.append(close);
    stack().append(el);
    if (timeout) setTimeout(() => el.isConnected && dismiss(el), timeout);
    return el;
  };

  const confirmToast = (message, { title = "Are you sure?", confirmLabel = "Confirm", danger = false } = {}) =>
    new Promise((resolve) => {
      $$(".toast-confirm, .toast-danger", stack()).forEach(dismiss); // one question at a time
      const { el, body } = buildToast(danger ? "danger" : "confirm", message, title);
      const row = document.createElement("div");
      row.className = "mt-3 flex justify-end gap-2";
      const cancel = Object.assign(document.createElement("button"), { type: "button", className: "btn btn-sm", textContent: "Cancel" });
      const ok = Object.assign(document.createElement("button"), { type: "button", className: `btn btn-sm ${danger ? "btn-danger border-danger/50" : "btn-primary"}`, textContent: confirmLabel });
      row.append(cancel, ok);
      body.append(row);
      const finish = (answer) => { document.removeEventListener("keydown", onKey); dismiss(el); resolve(answer); };
      const onKey = (e) => { if (e.key === "Escape") finish(false); };
      cancel.addEventListener("click", () => finish(false));
      ok.addEventListener("click", () => finish(true));
      document.addEventListener("keydown", onKey);
      stack().append(el);
      ok.focus();
    });

  window.Orbit = { toast, confirm: confirmToast };

  // Server messages (Django) arrive as JSON and become toasts.
  const serverMessages = $("#server-messages");
  if (serverMessages) {
    JSON.parse(serverMessages.textContent).forEach((m) => toast(m.text, m.level === "error" ? "error" : m.level === "success" ? "success" : "info"));
  }

  // --- Small behaviours (no inline handlers: the CSP blocks them) ---
  $$("[data-autosubmit]").forEach((el) => el.addEventListener("change", () => el.form.submit()));
  $$("[data-select-on-click]").forEach((el) => el.addEventListener("click", () => el.select()));
  // Calendar: "+" on a day fills the quick-add form's date.
  $$("[data-fill-date]").forEach((btn) => btn.addEventListener("click", () => {
    const form = $("#calendar-add");
    if (!form) return;
    form.querySelector("[name=due_date]").value = btn.dataset.fillDate;
    form.querySelector("[name=title]").focus();
    form.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }));
  // Type-to-confirm (delete project/account): the button unlocks only on an exact match.
  $$("input[data-match]").forEach((input) => {
    const btn = input.form.querySelector("[data-match-target]");
    const check = () => { btn.disabled = input.value.trim() !== input.dataset.match; };
    input.addEventListener("input", check);
    check();
  });
  // Appearance settings: preview theme/accent instantly before saving.
  $$("[data-preview-theme]").forEach((input) => input.addEventListener("change", () => {
    document.documentElement.dataset[input.dataset.previewTheme] = input.value;
  }));
  $$("input[data-filter]").forEach((input) => {
    const items = $$("[data-filter-text]", $(input.dataset.filter));
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      items.forEach((it) => it.classList.toggle("hidden", !!q && !it.dataset.filterText.includes(q)));
    });
  });
  document.addEventListener("click", (e) => {
    $$("details[data-menu][open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
  });

  // --- Confirm dangerous forms with a toast, never a native browser dialog ---
  $$("form[data-confirm]").forEach((f) =>
    f.addEventListener("submit", async (e) => {
      if (f.dataset.confirmed) return;
      e.preventDefault();
      const ok = await confirmToast(f.dataset.confirm, {
        title: f.dataset.confirmTitle || "Are you sure?",
        confirmLabel: f.dataset.confirmLabel || "Delete",
        danger: f.dataset.confirmTone !== "neutral",
      });
      if (ok) { f.dataset.confirmed = "1"; e.submitter ? f.requestSubmit(e.submitter) : f.requestSubmit(); }
    })
  );

  // --- Running timer ---
  $$("[data-timer-start]").forEach((el) => {
    const start = new Date(el.dataset.timerStart).getTime();
    const tick = () => {
      const s = Math.max(0, Math.floor((Date.now() - start) / 1000));
      el.textContent = `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    };
    tick();
    setInterval(tick, 1000);
  });

  // --- Command palette ---
  const palette = $("#palette"), input = $("#palette-input"), list = $("#palette-results");
  if (palette) {
    const nav = JSON.parse($("#palette-nav").textContent);
    let items = [], active = 0, timer;

    const render = () => {
      list.innerHTML = "";
      if (!items.length) {
        list.innerHTML = '<li class="px-4 py-6 text-center text-sm text-muted">No results</li>';
        return;
      }
      items.forEach((it, i) => {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", i === active);
        li.className = "flex cursor-pointer items-center gap-3 px-4 py-2 text-sm " + (i === active ? "bg-raised" : "");
        const type = document.createElement("span");
        type.className = "w-16 shrink-0 text-xs text-muted";
        type.textContent = it.type;
        const title = document.createElement("span");
        title.className = "flex-1 truncate";
        title.textContent = it.title;
        const sub = document.createElement("span");
        sub.className = "truncate text-xs text-muted";
        sub.textContent = it.subtitle || "";
        li.append(type, title, sub);
        li.addEventListener("click", () => (location.href = it.url));
        li.addEventListener("mousemove", () => { if (active !== i) { active = i; render(); } });
        list.append(li);
      });
    };

    const update = () => {
      const q = input.value.trim().toLowerCase();
      const cmds = nav.filter((c) => c.title.toLowerCase().includes(q));
      items = cmds; active = 0; render();
      clearTimeout(timer);
      if (q.length < 2) return;
      timer = setTimeout(async () => {
        const r = await fetch(`${O.searchUrl}?q=${encodeURIComponent(q)}`);
        if (!r.ok) return;
        const data = await r.json();
        if (input.value.trim().toLowerCase() !== q) return;
        items = [...cmds, ...data.results, { type: "Search", title: `All results for “${input.value.trim()}”`, url: `${O.searchPage}?q=${encodeURIComponent(q)}` }];
        render();
      }, 150);
    };

    const open = () => { palette.classList.remove("hidden"); input.value = ""; update(); input.focus(); };
    const close = () => palette.classList.add("hidden");

    $("#palette-open")?.addEventListener("click", open);
    palette.addEventListener("click", (e) => { if (e.target === palette) close(); });
    input.addEventListener("input", update);
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); palette.classList.contains("hidden") ? open() : close(); }
      if (palette.classList.contains("hidden")) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(active + 1, items.length - 1); render(); }
      if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(active - 1, 0); render(); }
      if (e.key === "Enter" && items[active]) location.href = items[active].url;
    });
  }

  // --- Markdown write/preview tabs ---
  $$("textarea[data-md-preview]").forEach((ta) => {
    const bar = document.createElement("div");
    bar.className = "mb-1 flex gap-1";
    const mk = (label) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label; b.className = "btn btn-sm btn-ghost";
      bar.append(b); return b;
    };
    const writeBtn = mk("Write"), prevBtn = mk("Preview");
    const preview = document.createElement("div");
    preview.className = "md hidden min-h-32 rounded-md border border-line bg-canvas p-3";
    ta.before(bar); ta.after(preview);
    const set = (showPreview) => {
      ta.classList.toggle("hidden", showPreview);
      preview.classList.toggle("hidden", !showPreview);
      writeBtn.classList.toggle("bg-raised", !showPreview);
      prevBtn.classList.toggle("bg-raised", showPreview);
    };
    writeBtn.addEventListener("click", () => set(false));
    prevBtn.addEventListener("click", async () => {
      set(true);
      preview.textContent = "Loading…";
      const r = await post(O.previewUrl, { text: ta.value });
      preview.innerHTML = r.ok ? await r.text() : "Preview failed."; // server returns sanitized HTML
      if (!ta.value.trim()) preview.innerHTML = '<p class="text-muted">Nothing to preview.</p>';
    });
    set(false);
  });

  // --- Kanban drag & drop ---
  const cols = $$(".kanban-col");
  if (cols.length) {
    let dragged = null;
    const refreshCounts = () => cols.forEach((c) => { c.querySelector("[data-col-count]").textContent = c.querySelectorAll(".kanban-card").length; });
    const move = async (card, status, index) => {
      const r = await post(card.dataset.moveUrl, { status, index });
      if (!r.ok) { location.reload(); return; }
      const data = await r.json();
      $$("[data-progress]").forEach((el) => (el.textContent = `${data.progress}%`));
      $$("[data-progress-bar]").forEach((el) => (el.style.width = `${data.progress}%`));
      card.querySelector("[data-title]")?.classList.toggle("line-through", status === "done");
      const sel = card.querySelector("select[data-status-select]");
      if (sel) sel.value = status;
    };

    $$(".kanban-card").forEach((card) => {
      let origin;
      const where = () => {
        const col = card.closest(".kanban-col");
        return { status: col.dataset.status, index: [...col.querySelectorAll(".kanban-card")].indexOf(card) };
      };
      card.addEventListener("dragstart", () => { dragged = card; origin = where(); card.classList.add("dragging"); });
      // Persist on dragend (always fires), not drop: dragover already moved the card in the DOM.
      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        dragged = null;
        cols.forEach((c) => c.classList.remove("drag-over"));
        const now = where();
        if (now.status !== origin.status || now.index !== origin.index) {
          refreshCounts();
          move(card, now.status, now.index);
        }
      });
      // Keyboard / no-drag fallback: status select on each card.
      card.querySelector("select[data-status-select]")?.addEventListener("change", (e) => {
        const col = cols.find((c) => c.dataset.status === e.target.value);
        col.querySelector("[data-cards]").append(card);
        refreshCounts();
        move(card, e.target.value, 9999);
      });
    });

    cols.forEach((col) => {
      const zone = col.querySelector("[data-cards]");
      col.addEventListener("dragover", (e) => {
        e.preventDefault();
        col.classList.add("drag-over");
        const after = [...zone.querySelectorAll(".kanban-card:not(.dragging)")].find(
          (c) => e.clientY < c.getBoundingClientRect().top + c.offsetHeight / 2
        );
        if (dragged) after ? zone.insertBefore(dragged, after) : zone.append(dragged);
      });
      col.addEventListener("dragleave", (e) => { if (!col.contains(e.relatedTarget)) col.classList.remove("drag-over"); });
      col.addEventListener("drop", (e) => e.preventDefault());
    });
  }

  // --- PWA ---
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
})();
