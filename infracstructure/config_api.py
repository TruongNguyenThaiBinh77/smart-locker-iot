from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn
import threading
import socket
import os
from pathlib import Path
from utils.logger import get_logger
from config.settings import settings

logger = get_logger("ConfigAPI")

class MQTTConfigUpdate(BaseModel):
    broker: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    useTls: bool = True

def create_config_app(db_manager, cabinet_state):
    app = FastAPI(title="AISL IoT Config API")
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Trong môi trường local cho phép tất cả
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _get_local_ip() -> str:
        """Lấy IP address của máy."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "0.0.0.0"

    @app.get("/system/info")
    @app.get("/system/info/")
    async def get_system_info():
        loc = cabinet_state.location
        return {
            "macAddress": settings.MAC_ADDRESS,
            "version": settings.FIRMWARE_VERSION,
            "status": "online",
            "ipAddress": _get_local_ip(),
            "location": loc,
            "cabinetCount": len(cabinet_state.all_cabinets),
        }

    @app.get("/system/state")
    async def get_system_state():
        """Trả về toàn bộ trạng thái: location, cabinets."""
        return {
            "location": cabinet_state.location,
            "cabinets": cabinet_state.all_cabinets,
            "isConfigured": cabinet_state.is_configured,
        }

    @app.get("/logs/recent")
    async def get_recent_logs(limit: int = 50):
        """Lấy các MQTT log gần nhất."""
        try:
            logs = db_manager.get_recent_logs(limit=limit)
            return logs
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @app.get("/config/mqtt")
    async def get_mqtt_config():
        config = db_manager.get_mqtt_config()
        if not config:
            return {
                "broker": "localhost",
                "port": 1883,
                "username": "",
                "password": "",
                "useTls": True,
                "isDefault": True
            }
        return config

    @app.get("/config/system")
    async def get_system_config():
        return {
            "max_cabinets": db_manager.get_system_setting("max_cabinets", settings.MAX_CABINETS)
        }

    @app.post("/config/mqtt")
    async def update_mqtt_config(config: MQTTConfigUpdate):
        try:
            db_manager.save_mqtt_config(config.model_dump())
            logger.info(f"MQTT config updated via API: {config.broker}:{config.port}")
            return {"status": "success", "message": "MQTT config updated. Please restart the service to apply."}
        except Exception as e:
            logger.error(f"Failed to update MQTT config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/config/system")
    async def update_system_config(config: dict):
        try:
            for key, value in config.items():
                db_manager.save_system_setting(key, value)
            # Re-load settings
            settings.update_system_config(db_manager)
            logger.info(f"System config updated via API: {config}")
            return {"status": "success", "message": "System config updated."}
        except Exception as e:
            logger.error(f"Failed to update system config: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/setup/clear")
    async def clear_setup():
        try:
            cabinet_state.clear()
            logger.info("Cabinet setup cleared via API")
            return {"status": "success", "message": "Cabinet setup cleared successfully."}
        except Exception as e:
            logger.error(f"Failed to clear setup: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # --- TEST API (Bypass hardware) ---
    class TestOpenOTPRequest(BaseModel):
        otp: str
        lockerId: Optional[str] = None
        boxId: Optional[str] = None

    @app.post("/test/open-otp")
    async def test_open_otp(req: TestOpenOTPRequest):
        logger.warning(f"🚀 MOCK API: Đã nhận mã OTP '{req.otp}' từ mobile để mở tủ (Không dùng linh kiện).")
        # Giả lập logic kiểm tra và mở khóa
        return {
            "success": True,
            "message": f"Giả lập mở tủ thành công với mã OTP: {req.otp}",
            "hardwareSimulated": True
        }

    # ─── Static UI Dashboard ───
    _ui_dir = Path(__file__).parent.parent / "ui" / "dist"
    if _ui_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(_ui_dir), html=True), name="ui")
        logger.info(f"Dashboard UI mounted at /ui (dir={_ui_dir})")
    else:
        logger.warning(f"UI directory not found at {_ui_dir}. Make sure you ran 'npm run build' inside ui/.")

    return app

def start_config_api(db_manager, cabinet_state, port: int = 8000):
    app = create_config_app(db_manager, cabinet_state)
    
    def run():
        logger.info(f"Starting Local Config API on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

    api_thread = threading.Thread(target=run, daemon=True, name="ConfigAPIThread")
    api_thread.start()
    return api_thread
