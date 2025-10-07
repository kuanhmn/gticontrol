# -*- coding: utf-8 -*-
"""
FastAPI cho add-on GTI Control
Routes:
- GET /api/which
- GET /api/devices
- GET /api/state?device_id=...
"""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from api_client import APIClient, load_options

app = FastAPI(title="GTI Control")

# 1 client dùng chung
_opts = load_options()
_api = APIClient(_opts)


def _ensure_login() -> bool:
    try:
        return _api.login()
    except Exception as e:
        print("LOGIN error:", e)
        return False


@app.get("/api/which")
def api_which():
    ok = _ensure_login()
    info = {
        "login": ok,
        "uid": _api.uid,
        "bound_device": _api.device_id,
        "device_ids": _api.device_ids,
        "server_base_url": _api.server_base_url,
        "device_suffixes": _opts.get("device_suffixes", ""),
        "include_devices": _opts.get("include_devices", []),
    }
    return JSONResponse(info)


@app.get("/api/devices")
def api_devices():
    if not _ensure_login():
        return JSONResponse({"error": "login failed"}, status_code=401)
    items = _api.list_devices()
    # gợi ý device pick
    picked = _api.ensure_device()
    return JSONResponse({"devices": items, "picked": picked, "uid": _api.uid})


@app.get("/api/state")
def api_state(device_id: str | None = Query(default=None, description="GTIControlXXX hoặc gtiXXX")):
    if not _ensure_login():
        return JSONResponse({"error": "login failed"}, status_code=401)

    st = _api.read_state_server(device_id=device_id)
    if not st:
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    return JSONResponse(st)
