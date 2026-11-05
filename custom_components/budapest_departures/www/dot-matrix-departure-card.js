/*!
 * Dotmatrix Indulási Kijelző kártya Home Assistanthoz
 * https://github.com/szbence7/dot-matrix-departure-card
 * MIT License (c) Szorgalmatos Bence
 */
const CARD_VERSION = "0.4.1";

// 5x7 dot-matrix font: 35 bits per glyph, row by row
const GLYPHS = {"0": "01110100011000110001100011000101110", "1": "00100011000010000100001000010001110", "2": "01110100010001000100010001000011111", "3": "01110100010000100110000011000101110", "4": "00010001100101010010111110001000010", "5": "11111100001111000001000011000101110", "6": "00110010001000011110100011000101110", "7": "11111000010001000100010000100001000", "8": "01110100011000101110100011000101110", "9": "01110100011000101111000010001001100", "A": "01110100011000111111100011000110001", "B": "11110100011000111110100011000111110", "C": "01110100011000010000100001000101110", "D": "11110100011000110001100011000111110", "E": "11111100001000011110100001000011111", "F": "11111100001000011110100001000010000", "G": "01110100011000010111100011000101110", "H": "10001100011000111111100011000110001", "I": "01110001000010000100001000010001110", "J": "00111000100001000010000101001001100", "K": "10001100101010011000101001001010001", "L": "10000100001000010000100001000011111", "M": "10001110111010110001100011000110001", "N": "10001110011010110011100011000110001", "O": "01110100011000110001100011000101110", "P": "11110100011000111110100001000010000", "Q": "01110100011000110001101011001001101", "R": "11110100011000111110101001001010001", "S": "01111100001000001110000010000111110", "T": "11111001000010000100001000010000100", "U": "10001100011000110001100011000101110", "V": "10001100011000110001010100101000100", "W": "10001100011000110101101011101110001", "X": "10001010100010000100001000101010001", "Y": "10001010100010000100001000010000100", "Z": "11111000010001000100010001000011111", " ": "00000000000000000000000000000000000", ":": "00000001000010000000001000010000000", "'": "00100001000000000000000000000000000", "Á": "00100011101000110001111111000110001", "É": "00100111111000011110100001000011111", "Í": "00100011100010000100001000010001110", "Ó": "00100011101000110001100011000101110", "Ö": "01010011101000110001100011000101110", "Ő": "10001011101000110001100011000101110", "Ú": "00100100011000110001100011000101110", "Ü": "01010100011000110001100011000101110", "Ű": "01001100100000010001100011000101110", ",": "00000000000000000000001100001000100", ".": "00000000000000000000000000011000110", "-": "00000000000000011111000000000000000", "/": "00001000100001000100010000100010000", "!": "00100001000010000100001000000000100", "?": "01110100010000100010001000000000100", "(": "00010001000100001000010000010000010", ")": "01000001000001000010000100010001000", "+": "00000001000010011111001000010000000"};
const BLANK = "0".repeat(35);

const COLORS = [
  { value: "#ff8800", label: "Borostyán (FUTÁR)" },
  { value: "#ffd200", label: "Sárga" },
  { value: "#3dff6e", label: "Zöld" },
  { value: "#f4f4f4", label: "Fehér" },
  { value: "#ff3b30", label: "Piros" },
];

const DEFAULTS = {
  rows: 6,
  color: "#ff8800",
  columns: "auto",
  scroll_speed: 23,
  show_title: true,
  show_alerts: true,
  route_colors: false,
  background: true,
  empty_text: "NINCS JÁRAT",
};

const MARQUEE_GAP = "   ";
// Responsive sizing: dot pitch in CSS px
const MIN_PITCH = 2;
const MAX_PITCH = 4.5;
const IDEAL_COLUMNS = 140;
const MIN_COLUMNS = 75; // route (30) + time (24) + a few letters of the destination

/** Text -> 7 rows of 0/1 columns, 1 blank column between glyphs. */
function textToMatrix(text) {
  const chars = [...String(text).toLocaleUpperCase("hu-HU")];
  const rows = [[], [], [], [], [], [], []];
  chars.forEach((ch, i) => {
    const g = GLYPHS[ch] || BLANK;
    for (let r = 0; r < 7; r++) {
      for (let c = 0; c < 5; c++) rows[r].push(g.charCodeAt(r * 5 + c) === 49 ? 1 : 0);
      if (i < chars.length - 1) rows[r].push(0);
    }
  });
  return rows;
}

