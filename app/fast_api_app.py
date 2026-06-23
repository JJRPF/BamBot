# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import json
import sqlite3
import asyncio
import logging
from typing import Set, Optional, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
import dotenv

# Load environment variables
dotenv.load_dotenv()
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

import google.auth
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from google.cloud import logging as google_cloud_logging

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback
from app.app_utils import bambuddy_client
from app.agent import root_agent, SESSION_METRICS, SAFETY_APPROVALS

# Setup logging
setup_telemetry()
logger = logging.getLogger("app")

if os.getenv("INTEGRATION_TEST") == "TRUE":
    DB_PATH = "bambot_agent_test.db"
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
else:
    DB_PATH = "bambot_agent.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        text TEXT,
        thoughts TEXT,
        session_id TEXT DEFAULT 's1',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        session_id TEXT PRIMARY KEY,
        title TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN session_id TEXT DEFAULT 's1'")
    except sqlite3.OperationalError:
        pass
    cursor.execute("INSERT OR IGNORE INTO chat_sessions (session_id, title) VALUES ('s1', 'Default Chat')")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state TEXT,
        nozzle_temp REAL,
        bed_temp REAL,
        percent_complete REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

init_db()

allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
session_service_uri = None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=False,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
)

app.title = "capstone"
app.description = "API for interacting with the Agent capstone"

# Telemetry WebSocket client manager
telemetry_clients: Set[WebSocket] = set()
telemetry_loop_task = None

def ensure_telemetry_loop_started():
    global telemetry_loop_task
    if telemetry_loop_task is None or telemetry_loop_task.done():
        print("[Startup] Lazily starting telemetry poll loop task.", flush=True)
        telemetry_loop_task = asyncio.create_task(poll_telemetry_loop())

class SafetyConfirmRequest(BaseModel):
    bed_cleared: bool
    door_closed: bool
    filament_verified: bool

@app.post("/api/safety/confirm")
def confirm_safety_checklist(req: SafetyConfirmRequest):
    SAFETY_APPROVALS["bed_cleared"] = req.bed_cleared
    SAFETY_APPROVALS["door_closed"] = req.door_closed
    SAFETY_APPROVALS["filament_verified"] = req.filament_verified
    logger.info(f"Safety Checklist confirmed: {SAFETY_APPROVALS}")
    return {"status": "success", "safety_state": SAFETY_APPROVALS}

class PrinterCommandRequest(BaseModel):
    action: str
    value: Optional[str] = None
    target_temp: Optional[float] = None
    ams_mapping: Optional[List[int]] = None
    plate_id: Optional[int] = None
    plate_name: Optional[str] = None

@app.get("/api/printers")
async def get_printers():
    is_real, active_id = await bambuddy_client.get_bambuddy_type_and_printer_id()
    async with httpx.AsyncClient() as client:
        try:
            if is_real:
                response = await client.get(
                    f"{bambuddy_client.BAMBUDDY_URL}/api/v1/printers/",
                    headers=bambuddy_client.get_headers(),
                    timeout=5.0
                )
                if response.status_code == 200:
                    printers = response.json()
                    detailed_printers = []
                    for p in printers:
                        p_id = p["id"]
                        status_data = {}
                        try:
                            status_resp = await client.get(
                                f"{bambuddy_client.BAMBUDDY_URL}/api/v1/printers/{p_id}/status",
                                headers=bambuddy_client.get_headers(),
                                timeout=2.0
                            )
                            if status_resp.status_code == 200:
                                status_data = status_resp.json()
                        except Exception as status_err:
                            logger.error(f"Failed to fetch status for printer {p_id}: {status_err}")
                        
                        temps = status_data.get("temperatures") or {}
                        detailed_printers.append({
                            "id": p_id,
                            "name": p.get("name"),
                            "model": p.get("model") or "X1C",
                            "state": (status_data.get("state") or "offline").lower(),
                            "nozzle_temp": temps.get("nozzle", 25.0),
                            "bed_temp": temps.get("bed", 20.0),
                            "percent_complete": status_data.get("progress", 0.0),
                            "is_active": p_id == active_id
                        })
                    return {"is_real": True, "printers": detailed_printers}
            
            # If not real, return mock printers
            return {
                "is_real": False,
                "printers": [
                    {
                        "id": 1,
                        "name": "Simulated X1-CARBON",
                        "model": "X1C",
                        "state": (await bambuddy_client.fetch_printer_status()).get("state", "idle"),
                        "nozzle_temp": (await bambuddy_client.fetch_printer_status()).get("nozzle_temp", 25.0),
                        "bed_temp": (await bambuddy_client.fetch_printer_status()).get("bed_temp", 20.0),
                        "percent_complete": (await bambuddy_client.fetch_printer_status()).get("percent_complete", 0.0),
                        "is_active": True
                    }
                ]
            }
        except Exception as e:
            logger.error(f"Failed to fetch printers list: {e}")
            return {
                "is_real": False,
                "printers": [
                    {
                        "id": 1,
                        "name": "Simulated X1-CARBON",
                        "model": "X1C",
                        "state": "idle",
                        "nozzle_temp": 25.0,
                        "bed_temp": 20.0,
                        "percent_complete": 0.0,
                        "is_active": True
                    }
                ]
            }

