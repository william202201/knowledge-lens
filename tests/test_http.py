import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.process = subprocess.Popen([sys.executable, "-m", "knowledge_lens", "--db", str(Path(cls.temp.name)/"demo.sqlite3"), "serve", "--port", str(cls.port)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                if cls.request("GET", "/api/status")[0] == 200:
                    return
            except OSError:
                pass
            if cls.process.poll() is not None:
                raise RuntimeError(cls.process.stderr.read().decode())
            time.sleep(0.05)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        raise RuntimeError("Server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.process.stderr.close()
        cls.temp.cleanup()

    @classmethod
    def request(cls, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_assets_and_unknown_route(self):
        status, body, headers = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'lang="zh-CN"', body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request("GET", "/missing")[0], 404)

    def test_cross_origin_and_invalid_host_rejected(self):
        self.assertEqual(self.request("POST", "/api/run", "{}", {"Origin":"https://evil.example", "Content-Type":"application/json"})[0], 403)
        self.assertEqual(self.request("GET", "/api/status", headers={"Host":"evil.example"})[0], 403)

    def test_content_type_and_request_size(self):
        self.assertEqual(self.request("POST", "/api/run", "{}")[0], 415)
        self.assertEqual(self.request("POST", "/api/run", "x"*17000, {"Content-Type":"application/json"})[0], 413)

    def test_bad_json_rejected(self):
        for body in ["[1]", "{broken", "null"]:
            self.assertEqual(self.request("POST", "/api/run", body, {"Content-Type":"application/json"})[0], 400)

    def test_offline_workflow(self):
        status, body, _ = self.request("POST", "/api/ask", json.dumps({"question":"API Key"}), {"Content-Type":"application/json"})
        self.assertEqual(status, 200)
        answer = json.loads(body)
        self.assertEqual(answer["mode"], "offline")
        self.assertTrue(answer["citation_ids"])
