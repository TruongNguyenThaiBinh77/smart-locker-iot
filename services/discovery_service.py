import json
import time
from datetime import datetime, timezone
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("DiscoveryService")

class DiscoveryService:
    """
    Dịch vụ khám phá Arduino Slaves trên bus RS485.
    Báo cáo kết quả về Backend qua MQTT.
    """

    def __init__(self, mqtt_client, serial_manager):
        self.mqtt = mqtt_client
        self.serial = serial_manager

    def discover_and_report(self, max_cabinets: int = None):
        """
        Thực hiện quét slaveId và gửi kết quả về backend.
        Topic: iot/{macAddress}/discovery/result
        """
        mac = settings.MAC_ADDRESS
        logger.info(f"Starting discovery for RPi: {mac} (max_cabinets={max_cabinets})")

        # 1. Quét phần cứng (Theo dải config từ settings hoặc dynamic từ BE)
        range_end = max_cabinets if max_cabinets is not None else settings.MAX_CABINETS
        slaves = self.serial.scan_slaves(range_start=1, range_end=range_end)
        
        # 2. Build payload
        payload = {
            "macAddress": mac,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "slaves": slaves, # List of {"slaveId": N, "availableSlots": M}
            "firmwareVersion": settings.FIRMWARE_VERSION
        }

        # 3. Publish MQTT
        topic = f"iot/{mac}/discovery/result"
        self.mqtt.publish(topic, json.dumps(payload), qos=1)
        logger.info(f"Discovery results reported to {topic}")
        return slaves
