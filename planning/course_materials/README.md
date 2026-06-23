# 5-Day AI Agents Intensive Course with Google

Welcome! This repository contains my personal notes, code, and solutions for the **5-Day AI Agents Intensive Course** hosted by Google.

This 5-day online program, crafted by Google’s ML researchers and engineers, helps developers explore the foundations and practical applications of AI agents.

## Course Overview

The curriculum is designed to move from foundational concepts to building production-ready systems. Each day blends conceptual deep dives, hands-on codelabs, and live discussions.

**Key concepts covered:**

  * Core agent components: **Models, Tools, Orchestration, Memory, and Evaluation**.
  * Agent Ops: Reliability, governance, and security.
  * Practical application: Building agents with the **Agent Development Kit (ADK)** and **Gemini**.
  * Interoperability: Using the **Model Context Protocol (MCP)** for complex, long-running operations.

-----

## Technologies & Tools

  * **Core Model:** Google Gemini
  * **Framework:** Agent Development Kit (ADK)
  * **Protocol:** Model Context Protocol (MCP)
  * **Platform:** Kaggle (for Codelabs)
  * **Language:** Python
  * **Support Tool:** NotebookLM

-----

## Daily Assignments & Curriculum

This section tracks the daily assignments and materials from the course.

### Day 1: Introduction to Agents

  * **Topic:** Introduces a taxonomy of agent capabilities, the need for an "Agent Ops" discipline, and the importance of interoperability and security.
  * **Whitepaper:** [Introduction to Agents](https://github.com/sdivyanshu90/5-Day-AI-Agents-Intensive-Course-with-Google/blob/39fe09e63a28f244b75fd674c8b261c4a3730444/Day%201/whitepaper/Day_1_v4.pdf)
  * **Podcast:** [Unit 1 Summary (via NotebookLM)](https://www.youtube.com/watch?v=zTxvGzpfF-g)
  * **Codelabs (Kaggle):**
    1.  [Build your first agent using Gemini and ADK](https://www.kaggle.com/code/kaggle5daysofai/day-1a-from-prompt-to-action)
    2.  [Build your first multi-agent systems using ADK](https://www.kaggle.com/code/kaggle5daysofai/day-1b-agent-architectures)
  * **Resources:**
      * [Codelab Troubleshooting Guide](https://www.kaggle.com/code/kaggle5daysofai/day-0-troubleshooting-and-faqs)
      * **Note:** Kaggle account phone verification is required for codelabs.

### Day 2: Agent Tools & Interoperability (MCP)

  * **Topic:** Focuses on external tools and functions that allow an agent to perform actions or retrieve real-time data. Introduces the Model Context Protocol (MCP) for complex operations.
  * **Whitepaper:** [Agent Tools & Interoperability with Model Context Protocol (MCP)](https://github.com/sdivyanshu90/5-Day-AI-Agents-Intensive-Course-with-Google/blob/39fe09e63a28f244b75fd674c8b261c4a3730444/Day%202/whitepaper/Day_2_v6.pdf)
  * **Podcast:** [Unit 2 Summary (via NotebookLM)](https://www.youtube.com/watch?v=Cr4NA6rxHAM)
  * **Codelabs (Kaggle):**
    1.  [Explore new ways to add tools to extend what your agents can do](https://www.kaggle.com/code/kaggle5daysofai/day-2a-agent-tools)
    2.  [Explore best practices for tools, including MCP and long-running operations](https://www.kaggle.com/code/kaggle5daysofai/day-2b-agent-tools-best-practices)

### Day 3: Context Engineering: Sessions & Memory

  * **Topic:** Focuses on context engineering, the practice of dynamically assembling and managing information in an agent's context window. Defines Sessions (immediate history) and Memory (long-term persistence) to create stateful, personalized AI experiences.
  * **Whitepaper:** [Context Engineering: Sessions & Memory](https://github.com/sdivyanshu90/5-Day-AI-Agents-Intensive-Course-with-Google/blob/39fe09e63a28f244b75fd674c8b261c4a3730444/Day%203/whitepaper/Day_3.pdf)
  * **Podcast:** [Unit 3 Summary (via NotebookLM)](https://www.youtube.com/watch?v=FMcExVE15a4)
  * **Codelabs (Kaggle):**
    1.  [Implement Sessions to manage immediate context in your agents](https://www.kaggle.com/code/divanshu22/day-3a-agent-sessions)
    2.  [Implement Memory to create long-term, personalized experiences](https://www.kaggle.com/code/divanshu22/day-3b-agent-memory)

### Day 4: Agent Quality

  * **Topics:** Focuses on agent quality assurance using a holistic evaluation framework. Covers the technical foundation of Observability (Logs, Traces, Metrics) and scalable feedback loops like LLM-as-a-Judge and Human-in-the-Loop (HITL).
  * **Whitepaper:** [Agent Quality](https://github.com/sdivyanshu90/5-Day-AI-Agents-Intensive-Course-with-Google/blob/0ed65af3a6bfe8d17e281b1618233e9f6791cd75/Day%204/whitepaper/Day_4.pdf)
  * **Podcast:** [Unit 4 Summary (via NotebookLM)](https://www.youtube.com/watch?v=LFQRy-Ci-lk)
  * **Codelabs (Kaggle):**
    1.  [Implement observability to help you debug your agents.](https://github.com/sdivyanshu90/5-Day-AI-Agents-Intensive-Course-with-Google/blob/0ed65af3a6bfe8d17e281b1618233e9f6791cd75/Day%204/notebooks/day-4a-agent-observability.ipynb)
    2.  [Evaluate your agents.](https://github.com/sdivyanshu90/5-Day-AI-Agents-Intensive-Course-with-Google/blob/0ed65af3a6bfe8d17e281b1618233e9f6791cd75/Day%204/notebooks/day-4b-agent-evaluation.ipynb)

### Day 5: Prototype to Production

  * **Topics:** Focuses on the operational lifecycle of AI agents (deployment, scaling, productionization) and transitioning prototypes to enterprise-grade solutions. Covers multi-agent systems using the Agent2Agent (A2A) Protocol and deploying agents to Vertex AI Agent Engine.
  * **Whitepaper:** [Prototype to Production](https://www.kaggle.com/whitepaper-prototype-to-production)
  * **Podcast:** [Unit 5 Summary (via NotebookLM)](https://www.youtube.com/watch?v=8Wyt9l7ge-g)
  * **Codelabs (Kaggle):**
    1.  [Explore how to use A2A Protocol to have agents interact with each other](https://www.kaggle.com/code/divanshu22/day-5a-agent2agent-communication)
    2.  [\[Optional\] Deploy your agent to Agent Engine on Google Cloud.](https://www.kaggle.com/code/divanshu22/day-5b-agent-deployment)

-----

## Acknowledgement & Disclaimer

This repository is for **personal learning and educational purposes only**.

All course materials, including whitepapers, codelabs, podcasts, and any other associated content, are the intellectual property of **Google** and **Kaggle**. All rights, licenses, and acknowledgements are held by them. This repository does not claim any ownership of the original course content.