const widthOf = (m) => (m[0] ? m[0].length : 0);
const pad = (m, before, after) => m.map((r) => [...Array(before).fill(0), ...r, ...Array(after).fill(0)]);

class DotMatrixDepartureCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._offsets = [];
    this._lastStep = 0;
    this._raf = null;
    this._width = 0;
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && Array.isArray(hass.states[id].attributes.departures)
    );
    return { entity: entity || "" };
  }

  static formDefinition() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "sensor", filter: { integration: "budapest_departures" } } } },
        { name: "title", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "rows", selector: { number: { min: 1, max: 12, mode: "box" } } },
            { name: "color", selector: { select: { options: COLORS, custom_value: true, mode: "dropdown" } } },
            { name: "columns", selector: { number: { min: 80, max: 300, step: 10, mode: "box" } } },
            { name: "scroll_speed", selector: { number: { min: 5, max: 60, mode: "box" } } },
          ],
        },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "show_title", selector: { boolean: {} } },
            { name: "show_alerts", selector: { boolean: {} } },
            { name: "route_colors", selector: { boolean: {} } },
            { name: "background", selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (s) =>
        ({
          entity: "Indulás szenzor",
          title: "Cím (alapból a megálló neve)",
          rows: "Sorok száma",
          color: "LED szín",
          columns: "Pötty / sor (üresen: automatikus)",
          scroll_speed: "Görgetés sebessége (pötty/mp)",
          show_title: "Cím mutatása",
          show_alerts: "Forgalmi zavarok mutatása",
          route_colors: "Járatszám a járat színében",
          background: "Fekete kijelző háttér",
        })[s.name],
    };
  }

  static getConfigElement() {
    return document.createElement("dot-matrix-departure-card-editor");
  }

  setConfig(config) {
    if (!config) throw new Error("Hiányzó konfiguráció");
    this._config = { ...DEFAULTS, ...config };
    this._build();
  }

  set hass(hass) {
    this._hass = hass;
    const state = this._config.entity ? hass.states[this._config.entity] : undefined;
    if (state !== this._state) {
      this._state = state;
      this._updateData();
    }
  }

  getCardSize() {
    return (this._config?.rows || 6) + 1;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 4, rows: "auto" };
  }

  connectedCallback() {
    this._resizeObserver = new ResizeObserver(() => this._resize());
    if (this._board) this._resizeObserver.observe(this._board);
    this._start();
  }

  disconnectedCallback() {
    this._resizeObserver?.disconnect();
    cancelAnimationFrame(this._raf);
    this._raf = null;
  }

  _build() {
    const c = this._config;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; }
        ha-card { display: block; overflow: hidden; height: 100%; box-sizing: border-box; }
        .wrap { padding: 14px; height: 100%; box-sizing: border-box; display: flex; flex-direction: column; }
        .title { color: var(--primary-text-color); font-size: 1.2em; font-weight: 500; margin: 0 0 10px 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: none; display: ${c.show_title ? "block" : "none"}; }
        .board { flex: ${typeof c.grid_options?.rows === "number" ? "1 1 auto" : "none"}; min-height: 0; display: flex; align-items: center; ${c.background ? "background: #000; border: 1px solid #333; box-shadow: inset 0 0 12px rgba(0,0,0,.8);" : ""} border-radius: 6px; padding: 10px; }
        canvas { display: block; width: 100%; }
      </style>
      <ha-card>
        <div class="wrap">
          <div class="title"></div>
          <div class="board"><canvas></canvas></div>
        </div>
      </ha-card>`;
    this._titleEl = this.shadowRoot.querySelector(".title");
    this._board = this.shadowRoot.querySelector(".board");
    this._canvas = this.shadowRoot.querySelector("canvas");
    this._ctx = this._canvas.getContext("2d");
    this._offsets = [];
    if (this.isConnected && this._resizeObserver) this._resizeObserver.observe(this._board);
    if (this._hass) {
      this._state = c.entity ? this._hass.states[c.entity] : undefined;
      this._updateData();
    }
  }

  _updateData() {
    const s = this._state;
    const a = s?.attributes || {};
    this._departures = Array.isArray(a.departures) ? a.departures : [];
    this._alert = this._config.show_alerts ? a.alert || "" : "";
    this._unavailable = !s || s.state === "unavailable";
    const stop = a.stop_name ? `${a.stop_name}${a.direction ? ` → ${a.direction}` : ""}` : "";
    if (this._titleEl) this._titleEl.textContent = this._config.title || stop || a.friendly_name || "";
    this._resize();
  }

  /** Height of the board in dot units for a given number of rows. */
  _heightDots(rows) {
    return (rows + (this._alert ? 1 : 0)) * 10 - 3 + (this._alert ? 2 : 0);
  }

  _resize() {
    if (!this._board) return;
    const width = this._board.clientWidth - 20;
    if (width <= 0) return;
    const c = this._config;
    const dpr = window.devicePixelRatio || 1;
    const snap = (v) => Math.max(1 / dpr, Math.round(v * dpr) / dpr);

    // 1) pitch from the width
    let pitch;
    if (Number(c.columns) > 0) {
      pitch = width / Number(c.columns);
    } else {
      pitch = Math.min(MAX_PITCH, Math.max(MIN_PITCH, width / IDEAL_COLUMNS));
      if (width / pitch < MIN_COLUMNS) pitch = width / MIN_COLUMNS; // very narrow card: smaller dots
    }

    // 2) fixed card height (sections view, height set by the user): fit as many rows as possible
    let rows = c.rows;
    const fixedHeight = typeof c.grid_options?.rows === "number";
    pitch = snap(pitch);
    if (fixedHeight) {
      const card = this.shadowRoot.querySelector("ha-card");
      const titleH = c.show_title ? this._titleEl.getBoundingClientRect().height + 10 : 0;
      const avail = card.clientHeight - 28 - titleH - 22; // wrap padding, title, board padding + border
      if (avail > 0) {
        const extra = this._alert ? 12 : 0;
        const fit = (pt) => Math.floor((avail / pt + 3 - extra) / 10);
        const wanted = Math.max(c.rows, this._departures.length || 1);
        rows = Math.max(1, Math.min(wanted, fit(pitch)));
        // still too tall at this size: shrink the dots so one row fits
        if (fit(pitch) < 1) pitch = Math.max(1 / dpr, Math.floor((avail / this._heightDots(1)) * dpr) / dpr);
      }
    }

    this._pitch = pitch;
    this._rowsShown = rows;
    this._cols = Math.floor(width / pitch + 1e-6);
    if (this._cols < 1) this._cols = 1;
    this._offsetX = Math.floor(((width - this._cols * pitch) / 2) * dpr) / dpr;
    const height = this._heightDots(rows) * pitch;
    this._canvas.width = Math.round(width * dpr);
    this._canvas.height = Math.round(height * dpr);
    this._canvas.style.height = `${height}px`;
    this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._width = width;
    this._draw(performance.now());
  }

  _start() {
    if (this._raf) return;
    const loop = (t) => {
      this._raf = requestAnimationFrame(loop);
      const stepMs = 1000 / this._config.scroll_speed;
      const blinkPhase = Math.floor(t / 500) % 2;
      const minuteTick = Math.floor(Date.now() / 5000);
      if (t - this._lastStep >= stepMs) {
        this._lastStep = t;
        this._offsets = this._offsets.map((o) => o + 1);
        this._draw(t);
      } else if (blinkPhase !== this._blinkPhase || minuteTick !== this._minuteTick) {
        this._draw(t);
      }
      this._blinkPhase = blinkPhase;
      this._minuteTick = minuteTick;
    };
    this._raf = requestAnimationFrame(loop);
  }

  /** Visible window of `cols` columns from a (possibly scrolling) text. */
  _window(text, cols, index) {
    const m = pad(textToMatrix(text), 0, 1);
    if (widthOf(m) <= cols) {
      this._offsets[index] = 0;
      return pad(m, 0, cols - widthOf(m));
    }
    const unit = m.map((r, i) => [...r, ...pad(textToMatrix(MARQUEE_GAP), 0, 1)[i]]);
    const len = widthOf(unit);
    const off = (this._offsets[index] || 0) % len;
    this._offsets[index] = off;
    return unit.map((r) => {
      const out = new Array(cols);
      for (let i = 0; i < cols; i++) out[i] = r[(off + i) % len];
      return out;
    });
  }

  _lines(now) {
    const c = this._config;
    if (!c.entity) return [{ cells: [{ text: "VÁLASSZ MEGÁLLÓT", flex: true }] }];
    if (this._unavailable) return [{ cells: [{ text: "NINCS ADAT", flex: true }] }];
    const deps = this._departures
      .map((d) => ({ ...d, min: Math.max(0, Math.round(((d.departure || 0) * 1000 - now) / 60000)) }))
      .filter((d) => d.departure * 1000 - now > -60000)
      .slice(0, this._rowsShown);
    if (!deps.length) return [{ cells: [{ text: c.empty_text, flex: true }] }];
    // column widths sized to the longest value on the board, so narrow cards keep room for the destination
    const routeW = Math.max(2, ...deps.map((d) => String(d.route).length));
    const timeW = Math.max(2, ...deps.map((d) => `${d.min}'`.length));
    const gap = this._cols < 110 ? 4 : 6;
    return deps.map((d) => ({
      blink: d.min <= 0,
      routeColor: c.route_colors && !d.night ? d.color : null,
      cells: [
        { text: String(d.route).padEnd(routeW, " "), fixed: true, before: 0, after: gap },
        { text: d.headsign || "", flex: true },
        { text: `${d.min}'`.padStart(timeW, " "), fixed: true, before: gap, after: 0 },
      ],
    }));
  }

  _draw(t) {
    const ctx = this._ctx;
    if (!ctx || !this._width) return;
    const c = this._config;
    const p = this._pitch;
    const ox = this._offsetX || 0;
    const dpr = window.devicePixelRatio || 1;
    const dot = Math.max(1 / dpr, Math.round(p * 0.78 * dpr) / dpr);
    const r = Math.min(dot / 2, p * 0.2);
    const now = Date.now();
    const blinkOff = Math.floor(t / 500) % 2 === 1;

    ctx.clearRect(0, 0, this._width, this._canvas.height);

    const lit = new Map(); // color -> Path2D
    const unlit = new Path2D();
    const addDot = (path, x, y) => {
      const px = ox + x * p;
      if (path.roundRect) path.roundRect(px, y * p, dot, dot, r);
      else path.rect(px, y * p, dot, dot);
    };
    const paint = (matrix, x0, y0, color, hidden) => {
      let path = lit.get(color);
      if (!path) lit.set(color, (path = new Path2D()));
      for (let y = 0; y < 7; y++) {
        const row = matrix[y];
        for (let x = 0; x < row.length; x++) addDot(row[x] && !hidden ? path : unlit, x0 + x, y0 + y);
      }
    };

    const lines = this._lines(now);
    let index = 0;
    lines.forEach((line, li) => {
      const y0 = li * 10;
      const hidden = line.blink && blinkOff;
      const fixed = line.cells.filter((cell) => cell.fixed).map((cell) => pad(textToMatrix(cell.text), cell.before || 0, cell.after || 0));
      const fixedWidth = fixed.reduce((s, m) => s + widthOf(m), 0);
      let x = 0;
      let fi = 0;
      line.cells.forEach((cell, ci) => {
        const color = ci === 0 && line.routeColor ? line.routeColor : c.color;
        if (cell.fixed) {
          const m = fixed[fi++];
          paint(m, x, y0, color, hidden);
          x += widthOf(m);
        } else {
          const cols = Math.max(0, this._cols - fixedWidth);
          paint(this._window(cell.text, cols, index), x, y0, color, hidden);
          x += cols;
        }
      });
      index++;
    });

    // empty rows keep the board size
    for (let li = lines.length; li < c.rows; li++) paint(textToMatrix(""), 0, li * 10, c.color, false);
    for (let li = lines.length; li < this._rowsShown; li++) {
      for (let y = 0; y < 7; y++) for (let x = 0; x < this._cols; x++) addDot(unlit, x, li * 10 + y);
    }

    if (this._alert) {
      const y0 = this._rowsShown * 10 + 2;
      ctx.fillStyle = "#222";
      ctx.fillRect(ox, (y0 - 2) * p, this._cols * p, Math.max(1, p * 0.3));
      paint(this._window(this._alert, this._cols, 99), 0, y0, c.color, false);
    }

    ctx.fillStyle = c.background ? "#111" : "rgba(127,127,127,0.12)";
    ctx.fill(unlit);
    lit.forEach((path, color) => {
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = p * 0.9;
      ctx.fillStyle = color;
      ctx.fill(path);
      ctx.restore();
    });
  }
}

