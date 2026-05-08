import os
import warnings

# ==========================================
# 0. TESTING TOGGLE
# ==========================================
# Set to False to bypass TensorFlow and AI Engine for instant API startup.
# In a real environment, prefer using os.getenv("ENABLE_AI_ENGINE", "True") == "True"
ENABLE_AI_ENGINE = False

# ==========================================
# 1. SUPPRESS TENSORFLOW & DEPRECATION NOISE
# ==========================================
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

if ENABLE_AI_ENGINE:
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

    import tensorflow as tf

    try:
        tf.config.set_visible_devices([], 'GPU')
    except Exception:
        pass

# ==========================================
# 2. STANDARD IMPORTS
# ==========================================
import asyncio
import multiprocessing
import queue
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Your App Routers
from api import auth, cameras, dashboard, floor, family, unwanted_person, logs, settings, others, rules

# Conditionally import your custom AI modules
if ENABLE_AI_ENGINE:
    from ai_engine.face_recognition import FaceCache
    from ai_engine.orchestrator import camera_manager

# ==========================================
# 3. GLOBAL STATE & WEBSOCKET BRIDGE
# ==========================================
alert_queue = multiprocessing.Queue()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


async def watch_queue():
    """Background task to constantly check if the AI found an intruder."""
    print("🌐 [WebSocket] Listening for AI alerts...")
    while True:
        try:
            alert = alert_queue.get_nowait()
            print(f"🚨 [FastAPI] Broadcasting Alert: {alert}")
            await manager.broadcast(alert)
        except queue.Empty:
            await asyncio.sleep(0.1)


# ==========================================
# 4. APP LIFESPAN (Startup & Shutdown)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting FastAPI Server...")

    # 1. Start the Background Queue Watcher for WebSockets
    asyncio.create_task(watch_queue())

    if ENABLE_AI_ENGINE:
        print("🧠 Booting AI Engine...")
        # 2. Sync database faces into memory
        FaceCache.sync_from_db()

        camera_manager.set_alert_queue(alert_queue)

        # 3. DELEGATE TO ORCHESTRATOR
        camera_manager.sync_cameras()
    else:
        print("⚡ FAST MODE ACTIVE: AI Engine and TensorFlow bypassed for testing.")

    yield  # The server is now running!

    print("🛑 Shutting down server and releasing resources...")

    if ENABLE_AI_ENGINE:
        # 4. Clean up AI Processes on shutdown
        camera_manager.shutdown_all()


# ==========================================
# 5. FASTAPI INITIALIZATION & ROUTERS
# ==========================================
app = FastAPI(lifespan=lifespan)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(cameras.router)
app.include_router(floor.router)
app.include_router(family.router)
app.include_router(unwanted_person.router)
app.include_router(logs.router)
app.include_router(settings.router)
app.include_router(others.router)
app.include_router(rules.router)

app.mount("/media", StaticFiles(directory="media"), name="media")
app.mount("/editor", StaticFiles(directory="static", html=True), name="editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    ai_status = "Online" if ENABLE_AI_ENGINE else "Offline"
    return {"status": "Surveillance System Online", "ai_engine": ai_status, "version": "1.0"}


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("📱 App disconnected from WebSockets.")


if __name__ == '__main__':
    uvicorn.run("main:app", host='0.0.0.0', port=8888, reload=False, lifespan="on")