"use strict";

const ANGULAR_TYPES = new Set(["azimuth", "angle", "direction"]);
const ELLIPSE_SCALE = 200; // error ellipses are mm-scale; magnify for visibility

const pointsBody = document.querySelector("#points-table tbody");
const obsBody = document.querySelector("#observations-table tbody");

// ---------- geometry helpers (mirrors geo_adjust/geometry.py, degrees) ----------

function dist(p, q) {
  return Math.hypot(q[0] - p[0], q[1] - p[1]);
}
function azimuthDeg(p, q) {
  return (Math.atan2(q[1] - p[1], q[0] - p[0]) * 180) / Math.PI;
}
function wrapDeg(a) {
  return ((a + 180) % 360 + 360) % 360 - 180;
}
function angleDeg(p, q, k) {
  return wrapDeg(azimuthDeg(p, k) - azimuthDeg(p, q));
}

// ---------- points table ----------

function addPointRow(id = "", x = "", y = "") {
  const tr = document.createElement("tr");
  tr.dataset.pointId = id;
  tr.innerHTML = `
    <td><input type="text" class="p-id" value="${id}"></td>
    <td><input type="number" step="any" class="p-x" value="${x}"></td>
    <td><input type="number" step="any" class="p-y" value="${y}"></td>
    <td><button type="button" class="remove-row">&times;</button></td>
  `;
  tr.querySelector(".p-id").addEventListener("input", (e) => {
    const oldId = tr.dataset.pointId;
    const newId = e.target.value.trim();
    if (!newId) return; // mid-edit (e.g. cleared before retyping) — don't cascade through a blank id
    if (oldId && oldId !== newId) renamePointIdInObservations(oldId, newId);
    tr.dataset.pointId = newId;
  });
  tr.querySelector(".remove-row").addEventListener("click", () => {
    tr.remove();
    renderConnectivityGraph();
  });
  pointsBody.appendChild(tr);
}

// A reference point's row is the one canonical place its identity lives, so
// renaming it here cascades to every observation cell using the old id.
// (Editing a from/to/to2 cell directly stays a local, non-cascading edit —
// there's no single "canonical" row for a determined point to rename from,
// and cascading a one-off cell edit could surprise-rename it everywhere.)
function renamePointIdInObservations(oldId, newId) {
  for (const tr of obsBody.querySelectorAll("tr")) {
    for (const cls of [".o-from", ".o-to", ".o-to2"]) {
      const input = tr.querySelector(cls);
      if (input.value === oldId) input.value = newId;
    }
  }
  renderConnectivityGraph();
}

function collectReferencePoints() {
  return [...pointsBody.querySelectorAll("tr")].map((tr) => ({
    id: tr.querySelector(".p-id").value.trim(),
    x: parseFloat(tr.querySelector(".p-x").value),
    y: parseFloat(tr.querySelector(".p-y").value),
  }));
}

// ---------- observations table ----------

function getDefaultSigma(isAngular) {
  const el = document.getElementById(isAngular ? "default-sigma-angular" : "default-sigma-linear");
  return el.value;
}

