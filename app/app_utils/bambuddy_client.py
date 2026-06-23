import os
import logging
from typing import Optional, List, Dict
import httpx
import dotenv

# Load environment variables using absolute path so MCP subprocesses always find .env
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.env')
dotenv.load_dotenv(_env_path)

logger = logging.getLogger("google.adk")

# Load environment configs
BAMBUDDY_URL = os.getenv("BAMBUDDY_URL", "http://localhost:8001").rstrip("/")
BAMBUDDY_API_KEY = os.getenv("BAMBUDDY_API_KEY", "")

# Cached type and ID
_is_real_bambuddy_cached = None
_printer_id_cached = 1

def set_active_printer_id(printer_id: int):
    global _printer_id_cached
    _printer_id_cached = printer_id
    logger.info(f"Active printer ID explicitly set to: {printer_id}")

def get_headers() -> dict:
    headers = {}
    if BAMBUDDY_API_KEY:
        headers["Authorization"] = f"Bearer {BAMBUDDY_API_KEY}"
    return headers

async def get_camera_stream_token() -> Optional[str]:
    """Obtain a time-limited camera stream token from BamBuddy."""
    is_real, _ = await get_bambuddy_type_and_printer_id()
    if not is_real:
        return None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BAMBUDDY_URL}/api/v1/printers/camera/stream-token",
                headers=get_headers(),
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("token")
        except Exception as e:
            logger.error(f"Failed to get camera stream token: {e}")
    return None

async def get_bambuddy_type_and_printer_id():
    global _is_real_bambuddy_cached, _printer_id_cached
    if _is_real_bambuddy_cached is not None:
        return _is_real_bambuddy_cached, _printer_id_cached

    async with httpx.AsyncClient() as client:
        try:
            # Try to query the printers list to probe if it is a real BamBuddy instance
            response = await client.get(f"{BAMBUDDY_URL}/api/v1/printers/", headers=get_headers(), timeout=2.0)
            if response.status_code == 200:
                printers = response.json()
                if printers and isinstance(printers, list):
                    _printer_id_cached = printers[0]["id"]
                _is_real_bambuddy_cached = True
                logger.info(f"Connected to real BamBuddy API on {BAMBUDDY_URL} (Printer ID: {_printer_id_cached})")
            else:
                _is_real_bambuddy_cached = False
        except Exception:
            _is_real_bambuddy_cached = False
            
    if not _is_real_bambuddy_cached:
        logger.info(f"Using mock BamBuddy API on {BAMBUDDY_URL}")
        
    return _is_real_bambuddy_cached, _printer_id_cached

async def fetch_printer_status() -> dict:
    is_real, printer_id = await get_bambuddy_type_and_printer_id()
    async with httpx.AsyncClient() as client:
        try:
            if is_real:
                response = await client.get(f"{BAMBUDDY_URL}/api/v1/printers/{printer_id}/status", headers=get_headers(), timeout=5.0)
                if response.status_code == 200:
                    raw = response.json()
                    
                    # Normalize real BamBuddy response to mock schema format
                    state = (raw.get("state") or "idle").lower()
                    temps = raw.get("temperatures") or {}
                    
                    ams_slots = []
                    ams_list = raw.get("ams") or []
                    if ams_list:
                        for tray in ams_list[0].get("tray") or []:
                            # Convert remain % to grams (estimate 1000g spool)
                            remain_g = float(tray.get("remain") or 0.0) * 10.0
                            color_hex = tray.get("tray_color") or ""
                            if color_hex:
                                color_hex = "#" + color_hex.lstrip("#")[:6]
                            ams_slots.append({
                                "slot": tray.get("id", 0) + 1,
                                "material": tray.get("tray_type") or "",
                                "color": color_hex,
                                "weight_g": remain_g
                            })
                    else:
                        ams_slots = [
                            {"slot": 1, "material": "", "color": "", "weight_g": 0.0},
                            {"slot": 2, "material": "", "color": "", "weight_g": 0.0},
                            {"slot": 3, "material": "", "color": "", "weight_g": 0.0},
                            {"slot": 4, "material": "", "color": "", "weight_g": 0.0}
                        ]

                    return {
                        "state": state,
                        "nozzle_temp": temps.get("nozzle", 25.0),
                        "target_nozzle_temp": temps.get("nozzle_target", 0.0),
                        "bed_temp": temps.get("bed", 20.0),
                        "target_bed_temp": temps.get("bed_target", 0.0),
                        "percent_complete": raw.get("progress", 0.0),
                        "active_file": raw.get("gcode_file") or "",
                        "door_state": "open" if raw.get("door_open") else "closed",
                        "ams_slots": ams_slots
                    }
                return {"error": f"API returned status {response.status_code}"}
            else:
                response = await client.get(f"{BAMBUDDY_URL}/api/v1/printer/status", headers=get_headers(), timeout=5.0)
                if response.status_code == 200:
                    return response.json()
                return {"error": f"API returned status {response.status_code}"}
        except Exception as e:
            return {"error": f"Failed to connect to BamBot: {str(e)}"}

