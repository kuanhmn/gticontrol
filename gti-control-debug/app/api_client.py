import os, json, time, logging, traceback, datetime
import requests

_LOG = logging.getLogger("gti.api")
_LOG.setLevel(logging.DEBUG)

def _short(s, n=800):
    if s is None: return ""
    s = str(s)
    return s if len(s) <= n else s[:n] + "..."

# 2 API keys trích từ APK (classes.dex/resources.arsc)
FALLBACK_API_KEYS = [
    "AIzaSyCIc1vxm9ZiqoMkgCDtADPjaL0d7Prpm5Q",
    "AIzaSyDRKQ9d6kfsoZT2lUnZcZnBYvH69HExNPE",
]

class APIClient:
    def __init__(self, options):
        self.base = (options.get("server_base_url") or "").rstrip("/")
        self.email = options.get("email") or ""
        self.password = options.get("password") or ""
        self.api_key = options.get("firebase_api_key") or ""
        self.session = requests.Session()
        self.id_token = None
        self.user_id = None
        self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists("/tmp/idtoken.txt"):
                self.id_token = open("/tmp/idtoken.txt").read().strip()
            if os.path.exists("/tmp/uid.txt"):
                self.user_id = open("/tmp/uid.txt").read().strip()
            if self.id_token:
                _LOG.info("[api] loaded cached token len=%d", len(self.id_token))
        except Exception as e:
            _LOG.debug("cache load err %s", e)

    def _save_cache(self):
        try:
            if self.id_token: open("/tmp/idtoken.txt","w").write(self.id_token)
            if self.user_id:  open("/tmp/uid.txt","w").write(self.user_id)
        except Exception as e:
            _LOG.debug("cache save err %s", e)

    def _headers(self):
        h = {
            "Accept": "application/json",
            "User-Agent": "gti-addon/1.0",
        }
        if self.id_token:
            # gửi 3 kiểu để “bắt” backend
            h["Authorization"] = "Bearer " + self.id_token
            h["idToken"] = self.id_token
            h["token"] = self.id_token
        return h

    def _log_resp(self, tag, r):
        try:
            _LOG.debug("[%s] %s -> %s\nHEADERS:%s\nBODY:%s",
                       tag, getattr(r,"url",tag), getattr(r,"status_code",None),
                       dict(getattr(r,"headers",{}).items()) if getattr(r,"headers",None) else {},
                       _short(getattr(r,"text",None), 800))
        except Exception:
            _LOG.debug("resp log err: %s", traceback.format_exc())

    def _test_token(self):
        if not self.id_token: return False
        # server không có /api/ping (404), nên test bằng 1 endpoint public sẵn.
        try:
            u = f"{self.base}/api/firmware/newest"
            r = self.session.get(u, headers=self._headers(), timeout=10)
            self._log_resp("test-token", r)
            # chấp nhận 200 / 401 / 403 (miễn là có phản hồi hợp lý)
            return r.status_code in (200,401,403)
        except Exception:
            return False

    def login(self):
        _LOG.info("[api] login: email=%s has_api_key=%s", bool(self.email), bool(self.api_key))
        # 0) thử token cache
        if self._test_token():
            _LOG.info("[api] use cached token")
            return True

        # 1) Firebase signInWithEmailAndPassword: dùng api_key cấu hình trước
        api_keys = []
        if self.api_key: api_keys.append(self.api_key)
        # 2) nếu không pass → thử 2 key trích từ APK
        for k in FALLBACK_API_KEYS:
            if k not in api_keys: api_keys.append(k)

        for key in api_keys:
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithEmailAndPassword?key={key}"
                payload = {"email": self.email, "password": self.password, "returnSecureToken": True}
                r = self.session.post(url, json=payload, timeout=15)
                self._log_resp("firebase-login", r)
                if r.status_code == 200:
                    j = r.json()
                    self.id_token = j.get("idToken")
                    self.user_id  = j.get("localId") or j.get("userId")
                    self._save_cache()
                    _LOG.info("[api] firebase OK (key=...%s) uid=%s", key[-6:], self.user_id)
                    return True
                else:
                    _LOG.warning("[api] firebase FAIL (key=...%s) %s %s", key[-6:], r.status_code, _short(r.text,500))
            except Exception as e:
                _LOG.exception("[api] firebase exception: %s", e)

        _LOG.warning("[api] login failed (all methods)")
        return False

    # ====== DEVICES ======
    def list_devices(self):
        # APK không lộ endpoint list rõ ràng → thử một vài khả năng
        cands = [
            f"{self.base}/api/inverter-setting/data/{self.user_id}",
            f"{self.base}/api/inverter-device/data/{self.user_id}",
            f"{self.base}/api/inverter-device/data/device/{self.user_id}",
        ]
        for u in cands:
            try:
                r = self.session.get(u, headers=self._headers(), timeout=12)
                self._log_resp("listdev", r)
                if r.status_code == 200:
                    try:
                        j = r.json()
                        # đoán cấu trúc: [{deviceId: 283}, ...]
                        out=[]
                        if isinstance(j, list):
                            for it in j:
                                did = (it.get("deviceId") or it.get("id") or it.get("device_id"))
                                if did is not None:
                                    did = str(did)
                                    if not did.startswith("gti"):
                                        did = "gti"+did
                                    out.append(did)
                        elif isinstance(j, dict) and "items" in j:
                            for it in j["items"]:
                                did = str(it.get("deviceId") or it.get("id"))
                                if not did.startswith("gti"):
                                    did = "gti"+did
                                out.append(did)
                        if out:
                            return out
                    except Exception:
                        pass
            except Exception as e:
                _LOG.debug("listdev err %s", e)
        return []

    # ====== STATE ======
    def read_state_server(self, device_id):
        # '/api/inverter/data/{userId}/{deviceId}/latest'
        did = str(device_id).replace("gti","").strip()
        if not did.isdigit():
            # nếu format khác, cứ gửi nguyên
            did = did
        u = f"{self.base}/api/inverter/data/{self.user_id}/{did}/latest"
        try:
            r = self.session.get(u, headers=self._headers(), timeout=12)
            self._log_resp("latest", r)
            if r.status_code == 200:
                return r.json() or {}
        except Exception as e:
            _LOG.debug("latest err %s", e)
        return {}

    # ====== DAILY / MONTHLY ======
    def read_daily(self, device_id, date=None):
        # '/api/daily-totals/by-day?userId=&deviceId=&date=YYYY-MM-DD'
        did = str(device_id).replace("gti","").strip()
        if date is None:
            date = datetime.date.today().isoformat()
        params = {"userId": self.user_id, "deviceId": did, "date": date}
        u = f"{self.base}/api/daily-totals/by-day"
        try:
            r = self.session.get(u, headers=self._headers(), params=params, timeout=12)
            self._log_resp("daily", r)
            if r.status_code == 200:
                return r.json() or {}
        except Exception as e:
            _LOG.debug("daily err %s", e)
        return {}

    def read_monthly(self, device_id, year=None, month=None):
        # '/api/daily-totals/monthly?userId=&deviceId=&year=&month='
        did = str(device_id).replace("gti","").strip()
        today = datetime.date.today()
        year  = year or today.year
        month = month or today.month
        params = {"userId": self.user_id, "deviceId": did, "year": year, "month": month}
        u = f"{self.base}/api/daily-totals/monthly"
        try:
            r = self.session.get(u, headers=self._headers(), params=params, timeout=12)
            self._log_resp("monthly", r)
            if r.status_code == 200:
                return r.json() or {}
        except Exception as e:
            _LOG.debug("monthly err %s", e)
        return {}