import os
import sys
import logging
import json
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent, Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext, BaseTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.genai import types as genai_types

# Workflow imports
from google.adk.workflow import Workflow, node, START, FunctionNode
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from app.app_utils import bambuddy_client

logger = logging.getLogger("google.adk")

# Global session metrics to be displayed on the dashboard
SESSION_METRICS = {
    "total_tokens": 0,
    "prompt_tokens": 0,
    "candidates_tokens": 0,
    "thinking_tokens": 0,
    "estimated_cost_usd": 0.0,
    "last_tool_latency_ms": 0,
    "trajectory": []
}

# In-memory safety state
SAFETY_APPROVALS = {
    "bed_cleared": False,
    "door_closed": False,
    "filament_verified": False
}

def reset_safety_checks():
    global SAFETY_APPROVALS
    SAFETY_APPROVALS = {
        "bed_cleared": False,
        "door_closed": False,
        "filament_verified": False
    }

# 1. Deterministic safety guardrail callback (preserved for test compatibility)
async def before_tool_callback(tool: BaseTool, args: dict, tool_context: ToolContext) -> dict | None:
    """
    Deterministic safety engine evaluating the 4 core safety guardrails before
    executing any printer command tool.
    """
    tool_name = tool.name if hasattr(tool, 'name') else tool.__class__.__name__
    logger.info(f"[SAFETY PRE-CHECK] Evaluating call to: {tool_name} with args: {args}")
    
    # Telemetry Log
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_attempt",
        "tool": tool_name,
        "args": args,
        "status": "evaluating_safety"
    })

    # Rule 1 & 2: Thermal Limits
    target_temp = args.get("target_temp")
    action = args.get("action")
    
    if target_temp is not None:
        target_temp = float(target_temp)
        if action == "heat_nozzle" and target_temp > 300.0:
            msg = f"Safety Block: Target nozzle temperature {target_temp}°C exceeds max limit of 300°C."
            logger.error(msg)
            return {"status": "error", "error": msg}
            
        if action == "heat_bed" and target_temp > 120.0:
            msg = f"Safety Block: Target bed temperature {target_temp}°C exceeds max limit of 120°C."
            logger.error(msg)
            return {"status": "error", "error": msg}

    # Rule 3: Bed Clearance check on start_print
    if action == "start_print" or tool_name == "start_print_job":
        bed_cleared = False
        if hasattr(tool_context, "state") and type(tool_context.state).__name__ != 'MagicMock':
            try:
                bed_cleared = bool(tool_context.state.get("current_print_bed_cleared", False))
            except Exception:
                pass
        if not bed_cleared:
            bed_cleared = SAFETY_APPROVALS.get("bed_cleared", False)

        if not bed_cleared:
            msg = "Safety Block: Print bed clearance has not been verified. Please ask the user to clear the bed first."
            logger.warning(msg)
            return {"status": "error", "error": msg}

    # Rule 4: Chamber Door State (Failsafe warning/reminders)
    if action == "start_print" or tool_name == "start_print_job":
        file_name = args.get("value", "")
        # Check if the file is ABS (requires closed chamber)
        if "abs" in file_name.lower() or "asa" in file_name.lower():
            door_closed = False
            if hasattr(tool_context, "state") and type(tool_context.state).__name__ != 'MagicMock':
                try:
                    door_closed = bool(tool_context.state.get("current_print_door_closed", False))
                except Exception:
                    pass
            if not door_closed:
                door_closed = SAFETY_APPROVALS.get("door_closed", False)

            if not door_closed:
                msg = f"Safety Block: Closed chamber door required for ABS/ASA print ({file_name}). Please ask the user to close the printer door."
                logger.warning(msg)
                return {"status": "error", "error": msg}

    # Allow if all policies pass
    return None

# 2. Post-tool callback for trajectory tracking (preserved for test compatibility)
async def after_tool_callback(tool: BaseTool, args: dict, tool_context: ToolContext, tool_response: dict) -> dict | None:
    tool_name = tool.name if hasattr(tool, 'name') else tool.__class__.__name__
    logger.info(f"[TELEMETRY] Tool call complete: {tool_name}")
    
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": tool_name,
        "result": str(tool_response)
    })
    return None

