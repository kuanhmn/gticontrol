# /app/server.py
import os
import json
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from paho.mqtt.client import Client

from api_client import APIClient
from coordinator import Coordinator

LOG = logging.getLogger("gti")
LOG.setLevel(logging.INFO)

# ----- Paths -----
ADDON_OPTIONS_PATH = "/data/options.json"          # do Supervisor mount (CHỈ ĐỌC)
USER_OPTIONS_PATH  = "/data/user_options.json"     # lưu thêm khi login bằng form

# ----- Jinja2 env -----
env = Environment(
    loader=FileSystemLoader("/app/templates"),
    autoescape=select_autoescape(["html", "xml"]),
)
def render(tpl: str, **ctx) -> HTMLResponse:
    template = env.get_template(tpl)
    return HTMLResponse(template.render(**ctx))

# ----- FastAPI app -----
app = FastAPI()

# Mount static nếu có thư mục
if os.path.isdir("/app/static"):
    app.mount("/static", StaticFiles(directory="/app/static"), name="static")

# ----- Globals runtime -----
mqtt_client: Optional[Client] = None
coordinator: Optional[Coordinator] = None
api_client: Optional[APIClient] = None
device_ids: List[str] = []

# ===== Helper =====
def _load_json(path: str) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_options() -> Dict:
    """Ưu tiên options.json từ Supervisor; thiếu mục nào thì lấy từ user_options.json."""
    main = _load_json(ADDON_OPTIONS_PATH)
    user = _load_json(USER_OPTIONS_PATH)
    # main ưu tiên: merge sao cho main ghi đè user
    merged = {**user, **main}
    return merged

def has_config_creds() -> bool:
    opt = load_options()
    email = (opt.get("email") or "").strip()
    pw    = (opt.get("password") or "").strip()
    ok = bool(email and pw) or bool(opt.get("google_oauth"))
    LOG.info("[gti] creds_from_config=%s email_set=%s google_oauth=%s",
             ok, bool(email), bool(opt.get("google_oauth")))
    return ok

def _mqtt_connect_from_options(opt: Dict) -> Optional[Client]:
    host = opt.get("mqtt_host") or os.getenv("MQTT_HOST") or "127.0.0.1"
    port = int(opt.get("mqtt_port", 1883))
    user = opt.get("mqtt_username") or os.getenv("MQTT_USERNAME")
    pwd  = opt.get("mqtt_password") or os.getenv("MQTT_PASSWORD")
    try:
        c = Client(client_id="gti-control-ui")
        if user:
            c.username_pw_set(user, pwd)
        c.connect(host, port, keepalive=60)
        return c
    except Exception as e:
        LOG.error("[gti] MQTT connect failed: %s", e)
        return None

def start_system() -> List[str]:
    """Khởi tạo API client, MQTT, Coordinator, và vòng publish."""
    global mqtt_client, coordinator, api_client, device_ids
    opt = load_options()

    # MQTT publish (HA Discovery/state)
    if mqtt_client is None:
        mqtt_client = _mqtt_connect_from_options(opt)

    # API Client (server side)
    api_client = APIClient(opt)
    try:
        api_client.login()
    except Exception as e:
        LOG.error("[gti] api_client.login() error: %s", e)

    # Populate devices
    dids: List[str] = []
    if opt.get("server_enabled", True):
        try:
            dids = api_client.list_devices()
        except Exception as e:
            LOG.error("[gti] list_devices error: %s", e)

    if not dids:
        inc = opt.get("include_devices", [])
        if inc and inc != ["all"]:
            dids = inc

    if not dids:
        dids = ["gti283"]  # fallback demo id

    device_ids = dids

    # Coordinator
    if coordinator is None:
        disc_prefix = opt.get("mqtt_prefix", "homeassistant")
        coordinator = Coordinator(mqtt_client, disc_prefix, opt, api_client)
        import threading, time
        t = threading.Thread(target=coordinator.loop, args=(dids,), daemon=True)
        t.start()
    else:
        # nếu đã có coordinator thì chỉ cập nhật danh sách thiết bị (nếu muốn)
        pass

    LOG.info("[gti] Started coordinator with devices: %s", device_ids)
    return device_ids

