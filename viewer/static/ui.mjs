// Page preferences shared by the 2D trace viewer and the 3D office: light/dark theme, text size and a
// keyboard-shortcut sheet. Choices live in this browser only (localStorage); nothing leaves the page.

// One small icon set (24-unit grid, 1.75 stroke, round caps) instead of Unicode glyphs. The sprite is
// added to the page once; icons reference it with <use>, so the page and JS draw the same shapes.
const ICONS = {
  play: '<path d="M7 4.5v15l12.5-7.5z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M8.5 5.5v13M15.5 5.5v13"/>',
  prev: '<path d="M14.5 6l-6 6 6 6"/>',
  next: '<path d="M9.5 6l6 6-6 6"/>',
  chevdown: '<path d="M6.5 9.5l5.5 5.5 5.5-5.5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  flag: '<path d="M6 20.5V4.5M6 5h10.5l-2 4 2 4H6"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5" fill="currentColor" stroke="none"/>',
};
const SVG = 'http://www.w3.org/2000/svg';

export function installIcons() {
  if (document.getElementById('icon-sprite')) return;
  const sprite = document.createElementNS(SVG, 'svg');
  sprite.id = 'icon-sprite';
  sprite.setAttribute('aria-hidden', 'true');
  sprite.style.display = 'none';
  const parser = new DOMParser();
  for (const [name, body] of Object.entries(ICONS)) {
    // Parsed as SVG from the fixed table above (never from page data), so no HTML sink is involved.
    const doc = parser.parseFromString(`<symbol xmlns="${SVG}" id="i-${name}" viewBox="0 0 24 24">${body}</symbol>`, 'image/svg+xml');
    sprite.append(document.importNode(doc.documentElement, true));
  }
  document.body.prepend(sprite);
}

/** An inline icon element; decorative unless a label is given. */
export function icon(name, label) {
  const node = document.createElementNS(SVG, 'svg');
  node.setAttribute('class', 'i');
  if (label) { node.setAttribute('role', 'img'); node.setAttribute('aria-label', label); } else node.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG, 'use');
  use.setAttribute('href', `#i-${name}`);
  node.append(use);
  return node;
}

/** Set a button to an icon plus a text label. */
export function iconLabel(button, name, text) {
  button.replaceChildren(icon(name), document.createTextNode(text));
}

const THEMES = [["auto", "Tự động", "Theo cài đặt sáng/tối của máy"], ["light", "Sáng", "Nền sáng"], ["dark", "Tối", "Nền tối"]];
const SIZES = [90, 100, 112, 125, 140];

function remember(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(`viewer.${key}`);
    localStorage.setItem(`viewer.${key}`, value);
  } catch { /* storage blocked: the choice is just not remembered */ }
  return null;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

/** "auto" leaves the attribute off, so the CSS follows prefers-color-scheme. */
export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "light" || theme === "dark") root.dataset.theme = theme;
  else delete root.dataset.theme;
}

export function applyTextSize(percent) {
  document.documentElement.style.fontSize = percent === 100 ? "" : `${17 * percent / 100}px`;
}

/**
 * Add the preference controls to `host` (the page header).
 * @param {HTMLElement} host
 * @param {[string, string][]} shortcuts key -> what it does, shown in the "?" sheet
 */
export function initPrefs(host, shortcuts) {
  installIcons();
  let theme = remember("theme") || "auto";
  let size = Number(remember("textSize")) || 100;
  if (!SIZES.includes(size)) size = 100;
  applyTheme(theme);
  applyTextSize(size);

  const bar = el("div", "prefs");
  bar.setAttribute("role", "group");
  bar.setAttribute("aria-label", "Tùy chọn hiển thị");

  const themes = el("div", "seg");
  themes.setAttribute("role", "radiogroup");
  themes.setAttribute("aria-label", "Giao diện sáng hoặc tối");
  for (const [value, label, hint] of THEMES) {
    const button = el("button", null, label);
    button.type = "button";
    button.title = hint;
    button.setAttribute("role", "radio");
    button.addEventListener("click", () => { theme = value; remember("theme", value); applyTheme(value); sync(); });
    button.dataset.value = value;
    themes.append(button);
  }

  const sizes = el("div", "seg");
  sizes.setAttribute("aria-label", "Cỡ chữ");
  sizes.setAttribute("role", "group");
  const smaller = el("button", null, "A−");
  const reset = el("button", "size-now", "100%");
  const larger = el("button", null, "A+");
  smaller.title = "Chữ nhỏ hơn";
  reset.title = "Về cỡ chữ mặc định";
  larger.title = "Chữ to hơn (khi trình chiếu)";
  const step = (delta) => {
    size = delta === 0 ? 100 : SIZES[Math.max(0, Math.min(SIZES.length - 1, SIZES.indexOf(size) + delta))];
    remember("textSize", String(size));
    applyTextSize(size);
    sync();
  };
  smaller.addEventListener("click", () => step(-1));
  reset.addEventListener("click", () => step(0));
  larger.addEventListener("click", () => step(1));
  for (const button of [smaller, reset, larger]) { button.type = "button"; sizes.append(button); }

  const help = el("button", "help-button", "?");
  help.type = "button";
  help.title = "Phím tắt (phím ?)";
  help.setAttribute("aria-label", "Xem phím tắt");

  const dialog = el("dialog", "shortcuts");
  dialog.setAttribute("aria-label", "Phím tắt");
  dialog.append(el("h2", null, "Phím tắt"));
  const list = el("dl");
  for (const [keys, text] of [...shortcuts, ["?", "Mở / đóng bảng này"], ["Esc", "Đóng bảng này"]]) {
    const dt = el("dt");
    for (const key of keys.split(" ")) dt.append(el("kbd", null, key));
    list.append(dt, el("dd", null, text));
  }
  const close = el("button", null, "Đóng");
  close.type = "button";
  close.addEventListener("click", () => dialog.close());
  dialog.append(list, close);
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  help.addEventListener("click", () => dialog.showModal());
  document.addEventListener("keydown", (event) => {
    if (event.key !== "?" || (event.target instanceof Element && event.target.closest("input, select, textarea"))) return;
    event.preventDefault();
    if (dialog.open) dialog.close(); else dialog.showModal();
  });

  function sync() {
    for (const button of themes.children) button.setAttribute("aria-checked", String(button.dataset.value === theme));
    reset.textContent = `${size}%`;
    smaller.disabled = size === SIZES[0];
    larger.disabled = size === SIZES[SIZES.length - 1];
  }
  sync();
  bar.append(themes, sizes, help);
  host.append(bar);
  document.body.append(dialog);
}
