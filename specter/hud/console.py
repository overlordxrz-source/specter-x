"""SPECTER-VIEW diagnostic mode, shared OpenCV stack; no sensor acquisition."""

from __future__ import annotations
import cv2
import numpy as np

BG = (20, 16, 13)
PANEL = (33, 28, 23)
BORDER = (58, 49, 40)
TEXT = (231, 226, 218)
MUTED = (157, 145, 129)
ACCENT = (198, 194, 98)
WARN = (103, 186, 232)


def render_console(
    session,
    width=1280,
    height=800,
    page="streams",
    stats=None,
    error="",
    session_name="No session loaded",
):
    if width < 800 or height < 480:
        raise ValueError("console requires at least 800x480")
    c = np.full((height, width, 3), BG, np.uint8)
    large = width >= 1100

    def txt(s, x, y, color=TEXT, size=0.59):
        s = str(s)
        cv2.putText(
            c,
            s,
            (int(x), int(y)),
            cv2.FONT_HERSHEY_SIMPLEX,
            size,
            color,
            1,
            cv2.LINE_AA,
        )

    def fit(s, max_width, size=0.59):
        s = str(s)
        while (
            s
            and cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, size, 1)[0][0] > max_width
        ):
            s = s[:-4] + "..." if len(s) > 4 else ""
        return s

    def box(x, y, w, h):
        cv2.rectangle(c, (x, y), (x + w, y + h), PANEL, -1)
        cv2.rectangle(c, (x, y), (x + w, y + h), BORDER, 1)

    txt("SPECTER / VIEW", 24, 34, size=0.8)
    txt("RESEARCH CONSOLE", 24, 59, MUTED, 0.52)
    txt("LOCAL REPLAY  /  NO LIVE ACQUISITION", max(300, width - 452), 34, ACCENT, 0.56)
    txt(fit(session_name, width - 330), 300, 59, MUTED, 0.52)
    reg = session.registry if session else None
    if reg is None:
        from specter.platform.registry import default_registry

        reg = default_registry()
    card_y = 80
    gap = 14
    cw = (width - 48 - 2 * gap) // 3
    for i, st in enumerate(reg.streams.values()):
        x = 24 + i * (cw + gap)
        box(x, card_y, cw, 112)
        txt(fit(st.spec.label, cw - 24), x + 12, card_y + 25, size=0.56)
        txt(
            st.state,
            x + 12,
            card_y + 51,
            ACCENT if st.state == "REPLAY" else MUTED,
            0.64,
        )
        rate = "--" if st.rate_hz is None else f"{st.rate_hz:.1f} records/s"
        txt(
            fit(rate + " | gaps " + str(st.source_missing), cw - 24),
            x + 12,
            card_y + 77,
            MUTED,
            0.49,
        )
        cal = (
            st.last.to_dict()["calibration"]["status"] if st.last else "not established"
        )
        txt(
            fit("Calibration: " + cal, cw - 24),
            x + 12,
            card_y + 99,
            WARN if st.last else MUTED,
            0.48,
        )
    y = 210
    bottom = height - 93
    content_h = bottom - y
    obs = (
        None
        if not session or session.position < 0
        else session.observations[session.position].to_dict()
    )
    if page == "nodes":
        box(24, y, width - 48, content_h)
        txt("NODES / EVIDENCE SOURCES", 40, y + 30, ACCENT)
        txt("bench  -  local recorded CSI; analog driver not connected", 40, y + 67)
        txt("future -  no thermal source; no remote peers connected", 40, y + 100)
        txt(
            "AIR / GROUND / WORLD are planned. No positions inferred.",
            40,
            y + 144,
            MUTED,
            0.55,
        )
        txt(
            "Network failure: local replay remains available.", 40, y + 181, MUTED, 0.55
        )
    elif page.startswith("evidence"):
        box(24, y, width - 48, content_h)
        txt("OBSERVATION / PROVENANCE", 40, y + 29, ACCENT)
        if obs:
            ac = obs["acquisition"]
            ev = obs["evidence"]
            rr = ev["raw"] or {}
            rows = [
                f"{obs['origin'].upper()} / {obs['classification'].upper()} / {ev['level']}",
                f"Source: {obs['sensor_id']}   Seq: {obs['seq']}",
                f"Acquired: {ac['ticks']} ticks @ {ac['tick_hz']} Hz",
                f"Clock: {ac['domain']} / {ac['epoch']}",
                f"Frame: {obs['frame_id']}    Units: {obs['units']}",
                f"Raw: {rr.get('artifact', 'unavailable')}  line {rr.get('line', '--')}",
                f"SHA256: {rr.get('sha256', 'unavailable')}",
                f"Flags: {', '.join(obs['validity']['flags'])}",
                f"Calibration: {obs['calibration']['status']} / uncertainty: {obs['uncertainty']['kind']}",
                f"Algorithm: {ev['algorithm']}  Revision: {ev['revision']}",
                "Original receive time: unrecorded"
                if obs["received"]["time_ns"] is None
                else f"Original receive time: {obs['received']['time_ns']} ns",
            ]
            # Small screen has multiple pages rather than shrinking text.
            cap = max(1, (content_h - 61 - 8) // 26 + 1)
            rows = rows[cap : cap * 2] if page == "evidence-more" else rows[:cap]
            for j, row in enumerate(rows):
                txt(
                    fit(row, width - 80),
                    40,
                    y + 61 + j * 26,
                    MUTED if j else TEXT,
                    0.55,
                )
        else:
            txt("Load a preserved session to inspect its evidence.", 40, y + 70, MUTED)
    else:
        leftw = int((width - 62) * 0.61)
        rightx = 38 + leftw
        rightw = width - rightx - 24
        box(24, y, leftw, content_h)
        box(rightx, y, rightw, content_h)
        txt("SIGNAL / CSI AMPLITUDES", 40, y + 29, ACCENT, 0.58)
        txt("Signal domain. No motion / localization claim.", 40, y + 53, MUTED, 0.49)
        plot_top = y + 72
        plot_h = max(70, min(150, content_h - 115))
        plot_w = leftw - 38
        cv2.line(
            c, (40, plot_top + plot_h), (40 + plot_w, plot_top + plot_h), BORDER, 1
        )
        if obs and isinstance(obs["value"], dict) and "amplitudes" in obs["value"]:
            vals = obs["value"]["amplitudes"]
            valid = [v for v in vals if v is not None]
            peak = max(valid or [1]) or 1
            for i, v in enumerate(vals):
                if v is None:
                    continue
                x = 40 + int(i * plot_w / max(1, len(vals) - 1))
                top = plot_top + plot_h - int(v / peak * (plot_h - 9))
                cv2.line(c, (x, plot_top + plot_h), (x, top), ACCENT, 2)
            txt(
                f"{len(vals)} frequency slots  |  peak {peak:.1f}",
                40,
                plot_top + plot_h + 24,
                MUTED,
                0.5,
            )
            if large:
                recent = list(reg.history)[-5:]
                for j, o in enumerate(recent):
                    d = o.to_dict()
                    txt(
                        f"#{d['seq']}  {d['classification']}  {d['validity']['state']}",
                        40,
                        plot_top + plot_h + 63 + j * 27,
                        MUTED,
                        0.56,
                    )
        else:
            txt(
                "No data / no generated demonstration feeds",
                40,
                plot_top + 40,
                MUTED,
                0.52,
            )
        txt("OBSERVATION", rightx + 14, y + 29, ACCENT, 0.58)
        rows = ["No observation selected"]
        if obs:
            ac = obs["acquisition"]
            rows = [
                obs["origin"].upper() + " / " + obs["classification"].upper(),
                f"Seq {obs['seq']} | {obs['validity']['state']}",
                f"Native tick: {ac['ticks']}",
                f"Calibration: {obs['calibration']['status']}",
                f"Uncertainty: {obs['uncertainty']['kind']}",
                f"Source missing: {obs['dropped_before']}",
                f"Buffer evictions: {reg.evictions}",
                "Receive time: unknown"
                if obs["received"]["time_ns"] is None
                else "Receive time preserved",
            ]
        if not large and obs:
            rows = [rows[i] for i in (0, 1, 2, 4, 5)]
        count = min(len(rows), max(0, (content_h - 61 - 7) // 27 + 1))
        for j, row in enumerate(rows[:count]):
            txt(
                fit(row, rightw - 28),
                rightx + 14,
                y + 61 + j * 27,
                TEXT if j == 0 else MUTED,
                0.54,
            )
    if error:
        txt(fit("ERROR: " + error, width - 48), 24, height - 78, WARN, 0.55)
    elif stats:
        txt(
            fit(
                f"Source malformed: {stats.get('malformed', 0)} | loaded {stats.get('loaded', 0)} | limited: {bool(stats.get('truncated', False))}",
                width - 48,
            ),
            24,
            height - 78,
            MUTED,
            0.5,
        )
    startx = 24
    endx = width - 24
    ly = height - 54
    cv2.line(c, (startx, ly), (endx, ly), BORDER, 4)
    pos = session.position if session else -1
    n = len(session.observations) if session else 0
    knob = startx + int(max(0, pos) * (endx - startx) / max(1, n - 1))
    cv2.circle(c, (knob, ly), 6, ACCENT, -1)
    txt(f"{max(0, pos + 1):,} / {n:,}", 24, height - 17, MUTED, 0.5)
    txt(
        "Space: play/pause   A/D: step   E: evidence   N: nodes   S: streams",
        max(165, width - 690),
        height - 17,
        MUTED,
        0.49,
    )
    return c
