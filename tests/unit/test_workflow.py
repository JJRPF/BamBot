import unittest
import asyncio
from unittest.mock import MagicMock, patch
from app import agent
from app.agent import intent_router_node, safety_check_node
from google.adk.events.request_input import RequestInput
from google.adk.events.event import Event

class TestPrinterWorkflowNodes(unittest.TestCase):

    def setUp(self):
        agent.reset_safety_checks()

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_intent_router_control(self):
        ctx = MagicMock()
        for action in ["heat_nozzle", "heat_bed", "start_print"]:
            node_input = {"action": action}
            events = []
            async def run():
                async for e in intent_router_node.run(ctx=ctx, node_input=node_input):
                    events.append(e)
            self.run_async(run())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].actions.route, "CONTROL")

    def test_intent_router_queries(self):
        ctx = MagicMock()
        for action in ["get_printer_status", "list_gcode_files", "get_spoolman_inventory"]:
            node_input = {"action": action}
            events = []
            async def run():
                async for e in intent_router_node.run(ctx=ctx, node_input=node_input):
                    events.append(e)
            self.run_async(run())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].actions.route, action)

    def test_intent_router_chat(self):
        ctx = MagicMock()
        for action in ["chat", "invalid_action", ""]:
            node_input = {"action": action}
            events = []
            async def run():
                async for e in intent_router_node.run(ctx=ctx, node_input=node_input):
                    events.append(e)
            self.run_async(run())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].actions.route, "CHAT")

    def test_safety_check_thermal_limits_nozzle(self):
        ctx = MagicMock()
        node_input = {"action": "heat_nozzle", "target_temp": 320.0}
        events = []
        async def run():
            async for e in safety_check_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actions.route, "UNSAFE")
        self.assertIn("exceeds max limit", events[0].output["error"])

    def test_safety_check_thermal_limits_bed(self):
        ctx = MagicMock()
        node_input = {"action": "heat_bed", "target_temp": 130.0}
        events = []
        async def run():
            async for e in safety_check_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actions.route, "UNSAFE")
        self.assertIn("exceeds max limit", events[0].output["error"])

    def test_safety_check_bed_clearance_hitl(self):
        ctx = MagicMock()
        ctx.resume_inputs = {}
        node_input = {"action": "start_print", "value": "benchy.gcode"}
        
        events = []
        async def run():
            async for e in safety_check_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        
        # Should yield 1 RequestInput interrupt
        self.assertEqual(len(events), 1)
        self.assertIn("confirm_bed_cleared", events[0].long_running_tool_ids)
        self.assertEqual(events[0].content.parts[0].function_call.name, "adk_request_input")

    def test_safety_check_bed_clearance_resume(self):
        # 1. Resume with confirm_bed_cleared = True
        ctx = MagicMock()
        ctx.resume_inputs = {"confirm_bed_cleared": {"result": True}}
        node_input = {"action": "start_print", "value": "benchy.gcode"}
        
        events = []
        async def run():
            async for e in safety_check_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        
        # Bed cleared is now True, routes to SAFE
        self.assertTrue(agent.SAFETY_APPROVALS["bed_cleared"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actions.route, "SAFE")

    def test_safety_check_door_state_hitl(self):
        agent.SAFETY_APPROVALS["bed_cleared"] = True
        
        # ABS print needs closed chamber
        ctx = MagicMock()
        ctx.resume_inputs = {}
        node_input = {"action": "start_print", "value": "spool_holder_abs_blue.gcode"}
        
        events = []
        async def run():
            async for e in safety_check_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        
        # Should yield 1 RequestInput interrupt for door closed
        self.assertEqual(len(events), 1)
        self.assertIn("confirm_door_closed", events[0].long_running_tool_ids)
        self.assertEqual(events[0].content.parts[0].function_call.name, "adk_request_input")

    def test_safety_check_door_state_resume(self):
        agent.SAFETY_APPROVALS["bed_cleared"] = True
        
        # Resume with confirm_door_closed = True
        ctx = MagicMock()
        ctx.resume_inputs = {"confirm_door_closed": {"result": True}}
        node_input = {"action": "start_print", "value": "spool_holder_abs_blue.gcode"}
        
        events = []
        async def run():
            async for e in safety_check_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        
        # Bed cleared is True, Door closed is True, routes to SAFE
        self.assertTrue(agent.SAFETY_APPROVALS["door_closed"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actions.route, "SAFE")

    @patch("app.agent.execute_tool")
    def test_get_printer_status_node_success(self, mock_execute):
        mock_execute.return_value = {
            "state": "printing",
            "nozzle_temp": 220.0,
            "target_nozzle_temp": 220.0,
            "bed_temp": 60.0,
            "target_bed_temp": 60.0,
            "percent_complete": 50.0,
            "active_file": "benchy.gcode"
        }
        ctx = MagicMock()
        node_input = {}
        events = []
        async def run():
            async for e in agent.get_printer_status_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Printer Status:\nState: printing", events[0].content.parts[0].text)
        self.assertEqual(events[1].output["state"], "printing")

    @patch("app.agent.execute_tool")
    def test_get_printer_status_node_error(self, mock_execute):
        mock_execute.return_value = {"error": "Failed to connect to BamBot"}
        ctx = MagicMock()
        node_input = {}
        events = []
        async def run():
            async for e in agent.get_printer_status_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Failed to retrieve printer status: Failed to connect to BamBot", events[0].content.parts[0].text)

    @patch("app.agent.execute_tool")
    def test_list_gcode_files_node_success(self, mock_execute):
        mock_execute.return_value = [
            {"name": "benchy.gcode"},
            {"name": "cube.gcode"}
        ]
        ctx = MagicMock()
        node_input = {}
        events = []
        async def run():
            async for e in agent.list_gcode_files_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Available G-code files on server:\n- benchy.gcode\n- cube.gcode", events[0].content.parts[0].text)
        self.assertEqual(events[1].output, mock_execute.return_value)

    @patch("app.agent.execute_tool")
    def test_list_gcode_files_node_empty(self, mock_execute):
        mock_execute.return_value = []
        ctx = MagicMock()
        node_input = {}
        events = []
        async def run():
            async for e in agent.list_gcode_files_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("No files found", events[0].content.parts[0].text)

    @patch("app.agent.execute_tool")
    def test_get_spoolman_inventory_node_success(self, mock_execute):
        mock_execute.return_value = [
            {"material": "PLA", "color": "#FF0000", "weight_g": 350.0},
            {"material": "PETG", "color": "#00FF00", "weight_g": 850.0}
        ]
        ctx = MagicMock()
        node_input = {}
        events = []
        async def run():
            async for e in agent.get_spoolman_inventory_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Spoolman Filament Inventory:\n- PLA (#FF0000): 350.0g remaining\n- PETG (#00FF00): 850.0g remaining", events[0].content.parts[0].text)

    @patch("app.agent.execute_tool")
    def test_send_printer_command_node_heat_nozzle(self, mock_execute):
        mock_execute.return_value = {"status": "success"}
        ctx = MagicMock()
        node_input = {"action": "heat_nozzle", "target_temp": 220.0}
        events = []
        async def run():
            async for e in agent.send_printer_command_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Heating nozzle to target: 220.0°C", events[0].content.parts[0].text)

    @patch("app.agent.execute_tool")
    def test_send_printer_command_node_error(self, mock_execute):
        mock_execute.return_value = {"error": "Device is offline"}
        ctx = MagicMock()
        node_input = {"action": "heat_nozzle", "target_temp": 220.0}
        events = []
        async def run():
            async for e in agent.send_printer_command_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Error executing command: Device is offline", events[0].content.parts[0].text)

    def test_chat_response_node_default(self):
        ctx = MagicMock()
        node_input = {}
        events = []
        async def run():
            async for e in agent.chat_response_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].content.parts[0].text, "Hello! I am your Bambu Lab X1C Printer Assistant. How can I help you today?")
        self.assertEqual(events[1].output, "Hello! I am your Bambu Lab X1C Printer Assistant. How can I help you today?")

    def test_chat_response_node_custom(self):
        ctx = MagicMock()
        node_input = {"chat_response": "I can help you print benchy!"}
        events = []
        async def run():
            async for e in agent.chat_response_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].content.parts[0].text, "I can help you print benchy!")

    def test_block_response_node_default(self):
        ctx = MagicMock()
        node_input = {}
        events = []
        async def run():
            async for e in agent.block_response_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].content.parts[0].text, "Safety check failed.")

    def test_block_response_node_custom(self):
        ctx = MagicMock()
        node_input = {"error": "Nozzle temperature exceeds limit."}
        events = []
        async def run():
            async for e in agent.block_response_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].content.parts[0].text, "Nozzle temperature exceeds limit.")

    @patch("app.agent.execute_tool")
    def test_search_slice_print_node_success(self, mock_execute):
        mock_execute.side_effect = [
            [{"id": "3dbenchy", "name": "3DBenchy", "site": "Printables"}],
            {"filename": "3dbenchy.stl", "recommended_settings": {"process_preset": "0.20mm Standard @BBL X1C", "filament_preset": "Bambu PLA Basic @BBL X1C"}},
            {"status": "success", "filename": "3dbenchy_sliced.gcode.3mf"}
        ]
        ctx = MagicMock()
        node_input = {"value": "benchy"}
        events = []
        async def run():
            async for e in agent.search_slice_print_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Successfully sliced: 3dbenchy_sliced.gcode.3mf", events[0].content.parts[0].text)
        self.assertEqual(events[1].output["action"], "start_print")
        self.assertEqual(events[1].output["value"], "3dbenchy_sliced.gcode.3mf")
        self.assertEqual(events[1].actions.route, "start_print")

    @patch("app.agent.execute_tool")
    def test_search_slice_print_node_failure(self, mock_execute):
        mock_execute.side_effect = [
            [],
        ]
        ctx = MagicMock()
        node_input = {"value": "unknown_model"}
        events = []
        async def run():
            async for e in agent.search_slice_print_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Search failed", events[0].content.parts[0].text)
        self.assertEqual(events[1].output["error"], "Search failed: No models found matching 'unknown_model'.")
        self.assertEqual(events[1].actions.route, "fail")

if __name__ == "__main__":
    unittest.main()
