from dataclasses import dataclass, field, asdict
from typing import Optional, List
import json


@dataclass
class HeartbeatPayload:
    cabinetId: str
    timestamp: str
    status: str           # "online"
    lockers: list         # [{"slotIndex": 0, "hwState": "CLOSING"}, ...]
    macAddress: Optional[str] = None
    uptime: Optional[int] = None
    cpuTemp: Optional[float] = None
    memoryUsage: Optional[float] = None

    def to_json(self):
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data)


@dataclass
class AckPayload:
    lockerId: str
    commandId: str
    action: str
    status: str
    message: str
    timestamp: str

    def to_json(self):
        return json.dumps(asdict(self))


@dataclass
class OpenAckPayload:
    """RPi → BE: Phản hồi sau khi mở locker (Topic: {prefix}/locker/{lockerId}/ack)"""
    lockerId: str
    slotIndex: int
    status: str        # "SUCCESS" | "FAIL"
    message: str
    timestamp: str
    errorCode: Optional[str] = None

    def to_json(self):
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data)


@dataclass
class StatusPayload:
    lockerId: str
    hwState: str
    doorSensor: bool
    lockSensor: bool
    timestamp: str
    commandId: Optional[str] = None
    previousHwState: Optional[str] = None
    temperature: Optional[float] = None
    slotIndex: Optional[int] = None

    def to_json(self):
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data)


@dataclass
class ErrorPayload:
    """RPi → BE: Báo lỗi phần cứng (Topic: {prefix}/locker/{lockerId}/error)"""
    lockerId: str
    errorCode: str
    errorMessage: str
    hwState: str
    timestamp: str
    commandId: Optional[str] = None
    slotIndex: Optional[int] = None

    def to_json(self):
        return json.dumps({k: v for k, v in asdict(self).items() if v is not None})


@dataclass
class ConfigSyncPayload:
    """RPi → BE: Đồng bộ cấu hình khi khởi động (Topic: {prefix}/config/sync)"""
    cabinetId: str
    cabinetCode: str
    macAddress: str
    ipAddress: str
    firmwareVersion: str
    pythonVersion: str
    configVersion: str
    connectedArduinos: int
    timestamp: str

    def to_json(self):
        return json.dumps(asdict(self))


# ─── Setup / Provisioning payloads ───

@dataclass
class HwDetail:
    """Chi tiết phần cứng từng slot khi test."""
    servoResponse: bool
    doorSensor: bool
    lockSensor: bool
    responseTimeMs: Optional[int] = None


@dataclass
class SetupProgress:
    """Tiến trình test slot."""
    tested: int
    total: int
    okCount: int
    failCount: int


@dataclass
class SetupProgressPayload:
    """RPi → BE: Progress sau mỗi locker test (Topic: {prefix}/setup/progress)"""
    commandId: str
    cabinetId: str
    slotIndex: int
    row: int
    column: int
    testResult: str
    hwDetail: dict
    progress: dict
    timestamp: str

    def to_json(self):
        return json.dumps(asdict(self))


@dataclass
class LockerResultDetail:
    """Chi tiết kết quả test 1 locker."""
    slotIndex: int
    row: int
    column: int
    testResult: str
    hwState: str
    responseTimeMs: Optional[int] = None
    errorCode: Optional[str] = None
    errorMessage: Optional[str] = None


@dataclass
class SetupResultSummary:
    """Tổng hợp kết quả setup."""
    total: int
    totalOk: int
    totalFail: int
    duration: int


@dataclass
class SetupResultPayload:
    """RPi → BE: Kết quả tổng hợp setup (Topic: {prefix}/setup/result)"""
    commandId: str
    cabinetId: str
    status: str
    summary: dict
    lockers: list
    timestamp: str

    def to_json(self):
        return json.dumps(asdict(self))


@dataclass
class CabinetConfigResponse:
    """API Gateway → RPi: Cấu hình cabinet (Topic: {prefix}/config/sync)"""
    cabinetId: str
    cabinetCode: str
    locationId: str
    mqttTopicPrefix: str
    heartbeatInterval: int
    openDoorTimeout: int
    ledIntensity: int
    volumeLevel: int
    isSynced: bool
    mqttBrokerHost: str
    mqttBrokerPort: int
    mqttUsername: str
    mqttPassword: str
    isActive: bool
    totalRows: int
    totalColumns: int
    lastSyncedAt: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class ClearSetupAckPayload:
    """RPi → BE: Phản hồi nhận lệnh clear (Topic: {prefix}/ack)"""
    cabinetId: str
    commandId: str
    action: str
    status: str
    message: str
    timestamp: str

    def to_json(self):
        return json.dumps(asdict(self))


@dataclass
class ClearSetupResultPayload:
    """RPi → BE: Phản hồi kết quả sau khi Clear xong (Topic: {prefix}/setup/clear-result)"""
    commandId: str
    cabinetId: str
    status: str
    timestamp: str
    errorMessage: Optional[str] = None

    def to_json(self):
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data)
