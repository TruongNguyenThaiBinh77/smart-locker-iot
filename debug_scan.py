import logging
import json
import time
import threading
import sys
import os

# Configure logging to show everything
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Giả lập sys.path để import được SerialManager
sys.path.append(os.getcwd())

from infracstructure.serial_manager import SerialManager

def debug_scan():
    # Khởi tạo SerialManager với port từ settings
    from config.settings import settings
    
    print(f"Initializing SerialManager on {settings.SERIAL_PORT} @ {settings.SERIAL_BAUD_RATE}")
    manager = SerialManager(settings.SERIAL_PORT, settings.SERIAL_BAUD_RATE)
    
    time.sleep(2) # Chờ ổn định
    
    print("\n--- STARTING DEBUG SCAN ---")
    
    range_start = 1
    range_end = 3
    
    found = []
    for sid in range(range_start, range_end + 1):
        print(f"\nScanning RS485 for Slave ID {sid}...")
        
        # Gọi internal _send_and_wait để debug trực tiếp
        # range_start = sid, range_end = sid
        # res = manager._send_and_wait(f"S{sid}:PING\n", -1, timeout=2, custom_slave_id=sid)
        
        # Hoặc gọi scan_slaves cho sid này
        res_list = manager.scan_slaves(range_start=sid, range_end=sid)
        
        if res_list:
            print(f"Result for SID {sid}: {res_list}")
            found.extend(res_list)
        else:
            print(f"Result for SID {sid}: NOT FOUND")
            # Kiểm tra trạng thái cuối cùng của manager._response_data nếu có thể
            print(f"Last raw response data: {manager._response_data}")

    print(f"\n--- SCAN COMPLETE ---")
    print(f"Total found: {len(found)}")
    print(f"Slaves: {found}")
    
    manager.close()

if __name__ == "__main__":
    try:
        debug_scan()
    except Exception as e:
        print(f"Error during debug scan: {e}")
