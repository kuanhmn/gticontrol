# -*- coding: utf-8 -*-
"""
API client cho add-on GTI Control
- Đọc options ở /data/options.json
- Đăng nhập Firebase (email/password + firebase_api_key)
- Lấy danh sách thiết bị thuộc tài khoản
- Chọn đúng device theo ưu tiên:
    1) device_suffixes: "283,468"  ->  ["GTIControl283","GTIControl468"]
    2) include_devices (nếu repo cũ còn dùng)
    3) thiết bị có userId == UID hoặc thiết bị cập nhật mới nhất
- Đọc state từ server_base_url
"""

from __future__ import annotations

import json, os, threading, time
from typing import Any, Dict, List, Optional

import requests

# ------------------------------------------------------------
# Đường dẫn lưu cache nhẹ (token / uid / device đã chọn)
USER_PATH = "/data/.gti_client.json"


def _load_options() -> Dict[str, Any]:
    try:
        with open("/data/options.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _now() -> float:
    return time.time()


def _parse_float(x: str) -> Optional[float]:
    try:
        return float(x)
    except Exception:
        return None


class APIClient:
    def __init__(self, opt: Optional[Dict[str, Any]] = None) -> None:
        self.opt: Dict[str, Any] = opt or _load_options()
        self.email: str = self.opt.get("email", "") or ""
        self.password: str = self.opt.get("password", "") or ""
        self.firebase_api_key: str = self.opt.get("firebase_api_key", "") or ""
        self.server_base_url: str = (self.opt.get("server_base_url") or "https://giabao-inverter.com").rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "GTIControl/HA"})

        # token & user
        self.id_token: Optional[str] = None
        self.uid: Optional[str] = None
        self.exp_at: float = 0.0

        # devices
        self.device_ids: List[str] = []
        self.device_id: Optional[str] = None  # thiết bị đang bound

        self._lock = threading.Lock()
        self._load_user_cache()

    # ---------------- persistence ----------------
    def _load_user_cache(self) -> None:
        try:
            with open(USER_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.id_token = data.get("id_token") or None
            self.uid = data.get("uid") or None
            self.exp_at = float(data.get("exp_at") or 0)
            self.device_id = data.get("device_id") or None
        except Exception:
            pass

    def _save_user_cache(self) -> None:
        data = {
            "id_token": self.id_token,
            "uid": self.uid,
            "exp_at": self.exp_at,
            "device_id": self.device_id,
        }
        os.makedirs(os.path.dirname(USER_PATH), exist_ok=True)
        with open(USER_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------------- auth ----------------
    def _token_valid(self) -> bool:
        return bool(self.id_token) and (_now() < (self.exp_at - 60))

    def login(self, force: bool = False) -> bool:
        if not force and self._token_valid():
            return True

        if not (self.email and self.password and self.firebase_api_key):
            print("[api] missing email/password/firebase_api_key")
            return False

        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.firebase_api_key}"
        payload = {"email": self.email, "password": self.password, "returnSecureToken": True}

        r = self.session.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            try:
                err = r.json()
            except Exception:
                err = {"message": r.text}
            print("[api] firebase FAIL:", err)
            return False

        data = r.json()
        self.id_token = data.get("idToken")
        self.uid = data.get("localId") or data.get("localID") or data.get("uid")
        valid_for = int(data.get("expiresIn", "3600"))
        self.exp_at = _now() + valid_for
        self._save_user_cache()
        print(f"[api] login ok uid= {self.uid} valid_for= {valid_for}s")
        return True

    # ---------------- device helpers ----------------
    @staticmethod
    def _normalize_did(x: str) -> str:
        """Chấp nhận 'gti283'/'GTIControl283' -> 'GTIControl283'"""
        if not x:
            return x
        xs = x.strip()
        if xs.lower().startswith("gti"):
            # 'gti283' or 'gticontrol283'
            num = "".join(ch for ch in xs if ch.isdigit())
            if num:
                return f"GTIControl{num}"
        return xs

    def _want_devices_from_options(self) -> List[str]:
        want: List[str] = []

        # device_suffixes: "283,468"
        suffixes = (self.opt.get("device_suffixes") or "").strip()
        if suffixes:
            for s in [p.strip() for p in suffixes.replace(";", ",").split(",") if p.strip()]:
                want.append(f"GTIControl{s}")

        # include_devices: ["GTIControl283", "gti468", ...]
        inc = self.opt.get("include_devices") or []
        if isinstance(inc, list):
            for x in inc:
                if isinstance(x, str) and x.strip().lower() != "all":
                    want.append(self._normalize_did(x))
        # loại trùng
        seen = set()
        out: List[str] = []
        for d in want:
            if d not in seen:
                out.append(d)
                seen.add(d)
        return out

    def list_devices(self) -> List[Dict[str, Any]]:
        """Trả về list các dict thô server trả về (ít nhất có deviceId, userId, updatedAt, raw/value...)"""
        if not self.login():
            return []

        url = f"{self.server_base_url}/api/inverter/data"
        params = {"uid": self.uid, "deviceId": "all"}

        r = self.session.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print("[api] GET devices FAIL", r.status_code, r.text[:200])
            return []

        data = r.json()
        items: List[Dict[str, Any]] = []
        # API có 2 kiểu: {data:[{...},...]} hoặc trả thẳng list
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            items = data["data"]
        elif isinstance(data, list):
            items = data
        # lưu danh sách id
        self.device_ids = []
        for d in items:
            did = d.get("deviceId") or d.get("device_id")
            if isinstance(did, str):
                self.device_ids.append(did)
        return items

    def _choose_device(self) -> Optional[str]:
        items = self.list_devices()
        if not items:
            return None

        # ưu tiên theo options
        want = self._want_devices_from_options()
        if want:
            for w in want:
                for d in items:
                    if (d.get("deviceId") or "").strip() == w:
                        return w

        # ưu tiên userId == uid
        for d in items:
            if d.get("userId") == self.uid and isinstance(d.get("deviceId"), str):
                return d["deviceId"]

        # fallback: updatedAt mới nhất
        def _ts(d: Dict[str, Any]) -> str:
            return str(d.get("updatedAt") or "")

        items_sorted = sorted(items, key=_ts, reverse=True)
        did = items_sorted[0].get("deviceId")
        return did if isinstance(did, str) else None

    def ensure_device(self) -> Optional[str]:
        """Đảm bảo self.device_id đã có; nếu chưa thì chọn theo tiêu chí trên."""
        if self.device_id and self.device_id in self.device_ids:
            return self.device_id
        with self._lock:
            if not self.login():
                return None
            # nếu cache có mà không nằm trong list hiện tại, vẫn thử dùng
            if self.device_id and self.device_id not in self.device_ids:
                return self.device_id
            picked = self._choose_device()
            if picked:
                self.device_id = picked
                self._save_user_cache()
            return self.device_id

    # ---------------- read state ----------------
    def read_state_server(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Đọc state thô + parse values từ server."""
        if not self.login():
            return {}

        did = device_id or self.device_id or self.ensure_device()
        if not did:
            return {}

        did = self._normalize_did(did)
        url = f"{self.server_base_url}/api/inverter/data"
        params = {"uid": self.uid, "deviceId": did}

        r = self.session.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print("[api] GET state FAIL", r.status_code, r.text[:200])
            return {}

        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # server có kiểu trả: {"raw":{...}, "values":[...]} hoặc {"data":{...}}
        node = data.get("raw") or data.get("data") or data
        values_str = ""
        if isinstance(node, dict):
            values_str = node.get("value") or node.get("Value") or ""

        values: List[float] = []
        if isinstance(values_str, str) and values_str:
            parts = [p for p in values_str.split("#") if p != ""]
            for p in parts:
                v = _parse_float(p)
                if v is not None:
                    values.append(v)

        out = {
            "raw": node,
            "values": values,
            "ts": int(_now() * 1_000_000),  # microseconds
        }
        # lưu device nếu thành công
        self.device_id = did
        self._save_user_cache()
        return out


# tiện lợi cho server import
def load_options() -> Dict[str, Any]:
    return _load_options()