async def get_library_file_id_by_name(filename: str) -> Optional[int]:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BAMBUDDY_URL}/api/v1/library/files", headers=get_headers(), timeout=5.0)
            if response.status_code == 200:
                files = response.json()
                for f in files:
                    if f.get("filename") == filename:
                        return f.get("id")
        except Exception as e:
            logger.error(f"Error fetching library file ID by name: {e}")
    return None

async def download_library_file(filename: str) -> Optional[str]:
    is_real, _ = await get_bambuddy_type_and_printer_id()
    if not is_real:
        local_path = os.path.join(os.path.dirname(__file__), "..", "data", "models", filename)
        if os.path.exists(local_path):
            return local_path
        tmp_path = os.path.join("/tmp", filename)
        if os.path.exists(tmp_path):
            return tmp_path
        # Create dummy file to allow slicing in mock mode
        with open(tmp_path, "w") as f:
            f.write("dummy model content")
        return tmp_path

    file_id = await get_library_file_id_by_name(filename)
    if not file_id:
        return None

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BAMBUDDY_URL}/api/v1/library/files/{file_id}/download",
                headers=get_headers(),
                timeout=30.0
            )
            if response.status_code == 200:
                tmp_path = os.path.join("/tmp", filename)
                with open(tmp_path, "wb") as f:
                    f.write(response.content)
                return tmp_path
        except Exception as e:
            logger.error(f"Error downloading library file: {e}")
    return None

