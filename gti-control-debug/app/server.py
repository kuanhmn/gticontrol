import os, json, threading, time
from typing import Dict, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from paho.mqtt.client import Client

from api_client import APIClient
from coordinator import Coordinator

ADDON_OPTIONS_PATH = "/data/options.json"

def load_options() -> Dict:
    try:
        with open(ADDON_OPTIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

env = Environment(loader=FileSystemLoader("/app/templates"), autoescape=select_autoescape(['html','xml']))

app = FastAPI()
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

mqtt_client: Client = None
coordinator: Coordinator = None
device_ids: List[str] = []
api_client: APIClient = None

@app.get("/health")
def health():
    return {"ok": True, "ts": time.time()}

def start_system():
    global mqtt_client, coordinator, api_client, device_ids
    opt = load_options()

    mqtt_host = opt.get("mqtt_host") or os.getenv("MQTT_HOST") or "core-mosquitto"
    mqtt_port = int(opt.get("mqtt_port", 1883))
    mqtt_user = opt.get("mqtt_username") or os.getenv("MQTT_USERNAME")
    mqtt_pass = opt.get("mqtt_password") or os.getenv("MQTT_PASSWORD")

    try:
        mqtt_client = Client(client_id="gti-control-ui")
        if mqtt_user:
            mqtt_client.username_pw_set(mqtt_user, mqtt_pass)
        mqtt_client.connect(mqtt_host, mqtt_port, keepalive=60)
    except Exception as e:
        print("[gti] MQTT connect failed:", e)

    api_client = APIClient(opt)
    api_client.login()

    dids = []
    if opt.get("server_enabled", True):
        dids = api_client.list_devices()
    inc = opt.get("include_devices", [])
    if not dids and inc and inc != ["all"]:
        dids = inc
    if not dids:
        dids = ["gti283"]

    coordinator = Coordinator(mqtt_client, opt.get("mqtt_prefix","homeassistant"), opt, api_client)
    t = threading.Thread(target=coordinator.loop, args=(dids,), daemon=True)
    t.start()
    print("[gti] Started coordinator with devices:", dids)
    return dids

device_ids = start_system()

def render(tpl, **ctx):
    template = env.get_template(tpl)
    return HTMLResponse(template.render(**ctx))

@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse(url="/app/login")

@app.get("/app", response_class=HTMLResponse)
def app_root():
    return RedirectResponse(url="/app/login")

from starlette.responses import HTMLResponse, RedirectResponse

from starlette.responses import HTMLResponse, RedirectResponse

@app.get("/app/login", response_class=HTMLResponse)
def login_page():
    """
    Nếu đã có sẵn email/password trong Add-on Options
    hoặc đang bật google_oauth thì bỏ qua form và vào thẳng
    trang thiết bị.
    """
    opt = load_options()
    has_creds = bool(
        (opt.get("email") and opt.get("password")) or opt.get("google_oauth")
    )
    if has_creds:
        return RedirectResponse(url="/app/devices", status_code=302)
    return render("login.html")


@app.post("/app/login", response_class=HTMLResponse)
async def do_login(req: Request):
    """
    Đăng nhập qua form: lưu thẳng vào options của add-on rồi chuyển trang.
    (Yêu cầu đã cài `python-multipart` trong requirements.txt)
    """
    form = await req.form()
    email = (form.get("email") or "").strip()
    password = (form.get("password") or "").strip()

    opt = load_options()
    opt["email"] = email
    opt["password"] = password

    with open(ADDON_OPTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(opt, f, ensure_ascii=False, indent=2)

    start_system()
    return RedirectResponse(url="/app/devices", status_code=302)

@app.get("/app/devices", response_class=HTMLResponse)
def devices_page():
    return render("devices.html", devices=device_ids)

@app.get("/app/device/{device_id}", response_class=HTMLResponse)
def device_detail(device_id: str, tab: str = "stats"):
    st = (coordinator.state_cache.get(device_id, {}) if coordinator else {}) or {}
    schedules = api_client.get_schedules(device_id) if (api_client and coordinator and coordinator.server_enabled) else {}
    return render("device_detail.html",
                  device_id=device_id, tab=tab,
                  state=st, schedules=schedules,
                  use_server_daily_monthly=(coordinator.use_server_daily_monthly if coordinator else False),
                  server_enabled=(coordinator.server_enabled if coordinator else False))

@app.post("/app/device/{device_id}/set", response_class=HTMLResponse)
async def device_set(device_id: str, req: Request):
    if not coordinator or not coordinator.server_enabled:
        raise HTTPException(400, "Server disabled")
    form = await req.form()
    action = form.get("action")
    ok = False
    try:
        if action == "cutoff":
            val = float(form.get("cutoff_voltage") or 0)
            ok = api_client.set_cutoff_voltage(device_id, val)
        elif action == "maxpower":
            val = float(form.get("max_power_limit") or 0)
            ok = api_client.set_max_power(device_id, val)
        elif action and action.startswith("sched"):
            idx = int(action.replace("sched",""))
            start = form.get(f"schedule{idx}_start") or "00:00"
            end   = form.get(f"schedule{idx}_end") or "00:00"
            cv    = float(form.get(f"schedule{idx}_cutoff_voltage") or 0)
            mw    = float(form.get(f"schedule{idx}_max_power") or 0)
            ok = api_client.set_schedule(device_id, idx, start, end, cv, mw)
    except Exception:
        ok = False
    return RedirectResponse(url=f"/app/device/{device_id}?tab=settings", status_code=302)