@app.post("/api/printers/{printer_id}/select")
async def select_active_printer(printer_id: int):
    try:
        bambuddy_client.set_active_printer_id(printer_id)
        status = await bambuddy_client.fetch_printer_status()
        return {"status": "success", "active_printer_id": printer_id, "printer_status": status}
    except Exception as e:
        logger.error(f"Failed to select active printer: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/printers/{printer_id}/camera/stream")
async def proxy_camera_stream(printer_id: int):
    is_real, _ = await bambuddy_client.get_bambuddy_type_and_printer_id()
    if not is_real:
        async def mock_stream_generator():
            import io
            import math
            from PIL import Image, ImageDraw
            frame_idx = 0
            while True:
                img = Image.new("RGB", (640, 480), color=(20, 20, 20))
                draw = ImageDraw.Draw(img)
                
                # Draw grid lines representing bed
                for i in range(100, 600, 80):
                    draw.line([(i, 120), (i, 400)], fill=(45, 45, 45), width=1)
                for j in range(120, 420, 60):
                    draw.line([(100, j), (540, j)], fill=(45, 45, 45), width=1)
                    
                # Draw print bed borders
                draw.rectangle([100, 120, 540, 400], outline=(70, 70, 70), width=3)
                
                status_data = {}
                try:
                    status_data = await bambuddy_client.fetch_printer_status()
                except Exception:
                    pass
                    
                state = status_data.get("state", "idle").lower()
                progress = status_data.get("percent_complete", 0.0)
                nozzle_temp = status_data.get("nozzle_temp", 25.0)
                bed_temp = status_data.get("bed_temp", 20.0)
                active_file = status_data.get("active_file", "")
                
                if state == "printing":
                    progress_factor = progress / 100.0
                    h = int(100 * progress_factor)
                    draw.rectangle([250, 300 - h, 390, 300], fill=(255, 120, 0), outline=(255, 180, 50), width=2)
                    
                    theta = frame_idx * 0.5
                    tx = 320 + int((60 * progress_factor + 20) * math.cos(theta))
                    ty = 250 + int((30 * progress_factor + 10) * math.sin(theta)) - h
                    
                    draw.line([(tx, 50), (tx, ty - 10)], fill=(120, 120, 120), width=4)
                    draw.rectangle([tx - 15, ty - 10, tx + 15, ty + 10], fill=(0, 200, 180), outline=(0, 255, 220), width=2)
                    draw.polygon([(tx - 4, ty + 10), (tx + 4, ty + 10), (tx, ty + 18)], fill=(220, 50, 50))
                    draw.line([(tx, ty + 10), (tx, ty + 15)], fill=(255, 180, 0), width=2)
                else:
                    tx, ty = 120, 120
                    draw.line([(tx, 50), (tx, ty - 10)], fill=(120, 120, 120), width=4)
                    draw.rectangle([tx - 15, ty - 10, tx + 15, ty + 10], fill=(60, 60, 60), outline=(80, 80, 80), width=2)
                    draw.polygon([(tx - 4, ty + 10), (tx + 4, ty + 10), (tx, ty + 18)], fill=(100, 100, 100))
                    
                draw.text((20, 20), f"BAMBU LAB X1C - PRINTER {printer_id}", fill=(255, 255, 255))
                draw.text((20, 40), f"STATE: {state.upper()}", fill=(0, 255, 180) if state == "printing" else (200, 200, 200))
                draw.text((20, 60), f"PROGRESS: {progress:.1f}%", fill=(255, 185, 95))
                draw.text((20, 80), f"FILE: {active_file or 'NONE'}", fill=(200, 200, 200))
                draw.text((20, 100), f"NOZZLE: {nozzle_temp:.1f}C | BED: {bed_temp:.1f}C", fill=(255, 100, 100))
                
                if state == "printing" and (frame_idx % 10 < 5):
                    draw.ellipse([600, 20, 615, 35], fill=(255, 0, 0))
                    
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                jpeg_bytes = buf.getvalue()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
                frame_idx += 1
                await asyncio.sleep(0.2)
                
        return StreamingResponse(mock_stream_generator(), media_type="multipart/x-mixed-replace; boundary=frame")
        
    # Obtain a time-limited stream token for camera access
    stream_token = await bambuddy_client.get_camera_stream_token()
    if not stream_token:
        return JSONResponse({"error": "Failed to obtain camera stream token"}, status_code=502)
    
    client = httpx.AsyncClient()
    stream_url = f"{bambuddy_client.BAMBUDDY_URL}/api/v1/printers/{printer_id}/camera/stream?token={stream_token}"
    
    async def stream_generator():
        try:
            async with client.stream("GET", stream_url, timeout=60.0) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk
        except Exception as e:
            logger.error(f"Error streaming camera: {e}")
        finally:
            await client.aclose()
            
    return StreamingResponse(stream_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/api/library/upload")
async def upload_library_file(file: UploadFile = File(...)):
    is_real, _ = await bambuddy_client.get_bambuddy_type_and_printer_id()
    if is_real:
        async with httpx.AsyncClient() as client:
            try:
                file_content = await file.read()
                files = {"file": (file.filename, file_content, file.content_type)}
                headers = bambuddy_client.get_headers()
                
                response = await client.post(
                    f"{bambuddy_client.BAMBUDDY_URL}/api/v1/library/files",
                    headers=headers,
                    files=files,
                    timeout=30.0
                )
                if response.status_code in [200, 201]:
                    return response.json()
                else:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
            except Exception as e:
                logger.error(f"Failed to upload file to real BamBuddy: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to upload file to real BamBuddy: {str(e)}")
    else:
        logger.info(f"Mock file upload received: {file.filename}")
        return {"status": "success", "message": f"Successfully uploaded mock file: {file.filename}"}

@app.get("/api/files")
async def get_files():
    try:
        files = await bambuddy_client.list_gcode_files()
        return files
    except Exception as e:
        logger.error(f"Failed to list gcode files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inventory")
async def get_inventory():
    try:
        inventory = await bambuddy_client.get_spoolman_inventory()
        return inventory
    except Exception as e:
        logger.error(f"Failed to get spoolman inventory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/printer/command")
async def printer_command(req: PrinterCommandRequest):
    try:
        res = await bambuddy_client.execute_printer_command(
            action=req.action,
            value=req.value,
            target_temp=req.target_temp,
            ams_mapping=req.ams_mapping,
            plate_id=req.plate_id,
            plate_name=req.plate_name
        )
        if "error" in res:
            raise HTTPException(status_code=400, detail=res["error"])
        return res
    except Exception as e:
        logger.error(f"Failed to execute printer command: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files/{filename}/requirements")
async def get_file_requirements(filename: str):
    try:
        reqs = await bambuddy_client.get_library_file_requirements(filename)
        return reqs
    except Exception as e:
        logger.error(f"Failed to get file requirements: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# # Shared Session Service to persist history across WebSocket reconnects
chat_session_service = InMemorySessionService()

@app.get("/api/chat/sessions")
def get_chat_sessions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT session_id, title, created_at FROM chat_sessions ORDER BY created_at DESC")
    sessions = [{"session_id": r[0], "title": r[1], "created_at": r[2]} for r in cursor.fetchall()]
    conn.close()
    return sessions

class CreateSessionRequest(BaseModel):
    title: Optional[str] = None

@app.post("/api/chat/sessions")
def create_chat_session(req: CreateSessionRequest):
    import uuid
    session_id = f"session_{uuid.uuid4().hex[:8]}"
    title = req.title or f"Chat {session_id.split('_')[1]}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_sessions (session_id, title) VALUES (?, ?)", (session_id, title))
    conn.commit()
    conn.close()
    return {"status": "success", "session_id": session_id, "title": title}

@app.delete("/api/chat/sessions/{session_id}")
def delete_chat_session(session_id: str):
    if session_id == "s1":
        raise HTTPException(status_code=400, detail="Cannot delete default session.")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Deleted session {session_id}"}

# WebSocket for Bidirectional Chat Loop (ADK Runner)
@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket, session_id: str = "s1"):
    await websocket.accept()
    ensure_telemetry_loop_started()
    logger.info(f"Chat WebSocket connected for session: {session_id}")
    
    # Send historical messages to client
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, text, thoughts FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
    history = cursor.fetchall()
    conn.close()
    
    for sender, text, thoughts in history:
        await websocket.send_json({
            "type": "history",
            "sender": sender,
            "text": text,
            "thoughts": thoughts
        })

    session = await chat_session_service.get_session(app_name="app", user_id="user", session_id=session_id)
    if not session:
        await chat_session_service.create_session(app_name="app", user_id="user", session_id=session_id)
        
    runner = Runner(agent=root_agent, app_name="app", session_service=chat_session_service)

    try:
        while True:
            # Receive user prompt
            data = await websocket.receive_text()
            try:
                user_data = json.loads(data)
                msg_type = user_data.get("type", "message")
            except Exception:
                user_data = {}
                msg_type = "message"

            if msg_type == "hitl_response":
                interrupt_id = user_data.get("interrupt_id")
                response_val = user_data.get("response")
                
                # Construct Part representing FunctionResponse
                part = genai_types.Part(
                    function_response=genai_types.FunctionResponse(
                        id=interrupt_id,
                        name="adk_request_input",
                        response=response_val
                    )
                )
                new_message = genai_types.Content(role="user", parts=[part])
                prompt = f"[Safety Confirmation: {interrupt_id}]"
            else:
                prompt = user_data.get("text", "")
                if not prompt:
                    continue
                new_message = genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt)])

            # Save user message/action to database (skip technical confirmations in history for cleaner UI)
            if msg_type != "hitl_response":
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO messages (sender, text, thoughts, session_id) VALUES (?, ?, ?, ?)", ("user", prompt, "", session_id))
                conn.commit()
                conn.close()

                # Broadcast user message immediately
                await websocket.send_json({
                    "type": "message",
                    "sender": "user",
                    "text": prompt,
                    "thoughts": ""
                })

            # Send typing status
            await websocket.send_json({"type": "status", "status": "thinking"})

            # Run ADK Agent Turn
            try:
                response_text = ""
                thoughts = ""
                is_interrupted = False
                
                # Stream agent execution events
                async for event in runner.run_async(
                    user_id="user",
                    session_id=session_id,
                    new_message=new_message
                ):
                    # Capture reasoning thoughts (excluding final text)
                    if hasattr(event, "thoughts") and event.thoughts:
                        thoughts += event.thoughts
                    
                    # Detect HITL interrupt
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.function_call and part.function_call.name == "adk_request_input":
                                is_interrupted = True
                                interrupt_id = part.function_call.id
                                message = part.function_call.args.get("message", "")
                                payload_arg = part.function_call.args.get("payload")
                                
                                # Send HITL request to client
                                await websocket.send_json({
                                    "type": "hitl_request",
                                    "interrupt_id": interrupt_id,
                                    "message": message,
                                    "payload": payload_arg
                                })

                    if event.content and event.content.parts:
                        # Skip accumulating the structured action JSON from printer_agent
                        node_name = event.node_info.name if event.node_info else ""
                        if node_name != "printer_agent":
                            for part in event.content.parts:
                                if part.text:
                                    response_text += part.text

                if is_interrupted:
                    await websocket.send_json({"type": "status", "status": "idle"})
                    continue

                # If no response text was generated (e.g. tool execution stalled/blocked)
                if not response_text:
                    response_text = "Completed safety processing."

                # Get session metrics
                session_obj = await runner.session_service.get_session(app_name="app", user_id="user", session_id=session_id) if hasattr(runner, "session_service") else None
                if session_obj and session_obj.events:
                    usage = None
                    for event in reversed(session_obj.events):
                        if hasattr(event, "usage_metadata") and event.usage_metadata:
                            usage = event.usage_metadata
                            break
                    if usage:
                        SESSION_METRICS["prompt_tokens"] = usage.prompt_token_count or 0
                        SESSION_METRICS["candidates_tokens"] = usage.candidates_token_count or 0
                        SESSION_METRICS["thinking_tokens"] = usage.thoughts_token_count or 0
                        SESSION_METRICS["total_tokens"] = usage.total_token_count or 0
                        
                        cost_input = (SESSION_METRICS["prompt_tokens"] / 1000000.0) * 0.075
                        cost_output = ((SESSION_METRICS["candidates_tokens"] + SESSION_METRICS["thinking_tokens"]) / 1000000.0) * 0.30
                        SESSION_METRICS["estimated_cost_usd"] = round(cost_input + cost_output, 6)

                # Save agent message to database
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO messages (sender, text, thoughts, session_id) VALUES (?, ?, ?, ?)", ("agent", response_text, thoughts, session_id))
                conn.commit()
                conn.close()

                # Send response to client
                await websocket.send_json({
                    "type": "message",
                    "sender": "agent",
                    "text": response_text,
                    "thoughts": thoughts,
                    "metrics": SESSION_METRICS,
                    "safety_state": SAFETY_APPROVALS
                })
            except WebSocketDisconnect:
                logger.info("Chat WebSocket disconnected during agent turn.")
                break
            except Exception as e:
                logger.error(f"Error in agent turn: {e}")
                await send_telegram_alert(f"Printer Agent Error: encountered exception in execution loop: {str(e)}")
                try:
                    await websocket.send_json({
                        "type": "message",
                        "sender": "agent",
                        "text": f"Error running printer agent loop: {str(e)}",
                        "thoughts": "Failed to invoke ADK Runner."
                    })
                except Exception:
                    pass
            
            try:
                await websocket.send_json({"type": "status", "status": "idle"})
            except Exception:
                pass
            
    except WebSocketDisconnect:
        logger.info("Chat WebSocket disconnected.")

