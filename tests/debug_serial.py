import serial
import time
import sys

def test_serial(port='/dev/ttyUSB0', baud=9600):
    print(f"Opening {port} at {baud}...")
    try:
        ser = serial.Serial(port, baud, timeout=2)
        time.sleep(2) # Wait for Arduino reset
        
        test_strings = [
            "O0\n",
            "T1\n",
            "C2\n",
            "hello\n",
            "ooOO__\n"
        ]
        
        for msg in test_strings:
            print(f"TX: {repr(msg)}")
            ser.write(msg.encode())
            ser.flush()
            
            # Wait for response
            time.sleep(0.5)
            if ser.in_waiting > 0:
                rx = ser.read(ser.in_waiting).decode(errors='ignore')
                print(f"RX: {repr(rx)}")
            else:
                print("RX: [No response]")
            print("-" * 20)
            
        ser.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
    test_serial(port)
