import requests, time
from typing import Dict, List, Optional

class APIClient:
    """
    Client REST tới server GTI + login Firebase.
    """

    def __init__(self, options: Dict):
        self.opt = options
        self.server_enabled: bool = options.get("server_enabled", True)
        self.server_base = options.get("server_base_url", "").rstrip("/")
        self.firebase_api_key = options.get("firebase_api_key") or ""
        self.email = options.get("email") or ""
        self.password = options.get("password") or ""
        self.auth_method = options.get("auth_method", "email_password")
        self.id_token: Optional[str] = None
        self.user_id: Optional[str] = None

    # ---------- AUTH ----------
    def login(self) -> bool:
        if not self.server_enabled:
            print("[api] server disabled")
            return True

        if self.auth_method == "email_password" and self.firebase_api_key and self.email and self.password:
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.firebase_api_key}"
                payload = {
                    "email": self.email,
                    "password": self.password,
                    "returnSecureToken": True
                }
                print("[api] POST", url)
                r = requests.post(url, json=payload, timeout=15)
                print("[api] ->", r.status_code, (r.text or "")[:200])
                r.raise_for_status()
                data = r.json()
                self.id_token = data.get("idToken")
                self.user_id  = data.get("localId")
                print("[api] login OK, uid=", self.user_id)
                return True
            except Exception as e:
                print("[api] firebase login fail:", e)
                return False

        print("[api] login skipped (no creds)")
        return False

    def _auth_headers(self) -> Dict:
        h = {"Content-Type": "application/json"}
        if self.id_token:
            h["Authorization"] = f"Bearer {self.id_token}"
        return h

    # ---------- DEVICES ----------
    def list_devices(self) -> List[str]:
        if not self.server_enabled:
            return []
        try:
            url = f"{self.server_base}/devices/inverter/"
            print("[api] GET", url)
            r = requests.get(url, headers=self._auth_headers(), timeout=15)
            print("[api] ->", r.status_code)
            r.raise_for_status()
            arr = r.json() if r.content else []
            ids = []
            for it in arr or []:
                did = it.get("deviceId") or it.get("id")
                if did:
                    if not str(did).startswith("gti"):
                        did = f"gti{did}"
                    ids.append(str(did))
            print("[api] devices:", ids)
            return ids
        except Exception as e:
            print("[api] list_devices fail:", e)
            return []

    # ---------- STATE ----------
    def read_state_server(self, device_id: str) -> Dict:
        if not self.server_enabled:
            return {}
        try:
            uid = self.user_id or "me"
            did = device_id.replace("gti", "")
            url = f"{self.server_base}/api/inverter/data/{uid}/{did}/latest"
            print("[api] GET", url)
            r = requests.get(url, headers=self._auth_headers(), timeout=15)
            print("[api] ->", r.status_code)
            r.raise_for_status()
            data = r.json() or {}
            mapped = {
                "energy_daily": data.get("export_energy_kwh_daily") or data.get("energy_daily") or 0.0,
                "energy_monthly": data.get("export_energy_kwh_monthly") or data.get("energy_monthly") or 0.0,
                "grid_energy_daily": data.get("grid_in_energy_kwh_daily") or data.get("grid_energy_daily") or 0.0,
                "grid_energy_monthly": data.get("grid_in_energy_kwh_monthly") or data.get("grid_energy_monthly") or 0.0,
                "tieuthu_energy_daily": data.get("consumption_energy_kwh_daily") or data.get("tieuthu_energy_daily") or 0.0,
                "tieuthu_energy_monthly": data.get("consumption_energy_kwh_monthly") or data.get("tieuthu_energy_monthly") or 0.0
            }
            print("[api] server state:", mapped)
            return mapped
        except Exception as e:
            print("[api] read_state_server fail:", e)
            return {}

    # ---------- SETTINGS ----------
    def get_schedules(self, device_id: str) -> Dict:
        if not self.server_enabled:
            return {}
        try:
            uid = self.user_id or "me"
            did = device_id.replace("gti","")
            url = f"{self.server_base}/schedule/value?uid={uid}&deviceId={did}"
            print("[api] GET", url)
            r = requests.get(url, headers=self._auth_headers(), timeout=15)
            print("[api] ->", r.status_code)
            r.raise_for_status()
            return r.json() or {}
        except Exception as e:
            print("[api] get_schedules fail:", e)
            return {}

    def set_cutoff_voltage(self, device_id: str, volts: float) -> bool:
        try:
            did = device_id.replace("gti","")
            url = f"{self.server_base}/settings/cutoff"
            r = requests.post(url, headers=self._auth_headers(),
                              json={"deviceId": did, "cutoff_voltage": volts}, timeout=15)
            print("[api] set_cutoff", r.status_code)
            r.raise_for_status()
            return True
        except Exception as e:
            print("[api] set_cutoff fail:", e)
            return False

    def set_max_power(self, device_id: str, watts: float) -> bool:
        try:
            did = device_id.replace("gti","")
            url = f"{self.server_base}/settings/max_power"
            r = requests.post(url, headers=self._auth_headers(),
                              json={"deviceId": did, "max_power": watts}, timeout=15)
            print("[api] set_max_power", r.status_code)
            r.raise_for_status()
            return True
        except Exception as e:
            print("[api] set_max_power fail:", e)
            return False

    def set_schedule(self, device_id: str, index: int, start: str, end: str, cutoff_v: float, max_w: float) -> bool:
        try:
            did = device_id.replace("gti","")
            url = f"{self.server_base}/schedule"
            payload = {
                "deviceId": did, "index": index,
                "start": start, "end": end,
                "cutoff_voltage": cutoff_v, "max_power": max_w
            }
            r = requests.post(url, headers=self._auth_headers(), json=payload, timeout=15)
            print("[api] set_schedule", r.status_code)
            r.raise_for_status()
            return True
        except Exception as e:
            print("[api] set_schedule fail:", e)
            return False