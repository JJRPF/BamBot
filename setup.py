#!/usr/bin/env python3
import os
import sys
import subprocess
import re
import shutil
import socket

# Color Codes for Pretty Terminal Output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_banner():
    banner = f"""
{BLUE}{BOLD}======================================================================
    ____                  ____            __     __     
   / __ )____ _____ ___  / __ )__  ______/ /____/ /_  __
  / __  / __ `/ __ `__ \\/ __  / / / / __  / __  / / / / /
 / /_/ / /_/ / / / / / / /_/ / /_/ / /_/ / /_/ / /_/ / / 
/_____/\\__,_/_/ /_/ /_/_____/\\__,_/\\__,_/\\__,_/\\__, /\\__,_/  
                                              /____/    
          🤖 BamBot X1C Printer Agent Setup Script 🤖
======================================================================{RESET}
"""
    print(banner)

def check_python_version():
    print(f"[{CYAN}*{RESET}] Checking Python version...")
    major, minor = sys.version_info.major, sys.version_info.minor
    if major != 3 or minor < 11:
        print(f"{RED}Error: Python 3.11 or higher is required. Found Python {major}.{minor}.{RESET}")
        sys.exit(1)
    print(f"{GREEN}✔ Python {major}.{minor} detected.{RESET}")

def check_command(cmd):
    return shutil.which(cmd) is not None

def check_dependencies():
    print(f"\n[{CYAN}*{RESET}] Checking system dependencies...")
    
    # Check uv
    if not check_command("uv"):
        print(f"{YELLOW}Warning: 'uv' package manager not found.{RESET}")
        print(f"Please install uv to manage python virtual environments:")
        print(f"  {BOLD}curl -LsSf https://astral.sh/uv/install.sh | sh{RESET}\n")
        confirm = input(f"Would you like to try installing uv automatically? (y/N): ").strip().lower()
        if confirm == 'y':
            try:
                subprocess.run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True, check=True)
                print(f"{GREEN}✔ uv installed successfully. Please restart your shell if commands are not found.{RESET}")
            except Exception as e:
                print(f"{RED}Failed to install uv automatically: {e}. Please install manually.{RESET}")
                sys.exit(1)
        else:
            sys.exit(1)
    else:
        print(f"{GREEN}✔ uv is installed.{RESET}")

    # Check agents-cli
    if not check_command("agents-cli"):
        print(f"{YELLOW}Warning: 'agents-cli' not found on your PATH.{RESET}")
        print("Installing google-agents-cli via uv tool...")
        try:
            subprocess.run(["uv", "tool", "install", "google-agents-cli"], check=True)
            print(f"{GREEN}✔ google-agents-cli installed successfully.{RESET}")
        except Exception as e:
            print(f"{RED}Failed to install agents-cli: {e}. Please run 'uv tool install google-agents-cli' manually.{RESET}")
            sys.exit(1)
    else:
        print(f"{GREEN}✔ agents-cli is installed.{RESET}")

def load_existing_env(filepath):
    env_vars = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        env_vars[parts[0].strip()] = parts[1].strip()
    return env_vars

def configure_agent_port():
    print(f"\n{BOLD}🔌 5. Configure BamBot Agent Port:{RESET}")
    print("  The real BamBuddy API server defaults to port 8000.")
    print("  Since we cannot run the BamBot Agent Web Portal and the BamBuddy API on the same port,")
    print("  you should select a different port for the BamBot Agent.")

    suggested = []
    candidates = [8080, 8002, 8003, 8004, 8005, 8081, 9000]
    for p in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', p))
                suggested.append(p)
                if len(suggested) >= 3:
                    break
        except Exception:
            continue
            
    suggested_str = ", ".join(map(str, suggested))
    default_port = 8080 if 8080 in suggested else (suggested[0] if suggested else 8002)
    
    print(f"  Suggested available ports on this system: {CYAN}{suggested_str}{RESET}")
    port_input = input(f"  Enter the port to run BamBot Agent Web Portal on [{default_port}]: ").strip()
    if not port_input:
        return default_port
    try:
        return int(port_input)
    except ValueError:
        print(f"  {YELLOW}Invalid port format. Using default: {default_port}{RESET}")
        return default_port

