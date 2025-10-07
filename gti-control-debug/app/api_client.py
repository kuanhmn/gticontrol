# -*- coding: utf-8 -*-
import os, json, time, threading
from typing import Dict, Any, List, Optional
import requests

OPTIONS_PATH = "/data/options.json"
USER_PATH    = "/data/user_options.json"

def _load_options() -> Dict[str, Any]:
    with open(OPTIONS_PATH, "r", encoding="utf-8") as f:
        opt = json.load(f)
    # strip khoảng trắng nhỡ nhập thừa
    for k in ("server_base_url", "firebase_api_key", "email", "password"):
        v = opt.get(k)
        if isinstance(v, str):
            opt[k] = v.strip()
    return opt

class APIClient:
    """
    - Login Firebase bằng Identity Toolkit (signInWithPassword)
    - Cache idToken vào /data/user_options.json (idToken, localId, expires_at)
    - Đọc state từ server qua route:  /api/inverter/data?uid=<UID>&deviceId=<DID>
      -> trả về phần tử đầu (data[0]) + parse value thành list số.
    """
    def __init__(self, opts: Dict[str, Any]) -> None:
        self.base   = (opts.get("server_base_url") or "").rstrip("/")
        self.email  = opts.get("email") or ""
        self.pw     = opts.get("password") or ""
        self.api_key= opts.get("firebase_api_key") or ""
        self.s      = requests.Session()
        self._lock  = threading.Lock()
        self.id_tok : Optional[str] = None
        self.uid    : Optional[str] = None
        self.exp_at : int = 0

        # nạp cache nếu có
        if os.path.exists(USER_PATH):
            try:
                c = json.load(open(USER_PATH, "r", encoding="utf-8"))
                self.id_tok = c.get("idToken")
                self.uid    = c.get("localId")
                self.exp_at = int(c.get("expires_at") or 0)
            except Exception:
                pass

    # ---------- auth ----------
    def _save_cache(self, j: Dict[str, Any]) -> None:
        self.id_tok = j.get("idToken")
        self.uid    = j.get("localId")
        exp_sec     = int(j.get("expiresIn") or 3600)
        self.exp_at = int(time.time()) + exp_sec
        os.makedirs(os.path.dirname(USER_PATH), exist_ok=True)
        json.dump(
            {"idToken": self.id_tok, "localId": self.uid, "expires_at": self.exp_at},
            open(USER_PATH, "w", encoding="utf-8"),
            ensure_ascii=False, indent=2
        )

    def _token_valid(self) -> bool:
        return bool(self.id_tok) and (time.time() < self.exp_at - 60)

    def login(self, force: bool = False) -> bool:
        if not self.base:
            print("[api] server disabled");  return True
        if self._token_valid() and not force:
            print("[api] already have valid token");  return True
        if not (self.api_key and self.email and self.pw):
            print("[api] missing api_key/email/password");  return False

        with self._lock:
            if self._token_valid() and not force:
                return True
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
            try:
                print(f"[api] POST {url}?key=***{self.api_key[-5:]}")
                r = self.s.post(url, params={"key": self.api_key},
                                json={"email": self.email, "password": self.pw, "returnSecureToken": True},
                                timeout=20)
                print("[api] ->", r.status_code)
                if not r.ok:
                    print("[api] login FAIL:", (r.text or "")[:400])
                    return False
                j = r.json()
                self._save_cache(j)
                print(f"[api] login ok uid={self.uid} valid_for={int(self.exp_at-time.time())}s")
                return True
            except Exception as e:
                print("[api] login error:", e)
                return False

    # ---------- data ----------
    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.id_tok}", "Accept": "application/json"}

    def _get_json(self, url: str) -> Optional[Dict[str, Any]]:
        r = self.s.get(url, headers=self._auth_headers(), timeout=20)
        print("[api] GET", url); print("[api] ->", r.status_code)
        if not r.ok:
            print("[api] body:", (r.text or "")[:400])
            return None
        try:
            return r.json()
        except Exception:
            print("[api] invalid json from", url)
            return None

    def read_state_server(self, device_id: str) -> Dict[str, Any]:
        """
        Trả: {"deviceId", "userId", "createdAt", "updatedAt", "value", "raw"}
        value là chuỗi "#", cần split khi render.
        """
        if not self.login(False):
            return {}
        url = f"{self.base}/api/inverter/data?uid={self.uid}&deviceId={device_id}"
        j = self._get_json(url)
        if not j or not j.get("data"):
            return {}
        row = j["data"][0].copy()
        row["raw"] = row.copy()
        return row

    # Optional: liệt kê nhanh (từ coordinator sẽ chuẩn hơn)
    def list_devices(self) -> List[str]:
        # không có API list chuẩn => trả về theo include_devices trong options
        try:
            inc = _load_options().get("include_devices") or []
            if inc and inc != ["all"]:
                return [str(x) for x in inc]
        except Exception:
            pass
        return ["gti283"]