# Configure MCP integration using stdio transport
mcp_script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bambuddy_mcp.py"))

mcp_servers = [
    McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[mcp_script_path]
            )
        )
    )
]

# Pydantic schema for structured planning output
class PrinterAction(BaseModel):
    action: Literal[
        "chat", 
        "get_printer_status", 
        "list_gcode_files", 
        "get_spoolman_inventory", 
        "heat_nozzle", 
        "heat_bed", 
        "start_print",
        "query_knowledge",
        "search_models",
        "download_model",
        "slice_model",
        "search_slice_print"
    ] = Field(
        description="The action/tool to run, or 'chat' if it is a general conversation/query."
    )
    target_temp: Optional[float] = Field(
        default=None,
        description="The target temperature if action is 'heat_nozzle' or 'heat_bed'."
    )
    value: Optional[str] = Field(
        default=None,
        description="General value: Gcode filename, search query string, model ID, or STL filename."
    )
    chat_response: Optional[str] = Field(
        default=None,
        description="The chat response if action is 'chat'."
    )

# Standard instructions guiding the agent planner
system_instructions = (
    "You are a professional Bambu Lab X1C Printer Assistant. Your core goal is to safely "
    "manage and monitor print jobs, filament spools, printer status, troubleshooting queries, and model search/slice via BamBot.\n\n"
    "Based on the user's input, choose the appropriate action and populate the structured output schema. "
    "Do NOT run tools directly; instead, set the 'action' field to the name of the tool or 'chat' if it is a general conversation/response. "
    "Make sure to populate target temperatures, filenames, model IDs, or queries if applicable.\n\n"
    "ROUTING GUIDELINES:\n"
    "- If the user asks for the printer status, state, temperatures, progress, or what the printer is doing, you MUST choose 'get_printer_status'.\n"
    "- If the user asks to list files, see available files, or what G-code files are on the server, you MUST choose 'list_gcode_files'.\n"
    "- If the user asks about filament inventory, spools, or Spoolman, you MUST choose 'get_spoolman_inventory'.\n"
    "- If the user asks a technical or troubleshooting question about 3D printing (e.g., stringing, warping, adhesion, temperature limits), you MUST choose 'query_knowledge' with value set to the query string.\n"
    "- If the user wants to search for models, search printables, thingiverse, makerworld, or search spool holders / calibration boats, you MUST choose 'search_models' with value set to the search term.\n"
    "- If the user wants to download or retrieve a specific model by ID, you MUST choose 'download_model' with value set to the model ID.\n"
    "- If the user wants to slice a model or stl file (using OrcaSlicer), you MUST choose 'slice_model' with value set to the STL filename.\n"
    "- If the user wants to search for, download, slice, and print a model in a single request (e.g., 'find a benchy then slice with default settings and print it', 'search for a calibration cube, slice it, and print it'), you MUST choose 'search_slice_print' with value set to the search term (e.g., 'benchy' or 'calibration cube').\n\n"
    "CONVERSATIONAL CONTEXT & FOLLOW-UPS:\n"
    "- Pay close attention to the conversation history. If the user replies with a follow-up confirmation (e.g., 'yes', 'no', 'sure', 'do it', 'go ahead', 'cancel') to a question the agent asked previously, map it to the corresponding logical action.\n"
    "- Specifically, if the user asks to download a model after a search (e.g., 'download it', 'download the first one'), you MUST choose the 'download_model' action and set 'value' to the model ID from the search results in the conversation history (e.g., '3dbenchy').\n"
    "- Specifically, if the agent previously asked 'Would you like to slice this model with these settings?' and the user replies with 'yes' or confirmation, you MUST choose the 'slice_model' action and set 'value' to the EXACT STL filename that was recently downloaded (which is specified in the agent's previous message, e.g., if the previous message said 'Successfully downloaded model STL: calibration_cube.stl', you MUST set 'value' to 'calibration_cube.stl'). Do NOT hardcode '3dbenchy.stl' or 'model.stl'; you MUST dynamically extract and use the actual filename from the previous message.\n"
    "- If the user replies with 'no' or declines, you should choose 'chat' and respond politely acknowledging their decision.\n\n"
    "CRITICAL BEHAVIORS:\n"
    "1. Prioritize Safety: Before starting any print job, you MUST ask the user to verify the printer "
    "bed is clear. Show AMS filament mapping details in your pre-print check.\n"
    "2. Thermal Safety: Never set nozzle temp > 300°C or bed temp > 120°C.\n"
    "3. Optional Features: If Spoolman details are empty or not configured, fall back gracefully "
    "and skip spool check warnings without throwing constant errors.\n"
    "4. Tone: Be helpful, technical, and alert."
)

