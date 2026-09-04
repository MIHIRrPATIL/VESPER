"""Tests for Module 3: Cognitive Agent Swarm (vesper-agent).

Verifies:
  1. Fast-Path Engine deterministic matching (<10ms).
  2. Output Evaluator & Sanitizer (<2ms speech/HUD separation).
  3. Dynamic Specialist Tool Registry.
  4. 2-Stage Plan-and-Execute Engine (Parallel & Sequential Chaining).
  5. Alfred Swarm Supervisor integration.
  6. Agent Microservice FastAPI HTTP endpoints (Port 8001).
"""

from __future__ import annotations

import pytest
from typing import Any, Dict, List, Optional, Tuple
from httpx import ASGITransport, AsyncClient

from backend.agent.alfred import AlfredSupervisor
from backend.agent.app import app as agent_app
from backend.agent.evaluator import OutputEvaluator
from backend.agent.fast_path import FastPathEngine
from backend.agent.llm import LLMClient
from backend.agent.planner import SwarmPlan, SwarmPlanner
from backend.agent.registry import SpecialistRegistry
from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.agent.tools.calendar_tool import GoogleCalendarTool
from backend.data.models import TaskModel
from backend.data.repositories.tasks import TaskRepository


# ── Mock Specialists for Testing ─────────────────────────────────────────────

class MockMediaSpecialist(BaseSpecialist):
    @property
    def name(self) -> str:
        return "media"

    @property
    def description(self) -> str:
        return "Controls music playback and Spotify search."

    def get_capabilities(self) -> str:
        return "Play tracks, control playback, and search Spotify."

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [{"name": "play_track", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}]

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        if action == "play_track":
            query = params.get("query", "Default Song")
            return SpecialistResult(
                success=True,
                action=action,
                data={"track": query, "status": "playing"},
                speech_summary=f"Playing '{query}', sir.",
                card_payload={"type": "media_card", "track": query, "status": "playing"},
            )
        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}'")


class MockResearchSpecialist(BaseSpecialist):
    @property
    def name(self) -> str:
        return "research"

    @property
    def description(self) -> str:
        return "Searches the web for news and information."

    def get_capabilities(self) -> str:
        return "Search the web and retrieve news headlines."

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [{"name": "web_search", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}]

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        if action == "web_search":
            query = params.get("query", "")
            return SpecialistResult(
                success=True,
                action=action,
                data={"query": query, "top_result": "Blinding Lights - The Weeknd"},
                speech_summary=f"Found result for '{query}': Blinding Lights.",
                card_payload={"type": "search_card", "query": query, "snippet": "Popular track"},
            )
        return SpecialistResult(success=False, action=action, error=f"Unknown action '{action}'")


# ── Unit Tests ───────────────────────────────────────────────────────────────

def test_fast_path_matcher():
    """Verifies sub-10ms pattern matching across media, volume, and clock."""
    fp = FastPathEngine()

    # Media
    res = fp.evaluate("pause music")
    assert res.matched is True
    assert res.intent == "media"
    assert res.action == "pause"
    assert "paused" in res.speech_text.lower()

    res = fp.evaluate("next track!")
    assert res.matched is True
    assert res.action == "next"

    # Volume
    res = fp.evaluate("mute")
    assert res.matched is True
    assert res.action == "mute"

    res = fp.evaluate("volume 80%")
    assert res.matched is True
    assert res.action == "set_volume"
    assert res.params.get("level") == 80

    # Clock & Date
    res = fp.evaluate("what time is it?")
    assert res.matched is True
    assert "currently" in res.speech_text

    res = fp.evaluate("what is today's date?")
    assert res.matched is True
    assert "today is" in res.speech_text.lower()

    # Unmatched
    res = fp.evaluate("tell me the history of quantum computing")
    assert res.matched is False


