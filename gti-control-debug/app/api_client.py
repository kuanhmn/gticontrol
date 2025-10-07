# -*- coding: utf-8 -*-
"""
API client cho GTI Control add-on.
- Đăng nhập Google IdentityToolkit bằng API key trong /data/options.json
- Cache idToken/localId vào /data/user_options.json để dùng lại
- Đọc dữ liệu từ server theo endpoint hoạt động:
    GET {base}/api/inverter/data?uid={UID}&deviceId={DEVICE_ID}
"""

from __future__ import annotations

import os
import json
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

import requests


OPTIONS_PATH = "/data/options.json"
USER_PATH = "/data/user_options.json"


def _safe_json_load(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_options() -> dict:
    j = _safe_json_load(OPTIONS_PATH) or {}
    # vệ sinh khoảng trắng các trường quan trọng
    for k in ("firebase_api_key", "email", "password", "server_base_url"):
        if isinstance(j.get(k), str):
            j[k] = j[k].strip()
    return j


class APIClient:
    def __init__(self, opts: dict):
        self.base: str = (opts.get("server_base_url") or "").rstrip("/")
        self.email: str = opts.get("email") or ""
        self.pw: str = opts.get("password") or ""
        self.api_key: str = opts.get("firebase_api_key") or ""
        self.server_enabled: bool = bool(opts.get("server_enabled", True))

        self.s = requests.Session()
        self._lock = threading.Lock()

        # token cache
        self.id_token: Optional[str] = None
        self.uid: Optional[str] = None
        self.exp_at: int = 0

        # nạp cache cũ nếu có
        cache = _safe_json_load(USER_PATH)
        if cache:
            self.id_token = cache.get("idToken") or cache.get("id_token")
            self.uid = cache.get("localId") or cache.get("uid") or cache.get("user_id")
            self.exp_at = int(cache.get("expires_at") or 0)

    # ---------- tiện ích ----------
    def _log(self, *args):
        print("[api]", *args, flush=True)

    def _have_valid_token(self) -> bool:
        return bool(self.id_token and (self.exp_at - int(time.time()) > 60))

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(USER_PATH), exist_ok=True)
            with open(USER_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "localId": self.uid,
                        "idToken": self.id_token,
                        "expires_at": self.exp_at,
                        "server_base_url": self.base,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            self._log("cannot write user_options.json:", e)

    def _auth_headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self.id_token:
            h["Authorization"] = f"Bearer {self.id_token}"
        return h

    def _get_json(self, url: str) -> Tuple[Optional[dict], int, str]:
        try:
            self._log("GET", url)
            r = self.s.get(url, headers=self._auth_headers(), timeout=20)
            ct = r.headers.get("content-type", "")
            self._log("->", r.status_code)
            if r.ok and "application/json" in ct.lower():
                return r.json(), r.status_code, ct
            # log body đầu 400 ký tự để dễ debug
            body = (r.text or "")[:400]
            self._log("non-json body:", body)
            return None, r.status_code, ct
        except Exception as e:
            self._log("GET error:", e)
            return None, 0, ""

    # ---------- đăng nhập ----------
    def login(self, force: bool = False) -> bool:
        if not self.server_enabled:
            self._log("server disabled")
            return True

        if not force and self._have_valid_token():
            self._log("already have valid token (cached)")
            return True

        if not (self.api_key and self.email and self.pw):
            self._log("missing firebase_api_key/email/password")
            return False

        key = self.api_key.strip()
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"
        payload = {"email": self.email, "password": self.pw, "returnSecureToken": True}

        try:
            mk = f"{key[:6]}…{key[-4:]}" if len(key) >= 12 else key
            self._log("POST", url.replace(key, mk))
            r = self.s.post(url, json=payload, timeout=20)
            self._log("->", r.status_code)
            if not r.ok:
                self._log("login fail body:", (r.text or "")[:400])
                return False

            j = r.json()
            self.id_token = j.get("idToken")
            self.uid = j.get("localId")
            expires_in = int(j.get("expiresIn") or 3600)
            self.exp_at = int(time.time()) + expires_in
            self._save_cache()
            self._log("login ok uid=", self.uid, "valid_for=", f"{expires_in}s")
            return True
        except Exception as e:
            self._log("login exception:", e)
            return False

    # ---------- đọc danh sách thiết bị ----------
    def list_devices(self) -> List[str]:
        """
        Lấy các deviceId xuất hiện trong bảng dữ liệu (từ endpoint hoạt động).
        """
        if not self.uid and not self.login():
            return []
        url = f"{self.base}/api/inverter/data?uid={self.uid}"
        j, _, _ = self._get_json(url)
        if not j:
            return []
        ids = []
        for it in j.get("data", []):
            dev = it.get("deviceId")
            if dev and dev not in ids:
                ids.append(dev)
        return ids

    # ---------- đọc trạng thái 1 thiết bị ----------
    def read_state_server(self, device_id: str) -> dict:
        """
        Thử cả 'gti283' và '283' theo định dạng server hiện có.
        Trả về record JSON (giữ 'value' thô) — add-on phần khác sẽ parse/mapping.
        """
        if not self.uid and not self.login():
            return {}

        cand = [device_id]
        # nếu dạng gti### thì thêm dạng số
        if device_id.lower().startswith("gti"):
            cand.append(device_id[3:])
        else:
            # nếu là số, thêm dạng gti###
            if device_id.isdigit():
                cand.append("gti" + device_id)

        for did in cand:
            url = f"{self.base}/api/inverter/data?uid={self.uid}&deviceId={did}"
            j, _, _ = self._get_json(url)
            if not j:
                continue
            arr = j.get("data") or []
            if not arr:
                continue
            # bản ghi mới nhất ở đầu mảng (theo server hiện hữu)
            rec = arr[0]
            # chỉ trả lại các trường cần dùng — 'value' sẽ parse ở nơi khác
            return {
                "deviceId": rec.get("deviceId"),
                "userId": rec.get("userId"),
                "createdAt": rec.get("createdAt"),
                "updatedAt": rec.get("updatedAt"),
                "value": rec.get("value", ""),
                "raw": rec,
            }
        return {}

    # ---------- đọc daily/monthly nếu sau này cần ----------
    def read_daily(self, device_id: str) -> dict:
        # nếu server có route riêng cho daily -> cập nhật tại đây
        return {}

    def read_monthly(self, device_id: str) -> dict:
        # nếu server có route riêng cho monthly -> cập nhật tại đây
        return {}