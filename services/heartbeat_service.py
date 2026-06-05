import time
import threading
from datetime import datetime, timezone
from infracstructure.serial_manager import MAX_SLOTS
from domain.models import HeartbeatPayload
from utils.logger import get_logger

logger = get_logger("HeartbeatService")

# Heartbeat interval mặc định (giây)
DEFAULT_HEARTBEAT_INTERVAL = 60


class HeartbeatService:
    """
    Publish heartbeat định kỳ lên MQTT để BE biết RPi còn online.

    Topic: cabinet/{cabinetName}/heartbeat
    Payload: {
        cabinetId, timestamp, status: "online",
        lockers: [{ slotIndex, hwState }]
    }
    """

    def __init__(self, mqtt_client, cabinet_state,
                 interval: int = DEFAULT_HEARTBEAT_INTERVAL):
        self.mqtt = mqtt_client
        self.cabinet_state = cabinet_state
        self.interval = interval

        self._thread: threading.Thread | None = None
        self._running = False
        self._start_time = time.time()

        # Theo dõi hwState của từng slot
        # Mặc định tất cả CLOSED khi chưa có thông tin
        self._locker_states: dict[int, str] = {}

    # ─── Locker state tracking ───

    def update_locker_state(self, cabinet_id: str, slot_index: int, hw_state: str):
        """Cập nhật hwState cho slot của một cabinet."""
        if cabinet_id not in self._locker_states:
            self._locker_states[cabinet_id] = {}
        self._locker_states[cabinet_id][slot_index] = hw_state

    def _get_lockers_status(self, cabinet_id: str) -> list:
        """Lấy danh sách trạng thái lockers cho một cabinet."""
        lockers = []
        # Lấy info cabinet từ state để biết số rows/cols
        cab = self.cabinet_state.get_cabinet_by_id(cabinet_id)
        if not cab:
            return []

        total_slots = cab.get("totalRows", 0) * cab.get("totalColumns", 0)
        # Nếu chưa có state tracking, mặc định CLOSED
        cabinet_states = self._locker_states.get(cabinet_id, {})
        
        for slot in range(total_slots):
            # [NEW] Lookup UUID để mapping chuẩn
            locker_info = self.cabinet_state.get_locker_by_slot(cabinet_id, slot)
            lockers.append({
                "lockerId": locker_info["id"] if locker_info else f"unknown-{slot}",
                "slotIndex": slot,
                "hwState": cabinet_states.get(slot, "CLOSING"),
            })
        return lockers

    # ─── Heartbeat loop ───

    def start(self):
        """Bắt đầu gửi heartbeat định kỳ (background thread)."""
        if not self.cabinet_state.is_configured:
            logger.info("Heartbeat not started – no cabinets configured yet")
            return

        if self._running:
            logger.warning("Heartbeat already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="HeartbeatThread"
        )
        self._thread.start()
        logger.info(f"Heartbeat service started (interval: {self.interval}s)")

    def stop(self):
        """Dừng heartbeat."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            logger.info("Heartbeat service stopped")

    def _heartbeat_loop(self):
        """Loop gửi heartbeat mỗi interval giây."""
        while self._running:
            try:
                self._publish_all_heartbeats()
            except Exception as e:
                logger.error(f"Heartbeat publish error: {e}")

            # Sleep theo interval nhưng check _running mỗi giây để shutdown nhanh
            for _ in range(self.interval):
                if not self._running:
                    return
                time.sleep(1)

    def _publish_all_heartbeats(self):
        """Build và publish heartbeat cho TẤT CẢ các cabinet đã config."""
        for cab in self.cabinet_state.all_cabinets:
            self._publish_single_heartbeat(cab)

    def _publish_single_heartbeat(self, cabinet: dict):
        """Build và publish heartbeat cho 1 cabinet."""
        cabinet_id = cabinet["id"]
        cabinet_name = cabinet["name"]
        prefix = f"cabinet/{cabinet_name}"
        topic = f"{prefix}/heartbeat"

        payload = HeartbeatPayload(
            cabinetId=cabinet_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="online",
            lockers=self._get_lockers_status(cabinet_id),
        )

        self.mqtt.publish(topic, payload.to_json(), qos=0)
        logger.debug(f"💓 Heartbeat → {topic}")
