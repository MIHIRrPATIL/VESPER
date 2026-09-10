# 3-Tier Semantic Routing & Cognitive Planning Architecture

This document details the hybrid 3-tier intent classification and planning engine in VESPER: how the system resolves user queries deterministically, semantically, and cognitively while eliminating false-positive keyword traps, avoiding dead duplicate code, and conserving LLM token quotas.

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

1. The query contains `"holding"` (List 1).
2. The query contains `"who"` (List 2).
3. **Consequence**: Alfred erroneously concluded that the user was holding an object in front of the camera and dispatched `vision:inspect_webcam`, attempting to open the desk webcam and visually inspect a marathon runner through physical computer vision instead of querying Wikipedia or web search.

#### Root Cause Analysis
Natural language frequently reuses verbs and participles in non-physical contexts (*"holding a record"*, *"holding a meeting"*, *"holding an opinion"*). Naive keyword sets and regex nets cannot understand semantic relationships; adding negative keyword filters only creates a fragile "whack-a-mole" cycle.

---

### Exhibit B: Dead Code Drift & Dual-Execution Redundancy
Previously, `_check_deterministic_prefilter` executed prior to the LLM call and returned immediately if matched. However, `create_plan` re-implemented identical regex blocks *after* the LLM call for:
1. Screen perception (`inspect_screen`, `ocr_screen`)
2. Handheld object OCR $\to$ research (`_is_holding_info`)
3. Direct webcam inspection (`inspect_webcam`, `ocr_webcam`)
4. Music + movie chaining (`get_playback_status` $\to$ `web_search`)
5. Email thread inspection (`read_thread`)
6. Who sent email (session context lookup)

#### Failure Mode
Because `_check_deterministic_prefilter` already intercepted and returned on those categories, the post-LLM copies were **unreachable dead code**. Worse, having duplicate regex implementations across two separate locations created silent logic drift (such as key mismatches between `"agent"` and `"action"`).

---

### The Operational Constraint: Rate Limits & Token Economics
VESPER operates on Groq LPU inference with strict rate tiers (e.g., 2,000 Requests Per Day / 100,000 Tokens Per Day on developer tiers). Routing every minor intent through an LLM roundtrip burns quota rapidly, introducing 429 rate limit pressure and latency overhead (300–800ms).

The solution requires a **hybrid 3-tier architecture**:
1. **Tier 1**: Deterministic exact cache and hardware commands (0ms, 0 tokens).
2. **Tier 2**: Local semantic embedding similarity router (~10ms CPU, 0 tokens, 0 API calls).
3. **Tier 3**: Cognitive LLM planning engine for genuinely open-vocabulary reasoning.

---

## 2. The 3-Tier Hybrid Routing Pipeline

