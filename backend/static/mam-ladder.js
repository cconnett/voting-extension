/*
 * mam-ladder.js — render a Maximize Affirmed Majorities result as a ladder.
 *
 * Draws candidates top-to-bottom in final-result order joined by a spine.
 * Each adjacent step ("rung") is annotated with the affirmed head-to-head
 * margin. Disaffirmed reversals (a lower-ranked candidate that beat a
 * higher-ranked one head-to-head) are drawn as muted dashed back-links that
 * arc up the left side. Redundant transitive affirmations are NOT drawn.
 *
 * No dependencies. ES module. Pure-logic and rendering are separated so the
 * derivation can be unit-tested without a DOM.
 *
 *   import { renderMamLadder } from './mam-ladder.js';
 *   renderMamLadder(canvas, { order, pref });
 *
 *   order : string[]  final ranking, winner first.
 *   pref  : either pref[a][b] = number of voters preferring a over b,
 *           or a function (a, b) => that number.
 *           (Use fromMatrix(candidates, matrix) if you have a 2-D array.)
 */

export function computeLadder(order, pref) {
  if (!Array.isArray(order) || order.length < 2)
    throw new Error('order must list at least 2 candidates, winner first');
  const lookup = typeof pref === 'function' ?
      pref :
      (a, b) => (pref[a] && typeof pref[a][b] === 'number') ? pref[a][b] : 0;
  const margin = (a, b) => lookup(a, b) - lookup(b, a);  // >0 means a beats b

  const rungs = [];
  for (let i = 0; i < order.length - 1; i++) {
    const hi = order[i], lo = order[i + 1];
    const m = margin(hi, lo);
    rungs.push({hi, lo, margin: m, tie: m === 0, inconsistent: m < 0});
  }
  // A reversal is any pair whose head-to-head winner sits BELOW its loser in
  // the final order. For a genuine MAM order these are exactly the discarded
  // (disaffirmed) majorities; every other majority is affirmed-but-redundant.
  const reversals = [];
  for (let i = 0; i < order.length; i++)
    for (let j = i + 1; j < order.length; j++) {
      const hi = order[i], lo = order[j];
      const m = margin(lo, hi);
      if (m > 0)
        reversals.push({
          winner: lo,
          loser: hi,
          margin: m,
          topIdx: i,
          botIdx: j,
          span: j - i
        });
    }
  return {order, rungs, reversals};
}

// Convenience: build a pref lookup object from a candidate list + 2-D array,
// where matrix[i][j] = voters preferring candidates[i] over candidates[j].
export function fromMatrix(candidates, matrix) {
  const pref = {};
  candidates.forEach((a, i) => {
    pref[a] = {};
    candidates.forEach((b, j) => {
      if (i !== j) pref[a][b] = matrix[i][j];
    });
  });
  return pref;
}

// Greedy interval partition: pack reversals into the fewest left-side lanes so
// no two arcs in the same lane share a vertical span (or a node).
function assignLanes(reversals) {
  const sorted =
      reversals.map((r, k) => ({r, k}))
          .sort((a, b) => a.r.topIdx - b.r.topIdx || a.r.botIdx - b.r.botIdx);
  const laneBottom = [];  // last botIdx placed in each lane
  const lane = new Array(reversals.length).fill(0);
  for (const {r, k} of sorted) {
    let placed = -1;
    for (let L = 0; L < laneBottom.length; L++) {
      if (laneBottom[L] < r.topIdx) {
        placed = L;
        break;
      }  // strict: don't share a node row
    }
    if (placed === -1) {
      placed = laneBottom.length;
      laneBottom.push(r.botIdx);
    } else
      laneBottom[placed] = r.botIdx;
    lane[k] = placed;
  }
  return {lane, laneCount: Math.max(1, laneBottom.length)};
}

const THEMES = {
  light: {
    spine: '#1D9E75',
    nodeFill: '#F1EFE8',
    nodeStroke: 'rgba(0,0,0,0.18)',
    nodeText: '#2C2C2A',
    nodeSub: '#5F5E5A',
    pillFill: '#FFFFFF',
    pillStroke: 'rgba(0,0,0,0.18)',
    pillText: '#2C2C2A',
    rev: '#D85A30',
    revText: '#993C1D',
    warn: '#A32D2D',
  },
  dark: {
    spine: '#1D9E75',
    nodeFill: '#33332F',
    nodeStroke: 'rgba(255,255,255,0.16)',
    nodeText: '#E8E6DD',
    nodeSub: '#B4B2A9',
    pillFill: '#262624',
    pillStroke: 'rgba(255,255,255,0.22)',
    pillText: '#E8E6DD',
    rev: '#E0773F',
    revText: '#F0997B',
    warn: '#F09595',
  },
};

