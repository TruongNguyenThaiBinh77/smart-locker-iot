from enum import Enum


class LockerHwState(Enum):
    OPENING = "OPENING"
    CLOSING = "CLOSING"
    OFFLINE = "OFFLINE"


class CommandAction(Enum):
    OPEN = "OPEN"
    RENT_OPEN = "RENT_OPEN"
    TEMP_OPEN = "TEMP_OPEN"
    EMERGENCY_OPEN = "EMERGENCY_OPEN"
    SETUP_LOCKERS = "SETUP_LOCKERS"
    BULK_SETUP_LOCKERS = "BULK_SETUP_LOCKERS"
    CLEAR_SETUP = "CLEAR_SETUP"


class AckStatus(Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SetupStatus(Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    ABORTED = "ABORTED"


class TestResult(Enum):
    OK = "OK"
    FAIL = "FAIL"


class ErrorCode(Enum):
    MOTOR_FAILURE = "MOTOR_FAILURE"
    SENSOR_ERROR = "SENSOR_ERROR"
    TIMEOUT = "TIMEOUT"
    LOCK_STUCK = "LOCK_STUCK"
    POWER_LOSS = "POWER_LOSS"
    UNKNOWN = "UNKNOWN"


class AuthMethod(Enum):
    FACE_ID = "FACE_ID"
    QR_CODE = "QR_CODE"