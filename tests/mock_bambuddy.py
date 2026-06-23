from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
import time

app = FastAPI(title="Mock BamBot API")

@app.get("/")
def read_root():
    return {"status": "online", "service": "Mock BamBot API Server", "documentation": "/docs"}

# Simulated Printer State
class PrinterState:
    def __init__(self):
        self.state = "idle"  # idle, printing, paused, error
        self.nozzle_temp = 25.0
        self.target_nozzle_temp = 0.0
        self.bed_temp = 20.0
        self.target_bed_temp = 0.0
        self.percent_complete = 0.0
        self.active_file = ""
        self.door_state = "closed"  # open, closed
        self.spoolman_enabled = True
        
        # AMS slot mappings
        self.ams_slots = [
            {"slot": 1, "material": "PLA", "color": "#FF0000", "weight_g": 350.0},
            {"slot": 2, "material": "PETG", "color": "#00FF00", "weight_g": 850.0},
            {"slot": 3, "material": "ABS", "color": "#0000FF", "weight_g": 500.0},
            {"slot": 4, "material": "", "color": "", "weight_g": 0.0}
        ]

printer = PrinterState()

class CommandRequest(BaseModel):
    action: str  # pause, resume, cancel, start_print, heat_nozzle, heat_bed, set_door
    value: Optional[str] = None
    target_temp: Optional[float] = None

@app.get("/api/v1/printer/status")
def get_printer_status():
    # Simulate temperatures rising/cooling slowly
    if printer.nozzle_temp < printer.target_nozzle_temp:
        printer.nozzle_temp = min(printer.target_nozzle_temp, printer.nozzle_temp + 20)
    elif printer.nozzle_temp > printer.target_nozzle_temp:
        printer.nozzle_temp = max(printer.target_nozzle_temp, printer.nozzle_temp - 15)

    if printer.bed_temp < printer.target_bed_temp:
        printer.bed_temp = min(printer.target_bed_temp, printer.bed_temp + 10)
    elif printer.bed_temp > printer.target_bed_temp:
        printer.bed_temp = max(printer.target_bed_temp, printer.bed_temp - 5)

    # Progress simulation
    if printer.state == "printing":
        if printer.nozzle_temp >= 200: # Wait for heating
            printer.percent_complete = min(100.0, printer.percent_complete + 1.5)
            if printer.percent_complete >= 100.0:
                printer.state = "idle"
                printer.active_file = ""
                printer.percent_complete = 0.0

    return {
        "state": printer.state,
        "nozzle_temp": printer.nozzle_temp,
        "target_nozzle_temp": printer.target_nozzle_temp,
        "bed_temp": printer.bed_temp,
        "target_bed_temp": printer.target_bed_temp,
        "percent_complete": printer.percent_complete,
        "active_file": printer.active_file,
        "door_state": printer.door_state,
        "ams_slots": printer.ams_slots
    }

@app.post("/api/v1/printer/command")
def send_printer_command(cmd: CommandRequest):
    if cmd.action == "pause":
        if printer.state == "printing":
            printer.state = "paused"
            return {"status": "success", "message": "Print paused"}
        raise HTTPException(status_code=400, detail="Cannot pause unless printing")
        
    elif cmd.action == "resume":
        if printer.state == "paused":
            printer.state = "printing"
            return {"status": "success", "message": "Print resumed"}
        raise HTTPException(status_code=400, detail="Cannot resume unless paused")
        
    elif cmd.action == "cancel":
        if printer.state in ["printing", "paused", "error"]:
            printer.state = "idle"
            printer.active_file = ""
            printer.percent_complete = 0.0
            printer.target_nozzle_temp = 0.0
            printer.target_bed_temp = 0.0
            return {"status": "success", "message": "Print cancelled"}
        raise HTTPException(status_code=400, detail="Nothing to cancel")
        
    elif cmd.action == "start_print":
        if not cmd.value:
            raise HTTPException(status_code=400, detail="Missing file name")
        printer.state = "printing"
        printer.active_file = cmd.value
        printer.percent_complete = 0.0
        printer.target_nozzle_temp = 220.0
        printer.target_bed_temp = 55.0
        return {"status": "success", "message": f"Started print job for {cmd.value}"}
        
    elif cmd.action == "heat_nozzle":
        if cmd.target_temp is None:
            raise HTTPException(status_code=400, detail="Missing target temperature")
        printer.target_nozzle_temp = cmd.target_temp
        return {"status": "success", "message": f"Set target nozzle temperature to {cmd.target_temp}"}
        
    elif cmd.action == "heat_bed":
        if cmd.target_temp is None:
            raise HTTPException(status_code=400, detail="Missing target temperature")
        printer.target_bed_temp = cmd.target_temp
        return {"status": "success", "message": f"Set target bed temperature to {cmd.target_temp}"}

    elif cmd.action == "set_door":
        if cmd.value not in ["open", "closed"]:
            raise HTTPException(status_code=400, detail="Door state must be open or closed")
        printer.door_state = cmd.value
        return {"status": "success", "message": f"Door is now {cmd.value}"}
        
    raise HTTPException(status_code=400, detail="Unknown command")

@app.get("/api/v1/gcode/files")
def list_gcode_files():
    return [
        {"name": "benchy_pla_red.gcode", "size": "4.5MB", "estimated_time": "45m", "filament_required_g": 18.5},
        {"name": "organizer_petg_green.gcode", "size": "15.2MB", "estimated_time": "3h 15m", "filament_required_g": 120.0},
        {"name": "spool_holder_abs_blue.gcode", "size": "22.1MB", "estimated_time": "5h 45m", "filament_required_g": 240.0},
        {"name": "cube.stl", "size": "0.5MB", "estimated_time": "Unknown", "filament_required_g": 0.0},
        {"name": "gear.3mf", "size": "1.2MB", "estimated_time": "Unknown", "filament_required_g": 0.0}
    ]

@app.get("/api/v1/inventory/spools")
def get_spoolman_inventory():
    if not printer.spoolman_enabled:
        raise HTTPException(status_code=404, detail="Spoolman integration disabled")
    return [
        {"id": 1, "material": "PLA", "color": "#FF0000", "remaining_g": 350.0, "name": "Red PLA Spool"},
        {"id": 2, "material": "PETG", "color": "#00FF00", "remaining_g": 850.0, "name": "Green PETG Spool"},
        {"id": 3, "material": "ABS", "color": "#0000FF", "remaining_g": 90.0, "name": "Low Blue ABS Spool"} # low filament
    ]