function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function arrowHead(ctx, tipX, tipY, angle, size, color) {
  ctx.save();
  ctx.fillStyle = color;
  ctx.translate(tipX, tipY);
  ctx.rotate(angle);
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(-size, -size * 0.5);
  ctx.lineTo(-size, size * 0.5);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

export function renderMamLadder(canvas, data, options = {}) {
  const ctx = canvas.getContext('2d');
  const model = computeLadder(data.order, data.pref);
  const {order, rungs, reversals} = model;
  const n = order.length;

  const prefersDark = typeof window !== 'undefined' && window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches;
  debugger;
  const o = Object.assign(
      {
        width: canvas.clientWidth || 680,
        nodeW: 150,
        nodeH: 50,
        vGap: 46,
        rungPillW: 56,
        rungPillH: 24,
        baseBulge: 28,
        laneStep: 34,
        topPad: 26,
        botPad: 26,
        fontFamily:
            'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        theme: prefersDark ? 'dark' : 'light',
        formatMargin: (m) => String(m),
        nodeLabel: (c) => String(c),
        nodeSub: (c, i) => i === 0 ?
            'rank 1 · winner' :
            (i === n - 1 ? `rank ${i + 1} · last` : `rank ${i + 1}`),
      },
      options);

  const t = (typeof o.theme === 'object') ? o.theme :
                                            (THEMES[o.theme] || THEMES.light);
  const {lane, laneCount} = assignLanes(reversals);
  const maxBulge = o.baseBulge + (laneCount - 1) * o.laneStep;

  // measure reversal labels to reserve left margin
  ctx.font = `500 12px ${o.fontFamily}`;
  let maxLabelW = 0;
  for (const r of reversals)
    maxLabelW =
        Math.max(maxLabelW, ctx.measureText(o.formatMargin(r.margin)).width);

  const leftArea =
      reversals.length ? o.baseBulge + 0.5 * maxBulge + maxLabelW + 18 : 20;
  const rightArea = 20;
  const contentW = leftArea + o.nodeW + rightArea;
  const cssW = Math.max(o.width, contentW);
  const offsetX = Math.max(0, (cssW - contentW) / 2);
  const cssH = o.topPad + n * o.nodeH + (n - 1) * o.vGap + o.botPad;

  const centerX = offsetX + leftArea + o.nodeW / 2;
  const nodeX = centerX - o.nodeW / 2;
  const centerY = (i) => o.topPad + i * (o.nodeH + o.vGap) + o.nodeH / 2;

  // hi-DPI canvas
  const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  canvas.style.width = cssW + 'px';
  canvas.style.height = cssH + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  // spine (drawn first; nodes occlude it except in the gaps = rungs)
  ctx.strokeStyle = t.spine;
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(centerX, centerY(0));
  ctx.lineTo(centerX, centerY(n - 1));
  ctx.stroke();

  // disaffirmed reversals: dashed back-links up the left side
  reversals.forEach((r, k) => {
    const topY = centerY(r.topIdx), botY = centerY(r.botIdx);
    const bulge = o.baseBulge + lane[k] * o.laneStep;
    const x0 = nodeX - 2;  // attach just outside the node's left edge
    const cx = nodeX - bulge, cy = (topY + botY) / 2;

    ctx.strokeStyle = t.rev;
    ctx.lineWidth = 1.4;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(x0, botY);
    ctx.quadraticCurveTo(cx, cy, x0, topY);
    ctx.stroke();
    ctx.setLineDash([]);

    arrowHead(ctx, x0, topY, Math.atan2(topY - cy, x0 - cx), 7, t.rev);

    const apexX = nodeX - 1 - 0.5 * bulge;
    ctx.fillStyle = t.revText;
    ctx.font = `500 12px ${o.fontFamily}`;
    ctx.textAlign = 'right';
    ctx.fillText(o.formatMargin(r.margin), apexX - 6, cy);
    ctx.textAlign = 'center';
  });

  // candidate nodes
  order.forEach((c, i) => {
    const cy = centerY(i), top = cy - o.nodeH / 2;
    roundRect(ctx, nodeX, top, o.nodeW, o.nodeH, 8);
    ctx.fillStyle = t.nodeFill;
    ctx.fill();
    ctx.lineWidth = 0.75;
    ctx.strokeStyle = t.nodeStroke;
    ctx.stroke();

    ctx.fillStyle = t.nodeText;
    ctx.font = `500 14px ${o.fontFamily}`;
    ctx.fillText(o.nodeLabel(c, i), centerX, cy - 7);
    ctx.fillStyle = t.nodeSub;
    ctx.font = `400 12px ${o.fontFamily}`;
    ctx.fillText(o.nodeSub(c, i), centerX, cy + 9);
  });

  // rung pills (affirmed adjacent margins)
  rungs.forEach((r, i) => {
    const midY = (centerY(i) + centerY(i + 1)) / 2;
    const x = centerX - o.rungPillW / 2, y = midY - o.rungPillH / 2;
    roundRect(ctx, x, y, o.rungPillW, o.rungPillH, o.rungPillH / 2);
    ctx.fillStyle = t.pillFill;
    ctx.fill();
    ctx.lineWidth = 0.75;
    ctx.strokeStyle = r.inconsistent ? t.warn : t.pillStroke;
    ctx.stroke();

    ctx.font = `600 13px ${o.fontFamily}`;
    ctx.fillStyle = r.inconsistent ? t.warn : t.pillText;
    const label = r.tie ? 'tie' : o.formatMargin(r.margin);
    ctx.fillText(label, centerX, midY + 0.5);
  });

  return {width: cssW, height: cssH, model};
}