```
                              User Utterance
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        TIER 1: Deterministic Exact Cache & Hardware Perception          │
│        (<0.1ms, 0 Groq tokens, 0 API calls)                            │
│  • Session context cache lookups: "who sent that email"                 │
│  • Exact financial balance checks: "what's my bank balance"            │
│  • Explicit hardware nouns: ("screen"/"monitor" or "camera"/"webcam")   │
│    combined with explicit perception verbs ("look", "read", "ocr")     │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ No Match
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        TIER 2: Local Semantic Similarity Router (all-MiniLM-L6-v2)      │
│        (~10ms on CPU, 0 Groq tokens, 0 API calls)                      │
│  • Vector cosine similarity against canonical prototype matrices:       │
│    - HANDHELD_OBJECT_RESEARCH (threshold: 0.60)                         │
│    - VERIFY_RESEARCH ("no try again", "wrong") (threshold: 0.55)        │
│    - EMAIL_THREAD ("check full thread") (threshold: 0.58)               │
│    - SONG_ORIGIN ("what movie is this song from") (threshold: 0.60)    │
│                                                                         │
│  "who is holding the world record for marathon" scores 0.083 -> REJECTED│
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ No Match
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        TIER 3: Cognitive LLM Planning Engine (Groq / OpenRouter)        │
│        (Structured JSON Mode + Few-Shot In-Context Prompting)           │
│  • Complex multi-intent dispatch, research, media trivia, and general   │
│    conversational planning.                                             │
│  • Cleaned of all dead duplicate post-LLM regex blocks.                │
│  • Safety fallback: enforces web search if LLM generates direct text   │
│    on an explicit search query.                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tier 1: Deterministic Exact Cache & Hardware Routing

Tier 1 handles queries that require **zero linguistic ambiguity resolution**—operations that are purely cache lookups or unambiguous hardware directives.

### 1. Active Context Sender Retrieval
- **Utterance**: *"Who sent that email?"*, *"Who sent it?"*, *"Who was that email from?"*
- **Mechanism**: Bypasses intent classification entirely. Retrieves `sender_name`, `sender`, and `subject` directly from `session_context["active_email"]`.
- **Response**: Generates a direct response in 0.0ms:
  > *"The email we were discussing was sent by Dr. Bruce Banner (banner@stark.com) regarding 'Gamma radiation report', sir."*

### 2. Direct Account Balance
- **Utterance**: *"What's my balance?"*, *"Check my bank balance"*, *"How much money do I have?"*
- **Mechanism**: Matches explicit balance regex $\to$ routes to `finance:get_balance`.

### 3. Explicit Hardware Perception
- **Screen Perception**: Strictly requires an explicit screen target (`"screen"`, `"monitor"`, `"display"`, `"desktop"`, `"ide"`) AND an explicit perception verb (`"look"`, `"see"`, `"read"`, `"ocr"`, `"inspect"`).
- **Webcam Perception**: Strictly requires explicit camera hardware terms (`"camera"`, `"webcam"`) AND an explicit perception verb.
  * *Crucial Difference*: Broad tokens like `"holding"`, `"in front of"`, and `"who"` are strictly banished from Tier 1.

---

## 4. Tier 2: Local Semantic Similarity Router

Implemented in [`backend/agent/semantic_router.py`](file:///home/mihir/Codes/VESPER/backend/agent/semantic_router.py), Tier 2 bridges the gap between brittle keyword regex and expensive cloud LLM inference.

### Technical Specifications
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense vectors).
- **Inference Runtime**: ONNX Runtime via `fastembed` (no PyTorch dependencies, pure C++ engine).
- **Latency**: Mean ~10.4ms on standard laptop CPU.
- **Token Cost**: 0 tokens, 0 network bandwidth, offline capable.

### Mathematical Formulation & Single-Pass Matmul
At initialization, canonical prototype phrases $P_i$ across all intents are embedded and stacked into a unified, unit-normalized prototype matrix $\mathbf{V}_{\text{bank}} \in \mathbb{R}^{N \times 384}$:
$$\mathbf{V}_{\text{bank}, i} = \frac{\mathbf{e}(P_{i})}{\|\mathbf{e}(P_{i})\|_2}$$

When a query $q$ enters Tier 2, its embedding $\mathbf{q} \in \mathbb{R}^{384}$ is unit-normalized and evaluated against the entire prototype bank via a single batched matrix-vector multiplication:
$$\mathbf{s} = \mathbf{V}_{\text{bank}} \mathbf{q} \quad \text{where } \mathbf{s} \in \mathbb{R}^{N}$$

The best candidate per intent is aggregated and filtered against calibrated thresholds:
$$\text{BestSim}(k) = \max_{i \in \text{Intent}(k)} s_i, \quad \text{Candidates} = \{ k \mid \text{BestSim}(k) \ge \tau_k \}$$

If $\text{Candidates} \ne \emptyset$, the winning intent is chosen by $\arg\max_k \text{BestSim}(k)$. The margin $\Delta = \text{BestSim}(k_{\text{winner}}) - \text{BestSim}(k_{\text{runner-up}})$ is computed and logged; margins below $0.03$ generate advisory warnings for prototype calibration.

### Production Architectural Hardening
1. **Thread-Safe Lazy Initialization & Singleton**: `_instance_lock` and `_init_lock` (`threading.Lock`) prevent race conditions and redundant model loads across concurrent async worker tasks.
2. **Init Failure Protection (`_init_failed`)**: If FastEmbed model loading encounters an unrecoverable failure (e.g., corrupted cache or network disconnect), the router short-circuits subsequent attempts immediately, preventing perpetual blocking latency and falling through directly to Tier 3 LLM planning.
3. **Fail-Fast Threshold Enforcement**: `__init__` validates that every registered `SemanticIntent` has an explicit entry in `thresholds`. Missing thresholds raise `ValueError` immediately at startup rather than defaulting silently to an arbitrary float.
4. **Single-Pass Matmul**: Replaces per-intent iterative dot products with a single flattened matrix multiplication, delivering sub-millisecond scoring that scales flat as intents expand.
5. **Exact Query Cache**: A bounded insertion-order cache (`cache_size=256`) serves repeated commands (e.g. *"no try again"*, *"check my unread emails"*) in $<0.05\text{ms}$ without embedding overhead.
6. **`RouteResult` Dataclass**: Provides rich metadata (`matched`, `margin`, `runner_up`, `runner_up_confidence`) while remaining fully backward compatible via tuple unpacking: `intent, conf, proto = router.classify(q)`.
7. **In-Module Self-Tests (`run_self_test()`)**: Ships with self-contained regression fixtures (verifying the Exhibit A marathon rejection and canonical exemplars) callable as startup canaries or in CI.

### Intent Definitions & Calibration Thresholds

| Intent | Target Action | Threshold ($\tau$) | Canonical Prototypes |
| :--- | :--- | :--- | :--- |
| **`HANDHELD_OBJECT_RESEARCH`** | Sequential `ocr_webcam` $\to$ `research:web_search` | `0.50` | *"tell me about what I am holding"*, *"what is this book I am holding"*, *"can you read this receipt in my hand"* |
| **`VERIFY_RESEARCH`** | Fresh `research:web_search` | `0.55` | *"are you sure? try again"*, *"no try again"*, *"that is wrong, look it up"*, *"nah that ain't it"* |
| **`EMAIL_THREAD`** | Parallel `email:read_thread` | `0.58` | *"check the entire email thread"*, *"show me the full email chain"*, *"read the whole conversation thread"* |
| **`UNREAD_EMAILS`** | Parallel `email:list_unread` | `0.58` | *"check my unread emails"*, *"do I have any unread emails"*, *"show me my unread emails"* |
| **`SONG_ORIGIN`** | Sequential `media:get_playback_status` $\to$ `research:web_search` | `0.60` | *"what movie is this song from"*, *"which film is this track from"*, *"who sang this song playing right now"* |
| **`DAILY_AGENDA`** | Parallel `tasks:list_today_agenda` | `0.60` | *"what is on my schedule today"*, *"give me my daily briefing"*, *"show me my agenda for today"* |
| **`FINANCE_BALANCE`** | Parallel `finance:get_account_balance` | `0.60` | *"what is my bank balance"*, *"how much money do I have"*, *"check my financial balance"* |
| **`SYSTEM_STATUS`** | Parallel `system:get_telemetry` | `0.60` | *"how is the system running"*, *"show me system vitals"*, *"what is the cpu and ram usage"* |
| **`MOBILE_NOTIFICATIONS`**| Parallel `tasks:list_mobile_notifications` | `0.58` | *"what notifications did I get on my phone"*, *"check my phone notifications"*, *"any new alerts on my phone"* |
| **`BATTERY_STATUS`** | Parallel `system:get_battery_status` | `0.58` | *"what is my phone battery"*, *"check battery on my devices"*, *"is my phone charging"* |

### Empirical Cosine Similarity Benchmark

The following benchmark demonstrates the crisp discrimination of the semantic embedding space:

```
=== Query: "who is holding the world record for the marathon" ===
  HANDHELD_OBJECT_RESEARCH : 0.083  (Threshold 0.50 -> REJECTED)
  VERIFY_RESEARCH          : 0.071  (Threshold 0.55 -> REJECTED)
  EMAIL_THREAD             : 0.030  (Threshold 0.58 -> REJECTED)
  SONG_ORIGIN              : 0.169  (Threshold 0.60 -> REJECTED)
  --> Result: SemanticIntent.NONE -> Falls through to Tier 3 LLM!

