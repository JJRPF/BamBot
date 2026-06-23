# Kaggle Course Whitepapers: Key Architecture Reference

This reference document compiles the core architectural patterns and principles from the 5 course whitepapers from Kaggle's 5-Day AI Agents Intensive.

---

## 1. The New SDLC with Vibe Coding
*   **Vibe Coding vs. Agentic Engineering**: Vibe coding is natural language prompting without rigorous validation, suitable for prototyping. Agentic engineering is the disciplined software engineering paradigm using constraints, tests, and human-in-the-loop checkpoints.
*   **Agent = Model (10%) + Harness (90%)**: The LLM is the reasoning core, but the surrounding architecture (instructions, tool sets, sandboxes, safety predicates, observability logs) provides the reliability.
*   **Developer as Orchestrator**: The developer's role shifts from writing syntax to specifying architecture, curating the harness, defining test criteria, and verifying outputs.

---

## 2. Agent Tools & Interoperability (MCP)
*   **Standardization**: Standardize integration points using the Model Context Protocol (MCP). This separates the reasoning agent from raw data connectors or hardware controllers.
*   **Decoupled Architecture**: Build modular MCP servers that expose clean, self-documenting JSON schemas for tools, making it easy for models to discover capabilities and reason about execution boundaries.

---

## 3. Agent Skills (Portable Context)
*   **Context Engineering**: Avoid context window bloat by packaging capabilities into portable, domain-specific directories ("Agent Skills") centered around a `SKILL.md` file.
*   **On-Demand Tool Loading**: General-purpose agents should dynamically load these specialized skill blocks only when the workflow transitions to that domain, reducing noise and API costs.

---

## 4. Vibe Coding Security and Evaluation
*   **Effective Trust Architecture**: Implement guardrails to handle non-deterministic outputs:
    1.  *Ephemeral Sandboxing*: Execute generated actions or tests in isolated runtime environments.
    2.  *Safety Predicates (Rules)*: Check commands before executing them (e.g., verifying that active print instructions do not exceed maximum threshold values).
    3.  *Human-in-the-Loop (HITL)*: Require explicit human confirmation for high-risk actions (e.g., executing a brand-new untrusted G-code file or remote server deployment).
*   **Trajectory Evaluation**: Track the agent's chain-of-thought, tool invocations, and errors to detect drift.

---

## 5. Spec-Driven Development (SDD)
*   **Disposable Code, Persistent Specs**: Treat generated application code as disposable and easily replaceable. Focus on keeping the specifications (Gherkin/BDD or schema definitions) and test suites persistent and human-reviewed.
*   **Validation First**: Always write automated tests or validation steps to check that the agent's generated solution fits the specified behavior before declaring a task done.
