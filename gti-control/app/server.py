import os, json, threading
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from paho.mqtt.client import Client

from api_client import APIClient
from coordinator import Coordinator

ADDON_OPTIONS_PATH = "/data/options.json"

def load_options() -> Dict:
    with open(ADDON_OPTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

env = Environment(
    loader=FileSystemLoader("/app/templates"),
    autoescape=select_autoescape(['html', 'xml'])
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

mqtt_client = None
coordinator = None
device_ids: List[str] = []
api_client = None

def start_system():
    global mqtt_client, coordinator, api_client, device_ids
    opt = load_options()
    mqtt_cfg = {
        "host": opt.get("mqtt_host") or os.getenv("MQTT_HOST") or "127.0.0.1",
        "port": int(opt.get("mqtt_port", 1883)),
        "username": opt.get("mqtt_username") or os.getenv("MQTT_USERNAME"),
        "password": opt.get("mqtt_password") or os.getenv("MQTT_PASSWORD")
    }
    mqtt_client = Client(client_id="gti-control-ui")
    if mqtt_cfg["username"]:
        mqtt_client.username_pw_set(mqtt_cfg["username"], mqtt_cfg["password"])
    try:
        mqtt_client.connect(mqtt_cfg["host"], mqtt_cfg["port"], keepalive=60)
    except Exception as e:
        print("[gti] MQTT connect failed:", e)

    api_client = APIClient(opt)
    api_client.login()

    dids = []
    if opt.get("server_enabled", True):
        dids = api_client.list_devices()
    if not dids:
        inc = opt.get("include_devices", [])
        if inc and inc != ["all"]:
            dids = inc
    if not dids:
        dids = ["gti283"]

    coordinator = Coordinator(mqtt_client, opt.get("mqtt_prefix","homeassistant"), opt, api_client)
    t = threading.Thread(target=coordinator.loop, args=(dids,), daemon=True)
    t.start()
    return dids

device_ids = start_system()

def render(tpl, **ctx):
    template = env.get_template(tpl)
    return HTMLResponse(template.render(**ctx))

@app.get("/app", response_class=HTMLResponse)
def root():
    return RedirectResponse(url="/app/login")

@app.get("/app/login", response_class=HTMLResponse)
def login_page():
    return render("login.html")

@app.post("/app/login", response_class=HTMLResponse)
async def do_login(req: Request):
    form = await req.form()
    email = form.get("email") or ""
    password = form.get("password") or ""
    opt = load_options()
    opt["email"] = email
    opt["password"] = password
    with open(ADDON_OPTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(opt, f, ensure_ascii=False, indent=2)
    global device_ids
    device_ids = start_system()
    return RedirectResponse(url="/app/devices", status_code=302)

@app.get("/app/devices", response_class=HTMLResponse)
def devices_page():
    return render("devices.html", devices=device_ids)

@app.get("/app/device/{device_id}", response_class=HTMLResponse)
def device_detail(device_id: str, tab: str = "stats"):
    st = coordinator.state_cache.get(device_id, {})
    schedules = {}
    return render("device_detail.html",
                  device_id=device_id, tab=tab,
                  state=st, schedules=schedules,
                  use_server_daily_monthly=coordinator.use_server_daily_monthly,
                  server_enabled=coordinator.server_enabled)
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

try:
    app  # nếu đã khai báo ở trên thì giữ
except NameError:
    app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "GTI Control running", "path": "/"}

@app.get("/app")
def go_app():
    return RedirectResponse("/")