from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote, urlparse
import json
import time

orders = []
bills = {}


class Handler(SimpleHTTPRequestHandler):
    def api_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self):
        self.api_json({"ok": True})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/orders":
            self.api_json(orders)
            return
        if path == "/api/bills":
            self.api_json(list(bills.values()))
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/orders":
            data = self.read_body()
            order = {
                "id": int(time.time() * 1000),
                "table": str(data.get("table", "")).strip(),
                "items": data.get("items", []),
                "total": data.get("total", 0),
                "status": "Yeni",
                "time": time.strftime("%d.%m.%Y %H:%M"),
                "billed": False,
            }
            orders.insert(0, order)
            self.api_json(order, 201)
            return
        self.api_json({"error": "not found"}, 404)

    def do_PATCH(self):
        path = urlparse(self.path).path
        if path.startswith("/api/orders/"):
            order_id = int(path.rsplit("/", 1)[-1])
            data = self.read_body()
            for order in orders:
                if order["id"] == order_id:
                    status = data.get("status", order["status"])
                    order["status"] = status
                    if status == "Tamamlandı" and not order.get("billed"):
                        table = str(order["table"])
                        bill = bills.setdefault(table, {"table": table, "total": 0, "items": []})
                        bill["total"] += order["total"]
                        bill["items"].extend(order["items"])
                        order["billed"] = True
                    self.api_json(order)
                    return
        self.api_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/bills/"):
            table = unquote(path.rsplit("/", 1)[-1])
            bills.pop(table, None)
            self.api_json({"ok": True})
            return
        if path == "/api/orders":
            orders.clear()
            bills.clear()
            self.api_json({"ok": True})
            return
        self.api_json({"error": "not found"}, 404)


ThreadingHTTPServer(("127.0.0.1", 8125), Handler).serve_forever()
