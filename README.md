# Smart Locker IoT

<!-- CURRENT_STATUS_START -->
> **Cập nhật 2026-06-13:** Tài liệu này đã được rà soát để bám theo trạng thái hiện tại của dự án. Backend Phase 2 cho locker flow đã triển khai SEND / RENTAL / QR / RBAC / maintenance; FE admin build pass; Flutter mobile đã có luồng Customer, Manager và Maintenance. Nguồn trạng thái chuẩn: `laundry-locker-microservices/docs/CURRENT_PROJECT_STATUS.md`, `RUN_RESULT.md`, `LOCKER_FLOW_PLAN.md`.
<!-- CURRENT_STATUS_END -->

Python/uv runtime for the smart locker cabinet side. This project is intended to run on a Raspberry Pi and talk to cabinet hardware through serial/RS485 while using MQTT for backend/device messages.

## Current Role In The System

The backend now supports access verification with either:

- Active PIN.
- Signed QR token returned as `qrToken` in `OrderResponse`.

The relevant backend endpoint is:

```http
POST /api/iot/verify-access
```

Body:

```json
{
  "boxId": 16,
  "pinCode": "123456 or LLQR..."
}
```

The IoT runtime should use the same broker/topic configuration as `iot-service` when testing real cabinet commands.

## Run Locally

```powershell
Set-Location G:\BigProject\smart-locker-iot
uv sync
uv run python main.py
```

On a normal PC without the Arduino/serial hardware attached, serial initialization may fail. Use simulation settings for software-only checks.

## Backend Dependency

Start the backend first:

```powershell
Set-Location G:\BigProject\laundry-locker-microservices
mvn.cmd clean package -DskipTests
docker compose up --build -d
```

Gateway:

```text
http://localhost:8080
```

IoT service:

```text
http://localhost:8088
```

## Demo Simulation (No Hardware)

`main.py` is the real hardware-track runtime: it only starts answering open
commands after it receives a `SETUP_LOCKERS` handshake on
`iot/{macAddress}/command/setup`, and nothing in the backend sends that
handshake yet (it's meant for a provisioning step that ships with the real
Raspberry Pi/Arduino integration). `SIMULATION=true` only mocks the serial
layer underneath `main.py` — it does not skip that handshake — so running
`main.py` alone today will never reply to `iot-service`'s unlock requests.

For demoing the mobile -> backend -> IoT -> backend -> mobile unlock loop
*right now*, without waiting on hardware, run the standalone simulator
instead. It is a separate script and does not touch `main.py`/serial/setup
code, so it won't conflict with that ongoing hardware work:

```powershell
Set-Location D:\capstone-laundry-locker\smart-locker-iot
uv run python simulate_demo_cabinet.py
```

It subscribes to `cabinet/+/command/open` for every locker and replies on
`cabinet/{lockerId}/command/open/result` after a short simulated delay,
matching exactly what `iot-service` (`LockerMqttService.sendUnlockCommandAsync`)
publishes today. From the mobile app, opening an active SEND/RENTAL order
and tapping "Mở tủ" calls `POST /api/iot/unlock`, which this script answers.

Useful env vars (only for this script):

- `SIM_DELAY_SECONDS` (default `1.5`) — simulated door latency.
- `SIM_FORCE_FAIL` (default `false`) — reply `FAILED` to test the error path.
- `MQTT_BROKER_URL` (e.g. `tcp://broker.hivemq.com:1883`) or `MQTT_BROKER`/`MQTT_PORT` — point at a different broker; defaults to the same broker `iot-service` defaults to.

Once real hardware + the setup handshake are ready, retire this script and
go through `main.py` instead — no backend changes are needed either way
since both speak the same MQTT contract.

## Kiosk Web (màn hình tủ mô phỏng — `ui/`)

Trong lúc chưa có tủ vật lý, web trong `ui/` đóng vai màn hình cảm ứng của
tủ: khách đặt đơn trên mobile xong, tới "tủ" (mở web này) và mở ô bằng:

- **Nhập mã PIN**: nhập số ô tủ → PIN 6 số (`/api/iot/verify-pin` + `/api/iot/unlock`).
- **Mã QR / Ủy quyền**: dán PIN, QR token (`LLQR...`) hoặc mã ủy quyền —
  backend tự tra đơn và suy ra ô (`/api/iot/unlock-with-code`).
- **Gửi đồ mới tại tủ**: đăng nhập OTP email/SĐT rồi tạo đơn ngay trên kiosk.

4 endpoint verify/unlock được gateway mở public (bản thân mã là credential,
sai mã nhiều lần bị khóa ô tạm thời); phần còn lại của `/api/iot/**` vẫn cần JWT.
Lệnh mở cửa vẫn đi MQTT → `simulate_demo_cabinet.py` trả lời như tủ thật.

```powershell
# backend + simulator chạy trước, rồi:
Set-Location .\ui
npm install
npm run dev          # http://localhost:5173 (?lockerId=1 nếu muốn đổi tủ)
```

Gateway mặc định `http://localhost:18080` — đổi bằng env `VITE_API_URL`.

## MQTT Notes

Backend `iot-service` currently defaults to a public broker unless overridden by environment/config. For real integration, make sure both sides point to the same broker.

Typical concepts used by the cabinet runtime:

- Device heartbeat.
- Box/cell status update.
- Backend command to open a box.
- Command result back to backend.

## Future Work

- Tablet-web locker UI.
- Door/weight sensor integration to auto-mark cells occupied after deposit.
- Real drone deposit channel integration.
- Biometric verification on Raspberry Pi.
