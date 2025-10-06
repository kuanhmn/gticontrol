import json, time, threading
from typing import Dict, List
from paho.mqtt.client import Client
from mapping import GTI_SENSORS, GRID_SENSORS, TIEUTHU_SENSORS, DAILY_KEYS, MONTHLY_KEYS
from mqtt_discovery import publish_sensor, publish_binary_sensor, publish_number, publish_datetime

def fmt2(x):
    try: return round(float(x), 2)
    except: return 0.00

class Coordinator:
    def __init__(self, mqtt_client: Client, disc_prefix: str, options: Dict, api_client):
        self.client = mqtt_client
        self.prefix = disc_prefix
        self.opt = options
        self.api = api_client
        self.scan_interval = int(options.get("scan_interval", 30))
        self.publish_mqtt = bool(options.get("publish_mqtt", True))
        self.use_server_daily_monthly = bool(options.get("use_server_daily_monthly", True))
        self.expose_totals_only = bool(options.get("expose_totals_only", False))
        self.server_enabled = bool(options.get("server_enabled", True))
        self.include_devices = options.get("include_devices", ["all"])
        self.state_cache: Dict[str, Dict] = {}

    def _device_info(self, device_id: str):
        return {
            "identifiers": [f"gti:{device_id}"],
            "name": device_id,
            "manufacturer": "GTI",
            "model": "GTI Control"
        }

    def discover_entities(self, device_id: str):
        if not self.publish_mqtt:
            return
        info = self._device_info(device_id)
        alls = {}; alls.update(GTI_SENSORS); alls.update(GRID_SENSORS); alls.update(TIEUTHU_SENSORS)
        for k, meta in alls.items():
            publish_sensor(self.client, self.prefix, device_id, k, meta, info)
        publish_binary_sensor(self.client, self.prefix, device_id, info)
        publish_number(self.client, self.prefix, device_id, "cutoff_voltage", "Điện áp ngắt", "V", 0, 100, 0.1, info)
        publish_number(self.client, self.prefix, device_id, "max_power_limit", "Công suất giới hạn", "W", 0, 5000, 10, info)
        for i in [1,2,3]:
            publish_datetime(self.client, self.prefix, device_id, f"schedule{i}_start", f"Lịch {i} - Bắt đầu", info)
            publish_datetime(self.client, self.prefix, device_id, f"schedule{i}_end",   f"Lịch {i} - Kết thúc", info)
            publish_number(self.client, self.prefix, device_id, f"schedule{i}_cutoff_voltage", f"Lịch {i} - Điện áp ngắt", "V", 0, 100, 0.1, info)
            publish_number(self.client, self.prefix, device_id, f"schedule{i}_max_power", f"Lịch {i} - Công suất", "W", 0, 5000, 10, info)

    def read_device_state(self, device_id: str) -> Dict:
        # TODO: Kết nối trực tiếp MQTT của thiết bị nếu cần (hiện để trống)
        return {}

    def build_state(self, device_id: str) -> Dict:
        st = self.read_device_state(device_id)
        for k in {**GTI_SENSORS, **GRID_SENSORS, **TIEUTHU_SENSORS}.keys():
            st[k] = fmt2(st.get(k, 0.0))
        st["online"] = bool(st.get("online", True))

        if self.server_enabled and self.use_server_daily_monthly and not self.expose_totals_only:
            srv = self.api.read_state_server(device_id) or {}
            for dk in DAILY_KEYS:   st[dk] = fmt2(srv.get(dk, st.get(dk, 0.0)))
            for mk in MONTHLY_KEYS: st[mk] = fmt2(srv.get(mk, st.get(mk, 0.0)))
        return st

    def publish_state(self, device_id: str, st: Dict):
        topic = f"gti/{device_id}/state"
        self.client.publish(topic, json.dumps(st), retain=True)
        self.state_cache[device_id] = st

    def loop(self, device_ids: List[str]):
        for d in device_ids:
            self.discover_entities(d)
        while True:
            for d in device_ids:
                try:
                    st = self.build_state(d)
                    self.publish_state(d, st)
                except Exception:
                    st = self.state_cache.get(d, {}) or {}
                    st["online"] = False
                    self.publish_state(d, st)
            time.sleep(self.scan_interval)
