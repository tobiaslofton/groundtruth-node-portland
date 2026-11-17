# GroundTruth Protocol: Physical Agency Layer for Autonomous AI Agents

> **Node #001: Portland Metro Genesis Node (Experimental Proof-of-Concept)**

## 1. The Core Thesis: Breaking the Reality Boundary
Autonomous AI agents have mastered code generation, web research, and digital API orchestration, but they remain completely blind and paralyzed at the physical boundary. 

Digital records on the open web lag physical reality by weeks or months. When online data is conflicting, stale, or non-existent, software agents have zero physical agency to verify facts on the ground.

The **GroundTruth Protocol** is an open proof-of-concept providing standardized **Model Context Protocol (MCP)** and REST interfaces that grant autonomous agents physical agency—allowing them to asynchronously command real-world human verification nodes to audit physical spaces, inspect assets, and extract non-digitized data.

---

## 2. Node #001 (Portland Genesis Node)
Node #001 is a live, reference implementation operating in the Portland, Oregon metropolitan area (Multnomah, Clackamas, and Washington counties).

It proves that an autonomous agent can:
1. Detect real-world data ambiguity during execution.
2. Dispatches an asynchronous physical task without blocking its runtime loop.
3. Alert a verified local Human-in-the-Loop (HITL) operator with structured questions.
4. Ingest timestamped, GPS-verified photo proof and structured key-value facts directly back into its context graph.

---

## 3. Terms of the Proof-of-Concept & Operator Discretion
* **Cost:** $0.00 (Fully subsidized research experiment for agent builders and researchers).
* **Absolute Operator Discretion:** Because this is an open research node, the human operator exercises complete sovereign right of refusal. Any task deemed unsafe, absurd, invasive, residential, or physically unreasonable is declined with a single tap.
* **Negative Feedback is Protocol Data:** An agent must learn to handle physical refusal gracefully. When a task is declined, the agent receives a structured refusal reason to test its adaptive recovery logic.
* **Physical Boundaries:** Strictly limited to public commercial frontage, storefronts, and open public records. Private residential properties and covert surveillance are strictly forbidden.

---

## 4. Architecture & Interface

```
[ Autonomous AI Agent ] 
     │ (Calls FastMCP or REST endpoint)
     ▼
[ GroundTruth Protocol Node #001 ]
     │ 1. Instant Non-Blocking Receipt (prevents agent timeout)
     │ 2. Deduplication & Anti-Loop Hash Filter
     │ 3. Pushes Dispatch Card to Telegram
     ▼
[ Human Operator (Phone) ]
     ├──► [ ❌ Decline ] ──► Returns structured refusal to Agent
     └──► [ ✅ Accept ]  ──► Captures photo on-site & returns EXIF-verified proof
```

### Installation for Developers (Claude Desktop / Cursor)
```json
{
  "mcpServers": {
    "groundtruth-portland": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "C:/path/to/portland-ground-truth-pilot"
    }
  }
}
```

### REST Endpoints
* `GET /llms.txt` — Machine-readable manifesto and API instructions for web-searching agents.
* `POST /v1/dispatch/storefront` — Commercial property audit dispatch.
* `POST /v1/dispatch/custom` — Custom physical actuation proposal.
* `GET /v1/tasks/{task_id}` — Poll task status, proof photo URL, and extracted facts.
