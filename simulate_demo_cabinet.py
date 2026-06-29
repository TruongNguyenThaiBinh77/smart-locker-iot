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

It also mirrors the **booking -> IoT sync** (GAP 1): whenever an order
reserves/occupies/releases a cell, locker-service -> iot-service publishes the
box's new state to `cabinet/{lockerId}/command/sync` with body
`{"boxId": <id>, "state": "RESERVED|OCCUPIED|AVAILABLE|FAULT", "orderId": <id>?}`.
That message is fire-and-forget (no reply expected); this script just logs it,
standing in for the cabinet updating its on-screen cell map.

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
    SIM_HEARTBEAT_SECONDS    how often to heartbeat known cabinets (default 30)
    SIM_HEARTBEAT_CABINETS   comma-separated cabinet/locker ids to mark ONLINE
                             up-front, e.g. "2,3" (otherwise learned from traffic)

Device health (GAP 3): iot-service records `cabinet/{id}/heartbeat` for the
device-health dashboard (`GET /api/manage/iot/device-status`). Nothing was
publishing one, so this sim now heartbeats every cabinet it knows about (seeded
via SIM_HEARTBEAT_CABINETS and/or learned from open/sync traffic).
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

OPEN_COMMAND_TOPIC = "cabinet/+/command/open"
# Booking -> IoT sync (GAP 1): locker-service publishes a box's new lifecycle
# state (RESERVED/OCCUPIED/AVAILABLE/FAULT) here whenever an order reserves/
# occupies/releases a cell, so the cabinet can mirror the booking. Fire-and-
# forget on the backend side (no reply expected) -- we just log it as if the
# cabinet were updating its on-screen cell map.
SYNC_COMMAND_TOPIC = "cabinet/+/command/sync"
SIM_DELAY_SECONDS = float(os.getenv("SIM_DELAY_SECONDS", "1.5"))
SIM_FORCE_FAIL = os.getenv("SIM_FORCE_FAIL", "false").lower() == "true"

# Device health (GAP 3): iot-service's `LockerMqttService` already subscribes to
# `cabinet/{id}/heartbeat` and records last-seen for the device-health dashboard
# (`GET /api/manage/iot/device-status`), but nothing was ever publishing one, so
# the dashboard stayed empty. This sim now periodically heartbeats every cabinet
# it knows about. Cabinets are learned from any traffic (open/sync command for
# `cabinet/{id}/...`) and/or seeded up-front via SIM_HEARTBEAT_CABINETS so a
# device can show ONLINE before the first command arrives.
SIM_HEARTBEAT_SECONDS = float(os.getenv("SIM_HEARTBEAT_SECONDS", "30"))
SIM_HEARTBEAT_CABINETS = [
    c.strip() for c in os.getenv("SIM_HEARTBEAT_CABINETS", "").split(",") if c.strip()
]
_known_cabinets: set[str] = set()
_known_lock = threading.Lock()


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


def _publish_heartbeat(client: mqtt.Client, cabinet_id: str):
    """Publish one ONLINE heartbeat for a cabinet. iot-service maps the topic
    segment to the device id and stamps last-seen, so the device shows ONLINE."""
    if not client.is_connected():
        return
    payload = {"status": "ONLINE", "timestamp": datetime.now(timezone.utc).isoformat()}
    client.publish(f"cabinet/{cabinet_id}/heartbeat", json.dumps(payload), qos=1)


def _learn_cabinet(client: mqtt.Client, cabinet_id: str):
    """Remember a cabinet seen in traffic and heartbeat it immediately so it
    appears ONLINE right away instead of waiting for the next interval tick."""
    with _known_lock:
        new = cabinet_id not in _known_cabinets
        _known_cabinets.add(cabinet_id)
    if new:
        print(f"[SIM] Learned cabinet {cabinet_id} -> heartbeating it")
        _publish_heartbeat(client, cabinet_id)


def _heartbeat_loop(client: mqtt.Client):
    """Background thread: periodically heartbeat every known cabinet."""
    while True:
        time.sleep(SIM_HEARTBEAT_SECONDS)
        with _known_lock:
            cabinets = list(_known_cabinets)
        for cabinet_id in cabinets:
            _publish_heartbeat(client, cabinet_id)
        if cabinets:
            print(f"[SIM] Heartbeat sent for {len(cabinets)} cabinet(s): {', '.join(cabinets)}")


def _on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[SIM] Connected. Subscribing to {OPEN_COMMAND_TOPIC} and {SYNC_COMMAND_TOPIC}")
        client.subscribe([(OPEN_COMMAND_TOPIC, 1), (SYNC_COMMAND_TOPIC, 1)])
        # Announce seeded cabinets ONLINE right after (re)connect.
        with _known_lock:
            cabinets = list(_known_cabinets)
        for cabinet_id in cabinets:
            _publish_heartbeat(client, cabinet_id)
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
    # Any traffic for this cabinet means it's alive — start heartbeating it.
    _learn_cabinet(client, locker_id)
    try:
        data = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print(f"[SIM] Ignoring non-JSON payload on {msg.topic}")
        return

    if msg.topic.endswith("/command/sync"):
        # Booking -> IoT sync: no reply expected, just mirror the cell state.
        box_id = data.get("boxId", data.get("box_id"))
        state = data.get("state")
        order_id = data.get("orderId")
        order_part = f" order={order_id}" if order_id is not None else ""
        print(f"[SIM] SYNC: cabinet display updated -> locker={locker_id} box={box_id} state={state}{order_part}")
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
    with _known_lock:
        _known_cabinets.update(SIM_HEARTBEAT_CABINETS)
    print("=" * 60)
    print("  Demo cabinet simulator (no hardware required)")
    print(f"  Broker: {host}:{port}")
    print(f"  Reply delay: {SIM_DELAY_SECONDS}s, force fail: {SIM_FORCE_FAIL}")
    print(f"  Heartbeat: every {SIM_HEARTBEAT_SECONDS}s for known cabinets")
    if SIM_HEARTBEAT_CABINETS:
        print(f"  Seeded cabinets (ONLINE on connect): {', '.join(SIM_HEARTBEAT_CABINETS)}")
    else:
        print("  Cabinets learned from traffic (set SIM_HEARTBEAT_CABINETS=2,3 to pre-seed)")
    print("  This stands in for the real cabinet runtime (main.py) until")
    print("  Raspberry Pi/Arduino hardware + the setup handshake are ready.")
    print("=" * 60)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(host, port, keepalive=60)

    threading.Thread(target=_heartbeat_loop, args=(client,), daemon=True).start()

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[SIM] Shutting down...")
        client.disconnect()


if __name__ == "__main__":
    main()
