"""pixling CLI: docs/code views and the MCP client against a local fake server (no network)."""
import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from pp import cli
from pp.scenario.mcp import Client, MCPError, result_data


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, buf.getvalue()


class FakeMCP(BaseHTTPRequestHandler):
    """initialize as JSON, everything else as SSE with a progress notification first; 401 for a stale token."""
    seen = []

    def do_POST(self):
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeMCP.seen.append((self.headers.get("Authorization"), self.headers.get("Mcp-Session-Id"), msg.get("method")))
        if self.headers.get("Authorization") != "Bearer fresh":
            self.send_response(401)
            self.end_headers()
            return
        if "id" not in msg:
            self.send_response(202)
            self.end_headers()
            return
        if msg["method"] == "initialize":
            body = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18"}})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Mcp-Session-Id", "s1")
            self.end_headers()
            self.wfile.write(body.encode())
            return
        if msg["method"] == "tools/list":
            result = {"tools": [{"name": "echo", "inputSchema": {"properties": {"x": {}}}}]}
        else:
            a = msg["params"]["arguments"]
            result = {"content": [{"type": "text", "text": json.dumps(a)}], "isError": a.get("fail", False)}
        events = [{"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1, "total": 2}},
                  {"jsonrpc": "2.0", "id": msg["id"], "result": result}]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for e in events:
            self.wfile.write(("event: message\ndata: %s\n\n" % json.dumps(e)).encode())

    def log_message(self, *a):
        pass


class TestMCP(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), FakeMCP)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/mcp" % self.srv.server_port
        self.token = ["stale"]
        FakeMCP.seen = []

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def auth(self, force):
        if force:
            self.token[0] = "fresh"
        return "Bearer " + self.token[0]

    def test_refresh_session_and_sse(self):
        c = Client(self.url, self.auth, quiet=True)
        self.assertEqual([t["name"] for t in c.tools()], ["echo"])
        self.assertEqual(result_data(c.call("echo", {"x": 3})), {"x": 3})
        self.assertEqual(FakeMCP.seen[0][0], "Bearer stale")           # 401, then refreshed and retried
        self.assertTrue(all(s == "s1" for _, s, m in FakeMCP.seen[3:]))  # session id kept after initialize
        with self.assertRaises(MCPError):
            result_data(c.call("echo", {"fail": True}))


class TestViews(unittest.TestCase):
    def test_usage_and_guide(self):
        self.assertIn("pixling scenario login", run()[1])
        code, out = run("guide", "artist", "Spec format")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("## Spec format"))
        self.assertNotIn("\n## ", out[3:])                              # stops at the next section
        self.assertIn("artist", json.dumps(json.loads(run("guide", "--json")[1])))

    def test_code_styles_specs(self):
        mods = {r["module"] for r in json.loads(run("code", "--json")[1])}
        self.assertIn("pp.forge", mods)
        items = json.loads(run("code", "forge", "--json")[1])["items"]
        self.assertIn("load_spec", {i["name"] for i in items})
        styles = {r["style"] for r in json.loads(run("styles", "--json")[1])}
        self.assertIn("vista", styles)
        self.assertTrue(json.loads(run("styles", "vista", "--json")[1])["materials"])
        self.assertTrue(json.loads(run("specs", "sunmeadow", "--json")[1]))

    def test_catalogue(self):
        # pipelines, the making-of per launch style, iso styles and the kits as readable code
        names = [r["pipeline"] for r in json.loads(run("pipelines", "--json")[1])]
        self.assertEqual(names, ["spec", "blocks", "iso", "map", "fx", "video", "painted", "style"])
        self.assertIn("**Steps**", json.loads(run("pipelines", "video", "--json")[1])["text"])
        for style in ("vista", "tactics", "flat", "flat_dunes"):
            how = json.loads(run("styles", style, "--how", "--json")[1])
            self.assertTrue(how["section"].startswith("## ") and how["code"], style)
        self.assertTrue(json.loads(run("styles", "tactics", "--json")[1])["ramps"])   # exact-iso style, no materials
        self.assertIn("tactics.kit", {r["module"] for r in json.loads(run("code", "tactics", "--json")[1])})

    def test_engine_commands_route(self):
        # every engine subcommand must be reachable through `pixling` (pp/cli.py ENGINE)
        import tempfile
        import numpy as np
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "x.png"
            a = np.zeros((8, 8, 4), np.uint8)
            a[2:6, 2:6] = (200, 100, 50, 255)
            Image.fromarray(a).save(png)
            code, _ = run("pixcheck", str(png))
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()


class TestWorkflow(unittest.TestCase):
    def test_new_and_agent_install(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                self.assertEqual(run("new", "fox", "my_fox")[0], 0)
                spec = json.loads(Path("specs/my_fox.json").read_text())
                self.assertEqual(spec["name"], "my_fox")
                with self.assertRaises(SystemExit):                     # never overwrites without --force
                    run("new", "fox", "my_fox")
                run("agent", "install", ".")
                run("agent", "install", ".")                           # idempotent: one block, not two
                self.assertEqual(Path("AGENTS.md").read_text().count("<!-- pixling -->"), 1)
                self.assertTrue(os.path.exists(".claude/skills/pixling/SKILL.md"))
            finally:
                os.chdir(cwd)


class TestScenarioRun(unittest.TestCase):
    """scenario.run against the real response shapes (model_run, then jobs_wait rows), with the network stubbed."""

    def test_wait_then_download(self):
        from pp import scenario as S
        calls = []

        def fake_call(name, args=None, **kw):
            calls.append(name)
            if name == "model_run":
                return {"model_id": "m", "job_id": "job_1", "status": "in_progress"}
            if name == "jobs_wait":
                if calls.count("jobs_wait") == 1:
                    return {"status": "in_progress", "jobs": [{"jobId": "job_1", "status": "processing"}],
                            "pending_job_ids": ["job_1"]}
                return {"status": "completed", "jobs": [{"jobId": "job_1", "status": "success",
                                                          "assetIds": ["asset_a", "asset_b"], "cuCost": 7}]}
            raise AssertionError(name)

        class FakeClient:
            def close(self):
                pass

        saved = []
        orig = S.call, S.client, S.download
        S.call, S.client = fake_call, lambda *a, **k: FakeClient()
        S.download = lambda a, out, fmt=None, c=None: saved.append((a, str(out))) or out
        try:
            paths, cu = S.run("m", {"prompt": "x"}, "takes/t.mp4")
        finally:
            S.call, S.client, S.download = orig
        self.assertEqual(cu, 7)
        self.assertEqual(saved, [("asset_a", "takes/t_0.mp4"), ("asset_b", "takes/t_1.mp4")])
        self.assertEqual(calls, ["model_run", "jobs_wait", "jobs_wait"])


class TestBrand(unittest.TestCase):
    def test_banner_quiet_when_piped(self):
        from pp.brand import terminal_banner
        self.assertEqual(terminal_banner(io.StringIO()), "")

    def test_mascot_frames(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        from brand_mark import idle_frames, mark
        from pp.brand import LOGO
        pal = {tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for v in LOGO.values()}
        frames = idle_frames()
        self.assertTrue(all(f.size == mark().size for f in frames))          # one canvas: nothing jumps
        for f in frames:
            self.assertTrue({p[:3] for p in f.getdata() if p[3]} <= pal)      # only brand colours
