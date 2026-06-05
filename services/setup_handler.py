import time
import threading
from datetime import datetime, timezone
from dataclasses import asdict
from config.settings import settings
from domain.models import (
    SetupProgressPayload,
    SetupResultPayload,
    HwDetail,
    SetupProgress,
    LockerResultDetail,
    SetupResultSummary,
)
from utils.logger import get_logger

logger = get_logger("SetupHandler")


class SetupHandler:
    """
    Xử lý lệnh SETUP_LOCKERS từ BE.

    Khi nhận lệnh setup:
    1. Lần lượt test từng slot qua SerialManager → Arduino
    2. Publish progress tới cabinet/{cabinetName}/setup/progress
    3. Publish result tới cabinet/{cabinetName}/setup/result
    """

    def __init__(self, mqtt_client, serial_manager, cabinet_state=None,
                 on_setup_complete=None):
        self.mqtt = mqtt_client
        self.serial = serial_manager
        self.cabinet_state = cabinet_state
        self._on_setup_complete = on_setup_complete
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def handle(self, payload: dict, prefix: str):
        """
        Handle SETUP_LOCKERS or BULK_SETUP_LOCKERS command.
        prefix = "iot/{macAddress}" (lấy từ topic)
        """
        if self._is_running:
            logger.warning("Setup already in progress, ignoring new command")
            return

        action = payload.get("action", "")
        
        # ─── Validate Payload ───
        if action == "BULK_SETUP_LOCKERS":
            cabinets = payload.get("cabinets", [])
            if not cabinets:
                logger.error("Bulk setup rejected: no cabinets in payload")
                return
        else:
            # Single setup validation
            from infracstructure.serial_manager import MAX_SLOTS
            layout = payload.get("lockerLayout", [])
            if len(layout) > MAX_SLOTS:
                logger.error(f"Setup REJECTED: layout={len(layout)} exceeds MAX_SLOTS={MAX_SLOTS}")
                self._report_failure(payload, prefix, "Arduino Limit Exceeded")
                return

        thread = threading.Thread(
            target=self._run_setup,
            args=(payload, prefix),
            daemon=True,
            name="SetupThread"
        )
        thread.start()

    def _report_failure(self, payload: dict, prefix: str, error_msg: str):
        reject_payload = SetupResultPayload(
            commandId=payload.get("commandId", ""),
            cabinetId=payload.get("cabinetId", ""),
            status="FAILED",
            summary=asdict(SetupResultSummary(total=0, totalOk=0, totalFail=0, duration=0)),
            lockers=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.mqtt.publish(f"{prefix}/setup/result", reject_payload.to_json(), qos=1)

    def _run_setup(self, payload: dict, prefix: str):
        """Logic chính setup – chạy trên thread riêng."""
        import logging
        from utils.logger import set_global_log_level
        self._is_running = True
        set_global_log_level(logging.INFO)
        
        action = payload.get("action", "")
        command_id = payload.get("commandId", "no-id")
        
        try:
            test_timeout = payload.get("testTimeout", 10)
            
            # Danh sách các tủ cần setup
            cabinets_to_process = []
            if action == "BULK_SETUP_LOCKERS":
                cabinets_to_process = payload.get("cabinets", [])
            else:
                # Wrap single setup into list
                cabinets_to_process = [{
                    "cabinetId": payload["cabinetId"],
                    "cabinetCode": payload.get("cabinetCode", "Unknown"),
                    "slaveId": payload.get("slaveId", 1),
                    "lockerLayout": payload.get("lockerLayout", []),
                    "totalRows": payload.get("totalRows", 0),
                    "totalColumns": payload.get("totalColumns", 0)
                }]

            logger.info(f"=== {action} START: count={len(cabinets_to_process)} ===")

            # 1. Lưu Location (chung cho cả gateway)
            if self.cabinet_state:
                # [NEW] Xoá sạch state cũ trước khi đồng bộ mới nếu là lệnh BULK
                if action == "BULK_SETUP_LOCKERS":
                    logger.info("Bulk setup detected. Pruning old cabinet state.")
                    self.cabinet_state.clear()

                loc_id = payload.get("locationId") or "unknown-loc"
                loc_name = payload.get("locationName") or "Unknown Location"
                loc_addr = payload.get("address") or ""
                self.cabinet_state.save_location(loc_id, loc_name, loc_addr)

            for cab_data in cabinets_to_process:
                cabinet_id = cab_data["cabinetId"]
                # Ưu tiên cabinetCode từ payload gởi xuống
                cabinet_name = cab_data.get("cabinetCode") or cab_data.get("name") or f"Cab-{cabinet_id[:4]}"
                slave_id = cab_data.get("slaveId", 1)
                layout = cab_data.get("lockerLayout", [])

                logger.info(f"Processing Cabinet: {cabinet_name} (Slave={slave_id}, Slots={len(layout)})")

                results = []
                ok_count = 0
                fail_count = 0
                start_time = time.time()

                for i, slot in enumerate(layout):
                    # SAFETY: Handle slotIndex being None or string
                    raw_slot_index = slot.get("slotIndex")
                    if raw_slot_index is None:
                        logger.error(f"[{cabinet_name}] Slot {i} has NULL slotIndex. Skipping.")
                        continue
                        
                    try:
                        slot_index = int(raw_slot_index)
                    except (ValueError, TypeError):
                        logger.error(f"[{cabinet_name}] Slot {i} has invalid slotIndex '{raw_slot_index}'. Skipping.")
                        continue

                    if slot_index < 0: continue

                    logger.info(f"[{cabinet_name}] Testing slot {slot_index} ({i+1}/{len(layout)})...")
                    
                    # Test hardware
                    result = self.serial.test_slot(slot_index, slave_id=slave_id, timeout=test_timeout)
                    is_door_closed = result.get("door", False)
                    
                    if result.get("result") != "OK":
                        test_result = "FAIL"
                        error_code = "HW_ERROR"
                        error_msg = f"Arduino test failed: {result.get('error', 'unknown')}"
                    elif is_door_closed:
                        test_result = "FAIL"
                        error_code = "DOOR_STUCK"
                        error_msg = "Servo popped but door remained closed (mechanical delay or stuck)"
                    else:
                        test_result = "OK"
                        error_code = None
                        error_msg = None
                        
                    if test_result == "OK": ok_count += 1
                    else: fail_count += 1
                    
                    result["result"] = test_result
                    result["error_code"] = error_code
                    result["error_msg"] = error_msg
                    results.append(result)

                    # Publish progress
                    progress_payload = SetupProgressPayload(
                        commandId=command_id, cabinetId=cabinet_id, slotIndex=slot_index,
                        row=slot.get("row", 0), column=slot.get("column", 0),
                        testResult=test_result,
                        hwDetail=asdict(HwDetail(
                            servoResponse=True if test_result == "OK" else False,
                            doorSensor=is_door_closed, lockSensor=False,
                            responseTimeMs=result.get("ms"),
                        )),
                        progress=asdict(SetupProgress(
                            tested=i + 1, total=len(layout), okCount=ok_count, failCount=fail_count,
                        )),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    self.mqtt.publish(f"{prefix}/setup/progress", progress_payload.to_json(), qos=1)
                    time.sleep(0.1)

                # --- Hoàn tất 1 tủ ---
                duration = int(time.time() - start_time)
                status = "COMPLETED" if fail_count == 0 else "FAILED" if ok_count == 0 else "PARTIAL"

                # Build result markers
                lockers_detail = []
                for slot, res in zip(layout, results):
                    detail = LockerResultDetail(
                        slotIndex=slot["slotIndex"], row=slot["row"], column=slot["column"],
                        testResult=res["result"], 
                        hwState="CLOSING" if res["result"] == "OK" else "OFFLINE",
                        responseTimeMs=res.get("ms"),
                        errorCode=res.get("error_code"),
                        errorMessage=res.get("error_msg")
                    )
                    lockers_detail.append(detail)

                # Publish result cho tủ này
                final_payload = SetupResultPayload(
                    commandId=command_id, cabinetId=cabinet_id, status=status,
                    summary=asdict(SetupResultSummary(total=len(layout), totalOk=ok_count, totalFail=fail_count, duration=duration)),
                    lockers=[asdict(d) for d in lockers_detail],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                self.mqtt.publish(f"{prefix}/setup/result", final_payload.to_json(), qos=1)

                # Lưu state tủ và mapping lockers
                if self.cabinet_state and status != "FAILED":
                    self.cabinet_state.save_cabinet(
                        cabinet_id=cabinet_id,
                        name=cabinet_name,
                        total_rows=cab_data.get("totalRows", 0),
                        total_columns=cab_data.get("totalColumns", 0),
                        slave_id=slave_id,
                        is_synced=True
                    )
                    
                    # [NEW] Save locker mapping (id <-> slotIndex) cho security reporting
                    self.cabinet_state.save_lockers(cabinet_id, cab_data.get("lockerLayout", []))

                    if self._on_setup_complete:
                        self._on_setup_complete(cabinet_name)

        except Exception as e:
            logger.exception(f"Unexpected error during setup: {e}")
        finally:
            self._is_running = False
            logger.info(f"=== {action} FINISHED ===")