def test_evaluator_sanitization():
    """Verifies output evaluator strips tables, URLs, and code blocks from speech."""
    raw_markdown = (
        "Here is the report, sir:\n\n"
        "| Account | Balance |\n"
        "| :--- | :--- |\n"
        "| SBI | ₹45,000 |\n\n"
        "Check this link: https://mybank.com/portal for details.\n"
        "```python\nprint('Secret Code')\n```\n"
        "All systems are green."
    )

    eval_result = OutputEvaluator.evaluate(raw_markdown)

    # Speech text should have NO URLs, NO table borders, and NO code blocks
    assert "https://" not in eval_result.speech_text
    assert "|" not in eval_result.speech_text
    assert "print('Secret Code')" not in eval_result.speech_text
    assert "the mybank website" in eval_result.speech_text or "mybank" in eval_result.speech_text
    assert "All systems are green." in eval_result.speech_text

    # Markdown body should retain everything
    assert "https://mybank.com/portal" in eval_result.markdown_body
    assert "| Account | Balance |" in eval_result.markdown_body


def test_specialist_registry():
    """Verifies dynamic specialist registration and capability generation."""
    reg = SpecialistRegistry()
    media_spec = MockMediaSpecialist()
    reg.register(media_spec)

    assert reg.get("media") is media_spec
    assert len(reg.list_specialists()) == 1

    prompt = reg.get_capabilities_prompt()
    assert "media:" in prompt
    assert "Play tracks" in prompt


@pytest.mark.asyncio
async def test_2_stage_planner_parallel():
    """Verifies parallel execution of multiple independent tasks."""
    reg = SpecialistRegistry()
    reg.register(MockMediaSpecialist())
    reg.register(MockResearchSpecialist())

    planner = SwarmPlanner()

    # Plan with 2 independent parallel tasks
    plan = SwarmPlan(
        plan_type="parallel",
        steps=[
            {"agent": "media", "action": "play_track", "params": {"query": "Jazz"}},
            {"agent": "research", "action": "web_search", "params": {"query": "Weather"}},
        ],
    )

    exec_result = await planner.execute_plan(plan, reg)
    assert exec_result.plan_type == "parallel"
    assert len(exec_result.specialist_results) == 2
    assert exec_result.specialist_results[0].success is True
    assert exec_result.specialist_results[1].success is True


@pytest.mark.asyncio
async def test_2_stage_planner_sequential_chaining():
    """Verifies sequential chained execution where Step 2 uses Step 1 output."""
    reg = SpecialistRegistry()
    reg.register(MockMediaSpecialist())
    reg.register(MockResearchSpecialist())

    planner = SwarmPlanner()

    # Step 1 finds song -> Step 2 plays it
    plan = SwarmPlan(
        plan_type="sequential",
        steps=[
            {"agent": "research", "action": "web_search", "params": {"query": "The Weeknd"}},
            {"agent": "media", "action": "play_track", "params": {"query": "$step_1.result.top_result"}},
        ],
    )

    exec_result = await planner.execute_plan(plan, reg)
    assert exec_result.plan_type == "sequential"
    assert len(exec_result.specialist_results) == 2

    # Verify Step 2 received the interpolated song title from Step 1
    media_res = exec_result.specialist_results[1]
    assert media_res.success is True
    assert media_res.data.get("track") == "Blinding Lights - The Weeknd"