printer_agent = LlmAgent(
    name="printer_agent",
    model=Gemini(
        model="gemini-3.1-flash-lite",
        retry_options=genai_types.HttpRetryOptions(attempts=3),
    ),
    instruction=system_instructions,
    output_schema=PrinterAction,
    output_key="planned_action"
)

def unpack_mcp_response(res: Any, tool_name: Optional[str] = None) -> Any:
    """
    Unpacks an MCP CallToolResult response.
    An MCP tool run typically returns a CallToolResult model or dict.
    This helper extracts the text content and parses it via json.loads if it is valid JSON.
    """
    # 1. Convert to dict if possible
    res_dict = None
    if isinstance(res, dict):
        res_dict = res
    elif hasattr(res, "model_dump"):
        try:
            res_dict = res.model_dump()
        except Exception:
            pass
    elif hasattr(res, "dict"):
        try:
            res_dict = res.dict()
        except Exception:
            pass

    # 2. Extract content list and error flag
    content_list = None
    is_error = False

    if res_dict is not None and isinstance(res_dict, dict):
        content_list = res_dict.get("content")
        is_error = res_dict.get("isError", False) or res_dict.get("is_error", False)
    elif hasattr(res, "content"):
        content_list = getattr(res, "content", None)
        is_error = getattr(res, "is_error", False) or getattr(res, "isError", False)

    # 3. Process the content
    if content_list is not None:
        if is_error:
            err_msg = "Unknown MCP tool error"
            if isinstance(content_list, list) and len(content_list) > 0:
                first_item = content_list[0]
                if hasattr(first_item, "model_dump"):
                    try:
                        first_item = first_item.model_dump()
                    except Exception:
                        pass
                elif hasattr(first_item, "dict"):
                    try:
                        first_item = first_item.dict()
                    except Exception:
                        pass

                if isinstance(first_item, dict) and "text" in first_item:
                    err_msg = first_item["text"]
                elif hasattr(first_item, "text"):
                    err_msg = first_item.text
            return {"error": err_msg}

        if not content_list:
            return []

        parsed_items = []
        for item in content_list:
            item_dict = None
            if hasattr(item, "model_dump"):
                try:
                    item_dict = item.model_dump()
                except Exception:
                    pass
            elif hasattr(item, "dict"):
                try:
                    item_dict = item.dict()
                except Exception:
                    pass
            elif isinstance(item, dict):
                item_dict = item

            text_val = None
            if item_dict is not None and isinstance(item_dict, dict):
                text_val = item_dict.get("text")
            elif hasattr(item, "text"):
                text_val = item.text

            if text_val is not None:
                try:
                    parsed_items.append(json.loads(text_val))
                except Exception:
                    parsed_items.append(text_val)

        # Reconstruct list structure for tools that return lists of objects
        list_tools = {"search_3d_models", "list_gcode_files", "get_spoolman_inventory"}
        if tool_name in list_tools:
            return parsed_items

        if len(parsed_items) == 1:
            return parsed_items[0]
        return parsed_items
    return res


# Helper to execute a tool from the MCP toolset
async def execute_tool(ctx: Context, name: str, args: dict) -> Any:
    tools = await mcp_servers[0].get_tools()
    for tool in tools:
        if tool.name == name:
            raw_res = await tool.run_async(args=args, tool_context=ctx)
            return unpack_mcp_response(raw_res, tool_name=name)
    raise ValueError(f"Tool {name} not found in MCP server tools.")

