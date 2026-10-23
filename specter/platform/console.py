"""CLI driver for the diagnostic mode of specter.app. No live hardware APIs."""

from pathlib import Path
import time
import cv2
from .replay import load_source, write_capture
from .registry import ReplaySession
from .observation import ContractError
from specter.hud.console import render_console


def run_console(args):
    width, height = map(int, args.console_size.lower().split("x"))
    if width < 800 or height < 480:
        raise ValueError("minimum console size is 800x480")
    files = []
    if args.session_dir:
        directory = Path(args.session_dir)
        files = sorted(
            p
            for p in directory.iterdir()
            if p.is_file()
            and (p.name.endswith(".raw.csi") or p.name.endswith(".observations.jsonl"))
        )[:64]
    if args.replay:
        p = Path(args.replay)
        if p not in files:
            files.insert(0, p)
    index = 0
    session = None
    stats = {}
    error = ""
    page = "streams"
    playing = False

    def load(path):
        observations, counts = load_source(path, args.replay_limit)
        result = ReplaySession(observations, args.buffer_capacity)
        result.seek(min(args.at, len(observations) - 1))
        return result, counts

    if files:
        session, stats = load(files[0])
    if args.capture_out:
        if session is None:
            raise ValueError("--capture-out requires a replay source")
        write_capture(args.capture_out, session.observations)
    if args.headless and not args.save_frame:
        raise ValueError("--headless console requires --save-frame")
    win = "SPECTER-X / Diagnostic Console"
    frame = 0
    running = True
    if not args.headless:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, width, height)

        def mouse(event, x, y, flags, param):
            if (
                event == cv2.EVENT_LBUTTONDOWN
                and session
                and abs(y - (height - 54)) < 22
            ):
                session.seek(
                    round(
                        (max(24, min(x, width - 24)) - 24)
                        / max(1, width - 48)
                        * (len(session.observations) - 1)
                    )
                )

        cv2.setMouseCallback(win, mouse)
    try:
        while running:
            if playing and session:
                for _ in range(8):
                    if not session.step():
                        playing = False
                        break
            image = render_console(
                session,
                width,
                height,
                page,
                stats,
                error,
                files[index].name if files else "No session / offline",
            )
            frame += 1
            if args.headless or (args.frames and frame >= args.frames):
                running = False
            if not args.headless:
                cv2.imshow(win, image)
                key = cv2.waitKey(30) & 255
                if key in (ord("q"), 27):
                    running = False
                elif key == 32:
                    playing = not playing
                elif key == ord("a") and session:
                    session.seek(session.position - 1)
                elif key == ord("d") and session:
                    session.seek(session.position + 1)
                elif key == ord("e"):
                    page = "evidence-more" if page == "evidence" else "evidence"
                elif key == ord("n"):
                    page = "nodes"
                elif key == ord("s"):
                    page = "streams"
                elif key == ord("j") and len(files) > 1:
                    index = (index + 1) % len(files)
                    try:
                        session, stats = load(files[index])
                        error = ""
                    except (ValueError, OSError) as exc:
                        session = None
                        error = str(exc)
            if args.save_frame and not running:
                if not cv2.imwrite(args.save_frame, image):
                    raise OSError("cannot write console preview")
    finally:
        if not args.headless:
            cv2.destroyWindow(win)
    return 0