# WebSocket for Downstream Telemetry Streaming
@app.websocket("/ws/telemetry")
async def telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    telemetry_clients.add(websocket)
    ensure_telemetry_loop_started()
    print(f"[WS] Telemetry client connected. Active: {len(telemetry_clients)}", flush=True)
    logger.info(f"Telemetry client connected. Active: {len(telemetry_clients)}")
    try:
        while True:
            # WebSocket needs to keep-alive or receive/wait
            await websocket.receive_text()
    except WebSocketDisconnect:
        telemetry_clients.remove(websocket)
        logger.info(f"Telemetry client disconnected. Active: {len(telemetry_clients)}")

# Background task to poll printer telemetry and broadcast to WebSockets
async def poll_telemetry_loop():
    print("[Telemetry] Telemetry loop started!", flush=True)
    BAMBUDDY_URL = os.getenv("BAMBUDDY_URL", "http://localhost:8001").rstrip("/")
    while True:
        await asyncio.sleep(1.0)
        # print(f"[Telemetry] Polling iteration. Active clients: {len(telemetry_clients)}", flush=True)
        if not telemetry_clients:
            continue
            
        try:
            status_data = await bambuddy_client.fetch_printer_status()
            if "error" not in status_data:
                # Log telemetry to SQLite database for graphing history
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO telemetry_logs (state, nozzle_temp, bed_temp, percent_complete) VALUES (?, ?, ?, ?)",
                        (status_data["state"], status_data["nozzle_temp"], status_data["bed_temp"], status_data["percent_complete"])
                    )
                    conn.commit()
                    conn.close()
                except Exception as db_err:
                    logger.error(f"Failed to log telemetry to database: {db_err}")

                # Broadcast to all connected WebSocket clients
                for ws in list(telemetry_clients):
                    try:
                        await ws.send_json({
                            "type": "telemetry",
                            "data": status_data
                        })
                    except Exception:
                        telemetry_clients.remove(ws)
            else:
                for ws in list(telemetry_clients):
                    try:
                        await ws.send_json({
                            "type": "telemetry_error",
                            "message": status_data["error"]
                        })
                    except Exception:
                        telemetry_clients.remove(ws)
        except Exception as e:
            logger.exception("Exception in poll_telemetry_loop background task")
            # Broadcast error to all connected WebSocket clients
            for ws in list(telemetry_clients):
                try:
                    await ws.send_json({
                        "type": "telemetry_error",
                        "message": f"Could not connect to BamBuddy on {BAMBUDDY_URL}: {str(e)}"
                    })
                except Exception:
                    telemetry_clients.remove(ws)

