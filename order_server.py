from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen
from html import unescape as html_unescape
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

orders = []
bills = {}
ADMIN_PASSWORD = "1234"
MENU_FILE = Path(__file__).parent / "restaurant-menu-photo" / "menu.json"
SALES_FILE = Path(__file__).parent / "sales.json"
INVENTORY_DIR = Path(__file__).parent / "inventory-system"
INVENTORY_PRODUCTS_FILE = INVENTORY_DIR / "products.json"
INVENTORY_SALES_FILE = INVENTORY_DIR / "sales.json"
INVENTORY_RECEIPTS_FILE = INVENTORY_DIR / "receipts.json"
INVENTORY_RETURNS_FILE = INVENTORY_DIR / "returns.json"
INVENTORY_EMPLOYEES_FILE = INVENTORY_DIR / "employees.json"
INVENTORY_ATTENDANCE_FILE = INVENTORY_DIR / "attendance.json"
BAGCATAP_DIR = Path(__file__).parent / "bagcatap"
BAGCATAP_FILE = BAGCATAP_DIR / "kindergartens.json"
BAGCATAP_NOTIFICATIONS_FILE = BAGCATAP_DIR / "notifications.json"
BAGCATAP_DEVICE_TOKENS_FILE = BAGCATAP_DIR / "device_tokens.json"
BAGCATAP_USERS_FILE = BAGCATAP_DIR / "users.json"
BAGCATAP_RESET_CODES_FILE = BAGCATAP_DIR / "reset_codes.json"
BAGCATAP_STATS_FILE = BAGCATAP_DIR / "stats.json"
BAGCATAP_UPLOADS_DIR = BAGCATAP_DIR / "uploads"
KNOWN_BARCODE_LOOKUPS = {
    "6262004910332": {
        "name": "Kalleh tomat ketçupu 330 qr",
        "category": "Souslar",
        "alternatives": ["Ketchup Kalleh tomato 330g", "Кетчуп томатный ПЭТ 330гр ТМ Kalleh"],
    },
    "4033100024351": {
        "name": "Sobranie Less Smoke Smell Göy 20 ədəd",
        "category": "Siqaret",
        "alternatives": ["Sobranie KSSS Blue", "SOBRANIE LESS SMOKE SMELL GOY 20ED"],
    },
}


def load_menu():
    if not MENU_FILE.exists():
        return []
    return json.loads(MENU_FILE.read_text(encoding="utf-8"))