=== Query: "tell me about this book I am holding" ===
  HANDHELD_OBJECT_RESEARCH : 0.967  (Threshold 0.50 -> MATCH!)
  --> Result: Sequential ocr_webcam -> web_search

=== Query: "can you read what is on this paper in my hand" ===
  HANDHELD_OBJECT_RESEARCH : 0.802  (Threshold 0.50 -> MATCH!)
  --> Result: Sequential ocr_webcam -> web_search

=== Query: "no try again" ===
  VERIFY_RESEARCH          : 1.000  (Threshold 0.55 -> MATCH!)
  --> Result: Fresh research:web_search

=== Query: "nah that ain't it" ===
  VERIFY_RESEARCH          : 1.000  (Threshold 0.55 -> MATCH!)
  --> Result: Fresh research:web_search

=== Query: "that's wrong search properly" ===
  VERIFY_RESEARCH          : 0.776  (Threshold 0.55 -> MATCH!)
  --> Result: Fresh research:web_search

=== Query: "check the entire thread of the email we were discussing" ===
  EMAIL_THREAD             : 0.827  (Threshold 0.58 -> MATCH!)
  --> Result: email:read_thread

=== Query: "what movie is this song from" ===
  SONG_ORIGIN              : 0.924  (Threshold 0.60 -> MATCH!)
  --> Result: Sequential media:get_playback_status -> web_search
