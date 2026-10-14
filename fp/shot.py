"""Look at a built fp world: screenshots along the walk, asset cards, contact sheets (via fp/shot.mjs + Playwright)."""
from __future__ import annotations

import functools
import http.server
import json
import subprocess
import threading
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(root: Path, port: int = 0):
    h = functools.partial(_Quiet, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def shoot(root: Path, shots: list, size=(1280, 720), page="walk.html") -> str:
    srv = serve(root)
    try:
        job = {"base": "http://127.0.0.1:%d/" % srv.server_address[1], "size": list(size), "shots": shots, "page": page}
        r = subprocess.run(["node", str(HERE / "shot.mjs"), json.dumps(job)], capture_output=True, text=True, timeout=1800)
        return r.stdout + r.stderr
    finally:
        srv.shutdown()


def film(root: Path, out: Path, t0=0.0, seconds=8.0, fps=15, size=(960, 540), query="", page="walk.html"):
    """frames stepped at a fixed rate through the real runtime, then an mp4 (needs ffmpeg) and a gif preview."""
    import shutil
    frames = out / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True)
    srv = serve(root)
    try:
        job = {"base": "http://127.0.0.1:%d/" % srv.server_address[1], "size": list(size), "shots": [], "page": page,
               "film": {"t0": t0, "frames": int(seconds * fps), "fps": fps, "dir": str(frames), "query": query}}
        r = subprocess.run(["node", str(HERE / "shot.mjs"), json.dumps(job)], capture_output=True, text=True, timeout=7200)
    finally:
        srv.shutdown()
    mp4 = out / ("film_t%g.mp4" % t0)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(frames / "f_%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(mp4)], check=False)
    return r.stdout + r.stderr, mp4


def sheet(paths, out: Path, cols=3, labels=None, width=640):
    ims = [Image.open(p).convert("RGB") for p in paths if Path(p).exists()]
    if not ims:
        return None
    w = width
    h = int(ims[0].height * w / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    S = Image.new("RGB", (cols * w, rows * (h + 18)), (28, 36, 64))
    d = ImageDraw.Draw(S)
    for i, im in enumerate(ims):
        x, y = (i % cols) * w, (i // cols) * (h + 18)
        S.paste(im.resize((w, h), Image.NEAREST), (x, y + 18))
        if labels:
            d.text((x + 6, y + 3), labels[i], fill=(144, 175, 163))
    S.save(out)
    return out


def walk_shots(root: Path, out: Path, times=(0, 6, 12, 18, 24, 30, 36, 44), size=(1280, 720), extra=""):
    out.mkdir(parents=True, exist_ok=True)
    shots = [{"query": "t=%s&pause=1%s" % (t, extra), "out": str(out / ("walk_t%02d.png" % int(float(t))))} for t in times]
    log = shoot(root, shots, size)
    s = sheet([x["out"] for x in shots], out / "walk_sheet.png", cols=2, labels=["t=%ss" % t for t in times], width=800)
    return log, s


def card_shots(root: Path, out: Path, meshes, yaws=(25, 145, 265), size=(720, 720), pitch=8):
    out.mkdir(parents=True, exist_ok=True)
    shots, labels = [], []
    for m in meshes:
        for y in yaws:
            shots.append({"query": "card=%s&yaw=%d&pitch=%d&pause=1" % (m, y, pitch),
                          "out": str(out / ("card_%s_y%03d.png" % (m.replace(":", "-"), y)))})
            labels.append("%s yaw %d" % (m, y))
    log = shoot(root, shots, size)
    s = sheet([x["out"] for x in shots], out / "cards_sheet.png", cols=len(yaws), labels=labels, width=480)
    return log, s
