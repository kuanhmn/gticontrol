# app/api_client.py
import os
import json
import time
import threading
import requests
from typing import Dict, Any, Optional, List

OPTIONS_PATH = "/data/options.json"
USER_PATH = "/data/user_options.json"

def load_options() -> Dict[str, Any]:
    with open(OPTIONS_PATH, "r", encoding="utf-8") as f:
        j = json.load(f)
    # strip khoảng trắng “vô hình”
    for k in ("firebase_api_key", "email", "password", "server_base_url"):
        v = j.get(k)
        if isinstance(v, str):
            j[k] = v.strip()
    return j


class APIClient:
    """Client lo phần login + gọi REST tới server giabao-inverter."""

    def __init__(self, opts: Dict[str, Any]):
        self.base = (opts.get("server_base_url") or "").rstrip("/")
        self.email = opts.get("email") or ""
        self.password = opts.get("password") or ""
        self.api_key = opts.get("firebase_api_key") or ""
        self.server_enabled = bool(opts.get("server_enabled", True))
        self.s = requests.Session()

        self._lock = threading.Lock()
        self.id_token: Optional[str] = None
        self.uid: Optional[str] = None
        self.exp_at: int = 0  # epoch seconds

        # nạp cache nếu có
        if os.path.exists(USER_PATH):
            try:
                c = json.load(open(USER_PATH, "r", encoding="utf-8"))
                self.id_token = c.get("idToken")
                self.uid = c.get("localId")
                self.exp_at = int(c.get("expires_at") or 0)
            except Exception:
                pass

    # ---------- nội bộ ----------
    def _save_cache(self, id_token: str, uid: str, expires_in: int) -> None:
        self.id_token = id_token
        self.uid = uid
        self.exp_at = int(time.time()) + int(expires_in or 3600)
        save = {
            "idToken": self.id_token,
            "localId": self.uid,
            "expires_at": self.exp_at,
            "server_base_url": self.base,
        }
        os.makedirs(os.path.dirname(USER_PATH), exist_ok=True)
        with open(USER_PATH, "w", encoding="utf-8") as f:
            json.dump(save, f, ensure_ascii=False, indent=2)

    def _token_valid(self) -> bool:
        # còn >60s coi như hợp lệ
        return bool(self.id_token) and (time.time() < (self.exp_at - 60))

from api_client import load_options

opt = load_options()

# nếu có device_suffixes thì map sang include_devices
suffixes = opt.get("device_suffixes", "")
if suffixes:
    suffix_list = [s.strip() for s in suffixes.split(",") if s.strip()]
    include_devices = [f"GTIControl{s}" for s in suffix_list]
    opt["include_devices"] = include_devices

    # ---------- public ----------
    def login(self, force: bool = False) -> bool:
        """Login Firebase. Trả True nếu OK (hoặc đã có token hợp lệ)."""
        if not self.server_enabled:
            print("[api] server disabled")
            return True

        with self._lock:
            if (not force) and self._token_valid():
                print("[api] already have valid token")
                return True

            if not (self.api_key and self.email and self.password):
                print("[api] missing api_key/email/password in options.json")
                return False

            url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
            params = {"key": self.api_key}
            payload = {
                "email": self.email,
                "password": self.password,
                "returnSecureToken": True,
            }
            try:
                print(f"[api] POST {url}?key={self.api_key[:6]}…{self.api_key[-4:]}")
                r = self.s.post(url, params=params, json=payload, timeout=20)
                print("[api] ->", r.status_code)
                if not r.ok:
                    # không log token hay thông tin nhạy cảm
                    print("[api] firebase FAIL (masked)", (r.text or "")[:180])
                    return False
                j = r.json()
                idt = j.get("idToken")
                uid = j.get("localId")
                exp = int(j.get("expiresIn") or 3600)
                if not (idt and uid):
                    print("[api] login response missing token/uid")
                    return False
                self._save_cache(idt, uid, exp)
                print("[api] login ok uid=", uid, "valid_for=", exp, "s")
                return True
            except Exception as e:
                print("[api] login exception:", e)
                return False

    def read_state_server(self, device_hint: str) -> Dict[str, Any]:
        """
        Lấy bản ghi mới nhất cho user từ server.
        Ưu tiên: /api/inverter/data?uid=<uid>&deviceId=<device_hint>
        Fallback: /api/inverter/data?uid=<uid>
        Trả về dict rỗng nếu không có dữ liệu.
        """
        if not self.login():
            return {}

        def _get(url: str) -> Optional[Dict[str, Any]]:
            h = {
                "Authorization": f"Bearer {self.id_token}",
                "Accept": "application/json",
            }
            r = self.s.get(url, headers=h, timeout=15)
            print("[api] GET", url)
            print("[api] ->", r.status_code)
            if not r.ok:
                return None
            try:
                return r.json()
            except Exception:
                return None

        base = self.base.rstrip("/")
        # 1) theo device_hint (gti283 / 283)
        url1 = f"{base}/api/inverter/data?uid={self.uid}&deviceId={device_hint}"
        j = _get(url1)
        rows: List[Dict[str, Any]] = j.get("data", []) if isinstance(j, dict) else []

        # 2) fallback theo uid
        if not rows:
            url2 = f"{base}/api/inverter/data?uid={self.uid}"
            j2 = _get(url2)
            rows = j2.get("data", []) if isinstance(j2, dict) else []

        if not rows:
            return {}

        rows.sort(key=lambda x: x.get("updatedAt") or x.get("createdAt") or "", reverse=True)
        row = rows[0]
        val = (row.get("value") or "").strip()

        return {
            "deviceId": row.get("deviceId"),
            "userId": row.get("userId"),
            "createdAt": row.get("createdAt"),
            "updatedAt": row.get("updatedAt"),
            "value": val,
            "raw": row,
        }