// Orbit select component: a themed dropdown over a native <select>.
// Use it with {% include "partials/select.html" %} in templates; form fields get it from StyledFormMixin.
// The native select stays (visually hidden) as the source of truth, so form posts and change listeners keep working.
// After setting a select's .value from code, call sel.dispatchEvent(new Event("orbit:sync")).
// Selects added later: OrbitSelect.enhance(el) or OrbitSelect.init(container).
(() => {
let openSelect = null;
let selectSeq = 0;
const enhanceSelect = (sel) => {
  if (sel.multiple || sel.dataset.enhanced) return;
  sel.dataset.enhanced = "1";
  const id = `orbit-select-${++selectSeq}`;
  const labelEl = sel.id ? document.querySelector(`label[for="${sel.id}"]`) : null;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `${sel.className} select-btn`;
  btn.setAttribute("aria-haspopup", "listbox");
  btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-controls", id);
  const name = sel.getAttribute("aria-label") || labelEl?.textContent.trim();
  if (name) btn.setAttribute("aria-label", name);
  if (sel.id) { btn.id = `${sel.id}-btn`; labelEl?.setAttribute("for", btn.id); }
  btn.innerHTML = '<span class="select-value"></span><svg class="select-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
  sel.className = "sr-only";
  sel.tabIndex = -1;
  sel.setAttribute("aria-hidden", "true");
  sel.after(btn);

  const list = document.createElement("ul");
  list.className = "select-menu";
  list.id = id;
  list.setAttribute("role", "listbox");
  list.tabIndex = -1;
  document.body.append(list);

  let items = [];
  let active = -1;
  const sync = () => {
    const o = sel.selectedOptions[0];
    btn.querySelector(".select-value").textContent = o ? o.textContent : "";
    btn.classList.toggle("select-placeholder", !o || o.value === "");
    btn.disabled = sel.disabled;
  };
  const setActive = (i) => {
    if (i < 0 || i >= items.length) return;
    items[active]?.li.classList.remove("active");
    active = i;
    items[i].li.classList.add("active");
    list.setAttribute("aria-activedescendant", items[i].li.id);
    items[i].li.scrollIntoView({ block: "nearest" });
  };
  const build = () => {
    list.innerHTML = "";
    items = [];
    active = -1;
    [...sel.children].forEach((node) => {
      const group = node.tagName === "OPTGROUP";
      if (group) {
        const h = document.createElement("li");
        h.className = "select-group";
        h.setAttribute("role", "presentation");
        h.textContent = node.label;
        list.append(h);
      }
      (group ? [...node.children] : [node]).forEach((o) => {
        const li = document.createElement("li");
        const index = items.length;
        li.className = "select-option";
        li.setAttribute("role", "option");
        li.id = `${id}-${index}`;
        li.textContent = o.textContent;
        li.setAttribute("aria-selected", String(o.selected));
        if (o.disabled) li.setAttribute("aria-disabled", "true");
        li.addEventListener("mousedown", (e) => e.preventDefault()); // keep focus in the menu
        li.addEventListener("click", () => !o.disabled && choose(o));
        li.addEventListener("mousemove", () => !o.disabled && active !== index && setActive(index));
        list.append(li);
        items.push({ li, o });
      });
    });
  };
  const step = (from, dir) => {
    for (let i = from + dir; i >= 0 && i < items.length; i += dir) if (!items[i].o.disabled) return i;
    return from;
  };
  const place = () => {
    const r = btn.getBoundingClientRect();
    list.style.minWidth = `${r.width}px`;
    list.style.left = `${Math.max(8, Math.min(r.left, innerWidth - list.offsetWidth - 8))}px`;
    const below = innerHeight - r.bottom;
    const up = below < Math.min(list.scrollHeight, 288) + 12 && r.top > below;
    list.style.top = up ? "" : `${r.bottom + 6}px`;
    list.style.bottom = up ? `${innerHeight - r.top + 6}px` : "";
    list.classList.toggle("up", up);
  };
  const close = (refocus = true) => {
    if (!list.classList.contains("open")) return;
    list.classList.remove("open");
    btn.setAttribute("aria-expanded", "false");
    openSelect = null;
    if (refocus) btn.focus({ preventScroll: true });
  };
  const open = () => {
    if (sel.disabled) return;
    openSelect?.close(false);
    build();
    list.classList.add("open");
    btn.setAttribute("aria-expanded", "true");
    place();
    setActive(Math.max(0, items.findIndex((it) => it.o.selected)));
    list.focus({ preventScroll: true });
    openSelect = { close, list, btn };
  };
  const choose = (o) => {
    const changed = !o.selected;
    sel.value = o.value;
    sync();
    close();
    if (changed) {
      sel.dispatchEvent(new Event("input", { bubbles: true }));
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }
  };
  // Type a letter to jump to an option, like a native select.
  let typed = "";
  let typedAt = 0;
  const match = (ch) => {
    typed = Date.now() - typedAt > 600 ? ch : typed + ch;
    typedAt = Date.now();
    return [...sel.options].findIndex((o) => !o.disabled && o.textContent.trim().toLowerCase().startsWith(typed));
  };

  btn.addEventListener("click", () => (list.classList.contains("open") ? close() : open()));
  btn.addEventListener("keydown", (e) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); open(); }
    else if (e.key.length === 1 && /\S/.test(e.key) && !e.ctrlKey && !e.metaKey) {
      const i = match(e.key.toLowerCase());
      if (i >= 0) choose(sel.options[i]);
    }
  });
  list.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(step(active, 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(step(active, -1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(step(-1, 1)); }
    else if (e.key === "End") { e.preventDefault(); setActive(step(items.length, -1)); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (items[active]) choose(items[active].o); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Tab") close(false);
    else if (e.key.length === 1 && /\S/.test(e.key)) {
      const i = match(e.key.toLowerCase());
      if (i >= 0) setActive(items.findIndex((it) => it.o === sel.options[i]));
    }
  });
  list.addEventListener("focusout", () => setTimeout(() => !list.contains(document.activeElement) && close(false), 0));
  sel.addEventListener("change", sync);
  sel.addEventListener("orbit:sync", sync);
  sel.form?.addEventListener("reset", () => setTimeout(sync, 0));
  sync();
};
document.addEventListener("pointerdown", (e) => {
  if (openSelect && !openSelect.list.contains(e.target) && !openSelect.btn.contains(e.target)) openSelect.close(false);
});
addEventListener("resize", () => openSelect?.close(false));
addEventListener("scroll", (e) => { if (openSelect && !openSelect.list.contains(e.target)) openSelect.close(false); }, true);

const init = (root = document) => root.querySelectorAll("select[data-orbit-select]").forEach(enhanceSelect);
window.OrbitSelect = { enhance: enhanceSelect, init };
init();
})();
