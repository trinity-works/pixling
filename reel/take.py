"""Takes: decode + key a generated video into Cels, cached on (file, key config)."""
from __future__ import annotations

import hashlib
import pickle
import zlib
from pathlib import Path

from pp.paths import OUT as PP_OUT

from . import cut, key
from .io import read_frames

ROOT = Path(__file__).resolve().parent.parent
OUT = PP_OUT / "reel"


def key_cfg(spec):
    k = dict(spec.get("key", {}))
    c = k.get("color")
    if c in (None, "auto"):
        k["color"] = None
    elif isinstance(c, str):
        k["color"] = key.KEYS[c] if c in key.KEYS else tuple(int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return key.KeyCfg(**k)


def key_take(path: Path, cfg: key.KeyCfg, cache_dir: Path, name: str, max_side=0, keep_src=False):
    """Decode + key a take, cached on (file mtime/size, key cfg). Returns ([Cel], src_frames or [])."""
    st = path.stat()
    h = hashlib.sha1(f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}|{cfg}|{max_side}".encode()).hexdigest()[:12]
    cp = cache_dir / f"{name}_{h}.pkl.z"                # zlib-1 pickles: ~3.5x smaller, 0.1 s to read back
    src = []
    if cp.exists():
        return pickle.loads(zlib.decompress(cp.read_bytes())), []
    cels = []
    for i, fr in enumerate(read_frames(path, max_side)):
        rgba, (x0, y0), _ = key.key_frame(fr, cfg)
        cels.append(cut.measure(cut.Cel(rgba, x0, y0, src=(name, i))))
        if keep_src and i % 15 == 0:
            src.append((i, fr))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(zlib.compress(pickle.dumps(cels), 1))
    return cels, src
