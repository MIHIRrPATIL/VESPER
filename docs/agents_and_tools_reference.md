# VESPER Swarm Specialists & Tool APIs Reference

This document provides the definitive technical specification and API manual for all 8 active cognitive specialist agents and background triage sentries operating within the VESPER multi-agent swarm.

---

## Architecture Overview

All specialists adhere to the uniform contract defined in [`backend/agent/specialists/base.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/base.py):
- **Dynamic Swarm Discovery**: Discovered dynamically by Alfred via [`SpecialistRegistry`](file:///home/mihir/Codes/VESPER/backend/agent/registry.py).
- **Uniform Execution Signature**:
  ```python
  async def execute(self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> SpecialistResult
  ```
- **Universal Result Schema (`SpecialistResult`)**:
  ```python
  class SpecialistResult(BaseModel):
      success: bool = True
      action: str = ""
      data: Dict[str, Any] = Field(default_factory=dict)
      speech_summary: str = ""
      card_payload: Optional[Dict[str, Any]] = None
      error: Optional[str] = None
  ```

---

## 1. `TaskSpecialist` (Personal Schedules, Tasks & Calendar)

- **Source**: [`backend/agent/specialists/task_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/task_specialist.py)
- **Identifier**: `tasks`
- **Capabilities Prompt**: *"Manages to-do items, tasks, schedules, deadlines, agendas, and calendar events via Supabase and Google Calendar."*

### Tools & API Actions

#### `add_task`
Creates a new personal to-do task in Supabase.
- **Parameters**:
  - `title` (`string`, **required**): Concise description of the task.
  - `description` (`string`, optional): Additional details or context.
  - `priority` (`string`, optional): `low` | `normal` (default) | `high` | `urgent`.
  - `due_date` (`string`, optional): ISO-8601 timestamp or natural date (`YYYY-MM-DDTHH:MM:SS`).
  - `tags` (`array[string]`, optional): Organization tags (`["work", "errands"]`).
- **Returns**: `data.task` (created task record), `card_payload` (type `task_created`).

#### `list_tasks`
Queries pending, in-progress, or completed tasks.
- **Parameters**:
  - `status` (`string`, optional): `pending` (default) | `in_progress` | `completed` | `all`.
  - `priority` (`string`, optional): Filter by priority.
  - `limit` (`integer`, optional): Maximum tasks to return (default `10`).
- **Returns**: `data.tasks` (array), `data.count`, `card_payload` (type `task_list`).

#### `complete_task`
Marks a task as completed.
- **Parameters**:
  - `task_id` (`string`, **required**): UUID of the task to close.
- **Returns**: `data.task` (updated record).

#### `get_daily_agenda`
Retrieves combined daily schedule (tasks + Google Calendar events) for a specific date.
- **Parameters**:
  - `date` (`string`, optional): Target date in `YYYY-MM-DD` (defaults to today).
- **Returns**: `data.agenda` (merged items sorted by time), `card_payload` (type `daily_agenda`).

#### `sync_google_calendar`
Fetches upcoming events from the user's primary Google Calendar via Google Calendar v3 OAuth.
- **Parameters**:
  - `days_ahead` (`integer`, optional): Window of days to inspect (default `7`).
- **Returns**: `data.events` (list of Google Calendar event objects).

#### `search_mobile_notifications`
Searches forwarded mobile companion notifications by text content, sender, contact, or app package.
- **Parameters**:
  - `query` (`string`, optional): Search keywords or phrases within notification title, body text, or subtext.
  - `sender_filter` (`string`, optional): Filter notifications by sender or sender group name (e.g., WhatsApp contact).
  - `app_filter` (`string`, optional): Filter by application name or package (e.g., `whatsapp`, `slack`, `spotify`).
  - `limit` (`integer`, optional): Maximum notifications to return (default `10`).
- **Returns**: `data.notifications` (list of matching notification records), `data.name_found` (boolean, if user queried whether their name was mentioned), `speech_summary` with natural British butler response, `card_payload` (type `NOTIFICATION_DIGEST`).
- **Privacy & System Boundary**: Searches local buffered notifications forwarded from the mobile companion app while connected. Transparently reports when queries are not in the local buffer rather than hallucinating or inappropriately attempting screen OCR on unrelated desktops.

---

## 2. `MediaSpecialist` (Music, Playback & YouTube Search)

- **Source**: [`backend/agent/specialists/media_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/media_specialist.py)
- **Identifier**: `media`
- **Capabilities Prompt**: *"Controls Spotify music playback (play, pause, resume, skip tracks/playlists) and searches YouTube videos via SerpAPI."*

### Tools & API Actions

#### `play_track`
Searches Spotify Web API for a track and triggers playback on the user's active Spotify Connect device.
- **Parameters**:
  - `query` (`string`, **required**): Track, artist, or song name (*e.g. "Starboy by The Weeknd"*).
- **Returns**: `data.track` (metadata, URI, artist, album art), `card_payload` (type `media_card`).

#### `play_playlist`
Searches and starts playback for a Spotify playlist or album.
- **Parameters**:
  - `query` (`string`, **required**): Playlist or album name (*e.g. "Lofi Beats", "Synthwave 2026"*).
- **Returns**: `data.playlist` (name, URI, track count).

#### `control_playback`
Controls active player state.
- **Parameters**:
  - `command` (`string`, **required**): `pause` | `resume` | `play` | `next` | `skip` | `previous` | `back`.
- **Returns**: `data.status` (`paused`, `resumed`, `skipped`).

#### `search_youtube_video`
Searches YouTube videos, channels, and uploads via SerpAPI Google Video Engine.
- **Parameters**:
  - `query` (`string`, **required**): Video search term (*e.g. "latest video by MrWhosetheboss"*).
  - `max_results` (`integer`, optional): Maximum results to return (default `5`).
- **Returns**: `data.videos` (title, link, channel, views, thumbnail, duration), `card_payload` (type `youtube_search_results`).

---

## 3. `ResearchSpecialist` (Live Web Search & Quick Lookups)

- **Source**: [`backend/agent/specialists/research_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/research_specialist.py)
- **Identifier**: `research`
- **Capabilities Prompt**: *"Conducts live web search for current events, technical documentation, news, facts, and live sports via Tavily and SerpAPI (<500ms)."*

### Tools & API Actions

#### `web_search`
Executes real-time web search across reputable live sources with automatic SerpAPI fallback.
- **Parameters**:
  - `query` (`string`, **required**): Search question or keywords (*e.g. "SpaceX Starship flight 6 status"*).
  - `search_depth` (`string`, optional): `basic` (fast, default) | `advanced` (deep research).
  - `max_results` (`integer`, optional): Maximum search links to extract (default `5`).
- **Returns**: `data.results` (title, url, snippet, score), `data.top_url`, `card_payload` (type `research_results`).

#### `quick_lookup`
Performs ultra-fast (<300ms) factual lookup for definitions, currency conversions, weather facts, or biographies.
- **Parameters**:
  - `query` (`string`, **required**): Factual inquiry (*e.g. "who is CEO of Anthropic"*).
- **Returns**: `data.answer`, `data.sources`.

---

## 4. `CrawlSpecialist` (Dynamic Web Scraper & Summarizer)

- **Source**: [`backend/agent/specialists/crawl_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/crawl_specialist.py)
- **Identifier**: `crawl`
- **Capabilities Prompt**: *"Scrapes, parses, and summarizes specific URLs or web documentation using Crawl4AI dynamic browser and HTTPX."*

### Tools & API Actions

#### `scrape_and_summarize`
Fetches a webpage, strips boilerplates/ads/cookie banners, and produces a structured summary via Groq LPU.
- **Parameters**:
  - `url` (`string`, **required**): Full URL to scrape (*e.g. "https://docs.nextjs.org/blog/next-16"*).
  - `user_prompt` (`string`, optional): Specific focal points or questions about the article.
- **Returns**: `data.summary`, `data.title`, `data.url`, `card_payload` (type `crawl_summary`).

#### `crawl_url`
Raw webpage extraction returning markdown representation.
- **Parameters**:
  - `url` (`string`, **required**): Target website URL.
  - `extract_markdown` (`boolean`, optional): Returns clean markdown (default `true`).
- **Returns**: `data.markdown`, `data.content_length`.

---

## 5. `FinanceSpecialist` (Ledger, Bill Splitting & Debts in ₹ INR)

- **Source**: [`backend/agent/specialists/finance_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/finance_specialist.py)
- **Identifier**: `finance`
- **Capabilities Prompt**: *"Manages double-entry financial accounts in ₹ INR, logs expenses/income, splits bills, manages running tabs, and tracks savings goals."*

### Tools & API Actions

#### `get_balance`
Retrieves current net balance, total monthly credits, and debits in ₹ INR.
- **Parameters**: None.
- **Returns**: `data.balance`, `data.total_credits`, `data.total_debits`, `card_payload` (type `finance_balance`).

#### `log_transaction`
Records an expense or income entry into the persistent ledger.
- **Parameters**:
  - `amount` (`number`, **required**): Value in ₹ INR (*e.g. 450.00*).
  - `category` (`string`, optional): `food` | `groceries` | `transport` | `utilities` | `entertainment` | `tech` | `salary` | `freelance` | `other`.
  - `type` (`string`, optional): `debit` (default) | `credit`.
  - `description` (`string`, optional): Memo/merchant (*e.g. "Dinner at Blue Tokai"*).
- **Returns**: `data.transaction_id`, `data.new_balance`, `card_payload` (type `transaction_logged`).

#### `split_expense`
Splits a bill equally or with custom amounts across multiple participants, updating debt balances.
- **Parameters**:
  - `total_amount` (`number`, **required**): Total bill in ₹ INR (*e.g. 1800.00*).
  - `people` (`array[string]`, **required**): Names of other participants (*e.g. `["Rohit", "Ananya"]`*).
  - `paid_by` (`string`, optional): Who paid the bill (defaults to `"user"`).
  - `description` (`string`, optional): Event/bill description (*e.g. "Team lunch"*).
- **Returns**: `data.per_person_share`, `data.debts_created`, `card_payload` (type `bill_split`).

#### `manage_debt`
Tracks, lists, or settles peer lending and borrowing.
- **Parameters**:
  - `action` (`string`, **required**): `list` | `record_lent` | `record_borrowed` | `settle`.
  - `person` (`string`, optional): Peer contact name.
  - `amount` (`number`, optional): Value in ₹ INR.
  - `notes` (`string`, optional): Context or repayment note.
- **Returns**: `data.debts`, `data.net_balance_with_person`, `card_payload` (type `debt_summary`).

#### `manage_financial_goal`
Creates, updates, tracks, or deletes savings targets.
- **Parameters**:
  - `action` (`string`, **required**): `list` | `create` | `update` | `delete`.
  - `goal_id` (`string`, optional): Target goal UUID.
  - `name` (`string`, optional): Goal name (*e.g. "Emergency Fund", "MacBook Pro"*).
  - `target_amount` (`number`, optional): Target in ₹ INR.
  - `saved_amount` (`number`, optional): Current progress in ₹ INR.
  - `target_date` (`string`, optional): Deadline in `YYYY-MM-DD`.
- **Returns**: `data.goals` (array of goals with progress percentages).

---

## 6. `SystemSpecialist` (Hardware Vitals, Processes & Audio)

- **Source**: [`backend/agent/specialists/system_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/system_specialist.py)
- **Identifier**: `system`
- **Capabilities Prompt**: *"Monitors host hardware vitals (CPU, RAM, disk, thermals), inspects system processes, and controls PipeWire/PulseAudio master volume and mute."*

### Tools & API Actions

#### `get_system_vitals`
Captures real-time CPU utilization, RAM usage, swap, disk percentage, host uptime, and system temperature.
- **Parameters**: None.
- **Returns**: `data.cpu_percent`, `data.memory_percent`, `data.disk_percent`, `data.temperatures`, `card_payload` (type `system_vitals`).

#### `get_top_processes`
Returns the top resource-consuming Linux processes.
- **Parameters**:
  - `sort_by` (`string`, optional): `cpu` (default) | `memory`.
  - `limit` (`integer`, optional): Number of processes to inspect (default `5`).
- **Returns**: `data.processes` (list with pid, name, cpu_percent, memory_percent, status).

#### `query_process`
Finds processes matching a substring name or checks if a service is running (*e.g. "docker", "postgres"*).
- **Parameters**:
  - `name` (`string`, **required**): Process or binary name to search for.
- **Returns**: `data.matches` (list of matching process details), `data.is_running`.

#### `set_volume`
Adjusts Linux host master audio volume via PipeWire / PulseAudio (`pactl`).
- **Parameters**:
  - `volume` (`integer`, **required**): Desired level between `0` and `100`.
  - `sink_name` (`string`, optional): Specific audio sink name (default `@DEFAULT_SINK@`).
- **Returns**: `data.volume`, `data.sink`.

#### `set_mute`
Mutes or unmutes host audio sink.
- **Parameters**:
  - `mute` (`boolean`, **required**): `true` to mute, `false` to unmute.
  - `sink_name` (`string`, optional): Specific sink (default `@DEFAULT_SINK@`).
- **Returns**: `data.muted`.

#### `list_audio_sinks`
Enumerates available PipeWire/PulseAudio output devices.
- **Parameters**: None.
- **Returns**: `data.sinks` (list of names and descriptions).

---

## 7. `MemorySpecialist` (4-Tier Shodh Cognitive Memory)

- **Source**: [`backend/agent/specialists/memory_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/memory_specialist.py)
- **Identifier**: `memory`
- **Capabilities Prompt**: *"Distills, stores, retrieves, and maintains 4-tier long-term cognitive memories, user preferences, and profile dossiers with automatic conflict resolution."*

### Tools & API Actions

#### `store_memory`
Distills a spoken user statement into a canonical 3rd-person fact, classifies into taxonomy categories, checks for contradictory facts (marking older ones inactive), and stores in Supabase with vector embeddings.
- **Parameters**:
  - `statement` (`string`, **required**): User's natural language memory (*e.g. "Remember that I prefer dark roast Ethiopian coffee without sugar"*).
- **Returns**: `data.action` (`stored` | `merged` | `superseded`), `data.canonical_fact`, `data.category`, `card_payload` (type `memory_stored`).

#### `recall_memory`
Queries active memories using lexical, category, recency, and frequency scoring.
- **Parameters**:
  - `query` (`string`, **required**): Search topic or question (*e.g. "what coffee do I drink?"*).
  - `category` (`string`, optional): `preference` | `personal` | `work_tech` | `health_diet` | `routine`.
  - `limit` (`integer`, optional): Maximum facts to retrieve (default `5`).
- **Returns**: `data.memories` (ranked list of active facts), `data.found` (`true` | `false`).

#### `forget_memory`
Soft-deletes or deactivates a fact when the user requests to forget it.
- **Parameters**:
  - `query` (`string`, optional): Text search for the fact to remove.
  - `memory_id` (`string`, optional): Direct UUID.
- **Returns**: `data.forgotten_count`.

#### `get_user_profile`
Synthesizes a 360-degree executive profile dossier across all active memories.
- **Parameters**: None.
- **Returns**: `data.dossier` (categorized user briefing), `card_payload` (type `user_profile_card`).

---

## 8. `VisionSpecialist` (Webcam Perception, OCR & Screen Analysis)

- **Source**: [`backend/agent/specialists/vision_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/vision_specialist.py)
- **Identifier**: `vision`
- **Capabilities Prompt**: *"Analyzes physical surroundings, hand-held objects, or documents via webcam (primary), performs OCR on held-up papers or screens, and inspects desktop monitors upon request."*

### Tools & API Actions

#### `inspect_webcam` (Primary Sensor)
Captures an optical frame from `/dev/video0` and invokes Groq Multimodal Vision LPU (`llama-3.2-11b-vision-preview`, 100% free) to describe what user is holding, pointing at, or showing.
- **Parameters**:
  - `query` (`string`, optional): Specific question (*e.g. "What book am I holding?", "Describe this hardware component"*).
  - `camera_index` (`integer`, optional): Camera index (default `0`).
- **Hardware Awareness**: If host has no camera (e.g. Orange Pi or camera disconnected), returns graceful butler explanation without crashing.
- **Returns**: `data.description`, `data.source` (`"webcam"`), `card_payload` (type `VISION_ANALYSIS`).

#### `ocr_webcam` (Primary Sensor)
Transcribes documents, book pages, handwritten notes, invoices, labels, and serial numbers held up in front of the webcam.
- **Parameters**:
  - `focus_hint` (`string`, optional): Section or element to prioritize (*e.g. "error code", "account number"*).
  - `camera_index` (`integer`, optional): Default `0`.
- **Returns**: `data.extracted_text`, `data.source` (`"webcam"`), `card_payload` (type `OCR_TRANSCRIPTION`).

#### `inspect_screen` (Secondary Sensor)
Captures desktop display monitor via `mss` / `PIL` to inspect terminals, IDE code errors, and open applications.
- **Parameters**:
  - `query` (`string`, optional): Specific question about what is on screen (*e.g. "What compiler error is on my terminal?"*).
  - `monitor_index` (`integer`, optional): Display index (default `1`).
- **Returns**: `data.description`, `data.source` (`"screen"`), `card_payload` (type `VISION_ANALYSIS`).

#### `ocr_screen` (Secondary Sensor)
Transcribes code or text directly from active desktop windows.
- **Parameters**:
  - `focus_hint` (`string`, optional): Target window or code snippet hint.
  - `monitor_index` (`integer`, optional): Default `1`.
- **Returns**: `data.extracted_text`, `card_payload` (type `OCR_TRANSCRIPTION`).

#### `get_device_vision_status`
Returns host hardware and sensory profile (device model, camera device nodes, display state).
- **Parameters**: None.
- **Returns**: `data.device_type`, `data.device_model`, `data.has_camera`, `data.has_display`, `data.is_headless`.

---

## 9. `EmailSpecialist` (Gmail Inbox Management & Thread Triage)

- **Source**: [`backend/agent/specialists/email_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/email_specialist.py)
- **Identifier**: `email`
- **Capabilities Prompt**: *"Manages Gmail messages: checks unread emails, searches message threads, reads email content, reconstructs entire conversation threads, drafts replies, and sends emails."*
- **Authentication & Resiliency**:
  - Automatically attempts live authentication using Google OAuth 2.0 (`backend/credentials/gmail_token.json` or `google_calendar_token.json`).
  - Gracefully validates required Gmail scopes. If absent or offline, seamlessly switches to a verified offline mock sandbox (`_sandbox_inbox`, `_sandbox_threads`, and `_sandbox_outbox`).

### Tools & API Actions

#### `list_unread_emails`
Retrieves recent unread messages in the inbox.
- **Parameters**:
  - `max_results` (`integer`, optional): Maximum unread emails to retrieve (default: `5`).
- **Live Gmail Integration**: Queries `is:unread` with metadata headers (`From`, `Subject`, `Date`).
- **Returns**: `data.count`, `data.emails` (array of email objects), `card_payload` (type `email_list_card`).

#### `search_emails`
Performs keyword, sender, subject, and filter searches across the email inbox.
- **Parameters**:
  - `query` (`string`, **required**): Search query or filter expression (*e.g. "from:rohit", "VESPER", "invoice"*).
  - `max_results` (`integer`, optional): Maximum results to return (default: `5`).
- **Resilient Prefix Stripping**: In offline sandbox mode, automatically strips Gmail filter prefixes (`from:`, `to:`, `subject:`) to match target senders and content.
- **Returns**: `data.query`, `data.count`, `data.emails`, `card_payload` (type `email_list_card`).

#### `read_email`
Retrieves the full headers, recipient details, and decoded text body of a specific email message.
- **Parameters**:
  - `email_id` (`string` or `dict`, **required**): Unique identifier of the email message (*e.g. "msg_001"*). Unpacks dictionary references from prior sequential search steps automatically.
- **Body Decoding**: Automatically handles `text/plain` multipart MIME payloads and base64 URL-safe decoding.
- **Mark as Read**: Marks message as read by removing the `UNREAD` label via Gmail API.
- **Returns**: `data.id`, `data.sender`, `data.to`, `data.subject`, `data.date`, `data.body`, `card_payload` (type `email_card`).

#### `read_thread`
Retrieves and reconstructs the complete chronological conversation thread (all back-and-forth messages and replies).
- **Parameters**:
  - `thread_id` (`string`, optional): Unique identifier of the conversation thread (*e.g. "thread_rohit_vesper"*).
  - `email_id` (`string`, optional): Specific email ID belonging to the thread.
  - `query` (`string`, optional): Search query or sender name if thread ID is unknown.
- **Chronological Stitching**: Reconstructs every message in temporal order, identifies all distinct participants, and isolates the latest reply.
- **Returns**: `data.thread_id`, `data.subject`, `data.count`, `data.participants`, `data.messages`, `data.latest`, `card_payload` (type `email_thread_card`).

#### `draft_email`
Composes an email draft with recipient, subject, and body text without sending it.
- **Parameters**:
  - `to` (`string`, **required**): Recipient email address.
  - `subject` (`string`, **required**): Subject line.
  - `body` (`string`, **required**): Body text content.
- **Returns**: `data.draft` (draft ID, to, subject, body), `card_payload` (type `email_draft_card`).

#### `send_email`
Dispatches an email message to a specified recipient via live Gmail API or sandbox outbox.
- **Parameters**:
  - `to` (`string`, **required**): Recipient email address.
  - `subject` (`string`, **required**): Subject line.
  - `body` (`string`, **required**): Body text content.
- **Returns**: `data.status` (`"sent"`), `data.to`, `data.subject`, `card_payload` (type `email_card`).

---

## 10. `GitHubSpecialist` (Repository Intelligence & Code Navigation)

- **Source**: [`backend/agent/specialists/github_specialist.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/github_specialist.py)
- **Identifier**: `github`
- **Capabilities Prompt**: *"Interacts with GitHub repositories: fetches repo metadata, searches code and files, reads code snippets, answers doubts, and tracks issues."*
- **Authentication**: Uses `GITHUB_TOKEN` from environment if configured; falls back to public GitHub REST API v3 with robust error handling for rate limits.

### Tools & API Actions

#### `get_repo_info`
Fetches high-level repository statistics, descriptions, star counts, fork counts, and primary programming languages.
- **Parameters**:
  - `repo` (`string`, **required**): Repository name in `owner/repo` format (*e.g. "MIHIRrPATIL/VESPER"*).
- **Returns**: `data.name`, `data.full_name`, `data.description`, `data.stars`, `data.forks`, `data.open_issues`, `data.language`, `data.default_branch`, `card_payload` (type `github_repo_card`).

#### `search_code`
Searches for symbols, class names, functions, or keywords across a repository's codebase.
- **Parameters**:
  - `repo` (`string`, **required**): Target repository (`owner/repo`).
  - `query` (`string`, **required**): Search expression (*e.g. "class BaseSpecialist", "FastAPI"*).
  - `max_results` (`integer`, optional): Maximum files to return (default: `5`).
- **Returns**: `data.repo`, `data.query`, `data.count`, `data.results` (list of file paths and matching symbol snippets).

#### `get_code_snippet`
Retrieves exact source code content from a specific file with optional line range slicing.
- **Parameters**:
  - `repo` (`string`, **required**): Target repository (`owner/repo`).
  - `file_path` (`string`, **required**): Path to the source file (*e.g. "backend/agent/alfred.py"*).
  - `start_line` (`integer`, optional): 1-indexed start line.
  - `end_line` (`integer`, optional): 1-indexed end line.
  - `ref` (`string`, optional): Branch or commit SHA (default: default branch).
- **Returns**: `data.repo`, `data.file_path`, `data.total_lines`, `data.snippet`, `data.language`, `card_payload` (type `github_snippet_card`).

#### `solve_doubt`
Synthesizes an architectural explanation or code solution to a programming question by analyzing repository files.
- **Parameters**:
  - `repo` (`string`, **required**): Target repository (`owner/repo`).
  - `query` (`string`, **required**): Developer doubt or bug question (*e.g. "How does Alfred handle fast-path queries?"*).
  - `file_context` (`string`, optional): Relevant file path to ground the answer (*e.g. "backend/agent/alfred.py"*).
- **Returns**: `data.repo`, `data.query`, `data.solution`, `data.reference_files`.

#### `list_issues`
Retrieves open or closed issues and pull requests from a repository.
- **Parameters**:
  - `repo` (`string`, **required**): Target repository (`owner/repo`).
  - `state` (`string`, optional): `open` (default) | `closed` | `all`.
  - `max_results` (`integer`, optional): Maximum issues to return (default: `5`).
- **Returns**: `data.repo`, `data.count`, `data.issues` (list of issue titles, authors, labels, and URLs).

#### `get_recent_commits`
Lists recent commits from the repository's commit history.
- **Parameters**:
  - `repo` (`string`, **required**): Target repository (`owner/repo`).
  - `max_results` (`integer`, optional): Maximum commits to return (default: `5`).
  - `branch` (`string`, optional): Target branch.
- **Returns**: `data.repo`, `data.count`, `data.commits` (list of commit SHAs, authors, messages, and dates).

---

## 11. `AsyncTaskTriageWorker` (Autonomous Background Sentry)

- **Source**: [`backend/agent/specialists/task_triage.py`](file:///home/mihir/Codes/VESPER/backend/agent/specialists/task_triage.py)
- **Role**: Non-blocking background worker that autonomously triages pending tasks.
- **Execution Interval**: Default 60-second periodic cycle or triggered on demand.
- **Behaviors**:
  - Queries pending and overdue tasks across Supabase.
  - Dispatches tasks to Groq LPU to identify urgent blockers and deadlines.
  - Synthesizes executive briefings without human intervention.
  - Emits notification envelopes to connected companion devices via Gateway.
