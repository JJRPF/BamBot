import unittest
import asyncio
from unittest.mock import MagicMock, patch
from bambuddy_mcp import search_3d_models, download_3d_model
from app import agent
from google.adk.events.event import Event
from google.adk.agents.context import Context

class TestModelFunctions(unittest.TestCase):

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_search_3d_models_success(self):
        # Test searching for "benchy"
        results = self.run_async(search_3d_models(query="benchy"))
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["id"], "3dbenchy")
        self.assertIn("calibration boat", results[0]["name"].lower())

    def test_search_3d_models_empty(self):
        # Test searching for non-existent model name
        results = self.run_async(search_3d_models(query="nonexistent_model_xyz"))
        self.assertEqual(len(results), 0)

    def test_search_3d_models_by_site(self):
        # Test filtering by site
        results_printables = self.run_async(search_3d_models(query="cube", site="Printables"))
        self.assertEqual(len(results_printables), 0) # Calibration cube is from Thingiverse

        results_thingiverse = self.run_async(search_3d_models(query="cube", site="Thingiverse"))
        self.assertEqual(len(results_thingiverse), 1)
        self.assertEqual(results_thingiverse[0]["id"], "calibration_cube")

    def test_download_3d_model_success(self):
        # Test downloading a valid model
        result = self.run_async(download_3d_model(model_id="3dbenchy"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["model_id"], "3dbenchy")
        self.assertEqual(result["filename"], "3dbenchy.stl")
        self.assertIn("recommended_settings", result)

    def test_download_3d_model_not_found(self):
        # Test downloading an invalid model ID
        result = self.run_async(download_3d_model(model_id="nonexistent_id"))
        self.assertIn("error", result)
        self.assertIn("not registered", result["error"])

    @patch("app.agent.execute_tool")
    def test_search_models_node_success(self, mock_execute):
        mock_execute.return_value = [
            {
                "id": "3dbenchy",
                "name": "3DBenchy",
                "creator": "CreativeTools",
                "description": "calibration boat",
                "site": "Printables",
                "original_url": "url",
                "image_url": "image",
                "recommended_settings": {
                    "filament": "PLA",
                    "bed_plate": "PEI",
                    "layer_height": "0.20mm",
                    "infill": "10%"
                }
            }
        ]
        ctx = MagicMock()
        node_input = {"value": "benchy"}
        events = []
        async def run():
            async for e in agent.search_models_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Found 1 model(s) matching your query", events[0].content.parts[0].text)
        self.assertEqual(events[1].output, mock_execute.return_value)

    @patch("app.agent.execute_tool")
    def test_download_model_node_success(self, mock_execute):
        mock_execute.return_value = {
            "status": "success",
            "model_id": "3dbenchy",
            "filename": "3dbenchy.stl",
            "recommended_settings": {
                "filament": "PLA",
                "bed_plate": "PEI",
                "layer_height": "0.20mm",
                "infill": "10%"
            }
        }
        ctx = MagicMock()
        node_input = {"value": "3dbenchy"}
        events = []
        async def run():
            async for e in agent.download_model_node.run(ctx=ctx, node_input=node_input):
                events.append(e)
        self.run_async(run())
        self.assertEqual(len(events), 2)
        self.assertIn("Successfully downloaded model STL: 3dbenchy.stl", events[0].content.parts[0].text)
        self.assertEqual(events[1].output, mock_execute.return_value)

if __name__ == "__main__":
    unittest.main()
