"""Loopback-only development server with JSON bounds and origin checks."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse


def serve(port, dispatch):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Prompts and credentials do not belong in access logs.

        def send(self, code, payload, content_type="application/json; charset=utf-8"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def handle_request(self, method):
            allowed = {f"localhost:{port}", f"127.0.0.1:{port}"}
            if self.headers.get("Host") not in allowed:
                return self.send(403, {"error": "Invalid Host"})
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{host}" for host in allowed}:
                return self.send(403, {"error": "Cross-origin request refused"})
            path = urlparse(self.path).path
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
            if method == "GET" and path in assets:
                name, kind = assets[path]
                return self.send(200, (Path(__file__).parent / "static" / name).read_bytes(), kind)
            data = {}
            try:
                if method == "POST":
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                        return self.send(415, {"error": "Expected application/json"})
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 16384:
                        return self.send(413, {"error": "Request body must contain 1–16384 bytes"})
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError("Expected a JSON object")
                result = dispatch(method, self.path, data)
                self.send(200, result)
            except LookupError:
                self.send(404, {"error": "Unknown endpoint"})
            except (ValueError, TypeError, UnicodeError) as error:
                code = 409 if error.__class__.__name__ == "ConflictError" else 400
                self.send(code, {"error": str(error)})
            except RuntimeError as error:
                self.send(502, {"error": str(error)})
            except Exception:
                self.send(500, {"error": "Internal error; inspect server locally"})

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Open http://127.0.0.1:{port} (local demo server)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
