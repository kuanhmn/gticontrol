# /app/server.py
from __future__ import annotations
import json, os, threading, time, logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Re-use API client & options from your current add-on
from api_client import APIClient, load_options  # <-- giữ nguyên file api_client.py hiện tại

APP_TITLE = "GTI Control"
USER_PATH = "/data/user_options.json"

app = FastAPI(title=APP_TITLE)
env = Environment(loader=FileSystemLoader("/app/templates"),
                  autoescape=select_autoescape(["html", "xml"]))

def render(tpl: str, **ctx):
    tplobj = env.get_template(tpl)
    return HTMLResponse(tplobj.render(**ctx))

_opts = load_options()
_api = APIClient(_opts)

_api_lock = threading.Lock()
logger = logging.getLogger("gti_control")
logger.setLevel(logging.DEBUG)


def ensure_login() -> bool:
    try:
        with _api_lock:
            ok = _api.login()
            return bool(ok)
    except Exception as e:
        logger.exception("ensure_login failed: %s", e)
        return False

def api_devices() -> List[str]:
    """
    Trả về danh sách device ids mà UI sẽ show.
    Nguyên tắc:
     - Nếu options.include_devices có giá trị (list hoặc "all"), dùng list đó (normalize).
     - Ngược lại, gọi read_state_server("all"), chọn các rows mà userId==api.uid (hoặc localId==api.uid).
     - Chỉ chọn deviceId bắt đầu bằng GTIControl (như app gốc), để lọc khác.
    """
    # load options each call (để thay đổi config không cần restart)
    opts = load_options()
    inc = opts.get("include_devices")
    if inc:
        # normalize include_devices: có thể là list or csv string
        if isinstance(inc, str):
            inc_list = [s.strip() for s in inc.split(",") if s.strip()]
        elif isinstance(inc, list):
            inc_list = list(inc)
        else:
            inc_list = []
        # if contains "all", return that marker to UI (we'll still list server devices later)
        if "all" in [x.lower() if isinstance(x,str) else x for x in inc_list]:
            # return empty to mean "use server's all devices" -- caller may call read_state_server
            return []
        # ensure GTIControl prefix if user provided only suffix numbers
        normalized = []
        for d in inc_list:
            if isinstance(d, str):
                if d.startswith("GTIControl"):
                    normalized.append(d)
                else:
                    # user might have provided suffix only, e.g. "283", or "283,426"
                    if d.isdigit() or (len(d)>0 and d.replace('-','').isdigit()):
                        normalized.append(f"GTIControl{d}")
                    else:
                        normalized.append(d)
        return sorted(list(dict.fromkeys(normalized)))  # dedupe, keep order

    # otherwise, read server state and filter by user id
    if not ensure_login():
        return []

    try:
        raw_all = _api.read_state_server("all") or {}
    except Exception as e:
        logger.exception("read_state_server failed: %s", e)
        return []

    matches = []
    uid_candidates = set()
    # prefer an explicit api.uid attribute (set by login)
    api_uid = getattr(_api, "uid", None) or getattr(_api, "user_id", None)

    if isinstance(raw_all, dict) and "data" in raw_all:
        for row in raw_all["data"]:
            try:
                did = row.get("deviceId") or row.get("device_id")
                # normalise possible integer suffix or full GTIControl...
                if not isinstance(did, str):
                    continue
                if not did.startswith("GTIControl"):
                    continue
                # If the row has a userId or localId field, check it
                row_user = row.get("userId") or row.get("user_id") or row.get("localId")
                if api_uid:
                    # match only devices that belong to logged-in user
                    if isinstance(row_user, str) and row_user == api_uid:
                        if did not in matches:
                            matches.append(did)
                    else:
                        # skip other users' devices
                        continue
                else:
                    # if we don't have a login uid, try to collect devices where userId present (best-effort)
                    if isinstance(row_user, str):
                        if did not in matches:
                            matches.append(did)
                    else:
                        # last-resort: include device if no userId existed
                        if did not in matches:
                            matches.append(did)
            except Exception:
                continue

    return sorted(matches)


# ---- basic routes
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/app/devices")

@app.get("/app", include_in_schema=False)
def app_root():
    return RedirectResponse(url="/app/devices")

@app.get("/app/devices", response_class=HTMLResponse)
def devices_page():
    # get device ids to render
    devs = api_devices()
    # if include_devices was empty list AND api_devices returned empty -> show message
    return render("devices.html", device_ids=sorted(devs))
