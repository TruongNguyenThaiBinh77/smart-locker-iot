import time
import signal
import sys
import threading
from config.settings import settings
from infracstructure.mqtt_client import MQTTClientWrapper
from infracstructure.serial_manager import SerialManager
from infracstructure.cabinet_state import CabinetState
from hardware.rpi_locker import HardwareController
from infracstructure.database import DatabaseManager
from services.locker_service import LockerService
from services.heartbeat_service import HeartbeatService
from services.discovery_service import DiscoveryService
from utils.logger import get_logger

logger = get_logger("Main")

# ─── Graceful shutdown ───
_running = True


def _signal_handler(sig, frame):
    global _running
    logger.info(f"Received signal {sig}, shutting down...")
    _running = False


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def main():
    import logging
    from utils.logger import set_global_log_level
    # Default level is INFO for startup, we'll quiet it down later
    set_global_log_level(logging.INFO)

    logger.info("=" * 60)
    logger.info("  AISL Smart Locker System – Starting...")
    logger.info("=" * 60)
    logger.info(f"  MAC Address : {settings.MAC_ADDRESS}")
    logger.info(f"  Firmware    : {settings.FIRMWARE_VERSION}")
    logger.info("=" * 60)


    logger.info(f"   MQTT Broker : {settings.MQTT_BROKER}:{settings.MQTT_PORT_SSL}")
    logger.info(f"   Serial Port : {settings.SERIAL_PORT}")

    # 2. Khởi tạo tầng Hardware (GPIO simulation)
    hw_controller = HardwareController()
    logger.info("[2/7] Hardware controller initialized")

    # 3. Khởi tạo Serial Manager (Arduino communication)
    serial_manager = SerialManager(
        port=settings.SERIAL_PORT,
        baud_rate=settings.SERIAL_BAUD_RATE,
        simulation=False
    )
    logger.info("[3/7] Serial manager initialized")

    # 4. Khởi tạo Database Manager
    db_manager = DatabaseManager(settings.DATABASE_PATH)
    logger.info(f"[4/7] Database manager ready")

    # 4.1 Cập nhật settings từ DB (nếu có)
    settings.update_system_config(db_manager)
    mqtt_db_config = db_manager.get_mqtt_config()
    if mqtt_db_config:
        settings.update_mqtt_config(mqtt_db_config)
        logger.info("[4.1/7] MQTT settings overridden from Database")

    # 5. Khởi tạo Cabinet State
    cabinet_state = CabinetState(db_manager=db_manager)
    if cabinet_state.is_configured:
        loc = cabinet_state.location
        cabs = cabinet_state.all_cabinets
        logger.info(f"[5/7] Cabinet state loaded: Location={loc.get('name')}, Cabinets={len(cabs)}")
        for i, c in enumerate(cabs):
            logger.info(f"   {i+1}. {c['name']} (slaveId={c['slaveId']})")
    else:
        logger.info("[5/7] System state: NOT CONFIGURED")

    # 4.2 Chạy Config API server (Local)
    from infracstructure.config_api import start_config_api
    start_config_api(db_manager, cabinet_state, port=8000)
    logger.info("[4.2/7] Local Config API started on port 8000")

    # 6. Khởi tạo MQTT Client & Heartbeat (chưa connect)
    mqtt_wrapper = MQTTClientWrapper(on_message_callback=None)
    
    heartbeat_service = HeartbeatService(
        mqtt_client=mqtt_wrapper,
        cabinet_state=cabinet_state,
        interval=cabinet_state.heartbeat_interval if cabinet_state.is_configured else 60,
    )

    # 8. Khởi tạo Discovery Service
    discovery_service = DiscoveryService(mqtt_wrapper, serial_manager)
    logger.info("[6/7] Components initialized (Heartbeat, MQTT Client, Discovery)")

    # 7. Khởi tạo Locker Service
    locker_service = LockerService(
        mqtt_client=mqtt_wrapper,
        hardware_controller=hw_controller,
        serial_manager=serial_manager,
        cabinet_state=cabinet_state,
        heartbeat_service=heartbeat_service,
        db_manager=db_manager,
        discovery_service=discovery_service,
    )
    logger.info("[7/7] Services ready (Locker, Heartbeat, Discovery)")

    serial_manager.on_door_event = locker_service.handle_door_event
    serial_manager.on_reconnect = discovery_service.discover_and_report
    mqtt_wrapper.callback = locker_service.handle_incoming_message

    # Start services at INFO level
    logger.info("System initializing...")

    # 8. Kết nối MQTT & start
    mqtt_wrapper.start()
    time.sleep(1)

    # Thực hiện discovery ngay khi start để báo cáo cho BE
    discovery_service.discover_and_report()

    if cabinet_state.is_configured:
        for cab in cabinet_state.all_cabinets:
            mqtt_wrapper.subscribe_locker_commands(cab["name"])
        heartbeat_service.start()
    
    logger.warning("✅ System is READY (Logged at WARNING level)")

    # Giữ chương trình chạy
    try:
        while _running:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        heartbeat_service.stop()
        serial_manager.close()
        mqtt_wrapper.stop()
        logger.info("Goodbye!")


if __name__ == "__main__":
    main()
