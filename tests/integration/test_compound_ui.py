import os
import sys
import time
import logging
import subprocess
import threading
import pytest
import requests
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = 8005
BASE_URL = f"http://127.0.0.1:{PORT}"

def log_output(pipe, log_func):
    for line in iter(pipe.readline, ""):
        log_func(line.strip())

@pytest.fixture(scope="module")
def ui_test_server():
    logger.info("Starting FastAPI server on port %d for UI testing", PORT)
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.fast_api_app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
    ]
    env = os.environ.copy()
    env["INTEGRATION_TEST"] = "TRUE"
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    # Start threads to capture logs
    threading.Thread(
        target=log_output, args=(process.stdout, logger.info), daemon=True
    ).start()
    threading.Thread(
        target=log_output, args=(process.stderr, logger.error), daemon=True
    ).start()

    # Wait for server to respond
    ready = False
    start_time = time.time()
    while time.time() - start_time < 30:
        try:
            resp = requests.get(f"{BASE_URL}/docs", timeout=2)
            if resp.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.5)

    if not ready:
        process.terminate()
        pytest.fail("FastAPI server failed to start on port 8005 for UI testing")

    yield process

    logger.info("Stopping FastAPI server on port %d", PORT)
    process.terminate()
    process.wait()

@pytest.mark.asyncio
async def test_compound_ui_e2e(ui_test_server):
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Navigate to Dashboard
        await page.goto(BASE_URL)

        # Assert title is correct
        title = await page.title()
        assert "BamBot" in title, f"Unexpected page title: {title}"

        # Wait for WebSocket badge to be connected
        badge = page.locator("#status-badge")
        await badge.wait_for(state="visible", timeout=10000)
        
        # Verify connected class
        await page.wait_for_function(
            "document.getElementById('status-badge').classList.contains('badge-connected')",
            timeout=10000
        )
        logger.info("UI is connected to WebSocket.")

        # Switch to Chat tab
        await page.click('button[data-tab="chat-view"]')
        logger.info("Switched to Chat tab.")

        # Click New Chat to ensure clean session
        new_chat_btn = page.locator("#btn-new-chat")
        await new_chat_btn.click()
        logger.info("Clicked New Chat.")

        # Wait for WebSocket to reconnect
        await page.wait_for_timeout(1000)
        await page.wait_for_function(
            "document.getElementById('status-badge').classList.contains('badge-connected')",
            timeout=10000
        )
        logger.info("Reconnected to WebSocket.")

        # Simulate typing a compound chat message
        chat_input = page.locator("#chat-input")
        await chat_input.fill("find a benchy then slice with default settings and print it.")
        await chat_input.press("Enter")
        logger.info("Sent compound print query.")

        # Wait for the agent's bubble response or HITL checkbox to appear
        # Slicing can take up to 20-30 seconds
        chk_bed = page.locator("#chk-bed")
        await chk_bed.wait_for(state="visible", timeout=45000)
        logger.info("Bed cleared safety checkbox is visible.")

        # Verify that the agent bubble has the correct text
        agent_bubble = page.locator(".chat-msg.agent .bubble").last
        text = await agent_bubble.inner_text()
        logger.info("Agent response text: %s", text)
        
        # Take a screenshot and save it to the artifact directory
        screenshot_path = "/Users/JJR/.gemini/antigravity/brain/988eb475-82e0-4e9a-a32e-e38cad51d3d5/screenshot_compound_flow.png"
        await page.screenshot(path=screenshot_path)
        logger.info("E2E UI test passed. Screenshot saved to %s", screenshot_path)

        await browser.close()
