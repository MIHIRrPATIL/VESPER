"""VESPER Crawl Specialist Agent.

Provides deep asynchronous web extraction and page analysis:
  1. Crawl4AI Engine: Strictly headless Chromium with dynamic JS execution and markdown extraction.
  2. Fast HTTPX Scraper: Ultra-fast (<300ms) static parser using BeautifulSoup (zero browser overhead).
  3. Groq LPU Summarizer: Synthesizes clean page digests in Alfred's British butler persona.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx

from backend.agent.llm import LLMClient
from backend.agent.specialists.base import BaseSpecialist, SpecialistResult

logger = logging.getLogger("vesper.agent.specialists.crawl")


class CrawlSpecialist(BaseSpecialist):
    """Specialist agent for deep web crawling, clean markdown extraction, and page summarization."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient()

    @property
    def name(self) -> str:
        return "crawl"

    @property
    def description(self) -> str:
        return "Scrapes and crawls web pages, extracts clean text/markdown, and summarizes articles or documentation."

    def get_capabilities(self) -> str:
        return (
            "Extract clean markdown from web pages via Crawl4AI (strictly headless), "
            "perform fast HTTPX text scraping, and summarize article or documentation contents."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "crawl_url",
                "description": "Scrapes a web page and extracts clean, readable Markdown content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The target website or article URL."},
                        "max_chars": {"type": "integer", "description": "Maximum characters of text to return (default 2500)."},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "scrape_and_summarize",
                "description": "Scrapes a URL and provides a concise, articulate British butler summary of its key points.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The target website or article URL."},
                        "focus_topic": {"type": "string", "description": "Optional question or specific topic to focus on."},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "quick_scrape",
                "description": "Ultra-fast (<300ms) static page text extraction using HTTPX (zero browser overhead).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The target web page URL."},
                    },
                    "required": ["url"],
                },
            },
        ]

    # ── Fast HTTPX + BeautifulSoup Scraper (<300ms) ──────────────────────────

    async def _fast_httpx_scrape(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrapes static page content using HTTPX and BeautifulSoup."""
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                res = await client.get(url, headers=headers)
                if res.status_code != 200:
                    return None

                soup = BeautifulSoup(res.text, "html.parser")
                # Strip unwanted elements
                for element in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                    element.decompose()

                title = soup.title.string.strip() if soup.title and soup.title.string else "Webpage"
                text = soup.get_text(separator="\n", strip=True)
                # Clean up excessive empty lines
                cleaned_text = re.sub(r"\n{3,}", "\n\n", text)

                return {
                    "title": title,
                    "content": cleaned_text,
                    "engine": "httpx_fast",
                }
        except Exception as e:
            logger.warning(f"[Crawl:HTTPX] Error fetching {url}: {e}")
            return None

    # ── Crawl4AI Headless Crawler ─────────────────────────────────────────────

    async def _crawl4ai_extract(self, url: str, max_chars: int = 2500) -> Dict[str, Any]:
        """Extracts markdown using strictly headless Crawl4AI (never displays a window)."""
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

            # Strict headless configuration ensuring NO browser window or popup ever opens
            browser_cfg = BrowserConfig(
                headless=True,
                verbose=False,
                extra_args=[
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                ],
            )
            run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                res = await crawler.arun(url=url, config=run_cfg)
                if res.success:
                    raw_md = res.markdown.raw_markdown if res.markdown else ""
                    return {
                        "title": url,
                        "content": raw_md[:max_chars],
                        "engine": "crawl4ai_headless",
                        "links": [link.get("href") for link in res.links.get("internal", [])[:5]] if res.links else [],
                    }
        except Exception as e:
            logger.warning(f"[Crawl:Crawl4AI] Headless run failed ({e}), falling back to HTTPX...")

        # Fallback to fast HTTPX
        fallback = await self._fast_httpx_scrape(url)
        if fallback:
            return {
                "title": fallback["title"],
                "content": fallback["content"][:max_chars],
                "engine": "httpx_fallback",
                "links": [],
            }

        return {
            "title": "Failed extraction",
            "content": f"Unable to retrieve content from {url}.",
            "engine": "failed",
            "links": [],
        }

    # ── Tool Implementations ─────────────────────────────────────────────────

    async def crawl_url(self, url: str, max_chars: int = 2500) -> SpecialistResult:
        """Crawls a URL and returns clean Markdown."""
        data = await self._crawl4ai_extract(url, max_chars=max_chars)
        content = data["content"]
        title = data["title"]

        if data["engine"] == "failed":
            return SpecialistResult(
                success=False,
                action="crawl_url",
                error=f"Could not extract content from '{url}'.",
                speech_summary=f"I was unable to load the web page at {url}, sir.",
            )

        speech = f"Successfully extracted the contents from {title}, sir."

        return SpecialistResult(
            success=True,
            action="crawl_url",
            data={
                "url": url,
                "title": title,
                "content": content,
                "length": len(content),
                "engine": data["engine"],
            },
            speech_summary=speech,
            card_payload={
                "type": "crawl_card",
                "url": url,
                "title": title,
                "content_snippet": content[:500],
                "char_count": len(content),
            },
        )

    async def scrape_and_summarize(self, url: str, focus_topic: Optional[str] = None) -> SpecialistResult:
        """Crawls a URL and synthesizes a concise butler summary."""
        # Try fast HTTPX first for speed (<300ms)
        data = await self._fast_httpx_scrape(url)
        if not data or len(data.get("content", "")) < 100:
            data = await self._crawl4ai_extract(url, max_chars=3000)

        content = data.get("content", "")
        title = data.get("title", url)

        if not content or len(content) < 50:
            return SpecialistResult(
                success=False,
                action="scrape_and_summarize",
                error=f"No readable content found at '{url}'.",
                speech_summary=f"I was unable to retrieve sufficient text from {url} to form a summary, sir.",
            )

        # Summarize via Groq LPU
        focus_directive = f"Focus particularly on: '{focus_topic}'." if focus_topic else "Highlight the primary key points."
        prompt = (
            "You are Alfred, a poised British assistant. Summarize the webpage excerpt below in 2 to 3 articulate sentences. "
            "Do not recite URLs or code fences. Speak naturally.\n\n"
            f"Page Title: {title}\n"
            f"Directive: {focus_directive}\n\n"
            f"Content:\n{content[:2500]}"
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Please provide the summary, Alfred."},
        ]

        summary, _ = await self.llm.generate_chat(messages, temperature=0.2, max_tokens=250)
        summary = summary.strip() or f"The page discusses {title}."

        return SpecialistResult(
            success=True,
            action="scrape_and_summarize",
            data={
                "url": url,
                "title": title,
                "summary": summary,
                "focus_topic": focus_topic,
            },
            speech_summary=summary,
            card_payload={
                "type": "crawl_summary_card",
                "url": url,
                "title": title,
                "summary": summary,
            },
        )

    # ── Execution Router ─────────────────────────────────────────────────────

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        act = action.lower().strip()
        url = str(params.get("url") or params.get("link") or "").strip()

        if not url:
            return SpecialistResult(success=False, action=action, error="URL is required for crawling.")

        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"

        if act in ["scrape_and_summarize", "summarize_page", "summarize", "read"]:
            focus = params.get("focus_topic") or params.get("topic")
            return await self.scrape_and_summarize(url, focus_topic=focus)

        elif act in ["quick_scrape", "fast_scrape"]:
            fast_data = await self._fast_httpx_scrape(url)
            if fast_data:
                return SpecialistResult(
                    success=True,
                    action="quick_scrape",
                    data=fast_data,
                    speech_summary=f"Extracted content from {fast_data['title']}, sir.",
                    card_payload={"type": "quick_scrape_card", "url": url, "title": fast_data["title"]},
                )
            # Fallback to crawl4ai
            return await self.crawl_url(url)

        # Default crawl
        max_c = int(params.get("max_chars") or 2500)
        return await self.crawl_url(url, max_chars=max_c)
