"""Scenario credentials: OAuth for the hosted MCP server, or an API key pair for headless runs.

OAuth is the MCP authorization flow (the same one Claude Code runs): protected-resource metadata -> authorization
server metadata -> dynamic client registration -> PKCE code via a loopback redirect, or the device-code grant when
there is no browser on this machine. Tokens live in ~/.config/pixling/scenario.json (mode 600) and refresh
themselves. SCENARIO_API_KEY + SCENARIO_API_SECRET (environment or the repo's .env) override OAuth.
"""
from __future__ import annotations

import base64
import hashlib
import html
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

SERVER = os.environ.get("SCENARIO_MCP_URL", "https://mcp.scenario.com/mcp")
ROOT = Path(__file__).resolve().parent.parent.parent
PORT = 33418                      # fixed loopback port, so the registered redirect URI stays valid
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


def config_dir() -> Path:
    base = os.environ.get("PIXLING_CONFIG") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "pixling")
    return Path(base)


def _store_path() -> Path:
    return config_dir() / "scenario.json"


def load() -> dict:
    p = _store_path()
    return json.loads(p.read_text()) if p.exists() else {}


def save(d: dict):
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f, indent=1)


def env(name):
    """SCENARIO_* or VITE_SCENARIO_* from the environment, else from a gitignored .env at the repo root."""
    for n in (name, "VITE_" + name):
        if os.environ.get(n):
            return os.environ[n]
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() in (name, "VITE_" + name):
                return v.strip().strip('"')
    return None


def api_key_header():
    k, s = env("SCENARIO_API_KEY"), env("SCENARIO_API_SECRET")
    return "Basic " + base64.b64encode(f"{k}:{s}".encode()).decode() if k and s else None


# ---- HTTP helpers -------------------------------------------------------------------------------------------

def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _post(url, data: dict, form=True):
    body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    ctype = "application/x-www-form-urlencoded" if form else "application/json"
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": ctype, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return {"_status": e.code, **json.loads(e.read() or b"{}")}
        except ValueError:
            return {"_status": e.code, "error": "http_%d" % e.code}


def discover(server=SERVER) -> dict:
    """RFC 9728 resource metadata -> RFC 8414 authorization server metadata."""
    u = urllib.parse.urlparse(server)
    origin = f"{u.scheme}://{u.netloc}"
    res = None
    for path in (f"/.well-known/oauth-protected-resource{u.path}", "/.well-known/oauth-protected-resource"):
        try:
            res = _get_json(origin + path)
            break
        except (urllib.error.URLError, ValueError):
            continue
    issuer = (res or {}).get("authorization_servers", [origin])[0].rstrip("/")
    for path in ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
        try:
            meta = _get_json(issuer + path)
            meta["resource"] = (res or {}).get("resource", server)
            meta["scopes_supported"] = (res or {}).get("scopes_supported") or meta.get("scopes_supported")
            return meta
        except (urllib.error.URLError, ValueError):
            continue
    raise SystemExit(f"no OAuth metadata at {issuer}")


def _register(meta, redirect):
    """RFC 7591 dynamic registration of a public client (no secret; PKCE protects the code)."""
    body = {"client_name": "Pixel Perfect CLI (pixling)", "redirect_uris": [redirect],
            "grant_types": ["authorization_code", "refresh_token", DEVICE_GRANT],
            "response_types": ["code"], "token_endpoint_auth_method": "none"}
    r = _post(meta["registration_endpoint"], body, form=False)
    if "client_id" not in r:                           # some servers refuse the device grant at registration
        body["grant_types"] = ["authorization_code", "refresh_token"]
        r = _post(meta["registration_endpoint"], body, form=False)
    if "client_id" not in r:
        raise SystemExit(f"client registration failed: {r}")
    return r


def _client(store, meta, redirect):
    c = store.get("client")
    if not c or c.get("redirect_uri") != redirect or c.get("issuer") != meta["issuer"]:
        r = _register(meta, redirect)
        c = {"client_id": r["client_id"], "redirect_uri": redirect, "issuer": meta["issuer"],
             "grant_types": r.get("grant_types", [])}
        store["client"] = c
        save(store)
    return c


def _keep(store, tok):
    if "access_token" not in tok:
        raise SystemExit(f"token request failed: {tok}")
    old = store.get("tokens", {})
    store["tokens"] = {"access_token": tok["access_token"],
                       "refresh_token": tok.get("refresh_token") or old.get("refresh_token"),
                       "expires_at": time.time() + float(tok.get("expires_in", 3600)),
                       "scope": tok.get("scope")}
    save(store)


# ---- login flows ----------------------------------------------------------------------------------------------

