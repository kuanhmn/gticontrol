import time
import requests
from typing import Dict, List, Optional, Tuple

class APIClient:
    """
    Client tới backend giống app Android.
    - Đăng nhập Firebase IdentityToolkit (nếu có API key)
    - Gọi các endpoint server theo một danh sách "ứng viên" để tự dò (có log chi tiết).
    """

    def __init__(self, options: Dict):
        self.opt = options
        self.server_enabled: bool = options.get("server_enabled", True)
        self.base = (options.get("server_base_url") or "").rstrip("/")
        self.api_key = options.get("firebase_api_key") or "AIzaSyDRKQ9d6kfsoZT2lUnZcZnBYvH69HExNPE"
        self.email = options.get("email") or ""
        self.password = options.get("password") or ""
        self.auth_method = options.get("auth_method", "email_password")
        self.id_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.debug = (options.get("log_level","INFO") == "DEBUG")

    # ---------- Helpers ----------
    def _h(self) -> Dict[str,str]:
        h = {"Accept": "application/json"}
        if self.id_token:
            h["Authorization"] = f"Bearer {self.id_token}"
        return h

    def _get_json(self, url: str, params: Dict=None, allow_noauth: bool=False):
        """
        GET JSON with logs. If 401/403, and allow_noauth=True, retry without auth.
        """
        if not self.server_enabled:
            return None, 0, "server_disabled"
        try:
            if self.debug: print(f"[api] GET {url} params={params} auth={'yes' if self.id_token else 'no'}")
            r = requests.get(url, headers=self._h(), params=params or {}, timeout=15)
            sc = r.status_code
            txt = (r.text or "")[:400]
            if self.debug: print(f"[api] -> {sc} {txt}")
            if sc == 401 and allow_noauth:
                if self.debug: print("[api] retry no-auth")
                r2 = requests.get(url, params=params or {}, timeout=15)
                sc = r2.status_code
                txt = (r2.text or "")[:400]
                if self.debug: print(f"[api] (noauth) -> {sc} {txt}")
                if sc==200:
                    return r2.json(), sc, None
            if sc==200 and r.content:
                return r.json(), sc, None
            return None, sc, txt
        except Exception as e:
            if self.debug: print("[api] EXC", e)
            return None, -1, str(e)

    # ---------- AUTH ----------
    def login(self) -> bool:
        """
        Firebase Email/Password. Không bắt buộc nếu server không cần Bearer.
        """
        if not self.server_enabled:
            return True
        if self.auth_method == "email_password" and self.api_key and self.email and self.password:
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.api_key}"
                payload = {"email": self.email, "password": self.password, "returnSecureToken": True}
                if self.debug: print("[api] login Firebase POST", url)
                r = requests.post(url, json=payload, timeout=20)
                r.raise_for_status()
                data = r.json() or {}
                self.id_token = data.get("idToken")
                self.user_id  = data.get("localId")
                if self.debug: print("[api] login ok uid=", self.user_id)
                return True
            except Exception as e:
                if self.debug: print("[api] login failed:", e)
                # vẫn tiếp tục, có thể server không yêu cầu Bearer
                return False
        return True

    # ---------- DEVICES ----------
    def list_devices(self) -> List[str]:
        """
        Tự dò danh sách thiết bị qua vài endpoint phổ biến.
        """
        if not self.server_enabled or not self.base:
            return []
        candidates = [
            f"{self.base}/devices/inverter",
            f"{self.base}/api/devices",
            f"{self.base}/api/inverter/devices",
            f"{self.base}/api/user/{self.user_id or 'me'}/devices",
        ]
        for url in candidates:
            data, sc, err = self._get_json(url, allow_noauth=True)
            if sc==200 and isinstance(data, list):
                ids=[]
                for it in data:
                    # accept string id or object with deviceId/id
                    if isinstance(it, str):
                        did = it
                    else:
                        did = it.get("deviceId") or it.get("id") or ""
                    if did:
                        if not str(did).startswith("gti"):
                            did=f"gti{did}"
                        ids.append(str(did))
                if ids:
                    return ids
            # also accept dict like {"devices":[...]}
            if sc==200 and isinstance(data, dict):
                arr = data.get("devices") or data.get("items") or []
                ids=[]
                for it in arr:
                    did = it if isinstance(it,str) else (it.get("deviceId") or it.get("id") or "")
                    if did:
                        if not str(did).startswith("gti"):
                            did=f"gti{did}"
                        ids.append(str(did))
                if ids: return ids
        return []

    # ---------- STATE ----------
    def read_state_server(self, device_id: str) -> Dict:
        """
        Lấy daily/monthly và (nếu có) tức thời từ server.
        Thử nhiều endpoint ứng viên, map về các field tiêu chuẩn.
        """
        if not self.server_enabled or not self.base:
            return {}
        did = device_id.replace("gti","")
        uid = self.user_id or "me"

        candidates = [
            f"{self.base}/api/inverter/data/{uid}/{did}/latest",
            f"{self.base}/api/inverter/{did}/latest",
            f"{self.base}/api/inverter/data",
            f"{self.base}/api/inverter/{did}",
        ]
        # thêm param uid nếu cần
        param_list = [None, {"uid": uid, "deviceId": did}, {"uid": uid}]

        for url in candidates:
            for params in param_list:
                data, sc, err = self._get_json(url, params=params, allow_noauth=True)
                if sc==200 and isinstance(data, dict):
                    g = lambda *keys, default=0.0: next((data.get(k) for k in keys if k in data), default)
                    mapped = {
                        # GTI energy daily/monthly
                        "energy_daily":          g("export_energy_kwh_daily","energy_daily","daily_export_kwh"),
                        "energy_monthly":        g("export_energy_kwh_monthly","energy_monthly","monthly_export_kwh"),
                        # GRID
                        "grid_energy_daily":     g("grid_in_energy_kwh_daily","grid_energy_daily","daily_grid_kwh"),
                        "grid_energy_monthly":   g("grid_in_energy_kwh_monthly","grid_energy_monthly","monthly_grid_kwh"),
                        # LOAD (tiêu thụ)
                        "tieuthu_energy_daily":  g("consumption_energy_kwh_daily","tieuthu_energy_daily","daily_load_kwh"),
                        "tieuthu_energy_monthly":g("consumption_energy_kwh_monthly","tieuthu_energy_monthly","monthly_load_kwh"),
                        # Instant / totals nếu server có
                        "power":                 g("export_power_w","power","export_w"),
                        "energy_total":          g("export_energy_kwh_total","energy_total","export_total_kwh"),
                        "voltage_dc":            g("vdc","voltage_dc","dc_voltage"),
                        "current":               g("idc","current","dc_current"),
                        "mosfet_temp":           g("mosfet_temp","temp_mos","heat_sink_temp_c"),
                        "grid_voltage":          g("grid_voltage","grid_v"),
                        "grid_frequency":        g("grid_frequency","grid_hz"),
                        "grid_power":            g("grid_power","grid_w"),
                        "grid_energy_total":     g("grid_energy_kwh_total","grid_total_kwh"),
                        "tieuthu_power":         g("load_power","tieuthu_power","load_w"),
                        "tieuthu_energy_total":  g("load_energy_kwh_total","load_total_kwh"),
                        "cutoff_voltage":        g("cutoff_voltage","cutoff_v"),
                        "max_power_limit":       g("max_power_limit","limit_w"),
                    }
                    for k,v in list(mapped.items()):
                        if v is None: mapped[k]=0.0
                    mapped["online"] = True
                    return mapped
        return {}

    # ---------- Schedules / Settings ----------
    def get_schedules(self, device_id: str) -> Dict:
        if not self.server_enabled or not self.base:
            return {}
        did = device_id.replace("gti","")
        uid = self.user_id or "me"
        cands = [
            f"{self.base}/schedule/value",
            f"{self.base}/api/schedule",
        ]
        for url in cands:
            data, sc, err = self._get_json(url, params={"uid":uid,"deviceId":did}, allow_noauth=True)
            if sc==200 and isinstance(data, dict):
                return data
        return {}

    def set_cutoff_voltage(self, device_id: str, volts: float) -> bool:
        if not self.server_enabled or not self.base: return False
        did = device_id.replace("gti","")
        url = f"{self.base}/settings/cutoff"
        try:
            r = requests.post(url, headers=self._h(), json={"deviceId": did, "cutoff_voltage": volts}, timeout=15)
            return r.status_code in (200,204)
        except Exception:
            return False

    def set_max_power(self, device_id: str, watts: float) -> bool:
        if not self.server_enabled or not self.base: return False
        did = device_id.replace("gti","")
        url = f"{self.base}/settings/max_power"
        try:
            r = requests.post(url, headers=self._h(), json={"deviceId": did, "max_power": watts}, timeout=15)
            return r.status_code in (200,204)
        except Exception:
            return False

    def set_schedule(self, device_id: str, index: int, start: str, end: str, cutoff_v: float, max_w: float) -> bool:
        if not self.server_enabled or not self.base: return False
        did = device_id.replace("gti","")
        url = f"{self.base}/schedule"
        payload = {"deviceId": did, "index": index, "start": start, "end": end, "cutoff_voltage": cutoff_v, "max_power": max_w}
        try:
            r = requests.post(url, headers=self._h(), json=payload, timeout=15)
            return r.status_code in (200,204)
        except Exception:
            return False