function addObservationRow(type = "distance", from = "", to = "", to2 = "", value = "", sigma = "") {
  if (sigma === "") sigma = getDefaultSigma(ANGULAR_TYPES.has(type));
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td>
      <select class="o-type">
        <option value="distance">distance</option>
        <option value="azimuth">azimuth</option>
        <option value="angle">angle</option>
        <option value="direction">direction</option>
      </select>
    </td>
    <td><input type="text" class="o-from" value="${from}"></td>
    <td><input type="text" class="o-to" value="${to}"></td>
    <td><input type="text" class="o-to2" value="${to2}"></td>
    <td><div class="value-with-unit"><input type="number" step="any" class="o-value" value="${value}"><span class="unit-suffix o-value-unit"></span></div></td>
    <td><div class="value-with-unit"><input type="number" step="any" class="o-sigma" value="${sigma}"><span class="unit-suffix o-sigma-unit"></span></div></td>
    <td><button type="button" class="remove-row">&times;</button></td>
  `;
  tr.querySelector(".o-type").value = type;
  updateUnitSuffix(tr);
  tr.querySelector(".o-type").addEventListener("change", (e) => {
    // Switch the sigma to the new type's default too, but only if it still
    // matches *some* default value — i.e. the user hasn't customized it.
    const sigmaInput = tr.querySelector(".o-sigma");
    if (sigmaInput.value === getDefaultSigma(false) || sigmaInput.value === getDefaultSigma(true)) {
      sigmaInput.value = getDefaultSigma(ANGULAR_TYPES.has(e.target.value));
    }
    updateUnitSuffix(tr);
  });
  tr.querySelector(".remove-row").addEventListener("click", () => {
    if (selectedObsRow === tr) selectedObsRow = null;
    tr.remove();
    renderConnectivityGraph();
  });
  tr.addEventListener("click", (e) => {
    if (e.target.closest(".remove-row")) return;
    selectObservationRow(tr);
  });
  obsBody.appendChild(tr);
}

function updateUnitSuffix(tr) {
  const isAngular = ANGULAR_TYPES.has(tr.querySelector(".o-type").value);
  tr.querySelector(".o-value-unit").textContent = isAngular ? "°" : "м";
  tr.querySelector(".o-sigma-unit").textContent = isAngular ? "″" : "м";
}

function collectObservations() {
  return [...obsBody.querySelectorAll("tr")].map((tr) => {
    const type = tr.querySelector(".o-type").value;
    const to2 = tr.querySelector(".o-to2").value.trim();
    const obs = {
      type,
      from: tr.querySelector(".o-from").value.trim(),
      to: tr.querySelector(".o-to").value.trim(),
      value: parseFloat(tr.querySelector(".o-value").value),
      sigma: parseFloat(tr.querySelector(".o-sigma").value),
    };
    if (type === "angle" && to2) obs.to2 = to2;
    return obs;
  });
}

// ---------- network file import (a constrained YAML subset, hand-parsed) ----------
//
// This is NOT a general-purpose YAML parser — it only understands exactly
// the shape our own file format uses: a flat `key: value` block for `meta`
// and `defaults`, and flow-style list-of-maps (`- {k: v, k2: v2}`) for
// `reference_points`/`observations`. No nesting, anchors, block scalars, or
// multi-document support. That's a deliberate scope match to the format,
// not a shortcut — see the project's no-external-dependencies choice.

function stripYamlComment(line) {
  let quote = null;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
    } else if (ch === "#") {
      return line.slice(0, i);
    }
  }
  return line;
}

function splitRespectingQuotes(str, delim) {
  const parts = [];
  let cur = "";
  let quote = null;
  for (const ch of str) {
    if (quote) {
      cur += ch;
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
      cur += ch;
    } else if (ch === delim) {
      parts.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  parts.push(cur);
  return parts;
}

function parseYamlScalar(raw) {
  const v = raw.trim();
  if (v.length >= 2 && ((v[0] === '"' && v.endsWith('"')) || (v[0] === "'" && v.endsWith("'")))) {
    return v.slice(1, -1);
  }
  if (v !== "" && !isNaN(v)) return parseFloat(v);
  return v;
}

function parseFlowMapping(text) {
  const obj = {};
  for (const pair of splitRespectingQuotes(text, ",")) {
    if (!pair.trim()) continue;
    const colon = pair.indexOf(":");
    if (colon === -1) continue;
    const key = pair.slice(0, colon).trim();
    obj[key] = parseYamlScalar(pair.slice(colon + 1));
  }
  return obj;
}

function parseYamlNetwork(text) {
  const sections = { meta: {}, defaults: {}, reference_points: [], observations: [] };
  let current = null;

  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = stripYamlComment(lines[i]).replace(/\s+$/, "");
    if (line.trim() === "") continue;

    const sectionMatch = line.match(/^(meta|defaults|reference_points|observations):\s*$/);
    if (sectionMatch) {
      current = sectionMatch[1];
      continue;
    }
    if (!current) {
      throw new Error(`строка ${i + 1}: ожидался заголовок секции (meta/defaults/reference_points/observations), получено "${lines[i]}"`);
    }

    if (current === "meta" || current === "defaults") {
      const m = line.trim().match(/^([A-Za-z0-9_]+):\s*(.*)$/);
      if (!m) throw new Error(`строка ${i + 1}: не удалось разобрать "key: value" в "${lines[i]}"`);
      sections[current][m[1]] = parseYamlScalar(m[2]);
    } else {
      const trimmed = line.trim();
      const flow = trimmed.match(/^-\s*\{(.*)\}\s*$/);
      if (!flow) throw new Error(`строка ${i + 1}: ожидалась запись вида "- {key: value, ...}" в "${lines[i]}"`);
      sections[current].push(parseFlowMapping(flow[1]));
    }
  }
  return sections;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = String(s);
  return div.innerHTML;
}

function renderMeta(meta) {
  const panel = document.getElementById("meta-panel");
  const keys = Object.keys(meta);
  if (keys.length === 0) {
    panel.hidden = true;
    return;
  }
  document.getElementById("meta-list").innerHTML = keys
    .map((k) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(meta[k])}</dd>`)
    .join("");
  panel.hidden = false;
}

