# BamBot Agent Architecture (State Graph Workflow)

The diagram below details the internal state machine graph of the **BamBot Agent** defined in `app/agent.py`. It shows how incoming user messages are routed between search, slicing, safety evaluations, and command execution states.

```mermaid
graph TD
    %% Styling Classes
    classDef input fill:#1a1b26,stroke:#7aa2f7,stroke-width:2px,color:#a9b1d6;
    classDef routing fill:#24283c,stroke:#bb9af7,stroke-width:2px,color:#c0caf5;
    classDef node fill:#1f2335,stroke:#2ac3de,stroke-width:2px,color:#9ece6a;
    classDef hitl fill:#343a40,stroke:#f7768e,stroke-width:2px,color:#db4b4b;

    %% Nodes
    UserInput([User Input Query])
    History[(Chat History Context)]
    
    %% Router Node
    Router{"Agent Routing Logic <br> (Gemini LLM / Schema Match)"}
    
    %% Graph Nodes
    BlockNode["General Chat Node <br> (block_response_node)"]
    CompoundNode["Compound Print Node <br> (search_slice_print_node)"]
    SafetyNode["Safety Check Node <br> (safety_check_node)"]
    CommandNode["Command Node <br> (send_printer_command_node)"]
    
    HITLCard{{"Render Dashboard HITL Card <br> (Awaiting Bed/Door/Filament)"}}

    class UserInput input;
    class History routing;
    class Router routing;
    class BlockNode,CompoundNode,SafetyNode,CommandNode node;
    class HITLCard hitl;

    %% Workflow Edges
    UserInput --> Router
    History --> Router
    
    %% Primary Router Decisions
    Router -->|General query / FAQs| BlockNode
    Router -->|Compound print action| CompoundNode
    Router -->|Standard print command| SafetyNode
    Router -->|Direct control: pause/heat| CommandNode

    %% Compound Workflow Transitions
    CompoundNode -->|Fail: Model not found| BlockNode
    CompoundNode -->|Success: Model Sliced| SafetyNode

    %% Safety Checks & HITL Bounds
    SafetyNode -->|Safety Check Failed / New Job| HITLCard
    HITLCard -->|User Approves / Sends 'yes'| SafetyNode
    SafetyNode -->|Safety Bounds Met| CommandNode

    %% Final Command Execution
    CommandNode -->|Reset Safety State| History
    CommandNode -->|Dispatched to Printer| UserInput
```

## Detailed Node Functions

### 1. Agent Routing Logic
*   **Context Evaluation**: Inspects the incoming prompt alongside the session's chat history.
*   **Action Mapping**: Evaluates the schema definitions to map queries to registered tools or state nodes. Short answers (like "yes", "sure", "cancel") are matched against the previous agent turn in the history to proceed with the pending action.

### 2. General Chat Node (`block_response_node`)
*   Provides standard conversation outputs, general explanations, and FAQ troubleshooting tips.
*   Optionally calls the `query_3d_printing_knowledge` MCP tool to search the local troubleshooting directory.

### 3. Compound Print Node (`search_slice_print_node`)
*   Runs a multi-step pipeline inside a single turn:
    1.  **Search**: Queries `search_3d_models` to locate candidate files.
    2.  **Download**: Automatically triggers `download_3d_model` using the matched model ID.
    3.  **Slicing**: Executes the `slice_model_file` MCP tool to invoke OrcaSlicer on the downloaded file.
*   If any stage fails, it redirects to the `block_response_node` to output the exact error (e.g. Slicer presets missing). If it succeeds, it automatically forwards the resulting `.gcode.3mf` filename to the `safety_check_node`.

### 4. Safety Check Node (`safety_check_node`)
*   **Approval Reset**: Automatically resets the session-scoped safety values (`bed_cleared`, `door_closed`) on every fresh print query to guarantee safety checks cannot be bypassed.
*   **Verification Check**: Checks the physical status of the chamber door (closed status is enforced if printing high-temp materials like ABS/ASA) and bed clearance.
*   **HITL Interrupt**: If safety conditions are not verified, it stops graph execution, suspends the print command, and yields an interrupt event to the frontend to render the interactive safety checklist card.

### 5. Command Node (`send_printer_command_node`)
*   Invokes the `send_printer_command` MCP tool to communicate with the BamBuddy API (e.g., executing `start_print`).
*   **Reset Hook**: Once a print command successfully executes, it immediately clears the safety verification status, requiring any subsequent print job to complete a new safety check.