if (!customElements.get("dot-matrix-departure-card")) {
  customElements.define("dot-matrix-departure-card", DotMatrixDepartureCard);
}

/* ---------- Visual editor with live stop search ---------- */

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class DotMatrixDepartureCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._seq = 0;
  }

  setConfig(config) {
    this._config = {
      show_title: DEFAULTS.show_title,
      show_alerts: DEFAULTS.show_alerts,
      route_colors: DEFAULTS.route_colors,
      background: DEFAULTS.background,
      ...config,
    };
    if (this._form) this._form.data = this._config;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    if (this._form) this._form.hass = hass;
  }

  async _build() {
    this._built = true;
    // make sure ha-form and the entity picker are loaded
    if (!customElements.get("ha-form") && window.loadCardHelpers) {
      try {
        const helpers = await window.loadCardHelpers();
        const card = await helpers.createCardElement({ type: "entities", entities: [] });
        await card.constructor.getConfigElement();
      } catch (e) { /* ignore */ }
    }
    this.shadowRoot.innerHTML = `
      <style>
        .search { margin-bottom: 20px; }
        .label { font-weight: 500; margin: 0 0 6px; color: var(--primary-text-color); }
        .hint { font-size: 12px; color: var(--secondary-text-color); margin: 4px 0 0; }
        input { box-sizing: border-box; width: 100%; height: 48px; padding: 0 14px; font-size: 16px; border-radius: 10px;
          border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color, #fff); color: var(--primary-text-color); outline: none; }
        input:focus { border-color: var(--primary-color); box-shadow: 0 0 0 1px var(--primary-color); }
        .status { font-size: 13px; color: var(--secondary-text-color); margin: 8px 2px 0; min-height: 18px; }
        .status.err { color: var(--error-color, #db4437); }
        .results { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; max-height: 420px; overflow: auto; }
        .item { all: unset; box-sizing: border-box; cursor: pointer; display: block; width: 100%; padding: 10px 12px; border-radius: 10px;
          border: 1px solid var(--divider-color, #ddd); background: var(--card-background-color, #fff); }
        .item:hover, .item:focus-visible { border-color: var(--primary-color); background: var(--secondary-background-color, #f5f5f5); }
        .item.selected { border-color: var(--primary-color); box-shadow: 0 0 0 1px var(--primary-color); }
        .place { font-size: 12px; font-weight: 600; letter-spacing: .3px; text-transform: uppercase; color: var(--secondary-text-color); }
        .line { display: flex; align-items: baseline; gap: 8px; margin: 2px 0 6px; color: var(--primary-text-color); }
        .name { font-size: 15px; font-weight: 600; }
        .dir { font-size: 14px; color: var(--secondary-text-color); }
        .added { margin-left: auto; font-size: 12px; color: var(--success-color, #43a047); font-weight: 600; white-space: nowrap; }
        .badges { display: flex; flex-wrap: wrap; gap: 4px; }
        .badge { font: 700 12px/1 Roboto, Arial, sans-serif; padding: 4px 6px; border-radius: 4px; min-width: 14px; text-align: center; }
        .badge.dark { box-shadow: inset 0 0 0 1px rgba(255,255,255,.35); }
      </style>
      <div class="search">
        <div class="label">Megálló keresése</div>
        <input type="search" autocomplete="off" placeholder="Kezdd el gépelni, pl. Deák Ferenc tér vagy Templom tér">
        <div class="hint">Kattints egy találatra: ha még nincs felvéve, automatikusan hozzáadja a Budapesti Indulások integrációhoz.</div>
        <div class="status"></div>
        <div class="results"></div>
      </div>
      <ha-form></ha-form>`;
    this._input = this.shadowRoot.querySelector("input");
    this._status = this.shadowRoot.querySelector(".status");
    this._results = this.shadowRoot.querySelector(".results");
    this._form = this.shadowRoot.querySelector("ha-form");
    const def = DotMatrixDepartureCard.formDefinition();
    this._form.schema = def.schema;
    this._form.computeLabel = def.computeLabel;
    this._form.hass = this._hass;
    this._form.data = this._config || {};
    this._form.addEventListener("value-changed", (ev) => {
      ev.stopPropagation();
      this._update(ev.detail.value);
    });
    this._input.addEventListener("input", () => {
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this._search(), 250);
    });
  }

  _setStatus(text, err = false) {
    this._status.textContent = text || "";
    this._status.classList.toggle("err", !!err);
  }

  async _search() {
    const q = this._input.value.trim();
    const seq = ++this._seq;
    if (q.length < 3) {
      this._results.innerHTML = "";
      this._setStatus(q.length ? "Írj be legalább 3 betűt…" : "");
      return;
    }
    this._setStatus("Keresés…");
    try {
      const res = await this._hass.callWS({ type: "budapest_departures/search", query: q });
      if (seq !== this._seq) return; // a newer search is running
      this._render(res.stops || []);
      this._setStatus(res.stops?.length ? `${res.stops.length} találat` : "Nincs ilyen megálló. Próbáld rövidebben vagy ékezettel.");
    } catch (e) {
      if (seq !== this._seq) return;
      this._results.innerHTML = "";
      this._setStatus(e?.code === "unknown_command"
        ? "Ehhez telepítsd és állítsd be a Budapesti Indulások integrációt."
        : e?.message || "Hiba a keresésnél.", true);
    }
  }

  _render(stops) {
    this._stops = stops;
    this._results.innerHTML = stops.map((s, i) => {
      const badges = (s.routes || []).map((r) => {
        const dark = /^#(0{6}|1|2)/i.test(r.color);
        return `<span class="badge${dark ? " dark" : ""}" style="background:${esc(r.color)};color:${esc(r.text_color)}">${esc(r.name)}</span>`;
      }).join("");
      const selected = s.entity_id && s.entity_id === this._config?.entity;
      return `<button class="item${selected ? " selected" : ""}" data-i="${i}">
        <div class="place">${esc(s.place || "")}</div>
        <div class="line"><span class="name">${esc(s.name)}</span>${s.direction ? `<span class="dir">→ ${esc(s.direction)}</span>` : ""}${s.added ? `<span class="added">✓ felvéve</span>` : ""}</div>
        <div class="badges">${badges}</div>
      </button>`;
    }).join("");
    this._results.querySelectorAll(".item").forEach((el) =>
      el.addEventListener("click", () => this._pick(this._stops[Number(el.dataset.i)]))
    );
  }

  async _pick(stop) {
    try {
      let entity = stop.entity_id;
      if (!stop.added || !entity) {
        this._setStatus(`${stop.name} felvétele…`);
        const res = await this._hass.callWS({ type: "budapest_departures/add_stop", stop_id: stop.id });
        entity = res.entity_id;
        stop.added = true;
        stop.entity_id = entity;
      }
      this._update({ ...this._config, entity });
      this._setStatus(`Kiválasztva: ${stop.place ? stop.place + " · " : ""}${stop.name}${stop.direction ? " → " + stop.direction : ""}`);
      this._render(this._stops);
    } catch (e) {
      this._setStatus(e?.message || "Nem sikerült felvenni a megállót.", true);
    }
  }

  _update(config) {
    this._config = config;
    if (this._form) this._form.data = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }
}

if (!customElements.get("dot-matrix-departure-card-editor")) {
  customElements.define("dot-matrix-departure-card-editor", DotMatrixDepartureCardEditor);
}


window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "dot-matrix-departure-card")) window.customCards.push({
  type: "dot-matrix-departure-card",
  name: "Dotmatrix Indulási Kijelző",
  description: "FUTÁR-szerű LED dotmatrix indulási kijelző a Budapesti Indulások integrációhoz.",
  preview: true,
  documentationURL: "https://github.com/szbence7/ha-budapest-departures",
});

console.info(`%c DOT-MATRIX-DEPARTURE-CARD %c v${CARD_VERSION} `, "color:#ff8800;background:#000;font-weight:700", "color:#000;background:#ff8800");
