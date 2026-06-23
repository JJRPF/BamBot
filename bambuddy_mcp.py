import sys
import os
import subprocess
import json
import httpx
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Add root directory to python path if not present (to allow importing app module)
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.app_utils import bambuddy_client

# Create MCP Server
mcp = FastMCP("bambot")

@mcp.tool()
async def get_printer_status() -> dict:
    """
    Fetch the current status of the Bambu Lab X1C printer.
    Returns temperatures (nozzle/bed), state, current file, and AMS slots.
    """
    return await bambuddy_client.fetch_printer_status()

@mcp.tool()
async def send_printer_command(
    action: str, 
    value: Optional[str] = None, 
    target_temp: Optional[float] = None,
    ams_mapping: Optional[list[int]] = None,
    plate_id: Optional[int] = None,
    plate_name: Optional[str] = None
) -> dict:
    """
    Send a control command to the 3D printer.
    Actions: pause, resume, cancel, start_print, heat_nozzle, heat_bed, set_door.
    """
    return await bambuddy_client.execute_printer_command(
        action=action, 
        value=value, 
        target_temp=target_temp, 
        ams_mapping=ams_mapping, 
        plate_id=plate_id, 
        plate_name=plate_name
    )


@mcp.tool()
async def query_3d_printing_knowledge(query: str) -> dict:
    """
    Search the 3D printing troubleshooting and technical knowledge base.
    Returns matched solutions or FAQ answers.
    """
    data_path = os.path.join(os.path.dirname(__file__), "app", "data", "printing_knowledge.json")
    if not os.path.exists(data_path):
        return {"error": "Knowledge base data file not found."}
    
    with open(data_path, "r") as f:
        kb = json.load(f)
        
    query_lower = query.lower()
    matches = []
    # Search troubleshooting
    for item in kb.get("troubleshooting", []):
        if any(kw in query_lower for kw in item["keywords"]) or item["topic"].lower() in query_lower:
            matches.append({"type": "troubleshooting", "topic": item["topic"], "solution": item["solution"]})
            
    # Search FAQ
    for item in kb.get("faq", []):
        if item["question"].lower() in query_lower or any(w in item["question"].lower() for w in query_lower.split()):
            matches.append({"type": "faq", "question": item["question"], "answer": item["answer"]})
            
    if matches:
        return {"status": "success", "results": matches}
    
    # Fallback to general advice
    return {
        "status": "partial",
        "message": "No exact matching topics found. For general issues: 1) Ensure the build plate is clean. 2) Dry your filament. 3) Double check your bed leveling and first layer height calibration."
    }

@mcp.tool()
async def search_3d_models(query: str, site: Optional[str] = None) -> list:
    """
    Query the unified model mirror registry across Printables, MakerWorld, and Thingiverse.
    Returns model metadata, creators, descriptions, image URLs, and recommended settings.
    """
    data_path = os.path.join(os.path.dirname(__file__), "app", "data", "model_library.json")
    if not os.path.exists(data_path):
        return []
        
    with open(data_path, "r") as f:
        models = json.load(f)
        
    query_lower = query.lower()
    results = []
    for m in models:
        # Filter by site if provided
        if site and site.lower() != m["site"].lower():
            continue
            
        if query_lower in m["name"].lower() or query_lower in m["description"].lower() or query_lower in m["id"].lower():
            results.append(m)
    return results

@mcp.tool()
async def download_3d_model(model_id: str) -> dict:
    """
    Download/retrieve the physical STL file associated with a mirror registry model ID.
    """
    data_path = os.path.join(os.path.dirname(__file__), "app", "data", "model_library.json")
    if not os.path.exists(data_path):
        return {"error": "Model registry not found."}
        
    with open(data_path, "r") as f:
        models = json.load(f)
        
    for m in models:
        if m["id"] == model_id:
            local_path = os.path.join(os.path.dirname(__file__), m["local_stl_path"])
            if os.path.exists(local_path):
                return {
                    "status": "success", 
                    "model_id": model_id,
                    "filename": os.path.basename(local_path),
                    "local_path": local_path,
                    "recommended_settings": m["recommended_settings"]
                }
            return {"error": f"STL file for model {model_id} not found at {local_path}."}
            
    return {"error": f"Model ID '{model_id}' not registered in mirror registry."}