function loadParsedNetwork(parsed) {
  if (parsed.defaults.sigma_distance !== undefined) {
    document.getElementById("default-sigma-linear").value = parsed.defaults.sigma_distance;
  }
  if (parsed.defaults.sigma_angular !== undefined) {
    document.getElementById("default-sigma-angular").value = parsed.defaults.sigma_angular;
  }

  pointsBody.innerHTML = "";
  for (const p of parsed.reference_points) {
    addPointRow(p.id, p.x, p.y);
  }

  obsBody.innerHTML = "";
  selectedObsRow = null;
  for (const o of parsed.observations) {
    addObservationRow(
      o.type,
      o.from,
      o.to,
      o.to2 !== undefined ? String(o.to2) : "",
      o.value,
      o.sigma !== undefined ? String(o.sigma) : ""
    );
  }

  renderMeta(parsed.meta);
  errorBox.hidden = true;
  emptyState.hidden = false;
  resultSection.hidden = true;
  renderConnectivityGraph();
}

document.getElementById("import-network-yaml").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  file.text().then((text) => {
    let parsed;
    try {
      parsed = parseYamlNetwork(text);
    } catch (err) {
      showError(`Не удалось разобрать файл: ${err.message}`);
      return;
    }
    loadParsedNetwork(parsed);
  });
  e.target.value = "";
});

// ---------- example network (mirrors geo_adjust/example.py) ----------

function loadExample() {
  const TRUE = { A: [0, 0], B: [0, 1000], C: [800, 300], D: [900, 900], E: [400, 700] };
  const REFERENCE = ["A", "B"];
  const DISTANCE_PAIRS = [
    ["A", "C"], ["A", "D"], ["A", "E"],
    ["B", "C"], ["B", "D"], ["B", "E"],
    ["C", "D"], ["D", "E"], ["C", "E"],
  ];
  const AZIMUTH_OBS = [["A", "C"], ["B", "E"]];
  const ANGLE_OBS = [["C", "A", "D"], ["D", "C", "B"]];
  const DIRECTION_OBS = [["D", "A"], ["D", "C"], ["D", "E"]];
  const Z_TRUE_D = 67.5;

  pointsBody.innerHTML = "";
  for (const id of REFERENCE) {
    const [x, y] = TRUE[id];
    addPointRow(id, x, y);
  }

  obsBody.innerHTML = "";
  selectedObsRow = null;
  for (const [i, j] of DISTANCE_PAIRS) {
    addObservationRow("distance", i, j, "", dist(TRUE[i], TRUE[j]).toFixed(4), 0.005);
  }
  for (const [i, j] of AZIMUTH_OBS) {
    addObservationRow("azimuth", i, j, "", azimuthDeg(TRUE[i], TRUE[j]).toFixed(6), 0.6);
  }
  for (const [station, j, k] of ANGLE_OBS) {
    addObservationRow("angle", station, j, k, angleDeg(TRUE[station], TRUE[j], TRUE[k]).toFixed(6), 0.6);
  }
  for (const [station, target] of DIRECTION_OBS) {
    const value = wrapDeg(azimuthDeg(TRUE[station], TRUE[target]) - Z_TRUE_D);
    addObservationRow("direction", station, target, "", value.toFixed(6), 0.6);
  }

  renderConnectivityGraph();
}

