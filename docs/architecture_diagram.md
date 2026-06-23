# BamBot Architecture Overview

The following diagram illustrates the relationship between the BamBot Agent, the FastAPI Web Dashboard, the Gemini-powered ADK workflow engine, the Model Context Protocol (MCP) server, OrcaSlicer, and the physical printer API interfaces.

```mermaid
graph TD
    %% Styling Classes
    classDef client fill:#1a1b26,stroke:#7aa2f7,stroke-width:2px,color:#a9b1d6;
    classDef server fill:#24283c,stroke:#bb9af7,stroke-width:2px,color:#c0caf5;
    classDef ai fill:#1f2335,stroke:#2ac3de,stroke-width:2px,color:#9ece6a;
    classDef extern fill:#1c1d21,stroke:#f7768e,stroke-width:2px,color:#db4b4b;

    %% Components
    subgraph UI ["User Interface (Client)"]
        Browser["Dashboard UI <br> (HTML/CSS/JS)"]
    end
    class Browser client;

    subgraph Backend ["FastAPI Web Portal & Server"]
        App["FastAPI Server <br> (fast_api_app.py)"]
        DB[("SQLite Database <br> (bambot_agent.db)")]
    end
    class App,DB server;

    subgraph AgentEngine ["AI Agent Engine (Google ADK)"]
        Agent["Gemini Agent <br> (agent.py)"]
        Workflow["State Graph Workflow <br> (Search -> Slice -> HITL -> Print)"]
    end
    class Agent,Workflow ai;

    subgraph MCPLayer ["Model Context Protocol (MCP)"]
        MCPServer["FastMCP Server <br> (bambuddy_mcp.py)"]
        Orca["OrcaSlicer CLI <br> (Slicer Executable)"]
        Presets[("System Presets <br> (BBL Profiles)")]
    end
    class MCPServer,Orca,Presets server;

    subgraph Hardware ["Printer API & Services"]
        BamBuddy["BamBuddy API <br> (Real/Mock on Pi)"]
        Spoolman["Spoolman API <br> (Filaments)"]
        Printer["Bambu Lab X1C"]
    end
    class BamBuddy,Spoolman,Printer extern;

    %% Relationships
    Browser <-->|WebSockets & HTTP REST| App
    App <-->|CRUD Chat & Sessions| DB
    App <-->|Run Loop/Context| Agent
    Agent <-->|Transition States| Workflow
    Workflow <-->|Call Tooling| MCPServer
    
    MCPServer <-->|CLI Invocation| Orca
    Orca <-->|Load Profiles| Presets
    Orca -->|Generate .gcode.3mf| MCPServer
    
    MCPServer <-->|Fetch/Send JSON & G-code| BamBuddy
    MCPServer <-->|Inventory| Spoolman
    BamBuddy <-->|MQTT / FTP Connect| Printer
```

## Component Details

### 1. Dashboard UI (Frontend)
*   **Web Portal**: Styled with a dark glassmorphic theme. Displays live telemetry (temps, print progress), active chat sidebar (multi-session history), active agent decision logs, and human-in-the-loop (HITL) prompt forms.
*   **Real-time Communication**: Links to the backend via REST for managing sessions and WebSockets for active chat execution and live telemetry updates.

### 2. FastAPI Backend
*   **Session Management**: Stores chat messages, active sessions, and printer telemetry logs inside `bambot_agent.db`.
*   **Agent Execution**: Hosts the Google ADK runner in a thread pool, managing execution context and passing messages back to the WebSocket connection.

### 3. AI Agent (Google ADK & Gemini)
*   **Workflow Graph**: Configures a directed state graph containing:
    *   `search_slice_print_node`: Chain-executes search, downloads, and slicing parameters.
    *   `safety_check_node`: Evaluates printer state and triggers the HITL safety confirmation card.
    *   `send_printer_command_node`: Directly dispatches commands after confirmation is approved.
*   **Dynamic Context Engine**: Evaluates conversation logs to parse follow-ups (e.g. "yes", "go ahead") and map appropriate model IDs or file targets.

### 4. FastMCP Server
*   **Encapsulated Tools**: Exposes direct Python operations as standard MCP tools (`get_printer_status`, `slice_model_file`, `download_3d_model`).
*   **OrcaSlicer Pipeline**: Launches the OrcaSlicer executable dynamically with loaded BBL system profiles (`.json`) to generate `.gcode.3mf` zip container prints.

### 5. Printer & Services Layer
*   **BamBuddy**: Acts as the printer-connected controller interface. Communicates directly with the printer hardware via FTP and local MQTT connections.
*   **Spoolman**: Serves as the database interface tracking materials and filament weights.
