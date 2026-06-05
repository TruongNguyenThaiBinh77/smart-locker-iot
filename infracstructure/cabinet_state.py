import json
from pathlib import Path
from typing import Optional
from utils.logger import get_logger

logger = get_logger("CabinetState")

# Mặc định lưu cùng thư mục config
_DEFAULT_STATE_PATH = str(Path(__file__).parent.parent / "config" / "cabinet_state.json")


class CabinetState:
    """
    Quản lý trạng thái hệ thống: lưu thông tin Location và danh sách các Cabinet.
    Hỗ trợ scale nhiều cabinet trên 1 Gateway RPi (kết nối qua RS485).
    """

    def __init__(self, state_path: str = _DEFAULT_STATE_PATH, db_manager=None):
        self._path = Path(state_path)
        self._db = db_manager
        
        self._location: Optional[dict] = None
        self._cabinets: dict[str, dict] = {} # Key là cabinet_id
        self._lockers: dict[str, dict[int, dict]] = {} # cabinet_id -> slot_index -> locker_data
        
        self.load()

    # ─── Properties ───

    @property
    def location(self) -> Optional[dict]:
        return self._location

    @property
    def all_cabinets(self) -> list:
        return list(self._cabinets.values())

    @property
    def is_configured(self) -> bool:
        """Đã được config ít nhất 1 location và 1 cabinet."""
        return self._location is not None and len(self._cabinets) > 0

    @property
    def heartbeat_interval(self) -> int:
        """Lấy interval từ bất kỳ cabinet nào (thường giống nhau trên cùng 1 gateway)."""
        if not self._cabinets:
            return 60
        # Lấy bản ghi đầu tiên
        first_cab = next(iter(self._cabinets.values()))
        return first_cab.get("heartbeatInterval", 60)

    def get_cabinet_by_id(self, cabinet_id: str) -> Optional[dict]:
        return self._cabinets.get(cabinet_id)

    def get_cabinet_by_name(self, name: str) -> Optional[dict]:
        for cab in self._cabinets.values():
            if cab.get("name") == name:
                return cab
        return None

    # ─── Persistence ───

    def save_location(self, location_id: str, name: str, address: str):
        """Lưu thông tin Location."""
        self._location = {
            "id": location_id,
            "name": name,
            "address": address
        }
        
        if self._db:
            self._db.save_location(self._location)
        self._save_to_json()
        logger.info(f"Location saved: {name} ({location_id})")

    def save_cabinet(self, cabinet_id: str, name: str, 
                     total_rows: int = 0, total_columns: int = 0,
                     slave_id: int = 0,
                     heartbeat_interval: int = 60,
                     is_synced: bool = False):
        """Lưu hoặc cập nhật thông tin một Cabinet."""
        if not self._location:
            logger.error("Cannot save cabinet without location")
            return

        cabinet_data = {
            "id": cabinet_id,
            "locationId": self._location["id"],
            "name": name,
            "totalRows": total_rows,
            "totalColumns": total_columns,
            "slaveId": slave_id,
            "heartbeatInterval": heartbeat_interval,
            "isSynced": is_synced
        }
        
        self._cabinets[cabinet_id] = cabinet_data
        
        if self._db:
            self._db.save_cabinet(cabinet_data)
        self._save_to_json()
        
        logger.info(
            f"Cabinet saved: {name} (id={cabinet_id}, slave={slave_id}, layout={total_rows}x{total_columns})"
        )

    def load(self):
        """Load state từ file JSON hoặc Database."""
        data = None
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.debug("System state loaded from JSON")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load state from JSON: {e}")

        if not data and self._db:
            loc = self._db.get_location()
            cabs = self._db.get_cabinets()
            if loc:
                data = {"location": loc, "cabinets": cabs}
                logger.info("System state recovered from Database")

        if not data:
            return

        self._location = data.get("location")
        cabinets_list = data.get("cabinets", [])
        self._cabinets = {c["id"]: c for c in cabinets_list}
        
        # Load lockers for each cabinet
        for cab_id in self._cabinets:
            if self._db:
                lockers = self._db.get_lockers(cab_id)
                self._lockers[cab_id] = {l["slot_index"]: l for l in lockers}
        
        cab_count = len(self._cabinets)
        loc_name = self._location.get("name") if self._location else "None"
        logger.info(f"System state initialized: Location={loc_name}, Cabinets={cab_count}")

    def save_lockers(self, cabinet_id: str, lockers: list):
        """Lưu danh sách locker và cập nhật cache memory."""
        if self._db:
            self._db.save_lockers(cabinet_id, lockers)
        
        # Update memory cache
        self._lockers[cabinet_id] = {l["slotIndex"]: {
            "id": l["id"],
            "cabinet_id": cabinet_id,
            "slot_index": l["slotIndex"],
            "locker_label": l["label"]
        } for l in lockers}

    def get_locker_by_slot(self, cabinet_id: str, slot_index: int) -> Optional[dict]:
        """Lấy thông tin locker từ memory cache."""
        cabinet_lockers = self._lockers.get(cabinet_id, {})
        return cabinet_lockers.get(slot_index)

    def _save_to_json(self):
        """Ghi toàn bộ state ra JSON."""
        try:
            data = {
                "location": self._location,
                "cabinets": list(self._cabinets.values())
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Failed to save state to JSON: {e}")

    def clear(self):
        """Xoá sạch state."""
        self._location = None
        self._cabinets = {}

        if self._path.exists():
            try:
                self._path.unlink()
            except IOError as e:
                logger.error(f"Failed to clear JSON state: {e}")

        if self._db:
            self._db.clear_all_state()

        logger.info("All system state cleared")