@mcp.tool()
async def slice_model_file(
    filename: str, 
    process_preset: str = "0.20mm Standard @BBL X1C", 
    filament_preset: str = "Bambu PLA Basic @BBL X1C"
) -> dict:
    """
    Run OrcaSlicer CLI on a registered STL model file to generate a G-code file.
    Presets should reside under standard macOS Application Support paths.
    """
    import json
    # Locate paths
    stl_path = os.path.join(os.path.dirname(__file__), "app", "data", "models", filename)
    if not os.path.exists(stl_path):
        stl_path = os.path.join("/tmp", filename)
        if not os.path.exists(stl_path):
            # Attempt to download from library
            downloaded_path = await bambuddy_client.download_library_file(filename)
            if downloaded_path:
                stl_path = downloaded_path
            else:
                return {"error": f"Model file '{filename}' not found in local directories or library."}
            
    import shutil
    
    # 1. Check environment variable first
    orca_path = os.getenv("ORCA_SLICER_PATH", "")
    if not orca_path or not os.path.exists(orca_path):
        # 2. Check macOS standard path
        mac_path = "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"
        if os.path.exists(mac_path):
            orca_path = mac_path
        else:
            # 3. Check system PATH (for Linux/Pi)
            which_orca = shutil.which("orcaslicer") or shutil.which("OrcaSlicer") or shutil.which("orca-slicer")
            if which_orca:
                orca_path = which_orca
            else:
                # 4. Fallback to common Linux paths
                for p in ["/usr/bin/orcaslicer", "/usr/local/bin/orcaslicer", "/usr/bin/OrcaSlicer"]:
                    if os.path.exists(p):
                        orca_path = p
                        break

    if not orca_path:
        return {"error": "OrcaSlicer installation not found. Please install OrcaSlicer and ensure it is on your PATH, or set the ORCA_SLICER_PATH environment variable."}
        
    # Locate preset JSON files dynamically based on OS
    home = os.path.expanduser("~")
    resource_dir = ""
    env_res_dir = os.getenv("ORCA_RESOURCES_DIR", "")
    if env_res_dir and os.path.exists(env_res_dir):
        resource_dir = env_res_dir
    else:
        mac_res_dir = os.path.join(home, "Library", "Application Support", "OrcaSlicer", "system", "BBL")
        linux_res_dir = os.path.join(home, ".config", "OrcaSlicer", "system", "BBL")
        linux_res_dir_lower = os.path.join(home, ".config", "orcaslicer", "system", "BBL")
        
        if os.path.exists(mac_res_dir):
            resource_dir = mac_res_dir
        elif os.path.exists(linux_res_dir):
            resource_dir = linux_res_dir
        elif os.path.exists(linux_res_dir_lower):
            resource_dir = linux_res_dir_lower
            
    if not resource_dir:
        # Fallback to macOS default if nothing found
        resource_dir = os.path.join(home, "Library", "Application Support", "OrcaSlicer", "system", "BBL")
        
    process_json = os.path.join(resource_dir, "process", f"{process_preset}.json")
    filament_json = os.path.join(resource_dir, "filament", f"{filament_preset}.json")
    machine_json = os.path.join(resource_dir, "machine", "Bambu Lab X1 Carbon 0.4 nozzle.json")
    
    if not os.path.exists(process_json):
        return {"error": f"Process preset '{process_preset}' not found in {process_json}."}
    if not os.path.exists(filament_json):
        return {"error": f"Filament preset '{filament_preset}' not found in {filament_json}."}
        
    output_dir = "/tmp"
    base_name = filename
    for ext in [".stl", ".STL", ".3mf", ".3MF"]:
        if base_name.endswith(ext):
            base_name = base_name[:-len(ext)]
            break
    target_name = base_name + "_sliced.gcode.3mf"
    
    cmd = [
        orca_path,
        "--slice", "0",
        "--outputdir", output_dir,
        "--load-settings", process_json,
        "--load-filaments", filament_json,
        "--load-settings", machine_json,
        "--export-3mf", target_name,
        stl_path
    ]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0)
        if proc.returncode != 0:
            return {"error": f"OrcaSlicer CLI error (exit code {proc.returncode}): {proc.stderr}"}
            
        # The output Gcode from OrcaSlicer is always plate_1.gcode in outputdir
        source_gcode = os.path.join(output_dir, "plate_1.gcode")
        if not os.path.exists(source_gcode):
            return {"error": "Slicing output 'plate_1.gcode' was not created by OrcaSlicer."}
            
        # Verify 3mf file was created
        source_3mf = os.path.join(output_dir, target_name)
        if not os.path.exists(source_3mf):
            return {"error": f"Slicing output '{target_name}' was not created by OrcaSlicer."}
            
        # Read the Gcode metadata (print time & filament usage)
        print_time = "Unknown"
        filament_used_g = 0.0
        
        with open(source_gcode, "r") as f:
            for _ in range(30):
                line = f.readline()
                if not line:
                    break
                if "total estimated time:" in line:
                    # ; model printing time: 4m 57s; total estimated time: 11m 31s
                    parts = line.split("total estimated time:")
                    if len(parts) > 1:
                        print_time = parts[1].strip()
                        
        # Find filament usage at the end
        with open(source_gcode, "r") as f:
            # Seek from end to read last lines
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 2000))
            tail = f.read()
            for line in tail.split("\n"):
                if "filament used [cm3]" in line:
                    # ; filament used [cm3] = 0.82
                    parts = line.split("=")
                    if len(parts) > 1:
                        try:
                            # 1 cm3 PLA is approx 1.24g
                            vol = float(parts[1].strip())
                            filament_used_g = round(vol * 1.24, 2)
                        except ValueError:
                            pass
                            
        # Now upload / copy the Gcode into BamBuddy library so it becomes available
        # Call upload endpoint locally or mock it
        dest_filename = target_name
        dest_path = source_3mf
        
        # We can perform a local upload to BamBuddy API using a multipart post or file system copy if is_real is false
        is_real, _ = await bambuddy_client.get_bambuddy_type_and_printer_id()
        if is_real:
            async with httpx.AsyncClient() as client:
                with open(source_3mf, "rb") as gf:
                    headers = bambuddy_client.get_headers()
                    response = await client.post(
                        f"{bambuddy_client.BAMBUDDY_URL}/api/v1/library/files",
                        headers=headers,
                        files={"file": (dest_filename, gf.read(), "application/octet-stream")},
                        timeout=30.0
                    )
                    if response.status_code not in [200, 201]:
                        return {"error": f"Failed to upload G-code to printer library: {response.text}"}
        else:
            # If mock, we can write a mock metadata file or simply upload mock logic
            logger.info("Mock Slicing complete. File uploaded to mock library.")
            
        return {
            "status": "success",
            "filename": dest_filename,
            "estimated_time": print_time,
            "filament_usage_g": filament_used_g,
            "settings": {
                "process_preset": process_preset,
                "filament_preset": filament_preset
            }
        }
    except Exception as e:
        return {"error": f"Failed to slice model file: {str(e)}"}

@mcp.tool()
async def list_gcode_files() -> list:
    """
    Retrieve the list of sliced G-code print files stored on the server.
    """
    return await bambuddy_client.list_gcode_files()

@mcp.tool()
async def get_spoolman_inventory() -> list:
    """
    Retrieve filament inventory from Spoolman.
    Returns a list of spools, remaining weights, colors, and materials.
    Returns an empty list if Spoolman is not configured or fails.
    """
    return await bambuddy_client.get_spoolman_inventory()

@mcp.tool()
async def run_ui_tests() -> dict:
    """
    Run automated Playwright E2E tests against the custom UI dashboard.
    This starts a test server on port 8005, runs browser checks, captures a screenshot,
    and returns a success status, output logs, and the screenshot path.
    """
    import subprocess
    test_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "tests", "integration", "test_ui.py"))
    
    # Run pytest on the test_ui.py file
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "-s", test_path],
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )
    
    success = process.returncode == 0
    return {
        "success": success,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "screenshot_path": "/Users/JJR/.gemini/antigravity/brain/1859a8d6-ea49-41e2-9afc-7a9e68e9f2ae/ui_test_screenshot.png"
    }

if __name__ == "__main__":
    mcp.run()