def configure_environment():
    print(f"\n{BOLD}[Step 1: Configuration]{RESET}")
    print("Setting up your .env configuration files. Press enter to accept defaults.")

    # Load existing env vars to offer as defaults
    root_env = load_existing_env(".env")
    app_env = load_existing_env("app/.env")
    
    # Merge existing values
    existing = {**root_env, **app_env}
    
    # 1. Gemini API Key
    print(f"\n{BOLD}🔑 1. Gemini API Key:{RESET}")
    print(f"  {CYAN}Where to get it:{RESET} Go to {BLUE}https://aistudio.google.com/{RESET}")
    print("  Click 'Get API Key' and create a key in a new or existing Google Cloud project.")
    print("  Supported Formats:")
    print("    - Standard Key: starts with 'AIza' (traditional GCP key)")
    print("    - New Auth Key: starts with 'AQ'   (newer project-scoped key)")
    print("  Both formats are fully supported and work identically.")
    
    default_gemini = existing.get("GEMINI_API_KEY") or existing.get("GOOGLE_API_KEY") or ""
    masked_default = f"{default_gemini[:6]}...{default_gemini[-4:]}" if len(default_gemini) > 10 else "Not set"
    
    gemini_key = input(f"  Enter your GEMINI_API_KEY [{masked_default}]: ").strip()
    if not gemini_key:
        gemini_key = default_gemini
        
    if gemini_key:
        if gemini_key.startswith("AIza"):
            print(f"  {GREEN}✔ Standard 'AIza' API Key detected.{RESET}")
        elif gemini_key.startswith("AQ"):
            print(f"  {GREEN}✔ New 'AQ' Authorization Key detected.{RESET}")
        else:
            print(f"  {YELLOW}⚠ Custom key prefix detected (proceeding as is).{RESET}")
    else:
        print(f"  {RED}Warning: No Gemini API Key provided. The agent will not function without it.{RESET}")
        
    # 2. BamBuddy URL
    print(f"\n{BOLD}🌐 2. BamBuddy API URL:{RESET}")
    print(f"  {CYAN}Description:{RESET} The HTTP URL of your BamBuddy control instance.")
    print(f"  {YELLOW}Note: BamBuddy defaults to port 8000 for their API.{RESET}")
    print("  - For local mock testing: use 'http://localhost:8001'")
    print("  - For live printer Pi:    use 'http://<your-pi-ip>:8000' (or the configured port)")
    default_url = existing.get("BAMBUDDY_URL", "http://localhost:8001")
    bambuddy_url = input(f"  Enter your BamBuddy API URL [{default_url}]: ").strip()
    if not bambuddy_url:
        bambuddy_url = default_url

    # 3. BamBuddy API Key (Optional)
    print(f"\n{BOLD}🔐 3. BamBuddy API Key (Optional):{RESET}")
    print(f"  {CYAN}Description:{RESET} The access key from your BamBuddy settings portal.")
    print("  Leave blank if API access key / basic auth is not configured.")
    default_bkey = existing.get("BAMBUDDY_API_KEY", "")
    bambuddy_key = input(f"  Enter BamBuddy API Key (optional) [{default_bkey or 'None'}]: ").strip()
    if not bambuddy_key and default_bkey:
        bambuddy_key = default_bkey

    # 4. Telegram Alerts (Optional)
    print(f"\n{BOLD}📢 4. Telegram Notifications (Optional):{RESET}")
    print("  Enable real-time push alerts from the agent to your phone.")
    print(f"  {CYAN}How to get Bot Token:{RESET}")
    print("    1. Search for @BotFather in Telegram.")
    print("    2. Send '/newbot', follow the steps, and copy the HTTP API Token.")
    default_tg_token = existing.get("TELEGRAM_BOT_TOKEN", "")
    tg_token = input(f"  Enter Telegram Bot Token [{default_tg_token or 'None'}]: ").strip()
    if not tg_token and default_tg_token:
        tg_token = default_tg_token

    if tg_token:
        print(f"\n  {CYAN}How to get Chat ID:{RESET}")
        print("    1. Search for @userinfobot or @GetIDsBot in Telegram.")
        print("    2. Start the bot to receive your numeric user/group Chat ID.")
        print("    3. Remember to press 'Start' on your own bot first!")
        default_tg_chat = existing.get("TELEGRAM_CHAT_ID", "")
        tg_chat = input(f"  Enter Telegram Chat ID [{default_tg_chat or 'None'}]: ").strip()
        if not tg_chat and default_tg_chat:
            tg_chat = default_tg_chat
    else:
        tg_chat = ""

    # Write configs
    print(f"\n[{CYAN}*{RESET}] Saving environment configuration to .env and app/.env...")
    
    env_content = f"""# BamBot Printer Agent Environment Variables
GEMINI_API_KEY={gemini_key}
GOOGLE_API_KEY={gemini_key}
BAMBUDDY_URL={bambuddy_url}
"""
    if bambuddy_key:
        env_content += f"BAMBUDDY_API_KEY={bambuddy_key}\n"
    if tg_token and tg_chat:
        env_content += f"TELEGRAM_BOT_TOKEN={tg_token}\nTELEGRAM_CHAT_ID={tg_chat}\n"

    with open(".env", "w") as f:
        f.write(env_content)
        
    with open("app/.env", "w") as f:
        f.write(f"# AI Studio Configuration\nGOOGLE_API_KEY={gemini_key}\nGEMINI_API_KEY={gemini_key}\nBAMBUDDY_URL={bambuddy_url}\n")
        if bambuddy_key:
            f.write(f"BAMBUDDY_API_KEY={bambuddy_key}\n")
        if tg_token and tg_chat:
            f.write(f"TELEGRAM_BOT_TOKEN={tg_token}\nTELEGRAM_CHAT_ID={tg_chat}\n")

    print(f"{GREEN}✔ Configuration files updated successfully.{RESET}")
    
    agent_port = configure_agent_port()
    return agent_port