// ---------- live connectivity graph (schematic, not to scale) ----------

const EDGE_COLORS = {
  distance: "var(--edge-distance)",
  azimuth: "var(--edge-azimuth)",
  angle: "var(--edge-angle)",
  direction: "var(--edge-direction)",
};

let selectedObsRow = null;

function markSelectedRow() {
  for (const row of obsBody.querySelectorAll("tr")) {
    row.classList.toggle("selected-row", row === selectedObsRow);
  }
}

function selectObservationRow(tr) {
  selectedObsRow = tr;
  markSelectedRow();
  renderConnectivityGraph();
}

function clearObservationSelection() {
  if (!selectedObsRow) return;
  selectedObsRow = null;
  markSelectedRow();
  renderConnectivityGraph();
}

function renderConnectivityGraph() {
  const svg = document.getElementById("connectivity-svg");
  svg.innerHTML = "";

  const referenceIds = new Set(collectReferencePoints().map((p) => p.id).filter(Boolean));
  const observations = collectObservations();
  const rows = [...obsBody.querySelectorAll("tr")];
  const selectedIndex = selectedObsRow ? rows.indexOf(selectedObsRow) : -1;

  const ids = new Set(referenceIds);
  const edges = [];
  observations.forEach((obs, obsIndex) => {
    if (obs.from) ids.add(obs.from);
    if (obs.to) ids.add(obs.to);
    if (obs.to2) ids.add(obs.to2);
    if (obs.from && obs.to) edges.push([obs.from, obs.to, obs.type, obsIndex]);
    if (obs.type === "angle" && obs.from && obs.to2) edges.push([obs.from, obs.to2, obs.type, obsIndex]);
  });

  const orderedIds = [...ids];
  if (orderedIds.length === 0) return;

  const size = 360, center = size / 2, radius = size / 2 - 36;
  const pos = new Map();
  orderedIds.forEach((id, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / orderedIds.length;
    pos.set(id, [center + radius * Math.cos(a), center + radius * Math.sin(a)]);
  });

  const ns = "http://www.w3.org/2000/svg";
  function el(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  }

  // Group edges by the unordered point pair they connect: when a pair has
  // more than one observation (e.g. both a distance and an azimuth between
  // A and C), drawing them as a single line segment means the last one
  // drawn hides the rest, making a distance edge visually "steal" whatever
  // color happened to be drawn on top of it. Offsetting each into its own
  // parallel line keeps every observation visible in its own true color.
  const pairGroups = new Map();
  for (const [a, b, type, obsIndex] of edges) {
    if (!pos.has(a) || !pos.has(b)) continue;
    const key = [a, b].sort().join("|");
    if (!pairGroups.has(key)) pairGroups.set(key, []);
    pairGroups.get(key).push([a, b, type, obsIndex]);
  }

  const hasSelection = selectedIndex >= 0;
  const highlightedIds = new Set();

  const EDGE_OFFSET = 5; // px between parallel lines for the same point pair
  for (const group of pairGroups.values()) {
    const n = group.length;
    group.forEach(([a, b, type, obsIndex], i) => {
      const isSelected = obsIndex === selectedIndex;
      if (isSelected) {
        highlightedIds.add(a);
        highlightedIds.add(b);
      }
      const [x1, y1] = pos.get(a), [x2, y2] = pos.get(b);
      const dx = x2 - x1, dy = y2 - y1;
      const len = Math.hypot(dx, dy) || 1;
      const offset = (i - (n - 1) / 2) * EDGE_OFFSET;
      const ox = (-dy / len) * offset, oy = (dx / len) * offset;
      const lx1 = x1 + ox, ly1 = y1 + oy, lx2 = x2 + ox, ly2 = y2 + oy;

      if (isSelected) {
        svg.appendChild(
          el("line", {
            x1: lx1, y1: ly1, x2: lx2, y2: ly2,
            stroke: "var(--accent)", "stroke-width": 8, opacity: 0.3, "stroke-linecap": "round",
          })
        );
      }
      svg.appendChild(
        el("line", {
          x1: lx1, y1: ly1, x2: lx2, y2: ly2,
          stroke: EDGE_COLORS[type] || "var(--muted)",
          "stroke-width": isSelected ? 3 : 1.6,
          opacity: hasSelection && !isSelected ? 0.25 : 0.9,
        })
      );
    });
  }

  for (const id of orderedIds) {
    const [x, y] = pos.get(id);
    const isRef = referenceIds.has(id);
    const isHighlighted = highlightedIds.has(id);
    if (isHighlighted) {
      svg.appendChild(
        el("circle", { cx: x, cy: y, r: 11, fill: "none", stroke: "var(--accent)", "stroke-width": 2 })
      );
    }
    svg.appendChild(
      el("circle", {
        cx: x, cy: y, r: 7,
        fill: isRef ? "var(--dot-fixed)" : "var(--dot-free)",
        stroke: "var(--panel)", "stroke-width": 1.5,
        opacity: hasSelection && !isHighlighted ? 0.4 : 1,
      })
    );
    const label = el("text", {
      x, y: y - 12, "font-size": 12, "text-anchor": "middle", fill: "var(--text)",
    });
    label.textContent = id;
    svg.appendChild(label);
  }
}

