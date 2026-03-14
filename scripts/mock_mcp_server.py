#!/usr/bin/env python3
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/mcp/tools/call":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "invalid json"}).encode("utf-8"))
            return

        tool_name = request.get("params", {}).get("name") or "unknown_tool"
        response = {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "content": [{"type": "text", "text": f"mock-mcp executed {tool_name}"}],
                "isError": False,
            },
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 7071), Handler)
    print("mock-mcp listening on :7071", flush=True)
    server.serve_forever()
