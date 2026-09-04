"""VESPER Research Specialist Agent.

Provides dual-engine web intelligence and fast fact retrieval:
  1. Tavily Search Engine (Primary AI-optimized search with direct answer synthesis).
  2. SerpAPI Google Search Engine (Fallback & quick Google search lookup).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import httpx

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.shared.config import SERPAPI_API_KEY, TAVILY_API_KEY

logger = logging.getLogger("vesper.agent.specialists.research")


class ResearchSpecialist(BaseSpecialist):
    """Specialist agent for real-time web research, fact verification, and news."""

    def __init__(
        self,
        tavily_key: Optional[str] = None,
        serpapi_key: Optional[str] = None,
    ) -> None:
        self.tavily_key = tavily_key or TAVILY_API_KEY
        self.serpapi_key = serpapi_key or SERPAPI_API_KEY

    @property
    def name(self) -> str:
        return "research"

    @property
    def description(self) -> str:
        return "Searches the web for up-to-date information, news, technical facts, and fast lookups."

    def get_capabilities(self) -> str:
        return (
            "Perform comprehensive web searches, quick fact lookups via Tavily or Google SerpAPI, "
            "and retrieve the latest news on any topic."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "web_search",
                "description": "Searches the live web for detailed information, documentation, or news using Tavily.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query or topic."},
                        "search_depth": {
                            "type": "string",
                            "enum": ["basic", "advanced"],
                            "description": "Depth of search. 'basic' is faster; 'advanced' is deeper.",
                        },
                        "max_results": {"type": "integer", "description": "Number of results (default 4)."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "quick_lookup",
                "description": "Ultra-fast lookup (<500ms) for direct facts, definitions, quick stats, or live scores.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The specific question or fact to lookup."},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "search_news",
                "description": "Searches recent news articles and current events on a specified topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "News topic or current event."},
                        "max_results": {"type": "integer", "description": "Max news items (default 3)."},
                    },
                    "required": ["topic"],
                },
            },
        ]

    # ── Tavily Search Engine ──────────────────────────────────────────────────

    async def _search_tavily(
        self, query: str, search_depth: str = "basic", max_results: int = 4
    ) -> Optional[Dict[str, Any]]:
        """Queries Tavily Search API."""
        if not self.tavily_key:
            return None

        depth = "advanced" if "adv" in (search_depth).lower() else "basic"
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": depth,
            "include_answer": True,
            "max_results": max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()
                logger.warning(f"[Research:Tavily] HTTP {res.status_code}: {res.text[:100]}")
        except Exception as e:
            logger.warning(f"[Research:Tavily] Request error: {e}")

        return None

    # ── SerpAPI Google Fallback ───────────────────────────────────────────────

    async def _search_serpapi_google(self, query: str, max_results: int = 3) -> Optional[Dict[str, Any]]:
        """Queries SerpAPI Google search engine."""
        if not self.serpapi_key:
            return None

        url = "https://serpapi.com/search.json"
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.serpapi_key,
            "num": max_results,
        }

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    data = res.json()
                    results = []
                    # Check organic results or answer box
                    answer = data.get("answer_box", {}).get("answer") or data.get("answer_box", {}).get("snippet")
                    for item in data.get("organic_results", [])[:max_results]:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                            "content": item.get("snippet", ""),
                        })
                    return {"answer": answer, "results": results}
        except Exception as e:
            logger.warning(f"[Research:SerpAPI] Request error: {e}")

        return None

    # ── Tool Implementations ─────────────────────────────────────────────────

    async def execute_web_search(
        self, query: str, search_depth: str = "basic", max_results: int = 4
    ) -> SpecialistResult:
        """Executes web search with Tavily primary and SerpAPI fallback."""
        data = await self._search_tavily(query, search_depth=search_depth, max_results=max_results)

        if not data:
            logger.info(f"[Research] Tavily unavailable, falling back to SerpAPI for '{query}'...")
            data = await self._search_serpapi_google(query, max_results=max_results)

        if not data or not data.get("results"):
            return SpecialistResult(
                success=False,
                action="web_search",
                error=f"Unable to retrieve search results for '{query}'.",
                speech_summary=f"I was unable to locate reliable web results for '{query}', sir.",
            )

        answer = data.get("answer")
        results = data.get("results", [])

        sources = []
        snippets = []
        for r in results[:max_results]:
            title = r.get("title", "Source")
            url = r.get("url", "")
            snippet = str(r.get("content", "")).strip()
            sources.append({
                "title": title,
                "url": url,
                "snippet": snippet[:350],
            })
            if snippet:
                snippets.append(f"[{title}]: {snippet[:250]}")

        top_url = sources[0]["url"] if sources else ""

        if answer:
            speech = f"{answer}"
        elif snippets:
            speech = f"Web search findings for '{query}': " + " | ".join(snippets[:2])
        else:
            top_title = sources[0]["title"] if sources else query
            speech = f"I have located relevant information regarding '{query}' from {top_title}, sir."

        return SpecialistResult(
            success=True,
            action="web_search",
            data={"query": query, "answer": answer, "top_url": top_url, "sources": sources},
            speech_summary=speech,
            card_payload={
                "type": "research_card",
                "query": query,
                "answer": answer,
                "top_url": top_url,
                "sources": sources,
            },
        )

    async def execute_quick_lookup(self, query: str) -> SpecialistResult:
        """Rapid fact lookup (<500ms)."""
        return await self.execute_web_search(query, search_depth="basic", max_results=2)

    # ── Execution Router ─────────────────────────────────────────────────────

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        act = action.lower().strip()
        query = str(params.get("query") or params.get("topic") or params.get("q") or "").strip()

        if not query:
            return SpecialistResult(success=False, action=action, error="Search query is required.")

        if act in ["quick_lookup", "fact_check", "lookup", "answer"]:
            return await self.execute_quick_lookup(query)

        elif act in ["search_news", "news"]:
            return await self.execute_web_search(f"{query} latest news", search_depth="basic", max_results=3)

        # Default web search
        depth = str(params.get("search_depth", "basic"))
        max_r = int(params.get("max_results") or 4)
        return await self.execute_web_search(query, search_depth=depth, max_results=max_r)