def save_menu(items):
    MENU_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sales():
    if not SALES_FILE.exists():
        return []
    try:
        return json.loads(SALES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_sales(items):
    SALES_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


sales = load_sales()


def now_display():
    return time.strftime("%d.%m.%Y %H:%M")


def today_iso():
    return time.strftime("%Y-%m-%d")


def load_json_file(path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def save_json_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def seed_inventory_products():
    return [
        {
            "id": "inv-1001",
            "barcode": "100000000001",
            "name": "Coca-Cola 500 ml",
            "category": "İçkilər",
            "color": "",
            "size": "500 ml",
            "quantity": 48,
            "costPrice": 0.75,
            "salePrice": 1.2,
            "minStock": 12,
            "image": "",
            "createdAt": now_display(),
            "updatedAt": now_display(),
            "active": True,
        },
        {
            "id": "inv-1002",
            "barcode": "100000000002",
            "name": "Su 500 ml",
            "category": "İçkilər",
            "color": "",
            "size": "500 ml",
            "quantity": 80,
            "costPrice": 0.25,
            "salePrice": 0.5,
            "minStock": 20,
            "image": "",
            "createdAt": now_display(),
            "updatedAt": now_display(),
            "active": True,
        },
        {
            "id": "inv-1003",
            "barcode": "100000000003",
            "name": "USB Type-C kabel",
            "category": "Aksesuar",
            "color": "Ağ",
            "size": "1 metr",
            "quantity": 25,
            "costPrice": 3,
            "salePrice": 7,
            "minStock": 5,
            "image": "",
            "createdAt": now_display(),
            "updatedAt": now_display(),
            "active": True,
        },
    ]


def load_inventory_products():
    products = load_json_file(INVENTORY_PRODUCTS_FILE, None)
    if products is None:
        products = seed_inventory_products()
        save_json_file(INVENTORY_PRODUCTS_FILE, products)
    return products


def save_inventory_products(products):
    save_json_file(INVENTORY_PRODUCTS_FILE, products)


def load_inventory_sales():
    return load_json_file(INVENTORY_SALES_FILE, [])


def save_inventory_sales(items):
    save_json_file(INVENTORY_SALES_FILE, items)


def load_inventory_receipts():
    return load_json_file(INVENTORY_RECEIPTS_FILE, [])


def save_inventory_receipts(items):
    save_json_file(INVENTORY_RECEIPTS_FILE, items)


def load_inventory_returns():
    return load_json_file(INVENTORY_RETURNS_FILE, [])


def save_inventory_returns(items):
    save_json_file(INVENTORY_RETURNS_FILE, items)


def load_inventory_employees():
    employees = load_json_file(INVENTORY_EMPLOYEES_FILE, [])
    return employees if isinstance(employees, list) else []


def save_inventory_employees(employees):
    save_json_file(INVENTORY_EMPLOYEES_FILE, employees)


def load_inventory_attendance():
    logs = load_json_file(INVENTORY_ATTENDANCE_FILE, [])
    return logs if isinstance(logs, list) else []


def save_inventory_attendance(logs):
    save_json_file(INVENTORY_ATTENDANCE_FILE, logs)


def public_employee(employee, include_descriptor=False):
    item = {
        "id": employee.get("id", ""),
        "name": employee.get("name", ""),
        "active": bool(employee.get("active", True)),
        "registeredAt": employee.get("registeredAt", ""),
        "image": employee.get("image", ""),
    }
    if include_descriptor:
        item["descriptor"] = employee.get("descriptor", [])
    return item


def create_inventory_attendance_record(employee_id, action="auto", score=0):
    employee_id = str(employee_id or "").strip()
    employees = load_inventory_employees()
    employee = next((item for item in employees if str(item.get("id", "")) == employee_id and item.get("active", True)), None)
    if not employee:
        return None
    logs = load_inventory_attendance()
    last = next((item for item in logs if str(item.get("employeeId", "")) == employee_id), None)
    action = str(action or "auto").strip()
    if action not in ("in", "out"):
        action = "out" if last and last.get("action") == "in" else "in"
    record = {
        "id": str(int(time.time() * 1000)),
        "employeeId": employee_id,
        "employeeName": employee.get("name", ""),
        "action": action,
        "date": today_iso(),
        "time": now_display(),
        "score": float(score or 0),
    }
    logs.insert(0, record)
    save_inventory_attendance(logs)
    return record


def public_inventory_product(product):
    return {
        "id": product.get("id"),
        "barcode": product.get("barcode", ""),
        "name": product.get("name", ""),
        "category": product.get("category", ""),
        "color": product.get("color", ""),
        "size": product.get("size", ""),
        "quantity": product.get("quantity", 0),
        "salePrice": product.get("salePrice", 0),
        "minStock": product.get("minStock", 0),
        "image": product.get("image", ""),
        "active": product.get("active", True),
    }


def money(value):
    return round(float(value or 0), 2)


def has_admin_password(value):
    return value == ADMIN_PASSWORD


def load_bagcatap_kindergartens():
    items = load_json_file(BAGCATAP_FILE, [])
    return items if isinstance(items, list) else []


def save_bagcatap_kindergartens(items):
    save_json_file(BAGCATAP_FILE, items)


def load_bagcatap_notifications():
    items = load_json_file(BAGCATAP_NOTIFICATIONS_FILE, [])
    return items if isinstance(items, list) else []


def save_bagcatap_notifications(items):
    save_json_file(BAGCATAP_NOTIFICATIONS_FILE, items[:100])


def load_bagcatap_device_tokens():
    tokens = load_json_file(BAGCATAP_DEVICE_TOKENS_FILE, [])
    return tokens if isinstance(tokens, list) else []


def save_bagcatap_device_tokens(tokens):
    save_json_file(BAGCATAP_DEVICE_TOKENS_FILE, tokens[-10000:])


def load_bagcatap_users():
    users = load_json_file(BAGCATAP_USERS_FILE, [])
    return users if isinstance(users, list) else []


def save_bagcatap_users(users):
    save_json_file(BAGCATAP_USERS_FILE, users)


def load_bagcatap_reset_codes():
    codes = load_json_file(BAGCATAP_RESET_CODES_FILE, [])
    return codes if isinstance(codes, list) else []


def save_bagcatap_reset_codes(codes):
    save_json_file(BAGCATAP_RESET_CODES_FILE, codes[-200:])


def load_bagcatap_stats():
    stats = load_json_file(BAGCATAP_STATS_FILE, {})
    if not isinstance(stats, dict):
        stats = {}
    stats.setdefault("kindergartenViews", {})
    stats.setdefault("appDevices", {})
    return stats


def save_bagcatap_stats(stats):
    save_json_file(BAGCATAP_STATS_FILE, stats)


def safe_upload_name(value):
    stem = Path(str(value or "bagca")).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:40] or "bagca"
    return stem


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def fcm_service_account_path():
    path = os.environ.get("BAGCATAP_FCM_SERVICE_ACCOUNT") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        return None
    service_account = Path(path).expanduser()
    return service_account if service_account.exists() else None


def fcm_access_token(service_account):
    data = json.loads(service_account.read_text(encoding="utf-8"))
    now = int(time.time())
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode("utf-8"))
    claims = {
        "iss": data["client_email"],
        "scope": "https://www.googleapis.com/auth/firebase.messaging",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    payload = b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{payload}".encode("utf-8")
    with tempfile.NamedTemporaryFile("w", delete=False) as key_file:
        key_file.write(data["private_key"])
        key_path = key_file.name
    try:
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=signing_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    finally:
        try:
            os.unlink(key_path)
        except OSError:
            pass
    assertion = f"{header}.{payload}.{b64url(result.stdout)}"
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=(
            "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer"
            + "&assertion="
            + assertion
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=12) as response:
        token_data = json.loads(response.read().decode("utf-8"))
    return data["project_id"], token_data["access_token"]


def send_bagcatap_push(title, message):
    tokens = [item for item in load_bagcatap_device_tokens() if item.get("active", True) and item.get("token")]
    if not tokens:
        return {"configured": bool(fcm_service_account_path()), "sent": 0, "failed": 0, "reason": "no devices"}
    service_account = fcm_service_account_path()
    if not service_account:
        return {"configured": False, "sent": 0, "failed": 0, "reason": "push not connected"}

    try:
        project_id, access_token = fcm_access_token(service_account)
    except Exception:
        return {"configured": False, "sent": 0, "failed": len(tokens), "reason": "push auth failed"}

    sent = 0
    failed = 0
    kept = []
    for token_row in tokens:
        token = token_row.get("token", "")
        payload = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": message},
                "android": {
                    "priority": "HIGH",
                    "notification": {
                        "channel_id": "bagcatap_notifications",
                        "click_action": "OPEN_BAGCATAP",
                    },
                },
                "data": {"source": "bagcatap_admin", "createdAt": now_display()},
            }
        }
        request = Request(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urlopen(request, timeout=12):
                sent += 1
                token_row["lastPushAt"] = now_display()
                kept.append(token_row)
        except Exception:
            failed += 1
            token_row["lastPushFailedAt"] = now_display()
            kept.append(token_row)
    save_bagcatap_device_tokens(kept)
    return {"configured": True, "sent": sent, "failed": failed, "devices": len(tokens)}


def image_extension(mime, filename):
    mime = str(mime or "").lower()
    suffix = Path(str(filename or "")).suffix.lower()
    if mime in ("image/jpeg", "image/jpg") or suffix in (".jpg", ".jpeg"):
        return ".jpg"
    if mime == "image/png" or suffix == ".png":
        return ".png"
    if mime == "image/webp" or suffix == ".webp":
        return ".webp"
    return ""


def public_request_origin(handler):
    host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host") or ""
    proto = handler.headers.get("X-Forwarded-Proto") or "https"
    if not host:
        return ""
    return f"{proto}://{host}"


def normalize_phone(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "994" + digits[1:]
    if len(digits) == 9 and digits[:2] in ("50", "51", "55", "70", "77", "99"):
        digits = "994" + digits
    return "+" + digits


def password_hash(password, salt):
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def public_bagcatap_user(user):
    return {
        "id": user.get("id", ""),
        "phone": user.get("phone", ""),
        "createdAt": user.get("createdAt", ""),
        "lastLoginAt": user.get("lastLoginAt", ""),
    }


def send_bagcatap_reset_sms(phone, code):
    # Real SMS can be connected here when an SMS provider account is ready.
    # Until then, the code is returned to the app only for testing.
    return False


def public_bagcatap_notification(item):
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "message": item.get("message", ""),
        "createdAt": item.get("createdAt", ""),
        "active": bool(item.get("active", True)),
    }


def list_from_value(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").splitlines() if item.strip()]


def bagcatap_kindergarten_from_data(data, existing=None):
    item = dict(existing or {})
    text_fields = (
        "name", "district", "address", "phone", "price", "ages", "hours",
        "places", "image", "note", "capacity", "groups", "meals", "staff"
    )
    for key in text_fields:
        if key in data or existing is None:
            item[key] = str(data.get(key, item.get(key, ""))).strip()
    for key in ("lat", "lng"):
        if key in data or existing is None:
            try:
                item[key] = float(data.get(key, item.get(key, 0)) or 0)
            except (TypeError, ValueError):
                item[key] = 0
    for key in ("services", "activity", "certificates", "admission", "safety"):
        if key in data or existing is None:
            item[key] = list_from_value(data.get(key, item.get(key, [])))
    if "active" in data or existing is None:
        item["active"] = bool(data.get("active", item.get("active", True)))
    if "featured" in data or existing is None:
        item["featured"] = bool(data.get("featured", item.get("featured", False)))
    return item


def public_bagcatap_kindergarten(item, include_inactive=False):
    if not include_inactive and not item.get("active", True):
        return None
    public_item = dict(item)
    public_item.setdefault("services", [])
    public_item.setdefault("activity", [])
    public_item.setdefault("certificates", [])
    public_item.setdefault("admission", [])
    public_item.setdefault("safety", [])
    public_item.setdefault("active", True)
    public_item.setdefault("featured", False)
    return public_item


def barcode_category_from_name(name):
    text = name.lower()
    if any(word in text for word in ("pall mall", "marlboro", "winston", "kent", "siqaret", "cigarette")):
        return "Siqaret"
    if any(word in text for word in ("cola", "fanta", "sprite", "su", "ayran", "juice", "içki")):
        return "İçkilər"
    if any(word in text for word in ("şokolad", "chocolate", "biscuit", "konfet", "snack")):
        return "Şirniyyat"
    if any(word in text for word in ("ketçup", "ketchup", "sous", "sauce")):
        return "Souslar"
    return "Avtomatik tapılan"


def clean_lookup_name(value):
    value = html_unescape(re.sub(r"<[^>]+>", " ", value or ""))
    value = re.sub(r"\s+", " ", value).strip(" -–—\t\r\n")
    return value


def lookup_barcode_online(barcode):
    barcode = re.sub(r"\D+", "", str(barcode or ""))
    if not barcode:
        return None
    if barcode in KNOWN_BARCODE_LOOKUPS:
        known = KNOWN_BARCODE_LOOKUPS[barcode]
        return {
            "barcode": barcode,
            "name": known["name"],
            "category": known.get("category", barcode_category_from_name(known["name"])),
            "alternatives": known.get("alternatives", []),
            "source": "known-cache",
        }

    # A public barcode page is used as a best-effort source. Some local/store-only
    # barcodes will not exist online, so callers must still allow manual entry.
    url = f"https://barcode-list.ru/barcode/RU/barcode-{barcode}/%D0%9F%D0%BE%D0%B8%D1%81%D0%BA.htm"
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urlopen(request, timeout=8) as response:
            html = response.read().decode("utf-8", "ignore")
    except Exception:
        return None

    candidates = []
    for match in re.finditer(rf"<td[^>]*>\s*{re.escape(barcode)}\s*</td>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S):
        name = clean_lookup_name(match.group(1))
        if name and name.lower() not in ("наименование", "name"):
            candidates.append(name)
    if not candidates:
        for match in re.finditer(rf"{re.escape(barcode)}\s*</td>\s*<td[^>]*>(.*?)</td>", html, re.I | re.S):
            name = clean_lookup_name(match.group(1))
            if name:
                candidates.append(name)

    seen = set()
    names = []
    for name in candidates:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    if not names:
        return None

    return {
        "barcode": barcode,
        "name": names[0],
        "category": barcode_category_from_name(names[0]),
        "alternatives": names[:8],
        "source": url,
    }


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
        if path == "/api/bagcatap/kindergartens":
            params = parse_qs(query)
            is_admin = has_admin_password(params.get("password", [""])[0])
            items = [
                public_bagcatap_kindergarten(item, include_inactive=is_admin)
                for item in load_bagcatap_kindergartens()
            ]
            items = [item for item in items if item]
            items.sort(key=lambda item: (not item.get("featured", False), item.get("name", "")))
            self.api_json(items)
            return
        if path == "/api/bagcatap/notifications":
            params = parse_qs(query)
            is_admin = has_admin_password(params.get("password", [""])[0])
            items = load_bagcatap_notifications()
            if not is_admin:
                items = [item for item in items if item.get("active", True)]
                items = items[:1]
            self.api_json([public_bagcatap_notification(item) for item in items])
            return
        if path == "/api/bagcatap/stats":
            params = parse_qs(query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            users = load_bagcatap_users()
            stats = load_bagcatap_stats()
            view_rows = []
            device_rows = []
            by_id = {str(item.get("id", "")): item for item in load_bagcatap_kindergartens()}
            for kindergarten_id, row in stats.get("kindergartenViews", {}).items():
                kindergarten = by_id.get(str(kindergarten_id), {})
                view_rows.append({
                    "kindergartenId": kindergarten_id,
                    "name": row.get("name") or kindergarten.get("name") or kindergarten_id,
                    "views": int(row.get("views", 0) or 0),
                    "lastViewedAt": row.get("lastViewedAt", ""),
                })
            view_rows.sort(key=lambda item: item["views"], reverse=True)
            for device_id, row in stats.get("appDevices", {}).items():
                lat = row.get("lat")
                lng = row.get("lng")
                has_location = isinstance(lat, (int, float)) and isinstance(lng, (int, float))
                device_rows.append({
                    "deviceId": device_id,
                    "shortId": str(device_id)[-6:],
                    "firstOpenAt": row.get("firstOpenAt", ""),
                    "lastOpenAt": row.get("lastOpenAt", ""),
                    "opens": int(row.get("opens", 0) or 0),
                    "lat": lat if has_location else None,
                    "lng": lng if has_location else None,
                    "accuracy": row.get("accuracy"),
                    "locationAt": row.get("locationAt", ""),
                    "mapUrl": f"https://maps.google.com/?q={lat},{lng}" if has_location else "",
                })
            device_rows.sort(key=lambda item: item.get("lastOpenAt", ""), reverse=True)
            self.api_json({
                "registeredUsers": len(users),
                "appUsers": int(stats.get("appUsers", 0) or 0),
                "appOpens": int(stats.get("appOpens", 0) or 0),
                "pushDevices": len(load_bagcatap_device_tokens()),
                "pushConnected": bool(fcm_service_account_path()),
                "lastAppOpenAt": stats.get("lastAppOpenAt", ""),
                "users": [public_bagcatap_user(user) for user in users],
                "devices": device_rows,
                "views": view_rows,
                "totalViews": sum(item["views"] for item in view_rows),
            })
            return
        if path == "/api/inventory/products":
            params = parse_qs(query)
            is_admin = has_admin_password(params.get("password", [""])[0])
            products = load_inventory_products()
            if is_admin:
                self.api_json(products)
            else:
                self.api_json([public_inventory_product(item) for item in products if item.get("active", True)])
            return
        if path == "/api/inventory/report":
            params = parse_qs(query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            start_date = params.get("start", [today_iso()])[0] or today_iso()
            end_date = params.get("end", [start_date])[0] or start_date
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            inventory_sales = load_inventory_sales()
            inventory_receipts = load_inventory_receipts()
            inventory_returns = load_inventory_returns()
            selected_sales = [
                sale for sale in inventory_sales
                if start_date <= sale.get("date", "") <= end_date
            ]
            selected_receipts = [
                receipt for receipt in inventory_receipts
                if start_date <= receipt.get("date", "") <= end_date
            ]
            selected_returns = [
                returned for returned in inventory_returns
                if start_date <= returned.get("date", "") <= end_date
            ]
            by_product = {}
            for sale in selected_sales:
                for line in sale.get("items", []):
                    key = line.get("productId") or line.get("barcode") or line.get("name")
                    row = by_product.setdefault(key, {
                        "productId": line.get("productId", ""),
                        "barcode": line.get("barcode", ""),
                        "name": line.get("name", ""),
                        "image": line.get("image", ""),
                        "quantity": 0,
                        "total": 0,
                        "profit": 0,
                    })
                    row["quantity"] += int(line.get("quantity", 0))
                    row["total"] += money(line.get("total", 0))
                    row["profit"] += money(line.get("profit", 0))
            by_date = {}
            for sale in selected_sales:
                date = sale.get("date", "")
                row = by_date.setdefault(date, {"date": date, "count": 0, "total": 0, "profit": 0})
                row["count"] += 1
                row["total"] += money(sale.get("total", 0))
                row["profit"] += money(sale.get("profit", 0))
            products = load_inventory_products()
            low_stock = [
                item for item in products
                if int(item.get("quantity", 0)) <= int(item.get("minStock", 0))
            ]
            total = money(sum(sale.get("total", 0) for sale in selected_sales))
            profit = money(sum(sale.get("profit", 0) for sale in selected_sales))
            cash_total = money(sum(sale.get("total", 0) for sale in selected_sales if sale.get("paymentType", "cash") == "cash"))
            card_total = money(sum(sale.get("total", 0) for sale in selected_sales if sale.get("paymentType") == "card"))
            discount_total = money(sum(sale.get("discountAmount", 0) for sale in selected_sales))
            returns_total = money(sum(returned.get("total", 0) for returned in selected_returns))
            sold_products = sorted(
                by_product.values(),
                key=lambda item: (item["quantity"], item["total"]),
                reverse=True,
            )
            self.api_json({
                "start": start_date,
                "end": end_date,
                "salesCount": len(selected_sales),
                "total": total,
                "profit": profit,
                "cashTotal": cash_total,
                "cardTotal": card_total,
                "discountTotal": discount_total,
                "returnsTotal": returns_total,
                "receiptCount": len(selected_sales),
                "itemsSold": sum(
                    int(line.get("quantity", 0))
                    for sale in selected_sales
                    for line in sale.get("items", [])
                ),
                "topProducts": sold_products[:10],
                "soldProducts": sold_products,
                "byDate": sorted(by_date.values(), key=lambda item: item["date"], reverse=True),
                "lowStock": low_stock,
                "sales": selected_sales,
                "receipts": selected_receipts,
                "returns": selected_returns,
            })
            return
        if path == "/api/inventory/sale":
            params = parse_qs(query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            receipt_id = str(params.get("receiptId", [""])[0]).strip()
            sale = next((item for item in load_inventory_sales() if str(item.get("id", "")) == receipt_id), None)
            if not sale:
                self.api_json({"error": "sale not found"}, 404)
                return
            self.api_json(sale)
            return
        if path == "/api/inventory/attendance":
            params = parse_qs(query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            start_date = params.get("start", [today_iso()])[0] or today_iso()
            end_date = params.get("end", [start_date])[0] or start_date
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            logs = [
                item for item in load_inventory_attendance()
                if start_date <= str(item.get("date", "")) <= end_date
            ]
            self.api_json({
                "employees": [public_employee(item, include_descriptor=True) for item in load_inventory_employees()],
                "logs": logs,
            })
            return
        if path == "/api/inventory/face-employees":
            self.api_json({
                "employees": [public_employee(item, include_descriptor=True) for item in load_inventory_employees() if item.get("active", True)],
            })
            return
        if path == "/api/inventory/face-attendance":
            params = parse_qs(query)
            start_date = params.get("start", [today_iso()])[0] or today_iso()
            end_date = params.get("end", [start_date])[0] or start_date
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            logs = [
                item for item in load_inventory_attendance()
                if start_date <= str(item.get("date", "")) <= end_date
            ]
            self.api_json({"logs": logs})
            return
        if path == "/api/inventory/barcode-lookup":
            params = parse_qs(query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            barcode = re.sub(r"\D+", "", str(params.get("barcode", [""])[0] or ""))
            if barcode:
                for product in load_inventory_products():
                    if str(product.get("barcode", "")).strip() == barcode:
                        self.api_json({
                            "found": True,
                            "barcode": barcode,
                            "name": product.get("name", ""),
                            "category": product.get("category", ""),
                            "image": product.get("image", ""),
                            "source": "local",
                        })
                        return
            result = lookup_barcode_online(barcode)
            if not result:
                self.api_json({"found": False, "barcode": barcode})
                return
            self.api_json({"found": True, **result})
            return
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
            params = parse_qs(query)
            password = params.get("password", [""])[0]
            selected_date = params.get("date", [""])[0]
            start_date = params.get("start", [""])[0]
            end_date = params.get("end", [""])[0]
            if not has_admin_password(password):
                self.api_json({"error": "wrong password"}, 403)
                return
            by_date = {}
            for sale in sales:
                date = sale.get("date", "")
                row = by_date.setdefault(date, {"date": date, "total": 0, "count": 0})
                row["total"] += sale["total"]
                row["count"] += 1
            today = time.strftime("%Y-%m-%d")
            report_start = start_date or selected_date or today
            report_end = end_date or report_start
            if report_start > report_end:
                report_start, report_end = report_end, report_start
            range_rows = [
                row for row in by_date.values()
                if report_start <= row.get("date", "") <= report_end
            ]
            report_count = sum(row.get("count", 0) for row in range_rows)
            report_total = sum(row.get("total", 0) for row in range_rows)
            self.api_json({
                "total": sum(item["total"] for item in sales),
                "todayTotal": by_date.get(today, {}).get("total", 0),
                "todayCount": by_date.get(today, {}).get("count", 0),
                "count": len(sales),
                "selectedDate": report_start if report_start == report_end else f"{report_start} - {report_end}",
                "selectedStartDate": report_start,
                "selectedEndDate": report_end,
                "selectedTotal": report_total,
                "selectedCount": report_count,
                "selectedAverage": round(report_total / report_count, 2) if report_count else 0,
                "byDate": sorted(range_rows, key=lambda item: item["date"], reverse=True),
                "sales": sales,
            })
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/bagcatap/kindergartens":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            item = bagcatap_kindergarten_from_data(data)
            if not item.get("name"):
                self.api_json({"error": "name required"}, 400)
                return
            if not item.get("address"):
                self.api_json({"error": "address required"}, 400)
                return
            if not item.get("id"):
                item["id"] = "kg-" + str(int(time.time() * 1000))
            item["createdAt"] = now_display()
            item["updatedAt"] = now_display()
            items = load_bagcatap_kindergartens()
            items.insert(0, item)
            save_bagcatap_kindergartens(items)
            self.api_json(item, 201)
            return
        if path == "/api/bagcatap/notifications":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            title = str(data.get("title", "")).strip() or "BağçaTap bildirişi"
            message = str(data.get("message", "")).strip()
            if not message:
                self.api_json({"error": "message required"}, 400)
                return
            item = {
                "id": "ntf-" + str(int(time.time() * 1000)),
                "title": title,
                "message": message,
                "active": bool(data.get("active", True)),
                "createdAt": now_display(),
            }
            items = load_bagcatap_notifications()
            items.insert(0, item)
            save_bagcatap_notifications(items)
            push = send_bagcatap_push(title, message) if item["active"] else {"sent": 0, "failed": 0, "skipped": "inactive"}
            result = public_bagcatap_notification(item)
            result["push"] = push
            self.api_json(result, 201)
            return
        if path == "/api/bagcatap/device-token":
            data = self.read_body()
            token = str(data.get("token", "")).strip()
            device_id = str(data.get("deviceId", "")).strip()
            app_version = str(data.get("appVersion", "")).strip()
            if not token:
                self.api_json({"error": "token required"}, 400)
                return
            tokens = [item for item in load_bagcatap_device_tokens() if item.get("token") != token]
            tokens.append({
                "token": token,
                "deviceId": device_id,
                "appVersion": app_version,
                "active": True,
                "registeredAt": now_display(),
                "lastSeenAt": now_display(),
            })
            save_bagcatap_device_tokens(tokens)
            self.api_json({"ok": True, "devices": len(tokens)}, 201)
            return
        if path == "/api/bagcatap/upload-image":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            filename = str(data.get("fileName", "bagca.jpg"))
            mime = str(data.get("mime", ""))
            ext = image_extension(mime, filename)
            if not ext:
                self.api_json({"error": "image type not allowed"}, 400)
                return
            raw_data = str(data.get("data", ""))
            if "," in raw_data and raw_data.split(",", 1)[0].startswith("data:"):
                raw_data = raw_data.split(",", 1)[1]
            try:
                image_bytes = base64.b64decode(raw_data, validate=True)
            except Exception:
                self.api_json({"error": "invalid image"}, 400)
                return
            if not image_bytes or len(image_bytes) > 4 * 1024 * 1024:
                self.api_json({"error": "image too large"}, 400)
                return
            BAGCATAP_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            stored_name = f"{int(time.time() * 1000)}-{safe_upload_name(filename)}{ext}"
            stored_path = BAGCATAP_UPLOADS_DIR / stored_name
            stored_path.write_bytes(image_bytes)
            relative_url = f"/bagcatap/uploads/{stored_name}"
            origin = public_request_origin(self)
            self.api_json({
                "ok": True,
                "url": f"{origin}{relative_url}" if origin else relative_url,
                "path": relative_url,
            }, 201)
            return
        if path == "/api/bagcatap/auth/register":
            data = self.read_body()
            phone = normalize_phone(data.get("phone"))
            password = str(data.get("password", ""))
            if not phone or len(password) < 4:
                self.api_json({"error": "phone and password required"}, 400)
                return
            users = load_bagcatap_users()
            if any(user.get("phone") == phone for user in users):
                self.api_json({"error": "phone exists"}, 409)
                return
            salt = secrets.token_hex(12)
            user = {
                "id": "usr-" + str(int(time.time() * 1000)),
                "phone": phone,
                "salt": salt,
                "passwordHash": password_hash(password, salt),
                "createdAt": now_display(),
                "lastLoginAt": now_display(),
            }
            users.insert(0, user)
            save_bagcatap_users(users)
            self.api_json({"ok": True, "user": public_bagcatap_user(user)}, 201)
            return
        if path == "/api/bagcatap/auth/login":
            data = self.read_body()
            phone = normalize_phone(data.get("phone"))
            password = str(data.get("password", ""))
            users = load_bagcatap_users()
            for user in users:
                if user.get("phone") == phone and user.get("passwordHash") == password_hash(password, user.get("salt", "")):
                    user["lastLoginAt"] = now_display()
                    save_bagcatap_users(users)
                    self.api_json({"ok": True, "user": public_bagcatap_user(user)})
                    return
            self.api_json({"error": "wrong credentials"}, 403)
            return
        if path == "/api/bagcatap/auth/request-reset":
            data = self.read_body()
            phone = normalize_phone(data.get("phone"))
            users = load_bagcatap_users()
            if not any(user.get("phone") == phone for user in users):
                self.api_json({"error": "phone not found"}, 404)
                return
            code = f"{secrets.randbelow(1000000):06d}"
            codes = [
                item for item in load_bagcatap_reset_codes()
                if item.get("phone") != phone or int(item.get("expiresAt", 0) or 0) > int(time.time())
            ]
            codes.append({
                "phone": phone,
                "codeHash": password_hash(code, phone),
                "createdAt": now_display(),
                "expiresAt": int(time.time()) + 15 * 60,
                "used": False,
            })
            save_bagcatap_reset_codes(codes)
            sent = send_bagcatap_reset_sms(phone, code)
            response = {"ok": True, "smsSent": sent}
            if not sent:
                response["testCode"] = code
            self.api_json(response)
            return
        if path == "/api/bagcatap/auth/reset-password":
            data = self.read_body()
            phone = normalize_phone(data.get("phone"))
            code = re.sub(r"\D+", "", str(data.get("code", "")))
            new_password = str(data.get("password", ""))
            if len(new_password) < 4:
                self.api_json({"error": "password too short"}, 400)
                return
            now_ts = int(time.time())
            codes = load_bagcatap_reset_codes()
            match = next((
                item for item in reversed(codes)
                if item.get("phone") == phone
                and not item.get("used")
                and int(item.get("expiresAt", 0) or 0) >= now_ts
                and item.get("codeHash") == password_hash(code, phone)
            ), None)
            if not match:
                self.api_json({"error": "wrong code"}, 403)
                return
            users = load_bagcatap_users()
            for user in users:
                if user.get("phone") == phone:
                    salt = secrets.token_hex(12)
                    user["salt"] = salt
                    user["passwordHash"] = password_hash(new_password, salt)
                    user["lastLoginAt"] = now_display()
                    match["used"] = True
                    save_bagcatap_users(users)
                    save_bagcatap_reset_codes(codes)
                    self.api_json({"ok": True, "user": public_bagcatap_user(user)})
                    return
            self.api_json({"error": "phone not found"}, 404)
            return
        if path == "/api/bagcatap/views":
            data = self.read_body()
            kindergarten_id = str(data.get("kindergartenId", "")).strip()
            name = str(data.get("name", "")).strip()
            if not kindergarten_id and not name:
                self.api_json({"error": "kindergarten required"}, 400)
                return
            key = kindergarten_id or name
            stats = load_bagcatap_stats()
            views = stats.setdefault("kindergartenViews", {})
            row = views.setdefault(key, {"name": name or key, "views": 0, "lastViewedAt": ""})
            row["name"] = name or row.get("name") or key
            row["views"] = int(row.get("views", 0) or 0) + 1
            row["lastViewedAt"] = now_display()
            save_bagcatap_stats(stats)
            self.api_json({"ok": True, "views": row["views"]}, 201)
            return
        if path == "/api/bagcatap/app-open":
            data = self.read_body()
            device_id = str(data.get("deviceId", "")).strip()
            if not device_id:
                self.api_json({"error": "device required"}, 400)
                return
            stats = load_bagcatap_stats()
            devices = stats.setdefault("appDevices", {})
            is_new = device_id not in devices
            row = devices.get(device_id, {})
            row["firstOpenAt"] = row.get("firstOpenAt", now_display())
            row["lastOpenAt"] = now_display()
            row["opens"] = int(row.get("opens", 0) or 0) + 1
            try:
                lat = float(data.get("lat"))
                lng = float(data.get("lng"))
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    row["lat"] = round(lat, 6)
                    row["lng"] = round(lng, 6)
                    row["accuracy"] = round(float(data.get("accuracy", 0) or 0), 1)
                    row["locationAt"] = now_display()
            except (TypeError, ValueError):
                pass
            devices[device_id] = row
            stats["appUsers"] = len(devices)
            stats["appOpens"] = int(stats.get("appOpens", 0) or 0) + 1
            stats["lastAppOpenAt"] = now_display()
            save_bagcatap_stats(stats)
            self.api_json({
                "ok": True,
                "newDevice": is_new,
                "appUsers": stats["appUsers"],
                "appOpens": stats["appOpens"],
            }, 201)
            return
        if path == "/api/inventory/products":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            products = load_inventory_products()
            barcode = str(data.get("barcode", "")).strip()
            if barcode and any(str(item.get("barcode", "")) == barcode for item in products):
                self.api_json({"error": "duplicate barcode"}, 409)
                return
            product = {
                "id": str(int(time.time() * 1000)),
                "barcode": barcode,
                "name": str(data.get("name", "")).strip(),
                "category": str(data.get("category", "")).strip(),
                "color": str(data.get("color", "")).strip(),
                "size": str(data.get("size", "")).strip(),
                "quantity": int(float(data.get("quantity", 0) or 0)),
                "costPrice": money(data.get("costPrice", 0)),
                "salePrice": money(data.get("salePrice", 0)),
                "minStock": int(float(data.get("minStock", 0) or 0)),
                "image": str(data.get("image", "")).strip(),
                "createdAt": now_display(),
                "updatedAt": now_display(),
                "active": bool(data.get("active", True)),
            }
            if not product["name"]:
                self.api_json({"error": "name required"}, 400)
                return
            products.insert(0, product)
            save_inventory_products(products)
            self.api_json(product, 201)
            return
        if path == "/api/inventory/employees":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            name = str(data.get("name", "")).strip()
            descriptor = data.get("descriptor")
            if not name:
                self.api_json({"error": "name required"}, 400)
                return
            if not isinstance(descriptor, list) or len(descriptor) < 64:
                self.api_json({"error": "face required"}, 400)
                return
            employee = {
                "id": str(int(time.time() * 1000)),
                "name": name,
                "descriptor": [float(value) for value in descriptor],
                "image": str(data.get("image", ""))[:120000],
                "active": True,
                "registeredAt": now_display(),
            }
            employees = load_inventory_employees()
            employees.insert(0, employee)
            save_inventory_employees(employees)
            self.api_json(public_employee(employee, include_descriptor=True), 201)
            return
        if path == "/api/inventory/attendance":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            record = create_inventory_attendance_record(data.get("employeeId"), data.get("action", "auto"), data.get("score", 0))
            if not record:
                self.api_json({"error": "employee not found"}, 404)
                return
            self.api_json(record, 201)
            return
        if path == "/api/inventory/face-attendance":
            data = self.read_body()
            record = create_inventory_attendance_record(data.get("employeeId"), data.get("action", "auto"), data.get("score", 0))
            if not record:
                self.api_json({"error": "employee not found"}, 404)
                return
            self.api_json(record, 201)
            return
        if path == "/api/inventory/sales":
            data = self.read_body()
            requested_items = data.get("items", [])
            if not isinstance(requested_items, list) or not requested_items:
                self.api_json({"error": "empty sale"}, 400)
                return
            products = load_inventory_products()
            by_id = {str(item.get("id")): item for item in products}
            by_barcode = {str(item.get("barcode", "")): item for item in products if item.get("barcode")}
            sale_items = []
            for requested in requested_items:
                product = by_id.get(str(requested.get("productId", ""))) or by_barcode.get(str(requested.get("barcode", "")))
                quantity = int(float(requested.get("quantity", 1) or 1))
                if not product:
                    self.api_json({"error": "product not found", "item": requested}, 404)
                    return
                if quantity <= 0:
                    self.api_json({"error": "wrong quantity"}, 400)
                    return
                if int(product.get("quantity", 0)) < quantity:
                    self.api_json({
                        "error": "not enough stock",
                        "product": product.get("name", ""),
                        "available": int(product.get("quantity", 0)),
                    }, 409)
                    return
                sale_price = money(product.get("salePrice", 0))
                cost_price = money(product.get("costPrice", 0))
                line_total = money(sale_price * quantity)
                line_profit = money((sale_price - cost_price) * quantity)
                sale_items.append({
                    "productId": product.get("id"),
                    "barcode": product.get("barcode", ""),
                    "name": product.get("name", ""),
                    "category": product.get("category", ""),
                    "color": product.get("color", ""),
                    "size": product.get("size", ""),
                    "image": product.get("image", ""),
                    "quantity": quantity,
                    "salePrice": sale_price,
                    "costPrice": cost_price,
                    "total": line_total,
                    "profit": line_profit,
                })
            for line in sale_items:
                product = by_id[str(line["productId"])]
                product["quantity"] = int(product.get("quantity", 0)) - int(line["quantity"])
                product["updatedAt"] = now_display()
            subtotal = money(sum(item["total"] for item in sale_items))
            discount_amount = money(data.get("discountAmount", 0))
            if discount_amount < 0:
                discount_amount = 0
            if discount_amount > subtotal:
                discount_amount = subtotal
            total = money(subtotal - discount_amount)
            payment_type = str(data.get("paymentType", "cash")).strip().lower()
            if payment_type not in ("cash", "card"):
                payment_type = "cash"
            cash_received = money(data.get("cashReceived", 0)) if payment_type == "cash" else 0
            cash_change = money(max(cash_received - total, 0)) if payment_type == "cash" else 0
            if payment_type == "cash" and cash_received < total:
                self.api_json({"error": "cash not enough", "total": total, "cashReceived": cash_received}, 400)
                return
            sale = {
                "id": str(int(time.time() * 1000)),
                "seller": str(data.get("seller", "Satıcı")).strip() or "Satıcı",
                "note": str(data.get("note", "")).strip(),
                "items": sale_items,
                "subtotal": subtotal,
                "discountAmount": discount_amount,
                "discountNote": str(data.get("discountNote", "")).strip(),
                "total": total,
                "profit": money(sum(item["profit"] for item in sale_items) - discount_amount),
                "paymentType": payment_type,
                "cashReceived": cash_received,
                "cashChange": cash_change,
                "time": now_display(),
                "date": today_iso(),
            }
            inventory_sales = load_inventory_sales()
            inventory_sales.insert(0, sale)
            save_inventory_products(products)
            save_inventory_sales(inventory_sales)
            self.api_json(sale, 201)
            return
        if path == "/api/inventory/receipts":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            requested_items = data.get("items", [])
            if not isinstance(requested_items, list) or not requested_items:
                self.api_json({"error": "empty receipt"}, 400)
                return
            products = load_inventory_products()
            by_id = {str(item.get("id")): item for item in products}
            by_barcode = {str(item.get("barcode", "")): item for item in products if item.get("barcode")}
            receipt_items = []
            for requested in requested_items:
                barcode = str(requested.get("barcode", "")).strip()
                product = by_id.get(str(requested.get("productId", ""))) or by_barcode.get(barcode)
                new_product = requested.get("newProduct") if isinstance(requested.get("newProduct"), dict) else {}
                if not product and new_product:
                    product_name = str(new_product.get("name", "")).strip()
                    product_barcode = str(new_product.get("barcode", barcode)).strip()
                    if not product_name:
                        self.api_json({"error": "name required", "item": requested}, 400)
                        return
                    if product_barcode and product_barcode in by_barcode:
                        self.api_json({"error": "duplicate barcode", "barcode": product_barcode}, 409)
                        return
                    product = {
                        "id": str(int(time.time() * 1000)) + str(len(products)),
                        "barcode": product_barcode,
                        "name": product_name,
                        "category": str(new_product.get("category", "")).strip(),
                        "color": str(new_product.get("color", "")).strip(),
                        "size": str(new_product.get("size", "")).strip(),
                        "quantity": 0,
                        "costPrice": money(requested.get("costPrice", new_product.get("costPrice", 0))),
                        "salePrice": money(requested.get("salePrice", new_product.get("salePrice", 0))),
                        "minStock": int(float(new_product.get("minStock", 0) or 0)),
                        "image": str(new_product.get("image", "")).strip(),
                        "createdAt": now_display(),
                        "updatedAt": now_display(),
                        "active": True,
                    }
                    products.insert(0, product)
                    by_id[str(product.get("id"))] = product
                    if product.get("barcode"):
                        by_barcode[str(product.get("barcode"))] = product
                quantity = int(float(requested.get("quantity", 0) or 0))
                if not product:
                    self.api_json({"error": "product not found", "item": requested}, 404)
                    return
                if quantity <= 0:
                    self.api_json({"error": "wrong quantity"}, 400)
                    return
                old_quantity = int(product.get("quantity", 0))
                new_cost = requested.get("costPrice", "")
                if new_cost != "" and new_cost is not None:
                    product["costPrice"] = money(new_cost)
                new_sale = requested.get("salePrice", "")
                if new_sale != "" and new_sale is not None:
                    product["salePrice"] = money(new_sale)
                product["quantity"] = old_quantity + quantity
                product["updatedAt"] = now_display()
                receipt_items.append({
                    "productId": product.get("id"),
                    "barcode": product.get("barcode", ""),
                    "name": product.get("name", ""),
                    "category": product.get("category", ""),
                    "color": product.get("color", ""),
                    "size": product.get("size", ""),
                    "image": product.get("image", ""),
                    "quantity": quantity,
                    "oldQuantity": old_quantity,
                    "newQuantity": product["quantity"],
                    "costPrice": money(product.get("costPrice", 0)),
                    "salePrice": money(product.get("salePrice", 0)),
                    "profitPerUnit": money(money(product.get("salePrice", 0)) - money(product.get("costPrice", 0))),
                })
            receipt = {
                "id": str(int(time.time() * 1000)),
                "supplier": str(data.get("supplier", "")).strip(),
                "receiver": str(data.get("receiver", "Admin")).strip() or "Admin",
                "note": str(data.get("note", "")).strip(),
                "items": receipt_items,
                "itemsCount": sum(item["quantity"] for item in receipt_items),
                "time": now_display(),
                "date": today_iso(),
            }
            inventory_receipts = load_inventory_receipts()
            inventory_receipts.insert(0, receipt)
            save_inventory_products(products)
            save_inventory_receipts(inventory_receipts)
            self.api_json(receipt, 201)
            return
        if path == "/api/inventory/returns":
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            quantity = int(float(data.get("quantity", 0) or 0))
            if quantity <= 0:
                self.api_json({"error": "wrong quantity"}, 400)
                return

            products = load_inventory_products()
            by_id = {str(item.get("id")): item for item in products}
            by_barcode = {str(item.get("barcode", "")): item for item in products if item.get("barcode")}
            mode = str(data.get("mode", "barcode")).strip().lower()
            receipt_id = str(data.get("receiptId", "")).strip()
            barcode = str(data.get("barcode", "")).strip()
            product_id = str(data.get("productId", "")).strip()
            sale = None
            sale_line = None

            if mode == "receipt" or receipt_id:
                sale = next((item for item in load_inventory_sales() if str(item.get("id", "")) == receipt_id), None)
                if not sale:
                    self.api_json({"error": "sale not found"}, 404)
                    return
                for line in sale.get("items", []):
                    line_product_id = str(line.get("productId", ""))
                    line_barcode = str(line.get("barcode", ""))
                    if (product_id and line_product_id == product_id) or (barcode and line_barcode == barcode):
                        sale_line = line
                        break
                if not sale_line:
                    self.api_json({"error": "sale item not found"}, 404)
                    return
                product_id = str(sale_line.get("productId", product_id))
                barcode = str(sale_line.get("barcode", barcode))
                returned_before = 0
                for returned in load_inventory_returns():
                    if str(returned.get("receiptId", "")) != receipt_id:
                        continue
                    same_product = product_id and str(returned.get("productId", "")) == product_id
                    same_barcode = barcode and str(returned.get("barcode", "")) == barcode
                    if same_product or same_barcode:
                        returned_before += int(returned.get("quantity", 0))
                sold_quantity = int(sale_line.get("quantity", 0))
                if quantity > max(sold_quantity - returned_before, 0):
                    self.api_json({"error": "return quantity too high", "sold": sold_quantity, "returnedBefore": returned_before}, 409)
                    return

            product = by_id.get(product_id) or by_barcode.get(barcode)
            if not product and sale_line:
                self.api_json({"error": "product not found in stock"}, 404)
                return
            if not product:
                self.api_json({"error": "product not found"}, 404)
                return

            old_quantity = int(product.get("quantity", 0))
            product["quantity"] = old_quantity + quantity
            product["updatedAt"] = now_display()
            sale_price = money((sale_line or product).get("salePrice", product.get("salePrice", 0)))
            cost_price = money((sale_line or product).get("costPrice", product.get("costPrice", 0)))
            returned_item = {
                "id": str(int(time.time() * 1000)),
                "mode": "receipt" if receipt_id else "barcode",
                "receiptId": receipt_id,
                "productId": product.get("id", ""),
                "barcode": product.get("barcode", barcode),
                "name": product.get("name", ""),
                "category": product.get("category", ""),
                "color": product.get("color", ""),
                "size": product.get("size", ""),
                "image": product.get("image", ""),
                "quantity": quantity,
                "oldQuantity": old_quantity,
                "newQuantity": product["quantity"],
                "salePrice": sale_price,
                "costPrice": cost_price,
                "total": money(sale_price * quantity),
                "profitImpact": money((sale_price - cost_price) * quantity),
                "reason": str(data.get("reason", "")).strip(),
                "operator": str(data.get("operator", "Admin")).strip() or "Admin",
                "time": now_display(),
                "date": today_iso(),
            }
            inventory_returns = load_inventory_returns()
            inventory_returns.insert(0, returned_item)
            save_inventory_products(products)
            save_inventory_returns(inventory_returns)
            self.api_json(returned_item, 201)
            return
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
        if path.startswith("/api/bagcatap/notifications/"):
            item_id = unquote(path.rsplit("/", 1)[-1])
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            items = load_bagcatap_notifications()
            for item in items:
                if str(item.get("id")) == item_id:
                    if "title" in data:
                        item["title"] = str(data.get("title", "")).strip() or item.get("title", "")
                    if "message" in data:
                        item["message"] = str(data.get("message", "")).strip() or item.get("message", "")
                    if "active" in data:
                        item["active"] = bool(data.get("active"))
                    item["updatedAt"] = now_display()
                    save_bagcatap_notifications(items)
                    self.api_json(public_bagcatap_notification(item))
                    return
            self.api_json({"error": "not found"}, 404)
            return
        if path.startswith("/api/bagcatap/kindergartens/"):
            item_id = unquote(path.rsplit("/", 1)[-1])
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            items = load_bagcatap_kindergartens()
            for index, item in enumerate(items):
                if str(item.get("id")) == item_id:
                    updated = bagcatap_kindergarten_from_data(data, existing=item)
                    updated["id"] = item.get("id")
                    updated["createdAt"] = item.get("createdAt", now_display())
                    updated["updatedAt"] = now_display()
                    items[index] = updated
                    save_bagcatap_kindergartens(items)
                    self.api_json(updated)
                    return
            self.api_json({"error": "not found"}, 404)
            return
        if path.startswith("/api/inventory/products/"):
            item_id = unquote(path.rsplit("/", 1)[-1])
            data = self.read_body()
            if not has_admin_password(data.get("password")):
                self.api_json({"error": "wrong password"}, 403)
                return
            products = load_inventory_products()
            for product in products:
                if str(product.get("id")) == item_id:
                    if "barcode" in data:
                        new_barcode = str(data.get("barcode", "")).strip()
                        if new_barcode and any(str(item.get("barcode", "")) == new_barcode and str(item.get("id")) != item_id for item in products):
                            self.api_json({"error": "duplicate barcode"}, 409)
                            return
                        product["barcode"] = new_barcode
                    for key in ("name", "category", "color", "size", "image"):
                        if key in data:
                            product[key] = str(data.get(key, "")).strip()
                    for key in ("costPrice", "salePrice"):
                        if key in data:
                            product[key] = money(data.get(key, 0))
                    for key in ("quantity", "minStock"):
                        if key in data:
                            product[key] = int(float(data.get(key, 0) or 0))
                    if "active" in data:
                        product["active"] = bool(data.get("active"))
                    product["updatedAt"] = now_display()
                    save_inventory_products(products)
                    self.api_json(product)
                    return
            self.api_json({"error": "not found"}, 404)
            return
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
                        save_sales(sales)
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
        if path.startswith("/api/bagcatap/notifications/"):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            item_id = unquote(path.rsplit("/", 1)[-1])
            items = [item for item in load_bagcatap_notifications() if str(item.get("id")) != item_id]
            save_bagcatap_notifications(items)
            self.api_json({"ok": True})
            return
        if path.startswith("/api/bagcatap/kindergartens/"):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            item_id = unquote(path.rsplit("/", 1)[-1])
            items = [item for item in load_bagcatap_kindergartens() if str(item.get("id")) != item_id]
            save_bagcatap_kindergartens(items)
            self.api_json({"ok": True})
            return
        if path.startswith("/api/inventory/products/"):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            item_id = unquote(path.rsplit("/", 1)[-1])
            products = [item for item in load_inventory_products() if str(item.get("id")) != item_id]
            save_inventory_products(products)
            self.api_json({"ok": True})
            return
        if path.startswith("/api/inventory/employees/"):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if not has_admin_password(params.get("password", [""])[0]):
                self.api_json({"error": "wrong password"}, 403)
                return
            employee_id = unquote(path.rsplit("/", 1)[-1])
            employees = [item for item in load_inventory_employees() if str(item.get("id", "")) != employee_id]
            save_inventory_employees(employees)
            self.api_json({"ok": True})
            return
        if path.startswith("/api/bills/"):
            table = unquote(path.rsplit("/", 1)[-1])
            bills.pop(table, None)
            self.api_json({"ok": True})
            return
        if path.startswith("/api/menu/"):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if not has_admin_password(params.get("password", [""])[0]):
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
