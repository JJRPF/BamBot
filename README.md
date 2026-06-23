# BamBot 3D Printer AI Assistant & Dashboard

BamBot is a premium, AI-powered control center and web portal designed specifically for the **Bambu Lab X1 Carbon (X1C)** 3D printer. It integrates a state-of-the-art interactive AI assistant powered by the **Google Agent Development Kit (ADK)** and the Gemini API, alongside a modern dark-themed web dashboard for real-time printer telemetry and management.

---

## Important Notice: Real API vs. Mock API

> [!IMPORTANT]
> This repository includes a simulated mock API (`mock_bambuddy.py`) which is designed for **testing and demonstration purposes only**.
> In a production/real environment, the `BAMBUDDY_URL` in your `.env` configuration should be pointed to a **real BamBuddy API server** connected to your physical Bambu Lab printer.

---

## Key Features

### 1. Interactive AI Chat & Multiple Sessions
*   **Multi-Chat Workspace**: Create, delete, and switch between separate chat sessions with independent conversation histories.
*   **Context-Aware Follow-Ups**: The agent dynamically resolves follow-up requests (e.g., replying with "yes", "download it", or "go ahead") by analyzing the conversation history.
*   **Intelligent ID Extraction**: Automatically extracts downloaded filenames or searched model IDs from previous messages to perform subsequent operations without requiring manual inputs.

### 2. Slicing & Compound Query Flows
*   **Single-Turn Automation**: Execute complex requests in one step (e.g., `"find a benchy then slice with default settings and print it"`). The agent searches unified model mirrors, downloads the STL, runs OrcaSlicer, uploads the result, and initiates safety checklists.
*   **Slicer 3MF Containerization**: OrcaSlicer CLI is configured to package raw G-code and metadata inside a valid `.gcode.3mf` ZIP container, complying with network-mode printing rules for Bambu Lab printers.
*   **Library Slicing**: Slice STL or 3MF models stored directly in the printer library by downloading and processing them automatically.

### 3. Human-in-the-Loop (HITL) Print Safety
*   **Bed Clearance & Chamber Door Checks**: Prints cannot be executed without checking the physical bed and chamber door (especially for temperature-sensitive filaments like ABS/ASA).
*   **Filament AMS Mapping**: Interactive dropdown selectors in the checklist allow users to map sliced virtual filament channels to active physical AMS slots or external spools.
*   **Metadata Integration**: The safety confirmation card renders estimated print times and filament weights directly extracted from OrcaSlicer metadata.
*   **Strict Security Boundaries**: Approvals are reset whenever a new print command is initiated or when a print job successfully starts, ensuring safety checks are never bypassed.

### 4. Live Telemetry Dashboard
*   **Real-time Monitoring**: Visual indicators for nozzle temperature, bed temperature, and print progress.
*   **Filament Inventory**: Integrated with Spoolman, presenting real-time filament spools, materials, remaining weights, and color markers.
*   **Telemetry Logs**: Real-time logging of tool executions, model decisions, and printer actions.

---

## Project Structure

```
capstone/
├── app/                      # Core FastAPI Application
│   ├── agent.py              # Main Agent logic & Workflow Graphs
│   ├── fast_api_app.py       # FastAPI Server and WebSocket endpoints
│   ├── static/               # Frontend Assets (HTML, CSS, JS)
│   └── app_utils/            # Client wrappers & Telemetry helpers
├── tests/                    # E2E Playwright and Unit tests
│   ├── mock_bambuddy.py      # Mock printer API server (for testing/demo only)
│   ├── integration/          # Integration & E2E tests
│   └── unit/                 # Unit tests for agent & safety nodes
├── bambuddy_mcp.py           # MCP (Model Context Protocol) Server for Slicer & Printer
├── GEMINI.md                 # Development constraints & commands
├── pyproject.toml            # Project dependencies and configuration
└── start.sh                  # Bootstrap script for local dev
```

---

## Getting Started

### Prerequisites

Ensure you have the following installed:
1.  **Python 3.12+**
2.  **uv** (Python package manager): [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
3.  **OrcaSlicer**: Can be installed manually or configured using our automatic setup script.
4.  **Google Cloud SDK / ADK**: Install the tool: `uv tool install google-agents-cli`.

### Configuration

You can configure the project easily using the interactive setup scripts:

1.  **Configure BamBot Agent**:
    Run the main setup script to verify dependencies, configure ports, endpoints, and API keys:
    ```bash
    uv run python setup.py
    ```

2.  **Install & Configure OrcaSlicer**:
    Run the slicer setup script to automatically install OrcaSlicer (via Homebrew on macOS or Flatpak/AppImage on Linux), verify paths, and generate default preset profile configurations:
    ```bash
    uv run python setup_orcaslicer.py
    ```


Alternatively, you can manually create a `.env` file in the root directory:

```ini
# BamBot API Configurations
BAMBUDDY_URL=http://localhost:8001
BAMBUDDY_API_KEY=your-api-key

# Gemini API Configurations
GOOGLE_API_KEY=your-gemini-api-key
GEMINI_API_KEY=your-gemini-api-key
```

### Quick Local Start

Use the bootstrap script to clean up ports and start both the **Mock Printer API** and the **FastAPI Agent Web Portal**:

```bash
chmod +x start.sh
./start.sh
```

Once running:
*   **Web Dashboard UI**: [http://localhost:8000](http://localhost:8000)
*   **Mock Printer API**: [http://localhost:8001](http://localhost:8001)

---

## Running Tests

Automated testing is configured via Pytest, covering unit tests, agent workflows, and full-browser E2E scenarios using Playwright.

Install testing dependencies:
```bash
uv pip install pytest pytest-asyncio playwright
uv run playwright install chromium
```

Run all tests:
```bash
uv run pytest
```

---

## CLI Command Cheat Sheet

| Command | Purpose |
|---------|---------|
| `agents-cli playground` | Launch local developer sandbox |
| `agents-cli lint` | Check code styling and quality |
| `agents-cli eval generate` | Generate evaluation traces |
| `agents-cli eval grade` | Run LLM-as-judge evaluations |
| `uv run pytest tests/unit` | Run unit tests |
| `uv run pytest tests/integration` | Run integration/E2E tests |
| `./start.sh` | Run all services locally in background |
