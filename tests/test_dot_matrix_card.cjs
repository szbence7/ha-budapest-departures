const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const { runInNewContext } = require("node:vm");

const script = readFileSync(
  require("node:path").join(__dirname, "../custom_components/budapest_departures/www/dot-matrix-departure-card.js"),
  "utf8",
);

function setup(config = {}, departures = [], alert = "") {
  const epoch = 1700000000000;
  let now = 0;
  let timerId = 0;
  let intersect;
  const timers = new Map();
  const elements = new Map();
  const metrics = { draws: 0, dots: 0, largestBitmap: 0 };
  const listeners = new Map();
  const board = { clientWidth: 440 };
  const title = { textContent: "", getBoundingClientRect: () => ({ height: 22 }) };
  const cardElement = { clientHeight: 300 };
  const canvas = {
    style: {},
    getContext: () => ({
      clearRect: () => metrics.draws++,
      drawImage() {},
      fillRect() {},
    }),
  };
  const document = {
    hidden: false,
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: (name) => listeners.delete(name),
    createElement: (tag) => {
      assert.equal(tag, "canvas");
      const bitmap = { getContext: () => ({ fill() {} }) };
      Object.defineProperty(bitmap, "width", {
        set: (width) => { metrics.largestBitmap = Math.max(width, metrics.largestBitmap); },
      });
      return bitmap;
    },
  };
  runInNewContext(script, {
    document,
    window: { devicePixelRatio: 1.25 },
    HTMLElement: class {
      attachShadow() {
        const children = { ".board": board, ".title": title, "ha-card": cardElement, canvas };
        this.shadowRoot = { querySelector: (name) => children[name] };
      }
    },
    customElements: {
      get: (name) => elements.get(name),
      define: (name, definition) => elements.set(name, definition),
    },
    ResizeObserver: class { observe() {} disconnect() {} },
    IntersectionObserver: class {
      constructor(callback) { intersect = (isIntersecting) => callback([{ isIntersecting }]); }
      observe() {}
      disconnect() {}
    },
    Path2D: class { roundRect() { metrics.dots++; } },
    Date: { now: () => epoch + now },
    performance: { now: () => now },
    setTimeout: (callback, delay) => {
      timers.set(++timerId, { callback, at: now + delay });
      return timerId;
    },
    clearTimeout: (id) => timers.delete(id),
  });

  const card = new (elements.get("dot-matrix-departure-card"))();
  const update = (deps, message = "") => {
    card.hass = { states: { "sensor.test": {
      state: "10",
      attributes: { departures: deps, alert: message },
    } } };
  };
  const dep = (seconds, headsign = "Hűvösvölgy") => ({
    route: "57", headsign, departure: epoch / 1000 + seconds,
  });
  const advance = (duration) => {
    const end = now + duration;
    while (timers.size) {
      assert.equal(timers.size, 1);
      const [id, timer] = timers.entries().next().value;
      if (timer.at > end) break;
      now = timer.at;
      timers.delete(id);
      timer.callback();
    }
    now = end;
  };
  card.setConfig({ entity: "sensor.test", ...config });
  update(departures.map(([seconds, text]) => dep(seconds, text)), alert);
  card.isConnected = true;
  card.connectedCallback();
  intersect(true);
  return { card, metrics, timers, advance, update, dep, intersect, document, listeners, board, cardElement };
}

test("static and empty boards do not repaint; equivalent sensor updates do not repaint", () => {
  for (const departures of [[], [[600]]]) {
    const { advance, metrics, update, dep, timers } = setup({}, departures);
    const initialDots = metrics.dots;
    advance(10000);
    update(departures.map(([seconds]) => dep(seconds)));
    assert.equal(metrics.draws, 1);
    assert.equal(metrics.dots, initialDots);
    assert.equal(timers.size, departures.length ? 1 : 0);
  }
});

test("countdown changes at the rounding boundary, blinks and expires", () => {
  const { card, advance, metrics, timers } = setup({}, [[31]]);
  advance(1000);
  assert.equal(metrics.draws, 1);
  advance(1);
  assert.equal(metrics.draws, 2);
  assert.equal(card._layers[0].blink, true);
  advance(499);
  assert.equal(metrics.draws, 3);
  advance(89500);
  assert.equal(card._layers[0].blink, undefined);
  assert.equal(timers.size, 0);
});

test("long text and alerts scroll using bounded bitmaps and pause out of view", () => {
  const longText = "Máriaremetei kegytemplom ".repeat(200);
  const { card, advance, metrics, intersect, timers, document, listeners } =
    setup({}, [[600, longText]], longText);
  const initialDots = metrics.dots;
  advance(1000);
  assert.ok(metrics.draws > 10);
  assert.equal(metrics.dots, initialDots);
  advance(10000);
  assert.ok(metrics.dots > initialDots);
  assert.ok(metrics.largestBitmap <= 2 * card._canvas.width);
  intersect(false);
  const draws = metrics.draws;
  advance(2000);
  assert.equal(metrics.draws, draws);
  assert.equal(timers.size, 0);
  intersect(true);
  assert.ok(metrics.draws > draws);
  document.hidden = true;
  listeners.get("visibilitychange")();
  assert.equal(timers.size, 0);
  document.hidden = false;
  listeners.get("visibilitychange")();
  assert.equal(timers.size, 1);
  card.isConnected = false;
  card.disconnectedCallback();
  assert.equal(timers.size, 0);
  assert.equal(listeners.size, 0);
});

test("geometry invalidates cached bitmaps when the card is resized", () => {
  const { card, board, cardElement, metrics, update, dep } =
    setup({ grid_options: { rows: 4 }, rows: 2 }, [[600]]);
  const initialWidth = card._canvas.width;
  board.clientWidth = 300;
  card._resize();
  assert.ok(card._canvas.width < initialWidth);
  assert.equal(metrics.draws, 2);
  card._resize();
  assert.equal(metrics.draws, 2);
  cardElement.clientHeight = 100;
  card._resize();
  assert.equal(card._rowsShown, 1);
  update([dep(600)], "Terelés");
  assert.ok(card._alertLayer);
  update([dep(600)]);
  assert.equal(card._alertLayer, null);
});
