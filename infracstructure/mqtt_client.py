import ssl
import paho.mqtt.client as mqtt
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("MQTT_Client")


class MQTTClientWrapper:
    def __init__(self, on_message_callback=None):
        self.callback = on_message_callback
        self._connected = False
        self.client = None
        self.re_init()

    def re_init(self):
        """Khởi tạo hoặc cập nhật cấu hình client (ví dụ khi host/user thay đổi)."""
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except:
                pass
                
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # ─── MQTT Authentication ───
        if settings.MQTT_USERNAME:
            self.client.username_pw_set(
                settings.MQTT_USERNAME,
                settings.MQTT_PASSWORD
            )
            logger.info(f"MQTT auth configured for user: {settings.MQTT_USERNAME}")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            self._connected = True
            logger.warning(f"🌐 MQTT Connected to Broker: {settings.MQTT_BROKER}")
            # ─── Subscribe setup command ───
            mac = settings.MAC_ADDRESS
            setup_topic = f"iot/{mac}/command/setup"
            client.subscribe(setup_topic, qos=1)
            logger.info(f"Subscribed: {setup_topic}")

            # ─── Subscribe clear-setup command ───
            clear_setup_topic = f"iot/{mac}/command/clear-setup"
            client.subscribe(clear_setup_topic, qos=1)
            logger.info(f"Subscribed: {clear_setup_topic}")

            # ─── Subscribe discovery start command ───
            discovery_start_topic = f"iot/{mac}/discovery/start"
            client.subscribe(discovery_start_topic, qos=1)
            logger.info(f"Subscribed: {discovery_start_topic}")

            logger.info(f"⏳ Waiting for setup command (MAC: {mac})...")
        else:
            logger.error(f"Connection failed, reason code: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._connected = False
        if reason_code != 0:
            logger.warning(f"Unexpected disconnection (rc={reason_code}). Will auto-reconnect...")
        else:
            logger.info("Disconnected from broker")

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode()
            logger.info(f"📩 Received on [{msg.topic}]: {payload_str}")
            if self.callback:
                self.callback(msg.topic, payload_str)
        except Exception as e:
            logger.error(f"Error handling message on {msg.topic}: {e}", exc_info=True)

    def subscribe(self, topic: str, qos: int = 1):
        self.client.subscribe(topic, qos=qos)
        logger.info(f"Subscribed (dynamic): {topic}")

    def unsubscribe(self, topic: str):
        self.client.unsubscribe(topic)
        logger.info(f"Unsubscribed: {topic}")

    def subscribe_locker_commands(self, cabinet_name: str):
        open_topic = f"cabinet/{cabinet_name}/command/open"
        close_topic = f"cabinet/{cabinet_name}/command/close"
        self.client.subscribe([(open_topic, 1), (close_topic, 1)])
        logger.info(f"Subscribed locker commands: {open_topic}, {close_topic}")

    def subscribe_open_command(self, cabinet_name: str):
        # Keep for backward compatibility or individual use
        topic = f"cabinet/{cabinet_name}/command/open"
        self.client.subscribe(topic, qos=1)
        logger.info(f"Subscribed open command: {topic}")

    def subscribe_close_command(self, cabinet_name: str):
        topic = f"cabinet/{cabinet_name}/command/close"
        self.client.subscribe(topic, qos=1)
        logger.info(f"Subscribed close command: {topic}")

    def publish(self, topic: str, payload: str, qos: int = 1):
        result = self.client.publish(topic, payload, qos=qos)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"📤 Published to [{topic}]: {payload}")
        else:
            logger.error(f"Publish failed to {topic}, rc={result.rc}")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def start(self):
        """Kết nối tới broker (ưu tiên MQTTS) và start background loop."""
        # --- 1. Thử kết nối MQTTS (Port 8883) ---
        try:
            logger.info(f"Attempting MQTTS connection to {settings.MQTT_BROKER}:{settings.MQTT_PORT_SSL}...")
            # HiveMQ Cloud requires TLS 1.2+
            self.client.tls_set(tls_version=ssl.PROTOCOL_TLSv1_2)
            self.client.tls_insecure_set(False)
            
            self.client.connect(
                settings.MQTT_BROKER,
                settings.MQTT_PORT_SSL,
                keepalive=settings.MQTT_KEEPALIVE
            )
            self.client.loop_start()
            logger.info("MQTTS connection initiated successfully")
            return
        except Exception as e:
            logger.warning(f"MQTTS connection failed: {e}. Falling back to plain MQTT...")

        # --- 2. Thử kết nối MQTT (Port 1883) ---
        try:
            # Reset client để xóa cấu hình TLS
            self.re_init()
            logger.info(f"Attempting MQTT connection to {settings.MQTT_BROKER}:{settings.MQTT_PORT}...")
            self.client.connect(
                settings.MQTT_BROKER,
                settings.MQTT_PORT,
                keepalive=settings.MQTT_KEEPALIVE
            )
            self.client.loop_start()
            logger.info("MQTT connection (plain) initiated successfully")
        except Exception as e:
            logger.error(f"All MQTT connection attempts failed: {e}")

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT client stopped")
        except Exception as e:
            logger.error(f"Error stopping MQTT client: {e}")
