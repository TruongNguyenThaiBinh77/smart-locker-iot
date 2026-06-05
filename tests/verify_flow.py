import os
import subprocess
import time
import signal

# Cấu hình môi trường test
os.environ["BACKEND_API_URL"] = "http://localhost:8081"
os.environ["SERIAL_PORT"] = "COM3" # Giả định COM3 cho simulation trong SerialManager nếu cần, 
                                    # nhưng main.py đang set simulation=False.
                                    # Thực tế SerialManager có mode simulation.

print("Starting main.py with mock backend...")
process = subprocess.Popen(["python", "main.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

try:
    # Đọc output trong 10 giây
    start_time = time.time()
    while time.time() - start_time < 15:
        line = process.stdout.readline()
        if not line:
            break
        print(f"[main.py] {line.strip()}")
        
        if "Settings updated from backend API" in line:
            print("✅ CONFIRMED: Settings updated from API")
        if "Triggering AUTO-SETUP" in line:
            print("✅ CONFIRMED: Auto-setup triggered")
        if "layout=2x2" in line:
            print("✅ CONFIRMED: Layout detected correctly")

except Exception as e:
    print(f"Error during test: {e}")
finally:
    print("Terminating main.py...")
    process.terminate()
    try:
        process.wait(timeout=2)
    except:
        process.kill()