async def get_library_file_requirements(filename: str) -> dict:
    is_real, _ = await get_bambuddy_type_and_printer_id()
    if not is_real:
        material = "PLA"
        color = "#FFFFFF"
        if "abs" in filename.lower():
            material = "ABS"
            color = "#0000FF"
        elif "petg" in filename.lower():
            material = "PETG"
            color = "#00FF00"
        return {
            "requested_filaments": [{"slot_id": 1, "type": material, "color": color, "used_grams": 15.0}],
            "requested_bed_plate": "Textured PEI Plate",
            "plate_id": 1,
            "plate_name": "Plate 1",
            "print_time": "45m",
            "filament_weight": 15.0
        }

    # Retrieve file object from the list to get estimated print time & weight
    file_obj = None
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BAMBUDDY_URL}/api/v1/library/files", headers=get_headers(), timeout=5.0)
            if response.status_code == 200:
                files = response.json()
                for f in files:
                    if f.get("filename") == filename:
                        file_obj = f
                        break
        except Exception as e:
            logger.error(f"Error fetching library files for requirements: {e}")

    if not file_obj:
        return {}

    file_id = file_obj.get("id")
    
    # Parse estimated time and filament usage
    sec = file_obj.get("print_time_seconds")
    if sec:
        hrs = int(sec // 3600)
        mins = int((sec % 3600) // 60)
        est_time = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"
    else:
        est_time = "Unknown"
    filament_used_g = round(file_obj.get("filament_used_grams") or 0.0, 1)

    requested_filaments = []
    requested_bed_plate = "Textured PEI Plate"
    plate_id = 1
    plate_name = "Plate 1"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BAMBUDDY_URL}/api/v1/library/files/{file_id}/plates", headers=get_headers(), timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                plates = data.get("plates") or []
                requested_bed_plate = data.get("source_printer_model") or data.get("bed_type") or "Textured PEI Plate"
                if plates:
                    plate = plates[0]
                    plate_id = plate.get("index") or 1
                    plate_name = plate.get("name") or "Plate 1"
                    for f in plate.get("filaments") or []:
                        requested_filaments.append({
                            "slot_id": f.get("slot_id"),
                            "type": f.get("type"),
                            "color": f.get("color"),
                            "used_grams": f.get("used_grams")
                        })
        except Exception as e:
            logger.error(f"Error getting file requirements: {e}")

    # Fallback/Default requested filament if none is parsed so select dropdown always renders
    if not requested_filaments:
        material = "PLA"
        color = "#FFFFFF"
        if "abs" in filename.lower():
            material = "ABS"
            color = "#0000FF"
        elif "petg" in filename.lower():
            material = "PETG"
            color = "#00FF00"
        requested_filaments.append({
            "slot_id": 1,
            "type": material,
            "color": color,
            "used_grams": filament_used_g or 15.0
        })

    return {
        "requested_filaments": requested_filaments,
        "requested_bed_plate": requested_bed_plate,
        "plate_id": plate_id,
        "plate_name": plate_name,
        "print_time": est_time,
        "filament_weight": filament_used_g or 15.0
    }

async def execute_printer_command(
    action: str, 
    value: Optional[str] = None, 
    target_temp: Optional[float] = None,
    ams_mapping: Optional[list] = None,
    plate_id: Optional[int] = None,
    plate_name: Optional[str] = None
) -> dict:
    is_real, printer_id = await get_bambuddy_type_and_printer_id()
    if is_real:
        async with httpx.AsyncClient() as client:
            try:
                if action == "pause":
                    response = await client.post(f"{BAMBUDDY_URL}/api/v1/printers/{printer_id}/print/pause", headers=get_headers(), timeout=5.0)
                    return response.json() if response.status_code == 200 else {"status": "error", "error": f"Failed to pause: {response.text}"}
                elif action == "resume":
                    response = await client.post(f"{BAMBUDDY_URL}/api/v1/printers/{printer_id}/print/resume", headers=get_headers(), timeout=5.0)
                    return response.json() if response.status_code == 200 else {"status": "error", "error": f"Failed to resume: {response.text}"}
                elif action in ["cancel", "stop"]:
                    response = await client.post(f"{BAMBUDDY_URL}/api/v1/printers/{printer_id}/print/stop", headers=get_headers(), timeout=5.0)
                    return response.json() if response.status_code == 200 else {"status": "error", "error": f"Failed to stop: {response.text}"}
                elif action == "start_print":
                    file_id = await get_library_file_id_by_name(value)
                    if not file_id:
                        return {"status": "error", "error": f"Gcode file '{value}' not found in print library."}
                    payload = {
                        "plate_id": plate_id,
                        "plate_name": plate_name,
                        "ams_mapping": ams_mapping,
                        "use_ams": ams_mapping is not None and len(ams_mapping) > 0,
                        "bed_levelling": True,
                        "flow_cali": False,
                        "vibration_cali": True
                    }
                    response = await client.post(
                        f"{BAMBUDDY_URL}/api/v1/library/files/{file_id}/print?printer_id={printer_id}",
                        json=payload,
                        headers=get_headers(),
                        timeout=10.0
                    )
                    if response.status_code in [200, 201]:
                        return {"status": "success", "message": f"Started print job for file '{value}'."}
                    else:
                        return {"status": "error", "error": f"Failed to start print: {response.text}"}
                elif action in ["heat_nozzle", "heat_bed"]:
                    return {"status": "error", "error": f"Direct heating command '{action}' is not supported on the real printer; please configure temperatures in your slicer or print queue."}
                elif action == "set_door":
                    return {"status": "error", "error": "The printer door state is read-only and cannot be set programmatically."}
                else:
                    return {"status": "error", "error": f"Unsupported action: {action}"}
            except Exception as e:
                return {"status": "error", "error": f"Failed to send command to BamBuddy: {str(e)}"}
    else:
        async with httpx.AsyncClient() as client:
            payload = {
                "action": action,
                "value": value,
                "target_temp": target_temp,
                "ams_mapping": ams_mapping,
                "plate_id": plate_id,
                "plate_name": plate_name
            }
            try:
                response = await client.post(
                    f"{BAMBUDDY_URL}/api/v1/printer/command", 
                    json=payload, 
                    headers=get_headers(), 
                    timeout=5.0
                )
                return response.json()
            except Exception as e:
                return {"error": f"Failed to send command to BamBuddy: {str(e)}"}

async def list_gcode_files() -> list:
    is_real, printer_id = await get_bambuddy_type_and_printer_id()
    async with httpx.AsyncClient() as client:
        try:
            if is_real:
                response = await client.get(f"{BAMBUDDY_URL}/api/v1/library/files", headers=get_headers(), timeout=5.0)
                if response.status_code == 200:
                    files = response.json()
                    normalized = []
                    for f in files:
                        if f.get("file_type") in ["gcode", "3mf", "stl", "STL"]:
                            size_mb = round((f.get("file_size") or 0) / (1024 * 1024), 1)
                            sec = f.get("print_time_seconds")
                            if sec:
                                hrs = int(sec // 3600)
                                mins = int((sec % 3600) // 60)
                                est_time = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"
                            else:
                                est_time = "Unknown"
                            normalized.append({
                                "id": f.get("id"),
                                "name": f.get("filename"),
                                "size": f"{size_mb}MB" if size_mb > 0 else "0.1MB",
                                "estimated_time": est_time,
                                "filament_required_g": round(f.get("filament_used_grams") or 0.0, 1)
                            })
                    return normalized
                return []
            else:
                response = await client.get(f"{BAMBUDDY_URL}/api/v1/gcode/files", headers=get_headers(), timeout=5.0)
                if response.status_code == 200:
                    return response.json()
                return []
        except Exception:
            return []


async def get_spoolman_inventory() -> list:
    is_real, printer_id = await get_bambuddy_type_and_printer_id()
    async with httpx.AsyncClient() as client:
        try:
            if is_real:
                response = await client.get(f"{BAMBUDDY_URL}/api/v1/spoolman/inventory/spools", headers=get_headers(), timeout=3.0)
                if response.status_code == 200:
                    spools = response.json()
                    normalized = []
                    for sp in spools:
                        filament = sp.get("filament") or {}
                        normalized.append({
                            "id": sp.get("id"),
                            "material": filament.get("material") or "",
                            "color": "#" + (filament.get("color_hex") or "").lstrip("#")[:6] if filament.get("color_hex") else "",
                            "remaining_g": sp.get("remaining_weight") or 0.0,
                            "name": sp.get("name") or filament.get("name") or "Spool"
                        })
                    return normalized
                return []
            else:
                response = await client.get(f"{BAMBUDDY_URL}/api/v1/inventory/spools", headers=get_headers(), timeout=3.0)
                if response.status_code == 200:
                    return response.json()
                return []
        except Exception:
            return []
