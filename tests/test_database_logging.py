import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from infracstructure.database import DatabaseManager
from config.settings import settings

def test_sqlite_logging():
    print("--- Testing SQLite Logging ---")
    
    # Use a temporary test database
    test_db_path = "data/test_locker_system.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        
    db = DatabaseManager(test_db_path)
    
    # 1. Test log_mqtt
    print("Testing MQTT logging...")
    db.log_mqtt("cabinet/cab-001/locker/L1/command/open", {"commandId": "cmd-123", "action": "OPEN"}, "IN")
    db.log_mqtt("cabinet/cab-001/locker/L1/ack", {"status": "SUCCESS"}, "OUT")
    
    # 2. Test log_event
    print("Testing Locker event logging...")
    db.log_event(
        event_type="OPEN_COMMAND",
        locker_id="locker-uuid-1",
        slot_index=0,
        status="SUCCESS",
        message="Locker opened via test script",
        command_id="cmd-123"
    )
    
    db.log_event(
        event_type="CLOSE_EVENT",
        slot_index=0,
        status="SUCCESS",
        message="Door sensor detected CLOSED"
    )
    
    # 3. Verify data
    print("Verifying data in database...")
    mqtt_logs = db.get_recent_logs(limit=10)
    print(f"Found {len(mqtt_logs)} MQTT logs.")
    for log in mqtt_logs:
        print(f"  [{log['direction']}] {log['topic']}: {log['payload']}")
        
    # Check locker events
    import sqlite3
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM locker_events")
    events = cursor.fetchall()
    print(f"Found {len(events)} locker events.")
    for event in events:
        print(f"  Event: {event[3]} | Slot: {event[2]} | Status: {event[4]}")
    conn.close()

    print("\n--- Test Complete ---")
    
    # Cleanup (optional - comment out if you want to inspect)
    # os.remove(test_db_path)

if __name__ == "__main__":
    test_sqlite_logging()