def login(device=False, browser=True, scope=None, server=SERVER, out=sys.stderr):
    meta = discover(server)
    store = load()
    store["server"] = server
    store["meta"] = {k: meta.get(k) for k in ("issuer", "token_endpoint", "authorization_endpoint",
                                               "device_authorization_endpoint", "revocation_endpoint", "resource")}
    redirect = f"http://127.0.0.1:{PORT}/callback"
    c = _client(store, meta, redirect)
    scope = scope or " ".join(meta.get("scopes_supported") or [])
    if device:
        _login_device(store, meta, c, scope, out)
    else:
        _login_browser(store, meta, c, scope, browser, out)
    return store


def _login_browser(store, meta, c, scope, browser, out):
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    q = {"response_type": "code", "client_id": c["client_id"], "redirect_uri": c["redirect_uri"],
         "code_challenge": challenge, "code_challenge_method": "S256", "state": state, "resource": meta["resource"]}
    if scope:
        q["scope"] = scope
    url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(q)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            if p.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            got.update({k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()})
            ok = "code" in got and got.get("state") == state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Signed in to Scenario. You can close this tab." if ok else "Sign-in failed: %s" % html.escape(
                got.get("error_description", got.get("error", "state mismatch")))
            self.wfile.write(f"<html><body style='font:16px system-ui;padding:3em'>{msg}</body></html>".encode())
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        raise SystemExit(f"port {PORT} is busy; free it or use `pixling scenario login --device`")
    print(f"Open this URL to sign in to Scenario:\n  {url}\n", file=out)
    if browser:
        webbrowser.open(url)
    t = threading.Timer(300, srv.shutdown)
    t.start()
    srv.serve_forever()
    t.cancel()
    srv.server_close()
    if got.get("state") != state or "code" not in got:
        raise SystemExit("sign-in failed or timed out: %s" % (got.get("error_description") or got.get("error") or "no code"))
    _keep(store, _post(meta["token_endpoint"], {
        "grant_type": "authorization_code", "code": got["code"], "redirect_uri": c["redirect_uri"],
        "client_id": c["client_id"], "code_verifier": verifier, "resource": meta["resource"]}))


def _login_device(store, meta, c, scope, out):
    ep = meta.get("device_authorization_endpoint")
    if not ep:
        raise SystemExit("this server has no device-code grant; run `pixling scenario login` in a terminal with a browser")
    d = {"client_id": c["client_id"], "resource": meta["resource"]}
    if scope:
        d["scope"] = scope
    r = _post(ep, d)
    if "device_code" not in r:
        raise SystemExit(f"device authorization failed: {r}")
    link = r.get("verification_uri_complete") or r["verification_uri"]
    print(f"Open {link}\nand confirm the code: {r['user_code']}\n(waiting up to {r.get('expires_in', 600)} s)",
          file=out, flush=True)
    every, end = float(r.get("interval", 5)), time.time() + float(r.get("expires_in", 600))
    while time.time() < end:
        time.sleep(every)
        tok = _post(meta["token_endpoint"], {"grant_type": DEVICE_GRANT, "device_code": r["device_code"],
                                             "client_id": c["client_id"], "resource": meta["resource"]})
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            every += 5
            continue
        _keep(store, tok)
        return
    raise SystemExit("device code expired")


def logout():
    store = load()
    tok, meta = store.get("tokens", {}), store.get("meta", {})
    if tok.get("refresh_token") and meta.get("revocation_endpoint"):
        _post(meta["revocation_endpoint"], {"token": tok["refresh_token"], "token_type_hint": "refresh_token",
                                            "client_id": store.get("client", {}).get("client_id", "")})
    store.pop("tokens", None)
    save(store)


def refresh(store) -> bool:
    tok, meta = store.get("tokens", {}), store.get("meta", {})
    if not tok.get("refresh_token"):
        return False
    r = _post(meta["token_endpoint"], {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                       "client_id": store["client"]["client_id"], "resource": meta.get("resource")})
    if "access_token" not in r:
        return False
    _keep(store, r)
    return True


def header(force_refresh=False):
    """Authorization header value, or SystemExit with the next step."""
    key = api_key_header()
    if key:
        return key
    store = load()
    tok = store.get("tokens")
    if not tok:
        raise SystemExit("not signed in to Scenario: run `pixling scenario login` (or `--device` without a browser)")
    if force_refresh or tok["expires_at"] - 60 < time.time():
        if not refresh(store):
            raise SystemExit("Scenario session expired: run `pixling scenario login`")
    return "Bearer " + store["tokens"]["access_token"]


def mode() -> str:
    return "api-key" if api_key_header() else ("oauth" if load().get("tokens") else "none")
