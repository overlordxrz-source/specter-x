"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const esc = (x) =>
  String(x ?? "—").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmt = (x, d = 0) =>
  x == null
    ? "—"
    : Number(x).toLocaleString(undefined, { maximumFractionDigits: d });
const token = $("meta[name=specter-token]").content;
let state = null,
  files = [],
  page = "overview",
  source = "",
  query = "",
  busy = false,
  scrubbing = false,
  evidenceId = null,
  evidenceText = null,
  problem = null,
  lastRender = "",
  generation = 0,
  switching = false;
const titles = {
  overview: [
    "System overview",
    "Evidence first. Every observation, traceable.",
  ],
  sensing: [
    "Sensing workspace",
    "Inspect acquired signals, source metadata and data quality.",
  ],
  spatial: [
    "Spatial workspace",
    "A shared world starts with defensible geometry.",
  ],
  research: [
    "Research & sessions",
    "Preserved observations and the evidence behind experimental claims.",
  ],
  nodes: [
    "Node network",
    "Source identity and availability. No assumed remote platforms.",
  ],
  evidence: [
    "Evidence & diagnostics",
    "Inspect the chain from displayed value to original recording.",
  ],
};
async function api(path, body) {
  const r = await fetch(
    "/api/" + path,
    body
      ? {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Specter-Token": token,
          },
          body: JSON.stringify(body),
        }
      : {},
  );
  const d = await r.json();
  if (!r.ok) throw Error(d.error || r.statusText);
  return d;
}
function notice(message) {
  problem = message;
  $("#notice").hidden = !message;
  $("#notice").textContent = message || "";
}
function badge(text, style = "") {
  return `<span class="badge ${style}">${esc(text)}</span>`;
}
function kv(rows) {
  return (
    '<dl class="kv">' +
    rows
      .map(
        ([k, v]) =>
          `<dt>${esc(k)}</dt><dd ${k === "Process uptime" ? 'id="service-uptime"' : ""}>${esc(v)}</dd>`,
      )
      .join("") +
    "</dl>"
  );
}
function panel(title, subtitle, body, right = "") {
  return `<section class="panel"><div class="panel-head"><div><h3>${title}</h3>${subtitle ? `<p class="subtitle">${subtitle}</p>` : ""}</div>${right}</div>${body}</section>`;
}
function metric(label, value, unit, note) {
  return `<div class="metric"><div class="label">${label}</div><div class="number">${value}<small>${unit}</small></div><div class="note">${esc(note)}</div></div>`;
}
function selected() {
  const o = state?.observation;
  return !source || o?.sensor_id === source ? o : null;
}
function amplitudeChart(o) {
  const a = o?.value?.amplitudes;
  if (!a)
    return '<div class="empty"><div class="empty-icon">∿</div><h2>No signal available</h2><p>This source has no acquired observations in the selected recording. No substitute feed is generated.</p></div>';
  const values = a.filter((x) => x != null),
    max = Math.max(1, ...values),
    w = 760,
    h = 200,
    left = 40,
    bottom = 170,
    scale = max * 1.15;
  let svg = `<svg class="signal-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Actual CSI amplitudes for selected observation">`;
  for (let j = 0; j < 4; j++) {
    const y = bottom - j * 45;
    svg += `<line x1="${left}" y1="${y}" x2="750" y2="${y}" stroke="#2c3038" stroke-dasharray="3 5"/><text x="0" y="${y + 3}">${fmt((scale * j * 45) / bottom, 1)}</text>`;
  }
  a.forEach((v, i) => {
    if (v != null) {
      const x = left + i * (710 / Math.max(1, a.length - 1)),
        y = bottom - (v / scale) * bottom;
      svg += `<line x1="${x}" y1="${bottom}" x2="${x}" y2="${y}" stroke="#8eb8bc" stroke-width="3"/>`;
    }
  });
  [0, 16, 32, 48, 63]
    .filter((i) => i < a.length)
    .forEach(
      (i) =>
        (svg += `<text x="${left + (i * 710) / (a.length - 1)}" y="193" text-anchor="middle">${i}</text>`),
    );
  return `<div class="panel-body"><div class="chart-top"><span class="chart-legend">LLTF amplitude · acquisition order</span><span class="value">Peak ${fmt(max, 2)}</span></div>${svg}</svg><div class="chart-foot"><span>${esc(o.units)} · slot index, not spatial position</span><span class="warning">UNCALIBRATED</span></div></div>`;
}
function rssiChart() {
  const seq = state.series.filter((p) => p.rssi != null);
  if (seq.length < 2)
    return '<div class="panel-body subtle">Not enough RSSI metadata in the selected window.</div>';
  const min = Math.min(...seq.map((x) => x.rssi)) - 1,
    max = Math.max(...seq.map((x) => x.rssi)) + 1,
    w = 760;
  const path = seq
    .map(
      (p, i) =>
        `${i ? "L" : "M"}${40 + (i * 710) / (seq.length - 1)},${95 - ((p.rssi - min) / (max - min)) * 80}`,
    )
    .join(" ");
  return `<div class="panel-body"><div class="chart-top"><span class="chart-legend">Received signal strength · dBm</span><span class="value">Latest ${fmt(seq.at(-1).rssi, 1)} dBm</span></div><svg class="signal-chart rssi-chart" viewBox="0 0 760 120" role="img" aria-label="Actual RSSI across recent records"><line x1="40" y1="95" x2="750" y2="95" stroke="#343740"/><text x="0" y="22">${fmt(max)}</text><text x="0" y="96">${fmt(min)}</text><path d="${path}" fill="none" stroke="#ae7b8d" stroke-width="1.8"/><text x="40" y="116">${fmt(seq[0].tick)} µs</text><text x="750" y="116" text-anchor="end">${fmt(seq.at(-1).tick)} µs</text></svg><div class="chart-foot"><span>Last ${seq.length} records · record-order spacing</span><span>Signal level ≠ motion detection</span></div></div>`;
}
function inspector(o) {
  if (!o)
    return '<div class="panel-body subtle">Select an available source or recording to inspect evidence.</div>';
  return `<div class="panel-body">${kv([
    [
      "Origin / interpretation",
      `${o.origin.toUpperCase()} / ${o.classification}`,
    ],
    ["Sequence", fmt(o.seq)],
    ["Native acquisition tick", fmt(o.acquisition.ticks) + " ticks"],
    ["Clock epoch", o.acquisition.epoch],
    [
      "Receive timestamp",
      o.received.time_ns == null ? "Unrecorded" : o.received.time_ns,
    ],
    ["Calibration", o.calibration.status],
    ["Uncertainty", o.uncertainty.kind],
    ["Frame", o.frame_id],
    ["Validity", o.validity.state],
  ])}<div class="divider"></div><div class="callout">Radio-channel measurement only. No motion, position, identity or physiology is inferred.</div><button class="inspection-button" data-inspect="current">Inspect complete observation ↗</button></div>`;
}
function sensors() {
  const known = [
    {
      id: "bench/esp32-s3/csi",
      name: "ESP32-S3 / Wi-Fi CSI",
      note: "No active hardware connection",
      fallback: "OFFLINE",
    },
    {
      id: "bench/di188/analog",
      name: "DATAQ DI-188",
      note: "Previously tested · currently disconnected",
      fallback: "OFFLINE",
    },
    {
      id: "future/thermal",
      name: "Radiometric thermal",
      note: "Module not received · no driver opened",
      fallback: "UNAVAILABLE",
    },
  ];
  const present = new Set(state.sources.map((s) => s.sensor_id));
  if (state.observation) present.add(state.observation.sensor_id);
  for (const sid of present)
    if (!known.some((s) => s.id === sid))
      known.push({
        id: sid,
        name: sid,
        note: "Recorded source",
        fallback: "OFFLINE",
      });
  return (
    '<div class="sensor-list">' +
    known
      .map((s) => {
        const active = present.has(s.id) && state.status !== "DISCONNECTED";
        return `<div class="sensor-row"><div><div class="sensor-name"><i class="dot ${active ? "replay" : ""}"></i>${esc(s.name)}</div><div class="sensor-meta">${active ? "Preserved recording · no live connection" : esc(s.note)}</div></div><span class="status-text ${active ? "replay" : ""}">${active ? "REPLAY" : s.fallback}</span></div>`;
      })
      .join("") +
    "</div>"
  );
}
function notifications() {
  return `<div class="panel-body">${
    state.events.length
      ? state.events
          .slice(-4)
          .reverse()
          .map(
            (e) =>
              `<div class="notification"><span class="code">${esc(e.code)}</span><span class="message">${esc(e.message)}</span></div>`,
          )
          .join("")
      : '<p class="subtle">No session events. Service available; acquisition is offline.</p>'
  }<p class="subtle">Transport: loopback only. Physical source freshness is unknown during replay.</p></div>`;
}
function table() {
  return `<div class="table-wrap"><table><thead><tr><th>RECORD</th><th>SEQUENCE</th><th>NATIVE TICK</th><th>RSSI / dBm</th><th>ORIGIN</th><th>VALIDITY</th></tr></thead><tbody>${state.rows.map((r) => `<tr tabindex="0" data-index="${r.index}" aria-label="Inspect record ${r.index + 1}"><td>${fmt(r.index + 1)}</td><td>${fmt(r.seq)}</td><td class="muted">${fmt(r.tick)}</td><td>${fmt(r.rssi)}</td><td>${esc(r.origin).toUpperCase()}</td><td class="warn">${esc(r.state)}</td></tr>`).join("") || '<tr><td colspan="6">No matching observations in this window.</td></tr>'}</tbody></table></div>`;
}
function filters() {
  return `<div class="toolbar"><select id="source-filter" aria-label="Source filter"><option value="">All recorded sources</option>${state.sources.map((s) => `<option value="${esc(s.sensor_id)}" ${source === s.sensor_id ? "selected" : ""}>${esc(s.sensor_id)}</option>`).join("")}<option value="bench/di188/analog" ${source === "bench/di188/analog" ? "selected" : ""}>DI-188 · OFFLINE</option><option value="future/thermal" ${source === "future/thermal" ? "selected" : ""}>Thermal · UNAVAILABLE</option></select><input id="record-filter" placeholder="Filter sequence or source…" aria-label="Filter records" value="${esc(query)}"></div>`;
}
function render() {
  if (!state) return;
  const o = selected(),
    h = o ? state.health || {} : {},
    v = o?.value || {};
  $("#mode").textContent =
    (state.status === "DISCONNECTED" ? "DETACHED / REPLAY" : state.mode) +
    (state.observation?.origin === "simulated"
      ? " / SIMULATED"
      : state.observation?.origin === "unknown"
        ? " / UNKNOWN"
        : "");
  $("#source-status").innerHTML =
    `<strong>${esc(state.status)}${state.status === "LOADING" ? " · indexing in background" : ""}</strong>${state.file ? esc(state.file) : "No active recording"}${state.limited ? " · limit reached" : ""}`;
  $("#recording").textContent = state.file || "No session selected";
  $("#record-count").textContent = state.count
    ? `${fmt(state.position + 1)} / ${fmt(state.count)}`
    : "— / —";
  if (!scrubbing) {
    $("#timeline").max = Math.max(0, state.count - 1);
    $("#timeline").value = state.position;
  }
  $("#play").textContent = state.playing ? "Ⅱ" : "▶";
  $("#play").setAttribute(
    "aria-label",
    state.playing ? "Pause replay" : "Play replay",
  );
  $("#play").disabled = state.status !== "READY";
  $("#timeline").disabled = !state.count;
  $("#previous").disabled = !state.count;
  $("#next").disabled = !state.count;
  $("#timeline-caption").textContent = state.count
    ? `${state.speed}× · 25 records/s base · ${fmt(state.count)} indexed · native acquisition time preserved`
    : "Open preserved evidence to begin.";
  const error = state.error
    ? `<div class="error-banner">${esc(state.error.code)} · ${esc(state.error.message)}</div>`
    : "";
  const signature = JSON.stringify([
    page,
    state.position,
    state.count,
    state.status,
    state.error,
    source,
    query,
    evidenceId,
    state.counters,
  ]);
  if (signature === lastRender) {
    const u = $("#service-uptime");
    if (u) u.textContent = fmt(state.service.uptime_seconds, 1) + " s";
    return;
  }
  lastRender = signature;
  const wholeSourceMissing =
    state.counters.sequence_missing ?? h.source_missing ?? 0;
  const faults =
    (state.counters.malformed || 0) +
    (state.counters.unsupported_layout || 0) +
    wholeSourceMissing;
  const quality = faults
    ? `<div class="error-banner">DATA QUALITY · ${fmt(state.counters.malformed || 0)} malformed lines · ${fmt(state.counters.unsupported_layout || 0)} unsupported layouts · ${fmt(wholeSourceMissing)} missing source records. Source totals where available. Exclusions are not sensing results.</div>`
    : "";
  let html = "";
  if (page === "overview") {
    html = `<div class="metrics">${metric("INDEXED OBSERVATIONS", fmt(state.count), "records", state.limited ? "Configured limit reached" : "Preserved source · no live capture")}${metric("RECENT ACQUISITION RATE", fmt(h.rate_hz, 1), "records/s", "Native ticks · up to 128-record window")}${metric("SOURCE SEQUENCE GAPS", fmt(h.source_missing), "missing", "Through selected observation")}${metric("CALIBRATION", o ? esc(o.calibration.status).toUpperCase() : "UNKNOWN", "", "Not a calibrated sensing result")}</div><div class="grid"><div class="stack">${panel("Wi-Fi CSI / signal workspace", "Preserved ESP32-S3 evidence", amplitudeChart(o), badge(o ? o.origin.toUpperCase() : "OFFLINE"))}${panel("Receive-level history", "Metadata from the selected source window", rssiChart())}${panel("Observation timeline", "Select a row to inspect the original envelope", table(), '<span class="subtle">Latest 80 records</span>')}</div><div class="stack">${panel("Source availability", "One registry · distinct readiness states", sensors())}${panel("Observation inspector", "Selected recording position", inspector(o), badge(o ? o.validity.state.toUpperCase() : "UNKNOWN", "warn"))}${panel("Session activity", "Service events, not experimental findings", notifications())}</div></div>`;
  } else if (page === "sensing") {
    html =
      filters() +
      `<div class="grid"><div class="stack">${panel("Signal inspection", o ? esc(o.sensor_id) : "Unavailable source", amplitudeChart(o), badge(o ? o.origin.toUpperCase() : "OFFLINE"))}${o ? panel("RSSI history", "No received-power normalization applied here", rssiChart()) : ""}${panel("Recorded observations", "Filtered window through current timeline position", table())}</div><div class="stack">${panel("Source metadata", "Actual selected observation", inspector(o))}${panel(
        "Acquisition quality",
        "Native timestamp and source accounting",
        `<div class="panel-body">${kv([
          ["PHY rate code", v.phy_rate_code],
          [
            "Frame signal length",
            v.sig_len_bytes == null ? "—" : v.sig_len_bytes + " B",
          ],
          [
            "Noise floor",
            v.noise_floor_dbm == null ? "—" : v.noise_floor_dbm + " dBm",
          ],
          ["Missing source records", h.source_missing],
          ["Retention evictions", h.buffer_evictions],
          ["Raw malformed lines", state.counters.malformed ?? "Unknown"],
          ["Clock synchronization", "Not established"],
        ])}<div class="divider"></div><p class="subtle">Unsupported layouts and malformed records are excluded visibly in diagnostics. Per-slot amplitudes retain the invalid-pair mask.</p></div>`,
      )}</div></div>`;
  } else if (page === "spatial") {
    html =
      panel(
        "SPECTER-WORLD / spatial layer",
        "2D / 3D research workspace",
        `<div class="empty"><div class="empty-icon">⌑</div>${badge("NO CALIBRATED SPATIAL DATA")}<h2>Geometry must be earned.</h2><p>The current recording contains radio-channel amplitudes in a frequency-slot frame. It does not contain calibrated locations, depth, tracks or a map. There is no spatial scene to render yet.</p><div class="requirements"><div class="requirement"><span>01 / GEOMETRY</span><h3>Calibrated frames</h3><p>Sensor intrinsics, rig extrinsics and an explicit world anchor.</p></div><div class="requirement"><span>02 / TIME</span><h3>Acquisition alignment</h3><p>Clock-domain mapping and measured synchronization uncertainty.</p></div><div class="requirement"><span>03 / EVIDENCE</span><h3>Defensible observations</h3><p>Reference comparisons, source provenance and valid uncertainty.</p></div></div></div>`,
      ) +
      `<div class="subheading">CURRENT FRAME INSPECTION</div>` +
      panel(
        "Signal-domain source",
        "Available for inspection, unsuitable for spatial plotting",
        `<div class="panel-body">${kv([
          ["Frame ID", o?.frame_id || "No observation"],
          ["Clock domain", o?.acquisition.domain || "Unknown"],
          ["Spatial uncertainty", "Unknown / not defined"],
          ["Physical source age", "Unknown during replay"],
          ["Spatial renderer", "PLANNED · no geometry pipeline"],
        ])}</div>`,
      );
  } else if (page === "research") {
    html = `<div class="split"><div>${panel("Recording library", "Actual files in approved local roots", `<div class="panel-body">${sessionButtons()}</div>`)}<div class="subheading">EXPERIMENTAL EVIDENCE</div>${panel("Reports & checkpoints", "Read source artifacts; no automatic claim promotion", `<div class="panel-body">${evidenceButtons()}</div>`)}</div><div class="stack">${panel(
      "Selected session",
      "Acquisition and experimental validity are separate",
      `<div class="panel-body">${kv([
        ["Recording", state.file || "Not selected"],
        ["Indexed records", fmt(state.count)],
        [
          "Load duration",
          state.load_seconds == null ? "—" : fmt(state.load_seconds, 2) + " s",
        ],
        ["Playback mode", state.mode],
        ["Experimental conclusion", "Not inferred by WORLD"],
        ["Protocol compliance", "Consult original report"],
      ])}<div class="divider"></div><div class="callout">A healthy capture is not a positive human-sensing result. Reported Alpha motion statistics remain experimental evidence, with their original controls and caveats.</div></div>`,
    )}${panel(evidenceText ? esc(evidenceText.name) : "Evidence reader", "Original artifact text, not a newly validated result", `<div class="panel-body"><pre>${esc(evidenceText?.content || "Select a report or checkpoint to inspect its source text.")}</pre></div>`)}${panel("Raw versus derived", "No hidden feature inference", `<div class="panel-body subtle">The raw CSI source contains firmware-emitted IQ values and metadata. FRONTIER derives amplitude as hypot(pair), masks the first invalid two pairs and retains the raw SHA-256 and line reference. WORLD reads those same envelopes. It does not run a motion classifier or recompute experimental statistics.</div>`)}</div></div>`;
  } else if (page === "nodes") {
    html = `<div class="node-cards">${panel(
      "Local research service",
      "Actual running Python process",
      `<div class="panel-body"><div class="node-mark">CORE / LOCAL SERVICE</div>${kv(
        [
          ["Service", state.service.state],
          ["Process uptime", fmt(state.service.uptime_seconds, 1) + " s"],
          ["Transport", state.service.transport],
          ["Hardware acquisition", state.service.acquisition],
          ["Device uptime", "Unrecorded"],
          ["Clock quality", "Unsynchronized source ticks"],
        ],
      )}</div>`,
      badge("RUNNING"),
    )}${panel(
      "Recorded bench node",
      "Identity scoped to this recording",
      `<div class="panel-body"><div class="node-mark">${esc(o?.node_id || "NO RECORDING")}</div>${kv(
        [
          ["Source ID", o?.sensor_id || "Unknown"],
          [
            "Connection",
            state.status === "DISCONNECTED" ? "Detached" : "Replay only",
          ],
          ["Native epoch", o?.acquisition.epoch || "Unknown"],
          ["Authenticated hardware identity", "Not established"],
          ["Source transport drops", h.source_missing ?? "Unknown"],
          ["Live freshness", "Unknown"],
        ],
      )}</div>`,
      badge(state.count ? "REPLAY" : "OFFLINE"),
    )}</div><div class="subheading">SENSOR AVAILABILITY</div>${panel("Registered source boundaries", "No competing status representations", sensors())}<div class="subheading">EXPANSION BOUNDARY</div>${panel("AIR / GROUND / LINK", "PLANNED · no remote platforms connected", `<div class="panel-body subtle">Future authenticated nodes need device identity, clock mapping, loss recovery and source-specific adapters. No fleet nodes, telemetry links, flight controls or safety-critical commands are implemented. Dedicated controllers retain flight-critical stabilization.</div>`)}`;
  } else {
    html = `<div class="grid"><div class="stack">${panel("Observation evidence", "Complete FRONTIER envelope; no UI-generated confidence", `<div class="panel-body"><pre>${esc(o ? JSON.stringify(o, null, 2) : "No observation selected.")}</pre></div>`, badge(o ? o.evidence.level.toUpperCase() : "UNKNOWN"))}${panel("Session event log", "Structured service and parsing errors", notifications())}</div><div class="stack">${panel(
      "Integrity & provenance",
      "References retained from FRONTIER",
      `<div class="panel-body">${kv([
        ["Raw artifact", o?.evidence.raw?.artifact || "Unknown"],
        ["Raw line", o?.evidence.raw?.line || "Unknown"],
        ["Algorithm", o?.evidence.algorithm || "Unknown"],
        ["Revision", o?.evidence.revision || "Unknown"],
        ["Parent references", o?.evidence.parents.length ?? "Unknown"],
      ])}<div class="divider"></div><div class="tiny-label">SOURCE SHA-256</div><p class="hash">${esc(o?.evidence.raw?.sha256 || "Unknown")}</p><div class="callout">A file hash establishes byte identity. It does not prove experimental labels, calibration or a scientific conclusion.</div></div>`,
    )}${panel(
      "Index / parser accounting",
      "Whole indexed source unless limited",
      `<div class="panel-body">${kv(Object.entries(state.counters).map(([k, v]) => [k, fmt(v)]))}<div class="divider"></div>${kv(
        [
          ["Index limit", fmt(state.max_records)],
          ["Limit reached", state.limited ? "Yes" : "No"],
          ["Retained diagnostic history", "256 observations"],
          ["Freshness basis", "Replay position; no live age"],
          ["Live hardware verified", "No"],
        ],
      )}</div>`,
    )}</div></div>`;
  }
  const focused = document.activeElement?.id;
  let caret =
    focused === "record-filter" ? document.activeElement.selectionStart : null;
  $("#content").innerHTML = error + quality + html;
  if (focused === "record-filter") {
    const el = $("#record-filter");
    el?.focus();
    el?.setSelectionRange(caret, caret);
  }
}
function sessionButtons() {
  const list = files.filter((f) => f.kind === "replay");
  return (
    list
      .map(
        (f) =>
          `<button class="session-item" data-session="${f.id}"><span><b>${esc(f.name)}</b><small>${esc(f.group)} / ${esc(f.relative)} · ${fmt(f.bytes / 1024, 1)} KiB</small></span><span>↗</span></button>`,
      )
      .join("") ||
    '<p class="subtle">No recordings in approved roots. Restart with --root /path/to/recordings or --replay /path/to/capture.raw.csi.</p>'
  );
}
function evidenceButtons() {
  return (
    files
      .filter((f) => f.kind === "evidence")
      .map(
        (f) =>
          `<button class="file-button" data-evidence="${f.id}"><span>${esc(f.name)}</span><small>↗</small></button>`,
      )
      .join("") || '<p class="subtle">No reports in approved roots.</p>'
  );
}
async function refresh() {
  if (busy || switching) return;
  busy = true;
  const requestGeneration = generation;
  try {
    const nextState = await api(
      "state?" +
        new URLSearchParams({
          ...(source ? { source } : {}),
          ...(query ? { q: query } : {}),
        }),
    );
    if (requestGeneration !== generation) return;
    state = nextState;
    $("#service-label").textContent = "Local service available";
    $("#service-dot").style.background = "#91a49c";
    render();
  } catch (e) {
    if (requestGeneration !== generation) return;
    $("#service-label").textContent = "Service disconnected";
    $("#service-dot").style.background = "#df8a8d";
    notice(e.message);
    $("#play").disabled = true;
  } finally {
    busy = false;
  }
}
async function control(action, value) {
  try {
    await api("control", { action, value });
    await refresh();
  } catch (e) {
    notice(e.message);
  }
}
async function openSession(id) {
  const previousState = state;
  generation++;
  switching = true;
  notice(null);
  if (state) {
    state = {
      ...state,
      status: "LOADING",
      count: 0,
      position: 0,
      playing: false,
      observation: null,
      health: null,
      rows: [],
      series: [],
      counters: {},
      sources: [],
      error: null,
      file: files.find((f) => f.id === id)?.name || "Selected recording",
    };
    lastRender = "";
    render();
  }
  $("#sessions-dialog").close();
  try {
    await api("session", { id });
    notice(null);
    lastRender = "";
    source = "";
    query = "";
    switching = false;
    await refresh();
  } catch (e) {
    switching = false;
    state = previousState;
    lastRender = "";
    render();
    notice(e.message);
  }
}
function navigate(view) {
  if (view !== "sensing") {
    source = "";
    query = "";
  }
  lastRender = "";
  page = titles[view] ? view : "overview";
  history.replaceState(null, "", "#" + page);
  $$("nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === page),
  );
  $("#breadcrumb").textContent = page.toUpperCase();
  $("#page-title").textContent = titles[page][0];
  $("#page-description").textContent = titles[page][1];
  render();
  window.scrollTo(0, 0);
}
async function inspect(index) {
  try {
    const d = index === "current" ? state : await api("state?index=" + index);
    $("#inspection-title").textContent =
      "Observation " + fmt(d.observation?.seq);
    $("#inspection-body").innerHTML =
      `<p>Preserved FRONTIER envelope. ${esc(d.observation?.origin)} origin; ${esc(d.observation?.validity.state)} validity.</p><pre>${esc(JSON.stringify(d.observation, null, 2))}</pre>`;
    $("#inspection").showModal();
  } catch (e) {
    notice(e.message);
  }
}
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button,[data-index]");
  if (!b) return;
  if (b.dataset.view) navigate(b.dataset.view);
  if (b.dataset.session) openSession(b.dataset.session);
  if (b.dataset.inspect) inspect("current");
  if (b.dataset.index) inspect(b.dataset.index);
  if (b.dataset.evidence) {
    try {
      evidenceId = b.dataset.evidence;
      evidenceText = await api("evidence?id=" + evidenceId);
      render();
    } catch (err) {
      notice(err.message);
    }
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.dataset.index)
    inspect(e.target.dataset.index);
});
document.addEventListener("change", (e) => {
  if (e.target.id === "source-filter") {
    source = e.target.value;
    refresh();
  }
  if (e.target.id === "record-filter") {
    query = e.target.value;
    refresh();
  }
});
let filterTimer;
document.addEventListener("input", (e) => {
  if (e.target.id === "record-filter") {
    query = e.target.value;
    clearTimeout(filterTimer);
    filterTimer = setTimeout(refresh, 250);
  }
});
$("#open-session").onclick = () => {
  $("#session-list").innerHTML = sessionButtons();
  $("#sessions-dialog").showModal();
};
$("#close-dialog").onclick = () => $("#sessions-dialog").close();
$("#close-inspection").onclick = () => $("#inspection").close();
$("#play").onclick = () => control("play", !state?.playing);
$("#speed").onchange = (e) => control("speed", Number(e.target.value));
$("#previous").onclick = () => control("seek", Math.max(0, state.position - 1));
$("#next").onclick = () =>
  control("seek", Math.min(state.count - 1, state.position + 1));
$("#detach").onclick = () => control("disconnect");
$("#timeline").onpointerdown = () => (scrubbing = true);
$("#timeline").oninput = (e) => {
  $("#record-count").textContent =
    fmt(Number(e.target.value) + 1) + " / " + fmt(state.count);
};
$("#timeline").onchange = (e) => {
  scrubbing = false;
  control("seek", Number(e.target.value));
};
$("#timeline").onpointerup = () => (scrubbing = false);
$("#shutdown").onclick = async () => {
  try {
    await api("shutdown", {});
    notice(
      "Service stopped. Close this window, or relaunch SPECTER-WORLD from the terminal.",
    );
  } catch (e) {
    notice(e.message);
  }
};
async function start() {
  try {
    files = await api("catalog");
    navigate(location.hash.slice(1) || "overview");
    await refresh();
  } catch (e) {
    notice(e.message);
  }
  setInterval(refresh, 500);
}
start();
