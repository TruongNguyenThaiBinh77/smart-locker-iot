import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger("Settings")


def _get_mac_address() -> str:
    """Lấy MAC address thật của máy."""
    mac_num = uuid.getnode()
    mac = ':'.join(('%012X' % mac_num)[i:i+2] for i in range(0, 12, 2))
    return mac


class Settings:
    # ─── RPi Identity (chỉ MAC address) ───
    MAC_ADDRESS = os.getenv("MAC_ADDRESS") or _get_mac_address()

    # ─── MQTT connection ───
    MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
    MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
    MQTT_PORT_SSL = int(os.getenv("MQTT_PORT_SSL", 8883))
    MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
    MQTT_KEEPALIVE = int(os.getenv("MQTT_KEEPALIVE", 60))
    MQTT_RECONNECT_INTERVAL = int(os.getenv("MQTT_RECONNECT_INTERVAL", 5))
    MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "true").lower() == "true"

    # ─── Serial / Arduino ───
    SERIAL_PORT = os.getenv("SERIAL_PORT", "AUTO")
    SERIAL_BAUD_RATE = int(os.getenv("SERIAL_BAUD_RATE", 9600))

    # ─── Hardware ───
    TOTAL_SLOTS = int(os.getenv("TOTAL_SLOTS", 24))
    MAX_CABINETS = 1
    SERVO_OPEN_ANGLE = int(os.getenv("SERVO_OPEN_ANGLE", 90))
    SERVO_CLOSE_ANGLE = int(os.getenv("SERVO_CLOSE_ANGLE", 0))
    SENSOR_DEBOUNCE_MS = int(os.getenv("SENSOR_DEBOUNCE_MS", 200))

    # ─── Network / Backend ───
    BACKEND_API_URL = os.getenv("BACKEND_API_URL", "")
    BACKEND_HEALTH_URL = os.getenv("BACKEND_HEALTH_URL", "")
    
    # ─── Firmware ───
    FIRMWARE_VERSION = os.getenv("FIRMWARE_VERSION", "v1.0.0")

    # ─── Database (PostgreSQL) ───
    # DATABASE_PATH chỉ là tham số legacy (SQLite) — DatabaseManager hiện bỏ qua và dùng POSTGRES_*
    DATABASE_PATH = os.getenv("DATABASE_PATH", "locker.db")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "iot_locker")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

    def update_mqtt_config(self, db_config: dict):
        """Cập nhật cấu hình MQTT từ database (ghi đè env)."""
        if not db_config:
            return
        
        self.MQTT_BROKER = db_config.get("broker", self.MQTT_BROKER)
        self.MQTT_PORT_SSL = db_config.get("port", self.MQTT_PORT_SSL) # Mặc định IoT dùng SSL port
        self.MQTT_USERNAME = db_config.get("username", self.MQTT_USERNAME)
        self.MQTT_PASSWORD = db_config.get("password", self.MQTT_PASSWORD)
        self.MQTT_USE_TLS = db_config.get("useTls", self.MQTT_USE_TLS)
        
        logger.info(f"Settings updated from DB: broker={self.MQTT_BROKER}")

    def update_system_config(self, db_manager):
        """Cập nhật các cấu hình hệ thống từ database."""
        max_cabs = db_manager.get_system_setting("max_cabinets")
        if max_cabs is not None:
            try:
                self.MAX_CABINETS = int(max_cabs)
                logger.info(f"Settings updated from DB: MAX_CABINETS={self.MAX_CABINETS}")
            except ValueError:
                logger.error(f"Invalid value for max_cabinets in DB: {max_cabs}")


settings = Settings()