@node
def intent_router_node(node_input: dict):
    action = node_input.get("action", "chat")
    logger.info(f"[INTENT ROUTER] Routing action: {action}")
    
    if action in ["heat_nozzle", "heat_bed", "start_print"]:
        return Event(output=node_input, route="CONTROL")
    elif action in ["get_printer_status", "list_gcode_files", "get_spoolman_inventory", "query_knowledge", "search_models", "download_model", "slice_model", "search_slice_print"]:
        return Event(output=node_input, route=action)
    else:
        return Event(output=node_input, route="CHAT")

@node(rerun_on_resume=True)
async def safety_check_node(ctx: Context, node_input: dict):
    action = node_input.get("action")
    target_temp = node_input.get("target_temp")
    value = node_input.get("value", "")

    # Rule 1 & 2: Thermal Limits (immediate rejection)
    if target_temp is not None:
        target_temp = float(target_temp)
        if action == "heat_nozzle" and target_temp > 300.0:
            msg = f"Safety Block: Target nozzle temperature {target_temp}°C exceeds max limit of 300°C."
            logger.error(msg)
            yield Event(output={"error": msg}, route="UNSAFE")
            return
            
        if action == "heat_bed" and target_temp > 120.0:
            msg = f"Safety Block: Target bed temperature {target_temp}°C exceeds max limit of 120°C."
            logger.error(msg)
            yield Event(output={"error": msg}, route="UNSAFE")
            return

    # Rule 3: Bed Clearance Check (with native HITL)
    if action == "start_print":
        # If this is a fresh print request (not a resume step), reset safety approvals
        if not ctx.resume_inputs and type(ctx).__name__ != 'MagicMock':
            reset_safety_checks()
            if hasattr(ctx, "state") and type(ctx.state).__name__ != 'MagicMock':
                ctx.state["current_print_bed_cleared"] = False
                ctx.state["current_print_door_closed"] = False

        # Process resume responses
        if ctx.resume_inputs and "confirm_bed_cleared" in ctx.resume_inputs:
            res = ctx.resume_inputs["confirm_bed_cleared"]
            val = res.get("result") if isinstance(res, dict) else res
            if val is True:
                SAFETY_APPROVALS["bed_cleared"] = True
                if hasattr(ctx, "state") and type(ctx.state).__name__ != 'MagicMock':
                    ctx.state["current_print_bed_cleared"] = True
                if isinstance(res, dict):
                    node_input["ams_mapping"] = res.get("ams_mapping")
                    node_input["plate_id"] = res.get("plate_id")
                    node_input["plate_name"] = res.get("plate_name")
                
        # Check approval status
        bed_cleared = False
        if hasattr(ctx, "state") and type(ctx.state).__name__ != 'MagicMock':
            bed_cleared = bool(ctx.state.get("current_print_bed_cleared", False))
        if not bed_cleared:
            bed_cleared = SAFETY_APPROVALS.get("bed_cleared", False)

        if not bed_cleared:
            reqs = await bambuddy_client.get_library_file_requirements(value)
            payload = {
                "prompt": "Print bed clearance has not been verified. Please confirm that the print bed has been cleared.",
                "filename": value,
                "requested_filaments": reqs.get("requested_filaments", []),
                "requested_bed_plate": reqs.get("requested_bed_plate", ""),
                "plate_id": reqs.get("plate_id"),
                "plate_name": reqs.get("plate_name"),
                "print_time": reqs.get("print_time", "Unknown"),
                "filament_weight": reqs.get("filament_weight", 0.0)
            }
            yield RequestInput(
                interrupt_id="confirm_bed_cleared",
                message="Print bed clearance has not been verified. Please confirm that the print bed has been cleared and verify the AMS filament mapping.",
                payload=payload
            )
            return

    # Rule 4: Chamber Door State for ABS/ASA (with native HITL)
    if action == "start_print":
        file_name = value or ""
        if "abs" in file_name.lower() or "asa" in file_name.lower():
            if ctx.resume_inputs and "confirm_door_closed" in ctx.resume_inputs:
                res = ctx.resume_inputs["confirm_door_closed"]
                val = res.get("result") if isinstance(res, dict) else res
                if val is True:
                    SAFETY_APPROVALS["door_closed"] = True
                    if hasattr(ctx, "state") and type(ctx.state).__name__ != 'MagicMock':
                        ctx.state["current_print_door_closed"] = True
            
            door_closed = False
            if hasattr(ctx, "state") and type(ctx.state).__name__ != 'MagicMock':
                door_closed = bool(ctx.state.get("current_print_door_closed", False))
            if not door_closed:
                door_closed = SAFETY_APPROVALS.get("door_closed", False)

            if not door_closed:
                yield RequestInput(
                    interrupt_id="confirm_door_closed",
                    message=f"Closed chamber door required for ABS/ASA print ({file_name}). Please confirm the chamber door is closed."
                )
                return

    yield Event(output=node_input, route="SAFE")

