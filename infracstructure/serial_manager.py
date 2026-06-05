import json
import time
import threading
from typing import Optional, Callable
from utils.logger import get_logger

logger = get_logger("SerialManager")

# Kiểm tra pyserial có sẵn không
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    logger.error("pyserial not available! Real hardware communication will not work.")

# Số slot tối đa (Arduino Uno: 6 lock + 6 magnetic)
MAX_SLOTS = 6


class SerialManager:
    """
    Quản lý giao tiếp RS485 với Arduino.

    Protocol (RPi → Arduino):
        T<slot>\n   – Test slot (toggle GPIO HIGH→LOW, đo thời gian + đọc sensor)
        O<slot>\n   – Open slot (set GPIO HIGH)
        C<slot>\n   – Close slot (set GPIO LOW)

    Protocol (Arduino → RPi):
        Command response:
          {"slot":0,"result":"OK","gpio":7,"door":true,"ms":450}\n
        Push event:
          {"event":"DOOR_CLOSED","slot":0}\n
    """

    def __init__(self, port: str, baud_rate: int, simulation: bool = False,
                 on_door_event: Optional[Callable] = None):
        self.port = port
        self.baud_rate = baud_rate
        self.simulation = simulation
        if not SERIAL_AVAILABLE and not self.simulation:
            raise ImportError("pyserial is not installed, cannot connect to real hardware.")
        self._ser: Optional[object] = None
        self._on_door_event = on_door_event

        # Background listener
        self._listener_thread: Optional[threading.Thread] = None
        self._listener_running = False

        # Response queue (command response từ Arduino)
        self._response_event = threading.Event()
        self._response_data: Optional[dict] = None
        self._response_lock = threading.Lock()
        
        self._buffer = ""
        self._waiting_for_slave: Optional[int] = None
        
        # Reconnect logic
        self._reconnect_attempts = 0
        self._max_reconnect_delay = 60
        self._on_reconnect: Optional[Callable] = None

        if self.simulation:
            logger.info("SerialManager running in SIMULATION mode")
        else:
            self._connect()

    @property
    def on_reconnect(self) -> Optional[Callable]:
        return self._on_reconnect

    @on_reconnect.setter
    def on_reconnect(self, callback: Callable):
        self._on_reconnect = callback

    @property
    def on_door_event(self) -> Optional[Callable]:
        return self._on_door_event

    @on_door_event.setter
    def on_door_event(self, callback: Callable):
        self._on_door_event = callback

    @staticmethod
    def find_arduino_port() -> Optional[str]:
        """Tự động tìm cổng serial khớp với Arduino/RS485 adapter."""
        if not SERIAL_AVAILABLE:
            return None
            
        try:
            ports = list(serial.tools.list_ports.comports())
            if not ports:
                logger.warning("No serial ports found on the system.")
                return None

            # 1. Thử tìm theo Hardware ID hoặc Description (CH340, FTDI, Arduino)
            # RS485 adapters thường dùng CH340 hoặc CP210x
            keywords = ["arduino", "ch34x", "ch340", "cp210", "ft232", "usb-serial", "usb serial"]
            for p in ports:
                desc = (p.description or "").lower()
                hwid = (p.hwid or "").lower()
                if any(k in desc for k in keywords) or any(k in hwid for k in keywords):
                    logger.info(f"Auto-detected port by keyword '{p.description}': {p.device}")
                    return p.device
            
            # 2. Nếu không tìm thấy, lấy cổng ttyUSB hoặc ttyACM đầu tiên (Linux/RPi)
            # Đây là trường hợp phổ biến khi driver không hiện tên chip
            for p in ports:
                if "ttyusb" in p.device.lower() or "ttyacm" in p.device.lower():
                    logger.info(f"Auto-detected port by device name: {p.device}")
                    return p.device
                    
            # 3. Cuối cùng, lấy cổng đầu tiên bất kỳ nếu có
            if ports:
                logger.warning(f"No specific Arduino found, picking first available: {ports[0].device}")
                return ports[0].device
        except Exception as e:
            logger.error(f"Error during auto-detecting serial port: {e}")
            
        return None

    def _connect(self):
        """Mở kết nối serial (RS485 qua USB adapter)."""
        current_port = self.port
        
        # Nếu port không tồn tại hoặc là "AUTO", thử tìm tự động
        if not current_port or current_port.upper() == "AUTO" or not self._is_port_valid(current_port):
            logger.info("Serial port not specified or invalid, attempting auto-detection...")
            detected_port = self.find_arduino_port()
            if detected_port:
                current_port = detected_port
                self.port = detected_port # Cập nhật lại port chính thức
            else:
                logger.error("Auto-detection failed. No serial ports available.")
                if not self.port:
                    raise serial.SerialException("No serial port specified and auto-detection failed.")

        try:
            self._ser = serial.Serial(
                current_port,
                self.baud_rate,
                timeout=1  # 1s timeout cho readline
            )
            # Arduino reset khi mở serial, chờ stable
            time.sleep(2)
            # Flush buffer cũ
            self._ser.reset_input_buffer()
            logger.info(f"RS485 connected: {current_port} @ {self.baud_rate}")

            # Start background listener
            self._start_listener()

        except Exception as e:
            logger.error(f"RS485 connection failed on {current_port}: {e}")
            
            # Nếu kết nối thất bại và chưa dùng auto-detect, thử tìm lại
            if current_port == self.port and self.port.upper() != "AUTO":
                 logger.info("Retrying connection with auto-detected port...")
                 detected_port = self.find_arduino_port()
                 if detected_port and detected_port != current_port:
                     self.port = detected_port
                     return self._connect()
            
            raise e

    def _is_port_valid(self, port_path: str) -> bool:
        """Kiểm tra xem tập tin thiết bị có tồn tại hay không."""
        import os
        return os.path.exists(port_path)

    # ═══════════════════════════════════════════════
    #  BACKGROUND LISTENER
    # ═══════════════════════════════════════════════

    def _start_listener(self):
        """Khởi động thread đọc RS485 liên tục."""
        self._listener_running = True
        self._listener_thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
            name="RS485Listener"
        )
        self._listener_thread.start()
        logger.info(f"RS485 background listener started on {self.port}")

    def _stop_listener(self):
        """Dừng background listener."""
        self._listener_running = False
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=3)
            logger.info("RS485 background listener stopped")

    def _listener_loop(self):
        """Loop đọc liên tục từ RS485 – Phiên bản Extreme Transparency."""
        logger.info(f"SERIAL LISTENER: Loop started on {self.port}")
        poll_count = 0
        
        while self._listener_running:
            try:
                if self._ser and self._ser.is_open:
                    waiting = self._ser.in_waiting
                    poll_count += 1
                    if poll_count >= 100:
                        # logger.info(f"Listener Loop Heartbeat: in_waiting={waiting}, buffer_len={len(self._buffer)}")
                        poll_count = 0
                    
                    if waiting > 0:
                        # Reset poll count khi có data
                        poll_count = 0
                        # 1. Đọc byte
                        chunk = self._ser.read(waiting).decode(errors="ignore")
                        self._buffer += chunk
                        
                        # 2. Xử lý lines
                        if "\n" in self._buffer:
                            lines = self._buffer.split("\n")
                            self._buffer = lines.pop(-1)
                            
                            for line in lines:
                                line = line.strip().replace('\x00', '')
                                if not line: continue
                                logger.info(f"RS485 IN: '{line}'")
                                start_idx = line.find("{")
                                if start_idx >= 0:
                                    self._handle_incoming_json(line[start_idx:])
                                else:
                                    if line != "=====":
                                        logger.debug(f"Non-JSON line from Arduino: {line}")
                    else:
                        poll_count += 1
                        # Cứ ~2 giây log 1 lần cho đỡ rác ở debug level
                        if poll_count >= 200: 
                            logger.debug(f"SERIAL LISTENER: Polling {self.port}... (Buffer size: {len(self._buffer)})")
                            poll_count = 0
                    
                    time.sleep(0.01)
                else:
                    # Port is closed but listener is running? Try to connect
                    logger.warning("SERIAL LISTENER: Port is closed, attempting recovery...")
                    self._attempt_reconnect()
                    
            except (OSError, serial.SerialException) as e:
                logger.error(f"SERIAL LISTENER FATAL ERROR: {e}")
                self._handle_fatal_error()
            except Exception as e:
                logger.error(f"SERIAL LISTENER UNKNOWN EXCEPTION: {e}")
                time.sleep(2)

    def _handle_fatal_error(self):
        """Xử lý khi gặp lỗi I/O hoặc SerialException (mất kết nối vật lý)."""
        logger.info("Initiating serial port recovery...")
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except:
            pass
        self._ser = None
        self._attempt_reconnect()

    def _attempt_reconnect(self):
        """Thử kết nối lại với độ trễ tăng dần."""
        delay = min(2 ** self._reconnect_attempts, self._max_reconnect_delay)
        logger.info(f"Waiting {delay}s before reconnecting to {self.port}...")
        time.sleep(delay)
        
        try:
            # Mở lại port (không gọi self._start_listener vì loop đang chạy)
            self._ser = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=1
            )
            time.sleep(2) # Arduino reset
            self._ser.reset_input_buffer()
            logger.warning(f"✅ SERIAL RECONNECTED on {self.port}!")
            self._reconnect_attempts = 0
            
            # Notify on_reconnect
            if self._on_reconnect:
                threading.Thread(target=self._on_reconnect, daemon=True).start()
                
        except Exception as e:
            self._reconnect_attempts += 1
            logger.error(f"Reconnect failed (attempt {self._reconnect_attempts}): {e}")

    # ─── DISCOVERY ───

    def scan_slaves(self, range_start: int = 1, range_end: int = 1) -> list:
        """
        Quét bus RS485 để tìm các Slave Arduino hoạt động.
        Trả về list: [{"slaveId": N, "availableSlots": 6}, ...]
        """
        if self.simulation:
            return [
                {"slaveId": 1, "availableSlots": 6}
            ]
        
        found = []
        for sid in range(range_start, range_end + 1):
            logger.info(f"Scanning RS485 for Slave ID {sid} (Wait up to 10s)...")
            # Gửi lệnh PING tới từng slave - Tăng timeout lên 10s theo yêu cầu chờ lâu hơn
            res = self._send_and_wait(f"S{sid}:PING\n", -1, timeout=10, custom_slave_id=sid)
            
            res_slave = res.get("slave", -1)
            result_val = res.get("result")
            
            logger.debug(f"Scan SID {sid} got response: {res}")

            if result_val == "OK" and (res_slave == sid or res_slave == -1):
                # Lấy số slot từ Arduino phản hồi, nếu không có thì dùng mặc định
                slots_count = res.get("slots", MAX_SLOTS)
                found.append({
                    "slaveId": sid,
                    "availableSlots": slots_count
                })
                logger.info(f"Found Slave ID {sid} with {slots_count} slots ✅")
            else:
                if result_val == "FAIL" and res.get("error") == "TIMEOUT":
                    logger.warning(f"Slave ID {sid} did not respond (Timeout)")
                else:
                    logger.warning(f"Slave ID {sid} rejected: result={result_val}, res_slave={res_slave}")
        
        logger.info(f"Scan complete. Found {len(found)} slaves: {found}")
        return found

    def _handle_incoming_json(self, line: str):
        """Phân loại JSON message từ Arduino."""
        try:
            data = json.loads(line)
            logger.info(f"RS485 JSON parsed successfully: {data}")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON segment: '{line}' | Error: {e}")
            return

        slave_id = data.get("slave", 1) # Mặc định 1 nếu không có

        # Push event (DOOR_CLOSED / DOOR_OPENED)
        if "event" in data:
            event = data.get("event")
            slot = data.get("slot", -1)
            logger.info(f"RS485 EVENT: slave={slave_id} {event} slot={slot}")

            if event in ("DOOR_CLOSED", "DOOR_OPENED") and self._on_door_event:
                try:
                    # Truyền thêm slave_id vào callback
                    self._on_door_event(slot, event, slave_id=slave_id)
                except Exception as e:
                    logger.error(f"Door event callback error: {e}")
            
            # Nếu là ALIVE, coi như đây cũng là 1 response hợp lệ cho PING (Proof of life)
            if event == "ALIVE":
                if self._waiting_for_slave is not None and slave_id == self._waiting_for_slave:
                    with self._response_lock:
                        # Giả lập 1 response OK từ slave này, kèm theo số slot nếu có
                        self._response_data = {
                            "slave": slave_id, 
                            "result": "OK", 
                            "slots": data.get("slots", MAX_SLOTS),
                            "event_confirm": "ALIVE"
                        }
                        self._response_event.set()
            return

        # Command response (slot + result)
        if "result" in data:
            slot = data.get("slot")
            result = data.get("result")
            logger.info(f"RS485 RESPONSE: slave {slave_id} slot {slot} -> {result}")
            if self._waiting_for_slave is not None and slave_id == self._waiting_for_slave:
                with self._response_lock:
                    self._response_data = data
                    self._response_event.set()
            return

        logger.warning(f"Unknown Arduino message: {data}")

    # ═══════════════════════════════════════════════
    #  COMMAND METHODS
    # ═══════════════════════════════════════════════

    def is_connected(self) -> bool:
        """Kiểm tra kết nối serial."""
        if self.simulation:
            return True
        return self._ser is not None and self._ser.is_open

    def test_slot(self, slot_index: int, slave_id: int = 1, timeout: int = 10) -> dict:
        """Gửi lệnh EXAMINE (Test) slot tới Arduino slave."""
        if self.simulation:
            return self._simulate_test_slot(slot_index, slave_id)
        return self._send_and_wait(f"\nS{slave_id}:T{slot_index}\n", slot_index, timeout, custom_slave_id=slave_id)

    def open_slot(self, slot_index: int, slave_id: int = 1, timeout: int = 5) -> dict:
        """Gửi lệnh ACTIVATE (Open) slot tới Arduino slave."""
        if self.simulation:
            return self._simulate_open_slot(slot_index, slave_id)
        return self._send_and_wait(f"\nS{slave_id}:O{slot_index}\n", slot_index, timeout, custom_slave_id=slave_id)

    def close_slot(self, slot_index: int, slave_id: int = 1, timeout: int = 5) -> dict:
        """Gửi lệnh BLOCK (Close) slot tới Arduino slave."""
        if self.simulation:
            return self._simulate_close_slot(slot_index, slave_id)
        return self._send_and_wait(f"\nS{slave_id}:C{slot_index}\n", slot_index, timeout, custom_slave_id=slave_id)

    def _send_and_wait(self, command: str, slot_index: int, timeout: int, custom_slave_id: int = 1) -> dict:
        """Gửi command qua RS485 và chờ response từ background listener."""
        try:
            # Clear previous response
            with self._response_lock:
                self._response_data = None
                self._response_event.clear()
                self._waiting_for_slave = custom_slave_id

            # KHÔNG reset input buffer ở đây vì background listener đang đọc liên tục.
            # reset_input_buffer() sẽ xóa mất data mà listener chưa kịp lấy.
            
            try:
                # Chờ 150ms để bus RS485 hoàn toàn trống từ Slave trước đó
                time.sleep(0.15)

                # Gửi command
                # Thêm \n vào đầu để reset buffer của Arduino nếu đang kẹt
                if self._ser:
                    # Flush serial buffer before sending to ensure we don't read old data
                    # self._ser.reset_input_buffer() # Tránh dùng vì listener đang chạy
                    
                    full_cmd = f"\n{command}"
                    self._ser.write(full_cmd.encode())
                    self._ser.flush()
                    logger.info(f"RS485 TX: {command.strip()} (Full: {full_cmd.replace('\n', '\\n')})")
                # Chờ response
                if self._response_event.wait(timeout=timeout + 1):
                    with self._response_lock:
                        response = self._response_data
                        self._response_data = None
                    return response if response else self._timeout_response(slot_index, timeout, custom_slave_id)
                else:
                    return self._timeout_response(slot_index, timeout, custom_slave_id)
            finally:
                self._waiting_for_slave = None
                time.sleep(0.1)

        except Exception as e:
            logger.error(f"RS485 error for slot {slot_index}: {e}")
            return {
                "slave": custom_slave_id,
                "slot": slot_index,
                "result": "FAIL",
                "error": "SERIAL_ERROR"
            }

    def _timeout_response(self, slot_index: int, timeout: int, slave_id: int) -> dict:
        """Response khi timeout."""
        logger.warning(f"Slave {slave_id} Slot {slot_index} timeout after {timeout}s")
        return {
            "slave": slave_id,
            "slot": slot_index,
            "result": "FAIL",
            "error": "TIMEOUT"
        }

    def close(self):
        """Đóng kết nối serial."""
        self._stop_listener()
        if self._ser and not self.simulation:
            try:
                self._ser.close()
                logger.info("RS485 connection closed")
            except Exception as e:
                logger.error(f"Error closing serial: {e}")

    # ═══════════════════════════════════════════════
    #  SIMULATION
    # ═══════════════════════════════════════════════

    def _simulate_test_slot(self, slot_index: int, slave_id: int) -> dict:
        time.sleep(0.2)
        return {"slave": slave_id, "slot": slot_index, "result": "OK", "door": True}

    def _simulate_open_slot(self, slot_index: int, slave_id: int) -> dict:
        time.sleep(0.2)
        return {"slave": slave_id, "slot": slot_index, "result": "OK", "door": False}

    def _simulate_close_slot(self, slot_index: int, slave_id: int) -> dict:
        time.sleep(0.2)
        return {"slave": slave_id, "slot": slot_index, "result": "OK", "door": True}
