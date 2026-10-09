"""Scenario (AI image/video/3D generation) through its hosted MCP server, from the shell.

The agent host doesn't need an MCP connection: `pixling scenario ...` signs in with OAuth (auth.py), speaks MCP
(mcp.py) and adds the jobs the reel engine needs: run a model and download its outputs, upload a file.

  from pp import scenario
  scenario.call("models_list", {"query": "minimax"})
  paths, cost = scenario.run("model_minimax-h3", {"prompt": "...", "image": asset_id}, "takes/attack_s_a.mp4")
"""
from __future__ import annotations

import base64
import json
import mimetypes
import time
import urllib.request
from pathlib import Path

from . import auth
from .mcp import Client, MCPError, result_data

__all__ = ["call", "tools", "run", "upload", "download", "cost", "client", "MCPError"]

_TOOLS_TTL = 24 * 3600


def client(full=False, quiet=False) -> Client:
    url = auth.load().get("server") or auth.SERVER
    if full:
        url += ("&" if "?" in url else "?") + "toolsets=full"
    return Client(url, lambda force: auth.header(force), quiet=quiet)


def tools(full=False, fresh=False) -> list:
    """The server's tool list (name, description, inputSchema), cached for a day."""
    cache = auth.config_dir() / ("tools_full.json" if full else "tools.json")
    if not fresh and cache.exists() and time.time() - cache.stat().st_mtime < _TOOLS_TTL:
        return json.loads(cache.read_text())
    c = client(full, quiet=True)
    out = c.tools()
    c.close()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def _scoped(name, args, full):
    """OAuth callers must name a team and project; add the saved ones where the tool takes them."""
    if auth.mode() != "oauth":
        return args
    st = auth.load()
    schema = next((t.get("inputSchema", {}) for t in tools(full) if t["name"] == name), None)
    if schema is None and not full:
        schema = next((t.get("inputSchema", {}) for t in tools(True) if t["name"] == name), {})
    props = (schema or {}).get("properties", {})
    for k in ("team_id", "project_id"):
        if k in props and k not in args and st.get(k):
            args = {**args, k: st[k]}
    return args


def call(name, args=None, full=False, raw=False, quiet=False, c=None):
    """Call one MCP tool; returns its parsed payload (or the raw MCP result with raw=True)."""
    own = c is None
    c = c or client(full, quiet)
    try:
        res = c.call(name, _scoped(name, dict(args or {}), full))
    finally:
        if own:
            c.close()
    return res if raw else result_data(res)


def _urls(x):
    """Every http(s) URL in a nested payload, in order."""
    if isinstance(x, str):
        return [x] if x.startswith(("http://", "https://")) else []
    if isinstance(x, dict):
        return [u for v in x.values() for u in _urls(v)]
    if isinstance(x, list):
        return [u for v in x for u in _urls(v)]
    return []


def _find(x, *keys):
    """First value under any of these keys, anywhere in a nested payload."""
    if isinstance(x, dict):
        for k in keys:
            if x.get(k) not in (None, "", []):
                return x[k]
        for v in x.values():
            f = _find(v, *keys)
            if f is not None:
                return f
    if isinstance(x, list):
        for v in x:
            f = _find(v, *keys)
            if f is not None:
                return f
    return None


def _asset_ids(x):
    ids = _find(x, "assetIds", "asset_ids")
    if ids:
        return list(ids)
    outs = _find(x, "outputs", "assets") or []
    return [o.get("id") or o.get("asset_id") for o in outs if isinstance(o, dict)]


def download(asset_id, out, fmt=None, c=None) -> Path:
    args = {"asset_id": asset_id}
    if fmt:
        args["format"] = fmt
    r = call("asset_download", args, quiet=True, c=c)
    url = _find(r, "download_url", "downloadUrl", "url") or (_urls(r) or [None])[0]
    if not url:
        raise MCPError(f"no download url for {asset_id}: {r}")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=600) as src, open(out, "wb") as dst:
        while True:
            b = src.read(1 << 20)
            if not b:
                break
            dst.write(b)
    return out


def cost(model, params):
    return call("model_run", {"model_id": model, "parameters": params, "dry_run": True}, quiet=True)


FAILED = ("failed", "failure", "canceled", "error")


def run(model, params, out=None, wait=True):
    """Generate with one model, wait for the job, download every output next to `out` (name_0, name_1 when several).
    Returns (paths or asset ids, creative units spent). With wait=False: ({"job_id", "status"}, None) at once."""
    c = client()
    try:
        r = call("model_run", {"model_id": model, "parameters": params, "wait": wait}, c=c)
        job, ids = _find(r, "job_id", "jobId"), _asset_ids(r)
        status, cu = str(_find(r, "status") or ""), _find(r, "cuCost", "creativeUnitsCost")
        if not wait:
            return {"job_id": job, "status": status}, None
        while job and not ids and status not in FAILED:
            w = call("jobs_wait", {"job_ids": [job]}, c=c)      # blocks ~180 s server-side per call
            row = next(iter(w.get("jobs") or []), {})
            ids, status, cu = _asset_ids(row), str(row.get("status", "")), row.get("cuCost", cu)
            if w.get("status") == "completed":
                break
        if not ids:
            raise MCPError(f"job {job} ended '{status}' with no outputs: {json.dumps(r)[:600]}")
        if out is None:
            return ids, cu
        p = Path(out)
        paths = [download(a, p if len(ids) == 1 else p.with_name(f"{p.stem}_{i}{p.suffix}"), c=c)
                 for i, a in enumerate(ids)]
        return paths, cu
    finally:
        c.close()


def upload(path) -> str:
    """Local file -> Scenario asset id (inline under 100 KB, else presigned multipart PUTs)."""
    path = Path(path)
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    kind = {"image": "image", "video": "video", "audio": "audio"}.get(ctype.split("/")[0], "3d")
    size = path.stat().st_size
    base = {"file_name": path.name, "content_type": ctype, "kind": kind}
    c = client()
    try:
        if size < 100_000:
            r = call("upload_asset", {**base, "data": base64.b64encode(path.read_bytes()).decode()}, c=c)
        else:
            r = call("upload_asset", {**base, "file_size": size}, c=c)
            parts = _find(r, "parts", "upload_urls", "urls") or []
            uid = _find(r, "upload_id", "uploadId")
            with open(path, "rb") as f:
                n = max(1, len(parts))
                chunk = _find(r, "part_size", "partSize") or -(-size // n)
                for part in parts:
                    url = part if isinstance(part, str) else (_urls(part) or [None])[0]
                    req = urllib.request.Request(url, data=f.read(int(chunk)), method="PUT")
                    urllib.request.urlopen(req, timeout=600).close()
            r = call("upload_asset_complete", {"upload_id": uid}, c=c)
        aid = _find(r, "asset_id", "assetId")
        if not aid:
            raise MCPError(f"upload did not return an asset id: {json.dumps(r)[:600]}")
        return aid
    finally:
        c.close()