# In-memory track of the active runner session for Telegram
telegram_session_service = InMemorySessionService()
telegram_runner = None

# Track if the current request is from Telegram or Web Chat
from contextvars import ContextVar
current_request_source = ContextVar("current_request_source", default="web")

async def get_telegram_runner():
    global telegram_runner
    if telegram_runner is None:
        await telegram_session_service.create_session(app_name="app", user_id="telegram_user", session_id="tg_s1")
        telegram_runner = Runner(agent=root_agent, app_name="app", session_service=telegram_session_service)
    return telegram_runner

# Keep track of last processed telegram update ID
last_update_id = 0

async def poll_telegram_messages():
    global last_update_id
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping Telegram listener.")
        return
        
    logger.info("Starting Telegram Bot listener loop.")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # get updates
                url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
                params = {"offset": last_update_id + 1, "timeout": 10}
                response = await client.get(url, params=params, timeout=15.0)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok") and data.get("result"):
                        for update in data["result"]:
                            last_update_id = update["update_id"]
                            message = update.get("message")
                            if not message:
                                continue
                            chat_id = message["chat"]["id"]
                            text = message.get("text", "")
                            if not text:
                                continue
                                
                            # Save user message to database
                            conn = sqlite3.connect(DB_PATH)
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO messages (sender, text, thoughts) VALUES (?, ?, ?)", ("user", text, ""))
                            conn.commit()
                            conn.close()

                            # Run Agent response
                            logger.info(f"Received telegram message from {chat_id}: {text}")
                            runner = await get_telegram_runner()
                            new_message = genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=text)])
                            
                            response_text = ""
                            thoughts = ""
                            
                            current_request_source.set(f"telegram:{chat_id}")
                            try:
                                async for event in runner.run_async(
                                    user_id="telegram_user",
                                    session_id="tg_s1",
                                    new_message=new_message
                                ):
                                    if hasattr(event, "thoughts") and event.thoughts:
                                        thoughts += event.thoughts
                                    if event.content and event.content.parts:
                                        node_name = event.node_info.name if event.node_info else ""
                                        if node_name != "printer_agent":
                                            for part in event.content.parts:
                                                if part.text:
                                                    response_text += part.text
                            except Exception as run_err:
                                logger.error(f"Error in telegram agent run: {run_err}")
                                response_text = f"Error processing request: {str(run_err)}"
                                
                            if not response_text:
                                response_text = "Processing complete."
                                
                            # Save agent response
                            conn = sqlite3.connect(DB_PATH)
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO messages (sender, text, thoughts) VALUES (?, ?, ?)", ("agent", response_text, thoughts))
                            conn.commit()
                            conn.close()
                            
                            # Reply to Telegram (this is a response to a prompt through Telegram)
                            await send_telegram_alert(response_text, force_chat_id=chat_id)
            except Exception as e:
                logger.error(f"Error in telegram poll loop: {e}")
            await asyncio.sleep(1.0)

