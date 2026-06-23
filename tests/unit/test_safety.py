import unittest
import asyncio
from app import agent

# Mock Tool class for testing callbacks
class MockTool:
    def __init__(self, name: str):
        self.name = name

class TestPrinterAgentSafety(unittest.TestCase):
    
    def setUp(self):
        # Reset approvals before each test
        agent.reset_safety_checks()

    def test_nozzle_temperature_limit(self):
        # 1. Hotend target too high (320°C) -> Should Deny (return error dict)
        tool = MockTool(name="send_printer_command")
        args = {"action": "heat_nozzle", "target_temp": 320.0}
        
        result_high = asyncio.run(agent.before_tool_callback(tool, args, None))
        self.assertIsNotNone(result_high)
        self.assertIn("exceeds max limit", result_high["error"])

        # 2. Hotend target safe (220°C) -> Should Allow (return None)
        args_safe = {"action": "heat_nozzle", "target_temp": 220.0}
        result_safe = asyncio.run(agent.before_tool_callback(tool, args_safe, None))
        self.assertIsNone(result_safe)

    def test_bed_temperature_limit(self):
        tool = MockTool(name="send_printer_command")
        
        # 1. Bed target too high (130°C) -> Should Deny (return error dict)
        args_high = {"action": "heat_bed", "target_temp": 130.0}
        result_high = asyncio.run(agent.before_tool_callback(tool, args_high, None))
        self.assertIsNotNone(result_high)
        self.assertIn("exceeds max limit", result_high["error"])

        # 2. Bed target safe (60°C) -> Should Allow (return None)
        args_safe = {"action": "heat_bed", "target_temp": 60.0}
        result_safe = asyncio.run(agent.before_tool_callback(tool, args_safe, None))
        self.assertIsNone(result_safe)

    def test_bed_clearance_guardrail(self):
        tool = MockTool(name="start_print_job")
        args = {"action": "start_print", "value": "benchy_pla_red.gcode"}
        
        # 1. Without verification -> Should Deny (return error dict)
        result_unverified = asyncio.run(agent.before_tool_callback(tool, args, None))
        self.assertIsNotNone(result_unverified)
        self.assertIn("bed clearance has not been verified", result_unverified["error"])
        
        # 2. Verify bed clearance -> Should Allow (return None)
        agent.SAFETY_APPROVALS["bed_cleared"] = True
        result_verified = asyncio.run(agent.before_tool_callback(tool, args, None))
        self.assertIsNone(result_verified)

    def test_chamber_door_guardrail_for_abs(self):
        tool = MockTool(name="start_print_job")
        args = {"action": "start_print", "value": "spool_holder_abs_blue.gcode"}
        
        # Verify bed cleared first
        agent.SAFETY_APPROVALS["bed_cleared"] = True
        
        # 1. Door open for ABS print -> Should Deny (return error dict)
        agent.SAFETY_APPROVALS["door_closed"] = False
        result_open = asyncio.run(agent.before_tool_callback(tool, args, None))
        self.assertIsNotNone(result_open)
        self.assertIn("Closed chamber door required for ABS/ASA", result_open["error"])
        
        # 2. Door closed for ABS print -> Should Allow (return None)
        agent.SAFETY_APPROVALS["door_closed"] = True
        result_closed = asyncio.run(agent.before_tool_callback(tool, args, None))
        self.assertIsNone(result_closed)

if __name__ == "__main__":
    unittest.main()