def install_dependencies():
    print(f"\n{BOLD}[Step 2: Dependency Installation]{RESET}")
    print("Installing Python dependencies and setting up virtual environment...")
    
    try:
        # Run agents-cli install
        subprocess.run(["agents-cli", "install"], check=True)
        print(f"{GREEN}✔ Dependencies installed successfully.{RESET}")
    except Exception as e:
        print(f"{RED}Error installing dependencies: {e}{RESET}")
        print("Attempting fallback using uv sync...")
        try:
            subprocess.run(["uv", "sync"], check=True)
            print(f"{GREEN}✔ Dependencies synced successfully via uv.{RESET}")
        except Exception as ex:
            print(f"{RED}Failed to install packages: {ex}{RESET}")
            sys.exit(1)

def run_tests():
    print(f"\n{BOLD}[Step 3: Verification & Unit Tests]{RESET}")
    print("Running safety engine unit tests to verify installation...")
    try:
        subprocess.run(["uv", "run", "pytest", "tests/unit/test_safety.py"], check=True)
        print(f"{GREEN}✔ All safety unit tests passed successfully!{RESET}")
    except Exception:
        print(f"{RED}❌ Some unit tests failed. Please check your dependencies or agent configuration.{RESET}")

def print_usage_guide(agent_port):
    guide = f"""
{BLUE}{BOLD}======================================================================
                   🎉 Setup Completed Successfully! 🎉
======================================================================{RESET}

Here is how to run and use the BamBot Printer Agent:

{BOLD}1. Run the Mock Printer Server (for local testing):{RESET}
   If you do not have a live BamBuddy instance, run the mock server on port 8001:
   {GREEN}uv run uvicorn tests.mock_bambuddy:app --host 0.0.0.0 --port 8001{RESET}

{BOLD}2. Run the FastAPI Web Portal & Agent Server:{RESET}
   Start the main agent portal on port {agent_port}:
   {GREEN}uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port {agent_port}{RESET}

{BOLD}3. Use the Dashboard Web Portal:{RESET}
   Open your browser to:
   👉 {CYAN}{BOLD}http://localhost:{agent_port}{RESET}
   
   This dashboard gives you a full Glassmorphic interface featuring:
   - 💬 {BOLD}Chat Box{RESET}: Send instructions to the agent (e.g. "heat nozzle to 220" or "start benchy").
   - 📊 {BOLD}Telemetry Gauges{RESET}: Live nozzle temp, bed temp, completion percentage, and active print name.
   - 🚨 {BOLD}HITL Prompts{RESET}: Standard safety checklists pop up inside the UI automatically when starting prints.
   - 📈 {BOLD}Observability{RESET}: View real-time token tracking, Gemini costs, and active agent decision traces.

{BOLD}4. Run Unit and Integration Tests:{RESET}
   Ensure safety constraints are working correctly anytime you edit code:
   {GREEN}uv run pytest tests/unit/test_safety.py{RESET}

{BLUE}======================================================================{RESET}
"""
    print(guide)

