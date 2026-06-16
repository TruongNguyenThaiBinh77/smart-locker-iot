"""Temporary cabinet simulator for demoing the mobile <-> IoT unlock loop
without real Raspberry Pi/Arduino hardware.

This is intentionally separate from `main.py` (the real hardware-track
runtime maintained for the physical cabinet) and does not touch
`infracstructure/serial_manager.py`, `services/setup_handler.py`, or any
other file on that track. `main.py` only starts responding to open
commands after it receives a SETUP_LOCKERS handshake on
`iot/{macAddress}/command/setup` -- nothing in the backend sends that
handshake today, and even with SIMULATION=true it would still wait for it.
This script skips that handshake entirely: it subscribes to every
cabinet's open command directly and replies as if a cabinet were wired up.

What it talks to: `iot-service` (`LockerMqttService.sendUnlockCommandAsync`)
publishes to `cabinet/{lockerId}/command/open` with body
`{"commandId": "...", "box_id": <id>, "action": "OPEN", "timeout": 15}` and
waits up to 20s for a reply on `cabinet/{lockerId}/command/open/result`.
This script answers that reply.

Usage:
    uv run python simulate_demo_cabinet.py
    SIM_FORCE_FAIL=true uv run python simulate_demo_cabinet.py   # test the failure path
    SIM_DELAY_SECONDS=3 uv run python simulate_demo_cabinet.py   # slower "door" for demos

Env (only used by this script, independent of config/settings.py so it
defaults to the SAME broker iot-service defaults to when nothing is
configured):
    MQTT_BROKER_URL   e.g. tcp://broker.hivemq.com:1883 (matches iot-service's own env var)
    MQTT_BROKER / MQTT_PORT   alternative host/port pair if you'd rather set those
    SIM_DELAY_SECONDS  simulated door latency before replying (default 1.5)
    SIM_FORCE_FAIL     "true" to always reply FAILED, for testing the error path
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

OPEN_COMMAND_TOPIC = "cabinet/+/command/open"
SIM_DELAY_SECONDS = float(os.getenv("SIM_DELAY_SECONDS", "1.5"))
SIM_FORCE_FAIL = os.getenv("SIM_FORCE_FAIL", "false").lower() == "true"


def _resolve_broker() -> tuple[str, int]:
    """Same default as iot-service's `mqtt.broker-url` (tcp://broker.hivemq.com:1883)
    so this script works out of the box without any local config, but still
    honours MQTT_BROKER_URL / MQTT_BROKER+MQTT_PORT if someone pointed both
    sides at a different broker (e.g. a local Mosquitto)."""
    url = os.getenv("MQTT_BROKER_URL")
    if url:
        without_scheme = url.split("://", 1)[-1]
        host, _, port = without_scheme.partition(":")
        return host, int(port) if port else 1883
    host = os.getenv("MQTT_BROKER", "broker.hivemq.com")
    port = int(os.getenv("MQTT_PORT", "1883"))
    return host, port


def _on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[SIM] Connected. Subscribing to {OPEN_COMMAND_TOPIC}")
        client.subscribe(OPEN_COMMAND_TOPIC, qos=1)
    else:
        print(f"[SIM] Connect failed, reason_code={reason_code}")


def _reply_after_delay(client: mqtt.Client, locker_id: str, command_id, box_id):
    time.sleep(SIM_DELAY_SECONDS)
    failed = SIM_FORCE_FAIL
    status = "FAILED" if failed else "SUCCESS"
    payload = {
        "commandId": command_id,
        "lockerId": locker_id,
        "boxId": box_id,
        "status": status,
        "hwState": "CLOSING" if failed else "OPENING",
        "errorCode": "SIMULATED_FAILURE" if failed else None,
        "errorMessage": "Simulated hardware failure" if failed else "Simulated: door opened",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result_topic = f"cabinet/{locker_id}/command/open/result"
    client.publish(result_topic, json.dumps(payload), qos=1)
    icon = "FAILED" if failed else "OK"
    print(f"[SIM] {icon} -> {result_topic}: {json.dumps(payload)}")


def _on_message(client, userdata, msg):
    parts = msg.topic.split("/")
    if len(parts) < 2:
        return
    locker_id = parts[1]
    try:
        data = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[SIM] Ignoring non-JSON payload on {msg.topic}")
        return

    command_id = data.get("commandId")
    box_id = data.get("box_id", data.get("boxId"))
    print(f"[SIM] OPEN request: locker={locker_id} box={box_id} commandId={command_id}")
    threading.Thread(
        target=_reply_after_delay,
        args=(client, locker_id, command_id, box_id),
        daemon=True,
    ).start()


def main():
    host, port = _resolve_broker()
    print("=" * 60)
    print("  Demo cabinet simulator (no hardware required)")
    print(f"  Broker: {host}:{port}")
    print(f"  Reply delay: {SIM_DELAY_SECONDS}s, force fail: {SIM_FORCE_FAIL}")
    print("  This stands in for the real cabinet runtime (main.py) until")
    print("  Raspberry Pi/Arduino hardware + the setup handshake are ready.")
    print("=" * 60)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(host, port, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[SIM] Shutting down...")
        client.disconnect()


if __name__ == "__main__":
    main()