# ===== Lifecycle =====
@app.on_event("startup")
async def on_startup():
    # nếu đã có creds trong config thì auto start
    if has_config_creds():
        start_system()

# ===== Routes =====
@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

@app.get("/", include_in_schema=False)
def root():
    if has_config_creds():
        return RedirectResponse(url="/app/devices", status_code=302)
    return RedirectResponse(url="/app/login", status_code=302)

@app.get("/app", include_in_schema=False)
def app_root():
    return RedirectResponse(url="/app/login", status_code=302)

@app.get("/app/login", response_class=HTMLResponse)
def login_page():
    if has_config_creds():
        # đã có cấu hình → bỏ qua login
        return RedirectResponse(url="/app/devices", status_code=302)
    return render("login.html")

@app.post("/app/login", response_class=HTMLResponse)
async def do_login(req: Request):
    """Đăng nhập qua form: ghi vào USER_OPTIONS_PATH, KHÔNG ghi đè options.json."""
    try:
        form = await req.form()  # cần python-multipart
        email = (form.get("email") or "").strip()
        password = (form.get("password") or "").strip()
        opt = load_options()
        opt["email"] = email
        opt["password"] = password
        os.makedirs("/data", exist_ok=True)
        with open(USER_OPTIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(opt, f, ensure_ascii=False, indent=2)
        start_system()
        return RedirectResponse(url="/app/devices", status_code=302)
    except Exception as e:
        LOG.exception("[gti] /app/login error: %s", e)
        raise HTTPException(400, f"Login error: {e}")

@app.get("/app/devices", response_class=HTMLResponse)
def devices_page():
    # đảm bảo hệ thống đã khởi động khi vào thẳng URL này
    if not has_config_creds():
        return RedirectResponse(url="/app/login", status_code=302)
    if coordinator is None:
        start_system()
    return render("devices.html", devices=device_ids)

@app.get("/app/device/{device_id}", response_class=HTMLResponse)
def device_detail(device_id: str, tab: str = "stats"):
    if coordinator is None:
        if not has_config_creds():
            return RedirectResponse(url="/app/login", status_code=302)
        start_system()
    st = {}
    try:
        st = coordinator.state_cache.get(device_id, {}) if coordinator else {}
    except Exception:
        st = {}
    schedules = {}
    try:
        if api_client and load_options().get("server_enabled", True):
            schedules = api_client.get_schedules(device_id) or {}
    except Exception as e:
        LOG.error("[gti] get_schedules error: %s", e)

    return render(
        "device_detail.html",
        device_id=device_id,
        tab=tab,
        state=st,
        schedules=schedules,
        use_server_daily_monthly=load_options().get("use_server_daily_monthly", True),
        server_enabled=load_options().get("server_enabled", True),
    )

@app.post("/app/device/{device_id}/set", response_class=HTMLResponse)
async def device_set(device_id: str, req: Request):
    if not load_options().get("server_enabled", True):
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
            idx = int(action.replace("sched", ""))
            start = form.get(f"schedule{idx}_start") or "00:00"
            end   = form.get(f"schedule{idx}_end") or "00:00"
            cv    = float(form.get(f"schedule{idx}_cutoff_voltage") or 0)
            mw    = float(form.get(f"schedule{idx}_max_power") or 0)
            ok = api_client.set_schedule(device_id, idx, start, end, cv, mw)
    except Exception as e:
        LOG.error("[gti] device_set error: %s", e)
        ok = False

    # quay lại tab settings
    return RedirectResponse(url=f"/app/device/{device_id}?tab=settings", status_code=302)