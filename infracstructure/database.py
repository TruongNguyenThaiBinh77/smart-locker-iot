import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
from utils.logger import get_logger

logger = get_logger("DatabaseManager")

class DatabaseManager:
    """
    Quản lý lưu trữ local bằng SQLite cho AISL IoT.
    Lưu log MQTT và các sự kiện của locker.
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        # Đảm bảo thư mục tồn tại
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Khởi tạo các bảng nếu chưa tồn tại."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Bảng log MQTT messages
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS mqtt_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        payload TEXT,
                        direction TEXT CHECK(direction IN ('IN', 'OUT')),
                        timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    )
                """)

                # Bảng sự kiện Locker (mở, đóng, lỗi, ack)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS locker_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        locker_id TEXT,
                        slot_index INTEGER,
                        event_type TEXT NOT NULL, -- OPEN, CLOSE, ACK, ERROR
                        status TEXT,              -- SUCCESS, FAIL
                        message TEXT,
                        command_id TEXT,
                        timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    )
                """)

                # Bảng lưu thông tin Location (Dùng chung cho các cabinet trên 1 RPi)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS locations (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        address TEXT,
                        updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    )
                """)

                # Bảng lưu trạng thái danh sách các Cabinet kết nối qua RS485
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cabinets (
                        id TEXT PRIMARY KEY,
                        location_id TEXT,
                        name TEXT,
                        total_rows INTEGER,
                        total_columns INTEGER,
                        slave_id INTEGER, -- ID Arduino cho RS485
                        heartbeat_interval INTEGER,
                        is_synced BOOLEAN,
                        updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
                        FOREIGN KEY (location_id) REFERENCES locations (id)
                    )
                """)

                # Bảng lưu thông tin từng Locker (mapped từ setup)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS lockers (
                        id TEXT PRIMARY KEY, -- Locker UUID
                        cabinet_id TEXT,
                        slot_index INTEGER,
                        locker_label TEXT,
                        updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now')),
                        FOREIGN KEY (cabinet_id) REFERENCES cabinets (id)
                    )
                """)

                # Bảng lưu cấu hình MQTT (thay thế env)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS mqtt_config (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        broker TEXT NOT NULL,
                        port INTEGER NOT NULL,
                        username TEXT,
                        password TEXT,
                        use_tls BOOLEAN DEFAULT 1,
                        updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    )
                """)

                # Bảng lưu các cấu hình hệ thống khác (key-value)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    )
                """)
                
                conn.commit()
                logger.info(f"Database initialized at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")

    # ─── System Settings ───

    def save_system_setting(self, key: str, value: Any):
        """Lưu hoặc cập nhật một cấu hình hệ thống."""
        try:
            val_str = str(value)
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO system_settings (key, value, updated_at)
                    VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
                    """,
                    (key, val_str)
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to save system setting {key}: {e}")

    def get_system_setting(self, key: str, default: Any = None) -> Any:
        """Lấy một cấu hình hệ thống."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                return row[0] if row else default
        except sqlite3.Error as e:
            logger.error(f"Failed to get system setting {key}: {e}")
            return default

    # ─── MQTT Logging ───

    def log_mqtt(self, topic: str, payload: Any, direction: str = "IN"):
        """Lưu log message MQTT."""
        try:
            payload_str = payload if isinstance(payload, str) else json.dumps(payload)
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO mqtt_logs (topic, payload, direction) VALUES (?, ?, ?)",
                    (topic, payload_str, direction)
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to log MQTT: {e}")

    # ─── Location & Cabinet Persistence ───

    def save_location(self, data: Dict[str, Any]):
        """Lưu hoặc cập nhật thông tin Location."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO locations (id, name, address, updated_at)
                    VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        address = excluded.address,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
                    """,
                    (data.get("id"), data.get("name"), data.get("address"))
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to save location to DB: {e}")

    def get_location(self) -> Optional[Dict[str, Any]]:
        """Lấy thông tin location (thường chỉ có 1 trên mỗi RPi)."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM locations LIMIT 1")
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get location from DB: {e}")
            return None

    def save_cabinet(self, data: Dict[str, Any]):
        """Lưu hoặc cập nhật trạng thái một Cabinet."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO cabinets 
                    (id, location_id, name, total_rows, total_columns, slave_id, heartbeat_interval, is_synced, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    ON CONFLICT(id) DO UPDATE SET
                        location_id = excluded.location_id,
                        name = excluded.name,
                        total_rows = excluded.total_rows,
                        total_columns = excluded.total_columns,
                        slave_id = excluded.slave_id,
                        heartbeat_interval = excluded.heartbeat_interval,
                        is_synced = excluded.is_synced,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
                    """,
                    (
                        data.get("id"),
                        data.get("locationId"),
                        data.get("name"),
                        data.get("totalRows", 0),
                        data.get("totalColumns", 0),
                        data.get("slaveId"),
                        data.get("heartbeatInterval", 60),
                        data.get("isSynced", False)
                    )
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to save cabinet to DB: {e}")

    def get_cabinets(self) -> list:
        """Lấy danh sách tất cả các cabinet."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM cabinets")
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get cabinets from DB: {e}")
            return []

    def save_lockers(self, cabinet_id: str, lockers: list):
        """Lưu danh sách locker cho 1 cabinet."""
        try:
            with self._get_connection() as conn:
                # Xoá cũ
                conn.execute("DELETE FROM lockers WHERE cabinet_id = ?", (cabinet_id,))
                # Thêm mới
                for locker in lockers:
                    conn.execute(
                        """
                        INSERT INTO lockers (id, cabinet_id, slot_index, locker_label)
                        VALUES (?, ?, ?, ?)
                        """,
                        (locker["id"], cabinet_id, locker["slotIndex"], locker["label"])
                    )
                conn.commit()
            logger.info(f"Saved {len(lockers)} lockers for cabinet {cabinet_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save lockers to DB: {e}")

    def get_lockers(self, cabinet_id: str) -> list:
        """Lấy danh sách locker của 1 cabinet."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM lockers WHERE cabinet_id = ?", (cabinet_id,))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get lockers from DB: {e}")
            return []

    def get_locker_by_slot(self, cabinet_id: str, slot_index: int) -> Optional[Dict[str, Any]]:
        """Tìm locker theo slotIndex."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM lockers WHERE cabinet_id = ? AND slot_index = ?", 
                    (cabinet_id, slot_index)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get locker by slot from DB: {e}")
            return None

    def clear_all_state(self):
        """Xoá sạch thông tin location và các cabinet."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM lockers")
                conn.execute("DELETE FROM cabinets")
                conn.execute("DELETE FROM locations")
        except sqlite3.Error as e:
            logger.error(f"Failed to clear state in DB: {e}")

    # ─── MQTT Configuration ───

    def save_mqtt_config(self, data: Dict[str, Any]):
        """Lưu hoặc cập nhật cấu hình MQTT."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO mqtt_config 
                    (id, broker, port, username, password, use_tls, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f', 'now'))
                    ON CONFLICT(id) DO UPDATE SET
                        broker = excluded.broker,
                        port = excluded.port,
                        username = excluded.username,
                        password = excluded.password,
                        use_tls = excluded.use_tls,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%f', 'now')
                    """,
                    (
                        data.get("broker"),
                        data.get("port"),
                        data.get("username"),
                        data.get("password"),
                        data.get("useTls", True)
                    )
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to save MQTT config to DB: {e}")

    def get_mqtt_config(self) -> Optional[Dict[str, Any]]:
        """Lấy cấu hình MQTT từ DB."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM mqtt_config WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    d = dict(row)
                    return {
                        "broker": d["broker"],
                        "port": d["port"],
                        "username": d["username"],
                        "password": d["password"],
                        "useTls": bool(d["use_tls"])
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get MQTT config from DB: {e}")
            return None

    # ─── Locker Events ───

    def log_event(self, 
                  event_type: str, 
                  locker_id: Optional[str] = None, 
                  slot_index: Optional[int] = None,
                  status: Optional[str] = None, 
                  message: Optional[str] = None,
                  command_id: Optional[str] = None):
        """Lưu sự kiện locker."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO locker_events 
                    (locker_id, slot_index, event_type, status, message, command_id) 
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (locker_id, slot_index, event_type, status, message, command_id)
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to log locker event: {e}")

    # ─── Querying (Optional/Future use) ───

    def get_recent_logs(self, limit: int = 50):
        """Lấy các log MQTT gần nhất."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM mqtt_logs ORDER BY id DESC LIMIT ?", 
                    (limit,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error:
            return []
