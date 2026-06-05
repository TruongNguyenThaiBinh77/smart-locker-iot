"""
Debug script v2: Test RS485 RX trên Pi.
Kiểm tra cả RTS control và raw byte monitoring.

Chạy trên Pi:  python3 debug_rs485_rx.py
"""
import serial
import time
import sys

# ─── CẤU HÌNH ───
PORT = "/dev/ttyUSB0"    # Đổi lại nếu port khác
BAUD = 9600
SLAVE_ID = 2

def test_ping(ser, label: str):
    """Gửi PING và đọc response."""
    ser.reset_input_buffer()
    time.sleep(0.1)
    
    cmd = f"\nS{SLAVE_ID}:PING\n".encode()
    print(f"  📤 TX: {cmd}")
    ser.write(cmd)
    ser.flush()
    
    # Đọc liên tục 5 giây
    start = time.time()
    response_bytes = b""
    while time.time() - start < 5:
        if ser.in_waiting > 0:
            chunk = ser.read(ser.in_waiting)
            response_bytes += chunk
            elapsed = time.time() - start
            print(f"  📥 [{elapsed:.3f}s] Raw hex: {chunk.hex()}")
            print(f"  📥 [{elapsed:.3f}s] Text: {chunk.decode(errors='replace')}")
        time.sleep(0.01)
    
    if response_bytes:
        print(f"  ✅ [{label}] Nhận được {len(response_bytes)} bytes!")
    else:
        print(f"  ❌ [{label}] KHÔNG nhận được byte nào!")
    return len(response_bytes) > 0


def main():
    print(f"=== RS485 RX Debug Tool v2 ===")
    print(f"Port: {PORT}, Baud: {BAUD}")
    
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.1)
    except Exception as e:
        print(f"❌ Không mở được port {PORT}: {e}")
        sys.exit(1)
    
    # In thông tin adapter
    print(f"  Port name: {ser.name}")
    print(f"  RTS state: {ser.rts}")
    print(f"  DTR state: {ser.dtr}")
    
    time.sleep(0.5)
    ser.reset_input_buffer()
    
    # ═══════════════════════════════════════════════
    # TEST 1: Gửi PING với cấu hình mặc định
    # ═══════════════════════════════════════════════
    print(f"\n[TEST 1] PING với cấu hình mặc định (RTS={ser.rts})...")
    result1 = test_ping(ser, "default")
    
    # ═══════════════════════════════════════════════
    # TEST 2: Set RTS=False (ép adapter về RX mode) rồi PING
    # ═══════════════════════════════════════════════
    print(f"\n[TEST 2] Set RTS=False (ép RX mode) rồi PING...")
    ser.rts = False
    time.sleep(0.1)
    print(f"  RTS đã set: {ser.rts}")
    result2 = test_ping(ser, "RTS=False")
    
    # ═══════════════════════════════════════════════
    # TEST 3: Set RTS=True trước khi gửi, rồi False ngay sau
    # ═══════════════════════════════════════════════
    print(f"\n[TEST 3] RTS=True (TX) → write → RTS=False (RX)...")
    ser.reset_input_buffer()
    ser.rts = True
    time.sleep(0.01)
    
    cmd = f"\nS{SLAVE_ID}:PING\n".encode()
    print(f"  📤 TX: {cmd}")
    ser.write(cmd)
    ser.flush()
    time.sleep(0.01)  # Chờ byte cuối ra khỏi adapter
    ser.rts = False    # Chuyển về RX
    print(f"  RTS switched to False (RX mode)")
    
    start = time.time()
    response_bytes = b""
    while time.time() - start < 5:
        if ser.in_waiting > 0:
            chunk = ser.read(ser.in_waiting)
            response_bytes += chunk
            elapsed = time.time() - start
            print(f"  📥 [{elapsed:.3f}s] Raw hex: {chunk.hex()}")
            print(f"  📥 [{elapsed:.3f}s] Text: {chunk.decode(errors='replace')}")
        time.sleep(0.01)
    
    if response_bytes:
        print(f"  ✅ [RTS toggle] Nhận được {len(response_bytes)} bytes!")
    else:
        print(f"  ❌ [RTS toggle] KHÔNG nhận được byte nào!")
    result3 = len(response_bytes) > 0
    
    # ═══════════════════════════════════════════════
    # TEST 4: Không gửi gì, chỉ đọc (chờ ALIVE)
    # ═══════════════════════════════════════════════
    print(f"\n[TEST 4] Chỉ đọc, chờ ALIVE từ Arduino (tối đa 70s)...")
    ser.rts = False
    ser.reset_input_buffer()
    
    start = time.time()
    alive_received = False
    while time.time() - start < 70:
        if ser.in_waiting > 0:
            chunk = ser.read(ser.in_waiting)
            text = chunk.decode(errors='replace')
            print(f"  📥 [{time.time()-start:.1f}s] hex={chunk.hex()}")
            print(f"  📥 [{time.time()-start:.1f}s] text={text.strip()}")
            if "ALIVE" in text or "slave" in text:
                alive_received = True
                break
        time.sleep(0.05)
    
    # ═══════════════════════════════════════════════
    # KẾT LUẬN
    # ═══════════════════════════════════════════════
    print(f"\n{'='*50}")
    print(f"KẾT QUẢ:")
    print(f"  TEST 1 (default):    {'✅' if result1 else '❌'}")
    print(f"  TEST 2 (RTS=False):  {'✅' if result2 else '❌'}")
    print(f"  TEST 3 (RTS toggle): {'✅' if result3 else '❌'}")
    print(f"  TEST 4 (ALIVE):      {'✅' if alive_received else '❌'}")
    print(f"{'='*50}")
    
    if alive_received and not (result1 or result2 or result3):
        print("→ Arduino→Pi hoạt động khi idle (ALIVE)")
        print("→ Nhưng response sau PING bị mất")
        print("→ Adapter cần thời gian TX→RX dài hơn")
        print("→ Thử tăng delay(50) → delay(200) trên Arduino")
    elif not alive_received and not (result1 or result2 or result3):
        print("→ Arduino→Pi HOÀN TOÀN không hoạt động!")
        print("→ Kiểm tra: dây A/B, module MAX485, adapter USB")
    elif result2 or result3:
        print("→ FIX: Cần set RTS=False trên Pi sau mỗi lần gửi!")
        print("→ Sẽ fix trong serial_manager.py")
    
    ser.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