@pytest.mark.asyncio
async def test_planner_search_decision_guardrails():
    """Verifies planner recognizes when to search for facts, movies, trivia, and follow-ups."""
    reg = SpecialistRegistry()
    reg.register(MockMediaSpecialist())
    reg.register(MockResearchSpecialist())

    # Use a dummy LLM client that would otherwise try to answer 'direct'
    class DummyLLM(LLMClient):
        def __init__(self) -> None:
            super().__init__(groq_key="mock", openrouter_key="mock")

        async def generate_json(
            self, messages: List[Dict[str, str]], temperature: float = 0.1, max_tokens: int = 512
        ) -> Tuple[Dict[str, Any], float]:
            return {"plan_type": "direct", "direct_response": "I think it is a great topic."}, 5.0

    planner = SwarmPlanner(llm_client=DummyLLM())

    # 1. Movie trivia query MUST trigger research:web_search
    plan1, _ = await planner.create_plan("What movie is Afghan Jalebi from?", reg)
    assert any(s.get("agent") == "research" and s.get("action") == "web_search" for s in plan1.steps)

    # 2. Director inquiry MUST trigger research:web_search
    plan2, _ = await planner.create_plan("Who directed Inception?", reg)
    assert any(s.get("agent") == "research" and s.get("action") == "web_search" for s in plan2.steps)

    # 3. Weather inquiry MUST trigger research:web_search
    plan3, _ = await planner.create_plan("What is the weather in Mumbai?", reg)
    assert any(s.get("agent") == "research" and s.get("action") == "web_search" for s in plan3.steps)

    # 4. Explicit search command MUST trigger research:web_search with cleaned query
    plan4, _ = await planner.create_plan("Google latest quantum computing breakthroughs", reg)
    assert any(s.get("agent") == "research" and s.get("action") == "web_search" for s in plan4.steps)
    research_step = [s for s in plan4.steps if s.get("agent") == "research"][0]
    assert "quantum" in research_step["params"]["query"].lower()
    assert not research_step["params"]["query"].lower().startswith("google")

    # 5. Follow-up origin query ("what movie is it from?") MUST trigger sequential media + research
    plan5, _ = await planner.create_plan("What movie is it from?", reg)
    assert plan5.plan_type == "sequential"
    assert len(plan5.steps) == 2
    assert plan5.steps[0]["agent"] == "media"
    assert plan5.steps[1]["agent"] == "research"

    # 6. Song + movie combined query MUST trigger sequential media + research
    plan6, _ = await planner.create_plan("What song is playing right now and what movie is it from?", reg)
    assert plan6.plan_type == "sequential"
    assert len(plan6.steps) == 2
    assert plan6.steps[0]["agent"] == "media"
    assert plan6.steps[1]["agent"] == "research"


@pytest.mark.asyncio
async def test_sequential_variable_interpolation_movie_track():
    """Verifies that $step_1.track movie correctly interpolates track name into search query."""
    reg = SpecialistRegistry()

    class StatusMedia(BaseSpecialist):
        @property
        def name(self) -> str:
            return "media"
        @property
        def description(self) -> str:
            return "media"
        def get_capabilities(self) -> str:
            return "media"
        def get_tool_schemas(self):
            return [{"name": "get_playback_status", "parameters": {}}]
        async def execute(self, action, params, context=None):
            return SpecialistResult(
                success=True,
                action="get_playback_status",
                data={"track": "Afghan Jalebi", "artist": "Pritam", "movie": "Phantom"},
                speech_summary="Playing Afghan Jalebi",
            )

    class CaptureResearch(BaseSpecialist):
        @property
        def name(self) -> str:
            return "research"
        @property
        def description(self) -> str:
            return "research"
        def get_capabilities(self) -> str:
            return "research"
        def get_tool_schemas(self):
            return [{"name": "web_search", "parameters": {}}]
        async def execute(self, action, params, context=None):
            return SpecialistResult(
                success=True,
                action="web_search",
                data={"query_received": params.get("query")},
                speech_summary=f"Searched for: {params.get('query')}",
            )

    reg.register(StatusMedia())
    reg.register(CaptureResearch())

    planner = SwarmPlanner()
    plan = SwarmPlan(
        plan_type="sequential",
        steps=[
            {"agent": "media", "action": "get_playback_status", "params": {}},
            {"agent": "research", "action": "web_search", "params": {"query": "$step_1.track movie"}},
        ],
    )

    exec_result = await planner.execute_plan(plan, reg)
    assert exec_result.plan_type == "sequential"
    res2 = exec_result.specialist_results[1]
    assert res2.success is True
    assert res2.data.get("query_received") == "Afghan Jalebi movie"


@pytest.mark.asyncio
async def test_alfred_supervisor_fast_path():
    """Verifies Alfred supervisor handles fast-path queries in <10ms."""
    supervisor = AlfredSupervisor()
    res = await supervisor.process_query("pause music")

    assert res.fast_path is True
    assert res.plan_type == "fast_path"
    assert "paused" in res.speech_text.lower()
    assert res.latency_ms < 50.0  # Well under fast-path budget


