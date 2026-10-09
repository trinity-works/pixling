"""A small MCP client over Streamable HTTP (JSON-RPC POSTs; replies come as JSON or an SSE stream).

Stdlib only, because the official SDK needs Python 3.10+. Enough for tools: initialize, tools/list, tools/call.
Progress notifications go to stderr so stdout stays a clean result.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

PROTOCOL = "2025-06-18"


class MCPError(RuntimeError):
    pass


class Client:
    def __init__(self, url, auth, name="pixling", version="0.1", quiet=False):
        self.url, self.auth, self.quiet = url, auth, quiet       # auth(force_refresh: bool) -> header value
        self.session, self._id, self.info = None, 0, None
        self.client_info = {"name": name, "version": version}

    # -- transport ---------------------------------------------------------------------------------------------
    def _send(self, msg, retry=True):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": self.auth(False)}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if self.info:
            headers["MCP-Protocol-Version"] = self.info.get("protocolVersion", PROTOCOL)
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), headers=headers, method="POST")
        try:
            r = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry:
                self.auth(True)
                return self._send(msg, retry=False)
            raise MCPError("HTTP %d: %s" % (e.code, e.read()[:500].decode("utf-8", "replace")))
        with r:
            self.session = r.headers.get("Mcp-Session-Id") or self.session
            if "id" not in msg:
                return None
            if r.headers.get("Content-Type", "").startswith("text/event-stream"):
                return self._read_sse(r, msg["id"])
            body = r.read()
            return self._reply(json.loads(body), msg["id"]) if body else None

    def _read_sse(self, r, want):
        data = []
        for raw in r:
            line = raw.decode("utf-8").rstrip("\r\n")
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line and data:
                out = self._reply(json.loads("\n".join(data)), want)
                data = []
                if out is not None:
                    return out
        raise MCPError("stream ended without a reply")

    def _reply(self, m, want):
        for one in (m if isinstance(m, list) else [m]):
            if one.get("id") == want:
                if "error" in one:
                    raise MCPError(json.dumps(one["error"]))
                return one.get("result")
            if one.get("method") == "notifications/progress" and not self.quiet:
                p = one.get("params", {})
                pct = "%s/%s" % (p.get("progress"), p.get("total")) if p.get("total") else p.get("progress")
                print("  ... %s %s" % (pct, p.get("message", "")), file=sys.stderr, flush=True)
        return None

    def request(self, method, params=None):
        if self.info is None and method != "initialize":
            self.initialize()
        self._id += 1
        return self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})

    # -- protocol ----------------------------------------------------------------------------------------------
    def initialize(self):
        self.info = {}
        self.info = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                                "clientInfo": self.client_info}) or {}
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self.info

    def tools(self):
        out, cursor = [], None
        while True:
            r = self.request("tools/list", {"cursor": cursor} if cursor else {})
            out += r.get("tools", [])
            cursor = r.get("nextCursor")
            if not cursor:
                return out

    def call(self, name, args=None, progress=True):
        params = {"name": name, "arguments": args or {}}
        if progress:
            params["_meta"] = {"progressToken": "pixling-%d" % (self._id + 1)}
        return self.request("tools/call", params)

    def close(self):
        if not self.session:
            return
        req = urllib.request.Request(self.url, method="DELETE", headers={
            "Mcp-Session-Id": self.session, "Authorization": self.auth(False)})
        try:
            urllib.request.urlopen(req, timeout=10).close()
        except (urllib.error.URLError, OSError):
            pass


def result_data(res):
    """A tools/call result -> the structured payload (parsed JSON text when the tool returns JSON as text)."""
    if res is None:
        return None
    if res.get("structuredContent") is not None:
        data = res["structuredContent"]
    else:
        texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        joined = "\n".join(texts)
        try:
            data = json.loads(joined)
        except ValueError:
            data = joined
    if res.get("isError"):
        raise MCPError(data if isinstance(data, str) else json.dumps(data))
    return data