@node
async def get_printer_status_node(ctx: Context, node_input: dict):
    res = await execute_tool(ctx, "get_printer_status", {})
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "get_printer_status",
        "result": str(res)
    })
    
    if not res or not isinstance(res, dict):
        msg = "Failed to retrieve printer status: Empty or invalid response."
    elif "error" in res:
        msg = f"Failed to retrieve printer status: {res['error']}"
    else:
        msg = f"Printer Status:\nState: {res.get('state')}\nNozzle: {res.get('nozzle_temp')}°C (Target: {res.get('target_nozzle_temp')}°C)\nBed: {res.get('bed_temp')}°C (Target: {res.get('target_bed_temp')}°C)\nProgress: {res.get('percent_complete')}%\nActive File: {res.get('active_file')}"
        
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
    yield Event(output=res)

@node
async def list_gcode_files_node(ctx: Context, node_input: dict):
    res = await execute_tool(ctx, "list_gcode_files", {})
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "list_gcode_files",
        "result": str(res)
    })
    
    if not isinstance(res, list):
        if isinstance(res, dict) and "error" in res:
            msg = f"Failed to list G-code files: {res['error']}"
        else:
            msg = "No G-code files available on the server."
            res = []
    else:
        files = [f.get("name") if isinstance(f, dict) else str(f) for f in res]
        msg = "Available G-code files on server:\n" + ("\n".join(f"- {f}" for f in files) if files else "No files found.")
        
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
    yield Event(output=res)

@node
async def get_spoolman_inventory_node(ctx: Context, node_input: dict):
    res = await execute_tool(ctx, "get_spoolman_inventory", {})
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "get_spoolman_inventory",
        "result": str(res)
    })
    
    if not isinstance(res, list):
        if isinstance(res, dict) and "error" in res:
            msg = f"Failed to retrieve Spoolman inventory: {res['error']}"
        else:
            msg = "Spoolman Filament Inventory: No filament spools found."
            res = []
    else:
        spools = []
        for s in res:
            if isinstance(s, dict):
                material = s.get("material", "Unknown")
                color = s.get("color", "Unknown")
                weight = s.get("weight_g", 0.0)
                spools.append(f"- {material} ({color}): {weight:.1f}g remaining")
        msg = "Spoolman Filament Inventory:\n" + ("\n".join(spools) if spools else "No filament spools found.")
        
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
    yield Event(output=res)

@node
async def send_printer_command_node(ctx: Context, node_input: dict):
    action = node_input.get("action")
    target_temp = node_input.get("target_temp")
    value = node_input.get("value")
    
    args = {}
    if action is not None:
        args["action"] = action
    if target_temp is not None:
        args["target_temp"] = target_temp
    if value is not None:
        args["value"] = value
        
    if node_input.get("ams_mapping") is not None:
        args["ams_mapping"] = node_input.get("ams_mapping")
    if node_input.get("plate_id") is not None:
        args["plate_id"] = node_input.get("plate_id")
    if node_input.get("plate_name") is not None:
        args["plate_name"] = node_input.get("plate_name")
        
    res = await execute_tool(ctx, "send_printer_command", args)
    
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "send_printer_command",
        "result": str(res)
    })
    
    if not res or not isinstance(res, dict):
        res = {"error": "Empty or invalid response from command execution."}
        
    msg = f"Successfully executed command: {action}."
    if "error" in res:
        msg = f"Error executing command: {res['error']}"
    elif action == "start_print":
        msg = f"Started print job for Gcode file: {value}."
        reset_safety_checks()
        if hasattr(ctx, "state") and type(ctx.state).__name__ != 'MagicMock':
            ctx.state["current_print_bed_cleared"] = False
            ctx.state["current_print_door_closed"] = False
    elif action == "heat_nozzle":
        msg = f"Heating nozzle to target: {target_temp}°C."
    elif action == "heat_bed":
        msg = f"Heating bed to target: {target_temp}°C."
        
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
    yield Event(output=res)

