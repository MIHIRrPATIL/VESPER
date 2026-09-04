# Multi-Turn Context Retention, Anaphora & Dynamic Swarm Planning

This document details the cognitive reasoning architecture in VESPER: how conversational context is preserved across turns, how implicit entity references (anaphora) are resolved, and how multi-step sequential plans execute with dynamic variable interpolation.

---

## 1. High-Level Cognitive Architecture

VESPER's cognitive engine consists of two interconnected layers:
1. **`AlfredSupervisor`** ([`backend/agent/alfred.py`](file:///home/mihir/Codes/VESPER/backend/agent/alfred.py)): The top-level orchestrator maintaining conversational history, active session entities, fast-path intent matching, and final persona synthesis.
2. **`SwarmPlanner`** ([`backend/agent/planner.py`](file:///home/mihir/Codes/VESPER/backend/agent/planner.py)): The cognitive planner determining whether an utterance can be answered directly, executed in parallel across independent specialists, or chained sequentially.

```
                  ┌─────────────────────────────────────────────────┐
                  │                 User Utterance                  │
                  └────────────────────────┬────────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │          Fast-Path Regex Matcher          │
                     │  (e.g., volume, pause, mute, window)      │
                     └──────┬─────────────────────────────┬──────┘
             Matched (<50ms)│                             │ No Fast-Path
                            ▼                             ▼
                   ┌──────────────────┐       ┌───────────────────────────────────┐
                   │ Direct Dispatch  │       │   Stage 1: 3-Tier Hybrid Router   │
                   └──────────────────┘       │  • Tier 1: Cache & Hardware (0ms) │
                                              │  • Tier 2: Semantic Router (~10ms)│
                                              │  • Tier 3: Cognitive LLM Engine   │
                                              └─────────────────┬─────────────────┘
                                                               │
                                         ┌─────────────────────┴─────────────────────┐
                                         │                                           │
                                         ▼                                           ▼
                            ┌────────────────────────┐                  ┌────────────────────────┐
                            │   Parallel Execution   │                  │  Sequential Execution  │
                            │  (Independent tools)   │                  │  ($step_1.var chained) │
                            └────────────┬───────────┘                  └────────────┬───────────┘
                                         │                                           │
                                         └─────────────────────┬─────────────────────┘
                                                               │
                                                               ▼
                                             ┌───────────────────────────────────┐
                                             │  Update Active Session Context    │
                                             │  (active_email, active_track, ...)│
                                             └─────────────────┬─────────────────┘
                                                               │
                                                               ▼
                                             ┌───────────────────────────────────┐
                                             │  Persona Synthesis & Evaluation   │
                                             │  (Ground truth snippet injection) │
                                             └───────────────────────────────────┘
```

> **Deep-Dive Reference**: For full mathematical formulations, embedding benchmarks, threshold tables, and false-positive elimination details, see **[3-Tier Semantic Routing Architecture](file:///home/mihir/Codes/VESPER/docs/three_tier_semantic_routing_architecture.md)**.

---

## 2. Multi-Turn Session Context Engine

### The Problem
In standard stateless LLM pipelines, if a user says:
1. *"Look into the email from Rohit"*
2. *"What is the weather in Mumbai?"*
3. *"Who sent me the email?"*
4. *"Check for the entire thread of the email we were discussing"*

A standard agent loses track of who sent the email because Turn 2 intervened, causing subsequent queries to fail or hallucinate.

### The Solution: `AlfredSupervisor.session_context`
VESPER implements a dedicated entity cache on the supervisor instance supporting both well-known entity slots and a dynamic, open-ended entities pool:

```python
self.session_context: Dict[str, Any] = {
    "active_email": None,   # {id, thread_id, sender, sender_name, subject}
    "active_track": None,   # {track, artist, album, device}
    "active_repo": None,    # {repo, file}
    "active_task": None,    # {task_id, title, priority}
    "pending_email_draft": None, # {to, subject, body, has_valid_email}
    "last_research": None,  # {query, summary, results}
    "entities": {},         # Open-ended pool: {"person": "...", "media": {...}, "task": {...}, "event": {...}}
}
```

#### Automatic Context Capture
Whenever any specialist completes an action, `AlfredSupervisor` inspects `exec_result.specialist_results` and locks active entities into `session_context`:
- `draft_email` → captures `pending_email_draft` with recipient validation and draft content.
- `web_search` → captures `last_research` with query, summary, and source citations.
- `read_email` / `read_thread` / `search_emails` → captures `active_email` and `entities["person"]`, `entities["email"]`.
- `play_track` / `get_playback_status` → captures `active_track` and `entities["media"]`.
- `get_repo_info` / `get_code_snippet` / `solve_doubt` → captures `active_repo` and `entities["repo"]`.
- `add_task` / `list_tasks` / `complete_task` → captures `active_task` and `entities["task"]`.
- `schedule_event` / `list_calendar_events` → captures `entities["event"]`.

#### Injection into Swarm Planning
When generating plans, `session_context` is dynamically injected into `SwarmPlanner.create_plan`:
```python
ACTIVE SESSION CONTEXT (retained across turns):
Active Email: ID='1a06ad79...', ThreadID='1a06ad79...', Sender='Hemanshu Kapadia <hemanshu@hipacewealth.com>', Subject='Re: Sanchay CRM agreement'
Active Person: "Hemanshu Kapadia"
Active Music Track: 'Afghan Jalebi' by Akhtar Chinnal from album/film 'Phantom'
```

---

## 3. Anaphora & Follow-Up Resolution

### Sender Resolution ("Who sent me the email?")
When a user asks:
- *"who sent me the email?"*
- *"who is that email from?"*
- *"who sent it?"*

The planner resolves the sender dynamically from `active_email` or `entities["email"]` without hardcoded placeholder fallbacks:
```python
if is_who_sent_email and active_email and (active_email.get("sender_name") or active_email.get("sender")):
    sender_name = active_email.get("sender_name") or active_email.get("sender")
    sender_addr = active_email.get("sender", "")
    subject = active_email.get("subject", "")
    plan = SwarmPlan(
        plan_type="direct",
        direct_response=f"The email we were discussing was sent by {sender_name} ({sender_addr}) regarding '{subject}', sir.",
    )
```
**Outcome**: Zero unnecessary tool calls; instant, accurate direct answer in <100ms.

---

## 4. Entire Email Thread Reconstruction

When the user asks:
- *"check for the entire thread of the email we were discussing"*
- *"read the entire thread"*
- *"show me the whole conversation"*

The planner automatically resolves the active thread:
1. Binds `thread_id` and `email_id` from `session_context["active_email"]`.
2. Generates a parallel plan invoking `email:read_thread`:
   ```json
   {
     "plan_type": "parallel",
     "steps": [
       {
         "agent": "email",
         "action": "read_thread",
         "params": {
           "thread_id": "$step_1.thread_id",
           "email_id": "$step_1.id"
         }
       }
     ]
   }
   ```
3. `EmailSpecialist.read_thread` retrieves the messages, formats them chronologically with authors and timestamps, and emits an `email_thread_card` to the HUD.
4. Alfred synthesizes an executive summary highlighting the progression of the discussion and the latest reply.

---

## 5. Multi-Turn Email Drafts & Spoken Address Normalization

### Spoken Address Resolution (`normalize_spoken_emails`)
Speech transcriptions often split email addresses across words or insert natural idioms:
- *"send an email to mihir patil 885 at the rate gmail.com"* $\to$ `mihirpatil885@gmail.com`
- *"at the rate gmail.com"* / *"at the rate of gmail.com"* $\to$ `@gmail.com`
- *"john dot doe at tech dot io"* $\to$ `john.doe@tech.io`

### Multi-Turn Draft Lifecycle & Domain Merging
1. **Initial Draft with Partial Handle**:
   If user says *"write an email to Mihir Patil saying here is the report"*, `EmailSpecialist.draft_email` creates the draft and checks `is_valid_email(to)`. Since `"mihirpatil"` lacks a domain, Alfred asks for clarification:
   > *"I have prepared an email draft for mihirpatil regarding '...', sir. However, I don't have a complete email address with a domain. What is the recipient's full email address, sir?"*
2. **Follow-Up Domain Completion**:
   When the user replies with *"at the rate gmail.com"*, the planner's deterministic prefilter intercepts the query, normalizes it to `@gmail.com`, and merges it into the pending draft recipient (`mihirpatil885@gmail.com`), asking:
   > *"I have set the recipient address to mihirpatil885@gmail.com, sir. Would you like me to dispatch the email now?"*
3. **Validation Protection**:
   If the user says *"yes send it"* while the address remains incomplete, the dispatcher blocks transmission and requests a full address, preventing malformed email sends.

---

## 6. Universal Recursive Variable Interpolation

When a multi-step task requires passing the output of Step 1 into Step 2 across any domain (email, tasks, code, media, web research):

### Plan Generation
```json
{
  "plan_type": "sequential",
  "steps": [
    {
      "agent": "email",
      "action": "search_emails",
      "params": { "query": "from:Hemanshu", "max_results": 1 }
    },
    {
      "agent": "email",
      "action": "read_email",
      "params": { "email_id": "$step_1.id" }
    }
  ]
}
```

### Universal Path Resolution Engine (`_resolve_step_var`)
The resolver operates without domain-specific branches (`track`, `movie`, `email_id`). Instead, it uses tokenized, recursive traversal:
- **Tokenized Path Traversal**: Handles arbitrary bracket notation and dot separators (e.g. `emails[0].id`, `items.0.title`, `data.results[2].snippet`, `status`).
- **Domain-Agnostic Auto-Unwrapping**: If a specialist returns a collection dict (e.g., `{"emails": [...]}`, `{"tasks": [...]}`, `{"results": [...]}`), referencing `$step_1.id` or `$step_1.title` automatically unwraps the first element when the root dict does not directly contain that key.
- **Entity Qualifier Stripping**: Tolerates LLM prefixes such as `$step_1.task.title` or `$step_1.email.id` by safely advancing past redundant wrapper identifiers.
- **Embedded String Substitution**: `re.sub` allows partial variable interpolation within sentences:
  `"params": {"query": "$step_1.track movie"}` → `"params": {"query": "Afghan Jalebi movie"}`
  `"params": {"query": "$step_1.title tutorial"}` → `"params": {"query": "Research WebRTC DataChannels tutorial"}`

---

## 6. Factual Verification & Anti-Hallucination Pipeline

To prevent LLMs from fabricating information when asked factual or media questions:

1. **Deterministic Search Triggers**:
   In `planner.py`, queries regarding:
   - Movie/film soundtrack origins (*"what movie is it from"*, *"which film is Afghan Jalebi in"*)
   - Directors, actors, release dates, composers
   - Real-time weather, forecast, current news, sports scores
   - Explicit web lookups (*"google X"*, *"search the web for Y"*)
   Are intercepted. The planner never allows the model to respond `"direct"` with internal knowledge; it forces a `research:web_search` step.

2. **Verified Source Snippet Propagation**:
   In `alfred.py`, web search snippets (`• [Title]: Snippet text...`), direct facts, and Spotify album metadata are injected directly into `ALFRED_SYNTHESIS_PROMPT`.

3. **Strict Persona Synthesis Directives**:
   The prompt explicitly forbids Alfred from contradicting, correcting, or guessing beyond the verified search snippets provided in the execution outcomes block.