```

---

## 5. Tier 3: Cognitive LLM Planning Engine

When neither Tier 1 nor Tier 2 matches, the utterance represents genuinely open-vocabulary conversation, complex multi-intent requests, or factual inquiry.

### Prompt Formulation
The planner invokes the cloud LLM using `PLANNER_SYSTEM_PROMPT` populated with:
1. **Dynamic Specialist Registry Capabilities**: Current tools from registered specialists.
2. **Active Session Context**: Current `active_email`, `active_track`, `active_repo`, and `active_visual`.
3. **Recent Dialogue History**: Last 6 conversation turns for pronoun resolution.
4. **Proactive Few-Shot Examples**: Canonical exemplars teaching the model when to execute in parallel, when to chain sequentially with `$step_1.var`, and when to answer directly.

### Structured Output Enforcement
The request is submitted to Groq/OpenRouter with `response_format={"type": "json_object"}`. This forces schema conformity at token generation time, ensuring the model returns valid JSON matching the `SwarmPlan` schema:
```json
{
  "plan_type": "parallel" | "sequential" | "direct",
  "direct_response": null,
  "steps": [
    {
      "agent": "research",
      "action": "web_search",
      "params": { "query": "current marathon world record holder" }
    }
  ]
}
```

### Dead Code Elimination in `create_plan`
With Tiers 1 and 2 active, all six post-LLM duplicate blocks have been deleted from `create_plan`:
- [DELETED] Screen perception override (handled by Tier 1)
- [DELETED] Handheld info OCR override (handled by Tier 2)
- [DELETED] Direct camera inspection override (handled by Tier 1)
- [DELETED] Music/movie song origin chaining (handled by Tier 2)
- [DELETED] Email sender context resolution (handled by Tier 1)
- [DELETED] Email thread inspection (handled by Tier 2)

### Retained Post-LLM Guardrail: Unsupported Direct Response Fallback
The only logic retained post-LLM is a lightweight factual safety net:
```python
if (is_explicit_search or is_realtime_data or is_media_trivia or is_entity_lookup or is_open_research) and (
    plan.plan_type == "direct" or not any(s.get("agent") == "research" for s in plan.steps)
):
    # Enforce research:web_search if the model attempted to answer a factual query directly
```
If an LLM hallucinates a direct conversational answer without querying tools on queries like *"Google latest quantum computing breakthroughs"*, the guardrail wraps the search term into `research:web_search`.

---

## 6. Verification and Regression Testing

The 3-tier architecture is guarded by automated regression tests in [`backend/tests/test_agent.py`](file:///home/mihir/Codes/VESPER/backend/tests/test_agent.py):

### 1. `test_semantic_router_intent_classifications`
Verifies that `SemanticIntentRouter` correctly routes diverse natural language phrasings while cleanly rejecting the Exhibit A marathon query:
- *"who is holding the world record for the marathon"* $\to$ `SemanticIntent.NONE`
- *"tell me about this book I am holding"* $\to$ `SemanticIntent.HANDHELD_OBJECT_RESEARCH`
- *"can you read what is on this paper in my hand"* $\to$ `SemanticIntent.HANDHELD_OBJECT_RESEARCH`
- *"no try again"* $\to$ `SemanticIntent.VERIFY_RESEARCH`
- *"nah that ain't it"* $\to$ `SemanticIntent.VERIFY_RESEARCH`
- *"that's wrong search properly"* $\to$ `SemanticIntent.VERIFY_RESEARCH`
- *"check the entire email thread"* $\to$ `SemanticIntent.EMAIL_THREAD`
- *"what movie is this song from"* $\to$ `SemanticIntent.SONG_ORIGIN`

### 2. `test_marathon_record_never_routes_to_vision`
End-to-end integration test verifying that *"who is holding the world record for the marathon"*:
- Does **NOT** contain any steps for `agent="vision"`.
- Successfully plans `agent="research"`.

### Test Suite Summary
```bash
$ .venv/bin/pytest backend/tests/test_agent.py backend/tests/test_hardening_pillars.py backend/tests/test_new_specialists.py backend/tests/test_cluster_allocator.py

backend/tests/test_agent.py .....................                        [ 50%]
backend/tests/test_hardening_pillars.py .......                          [ 67%]
backend/tests/test_new_specialists.py ........                           [ 86%]
backend/tests/test_cluster_allocator.py ......                           [100%]

============================= 42 passed in 88.24s ==============================
```