@node
async def query_knowledge_node(ctx: Context, node_input: dict):
    val = node_input.get("value") or ""
    res = await execute_tool(ctx, "query_3d_printing_knowledge", {"query": val})
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "query_3d_printing_knowledge",
        "result": str(res)
    })
    
    if not res or not isinstance(res, dict) or "error" in res:
        msg = f"Failed to retrieve 3D printing knowledge: {res.get('error') or 'Empty response'}"
    else:
        results = res.get("results", [])
        if results:
            msg = ""
            for r in results:
                if r["type"] == "troubleshooting":
                    msg += f"Troubleshooting Topic: {r['topic']}\nSolution:\n{r['solution']}\n\n"
                elif r["type"] == "faq":
                    msg += f"FAQ Question: {r['question']}\nAnswer: {r['answer']}\n\n"
        else:
            msg = res.get("message", "No exact matching topics found in knowledge base.")
            
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg.strip())]))
    yield Event(output=res)

@node
async def search_models_node(ctx: Context, node_input: dict):
    val = node_input.get("value") or ""
    res = await execute_tool(ctx, "search_3d_models", {"query": val})
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "search_3d_models",
        "result": str(res)
    })
    
    if not isinstance(res, list):
        msg = "Failed to search models: invalid response."
        res = []
    elif not res:
        msg = f"No models found matching: '{val}'"
    else:
        msg = f"Found {len(res)} model(s) matching your query:\n"
        for m in res:
            msg += f"- [{m['name']}]({m['original_url']}) by {m['creator']} on {m['site']}. ID: {m['id']}\nDescription: {m['description']}\nRecommended: Filament={m['recommended_settings']['filament']}, Bed={m['recommended_settings']['bed_plate']}, Layer={m['recommended_settings']['layer_height']}, Infill={m['recommended_settings']['infill']}\nImage: {m['image_url']}\n\n"
            
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg.strip())]))
    yield Event(output=res)

@node
async def download_model_node(ctx: Context, node_input: dict):
    val = node_input.get("value") or ""
    res = await execute_tool(ctx, "download_3d_model", {"model_id": val})
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "download_3d_model",
        "result": str(res)
    })
    
    if not res or not isinstance(res, dict) or "error" in res:
        msg = f"Failed to download model: {res.get('error') or 'Empty response'}"
    else:
        rec = res.get("recommended_settings", {})
        msg = (
            f"Successfully downloaded model STL: {res.get('filename')}.\n"
            f"Recommended slicing settings:\n"
            f"- Filament: {rec.get('filament')}\n"
            f"- Bed Plate: {rec.get('bed_plate')}\n"
            f"- Layer Height: {rec.get('layer_height')}\n"
            f"- Infill: {rec.get('infill')}\n"
            f"Would you like to slice this model with these settings?"
        )
        
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
    yield Event(output=res)

@node
async def slice_model_node(ctx: Context, node_input: dict):
    val = node_input.get("value") or ""
    # Look for settings parameters inside node_input, or default
    process = node_input.get("process_preset") or "0.20mm Standard @BBL X1C"
    filament = node_input.get("filament_preset") or "Bambu PLA Basic @BBL X1C"
    
    res = await execute_tool(ctx, "slice_model_file", {
        "filename": val,
        "process_preset": process,
        "filament_preset": filament
    })
    SESSION_METRICS["trajectory"].append({
        "type": "tool_call_success",
        "tool": "slice_model_file",
        "result": str(res)
    })
    
    if not res or not isinstance(res, dict) or "error" in res:
        msg = f"Failed to slice model: {res.get('error') or 'Empty response'}"
    else:
        msg = (
            f"Successfully sliced model using OrcaSlicer.\n"
            f"- Output File: {res.get('filename')}\n"
            f"- Estimated Time: {res.get('estimated_time')}\n"
            f"- Filament Used: {res.get('filament_usage_g')}g\n"
            f"- Presets: {res.get('settings', {}).get('process_preset')} | {res.get('settings', {}).get('filament_preset')}\n"
            f"The sliced G-code has been added to your printer files library."
        )
        
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
    yield Event(output=res)

