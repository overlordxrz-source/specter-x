"""Lightweight real-time monitoring dashboard for the DI-188 on macOS.

Runs a tiny stdlib HTTP server on 127.0.0.1 and serves a single page with
live channel traces, signal statistics, link health and recording controls.
No web framework, no CDN, no build step - it works offline and starts in
milliseconds.

Honesty rules baked into the UI (repo rule: provenance first):

* a channel with no declared source is rendered as **FLOATING / NOISE**, and
  its numbers are never presented as measurements;
* the calibration basis (nominal vs measured) is shown next to every volt
  value;
* the device identity (model, serial, USB VID:PID, port) is in the header so
  every number on screen is attributable.
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Sequence

from .calibration import CalibrationSet
from .driver import DI188Driver, DI188Error
from .recorder import CsvRecorder, build_provenance
from .stats import ChannelMonitor, ChannelSpec, ChannelState

SERIES_LEN = 900


class Di188Dashboard:
    """Owns the acquisition thread, the shared state and the HTTP server."""

    def __init__(self, driver: DI188Driver, specs: Sequence[ChannelSpec],
                 calibration: CalibrationSet, channels: Sequence[int],
                 rate: float = 100.0, history: int = SERIES_LEN):
        self.driver = driver
        self.specs = list(specs)
        self.calibration = calibration
        self.channels = list(channels)
        self.rate = rate
        self.monitor = ChannelMonitor(self.specs)
        self.history = history
        self.series: Dict[int, deque] = {c: deque(maxlen=history) for c in self.channels}
        self.lock = threading.Lock()
        self.recorder: Optional[CsvRecorder] = None
        self.record_path: Optional[str] = None
        self.record_started: Optional[str] = None
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.server: Optional[ThreadingHTTPServer] = None
        self.http_thread: Optional[threading.Thread] = None
        self.frames_received = 0
        self.frames_expected = 0
        self.stall_events = 0
        self.max_gap_s = 0.0
        self.errors: List[str] = []
        self.started_at = time.time()
        self.realised_rate = rate
        self.last_frame_t = time.time()
        self.link_ok = True

    # -- acquisition -------------------------------------------------------

    def start(self) -> None:
        self.realised_rate = self.driver.configure(self.channels, self.rate)
        self.started_at = time.time()
        self.last_frame_t = self.started_at
        self.thread = threading.Thread(target=self._run, name="di188-acq", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        frame_period = 1.0 / self.realised_rate if self.realised_rate else 0.0
        # macOS delivers CDC-ACM data in bursts: the host routinely sees a
        # quiet moment of up to ~1 s followed by a batch of frames. The frame
        # count is unaffected, so a short gap is batching, not a stall - only
        # a long silence counts as a stall.
        stall_threshold = max(5.0, 20 * frame_period)
        try:
            self.driver.start()
            for sample in self.driver.stream():
                if self.stop_event.is_set():
                    break
                now = time.time()
                gap = now - self.last_frame_t
                self.last_frame_t = now
                with self.lock:
                    if gap > self.max_gap_s:
                        self.max_gap_s = gap
                    if gap > stall_threshold:
                        self.stall_events += 1
                    self.frames_received += 1
                    self.monitor.add(sample.values)
                    volts = []
                    for i, ch in enumerate(self.channels):
                        value = sample.values[i] if i < len(sample.values) else None
                        self.series[ch].append(
                            [sample.t, value,
                             self.calibration.to_volts(ch, value) if value is not None else None])
                        volts.append(self.calibration.to_volts(ch, value)
                                     if value is not None else None)
                    rec = self.recorder
                    if rec is not None:
                        rec.write(sample.t, sample.index, sample.values, volts)
        except DI188Error as exc:
            with self.lock:
                self.link_ok = False
                self.errors.append(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            with self.lock:
                self.link_ok = False
                self.errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            try:
                self.driver.stop()
            except Exception:
                pass

    # -- recording ---------------------------------------------------------

    def start_recording(self, path: str) -> None:
        with self.lock:
            if self.recorder is not None:
                return
            reports = self.monitor.report(self.calibration)
            provenance = build_provenance(
                self.driver.identity, self.driver.device_calibration, self.calibration,
                self.channels, self.realised_rate, reports)
            self.recorder = CsvRecorder(path, self.channels, provenance)
            self.record_path = path
            self.record_started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def stop_recording(self) -> None:
        with self.lock:
            rec, self.recorder = self.recorder, None
        if rec is not None:
            rec.close()

    # -- state for the UI --------------------------------------------------

    def snapshot(self) -> Dict:
        with self.lock:
            uptime = time.time() - self.started_at
            achieved = self.frames_received / uptime if uptime > 0 else 0.0
            expected = int(round(self.realised_rate * uptime))
            reports = self.monitor.report(self.calibration)
            series = {str(ch): [[round(p[0], 4), p[1],
                                 None if p[2] is None else round(p[2], 6)]
                                for p in self.series[ch]] for ch in self.channels}
            rec = self.recorder
            rec_info = {
                "active": rec is not None,
                "path": self.record_path,
                "started_utc": self.record_started,
                "rows": rec.rows if rec is not None else 0,
            }
            floating = [r.index for r in reports
                        if r.state in (ChannelState.FLOATING, ChannelState.UNDECLARED)]
            return {
                "device": self.driver.identity.as_dict(),
                "device_calibration": self.driver.device_calibration.as_dict(),
                "calibration": self.calibration.as_dict(),
                "rate": {
                    "requested": self.rate,
                    "realised": self.realised_rate,
                    "achieved": round(achieved, 2),
                },
                "channels": [r.as_dict() for r in reports],
                "series": series,
                "link": {
                    "uptime_s": round(uptime, 2),
                    "frames_received": self.frames_received,
                    "frames_expected": expected,
                    "shortfall": max(0, expected - self.frames_received),
                    "stall_events": self.stall_events,
                    "max_gap_s": round(self.max_gap_s, 4),
                    "malformed_lines": getattr(self.driver, "malformed_lines", 0),
                    "errors": self.errors[-10:],
                    "ok": self.link_ok,
                },
                "recording": rec_info,
                "floating_channels": floating,
                "all_floating": len(floating) == len(reports) and bool(reports),
            }

    # -- server ------------------------------------------------------------

    def serve(self, host: str = "127.0.0.1", port: int = 8765,
              block: bool = True) -> str:
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):        # quiet
                pass

            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
                elif self.path == "/api/state":
                    body = json.dumps(dashboard.snapshot()).encode("utf-8")
                    self._send(200, body, "application/json")
                elif self.path == "/api/export.csv":
                    path = dashboard.record_path
                    if path and __import__("os").path.exists(path):
                        with open(path, "rb") as fh:
                            data = fh.read()
                        self._send(200, data, "text/csv")
                    else:
                        self._send(404, b"no recording", "text/plain")
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    payload = {}
                action = payload.get("action")
                if action == "start_record":
                    dashboard.start_recording(payload.get("path") or "di188_recording.csv")
                elif action == "stop_record":
                    dashboard.stop_recording()
                elif action == "quit":
                    dashboard.shutdown()
                body = json.dumps({"ok": True, "action": action}).encode("utf-8")
                self._send(200, body, "application/json")

        self.server = ThreadingHTTPServer((host, port), Handler)
        bound_port = self.server.server_address[1]
        url = f"http://{host}:{bound_port}/"
        self.http_thread = threading.Thread(target=self.server.serve_forever,
                                            name="di188-http", daemon=True)
        self.http_thread.start()
        return url

    def shutdown(self) -> None:
        self.stop_event.set()
        self.stop_recording()
        if self.server is not None:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        try:
            self.driver.stop()
        except Exception:
            pass


PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8">
<title>SPECTER-X &middot; DI-188 monitor</title>
<style>
 :root{--bg:#0d1117;--panel:#161b22;--line:#21262d;--fg:#c9d1d9;--dim:#8b949e;
       --ok:#3fb950;--warn:#d29922;--bad:#f85149;--accent:#58a6ff;}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 -apple-system,
      "SF Mono",Menlo,monospace}
 header{padding:10px 16px;border-bottom:1px solid var(--line);background:var(--panel);
        display:flex;flex-wrap:wrap;gap:14px;align-items:baseline;position:sticky;top:0;z-index:5}
 h1{font-size:14px;margin:0;letter-spacing:.5px}
 .k{color:var(--dim)}
 .v{color:var(--fg)}
 .badge{padding:1px 7px;border-radius:10px;font-size:11px;border:1px solid}
 .b-ok{color:var(--ok);border-color:var(--ok)}
 .b-warn{color:var(--warn);border-color:var(--warn)}
 .b-bad{color:var(--bad);border-color:var(--bad)}
 #banner{background:#2a1d05;border:1px solid var(--warn);color:#f0c674;
         padding:8px 16px;display:none;font-weight:600}
 #banner.on{display:block}
 .bar{display:flex;flex-wrap:wrap;gap:16px;padding:8px 16px;border-bottom:1px solid var(--line);
      background:#10161d;font-size:12px}
 .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px;padding:12px}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
 .card.float{border-color:var(--warn)}
 .chead{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
 .ctitle{font-weight:700;letter-spacing:.4px}
 .val{font-size:24px;font-weight:700}
 .unit{font-size:12px;color:var(--dim);font-weight:400}
 table{width:100%;border-collapse:collapse;margin-top:6px;font-size:12px}
 td{padding:1px 0;color:var(--dim);white-space:nowrap}
 td.r{text-align:right;color:var(--fg);padding-right:16px}
 td.lbl{width:34px;color:var(--dim)}
 td.lbl2{width:34px;color:var(--dim);padding-left:6px}
 canvas{width:100%;height:90px;display:block;margin:6px 0;background:#0b0f14;
        border:1px solid var(--line);border-radius:4px}
 .note{font-size:11px;color:var(--dim);margin-top:4px}
 .warnnote{color:var(--warn)}
 .ctrl{padding:10px 16px;border-top:1px solid var(--line);background:var(--panel);
       display:flex;gap:10px;align-items:center;flex-wrap:wrap}
 button{background:#21262d;color:var(--fg);border:1px solid #30363d;border-radius:6px;
        padding:6px 12px;cursor:pointer;font:inherit}
 button:hover{border-color:var(--accent);color:#fff}
 button.pri{background:var(--accent);border-color:var(--accent);color:#06131f;font-weight:700}
 button.danger{border-color:var(--bad);color:var(--bad)}
</style></head><body>
<header>
  <h1>SPECTER-X &middot; DI-188</h1>
  <span class="k">port</span><span class="v" id="h-port">-</span>
  <span class="k">model</span><span class="v" id="h-model">-</span>
  <span class="k">serial</span><span class="v" id="h-serial">-</span>
  <span class="k">usb</span><span class="v" id="h-usb">-</span>
  <span class="badge" id="h-cal">-</span>
  <span class="badge" id="h-link">-</span>
</header>
<div id="banner"></div>
<div class="bar">
  <span><span class="k">rate req/real/ach</span>
        <span class="v" id="b-rate">-</span></span>
  <span><span class="k">uptime</span> <span class="v" id="b-up">-</span></span>
  <span><span class="k">frames</span> <span class="v" id="b-frames">-</span></span>
  <span><span class="k">shortfall</span> <span class="v" id="b-short">-</span></span>
  <span><span class="k">stalls</span> <span class="v" id="b-stall">-</span></span>
  <span><span class="k">max gap</span> <span class="v" id="b-gap">-</span></span>
  <span><span class="k">malformed</span> <span class="v" id="b-malf">-</span></span>
  <span><span class="k">rec</span> <span class="v" id="b-rec">idle</span></span>
</div>
<div class="cards" id="cards"></div>
<div class="ctrl">
  <button class="pri" id="btn-rec">Start recording</button>
  <button id="btn-export">Export CSV</button>
  <button id="btn-clear">Clear stats</button>
  <button class="danger" id="btn-quit">Quit</button>
  <span class="k" id="recpath"></span>
</div>
<script>
const CH = 4;
let cards = {}, lastState = null;

function fmt(v, d){ return (v===null||v===undefined) ? "-" : Number(v).toFixed(d===undefined?3:d); }
function badge(txt, cls){ return '<span class="badge '+cls+'">'+txt+'</span>'; }

function buildCards(n){
  const wrap = document.getElementById('cards');
  wrap.innerHTML = '';
  for(let i=0;i<n;i++){
    const d = document.createElement('div');
    d.className = 'card';
    d.innerHTML =
      '<div class="chead"><span class="ctitle">CH'+(i+1)+'</span><span class="st"></span></div>'+
      '<div class="val"><span class="cv">-</span> <span class="unit">counts</span></div>'+
      '<div class="unit vv">-</div>'+
      '<canvas height="90"></canvas>'+
      '<table>'+
        '<tr><td class="lbl">mean</td><td class="r rm">-</td><td class="lbl2">std</td><td class="r rs">-</td></tr>'+
        '<tr><td class="lbl">min</td><td class="r rmin">-</td><td class="lbl2">max</td><td class="r rmax">-</td></tr>'+
        '<tr><td class="lbl">rms</td><td class="r rr">-</td><td class="lbl2">p-p</td><td class="r rpp">-</td></tr>'+
        '<tr><td class="lbl">n</td><td class="r rn">-</td><td class="lbl2">terminal</td><td class="r rterm">-</td></tr>'+
      '</table>'+
      '<div class="note"></div>';
    wrap.appendChild(d);
    cards[i] = d;
  }
}

function drawSpark(cv, series, key){
  const ctx = cv.getContext('2d');
  const w = cv.clientWidth, h = cv.clientHeight;
  cv.width = w; cv.height = h;
  ctx.clearRect(0,0,w,h);
  if(!series || series.length < 2) return;
  const vals = series.map(p => p[key]).filter(v => v!==null && v!==undefined);
  if(vals.length < 2) return;
  let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  if(hi-lo < 1e-9){ hi = lo + 1; lo = lo - 1; }
  const pad = (hi-lo)*0.12; lo -= pad; hi += pad;
  const n = series.length;
  ctx.strokeStyle = '#58a6ff'; ctx.lineWidth = 1; ctx.beginPath();
  let started = false;
  for(let i=0;i<n;i++){
    const v = series[i][key];
    if(v===null||v===undefined){ started=false; continue; }
    const x = (i/(n-1))*(w-2)+1;
    const y = h-2 - ((v-lo)/(hi-lo))*(h-4);
    if(!started){ ctx.moveTo(x,y); started=true; } else ctx.lineTo(x,y);
  }
  ctx.stroke();
  ctx.strokeStyle='rgba(255,255,255,0.10)';
  ctx.beginPath(); ctx.moveTo(0,h/2); ctx.lineTo(w,h/2); ctx.stroke();
}

function render(s){
  lastState = s;
  const d = s.device || {};
  document.getElementById('h-port').textContent = d.port || '-';
  document.getElementById('h-model').textContent = d.model_name || '-';
  document.getElementById('h-serial').textContent = d.serial_number || '-';
  document.getElementById('h-usb').textContent =
      (d.usb_product||'?') + ' ' + (d.usb_vid!==null&&d.usb_vid!==undefined?
      ('0x'+Number(d.usb_vid).toString(16)):'?') + ':' +
      (d.usb_pid!==null&&d.usb_pid!==undefined?
      ('0x'+Number(d.usb_pid).toString(16)):'?');

  const cal = s.calibration || {};
  const cb = document.getElementById('h-cal');
  cb.textContent = 'CAL: ' + (cal.basis_label || '-');
  cb.className = 'badge ' + (cal.any_calibrated ? 'b-ok' : 'b-warn');

  const link = s.link || {};
  const lb = document.getElementById('h-link');
  lb.textContent = link.ok ? 'LINK OK' : 'LINK ERROR';
  lb.className = 'badge ' + (link.ok ? 'b-ok' : 'b-bad');

  const bn = document.getElementById('banner');
  if(s.all_floating){
    bn.className = 'on';
    bn.textContent = 'ALL INPUTS FLOATING / NOISE - no source connected. '+
      'Values below are ADC noise, NOT measurements. Do not use them as data.';
  } else if((s.floating_channels||[]).length){
    bn.className = 'on';
    bn.textContent = 'Channels ' + s.floating_channels.map(i=>'CH'+(i+1)).join(', ') +
      ' are FLOATING / NOISE - not measurements.';
  } else { bn.className = ''; bn.textContent=''; }

  const r = s.rate||{};
  document.getElementById('b-rate').textContent =
      fmt(r.requested,1)+' / '+fmt(r.realised,1)+' / '+fmt(r.achieved,1)+' Hz';
  document.getElementById('b-up').textContent = fmt(link.uptime_s,1)+' s';
  document.getElementById('b-frames').textContent =
      (link.frames_received||0)+' / '+(link.frames_expected||0);
  document.getElementById('b-short').textContent = link.shortfall||0;
  document.getElementById('b-stall').textContent = link.stall_events||0;
  document.getElementById('b-gap').textContent = fmt(link.max_gap_s,3)+' s';
  document.getElementById('b-malf').textContent = link.malformed_lines||0;

  const rec = s.recording||{};
  document.getElementById('b-rec').textContent =
      rec.active ? ('RECORDING '+rec.rows+' rows') : 'idle';
  document.getElementById('recpath').textContent = rec.path || '';
  document.getElementById('btn-rec').textContent =
      rec.active ? 'Stop recording' : 'Start recording';
  document.getElementById('btn-rec').className = rec.active ? 'danger' : 'pri';

  (s.channels||[]).forEach((ch, i) => {
    const card = cards[i]; if(!card) return;
    const floating = ch.state !== 'CONNECTED';
    card.className = 'card' + (floating ? ' float' : '');
    card.querySelector('.st').innerHTML = floating
      ? badge(ch.state==='FLOATING'?'FLOATING / NOISE':'UNDECLARED (assumed floating)','b-warn')
      : badge('CONNECTED','b-ok');
    card.querySelector('.cv').textContent = fmt(ch.counts.last,1);
    card.querySelector('.vv').textContent = ch.volts===null||ch.volts===undefined
      ? (ch.is_measurement ? 'volts: not claimed (unknown front end)'
                           : 'volts: none - floating input, not a measurement')
      : ('volts: '+fmt(ch.volts,4)+' V  (nominal, uncertified)');
    card.querySelector('.rm').textContent = fmt(ch.counts.mean,2);
    card.querySelector('.rs').textContent = fmt(ch.counts.std,2);
    card.querySelector('.rmin').textContent = fmt(ch.counts.min,1);
    card.querySelector('.rmax').textContent = fmt(ch.counts.max,1);
    card.querySelector('.rr').textContent = fmt(ch.counts.rms,2);
    card.querySelector('.rpp').textContent = fmt(ch.counts.peak_to_peak,1);
    card.querySelector('.rn').textContent = ch.counts.n;
    card.querySelector('.rterm').textContent = ch.terminal || '-';
    const note = card.querySelector('.note');
    note.textContent = ch.note || '';
    note.className = floating ? 'note warnnote' : 'note';
    drawSpark(card.querySelector('canvas'), (s.series||{})[String(ch.index)], 1);
  });
}

async function poll(){
  try{
    const r = await fetch('/api/state', {cache:'no-store'});
    const s = await r.json();
    if(!cards[0]) buildCards((s.channels||[]).length);
    render(s);
  }catch(e){ /* keep polling */ }
}
async function post(action, extra){
  await fetch('/api/'+action.replace('_','-'), {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(Object.assign({action:action}, extra||{}))});
}
document.getElementById('btn-rec').onclick = () =>
  post(lastState && lastState.recording && lastState.recording.active ? 'stop_record' : 'start_record',
       {path:'di188_recording.csv'});
document.getElementById('btn-export').onclick = () => { window.location = '/api/export.csv'; };
document.getElementById('btn-clear').onclick = () => { location.reload(); };
document.getElementById('btn-quit').onclick = () => post('quit');
setInterval(poll, 500);
poll();
</script></body></html>
"""
