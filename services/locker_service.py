import json
import time
import threading
import platform
from datetime import datetime, timezone
from config.settings import settings
from domain.enums import CommandAction, LockerHwState
from domain.models import OpenAckPayload
from services.setup_handler import SetupHandler
from utils.logger import get_logger

logger = get_logger("LockerService")


class LockerService:
    def __init__(self, mqtt_client, hardware_controller,
                 serial_manager=None, cabinet_state=None,
                 heartbeat_service=None, db_manager=None,
                 discovery_service=None):
        self.mqtt = mqtt_client
        self.hw = hardware_controller
        self.serial = serial_manager
        self.cabinet_state = cabinet_state
        self.heartbeat = heartbeat_service
        self.db = db_manager
        self.discovery = discovery_service

        self.active_commands = {}

        # Setup handler (nếu có serial manager)
        self.setup_handler = None
        if self.serial:
            self.setup_handler = SetupHandler(
                mqtt_client,
                serial_manager,
                cabinet_state=cabinet_state,
                on_setup_complete=self._on_setup_complete,
            )

        self._start_time = time.time()

    # ═══════════════════════════════════════════════════════════
    #  MESSAGE ROUTING
    # ═══════════════════════════════════════════════════════════

    def handle_incoming_message(self, topic: str, payload_str: str):
        """
        Xử lý messages từ MQTT.
        Topics:
            cabinet/{cabinetName}/command/setup
            cabinet/{cabinetName}/command/open
            cabinet/{cabinetName}/command/close
            iot/{macAddress}/discovery/start
        """
        try:
            # Log MQTT message to database
            if self.db:
                self.db.log_mqtt(topic, payload_str, direction="IN")

            # Route: Discovery start command
            if topic.endswith("/discovery/start"):
                logger.info(f"Received discovery trigger on {topic}")
                if self.discovery:
                    # Parse maxCabinets from payload if available
                    max_cabinets = None
                    try:
                        data = json.loads(payload_str)
                        max_cabinets = data.get("maxCabinets")
                    except Exception:
                        pass
                        
                    threading.Thread(target=self.discovery.discover_and_report, 
                                     args=(max_cabinets,), daemon=True).start()
                else:
                    logger.error("Discovery service not available in LockerService")
                return

            data = json.loads(payload_str)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON payload on {topic}")
            return

        # ─── Route: Setup command ───
        if topic.endswith("/command/setup"):
            self._handle_setup_command(topic, data)
            return

        # ─── Route: Clear Setup command ───
        if topic.endswith("/command/clear-setup"):
            self._handle_clear_setup_command(topic, data)
            return

        # ─── Route: Open command ───
        if "/command/open" in topic:
            self._handle_open_command(topic, data)
            return

        # ─── Route: Close command ───
        if "/command/close" in topic:
            self._handle_close_command(topic, data)
            return

        logger.debug(f"Unhandled topic: {topic}")

    # ═══════════════════════════════════════════════════════════
    #  SETUP COMMAND (BE → RPi)
    # ═══════════════════════════════════════════════════════════

    def _handle_setup_command(self, topic: str, data: dict):
        """
        Nhận lệnh setup từ BE.
        """
        action = data.get("action", "")
        if action not in [CommandAction.SETUP_LOCKERS.value, CommandAction.BULK_SETUP_LOCKERS.value]:
            logger.debug(f"Ignoring action: {action}")
            return

        # Check macAddress
        payload_mac = data.get("macAddress", "").lower()
        my_mac = settings.MAC_ADDRESS.lower()

        if payload_mac != my_mac:
            logger.warning(f"Ignoring setup command – MAC mismatch (payload={payload_mac}, mine={my_mac})")
            return

        # Extract prefix: iot/{macAddress}
        # Topic format: iot/{macAddress}/command/setup
        parts = topic.split("/")
        prefix = f"{parts[0]}/{parts[1]}"

        logger.warning(f"📋 Setup command received for gateway {prefix} (Action: {action})")

        # Chạy setup handler
        if self.setup_handler:
            self.setup_handler.handle(data, prefix)
        else:
            logger.error("Setup handler not available")

    # ═══════════════════════════════════════════════════════════
    #  CLEAR SETUP COMMAND
    # ═══════════════════════════════════════════════════════════

    def _handle_clear_setup_command(self, topic: str, data: dict):
        """Xoá toàn bộ cấu hình."""
        action = data.get("action", "")
        if action != CommandAction.CLEAR_SETUP.value: return

        def do_clear():
            if self.cabinet_state:
                self.cabinet_state.clear()
                if self.heartbeat: self.heartbeat.stop()
                logger.info("System state cleared")

        threading.Thread(target=do_clear, daemon=True).start()

    # ═══════════════════════════════════════════════════════════
    #  OPEN COMMAND (BE → RPi)
    # ═══════════════════════════════════════════════════════════

    def _handle_open_command(self, topic: str, data: dict):
        """
        Topic: cabinet/{cabinetName}/command/open
        """
        # Extract cabinet name từ topic
        parts = topic.split("/")
        if len(parts) < 2: return
        cabinet_name = parts[1]

        # Tìm cabinet trong state
        cab = self.cabinet_state.get_cabinet_by_name(cabinet_name)
        if not cab:
            logger.error(f"Cannot open locker – cabinet '{cabinet_name}' not configured")
            return

        cabinet_id = cab["id"]
        slave_id = cab.get("slaveId", 1)
        locker_id = data.get("lockerId", "")
        slot_index = data.get("slotIndex")
        command_id = data.get("commandId")

        if slot_index is None: return

        logger.warning(f"🔓 OPEN REQUEST: cabinet={cabinet_name}, slot={slot_index}, cmdId={command_id}")

        # Gửi serial command
        if self.serial:
            # Immediately set state to OPENING (Optimistic, but will be corrected by result)
            if self.heartbeat:
                self.heartbeat.update_locker_state(cabinet_id, slot_index, LockerHwState.OPENING.value)

            result = self.serial.open_slot(slot_index, slave_id=slave_id)
            ok = result.get("result") == "OK"
            door_is_closed = result.get("door", True) # door: True means closed

            # Determine final state based on physical sensor
            if ok and not door_is_closed:
                status = "SUCCESS"
                message = "Door opened successfully"
                hw_state = LockerHwState.OPENING.value
                error_code = None
            else:
                status = "FAILED"
                # Nếu không mở được (vẫn closed), set state là CLOSING như user yêu cầu
                hw_state = LockerHwState.CLOSING.value
                if ok and door_is_closed:
                    message = "Command OK but door remained closed (jammed?)"
                    error_code = "JAMMED"
                else:
                    message = f"Hardware error: {result.get('error')}"
                    error_code = result.get("error", "SERIAL_ERROR")
            
            # --- 1. Publish Result (BE waits for this) ---
            result_topic = f"cabinet/{cabinet_name}/command/open/result"
            res_payload = {
                "commandId": command_id,
                "lockerId": locker_id,
                "slotIndex": slot_index,
                "status": status,
                "hwState": hw_state,
                "errorCode": error_code,
                "errorMessage": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.mqtt.publish(result_topic, json.dumps(res_payload), qos=1)

            # --- 2. Publish legacy ACK (for compatibility) ---
            ack_topic = f"cabinet/{cabinet_name}/locker/{locker_id}/ack"
            ack_payload = OpenAckPayload(
                lockerId=locker_id,
                slotIndex=slot_index,
                status=status,
                message=message,
                timestamp=datetime.now(timezone.utc).isoformat(),
                errorCode=error_code
            ).to_json()
            self.mqtt.publish(ack_topic, ack_payload, qos=1)

            if self.heartbeat:
                self.heartbeat.update_locker_state(cabinet_id, slot_index, hw_state)
        else:
            logger.error("Serial not available")

    # ═══════════════════════════════════════════════════════════
    #  CLOSE COMMAND (BE → RPi)
    # ═══════════════════════════════════════════════════════════

    def _handle_close_command(self, topic: str, data: dict):
        """
        Topic: cabinet/{cabinetName}/command/close
        """
        parts = topic.split("/")
        if len(parts) < 2: return
        cabinet_name = parts[1]

        cab = self.cabinet_state.get_cabinet_by_name(cabinet_name)
        if not cab:
            logger.error(f"Cannot close locker – cabinet '{cabinet_name}' not configured")
            return

        cabinet_id = cab["id"]
        slave_id = cab.get("slaveId", 1)
        locker_id = data.get("lockerId", "")
        slot_index = data.get("slotIndex")
        command_id = data.get("commandId")

        if slot_index is None: return

        logger.warning(f"🔒 CLOSE REQUEST: cabinet={cabinet_name}, slot={slot_index}, cmdId={command_id}")

        if self.serial:
            result = self.serial.close_slot(slot_index, slave_id=slave_id)
            ok = result.get("result") == "OK"
            door_is_closed = result.get("door", True)

            if ok and door_is_closed:
                status = "SUCCESS"
                message = "Door is closed and locked"
                hw_state = LockerHwState.CLOSING.value
                error_code = None
            else:
                status = "FAILED"
                # Cố gắng report đúng trạng thái thực tế
                hw_state = LockerHwState.CLOSING.value if door_is_closed else LockerHwState.OPENING.value
                message = "Door failed to lock or is still open"
                error_code = result.get("error", "HARDWARE_FAILURE")

            # Publish Result
            result_topic = f"cabinet/{cabinet_name}/command/close/result"
            res_payload = {
                "commandId": command_id,
                "lockerId": locker_id,
                "slotIndex": slot_index,
                "status": status,
                "hwState": hw_state,
                "errorCode": error_code,
                "errorMessage": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.mqtt.publish(result_topic, json.dumps(res_payload), qos=1)

            if self.heartbeat:
                self.heartbeat.update_locker_state(cabinet_id, slot_index, hw_state)
        else:
            logger.error("Serial not available")

    # ═══════════════════════════════════════════════════════════
    #  DOOR EVENT (Arduino → RPi → BE)
    # ═══════════════════════════════════════════════════════════

    def handle_door_event(self, slot_index: int, event_type: str, slave_id: int = 1):
        """
        Callback khi Arduino detect sensor đổi trạng thái.
        """
        # Tìm cabinet đang map với slave_id này
        # (Giả định 1 slave_id map với 1 cabinet_id duy nhất)
        cab = None
        for c in self.cabinet_state.all_cabinets:
            if c.get("slaveId") == slave_id:
                cab = c
                break
        
        if not cab:
            logger.warning(f"Event ignored – no cabinet mapped to Slave {slave_id}")
            return

        cabinet_id = cab["id"]
        cabinet_name = cab["name"]
        prefix = f"cabinet/{cabinet_name}"

        # [NEW] Lookup lockerId from state (chuẩn hóa topic)
        locker_info = self.cabinet_state.get_locker_by_slot(cabinet_id, slot_index)
        locker_id = locker_info["id"] if locker_info else f"unknown-{slot_index}"

        logger.warning(f"门 {event_type}: cabinet={cabinet_name}, slot={slot_index}, lockerId={locker_id}")

        # 1. Publish Status (Chuẩn: {prefix}/locker/{lockerId}/status)
        status_topic = f"{prefix}/locker/{locker_id}/status"
        hw_state = LockerHwState.OPENING.value if event_type == "DOOR_OPENED" else LockerHwState.CLOSING.value
        
        status_payload = {
            "lockerId": locker_id,
            "slotIndex": slot_index,
            "hwState": hw_state,
            "doorSensor": True if event_type == "DOOR_OPENED" else False,
            "lockSensor": False, # Placeholder as hardware might not report this yet
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.mqtt.publish(status_topic, json.dumps(status_payload), qos=1)

        # 2. Publish Close Command if needed (legacy compatibility or specific logic)
        if event_type == "DOOR_CLOSED":
            payload = json.dumps({"cabinetId": cabinet_id, "slotIndex": slot_index})
            self.mqtt.publish(f"{prefix}/command/close", payload, qos=1)
            
        if self.heartbeat:
            self.heartbeat.update_locker_state(cabinet_id, slot_index, hw_state)

    def _on_setup_complete(self, cabinet_name: str):
        """Setup xong -> subscribe topic mở của cabinet đó."""
        logger.info(f"Subscribing commands for new cabinet: {cabinet_name}")
        self.mqtt.subscribe_open_command(cabinet_name)
        if self.heartbeat: self.heartbeat.start()

    # ═══════════════════════════════════════════════════════════
    #  UTILITY METHODS
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _get_ip_address() -> str:
        """Lấy IP address hiện tại."""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "0.0.0.0"