def create_start_script(agent_port):
    # Helper start script to run both mock and app together in background
    start_sh_content = f"""#!/bin/bash
# Color definitions
GREEN="\\033[92m"
BLUE="\\033[94m"
YELLOW="\\033[93m"
RESET="\\033[0m"

echo -e "${{BLUE}}=========================================${{RESET}}"
echo -e "${{BLUE}}   Starting BamBot Agent Services...   ${{RESET}}"
echo -e "${{BLUE}}=========================================${{RESET}}"

# Kill any existing uvicorn processes on {agent_port} and 8001
echo "Cleaning up any stale servers on ports {agent_port}/8001..."
pkill -f "uvicorn.*{agent_port}" || true
pkill -f "uvicorn.*8001" || true

# Start Mock Printer Server
echo -e "Starting ${{YELLOW}}Mock BamBot API Server${{RESET}} on port 8001..."
uv run uvicorn tests.mock_bambuddy:app --host 0.0.0.0 --port 8001 > mock_bambuddy.log 2>&1 &
MOCK_PID=$!

# Wait for mock to boot
sleep 1.5

# Start FastAPI Portal
echo -e "Starting ${{YELLOW}}FastAPI Agent Web Portal${{RESET}} on port {agent_port}..."
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port {agent_port} > fast_api_app.log 2>&1 &
PORTAL_PID=$!

echo -e "${{GREEN}}✔ Both services successfully running in the background!${{RESET}}"
echo -e "- Mock Printer API:  ${{BLUE}}http://localhost:8001${{RESET}}"
echo -e "- Web Dashboard UI:  ${{BLUE}}http://localhost:{agent_port}${{RESET}}"
echo ""
echo "Logs are written to 'mock_bambuddy.log' and 'fast_api_app.log'."
echo -e "To stop both servers, run: ${{YELLOW}}kill $MOCK_PID $PORTAL_PID${{RESET}}"
echo -e "${{BLUE}}=========================================${{RESET}}"
"""
    with open("start.sh", "w") as f:
        f.write(start_sh_content)
    os.chmod("start.sh", 0o755)
    print(f"[{{GREEN}}✔{{RESET}}] Created helper script {{BOLD}}./start.sh{{RESET}} to run both servers simultaneously.")

def main():
    print_banner()
    check_python_version()
    check_dependencies()
    agent_port = configure_environment()
    install_dependencies()
    create_start_script(agent_port)
    run_tests()
    print_usage_guide(agent_port)

if __name__ == "__main__":
    main()
