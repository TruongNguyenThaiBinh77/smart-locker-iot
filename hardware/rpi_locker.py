import time
from domain.enums import LockerHwState
from utils.logger import get_logger

logger = get_logger("Hardware")

class HardwareController:
    """
    Class này chịu trách nhiệm điều khiển GPIO thật.
    Hiện tại đang viết dạng Simulation (giả lập) để bạn test logic.
    """
    def __init__(self):
        # Lưu trạng thái giả lập của các locker
        self._states = {} 

    def init_locker(self, locker_id):
        self._states[locker_id] = {
            "hwState": LockerHwState.CLOSING.value,
            "doorSensor": False, # False = Đóng
            "lockSensor": True   # True = Đang khóa
        }

    def unlock(self, locker_id, timeout=5):
        """Mở khóa tủ"""
        if locker_id not in self._states:
            self.init_locker(locker_id)
            
        logger.info(f"[GPIO] Unlocking locker {locker_id}...")
        
        # Cập nhật trạng thái thành công
        self._states[locker_id]["hwState"] = LockerHwState.OPENING.value
        self._states[locker_id]["doorSensor"] = True
        self._states[locker_id]["lockSensor"] = False
        
        logger.info(f"[GPIO] Locker {locker_id} opened.")
        return True

    def get_status(self, locker_id):
        """Đọc cảm biến hiện tại"""
        if locker_id not in self._states:
            self.init_locker(locker_id)
        return self._states[locker_id]