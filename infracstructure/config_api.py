from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import threading
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

    @app.get("/system/info")
    @app.get("/system/info/")
    async def get_system_info():
        return {
            "macAddress": settings.MAC_ADDRESS,
            "version": settings.FIRMWARE_VERSION,
            "status": "online"
        }

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

    return app

def start_config_api(db_manager, cabinet_state, port: int = 8000):
    app = create_config_app(db_manager, cabinet_state)
    
    def run():
        logger.info(f"Starting Local Config API on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

    api_thread = threading.Thread(target=run, daemon=True, name="ConfigAPIThread")
    api_thread.start()
    return api_thread