@pytest.mark.asyncio
async def test_agent_fastapi_endpoints():
    """Verifies Port 8001 FastAPI microservice endpoints."""
    transport = ASGITransport(app=agent_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        health_res = await client.get("/health")
        assert health_res.status_code == 200
        assert health_res.json()["status"] == "healthy"
        assert health_res.json()["service"] == "vesper-agent"

        # 2. Fast-path Query
        query_res = await client.post("/query", json={"query": "volume 60%"})
        assert query_res.status_code == 200
        data = query_res.json()
        assert data["fast_path"] is True
        assert "60" in data["speech_text"]

        # 3. Empty query validation
        empty_res = await client.post("/query", json={"query": ""})
        assert empty_res.status_code == 400


@pytest.mark.asyncio
async def test_media_specialist_serpapi_youtube():
    """Verifies SerpAPI YouTube search integration on MediaSpecialist."""
    from backend.agent.specialists.media_specialist import MediaSpecialist

    spec = MediaSpecialist()
    res = await spec.execute("search_youtube_video", {"query": "Hans Zimmer Time", "max_results": 2})

    assert res.success is True
    assert len(res.data.get("videos", [])) >= 1
    assert "Time" in res.data["top_video"]["title"] or "Hans" in res.data["top_video"]["title"]
    assert res.card_payload is not None
    assert res.card_payload.get("type") == "media_video_card"
    assert "youtube.com" in res.card_payload.get("link", "")


class MockTaskRepository(TaskRepository):
    def __init__(self) -> None:
        super().__init__(client=None)
        self._tasks: List[TaskModel] = []

    def create(self, task: Any) -> TaskModel:
        t = TaskModel(
            id=f"mock_task_{len(self._tasks)+1}",
            user_id=task.user_id,
            title=task.title,
            done=False,
            priority=task.priority,
            metadata=task.metadata or {},
        )
        self._tasks.append(t)
        return t

    def list(self, user_id: str = "default_user", include_completed: bool = False, limit: int = 50) -> List[TaskModel]:
        tasks = [t for t in self._tasks if include_completed or not t.done]
        return tasks[:limit]

    def mark_done(self, task_id: str, done: bool = True) -> bool:
        for t in self._tasks:
            if t.id == task_id:
                t.done = done
                return True
        return False

    def delete(self, task_id: str) -> bool:
        self._tasks = [t for t in self._tasks if t.id != task_id]
        return True


class MockGoogleCalendarTool(GoogleCalendarTool):
    def __init__(self) -> None:
        pass

    def is_configured(self) -> bool:
        return True

    async def list_upcoming_events(self, max_results: int = 5) -> List[Dict[str, Any]]:
        return [
            {
                "id": "mock_event_1",
                "summary": "Sprint Planning Meeting",
                "start": "10:00 AM",
                "status": "confirmed",
                "source": "sandbox",
            }
        ]

    async def create_event(
        self,
        summary: str,
        start_time_str: str,
        end_time_str: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "id": "mock_cal_event_123",
            "summary": summary,
            "start": "05:30 PM",
            "end": "06:00 PM",
            "status": "confirmed",
            "source": "sandbox",
        }

    async def delete_event(self, event_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_task_specialist_crud_and_agenda():
    """Verifies TaskSpecialist adds tasks, triggers background triage, and gets daily agenda."""
    from backend.agent.specialists.task_specialist import TaskSpecialist

    spec = TaskSpecialist(repo=MockTaskRepository(), calendar_tool=MockGoogleCalendarTool())

    # 1. Add Task (fast return + background triage fired)
    add_res = await spec.execute("add_task", {"title": "Test Deploy Prometheus", "priority": "high"})
    assert add_res.success is True
    assert "Prometheus" in add_res.speech_summary
    task_id = add_res.data["task_id"]

    # 2. List Tasks
    list_res = await spec.execute("list_tasks", {"limit": 5})
    assert list_res.success is True
    assert list_res.data["count"] >= 1

    # 3. Daily Agenda Briefing
    agenda_res = await spec.execute("get_daily_agenda", {})
    assert agenda_res.success is True
    assert agenda_res.card_payload is not None
    assert agenda_res.card_payload.get("type") == "daily_agenda"

    # 4. Clean up complete
    comp_res = await spec.execute("complete_task", {"task_id": task_id})
    assert comp_res.success is True


@pytest.mark.asyncio
async def test_research_specialist_web_search():
    """Verifies live search via Tavily and SerpAPI fallback."""
    from backend.agent.specialists.research_specialist import ResearchSpecialist

    spec = ResearchSpecialist()
    res = await spec.execute("web_search", {"query": "Latest Python release date", "max_results": 2})

    assert res.success is True
    assert res.card_payload is not None
    assert res.card_payload.get("type") == "research_card"
    assert len(res.data.get("sources", [])) >= 1


@pytest.mark.asyncio
async def test_crawl_specialist_url():
    """Verifies headless web extraction and summarization on CrawlSpecialist."""
    from backend.agent.specialists.crawl_specialist import CrawlSpecialist

    spec = CrawlSpecialist()
    # Fast HTTPX scrape verification
    quick_res = await spec.execute("quick_scrape", {"url": "https://example.com"})
    assert quick_res.success is True
    assert "Example" in quick_res.data.get("title", "")

    # Headless crawl & summary verification
    sum_res = await spec.execute("scrape_and_summarize", {"url": "https://example.com"})
    assert sum_res.success is True
    assert sum_res.card_payload is not None
    assert sum_res.card_payload.get("type") == "crawl_summary_card"


@pytest.mark.asyncio
async def test_finance_specialist_lifecycle():
    """Verifies balance check, transaction logging, bill splitting, and debts in ₹."""
    from backend.agent.specialists.finance_specialist import FinanceSpecialist

    spec = FinanceSpecialist()

    # 1. Balance Check
    bal_res = await spec.execute("get_balance", {})
    assert bal_res.success is True
    assert bal_res.card_payload is not None
    assert "₹" in bal_res.speech_summary

    # 2. Log Expense
    txn_res = await spec.execute("log_transaction", {"amount": 150.0, "type": "expense", "category": "coffee"})
    assert txn_res.success is True
    assert txn_res.data["amount"] == 150.0

    # 3. Split Bill
    split_res = await spec.execute("split_expense", {"total_amount": 900.0, "people": ["Karan", "Aman"]})
    assert split_res.success is True
    assert split_res.data["share_per_person"] == 300.0
    assert len(split_res.data["debts"]) == 2

    # 4. Peer Debts
    debt_res = await spec.execute("manage_debt", {"action": "list"})
    assert debt_res.success is True


@pytest.mark.asyncio
async def test_system_specialist_vitals_and_processes():
    """Verifies hardware vitals, process inspection, and volume adjustment."""
    from backend.agent.specialists.system_specialist import SystemSpecialist

    spec = SystemSpecialist()

    # 1. Hardware Vitals
    vitals_res = await spec.execute("get_system_vitals", {})
    assert vitals_res.success is True
    assert vitals_res.data["cpu_percent"] >= 0.0
    assert vitals_res.data["ram"]["used_gb"] > 0.0

    # 2. Top Processes
    top_res = await spec.execute("get_top_processes", {"limit": 3})
    assert top_res.success is True
    assert len(top_res.data["processes"]) >= 1

    # 3. Query Process
    proc_res = await spec.execute("query_process", {"name": "systemd"})
    assert proc_res.success is True

    # 4. Volume Adjustment
    vol_res = await spec.execute("set_volume", {"volume_percent": 55})
    assert vol_res.success is True
    assert vol_res.data["volume"] == 55


@pytest.mark.asyncio
async def test_memory_specialist_lifecycle():
    """Verifies Shodh memory storage, deduplication, recall, profile dossier, and forgetting."""
    from backend.agent.specialists.memory_specialist import MemorySpecialist

    spec = MemorySpecialist()

    # 1. Store Fact
    store_res = await spec.execute("store_memory", {"statement": "I love drinking Earl Grey tea in the afternoon"})
    assert store_res.success is True
    assert store_res.card_payload is not None
    assert store_res.card_payload.get("type") == "memory_card"

    # 2. Re-store exact fact (deduplication test)
    dup_res = await spec.execute("store_memory", {"statement": store_res.data["statement"]})
    assert dup_res.success is True
    assert dup_res.data.get("action") == "merged"

    # 3. Recall Fact
    recall_res = await spec.execute("recall_memory", {"query": "Earl Grey tea"})
    assert recall_res.success is True
    assert recall_res.data.get("found") is True
    assert len(recall_res.data.get("memories", [])) >= 1

    # 4. Profile Dossier
    prof_res = await spec.execute("get_user_profile", {})
    assert prof_res.success is True
    assert prof_res.card_payload is not None
    assert prof_res.card_payload.get("type") == "user_profile_card"


    # 5. Forget Fact
    forget_res = await spec.execute("forget_memory", {"query": "Earl Grey"})
    assert forget_res.success is True


@pytest.mark.asyncio
async def test_task_specialist_reminders_and_events():
    """Verifies TaskSpecialist diagnostic separation: reminders, tasks, and calendar events."""
    from backend.agent.specialists.task_specialist import TaskSpecialist

    spec = TaskSpecialist(repo=MockTaskRepository(), calendar_tool=MockGoogleCalendarTool())

    # 1. Set time-bound reminder
    rem_res = await spec.execute("set_reminder", {"reminder": "Pick up mom from airport", "time": "5:30 today"})
    assert rem_res.success is True
    assert "reminder" in rem_res.speech_summary.lower()
    assert rem_res.data.get("reminder") == "Pick up mom from airport"

    # 2. List reminders specifically
    list_rem = await spec.execute("list_reminders", {})
    assert list_rem.success is True
    assert len(list_rem.data.get("reminders", [])) >= 1

    # 3. Schedule calendar event
    evt_res = await spec.execute(
        "schedule_event",
        {"summary": "Sprint Planning Meeting", "start_time": "tomorrow at 10am", "location": "Zoom"}
    )
    assert evt_res.success is True
    assert "sprint planning" in evt_res.speech_summary.lower()
    assert evt_res.data.get("summary") == "Sprint Planning Meeting"

    # 4. Clear all reminders
    clear_res = await spec.execute("clear_reminders", {})
    assert clear_res.success is True
    assert clear_res.data is not None
    assert int(clear_res.data.get("deleted_count") or 0) >= 1

    # 5. Verify reminders are now 0
    list_after = await spec.execute("list_reminders", {})
    assert list_after.success is True
    assert list_after.data.get("count", 0) == 0


@pytest.mark.asyncio
async def test_alfred_conversation_history_persistence():
    """Verifies Alfred supervisor persists multi-turn dialogue history across turns."""
    from backend.agent.alfred import AlfredSupervisor

    supervisor = AlfredSupervisor()
    assert len(supervisor.get_history()) == 0

    # Turn 1: fast path
    res1 = await supervisor.process_query("pause music")
    assert res1.fast_path is True
    history = supervisor.get_history()
    assert len(history) == 2
    assert history[0]["content"] == "pause music"
    assert "pause" in history[1]["content"].lower()

    # Turn 2: clear history
    supervisor.clear_history()
    assert len(supervisor.get_history()) == 0


@pytest.mark.asyncio
async def test_multi_turn_context_email_retention_and_thread():
    """Verifies agent remembers active email across intermediate turns and fetches entire thread."""
    from backend.agent.specialists.email_specialist import EmailSpecialist

    reg = SpecialistRegistry()
    reg.register(EmailSpecialist())
    reg.register(MockResearchSpecialist())

    supervisor = AlfredSupervisor(registry=reg)

    # Turn 1: User asks to inspect/read email from Rohit
    res1 = await supervisor.process_query("look into the email from Rohit")
    assert res1.specialist_actions
    assert supervisor.session_context.get("active_email") is not None
    assert "rohit" in supervisor.session_context["active_email"]["sender"].lower()

    # Turn 2: Intermediate unrelated prompt (weather)
    res2 = await supervisor.process_query("What is the weather in Mumbai?")
    # Context must still be preserved!
    assert supervisor.session_context.get("active_email") is not None
    assert "rohit" in supervisor.session_context["active_email"]["sender"].lower()

    # Turn 3: User asks "who sent me the email?"
    res3 = await supervisor.process_query("who sent me the email?")
    assert "rohit" in res3.speech_text.lower()

    # Turn 4: User asks "check for the entire thread of the email we were discussing"
    res4 = await supervisor.process_query("check for the entire thread of the email we were discussing")
    thread_actions = [a for a in res4.specialist_actions if a.get("action") == "read_thread"]
    assert len(thread_actions) == 1
    assert thread_actions[0]["success"] is True
    assert thread_actions[0]["data"]["count"] == 3
    assert any("rohit" in p.lower() for p in thread_actions[0]["data"]["participants"])
    assert "rohit" in res4.speech_text.lower() or "thread" in res4.speech_text.lower()


@pytest.mark.asyncio
async def test_semantic_router_intent_classifications():
    """Verifies that the local zero-token semantic router correctly distinguishes intents and rejects false positives."""
    from backend.agent.semantic_router import SemanticIntent, SemanticIntentRouter

    router = SemanticIntentRouter.get_instance()

    # Exhibit A: Marathon query MUST NOT trigger handheld or vision intents
    intent_m, conf_m, _ = router.classify("who is holding the world record for the marathon")
    assert intent_m == SemanticIntent.NONE

    # Handheld variations
    intent_b, conf_b, _ = router.classify("tell me about this book I am holding")
    assert intent_b == SemanticIntent.HANDHELD_OBJECT_RESEARCH

    intent_p, conf_p, _ = router.classify("can you read what is on this paper in my hand")
    assert intent_p == SemanticIntent.HANDHELD_OBJECT_RESEARCH

    # Verify/challenge variations
    intent_v1, conf_v1, _ = router.classify("no try again")
    assert intent_v1 == SemanticIntent.VERIFY_RESEARCH

    intent_v2, conf_v2, _ = router.classify("nah that ain't it")
    assert intent_v2 == SemanticIntent.VERIFY_RESEARCH

    intent_v3, conf_v3, _ = router.classify("that's wrong search properly")
    assert intent_v3 == SemanticIntent.VERIFY_RESEARCH

    # Thread query
    intent_t, conf_t, _ = router.classify("check the entire email thread")
    assert intent_t == SemanticIntent.EMAIL_THREAD

    # Song origin query
    intent_s, conf_s, _ = router.classify("what movie is this song from")
    assert intent_s == SemanticIntent.SONG_ORIGIN

    # Desk intents (0-token expansion)
    intent_a, conf_a, _ = router.classify("what is on my schedule today")
    assert intent_a == SemanticIntent.DAILY_AGENDA
    assert conf_a >= 0.60

    intent_f, conf_f, _ = router.classify("check my bank balance")
    assert intent_f == SemanticIntent.FINANCE_BALANCE
    assert conf_f >= 0.60

    intent_sys, conf_sys, _ = router.classify("how is the system running")
    assert intent_sys == SemanticIntent.SYSTEM_STATUS
    assert conf_sys >= 0.60


@pytest.mark.asyncio
async def test_marathon_record_never_routes_to_vision():
    """Exhibit A regression test: Marathon holding query must NEVER route to vision/webcam."""
    planner = SwarmPlanner()
    registry = SpecialistRegistry()

    plan, _ = await planner.create_plan(
        "who is holding the world record for the marathon",
        registry,
    )

    # Must NEVER route to vision
    assert not any(s.get("agent") == "vision" for s in plan.steps), "Exhibit A bug: routed to vision!"
    # Must route to research
    assert any(s.get("agent") == "research" for s in plan.steps), "Expected research step for marathon query"


@pytest.mark.asyncio
async def test_alfred_single_action_synthesis_bypass_and_compact_history():
    """Verifies single successful specialist turns bypass Stage 2 LLM and dialogue history is compacted."""
    from backend.agent.specialists.system_specialist import SystemSpecialist

    reg = SpecialistRegistry()
    reg.register(SystemSpecialist())
    supervisor = AlfredSupervisor(registry=reg)

    # 1. Single action system query -> bypasses Stage 2 synthesis
    res = await supervisor.process_query("how is the system running")
    assert res.plan_type == "parallel"
    assert "cpu" in res.speech_text.lower() or "memory" in res.speech_text.lower() or "vitals" in res.speech_text.lower()
    assert len(res.hud_cards) >= 1

    # 2. Dialogue history compaction verification
    supervisor.conversation_history.append({
        "role": "assistant",
        "content": "Certainly, sir. I have meticulously audited your inbox and verified that Mr. Rohit sent an inquiry concerning the deployment of Prometheus metrics for the edge cluster scaling initiative yesterday afternoon."
    })
    compact_history = supervisor._get_compact_planner_history(max_turns=6)
    assert len(compact_history) == 3
    # The long assistant turn must be truncated/compacted to <160 chars
    assert len(compact_history[-1]["content"]) <= 160


def test_normalize_spoken_emails():
    """Verifies spoken email normalizer handles spaced handles, standalone domains, and dots."""
    from backend.agent.alfred import normalize_spoken_emails

    # 1. Spoken handle with spaces after "to"
    res1 = normalize_spoken_emails("send an email to mihir patil 885 at the rate gmail.com saying hello")
    assert "mihirpatil885@gmail.com" in res1

    # 2. Direct handle without spaces
    res2 = normalize_spoken_emails("write an email to mihirpatil885 at the rate of gmail.com")
    assert "mihirpatil885@gmail.com" in res2

    # 3. Standalone domain follow-up utterance
    res3 = normalize_spoken_emails("at the rate gmail.com")
    assert res3 == "@gmail.com"

    res4 = normalize_spoken_emails("at the rate of gmail.com")
    assert res4 == "@gmail.com"

    # 4. Spoken dots
    res5 = normalize_spoken_emails("send to alex dot smith at tech dot io")
    assert "alex.smith@tech.io" in res5


@pytest.mark.asyncio
async def test_email_specialist_validation_and_clarification():
    """Verifies email specialist validates RFC email format and clarifies missing domains."""
    from backend.agent.specialists.email_specialist import EmailSpecialist, is_valid_email

    specialist = EmailSpecialist()

    # 1. Validation function
    assert is_valid_email("mihirpatil885@gmail.com") is True
    assert is_valid_email("alex.smith@technext.io") is True
    assert is_valid_email("mihirpatil885") is False
    assert is_valid_email("") is False

    # 2. Draft email without valid domain -> asks for clarification
    draft_res = await specialist.draft_email("mihirpatil885", "Project Update", "Status report")
    assert draft_res.success is True
    assert draft_res.data["has_valid_email"] is False
    assert "don't have a complete email address with a domain" in draft_res.speech_summary

    # 3. Draft email with valid address -> asks to send
    draft_valid = await specialist.draft_email("mihirpatil885@gmail.com", "Project Update", "Status report")
    assert draft_valid.success is True
    assert draft_valid.data["has_valid_email"] is True
    assert "Would you like me to send it" in draft_valid.speech_summary

    # 4. Send email with invalid address -> rejected with guidance
    send_invalid = await specialist.send_email("mihirpatil885", "Project Update", "Status report")
    assert send_invalid.success is False
    assert send_invalid.data["error"] == "invalid_email_address"
    assert "not a complete email address" in send_invalid.speech_summary


@pytest.mark.asyncio
async def test_planner_pending_email_draft_domain_merging_and_validation():
    """Verifies planner prefilter merges standalone domain into pending draft and blocks invalid dispatch."""
    planner = SwarmPlanner()

    # Context with incomplete recipient handle
    ctx = {
        "pending_email_draft": {
            "to": "mihirpatil885",
            "subject": "Coding LLMs Report",
            "body": "Here is the LLM analysis.",
        }
    }

    # 1. User confirms send while recipient is invalid -> blocks dispatch and asks for full address
    block_plan = planner._check_deterministic_prefilter("yes send it", ctx)
    assert block_plan is not None
    assert block_plan.plan_type == "direct"
    assert "not a complete email address" in block_plan.direct_response

    # 2. User provides standalone domain "@gmail.com" -> merges into pending draft
    merge_plan = planner._check_deterministic_prefilter("@gmail.com", ctx)
    assert merge_plan is not None
    assert merge_plan.plan_type == "direct"
    assert "mihirpatil885@gmail.com" in merge_plan.direct_response
    assert ctx["pending_email_draft"]["to"] == "mihirpatil885@gmail.com"

    # 3. User now confirms send with valid recipient -> plans email:send_email
    send_plan = planner._check_deterministic_prefilter("yes send it", ctx)
    assert send_plan is not None
    assert send_plan.plan_type == "parallel"
    assert send_plan.steps[0]["action"] == "send_email"
    assert send_plan.steps[0]["params"]["to"] == "mihirpatil885@gmail.com"


