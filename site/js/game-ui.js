// Game UI: draws the windows, takes Up/Down calls, reveals the answer. Scoring lives in game.js (pure functions).
(async function () {
  "use strict";
  const site = await KL.loadSite();
  if (!site) return;
  const { el } = KL;
  const S = KLSVG, G = KLGame;
  const wins = site.game;
  const total = wins.length;
  let state = G.initialState();

  const stage = document.getElementById("stage");
  const live = document.getElementById("live");
  const talliesEl = document.getElementById("tallies");
  const word = (d) => (d > 0 ? "up" : d < 0 ? "down" : "flat");

  function candles(win, reveal) {
    const W = 640, H = 300, l = 8, r = 8, t = 10, b = 280;
    const [lo, hi] = G.priceRange(win, reveal);
    const pad = (hi - lo) * 0.06 || 1;
    const nCtx = win.context.length, nAct = reveal ? win.actual.length : 0;
    const slots = nCtx + nAct;
    const x = (i) => l + ((i + 0.5) / slots) * (W - l - r);
    const y = S.scale(lo - pad, hi + pad, b, t);
    const bw = Math.max(2, ((W - l - r) / slots) * 0.6);
    const svg = S.chart(W, H, "Candlestick chart of the recent context bars" + (reveal ? " followed by the actual path" : ""));
    win.context.forEach((c, i) => {
      const [o, h, lw, cl] = c;
      svg.appendChild(S.s("line", { class: "wick", x1: x(i), x2: x(i), y1: y(h), y2: y(lw) }));
      const top = y(Math.max(o, cl)), hgt = Math.max(1.5, Math.abs(y(o) - y(cl)));
      svg.appendChild(S.s("rect", { class: cl >= o ? "candle-up" : "candle-down", x: x(i) - bw / 2, y: top, width: bw, height: hgt }));
    });
    svg.appendChild(S.s("line", { class: "s-zero", x1: l, x2: W - r, y1: y(G.reference(win)), y2: y(G.reference(win)) }));
    if (reveal) {
      svg.appendChild(S.s("line", { class: "divider", x1: x(nCtx - 1) + (W - l - r) / slots / 2, x2: x(nCtx - 1) + (W - l - r) / slots / 2, y1: t, y2: b }));
      const xs = win.actual.map((_, k) => x(nCtx + k));
      const startX = [x(nCtx - 1)].concat(xs), startY = [y(G.reference(win))].concat(win.actual.map(y));
      svg.appendChild(S.s("path", { class: "s-actual", d: S.pathD(startX, startY) }));
    }
    return svg;
  }

  function renderTallies() {
    const t = G.tallies(state);
    talliesEl.replaceChildren(
      el("div", { class: "you" }, [el("strong", { text: String(t.you) }), "You"]),
      el("div", { class: "kronos" }, [el("strong", { text: String(t.kronos) }), "Kronos"]),
      el("div", { class: "coin" }, [el("strong", { text: String(t.coin) }), "Coin flip"]));
    document.getElementById("progress").textContent = KL.text.game.progress(t.answered, total);
    const bar = document.getElementById("progressbar");
    bar.setAttribute("aria-valuemax", String(total));
    bar.setAttribute("aria-valuenow", String(t.answered));
    bar.firstElementChild.style.width = (total ? (t.answered / total) * 100 : 0) + "%";
  }

  function showWindow() {
    const win = wins[state.index];
    const pn = site.protocol.pred_len, nb = win.context.length;
    stage.replaceChildren();
    stage.appendChild(el("p", { class: "small", text: "Window " + (state.index + 1) + " of " + total + ". The last " + nb +
      " hourly bars are shown, rescaled so the last close sits at the dashed line. Will the close " + pn + " bars later be above or below it?" }));
    const holder = el("div", { id: "chartholder" }, [candles(win, false)]);
    stage.appendChild(holder);
    const up = el("button", { type: "button", class: "call", id: "btn-up", "aria-label": "Call up" }, ["Up"]);
    const down = el("button", { type: "button", class: "call", id: "btn-down", "aria-label": "Call down" }, ["Down"]);
    const row = el("div", { class: "row", role: "group", "aria-label": "Your call" }, [up, down]);
    stage.appendChild(row);
    stage.appendChild(el("p", { class: "small", text: "Keyboard: press the Up or Down arrow key, or tab to a button and press Enter." }));
    const call = (c) => answer(c);
    up.addEventListener("click", () => call(1));
    down.addEventListener("click", () => call(-1));
    up.focus({ preventScroll: true });
  }

  function answer(c) {
    if (state.revealed) return;
    const win = wins[state.index];
    state = G.answer(state, win, c);
    const rec = state.history[state.history.length - 1];
    document.getElementById("chartholder").replaceChildren(candles(win, true));
    stage.querySelector(".row").remove();
    stage.querySelectorAll("p.small").forEach((p, i) => { if (i) p.remove(); });
    const msg = "The close ended " + word(rec.truth) + ". You called " + word(rec.you) + " (" + (rec.youHit ? "right" : "wrong") + "). Kronos called " +
      word(rec.kronos) + " (" + (rec.kronosHit ? "right" : "wrong") + "). The coin flip said " + word(rec.coin) + " (" + (rec.coinHit ? "right" : "wrong") + ").";
    live.textContent = msg;
    stage.appendChild(el("p", { class: "reveal", text: msg }));
    stage.appendChild(el("p", { class: "small reveal" }, [KL.text.game.thisWas, KL.chip(win.reveal.pair), KL.text.game.on + win.reveal.date + "."]));
    const nextBtn = el("button", { type: "button", id: "btn-next", class: "reveal" }, [state.index + 1 >= total ? "See final result" : "Next window"]);
    nextBtn.addEventListener("click", () => { state = G.next(state); renderTallies(); G.isFinished(state, total) ? finish() : showWindow(); });
    stage.appendChild(nextBtn);
    renderTallies();
    nextBtn.focus({ preventScroll: true });
  }

  function finish() {
    const t = G.tallies(state);
    stage.replaceChildren(
      el("h2", { text: "Final tallies" }),
      el("p", { text: "You got " + t.you + " right, Kronos " + t.kronos + ", the coin flip " + t.coin + ", out of " + t.answered + "." }),
      el("p", { class: "card", text: "This is a game of " + total + " hand-picked-by-seed windows, not evidence about the model; the evidence is on the Evidence page." }));
    const again = el("button", { type: "button" }, ["Play again"]);
    again.addEventListener("click", () => { state = G.initialState(); renderTallies(); showWindow(); });
    stage.appendChild(again);
    again.focus({ preventScroll: true });
  }

  document.addEventListener("keydown", (e) => {
    if (state.revealed || G.isFinished(state, total)) return;
    if (e.key === "ArrowUp") { e.preventDefault(); answer(1); }
    else if (e.key === "ArrowDown") { e.preventDefault(); answer(-1); }
  });

  renderTallies();
  if (total) showWindow(); else stage.textContent = "No game windows in the data.";
})();
