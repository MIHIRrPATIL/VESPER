# 3-Tier Semantic Routing & Cognitive Planning Architecture

This document details the hybrid 3-tier intent classification, safety guardrail, and planning engine in VESPER. It explains how the system resolves user queries deterministically, semantically, and cognitively while eliminating false-positive keyword traps, avoiding dead duplicate code, conserving LLM token quotas, and protecting against hallucinations.

---

## 1. Problem Statement & Motivation

### Exhibit A: The False-Positive Keyword Co-occurrence Bug
In earlier iterations of VESPER's prefilter, camera perception relied on keyword co-occurrence:

```python
# FLAWED PATTERN:
if any(w in q_lower for w in ["camera", "webcam", "holding", "in front of"]) and any(w in q_lower for w in ["look", "see", "read", "ocr", "check", "inspect", "who"]):
    act = "ocr_webcam" if "ocr" in q_lower or "read" in q_lower else "inspect_webcam"
    return SwarmPlan(plan_type="parallel", steps=[{"agent": "vision", "action": act, "params": {"query": query}}])
```

#### Failure Mode
When a user asks:
> *"Who is holding the world record for the marathon?"*

1. The query contains `"holding"`.
2. The query contains `"who"`.
3. **Consequence**: Alfred erroneously concluded that the user was holding an object in front of the camera and dispatched `vision:inspect_webcam`, attempting to open the desk webcam and visually inspect a marathon runner through physical computer vision instead of querying web search.

#### Root Cause Analysis
Natural language frequently reuses verbs and participles in non-physical contexts (*"holding a record"*, *"holding a meeting"*, *"holding an opinion"*). Naive keyword sets cannot understand semantic relationships; adding negative keyword filters creates a fragile "whack-a-mole" cycle.

---

### Exhibit B: Dead Code Drift & Dual-Execution Redundancy
Previously, deterministic prefilters executed prior to the LLM call and returned immediately if matched. However, post-LLM logic re-implemented duplicate regex blocks. Having duplicate implementations across separate locations created silent logic drift.

---

### The Operational Constraint: Rate Limits & Token Economics
VESPER operates on Groq LPU inference with strict rate tiers (e.g., 2,000 Requests Per Day). Routing every minor intent through an LLM roundtrip burns quota rapidly, introducing 429 rate limit pressure and latency overhead (300–800ms).

The solution requires a **hybrid 3-tier architecture**:
1. **Tier 1**: Deterministic exact cache, proactive staged confirmations, and explicit hardware commands (<0.1ms, 0 tokens).
2. **Tier 2**: Local semantic embedding similarity router with hard negative contrast scoring (~10ms CPU, 0 tokens).
3. **Tier 3**: Cognitive LLM planning engine with structured JSON mode and post-planner safety guardrails.

---

## 2. The 3-Tier Hybrid Routing Pipeline

