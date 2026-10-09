"""Video and image I/O through ffmpeg pipes (no OpenCV needed)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image


def probe(path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": float(num) / float(den),
            "frames": int(s.get("nb_read_frames", 0))}


def read_frames(path, max_side: int = 0):
    """Yield HxWx3 uint8 frames. max_side>0 downsizes on decode (keeps aspect)."""
    info = probe(path)
    w, h = info["w"], info["h"]
    vf = []
    if max_side and max(w, h) > max_side:
        s = max_side / max(w, h)
        w, h = int(round(w * s / 2) * 2), int(round(h * s / 2) * 2)
        vf = ["-vf", f"scale={w}:{h}:flags=area"]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), *vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.wait()


def write_video(frames, path, fps: float, crf: int = 18):
    """Frames HxWx3 uint8 -> h264 mp4 (used by tests to simulate generator output)."""
    frames = list(frames)
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
                          str(path)], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    p.wait()


def save_png(arr: np.ndarray, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path)


def save_gif(frames, path, durations_ms, bg=None):
    """RGBA frames -> looping GIF. bg=None keeps 1-bit transparency, else composites on bg (r,g,b)."""
    ims = []
    for f in frames:
        if bg is not None:
            base = Image.new("RGBA", (f.shape[1], f.shape[0]), tuple(bg) + (255,))
            base.alpha_composite(Image.fromarray(f))
            ims.append(base.convert("RGB").quantize(255, dither=Image.Dither.NONE))
        else:
            im = Image.fromarray(f)
            a = im.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
            q = im.convert("RGB").quantize(255, dither=Image.Dither.NONE)
            q.paste(255, mask=Image.eval(a, lambda v: 255 - v))
            q.info["transparency"] = 255
            ims.append(q)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ims[0].save(path, save_all=True, append_images=ims[1:], duration=list(durations_ms), loop=0, disposal=2,
                **({"transparency": 255} if bg is None else {}))
