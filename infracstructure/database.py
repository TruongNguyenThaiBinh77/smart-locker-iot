import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import psycopg2
import psycopg2.extras
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("DatabaseManager")

class DatabaseManager:
    """
    Quản lý lưu trữ local bằng PostgreSQL cho AISL IoT.
    Lưu log MQTT và các sự kiện của locker.
    """

    def __init__(self, db_path=None):
        # db_path is ignored for Postgres, using settings instead
        self._init_db()

    def _get_connection(self):
        return psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            dbname=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD
        )

    def _init_db(self):
        """Khởi tạo các bảng nếu chưa tồn tại."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Bảng log MQTT messages
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS mqtt_logs (
                            id SERIAL PRIMARY KEY,
                            topic TEXT NOT NULL,
                            payload TEXT,
                            direction TEXT CHECK(direction IN ('IN', 'OUT')),
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Bảng sự kiện Locker (mở, đóng, lỗi, ack)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS locker_events (
                            id SERIAL PRIMARY KEY,
                            locker_id TEXT,
                            slot_index INTEGER,
                            event_type TEXT NOT NULL,
                            status TEXT,
                            message TEXT,
                            command_id TEXT,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Bảng lưu thông tin Location
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS locations (
                            id TEXT PRIMARY KEY,
                            name TEXT,
                            address TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Bảng lưu trạng thái danh sách các Cabinet
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS cabinets (
                            id TEXT PRIMARY KEY,
                            location_id TEXT REFERENCES locations(id) ON DELETE CASCADE,
                            name TEXT,
                            total_rows INTEGER,
                            total_columns INTEGER,
                            slave_id INTEGER,
                            heartbeat_interval INTEGER,
                            is_synced BOOLEAN,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Bảng lưu thông tin từng Locker
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS lockers (
                            id TEXT PRIMARY KEY,
                            cabinet_id TEXT REFERENCES cabinets(id) ON DELETE CASCADE,
                            slot_index INTEGER,
                            locker_label TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Bảng lưu cấu hình MQTT
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS mqtt_config (
                            id INTEGER PRIMARY KEY CHECK (id = 1),
                            broker TEXT NOT NULL,
                            port INTEGER NOT NULL,
                            username TEXT,
                            password TEXT,
                            use_tls BOOLEAN DEFAULT TRUE,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    # Bảng lưu các cấu hình hệ thống khác
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS system_settings (
                            key TEXT PRIMARY KEY,
                            value TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                conn.commit()
                logger.info(f"PostgreSQL Database initialized at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
        except psycopg2.Error as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")

    # ─── System Settings ───

    def save_system_setting(self, key: str, value: Any):
        """Lưu hoặc cập nhật một cấu hình hệ thống."""
        try:
            val_str = str(value)
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO system_settings (key, value, updated_at)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (key) DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (key, val_str)
                    )
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to save system setting {key}: {e}")

    def get_system_setting(self, key: str, default: Any = None) -> Any:
        """Lấy một cấu hình hệ thống."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
                    row = cursor.fetchone()
                    return row[0] if row else default
        except psycopg2.Error as e:
            logger.error(f"Failed to get system setting {key}: {e}")
            return default

    # ─── MQTT Logging ───

    def log_mqtt(self, topic: str, payload: Any, direction: str = "IN"):
        """Lưu log message MQTT."""
        try:
            payload_str = payload if isinstance(payload, str) else json.dumps(payload)
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO mqtt_logs (topic, payload, direction) VALUES (%s, %s, %s)",
                        (topic, payload_str, direction)
                    )
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to log MQTT: {e}")

    # ─── Location & Cabinet Persistence ───

    def save_location(self, data: Dict[str, Any]):
        """Lưu hoặc cập nhật thông tin Location."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO locations (id, name, address, updated_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            address = EXCLUDED.address,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (data.get("id"), data.get("name"), data.get("address"))
                    )
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to save location to DB: {e}")

    def get_location(self) -> Optional[Dict[str, Any]]:
        """Lấy thông tin location (thường chỉ có 1 trên mỗi RPi)."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM locations LIMIT 1")
                    row = cursor.fetchone()
                    return dict(row) if row else None
        except psycopg2.Error as e:
            logger.error(f"Failed to get location from DB: {e}")
            return None

    def save_cabinet(self, data: Dict[str, Any]):
        """Lưu hoặc cập nhật trạng thái một Cabinet."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO cabinets 
                        (id, location_id, name, total_rows, total_columns, slave_id, heartbeat_interval, is_synced, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            location_id = EXCLUDED.location_id,
                            name = EXCLUDED.name,
                            total_rows = EXCLUDED.total_rows,
                            total_columns = EXCLUDED.total_columns,
                            slave_id = EXCLUDED.slave_id,
                            heartbeat_interval = EXCLUDED.heartbeat_interval,
                            is_synced = EXCLUDED.is_synced,
                            updated_at = CURRENT_TIMESTAMP
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
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to save cabinet to DB: {e}")

    def get_cabinets(self) -> list:
        """Lấy danh sách tất cả các cabinet."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM cabinets")
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Failed to get cabinets from DB: {e}")
            return []

    def save_lockers(self, cabinet_id: str, lockers: list):
        """Lưu danh sách locker cho 1 cabinet."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Xoá cũ
                    cursor.execute("DELETE FROM lockers WHERE cabinet_id = %s", (cabinet_id,))
                    # Thêm mới
                    for locker in lockers:
                        cursor.execute(
                            """
                            INSERT INTO lockers (id, cabinet_id, slot_index, locker_label)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (locker["id"], cabinet_id, locker["slotIndex"], locker["label"])
                        )
                conn.commit()
            logger.info(f"Saved {len(lockers)} lockers for cabinet {cabinet_id}")
        except psycopg2.Error as e:
            logger.error(f"Failed to save lockers to DB: {e}")

    def get_lockers(self, cabinet_id: str) -> list:
        """Lấy danh sách locker của 1 cabinet."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM lockers WHERE cabinet_id = %s", (cabinet_id,))
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f"Failed to get lockers from DB: {e}")
            return []

    def get_locker_by_slot(self, cabinet_id: str, slot_index: int) -> Optional[Dict[str, Any]]:
        """Tìm locker theo slotIndex."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM lockers WHERE cabinet_id = %s AND slot_index = %s", 
                        (cabinet_id, slot_index)
                    )
                    row = cursor.fetchone()
                    return dict(row) if row else None
        except psycopg2.Error as e:
            logger.error(f"Failed to get locker by slot from DB: {e}")
            return None

    def clear_all_state(self):
        """Xoá sạch thông tin location và các cabinet."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM lockers")
                    cursor.execute("DELETE FROM cabinets")
                    cursor.execute("DELETE FROM locations")
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to clear state in DB: {e}")

    # ─── MQTT Configuration ───

    def save_mqtt_config(self, data: Dict[str, Any]):
        """Lưu hoặc cập nhật cấu hình MQTT."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO mqtt_config 
                        (id, broker, port, username, password, use_tls, updated_at)
                        VALUES (1, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            broker = EXCLUDED.broker,
                            port = EXCLUDED.port,
                            username = EXCLUDED.username,
                            password = EXCLUDED.password,
                            use_tls = EXCLUDED.use_tls,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            data.get("broker"),
                            data.get("port"),
                            data.get("username"),
                            data.get("password"),
                            data.get("useTls", True)
                        )
                    )
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to save MQTT config to DB: {e}")

    def get_mqtt_config(self) -> Optional[Dict[str, Any]]:
        """Lấy cấu hình MQTT từ DB."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT * FROM mqtt_config WHERE id = 1")
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
        except psycopg2.Error as e:
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
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO locker_events 
                        (locker_id, slot_index, event_type, status, message, command_id) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (locker_id, slot_index, event_type, status, message, command_id)
                    )
                conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to log locker event: {e}")

    # ─── Querying ───

    def get_recent_logs(self, limit: int = 50):
        """Lấy các log MQTT gần nhất."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM mqtt_logs ORDER BY id DESC LIMIT %s", 
                        (limit,)
                    )
                    return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error:
            return []
