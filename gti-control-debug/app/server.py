# /app/server.py
from __future__ import annotations
import json, os, threading, time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Re-use API client & options from your current add-on
from api_client import APIClient, load_options  # <-- giữ nguyên file api_client.py hiện tại

APP_TITLE = "GTI Control"
USER_PATH = "/data/user_options.json"

app = FastAPI(title=APP_TITLE)

# ---------- Jinja templates ----------
env = Environment(
    loader=FileSystemLoader("/app/templates"),
    autoescape=select_autoescape(["html", "xml"])
)
def render(tpl: str, **ctx) -> HTMLResponse:
    return HTMLResponse(env.get_template(tpl).render(**ctx))

# ---------- API client & login ----------
_opts: Dict[str, Any] = load_options()
_api = APIClient(_opts)
_api_lock = threading.Lock()

def ensure_login() -> bool:
    try:
        with _api_lock:
            return _api.login()
    except Exception:
        return False

# ---------- cache helpers ----------
def _load_user_cache() -> Dict[str, Any]:
    if os.path.exists(USER_PATH):
        try:
            with open(USER_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_user_cache(cache: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(USER_PATH), exist_ok=True)
    with open(USER_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# ---------- value parsing ----------
def parse_value_string(val: str) -> List[float]:
    parts = [p for p in (val or "").split("#") if p != ""]
    out: List[float] = []
    for p in parts:
        try:
            out.append(float(str(p).replace(",", ".")))
        except Exception:
            out.append(float("nan"))
    return out

# nhãn mặc định (đủ dài để không lỗi; UI sẽ ẩn phần không có dữ liệu)
DEFAULT_LABELS = [
    "Điện áp lưới (V)",          # 0
    "Tần số lưới (Hz)",           # 1
    "Công suất xả (W)",           # 2
    "Điện áp pin (V)",            # 3
    "Dòng điện pin (A)",          # 4 (suy ra nếu backend có)
    "Điện áp ngắt (V)",           # 5
    "Công suất giới hạn (W)",     # 6
    "Công suất hoà lưới (W)",     # 7
    "Nhiệt độ Mosfet (°C)",       # 8
    "Dự phòng 9",                  # 9
    "Dự phòng 10",                 # 10
    "Dự phòng 11",                 # 11
]

# ---------- device resolve ----------
def resolve_device_id(slug_or_id: str = "gti283") -> Optional[str]:
    """
    Cho phép user gọi /app/device/gti283 nhưng thực tế thiết bị backend là "GTIControl###".
    Ưu tiên dùng cache, nếu không có sẽ dò từ API /all rồi chọn thiết bị có dữ liệu gần nhất.
    """
    cache = _load_user_cache()
    devmap = cache.get("device_map", {}) if isinstance(cache.get("device_map"), dict) else {}

    # cache hit
    if slug_or_id in devmap:
        return devmap[slug_or_id]

    # login + lấy danh sách
    if not ensure_login():
        return None

    raw_all = _api.read_state_server("all") or {}
    dids: List[str] = []
    if isinstance(raw_all, dict) and "data" in raw_all:
        for row in raw_all["data"]:
            did = row.get("deviceId") or row.get("device_id")
            if isinstance(did, str) and did.startswith("GTIControl") and did not in dids:
                dids.append(did)

    # thử cái nào có dữ liệu trước thì lấy luôn
    best: Optional[str] = None
    best_ts: float = 0.0
    for did in dids:
        st = _api.read_state_server(did) or {}
        # có value hợp lệ
        if isinstance(st, dict) and (st.get("value") or st.get("raw") or st.get("values")):
            # updatedAt trong raw
            ts = 0.0
            try:
                raw = st.get("raw") or {}
                ua = raw.get("updatedAt") or raw.get("updated_at")
                # không cần parse ISO phức tạp; chỉ cần ưu tiên cái nào có dữ liệu
                ts = time.time() if (st.get("value") or st.get("values")) else 0.0
            except Exception:
                ts = 0.0
            if ts >= best_ts:
                best = did
                best_ts = ts

    # fallback: nếu không cái nào có state, lấy cái đầu
    if not best and dids:
        best = dids[0]

    if best:
        devmap[slug_or_id] = best
        cache["device_map"] = devmap
        _save_user_cache(cache)
    return best

# ---------- REST: state JSON ----------
@app.get("/api/state")
def api_state(device_id: str = "gti283"):
    did = resolve_device_id(device_id) or device_id
    if not ensure_login():
        return JSONResponse({"detail": "login failed"}, status_code=500)

    st = _api.read_state_server(did) or {}
    raw = st.get("raw") or st

    # value -> numbers
    values: List[float] = []
    if "value" in st and isinstance(st["value"], str):
        values = parse_value_string(st["value"])
    elif "values" in st and isinstance(st["values"], list):
        values = st["values"]

    return {
        "raw": raw,
        "values": values,
        "labels": DEFAULT_LABELS[:len(values)],
        "ts": int(time.time()),
    }

# ---------- UI: routes ----------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/app/devices")

@app.get("/app", include_in_schema=False)
def app_root():
    return RedirectResponse(url="/app/devices")

@app.get("/app/devices", response_class=HTMLResponse)
def devices_page():
    # build danh sách từ "all"
    items: List[Dict[str, str]] = []
    ensure_login()
    raw = _api.read_state_server("all") or {}
    seen = set()
    if isinstance(raw, dict) and "data" in raw:
        for r in raw["data"]:
            did = r.get("deviceId") or r.get("device_id")
            if isinstance(did, str) and did.startswith("GTIControl") and did not in seen:
                seen.add(did)
                items.append({"id": did, "name": did})
    # nếu không có gì, vẫn hiển thị link mặc định gti283 (sẽ resolve)
    if not items:
        items.append({"id": "gti283", "name": "gti283"})

    return render("devices.html", items=items, app_title=APP_TITLE)

@app.get("/app/device/{device_id}", response_class=HTMLResponse)
def device_detail(device_id: str, tab: str = "stats"):
    did = resolve_device_id(device_id) or device_id
    data = api_state(did)
    # data có thể là JSONResponse khi lỗi
    if isinstance(data, JSONResponse):
        return render("device_detail.html", device_id=device_id, did=did, have=False, app_title=APP_TITLE)

    values = data.get("values") or []
    labels = data.get("labels") or []
    kv = []
    for i, v in enumerate(values):
        name = labels[i] if i < len(labels) else f"Chỉ số {i}"
        kv.append({"k": name, "v": v})

    return render(
        "device_detail.html",
        device_id=device_id,
        did=did,
        have=(len(values) > 0),
        kv=kv,
        raw=data.get("raw") or {},
        app_title=APP_TITLE
    )