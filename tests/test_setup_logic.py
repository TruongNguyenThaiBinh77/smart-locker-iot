import sys
import os
import json
import time
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.setup_handler import SetupHandler
from domain.enums import CommandAction

def test_setup_jammed_logic():
    # Mock MQTT and Serial
    mock_mqtt = MagicMock()
    mock_serial = MagicMock()
    
    # Payload for setup
    payload = {
        "commandId": "setup-123",
        "cabinetId": "cab-123",
        "macAddress": "00:00:00:00:00:00",
        "totalRows": 1,
        "totalColumns": 1,
        "setupQuantity": 1,
        "lockerLayout": [{"slotIndex": 0, "row": 0, "column": 0}],
        "testTimeout": 5
    }

    handler = SetupHandler(mock_mqtt, mock_serial)
    
    # Case 1: Door stays CLOSED after open (JAMMED)
    mock_serial.open_slot.return_value = {
        "slot": 0,
        "result": "OK",
        "door": False, # Still closed
        "servo": True,
        "ms": 500
    }
    
    # We need to capture the MQTT message to verify result
    sent_payloads = []
    def mock_publish(topic, msg, qos=1):
        if "setup/result" in topic:
            sent_payloads.append(json.loads(msg))
            
    mock_mqtt.publish.side_effect = mock_publish
    
    # Run setup
    handler._run_setup(payload, "cabinet/test")
    
    # Verify result
    result = sent_payloads[0]
    assert result["status"] == "FAILED"
    assert result["lockers"][0]["hwState"] == "JAMMED"
    assert result["lockers"][0]["errorCode"] == "JAMMED"
    
    print("✅ SetupHandler JAMMED logic test passed!")

    # Case 2: Door opens successfully
    sent_payloads.clear()
    mock_serial.open_slot.return_value = {
        "slot": 0,
        "result": "OK",
        "door": True, # Opened
        "servo": True,
        "ms": 500
    }
    
    handler._run_setup(payload, "cabinet/test")
    
    result = sent_payloads[0]
    assert result["status"] == "COMPLETED"
    assert result["lockers"][0]["hwState"] == "CLOSING" # result detail hwState is mapped to CLOSING if testResult is OK
    
    # Verify close_command was called to reset
    mock_serial.close_slot.assert_called_with(0)
    
    print("✅ SetupHandler SUCCESS logic test passed!")

if __name__ == "__main__":
    try:
        test_setup_jammed_logic()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
