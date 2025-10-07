# app/server.py
import os
import time
import asyncio
from typing import Dict, Any, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from api_client import APIClient, load_options

app = FastAPI()

# mount /static nếu thư mục tồn tại (tránh lỗi 502 nếu không có)
if os.path.isdir("/app/static"):
    app.mount("/static", StaticFiles(directory="/app/static"), name="static")

templates = Jinja2Templates(directory="/app/templates")

api_client: APIClient | None = None
latest_state: Dict[str, Any] = {}

def parse_value_str(v: str) -> List[float]:
    out: List[float] = []
    for p in (v or "").split("#"):
        p = p.strip()
        if not p:
            continue
        try:
            out.append(float(p))
        except Exception:
            pass
    return out

async def poll_loop():
    global latest_state
    opt = load_options()
    scan = int(opt.get("scan_interval", 30)) or 30
    include = opt.get("include_devices") or ["gti283"]
    device_hint = include[0] if include else "gti283"

    while True:
        try:
            st = api_client.read_state_server(device_hint) if api_client else {}
            if st:
                vals = parse_value_str(st.get("value", ""))
                latest_state = {
                    "raw": st,
                    "values": vals,
                    "ts": time.time(),
                }
                print("[coord] server state", device_hint, st.get("deviceId"), st.get("updatedAt"))
        except Exception as e:
            print("[coord] read error:", e)
        await asyncio.sleep(scan)

@app.on_event("startup")
async def _startup():
    global api_client
    opt = load_options()
    api_client = APIClient(opt)
    ok = api_client.login(force=True)
    print("[api] login at startup:", ok, "uid:", api_client.uid)
    asyncio.create_task(poll_loop())

# ---------------- UI routes (đơn giản để bạn test nhanh) ----------------

@app.get("/", response_class=HTMLResponse)
def _root():
    return RedirectResponse(url="/app/devices")

@app.get("/app/devices", response_class=HTMLResponse)
def devices_page():
    raw = latest_state.get("raw") or {}
    vals = latest_state.get("values") or []
    ctx = {
        "request": {},   # Jinja2Templates yêu cầu
        "devices": ["gti283"],
        "device_id": raw.get("deviceId"),
        "updated": raw.get("updatedAt"),
        # vài cột minh hoạ; bạn map lại theo ý muốn
        "pv_power": vals[0] if len(vals) > 0 else None,
        "grid_voltage": vals[8] if len(vals) > 8 else None,
        "mosfet_temp": vals[10] if len(vals) > 10 else None,
    }
    # Nếu bạn đã có template devices.html riêng, nó sẽ render đẹp hơn.
    # Tạm thời, trả HTML đơn giản nếu thiếu template.
    tpl_path = "/app/templates/devices.html"
    if os.path.isfile(tpl_path):
        return templates.TemplateResponse("devices.html", ctx)
    # fallback HTML giản lược
    body = f"""
    <html><body style="font-family: sans-serif;">
      <h2>GTI Control</h2>
      <div>Device: {ctx["device_id"] or "-"}</div>
      <div>Updated: {ctx["updated"] or "-"}</div>
      <div>PV Power: {ctx["pv_power"]}</div>
      <div>Grid V: {ctx["grid_voltage"]}</div>
      <div>Mosfet °C: {ctx["mosfet_temp"]}</div>
    </body></html>
    """
    return HTMLResponse(body)

# Debug JSON
@app.get("/api/state")
def api_state():
    return JSONResponse(latest_state or {})