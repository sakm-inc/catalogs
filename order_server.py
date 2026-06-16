from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote, urlparse
import json
import os
import time
from pathlib import Path

orders = []
bills = {}
sales = []
ADMIN_PASSWORD = "1234"
MENU_FILE = Path(__file__).parent / "restaurant-menu-photo" / "menu.json"


def load_menu():
    if not MENU_FILE.exists():
        return []
    return json.loads(MENU_FILE.read_text(encoding="utf-8"))


def save_menu(items):
    MENU_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def has_admin_password(value):
    return value == ADMIN_PASSWORD


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
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query
        if path == "/api/orders":
            self.api_json(orders)
            return
        if path == "/api/bills":
            self.api_json(list(bills.values()))
            return
        if path == "/api/menu":
            self.api_json(load_menu())
            return
        if path == "/api/sales":
            params = dict(pair.split("=", 1) for pair in query.split("&") if "=" in pair)
            if not has_admin_password(params.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            by_date = {}
            for sale in sales:
                date = sale.get("date", "")
                row = by_date.setdefault(date, {"date": date, "total": 0, "count": 0})
                row["total"] += sale["total"]
                row["count"] += 1
            today = time.strftime("%Y-%m-%d")
            self.api_json({
                "total": sum(item["total"] for item in sales),
                "todayTotal": by_date.get(today, {}).get("total", 0),
                "todayCount": by_date.get(today, {}).get("count", 0),
                "count": len(sales),
                "byDate": sorted(by_date.values(), key=lambda item: item["date"], reverse=True),
                "sales": sales,
            })
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/orders":
            data = self.read_body()
            order = {
                "id": int(time.time() * 1000),
                "type": str(data.get("type", "order")).strip() or "order",
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
        if path == "/api/menu":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            items = load_menu()
            item = {
                "id": str(int(time.time() * 1000)),
                "category": str(data.get("category", "")).strip(),
                "name": str(data.get("name", "")).strip(),
                "price": float(data.get("price", 0)),
                "desc": str(data.get("desc", "")).strip(),
                "img": str(data.get("img", "")).strip(),
                "active": bool(data.get("active", True)),
            }
            items.append(item)
            save_menu(items)
            self.api_json(item, 201)
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
                    if status == "Tamamlandı" and order.get("type") != "waiter_call" and not order.get("billed"):
                        table = str(order["table"])
                        billed_at = time.strftime("%d.%m.%Y %H:%M")
                        bill = bills.setdefault(table, {
                            "table": table,
                            "total": 0,
                            "items": [],
                            "orders": [],
                            "firstTime": order["time"],
                            "lastTime": order["time"],
                        })
                        bill["total"] += order["total"]
                        bill["items"].extend(order["items"])
                        bill["lastTime"] = order["time"]
                        bill["orders"].append({
                            "id": order["id"],
                            "time": order["time"],
                            "completedAt": billed_at,
                            "total": order["total"],
                        })
                        sales.insert(0, {
                            "id": order["id"],
                            "table": table,
                            "items": order["items"],
                            "total": order["total"],
                            "time": billed_at,
                            "date": time.strftime("%Y-%m-%d"),
                        })
                        order["billed"] = True
                    self.api_json(order)
                    return
        if path.startswith("/api/menu/"):
            item_id = unquote(path.rsplit("/", 1)[-1])
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            items = load_menu()
            for item in items:
                if str(item["id"]) == item_id:
                    for key in ("category", "name", "desc", "img"):
                        if key in data:
                            item[key] = str(data.get(key, "")).strip()
                    if "price" in data:
                        item["price"] = float(data.get("price") or 0)
                    if "active" in data:
                        item["active"] = bool(data.get("active"))
                    save_menu(items)
                    self.api_json(item)
                    return
        self.api_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/bills/"):
            table = unquote(path.rsplit("/", 1)[-1])
            bills.pop(table, None)
            self.api_json({"ok": True})
            return
        if path.startswith("/api/menu/"):
            parsed = urlparse(self.path)
            params = dict(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair)
            if not has_admin_password(params.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            item_id = unquote(path.rsplit("/", 1)[-1])
            items = [item for item in load_menu() if str(item["id"]) != item_id]
            save_menu(items)
            self.api_json({"ok": True})
            return
        if path == "/api/orders":
            orders.clear()
            bills.clear()
            self.api_json({"ok": True})
            return
        self.api_json({"error": "not found"}, 404)


port = int(os.environ.get("PORT", "8125"))
ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