pointsBody.addEventListener("input", renderConnectivityGraph);
obsBody.addEventListener("input", renderConnectivityGraph);
obsBody.addEventListener("change", renderConnectivityGraph);
document.getElementById("connectivity-svg").addEventListener("click", clearObservationSelection);

// ---------- adjust ----------

const resultSection = document.getElementById("result");
const errorBox = document.getElementById("error-box");
const emptyState = document.getElementById("empty-state");

function showError(message) {
  errorBox.hidden = false;
  errorBox.querySelector(".error-text").textContent = message;
  resultSection.hidden = true;
  emptyState.hidden = true;
}

function formatValidationError(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => `${(e.loc || []).join(".")}: ${e.msg}`).join("\n");
  }
  return JSON.stringify(detail);
}

async function runAdjust() {
  errorBox.hidden = true;
  const payload = {
    reference_points: collectReferencePoints(),
    observations: collectObservations(),
    include_trace: document.getElementById("include-trace").checked,
  };

  let res, data;
  try {
    res = await fetch("/adjust", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    data = await res.json();
  } catch (err) {
    showError(`Не удалось связаться с сервером: ${err}`);
    return;
  }

  if (!res.ok) {
    showError(formatValidationError(data.detail));
    return;
  }

  renderResult(data);
}

// ---------- render result ----------

function renderResult(data) {
  errorBox.hidden = true;
  emptyState.hidden = true;
  resultSection.hidden = false;

  const badge = document.getElementById("status-badge");
  badge.textContent = data.converged ? "Сошлось" : "Не сошлось";
  badge.className = "badge " + (data.converged ? "ok" : "fail");

  const sigma0Text = data.sigma0 === null ? "—" : data.sigma0.toPrecision(4);
  document.getElementById("status-line").textContent =
    `итераций: ${data.iterations}; σ₀ = ${sigma0Text}; ранг = ${data.rank}`;

  const warn = document.getElementById("free-network-warning");
  if (data.rank_deficiency > 0) {
    warn.hidden = false;
    warn.textContent =
      `Свободная сеть: датум недоопределён (дефект ранга = ${data.rank_deficiency}). ` +
      `Абсолютные координаты условны — сохраняются только форма/масштаб/ориентировка сети.`;
  } else {
    warn.hidden = true;
  }

  const ptBody = document.querySelector("#result-points-table tbody");
  ptBody.innerHTML = "";
  for (const p of data.points) {
    const tr = document.createElement("tr");
    const ellipse = p.error_ellipse
      ? `${p.error_ellipse.semi_major_mm.toFixed(2)} / ${p.error_ellipse.semi_minor_mm.toFixed(2)}`
      : "—";
    const theta = p.error_ellipse ? p.error_ellipse.orientation_deg.toFixed(1) : "—";
    tr.innerHTML = `
      <td>${p.id}${p.fixed ? " (опорная)" : ""}</td>
      <td>${p.x.toFixed(4)}</td>
      <td>${p.y.toFixed(4)}</td>
      <td>${p.sigma_x_mm !== null ? p.sigma_x_mm.toFixed(2) : "—"}</td>
      <td>${p.sigma_y_mm !== null ? p.sigma_y_mm.toFixed(2) : "—"}</td>
      <td>${ellipse}</td>
      <td>${theta}</td>
    `;
    ptBody.appendChild(tr);
  }

  const orientHeading = document.getElementById("orientations-heading");
  const orientTable = document.getElementById("orientations-table");
  const orientBody = orientTable.querySelector("tbody");
  orientBody.innerHTML = "";
  if (data.orientations.length > 0) {
    orientHeading.hidden = false;
    orientTable.hidden = false;
    for (const o of data.orientations) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${o.station}</td><td>${o.z_deg.toFixed(4)}</td><td>${o.sigma_z_arcsec.toFixed(2)}</td>`;
      orientBody.appendChild(tr);
    }
  } else {
    orientHeading.hidden = true;
    orientTable.hidden = true;
  }

  const resBody = document.querySelector("#residuals-table tbody");
  resBody.innerHTML = "";
  for (const r of data.residuals) {
    const value = r.value_mm !== null ? `${r.value_mm.toFixed(2)} мм` : `${r.value_arcsec.toFixed(2)} ″`;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.type}</td><td>${r.from}</td><td>${r.to}</td><td>${r.to2 || ""}</td><td>${value}</td>`;
    resBody.appendChild(tr);
  }

  document.getElementById("ellipse-scale-label").textContent = ELLIPSE_SCALE;
  renderNetworkSvg(data);
  renderTrace(data.trace || []);
}

// ---------- computation trace (step-by-step log, raw internal units) ----------

function fmtNum(n, digits = 6) {
  return Number(n).toFixed(digits);
}

function obsLabel(o) {
  return `${o.type} ${o.from}→${o.to}${o.to2 ? "," + o.to2 : ""}`;
}

function renderMatrixTable(matrix, rowLabels, colLabels) {
  let html = "<table><thead><tr><th></th>" + colLabels.map((c) => `<th>${escapeHtml(c)}</th>`).join("") + "</tr></thead><tbody>";
  matrix.forEach((row, i) => {
    html += `<tr><th>${escapeHtml(rowLabels[i])}</th>` + row.map((v) => `<td>${fmtNum(v)}</td>`).join("") + "</tr>";
  });
  return html + "</tbody></table>";
}

function renderVectorTable(vec, rowLabels, colLabel) {
  let html = `<table><thead><tr><th></th><th>${escapeHtml(colLabel)}</th></tr></thead><tbody>`;
  vec.forEach((v, i) => {
    html += `<tr><th>${escapeHtml(rowLabels[i])}</th><td>${fmtNum(v)}</td></tr>`;
  });
  return html + "</tbody></table>";
}

function renderObservationsTable(rows, extraCols) {
  let html = "<table><thead><tr><th>Измерение</th>" + extraCols.map((c) => `<th>${escapeHtml(c.label)}</th>`).join("") + "</tr></thead><tbody>";
  for (const r of rows) {
    html += `<tr><td>${escapeHtml(obsLabel(r))}</td>` + extraCols.map((c) => `<td>${fmtNum(r[c.key])}</td>`).join("") + "</tr>";
  }
  return html + "</tbody></table>";
}

function renderCoordsTable(coords) {
  let html = "<table><thead><tr><th>ID</th><th>X</th><th>Y</th></tr></thead><tbody>";
  for (const [id, [x, y]] of Object.entries(coords)) {
    html += `<tr><td>${escapeHtml(id)}</td><td>${fmtNum(x, 4)}</td><td>${fmtNum(y, 4)}</td></tr>`;
  }
  return html + "</tbody></table>";
}

function renderStepBody(step) {
  if (step.step === "start") {
    let html = "<h4>Приближённые координаты (м)</h4>" + renderCoordsTable(step.coords);
    const stations = Object.keys(step.orientations);
    if (stations.length > 0) {
      html += "<h4>Начальные ориентировки станций Z (рад)</h4>" + renderVectorTable(Object.values(step.orientations), stations, "Z");
    }
    return html;
  }

  if (step.step === "final") {
    let html = "<h4>Невязки v = Aδ − l</h4>" + renderObservationsTable(step.residuals, [{ key: "v", label: "v" }]);
    html +=
      "<h4>Итог</h4><table><tbody>" +
      `<tr><th>σ₀</th><td>${step.sigma0 === null ? "—" : fmtNum(step.sigma0)}</td></tr>` +
      `<tr><th>степени свободы</th><td>${step.dof}</td></tr>` +
      `<tr><th>ранг</th><td>${step.rank}</td></tr>` +
      "</tbody></table>";
    return html;
  }

  // iteration step
  let html = "<h4>Координаты до итерации (м)</h4>" + renderCoordsTable(step.coords_before);
  html +=
    "<h4>Измерения: наблюдено / вычислено по текущим координатам / l = набл. − выч.</h4>" +
    renderObservationsTable(step.observations, [
      { key: "observed", label: "набл." },
      { key: "calc", label: "выч." },
      { key: "l", label: "l" },
      { key: "sigma", label: "σ" },
    ]);
  html += "<h4>Матрица A (частные производные)</h4>" + renderMatrixTable(step.A, step.observations.map(obsLabel), step.unknown_labels);
  html += "<h4>Нормальная матрица N = AᵀPA</h4>" + renderMatrixTable(step.N, step.unknown_labels, step.unknown_labels);
  html += "<h4>Вектор b = AᵀPl</h4>" + renderVectorTable(step.b, step.unknown_labels, "b");
  html += "<h4>Решение δ (поправки к неизвестным)</h4>" + renderVectorTable(step.delta, step.unknown_labels, "δ");
  html += `<h4>max|δ| = ${fmtNum(step.max_delta)} — ${step.converged ? "сошлось" : "продолжаем итерации"}</h4>`;
  html += "<h4>Координаты после итерации (м)</h4>" + renderCoordsTable(step.coords_after);
  return html;
}

function renderTrace(trace) {
  const section = document.getElementById("trace-section");
  const container = document.getElementById("trace-steps");
  if (!trace || trace.length === 0) {
    section.hidden = true;
    container.innerHTML = "";
    return;
  }
  section.hidden = false;
  container.innerHTML = trace
    .map(
      (step, i) => `
    <details class="trace-step" ${i === 0 ? "open" : ""}>
      <summary>${escapeHtml(step.title)}</summary>
      <div class="trace-step-body">${renderStepBody(step)}</div>
    </details>`
    )
    .join("");
}

// ---------- SVG network diagram ----------

function renderNetworkSvg(data) {
  const svg = document.getElementById("network-svg");
  svg.innerHTML = "";

  const before = new Map(data.seed_points.map((p) => [p.id, [p.x, p.y]]));
  const after = new Map(data.points.map((p) => [p.id, [p.x, p.y]]));
  const fixedIds = new Set(data.points.filter((p) => p.fixed).map((p) => p.id));
  const accuracyById = new Map(data.points.map((p) => [p.id, p]));

  const allCoords = [...before.values(), ...after.values()];
  const xs = allCoords.map((c) => c[0]);
  const ys = allCoords.map((c) => c[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const size = 640, pad = 60;
  const scale = Math.min((size - 2 * pad) / spanY, (size - 2 * pad) / spanX);

  // X = north -> screen up (svg y decreases); Y = east -> screen right (svg x increases)
  function toScreen(x, y) {
    const sx = pad + (y - minY) * scale;
    const sy = size - pad - (x - minX) * scale;
    return [sx, sy];
  }

  const ns = "http://www.w3.org/2000/svg";
  function el(tag, attrs) {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  }

  // observation lines (drawn using adjusted positions)
  for (const obs of collectObservations()) {
    const a = after.get(obs.from), b = after.get(obs.to);
    if (a && b) {
      const [x1, y1] = toScreen(...a), [x2, y2] = toScreen(...b);
      svg.appendChild(el("line", { x1, y1, x2, y2, stroke: "var(--dot-before)", "stroke-width": 1, opacity: 0.7 }));
    }
    if (obs.type === "angle" && obs.to2) {
      const c = after.get(obs.to2);
      if (a && c) {
        const [x1, y1] = toScreen(...a), [x2, y2] = toScreen(...c);
        svg.appendChild(el("line", { x1, y1, x2, y2, stroke: "var(--dot-before)", "stroke-width": 1, opacity: 0.7 }));
      }
    }
  }

  // approx -> adjusted shift, approx point, adjusted point, error ellipse
  for (const [id, afterXY] of after) {
    const beforeXY = before.get(id);
    const [ax, ay] = toScreen(...afterXY);

    if (beforeXY && (beforeXY[0] !== afterXY[0] || beforeXY[1] !== afterXY[1])) {
      const [bx, by] = toScreen(...beforeXY);
      svg.appendChild(el("line", { x1: bx, y1: by, x2: ax, y2: ay, stroke: "var(--dot-before)", "stroke-width": 1, "stroke-dasharray": "3,3" }));
      svg.appendChild(el("circle", { cx: bx, cy: by, r: 3, fill: "var(--dot-before)" }));
    }

    const acc = accuracyById.get(id);
    if (acc && acc.error_ellipse) {
      const semiMajorM = (acc.error_ellipse.semi_major_mm / 1000) * ELLIPSE_SCALE;
      const semiMinorM = (acc.error_ellipse.semi_minor_mm / 1000) * ELLIPSE_SCALE;
      const rx = semiMajorM * scale, ry = semiMinorM * scale;
      const screenRotation = acc.error_ellipse.orientation_deg - 90;
      svg.appendChild(
        el("ellipse", {
          cx: ax, cy: ay, rx, ry,
          transform: `rotate(${screenRotation}, ${ax}, ${ay})`,
          fill: "none", stroke: "var(--ellipse)", "stroke-width": 1.2,
        })
      );
    }

    svg.appendChild(el("circle", { cx: ax, cy: ay, r: 5, fill: fixedIds.has(id) ? "var(--dot-fixed)" : "var(--dot-free)", stroke: "var(--panel)", "stroke-width": 1.5 }));
    svg.appendChild(el("text", { x: ax + 8, y: ay - 8, "font-size": 12, fill: "var(--text)" })).textContent = id;
  }
}

// ---------- wiring ----------

document.getElementById("add-point").addEventListener("click", () => {
  addPointRow();
  renderConnectivityGraph();
});
document.getElementById("add-observation").addEventListener("click", () => {
  addObservationRow();
  renderConnectivityGraph();
});
document.getElementById("load-example").addEventListener("click", loadExample);
document.getElementById("adjust").addEventListener("click", runAdjust);
document.getElementById("apply-sigma-defaults").addEventListener("click", () => {
  for (const tr of obsBody.querySelectorAll("tr")) {
    const isAngular = ANGULAR_TYPES.has(tr.querySelector(".o-type").value);
    tr.querySelector(".o-sigma").value = getDefaultSigma(isAngular);
  }
});

loadExample();