@node
async def chat_response_node(ctx: Context, node_input: dict):
    response_text = node_input.get("chat_response") or "Hello! I am your Bambu Lab X1C Printer Assistant. How can I help you today?"
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=response_text)]))
    yield Event(output=response_text)

@node
async def block_response_node(ctx: Context, node_input: dict):
    err = node_input.get("error", "Safety check failed.")
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=err)]))
    yield Event(output=err)

@node
async def search_slice_print_node(ctx: Context, node_input: dict):
    query = node_input.get("value") or ""
    logger.info(f"[SEARCH_SLICE_PRINT_NODE] Starting compound search_slice_print for: {query}")
    
    # 1. Search for models
    search_res = await execute_tool(ctx, "search_3d_models", {"query": query})
    if not isinstance(search_res, list) or not search_res:
        msg = f"Search failed: No models found matching '{query}'."
        yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
        yield Event(output={"error": msg}, route="fail")
        return
        
    first_model = search_res[0]
    model_id = first_model.get("id")
    model_name = first_model.get("name")
    
    # 2. Download the model
    download_res = await execute_tool(ctx, "download_3d_model", {"model_id": model_id})
    if not download_res or not isinstance(download_res, dict) or "error" in download_res:
        msg = f"Failed to download model '{model_name}': {download_res.get('error') if download_res else 'Empty response'}"
        yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
        yield Event(output={"error": msg}, route="fail")
        return
        
    stl_filename = download_res.get("filename")
    
    # 3. Slice the model
    rec = download_res.get("recommended_settings", {})
    process = rec.get("process_preset") or "0.20mm Standard @BBL X1C"
    filament = rec.get("filament_preset") or "Bambu PLA Basic @BBL X1C"
    
    slice_res = await execute_tool(ctx, "slice_model_file", {
        "filename": stl_filename,
        "process_preset": process,
        "filament_preset": filament
    })
    
    if not slice_res or not isinstance(slice_res, dict) or "error" in slice_res:
        msg = f"Failed to slice model '{stl_filename}': {slice_res.get('error') if slice_res else 'Empty response'}"
        yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
        yield Event(output={"error": msg}, route="fail")
        return
        
    sliced_filename = slice_res.get("filename")
    
    # Yield dynamic success info message
    msg = (
        f"Found model '{model_name}' (ID: {model_id}) on {first_model.get('site')}.\n"
        f"1. Successfully downloaded: {stl_filename}\n"
        f"2. Successfully sliced: {sliced_filename}\n"
        f"Initiating print job..."
    )
    yield Event(content=genai_types.Content(role='model', parts=[genai_types.Part.from_text(text=msg)]))
    
    # Transition to safety_check_node for printing
    yield Event(output={"action": "start_print", "value": sliced_filename}, route="start_print")

root_agent = Workflow(
    name="printer_workflow",
    edges=[
        (START, printer_agent),
        (printer_agent, intent_router_node),
        (intent_router_node, {
            "CONTROL": safety_check_node,
            "get_printer_status": get_printer_status_node,
            "list_gcode_files": list_gcode_files_node,
            "get_spoolman_inventory": get_spoolman_inventory_node,
            "query_knowledge": query_knowledge_node,
            "search_models": search_models_node,
            "download_model": download_model_node,
            "slice_model": slice_model_node,
            "search_slice_print": search_slice_print_node,
            "CHAT": chat_response_node
        }),
        (search_slice_print_node, {
            "start_print": safety_check_node,
            "fail": block_response_node
        }),
        (safety_check_node, {
            "SAFE": send_printer_command_node,
            "UNSAFE": block_response_node
        })
    ]
)

app = App(
    root_agent=root_agent,
    name="app"
)