```
                               User Utterance
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        TIER 1: Deterministic Exact Cache & Hardware Perception          │
│        (<0.1ms, 0 Groq tokens, 0 API calls)                            │
│  • Active context lookups: "who sent that email" -> active_email sender │
│  • Proactive undo & staged action confirmations (15s windowing)         │
│  • Exact financial balance checks: "what's my bank balance"            │
│  • Explicit hardware nouns ("screen", "camera") + explicit verbs        │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ No Match
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        TIER 2: Local Semantic Similarity Router (all-MiniLM-L6-v2)      │
│        (~10ms on CPU, 0 Groq tokens, 0 API calls)                      │
│  1. Multi-Intent Guard: If query contains conjunctions -> yield to T3.  │
│  2. Acoustic Normalization: Strip wake words & speech fillers.          │
│  3. Single-Pass Matmul: s = V_bank * q against all 150+ prototypes.     │
│  4. Hard Negative Contrast: s_winner - s_NONE >= 0.02 (contrast margin)│
│  5. Calibrated Threshold Validation: s_winner >= tau_k                  │
│                                                                         │
│  "who is holding the world record for marathon" scores 0.083 -> REJECTED│
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ No Match / Contrast Penalty
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        TIER 3: Cognitive LLM Planning Engine & Safety Guardrails        │
│        (Structured JSON Mode + Post-Planner Verification)              │
│  • Complex multi-intent dispatch, research, media trivia, and general   │
│    conversational planning.                                             │
│  • Post-Planner Guardrails: Task title cleansing, email disambiguation,│
│    and mandatory web search enforcement for real-time/factual queries.  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tier 1: Deterministic Exact Cache & Hardware Routing

Tier 1 handles queries that require **zero linguistic ambiguity resolution**—operations that are purely cache lookups, staged action confirmations, or explicit hardware directives.

1. **Active Context Retrieval**:
   - Utterances like *"Who sent that email?"* retrieve `sender_name`, `sender`, and `subject` directly from `session_context["active_email"]` in 0.0ms.
2. **Proactive Staged Action Confirmations**:
   - Resolves unconfirmed actions in `action_queue` (e.g. user saying *"yes log that transaction"* or *"cancel that task"*).
3. **Explicit Hardware Perception**:
   - Screen perception strictly requires explicit target nouns (`"screen"`, `"monitor"`, `"display"`) AND explicit perception verbs (`"look"`, `"see"`, `"read"`, `"ocr"`, `"inspect"`).
   - Camera perception requires explicit camera hardware terms (`"camera"`, `"webcam"`) AND explicit perception verbs. Broad ambiguous tokens like `"holding"` are banished from Tier 1.

---

## 4. Tier 2: Local Semantic Embedding Router with Hard Negative Contrast

Implemented in [`backend/agent/semantic_router.py`](file:///home/mihir/Codes/VESPER/backend/agent/semantic_router.py), Tier 2 bridges the gap between brittle keyword regex and expensive cloud LLM inference.

### Technical Specifications
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors).
- **Inference Runtime**: ONNX Runtime via `fastembed` (C++ engine, zero PyTorch dependencies).
- **Latency**: Mean ~10.4ms on standard laptop CPU.
- **Token Cost**: 0 tokens, 0 network bandwidth, offline capable.

### Mathematical Formulation & Hard Negative Contrast
At initialization, prototype phrases across all 11 intent classes (including 29 adversarial `SemanticIntent.NONE` hard negatives) are embedded and stacked into a unit-normalized prototype matrix $\mathbf{V}_{\text{bank}} \in \mathbb{R}^{150 \times 384}$:

$$\mathbf{V}_{\text{bank}, i} = \frac{\mathbf{e}(P_{i})}{\|\mathbf{e}(P_{i})\|_2}$$

When a normalized query $q$ enters Tier 2, its embedding $\mathbf{q} \in \mathbb{R}^{384}$ is evaluated against the prototype bank via a single matrix-vector multiplication:

$$\mathbf{s} = \mathbf{V}_{\text{bank}} \mathbf{q} \quad \text{where } \mathbf{s} \in \mathbb{R}^{150}$$

The router extracts the highest score per candidate intent $s_{\text{winner}}$ and the highest score for hard negatives $s_{\text{NONE}}$:

$$s_{\text{winner}} = \max_{i \in \text{Intent}(k)} s_i, \quad s_{\text{NONE}} = \max_{j \in \text{Intent}(\text{NONE})} s_j$$

An intent is selected **only if**:
1. $s_{\text{winner}} \ge \tau_k$ (exceeds the intent threshold).
2. $s_{\text{winner}} - s_{\text{NONE}} \ge \text{contrast\_margin}$ (exceeds the closest hard-negative by at least $0.02$).

### Intent Definitions & Calibrated Thresholds

| Intent Class | Target Action | Threshold ($\tau$) | Prototypes |
| :--- | :--- | :--- | :--- |
| **`HANDHELD_OBJECT_RESEARCH`** | Sequential `ocr_webcam` $\to$ `research:web_search` | `0.50` | 25 prototypes |
| **`VERIFY_RESEARCH`** | Fresh `research:web_search` | `0.48` | 18 prototypes |
| **`EMAIL_THREAD`** | Parallel `email:read_thread` | `0.52` | 8 prototypes |
| **`UNREAD_EMAILS`** | Parallel `email:list_unread_emails` | `0.50` | 10 prototypes |
| **`SONG_ORIGIN`** | Sequential `media:get_playback_status` $\to$ `research:web_search` | `0.50` | 6 prototypes |
| **`DAILY_AGENDA`** | Parallel `tasks:get_daily_agenda` | `0.46` | 19 prototypes |
| **`FINANCE_BALANCE`** | Parallel `finance:get_balance` | `0.50` | 8 prototypes |
| **`SYSTEM_STATUS`** | Parallel `system:get_system_vitals` | `0.46` | 18 prototypes |
| **`MOBILE_NOTIFICATIONS`**| Parallel `tasks:list_mobile_notifications` | `0.48` | 12 prototypes |
| **`BATTERY_STATUS`** | Parallel `system:check_battery_status` | `0.50` | 10 prototypes |
| **`NONE` (Hard Negatives)**| Yields to Tier 3 Cognitive LLM Planner | `0.45` | 29 adversarial prototypes |

---

## 5. Tier 3: Cognitive LLM Planner & Safety Guardrails

When Tier 1 and Tier 2 yield, the utterance is processed by the Stage 1 Cognitive Planner ([backend/agent/planner.py](file:///home/mihir/Codes/VESPER/backend/agent/planner.py)) using dynamic capability prompts and structured JSON mode (`response_format={"type": "json_object"}`).

### Post-Planner Safety Guardrails

To prevent LLM non-determinism, all plans are filtered through 5 post-planner guardrails before execution:

1. **Schema Validation & Fallback**: Validates output against `SwarmPlan` Pydantic models. If steps are present but `plan_type == "direct"`, it coerces `plan_type` to `"parallel"`.
2. **Title Normalization & Action Retargeting**: Uses `build_action()` to strip conversational filler (`"remind me to buy milk"` $\to$ title: `"Buy milk"`). Maps non-standard actions (`create_task`, `add_reminder`) to canonical specialist endpoints (`add_task`, `set_reminder`, `schedule_event`).
3. **Personal Correspondence Disambiguation**: Intercepts personal inbox inquiries (*"did I hear back from Rohit?"*) and overrides erroneous web search steps to `email:search_emails`.
4. **Hallucination & Factual Search Guardrail**: Scans queries for factual triggers (`is_explicit_search`, `is_realtime_data`, `is_media_trivia`, `is_entity_lookup`, `is_open_research`, `is_verify_request`). If the LLM generates a direct response without tools, the guardrail injects `research:web_search`.
5. **Recipient Validation**: Verifies recipient email syntax via `is_valid_email()`. Halts execution and requests domain completions for incomplete handles.

---

## 6. Regression Verification

The 3-tier routing architecture and safety guardrails are verified by automated test suites in [`backend/tests/test_agent.py`](file:///home/mihir/Codes/VESPER/backend/tests/test_agent.py):

```bash
$ .venv/bin/pytest backend/tests/test_agent.py backend/tests/test_hardening_pillars.py
============================= 42 passed in 88.24s ==============================
```
