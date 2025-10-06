import json
from typing import Dict, Any
from paho.mqtt.client import Client

def disc_topic(prefix, comp, object_id):
    return f"{prefix}/{comp}/{object_id}/config"

def obj_id(device_id: str, key: str) -> str:
    return f"{device_id}_{key}"

def publish_sensor(client: Client, prefix: str, device_id: str, key: str, meta: Dict[str, Any], device_info: Dict[str, Any]):
    object_id = obj_id(device_id, key)
    payload = {
        "name": meta[0],
        "state_topic": f"gti/{device_id}/state",
        "unit_of_measurement": meta[1],
        "value_template": f"{{{{ value_json.{key} | default(0.0) }}}}",
        "unique_id": object_id,
        "device": device_info
    }
    if meta[2]:
        payload["device_class"] = meta[2]
    if meta[3]:
        payload["state_class"] = meta[3]
    client.publish(disc_topic(prefix, "sensor", object_id), json.dumps(payload), retain=True)

def publish_binary_sensor(client: Client, prefix: str, device_id: str, device_info: Dict[str, Any]):
    object_id = obj_id(device_id, "online")
    payload = {
        "name": "Trạng thái online",
        "state_topic": f"gti/{device_id}/state",
        "value_template": "{{ 'ON' if value_json.online else 'OFF' }}",
        "payload_on": "ON",
        "payload_off": "OFF",
        "unique_id": object_id,
        "device": device_info
    }
    client.publish(disc_topic(prefix, "binary_sensor", object_id), json.dumps(payload), retain=True)

def publish_number(client: Client, prefix: str, device_id: str, key: str, name: str, unit: str, minv: float, maxv: float, step: float, device_info: Dict[str, Any]):
    object_id = obj_id(device_id, key)
    payload = {
        "name": name,
        "command_topic": f"gti/{device_id}/cmd/number/{key}",
        "state_topic": f"gti/{device_id}/state",
        "value_template": f"{{{{ value_json.{key} | default(0.0) }}}}",
        "unique_id": object_id,
        "device": device_info,
        "unit_of_measurement": unit,
        "min": minv, "max": maxv, "step": step
    }
    client.publish(disc_topic(prefix, "number", object_id), json.dumps(payload), retain=True)

def publish_datetime(client: Client, prefix: str, device_id: str, key: str, name: str, device_info: Dict[str, Any]):
    object_id = obj_id(device_id, key)
    payload = {
        "name": name,
        "command_topic": f"gti/{device_id}/cmd/datetime/{key}",
        "state_topic": f"gti/{device_id}/state",
        "value_template": f"{{{{ value_json.{key} | default('00:00') }}}}",
        "unique_id": object_id,
        "device": device_info
    }
    client.publish(disc_topic(prefix, "datetime", object_id), json.dumps(payload), retain=True)
