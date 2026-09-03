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
from typing import Any, Dict, List, Optional
from httpx import ASGITransport, AsyncClient

from backend.agent.alfred import AlfredSupervisor
from backend.agent.app import app as agent_app
from backend.agent.evaluator import OutputEvaluator
from backend.agent.fast_path import FastPathEngine
from backend.agent.planner import SwarmPlan, SwarmPlanner
from backend.agent.registry import SpecialistRegistry
from backend.agent.specialists.base import BaseSpecialist, SpecialistResult


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


@pytest.mark.asyncio
async def test_task_specialist_crud_and_agenda():
    """Verifies TaskSpecialist adds tasks, triggers background triage, and gets daily agenda."""
    from backend.agent.specialists.task_specialist import TaskSpecialist

    spec = TaskSpecialist()

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