# Optional Telegram notifier helper
async def send_telegram_alert(message: str, force_chat_id: Optional[int] = None):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = force_chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        async with httpx.AsyncClient() as client:
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                await client.post(url, json={"chat_id": chat_id, "text": message}, timeout=3.0)
                logger.info("Telegram notification sent successfully.")
            except Exception as e:
                logger.warning(f"Failed to send Telegram notification: {e}")

@app.on_event("startup")
async def startup_event():
    ensure_telemetry_loop_started()
    asyncio.create_task(poll_telegram_messages())
    # Start monitor task for print failures / errors to notify telegram
    asyncio.create_task(monitor_printer_failures())

# Monitor printer status in background specifically for error state / print failure alerts
async def monitor_printer_failures():
    last_state = None
    while True:
        try:
            status_data = await bambuddy_client.fetch_printer_status()
            if "error" not in status_data:
                state = (status_data.get("state") or "").lower()
                # Print fails / goes to error/failed
                if state in ["failed", "error"] and last_state not in ["failed", "error"]:
                    await send_telegram_alert(f"Printer Alert: Print job failed or encountered an error. Current state: {state.upper()}")
                last_state = state
        except Exception:
            pass
        await asyncio.sleep(5.0)

@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    return {"status": "success"}

# Mount static web portal
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# Main execution
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
