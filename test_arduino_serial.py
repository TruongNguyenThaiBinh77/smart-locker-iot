"""
Script test giao tiếp RS485 với Arduino.

Gửi ký tự 'H' (bật LED pin 13 + buzzer pin 7) hoặc 'L' (tắt LED)
qua RS485 serial và đợi phản hồi "OK: " từ Arduino.

Dùng code Arduino (SoftwareSerial trên pin 10/9, TxControl pin 3):
  - Nhận 'H' (ASCII 72) → digitalWrite(13, HIGH), buzzer pin 7
  - Nhận 'L' (ASCII 76) → digitalWrite(13, LOW)
  - Gửi lại "OK: " qua RS485

Usage:
    python test_arduino_serial.py
    
Sau đó nhấn H hoặc L rồi Enter.
Nhấn Q để thoát.
"""

import sys
import time
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("ArduinoTest")

try:
    import serial
except ImportError:
    print("❌ Cần cài pyserial: pip install pyserial")
    sys.exit(1)


def open_serial(port: str, baud: int) -> serial.Serial:
    """Mở kết nối serial tới Arduino qua RS485 adapter."""
    logger.info(f"Đang kết nối tới {port} @ {baud} baud...")
    ser = serial.Serial(port, baud, timeout=2)
    # Arduino reset khi mở serial → chờ ổn định
    time.sleep(2)
    ser.reset_input_buffer()
    logger.info(f"✅ Kết nối thành công: {port}")
    return ser


def send_command(ser: serial.Serial, cmd: str) -> str | None:
    """
    Gửi 1 ký tự (H hoặc L) xuống Arduino qua RS485.
    Chờ phản hồi trong 3 giây.
    """
    # Flush buffer cũ
    ser.reset_input_buffer()

    # Gửi ký tự
    ser.write(cmd.encode())
    ser.flush()
    logger.info(f"📤 TX: '{cmd}' (ASCII {ord(cmd)})")

    # Chờ phản hồi từ Arduino
    start = time.time()
    timeout = 3  # seconds
    response_lines = []

    while time.time() - start < timeout:
        if ser.in_waiting > 0:
            line = ser.readline().decode(errors="replace").strip()
            if line:
                response_lines.append(line)
                logger.info(f"📥 RX: {line}")
        time.sleep(0.05)

    if response_lines:
        return "\n".join(response_lines)
    else:
        logger.warning("⏰ Không nhận được phản hồi (timeout 3s)")
        return None


def main():
    port = settings.SERIAL_PORT
    baud = settings.SERIAL_BAUD_RATE

    print("=" * 50)
    print("  🔧 Arduino RS485 Test Tool")
    print("=" * 50)
    print(f"  Serial Port : {port}")
    print(f"  Baud Rate   : {baud}")
    print("=" * 50)
    print()
    print("  Lệnh khả dụng:")
    print("    H  → Gửi 'H' (bật LED pin 13 + buzzer pin 7)")
    print("    L  → Gửi 'L' (tắt LED pin 13)")
    print("    Q  → Thoát")
    print()

    try:
        ser = open_serial(port, baud)
    except Exception as e:
        logger.error(f"❌ Không thể kết nối serial: {e}")
        print(f"\n💡 Kiểm tra lại:")
        print(f"   - Cổng serial đúng chưa? (hiện tại: {port})")
        print(f"   - Arduino đã cắm USB chưa?")
        print(f"   - Driver RS485 adapter đã cài chưa?")
        sys.exit(1)

    try:
        while True:
            user_input = input("\n🎮 Nhập lệnh (H / L / Q): ").strip().upper()

            if user_input == "Q":
                print("👋 Thoát...")
                break

            if user_input in ("H", "L"):
                action = "BẬT LED + BUZZER" if user_input == "H" else "TẮT LED"
                print(f"   → Gửi '{user_input}' ({action})...")
                response = send_command(ser, user_input)

                if response:
                    print(f"   ✅ Arduino phản hồi: {response}")
                else:
                    print(f"   ⚠️  Không có phản hồi. Kiểm tra:")
                    print(f"       - Arduino đã nạp code RS485 chưa?")
                    print(f"       - Dây A/B RS485 đã nối đúng chưa?")
                    print(f"       - SSerialTxControl (pin 3) hoạt động không?")
            else:
                print(f"   ❓ Lệnh không hợp lệ: '{user_input}'. Dùng H, L, hoặc Q.")

    except KeyboardInterrupt:
        print("\n👋 Ctrl+C – Thoát...")
    finally:
        ser.close()
        logger.info("Serial connection closed.")
        print("🔌 Đã đóng kết nối serial.")


if __name__ == "__main__":
    main()
