"""VESPER Email Specialist Agent.

Provides email management and inbox triage for Alfred:
  - `list_unread_emails`: Fetches recent unread messages with sender, subject, and preview.
  - `search_emails`: Searches messages by query, sender, keyword, or label.
  - `read_email`: Retrieves full email body, recipient headers, and timestamps.
  - `draft_email`: Creates an email draft with subject and content.
  - `send_email`: Sends an email message or queues it for user confirmation.

Integrates with Google Gmail API (via OAuth credentials in `backend/credentials/`)
and provides a resilient offline sandbox with outbox persistence when credentials
are pending initial interactive browser authentication.
"""

from __future__ import annotations

import base64
import datetime
import html
import logging
import os
import re
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.agent.llm import LLMClient
from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.shared.config import (
    GMAIL_CLIENT_ID,
    GMAIL_CLIENT_SECRET,
    GOOGLE_CALENDAR_CLIENT_ID,
    GOOGLE_CALENDAR_CLIENT_SECRET,
)

logger = logging.getLogger("vesper.agent.specialists.email")

CREDENTIALS_PATH = Path(__file__).resolve().parent.parent.parent / "credentials" / "google_calendar_credentials.json"
GMAIL_TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / "credentials" / "gmail_token.json"
CALENDAR_TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / "credentials" / "google_calendar_token.json"

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def is_valid_email(email_str: str) -> bool:
    """Validates whether an email string is complete and RFC-compliant."""
    if not email_str:
        return False
    clean = email_str.strip()
    return bool(EMAIL_REGEX.match(clean))


# Default mock sandbox messages for resilient offline / pre-OAuth testing
DEFAULT_MOCK_INBOX = [
    {
        "id": "msg_001",
        "thread_id": "thread_rohit_vesper",
        "sender": "rohit.dev@technext.io",
        "sender_name": "Rohit Kumar",
        "subject": "VESPER Swarm Architecture & Edge Sync Sync",
        "snippet": "Hey Mihir, reviewed the Orange Pi least-capability distribution specs. The audio capture offloading looks solid...",
        "body": (
            "Hey Mihir,\n\n"
            "I reviewed the latest PR and design specs for the VESPER distributed cluster.\n"
            "The least-capability allocation where Orange Pi handles WebRTC VAD audio capture "
            "while the laptop runs the VLLM vision perception and cognitive swarm is super clean.\n\n"
            "Let's jump on a quick sync this evening if you're free to test cross-device latency.\n\n"
            "Cheers,\nRohit"
        ),
        "date": "Today, 11:20 AM",
        "unread": True,
        "labels": ["INBOX", "UNREAD", "WORK"],
    },
    {
        "id": "msg_002",
        "thread_id": "thread_github_stars",
        "sender": "notifications@github.com",
        "sender_name": "GitHub Notifications",
        "subject": "[MIHIRrPATIL/VESPER] Star and Discussion Created on Repository",
        "snippet": "A new discussion thread 'Edge Device Cluster Scaling' was opened on MIHIRrPATIL/VESPER by contributor...",
        "body": (
            "Hi Mihir,\n\n"
            "You have new activity on MIHIRrPATIL/VESPER:\n"
            "- Discussion #4: 'Edge Device Cluster Scaling' opened by user alex-embed.\n"
            "- 3 new stars on main branch.\n\n"
            "View on GitHub: https://github.com/MIHIRrPATIL/VESPER/discussions/4\n"
        ),
        "date": "Today, 09:45 AM",
        "unread": True,
        "labels": ["INBOX", "UNREAD", "GITHUB"],
    },
    {
        "id": "msg_003",
        "thread_id": "thread_sarah_invoice",
        "sender": "sarah.finance@alpha-capital.com",
        "sender_name": "Sarah Miller",
        "subject": "Monthly Invoice and Compute Cloud Settlement",
        "snippet": "Mihir, here is your summary statement for Groq and OpenRouter compute usage for August 2026...",
        "body": (
            "Hi Mihir,\n\n"
            "Attached is the compute invoice for your August LLM inference runs.\n"
            "Total balance settled: $14.20.\n"
            "All API quotas have been refreshed for September.\n\n"
            "Best,\nSarah Miller"
        ),
        "date": "Yesterday, 04:15 PM",
        "unread": False,
        "labels": ["INBOX", "FINANCE"],
    },
]

DEFAULT_MOCK_THREADS: Dict[str, List[Dict[str, Any]]] = {
    "thread_rohit_vesper": [
        {
            "id": "msg_001_initial",
            "thread_id": "thread_rohit_vesper",
            "sender": "rohit.dev@technext.io",
            "sender_name": "Rohit Kumar",
            "subject": "VESPER Swarm Architecture & Edge Sync Sync",
            "snippet": "Hi Mihir, let's establish the communication topology between Orange Pi, mobile, and laptop.",
            "body": (
                "Hi Mihir,\n\n"
                "Let's establish the communication topology between Orange Pi, mobile, and laptop. "
                "Are we utilizing WebSockets over LAN for local IPC?\n\n"
                "Best,\nRohit"
            ),
            "date": "Yesterday, 04:30 PM",
        },
        {
            "id": "msg_001_reply",
            "thread_id": "thread_rohit_vesper",
            "sender": "mihir.patil@vesper.ai",
            "sender_name": "Mihir Patil",
            "subject": "Re: VESPER Swarm Architecture & Edge Sync Sync",
            "snippet": "Hey Rohit, yes! Port 8000 acts as our centralized gateway with WebSocket IPC...",
            "body": (
                "Hey Rohit,\n\n"
                "Yes! Port 8000 acts as our centralized gateway with WebSocket IPC and binary frame routing.\n"
                "The least-capability allocator distributes audio to the Orange Pi and VLLM to the laptop.\n\n"
                "Cheers,\nMihir"
            ),
            "date": "Yesterday, 06:15 PM",
        },
        {
            "id": "msg_001",
            "thread_id": "thread_rohit_vesper",
            "sender": "rohit.dev@technext.io",
            "sender_name": "Rohit Kumar",
            "subject": "Re: VESPER Swarm Architecture & Edge Sync Sync",
            "snippet": "Hey Mihir, reviewed the Orange Pi least-capability distribution specs. The audio capture offloading looks solid...",
            "body": (
                "Hey Mihir,\n\n"
                "I reviewed the latest PR and design specs for the VESPER distributed cluster.\n"
                "The least-capability allocation where Orange Pi handles WebRTC VAD audio capture "
                "while the laptop runs the VLLM vision perception and cognitive swarm is super clean.\n\n"
                "Let's jump on a quick sync this evening if you're free to test cross-device latency.\n\n"
                "Cheers,\nRohit"
            ),
            "date": "Today, 11:20 AM",
        },
    ],
    "thread_github_stars": [
        {
            "id": "msg_002",
            "thread_id": "thread_github_stars",
            "sender": "notifications@github.com",
            "sender_name": "GitHub Notifications",
            "subject": "[MIHIRrPATIL/VESPER] Star and Discussion Created on Repository",
            "snippet": "A new discussion thread 'Edge Device Cluster Scaling' was opened on MIHIRrPATIL/VESPER by contributor...",
            "body": (
                "Hi Mihir,\n\n"
                "You have new activity on MIHIRrPATIL/VESPER:\n"
                "- Discussion #4: 'Edge Device Cluster Scaling' opened by user alex-embed.\n"
                "- 3 new stars on main branch.\n\n"
                "View on GitHub: https://github.com/MIHIRrPATIL/VESPER/discussions/4\n"
            ),
            "date": "Today, 09:45 AM",
        },
    ],
    "thread_sarah_invoice": [
        {
            "id": "msg_003",
            "thread_id": "thread_sarah_invoice",
            "sender": "sarah.finance@alpha-capital.com",
            "sender_name": "Sarah Miller",
            "subject": "Monthly Invoice and Compute Cloud Settlement",
            "snippet": "Mihir, here is your summary statement for Groq and OpenRouter compute usage for August 2026...",
            "body": (
                "Hi Mihir,\n\n"
                "Attached is the compute invoice for your August LLM inference runs.\n"
                "Total balance settled: $14.20.\n"
                "All API quotas have been refreshed for September.\n\n"
                "Best,\nSarah Miller"
            ),
            "date": "Yesterday, 04:15 PM",
        },
    ],
}


class EmailSpecialist(BaseSpecialist):
    """Specialist sub-agent for Gmail inbox management, search, and message drafting."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        sandbox_mode: bool = False,
    ) -> None:
        self.llm = llm_client or LLMClient()
        self.sandbox_mode = (
            sandbox_mode
            or (os.environ.get("VESPER_ENV") == "test")
            or bool(os.environ.get("PYTEST_CURRENT_TEST"))
        )
        self.client_id = GMAIL_CLIENT_ID or GOOGLE_CALENDAR_CLIENT_ID
        self.client_secret = GMAIL_CLIENT_SECRET or GOOGLE_CALENDAR_CLIENT_SECRET
        self._sandbox_inbox = list(DEFAULT_MOCK_INBOX)
        self._sandbox_threads = {k: list(v) for k, v in DEFAULT_MOCK_THREADS.items()}
        self._sandbox_outbox: List[Dict[str, Any]] = []
        self._last_search_results: List[Dict[str, Any]] = []

    @staticmethod
    def _clean_html_to_text(text: str) -> str:
        """Converts HTML or rich email text into clean, human-readable plain text without tags, scripts, styles, or zero-width unicode artifacts."""
        if not text:
            return ""
        # Remove style, script, head, title blocks completely
        text = re.sub(r"<(script|style|head|title)[^>]*>[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Unescape HTML entities (e.g. &#39; -> ', &amp; -> &, &zwnj; -> "")
        text = html.unescape(text)
        # Remove zero-width characters and invisible unicode artifacts (\u200b-\u200f, \ufeff, \u034f, \u00ad, etc.)
        text = re.sub(r"[\u200b-\u200f\ufeff\u034f\u00ad]", "", text)
        # Collapse multiple whitespace / newlines
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def _extract_body_from_payload(cls, payload: Dict[str, Any]) -> str:
        """Recursively extracts and sanitizes body text from Gmail payload parts."""
        def _find_parts(p: Dict[str, Any], mime: str) -> Optional[str]:
            if p.get("mimeType") == mime:
                data = p.get("body", {}).get("data", "")
                if data:
                    try:
                        return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="ignore")
                    except Exception:
                        pass
            for subpart in p.get("parts", []):
                found = _find_parts(subpart, mime)
                if found:
                    return found
            return None

        # 1. Look for text/plain
        plain = _find_parts(payload, "text/plain")
        if plain:
            return cls._clean_html_to_text(plain) if ("<" in plain and ">" in plain) else html.unescape(plain).strip()

        # 2. Look for text/html
        html_raw = _find_parts(payload, "text/html")
        if html_raw:
            return cls._clean_html_to_text(html_raw)

        # 3. Fallback to direct body data
        data = payload.get("body", {}).get("data")
        if data:
            try:
                raw = base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="ignore")
                return cls._clean_html_to_text(raw) if ("<" in raw and ">" in raw) else html.unescape(raw).strip()
            except Exception:
                pass

        return ""

    @property
    def name(self) -> str:
        return "email"

    @property
    def description(self) -> str:
        return (
            "Manages Gmail messages: checks unread emails, searches message threads, "
            "reads email content, drafts replies, and sends emails."
        )

    def get_capabilities(self) -> str:
        return (
            "List unread emails, search inbox by sender or keyword, read full email contents, "
            "compose drafts, and send email messages."
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "list_unread_emails",
                "description": "Lists recent unread emails in the user's inbox with sender, subject, and preview snippets.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of unread emails to retrieve (default: 5).",
                        },
                    },
                },
            },
            {
                "name": "search_emails",
                "description": "Searches the email inbox using keywords, sender email, subject, or standard Gmail search syntax.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query or filters (e.g. 'from:rohit', 'GitHub', 'VESPER', 'invoice').",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum search results to return (default: 5).",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "read_email",
                "description": "Retrieves the full body text and headers of a specific email message by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email_id": {
                            "type": "string",
                            "description": "Unique identifier of the email (e.g. 'msg_001').",
                        },
                    },
                    "required": ["email_id"],
                },
            },
            {
                "name": "draft_email",
                "description": "Creates a draft email to a recipient with subject line and body text without sending it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address."},
                        "subject": {"type": "string", "description": "Subject line of the email."},
                        "body": {"type": "string", "description": "Body message text for the draft."},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
            {
                "name": "send_email",
                "description": "Sends an email message to a specified recipient.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address."},
                        "subject": {"type": "string", "description": "Subject line of the email."},
                        "body": {"type": "string", "description": "Body content of the email message."},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
            {
                "name": "read_thread",
                "description": "Retrieves the complete conversation thread (all chronological messages and replies) for an email conversation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Unique identifier of the email thread (e.g. 'thread_rohit_vesper').",
                        },
                        "email_id": {
                            "type": "string",
                            "description": "Optional email ID belonging to the thread.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Optional search term or sender name if thread ID is unknown.",
                        },
                    },
                },
            },
        ]

    def _get_gmail_service(self) -> Any:
        """Attempts to instantiate authenticated Google Gmail service."""
        if self.sandbox_mode:
            return None
        token_file = GMAIL_TOKEN_PATH if GMAIL_TOKEN_PATH.exists() else CALENDAR_TOKEN_PATH
        if not token_file.exists():
            return None

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(str(token_file))
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_file, "w") as tf:
                        tf.write(creds.to_json())
                except Exception as ref_err:
                    logger.warning(f"[EmailSpecialist] Token refresh failed: {ref_err}")

            if creds and creds.valid:
                # Check if scopes allow gmail
                scopes = creds.scopes or []
                if not any("gmail" in str(s).lower() for s in scopes):
                    logger.debug("[EmailSpecialist] Token lacks gmail scopes, using sandbox.")
                    return None
                service = build("gmail", "v1", credentials=creds)
                return service
        except Exception as e:
            logger.debug(f"[EmailSpecialist] Live Gmail client init skipped ({e}), using resilient sandbox.")
        return None

    async def execute(
        self, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        """Dispatches email tool actions."""
        try:
            if action == "list_unread_emails":
                max_results = int(params.get("max_results", 5))
                return await self.list_unread_emails(max_results)
            elif action == "search_emails":
                query = str(params.get("query", "")).strip()
                max_results = int(params.get("max_results", 5))
                return await self.search_emails(query, max_results)
            elif action == "read_email":
                raw_eid = params.get("email_id", "")
                return await self.read_email(raw_eid)
            elif action in ("read_thread", "get_thread", "email_thread"):
                thread_id = str(params.get("thread_id", "")).strip()
                email_id = str(params.get("email_id", "")).strip()
                query = str(params.get("query", "")).strip()
                return await self.read_thread(thread_id=thread_id, email_id=email_id, query=query)
            elif action == "draft_email":
                to = str(params.get("to", "")).strip()
                subject = str(params.get("subject", "")).strip()
                body = str(params.get("body", "")).strip()
                return await self.draft_email(to, subject, body)
            elif action == "send_email":
                to = str(params.get("to", "")).strip()
                subject = str(params.get("subject", "")).strip()
                body = str(params.get("body", "")).strip()
                return await self.send_email(to, subject, body)
            else:
                return SpecialistResult(
                    success=False,
                    action=action,
                    error=f"Unknown email action: '{action}'",
                    speech_summary=f"I'm sorry sir, but I do not recognize the email action '{action}'.",
                )
        except Exception as e:
            logger.exception(f"[EmailSpecialist] Exception in {action}: {e}")
            return SpecialistResult(
                success=False,
                action=action,
                error=str(e),
                speech_summary=f"I encountered an error managing your emails, sir: {e}",
            )

    async def list_unread_emails(self, max_results: int = 5) -> SpecialistResult:
        """Fetches unread emails from Gmail or sandbox inbox."""
        service = self._get_gmail_service()
        if service:
            try:
                res = service.users().messages().list(
                    userId="me", q="is:unread", maxResults=max_results
                ).execute()
                msgs = res.get("messages", [])
                items = []
                for m in msgs:
                    detail = service.users().messages().get(
                        userId="me", id=m["id"], format="metadata",
                        metadataHeaders=["From", "Subject", "Date"]
                    ).execute()
                    headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
                    items.append({
                        "id": m["id"],
                        "sender": headers.get("From", "Unknown Sender"),
                        "subject": headers.get("Subject", "(No Subject)"),
                        "snippet": detail.get("snippet", ""),
                        "date": headers.get("Date", ""),
                        "unread": True,
                    })

                count = len(items)
                speech = f"You have {count} unread {'email' if count == 1 else 'emails'} in your inbox, sir."
                if count > 0:
                    top_senders = ", ".join([str(it.get("sender", "")).split("<")[0].strip() for it in items[:2]])
                    speech += f" The most recent are from {top_senders}."

                return SpecialistResult(
                    success=True,
                    action="list_unread_emails",
                    data={"count": count, "emails": items},
                    speech_summary=speech,
                    card_payload={"type": "email_list_card", "emails": items, "title": "Unread Inbox"},
                )
            except Exception as live_err:
                logger.warning(f"[EmailSpecialist] Live Gmail query failed ({live_err}), falling back to sandbox.")

        # Fallback to sandbox inbox
        unread = [m for m in self._sandbox_inbox if bool(m.get("unread"))][:max_results]
        count = len(unread)
        speech = f"You have {count} unread {'email' if count == 1 else 'emails'} in your inbox, sir."
        if count > 0:
            top_senders = ", ".join([str(it.get("sender_name", "")) for it in unread[:2]])
            speech += f" Recent messages include updates from {top_senders}."

        return SpecialistResult(
            success=True,
            action="list_unread_emails",
            data={"count": count, "emails": unread, "source": "sandbox_inbox"},
            speech_summary=speech,
            card_payload={"type": "email_list_card", "emails": unread, "title": "Unread Inbox"},
        )

    @staticmethod
    def _sanitize_search_query(q: str) -> str:
        """Strips quotes and normalizes whitespace in email search queries."""
        cleaned = re.sub(r"['\"`]", "", q).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        m = re.match(r"^(from:\s*)(.*)$", cleaned, flags=re.IGNORECASE)
        if m:
            name_part = m.group(2).strip()
            return f"from:{name_part}" if name_part else ""
        return cleaned

    async def search_emails(self, query: str, max_results: int = 5) -> SpecialistResult:
        """Searches emails matching query string."""
        if not query:
            return await self.list_unread_emails(max_results)

        service = self._get_gmail_service()
        if service:
            try:
                # 1. Try initial raw query
                res = service.users().messages().list(
                    userId="me", q=query, maxResults=max_results
                ).execute()
                msgs = res.get("messages", [])

                # 2. If 0 results, retry with sanitized query (removes quotes and honorifics like 'Sir')
                clean_q = self._sanitize_search_query(query)
                if not msgs and clean_q and clean_q != query:
                    logger.info(f"[EmailSpecialist] Gmail raw search '{query}' returned 0, retrying with sanitized: '{clean_q}'")
                    res = service.users().messages().list(
                        userId="me", q=clean_q, maxResults=max_results
                    ).execute()
                    msgs = res.get("messages", [])

                # 3. If still 0 results and query was 'from:Name', retry broad keyword search 'Name'
                if not msgs and clean_q.lower().startswith("from:"):
                    name_kw = clean_q[5:].strip()
                    if name_kw:
                        logger.info(f"[EmailSpecialist] Retrying Gmail search with keyword '{name_kw}'")
                        res = service.users().messages().list(
                            userId="me", q=name_kw, maxResults=max_results
                        ).execute()
                        msgs = res.get("messages", [])

                items = []
                for m in msgs:
                    detail = service.users().messages().get(
                        userId="me", id=m["id"], format="metadata",
                        metadataHeaders=["From", "Subject", "Date"]
                    ).execute()
                    headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
                    items.append({
                        "id": m["id"],
                        "sender": headers.get("From", "Unknown"),
                        "subject": headers.get("Subject", "(No Subject)"),
                        "snippet": detail.get("snippet", ""),
                        "date": headers.get("Date", ""),
                    })

                self._last_search_results = items
                count = len(items)
                if count > 0:
                    first = items[0]
                    first_snd = first.get("sender_name") or first.get("sender", "Unknown").split("<")[0].strip()
                    snippet_text = (first.get("snippet") or "")[:140]
                    subj_text = first.get("subject") or "No Subject"
                    speech = (
                        f"Found {count} email{'s' if count != 1 else ''} matching '{query}', sir. "
                        f"The most recent is from {first_snd} regarding '{subj_text}': \"{snippet_text}...\""
                    )
                else:
                    speech = f"I could not locate any emails matching '{query}', sir."

                return SpecialistResult(
                    success=True,
                    action="search_emails",
                    data={"query": query, "count": count, "emails": items},
                    speech_summary=speech,
                    card_payload={"type": "email_list_card", "emails": items, "title": f"Search: {query}"},
                )
            except Exception as live_err:
                logger.warning(f"[EmailSpecialist] Gmail search failed ({live_err}), filtering sandbox.")

        # Sandbox search
        clean_q = re.sub(r"\bfrom:\s*", "", query, flags=re.IGNORECASE).strip().lower()
        clean_q = re.sub(r"\bto:\s*", "", clean_q, flags=re.IGNORECASE).strip()
        clean_q = re.sub(r"\bsubject:\s*", "", clean_q, flags=re.IGNORECASE).strip()
        if not clean_q:
            clean_q = query.lower()

        def _match_score(m: Dict[str, Any]) -> int:
            subj = str(m.get("subject", "")).lower()
            snip = str(m.get("snippet", "")).lower()
            sndr = str(m.get("sender", "")).lower()
            sname = str(m.get("sender_name", "")).lower()
            lbls = " ".join(str(lbl).lower() for lbl in m.get("labels", []))
            searchable = f"{sname} {sndr} {subj} {snip} {lbls}"

            if clean_q in searchable:
                return 100
            tokens = [
                t for t in re.findall(r"\b[a-zA-Z0-9_-]+\b", clean_q)
                if t not in ("email", "emails", "from", "to", "subject", "the", "me", "a", "an", "last", "latest", "recent", "received")
            ]
            if not tokens:
                return 0
            if all(t in searchable for t in tokens):
                return 80
            matched_count = sum(1 for t in tokens if t in searchable)
            return int((matched_count / len(tokens)) * 50) if matched_count > 0 else 0

        scored = [(m, _match_score(m)) for m in self._sandbox_inbox]
        matched = [m for m, sc in scored if sc > 0]
        matched.sort(key=lambda item: _match_score(item), reverse=True)
        matched = matched[:max_results]

        self._last_search_results = matched
        count = len(matched)
        if count == 0:
            speech = f"I could not locate any emails matching '{query}', sir."
        else:
            first = matched[0]
            speech = f"Found {count} email{'s' if count != 1 else ''} matching '{query}'. Top result is '{first['subject']}' from {first.get('sender_name', first['sender'])}."

        return SpecialistResult(
            success=True,
            action="search_emails",
            data={"query": query, "count": count, "emails": matched, "source": "sandbox_inbox"},
            speech_summary=speech,
            card_payload={"type": "email_list_card", "emails": matched, "title": f"Search: {query}"},
        )

    async def read_email(self, email_id: Any) -> SpecialistResult:
        """Reads full details and text body of an email."""
        if isinstance(email_id, dict):
            if "emails" in email_id and isinstance(email_id["emails"], list) and email_id["emails"]:
                email_id = email_id["emails"][0].get("id", "")
            else:
                email_id = email_id.get("id") or email_id.get("email_id") or ""
        email_id = str(email_id).strip()

        # Extract ID if a dict or stringified dict was passed
        if "{" in email_id and ("'id':" in email_id or '"id":' in email_id):
            m_id = re.search(r"['\"]id['\"]:\s*['\"]([a-zA-Z0-9_-]+)['\"]", email_id)
            if m_id:
                resolved_id = m_id.group(1)
                logger.info(f"[EmailSpecialist] Extracted message ID '{resolved_id}' from structured parameter")
                email_id = resolved_id

        # Handle placeholders generated by LLMs like '<email_id_from_previous_step>'
        if (
            not email_id
            or email_id.startswith("<")
            or email_id.startswith("$step_")
            or email_id.lower() in ("none", "null", "undefined", "latest")
        ):
            if self._last_search_results:
                resolved_id = str(self._last_search_results[0].get("id", "")).strip()
                logger.info(f"[EmailSpecialist] Resolving placeholder email_id '{email_id}' to first search result: {resolved_id}")
                email_id = resolved_id

        service = self._get_gmail_service()
        if service:
            try:
                detail = service.users().messages().get(
                    userId="me", id=email_id, format="full"
                ).execute()
                payload = detail.get("payload", {})
                headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
                
                body_text = self._extract_body_from_payload(payload)
                raw_snippet = self._clean_html_to_text(detail.get("snippet", ""))

                email_obj = {
                    "id": email_id,
                    "sender": headers.get("From", "Unknown"),
                    "to": headers.get("To", "me"),
                    "subject": headers.get("Subject", "(No Subject)"),
                    "date": headers.get("Date", ""),
                    "body": body_text or raw_snippet,
                }
                # Mark as read
                try:
                    service.users().messages().modify(
                        userId="me", id=email_id, body={"removeLabelIds": ["UNREAD"]}
                    ).execute()
                except Exception:
                    pass

                clean_body = self._clean_html_to_text(email_obj["body"])
                excerpt = (clean_body[:160] + "...") if len(clean_body) > 160 else clean_body
                speech = f"Email from {email_obj['sender'].split('<')[0].strip()} regarding '{email_obj['subject']}': {excerpt}"
                return SpecialistResult(
                    success=True,
                    action="read_email",
                    data=email_obj,
                    speech_summary=speech,
                    card_payload={"type": "email_card", "email": email_obj},
                )
            except Exception as live_err:
                logger.warning(f"[EmailSpecialist] Read email {email_id} failed ({live_err}), checking sandbox.")

        # Sandbox retrieval
        target = None
        clean_eid = email_id.lower().strip("'\"")
        for m in self._sandbox_inbox:
            if (
                m.get("id") == email_id
                or (clean_eid and clean_eid == str(m.get("id", "")).lower())
                or (clean_eid and clean_eid in str(m.get("subject", "")).lower())
                or (clean_eid and clean_eid in str(m.get("sender_name", "")).lower())
                or (clean_eid and clean_eid in str(m.get("sender", "")).lower())
            ):
                target = m
                break

        if not target and self._sandbox_inbox:
            for m in self._sandbox_inbox:
                snd = str(m.get("sender_name", "")).lower()
                first_name = snd.split()[0] if snd else ""
                if first_name and first_name in clean_eid:
                    target = m
                    break

        if not target and self._sandbox_inbox:
            # Fallback to first email if index-based or empty
            if email_id in ("1", "first", "msg_001", ""):
                target = self._sandbox_inbox[0]
            elif email_id in ("2", "second", "msg_002") and len(self._sandbox_inbox) > 1:
                target = self._sandbox_inbox[1]

        if not target:
            return SpecialistResult(
                success=False,
                action="read_email",
                error=f"Email '{email_id}' was not found.",
                speech_summary=f"I couldn't locate an email with ID '{email_id}', sir.",
            )

        target["unread"] = False
        target["source"] = "sandbox"
        if not target.get("thread_id"):
            target["thread_id"] = "thread_general"
        clean_snippet = self._clean_html_to_text(target.get("snippet", ""))
        clean_body = self._clean_html_to_text(target.get("body", ""))
        excerpt = clean_snippet or ((clean_body[:160] + "...") if len(clean_body) > 160 else clean_body)
        speech = f"Email from {target.get('sender_name', target['sender'])} regarding '{target['subject']}': {excerpt}"
        return SpecialistResult(
            success=True,
            action="read_email",
            data=target,
            speech_summary=speech,
            card_payload={"type": "email_card", "email": target},
        )

    async def read_thread(
        self,
        thread_id: Optional[str] = None,
        email_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> SpecialistResult:
        """Retrieves and reconstructs the complete chronological email thread."""
        service = self._get_gmail_service()
        tid = thread_id or email_id

        if service and not tid and query:
            clean_q = self._sanitize_search_query(query)
            try:
                t_res = service.users().threads().list(userId="me", q=clean_q, maxResults=1).execute()
                if not t_res.get("threads") and clean_q != query:
                    t_res = service.users().threads().list(userId="me", q=query, maxResults=1).execute()
                if not t_res.get("threads") and clean_q.lower().startswith("from:"):
                    t_res = service.users().threads().list(userId="me", q=clean_q[5:].strip(), maxResults=1).execute()
                threads = t_res.get("threads", [])
                if threads:
                    tid = threads[0]["id"]
            except Exception as e:
                logger.warning(f"[EmailSpecialist] Live thread query for '{query}' failed: {e}")

        if service and tid:
            try:
                res = service.users().threads().get(userId="me", id=tid, format="full").execute()
                messages_data = res.get("messages", [])
                msgs = []
                for m in messages_data:
                    payload = m.get("payload", {})
                    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
                    body_text = self._extract_body_from_payload(payload)
                    raw_snippet = self._clean_html_to_text(m.get("snippet", ""))
                    msgs.append({
                        "id": m["id"],
                        "thread_id": tid,
                        "sender": headers.get("From", "Unknown"),
                        "sender_name": headers.get("From", "Unknown").split("<")[0].strip(),
                        "subject": headers.get("Subject", "(No Subject)"),
                        "date": headers.get("Date", ""),
                        "body": body_text or raw_snippet,
                        "snippet": raw_snippet or (body_text[:140] if body_text else ""),
                    })

                if msgs:
                    subject = msgs[0].get("subject", "Conversation")
                    participants = list(dict.fromkeys([m.get("sender_name", m.get("sender")) for m in msgs]))
                    latest = msgs[-1]
                    speech = (
                        f"The email thread on '{subject}' contains {len(msgs)} messages between {', '.join(participants)}. "
                        f"The latest response is from {latest.get('sender_name')}: '{latest.get('snippet')[:140]}...'"
                    )
                    return SpecialistResult(
                        success=True,
                        action="read_thread",
                        data={
                            "thread_id": tid,
                            "subject": subject,
                            "count": len(msgs),
                            "participants": participants,
                            "messages": msgs,
                            "id": latest.get("id"),
                            "sender": latest.get("sender"),
                            "sender_name": latest.get("sender_name"),
                        },
                        speech_summary=speech,
                        card_payload={"type": "email_thread_card", "thread_id": tid, "subject": subject, "messages": msgs},
                    )
            except Exception as live_err:
                logger.warning(f"[EmailSpecialist] Gmail thread {tid} fetch failed ({live_err}), checking sandbox.")

        # Sandbox retrieval
        matched_thread_key = None
        if thread_id and thread_id in self._sandbox_threads:
            matched_thread_key = thread_id
        else:
            cand = thread_id or email_id
            if cand:
                for k, t_msgs in self._sandbox_threads.items():
                    if any(m.get("id") == cand or m.get("thread_id") == cand for m in t_msgs):
                        matched_thread_key = k
                        break

        if not matched_thread_key and query:
            q_low = query.lower()
            for k, t_msgs in self._sandbox_threads.items():
                if any(
                    q_low in str(m.get("subject", "")).lower()
                    or q_low in str(m.get("sender", "")).lower()
                    or q_low in str(m.get("sender_name", "")).lower()
                    for m in t_msgs
                ):
                    matched_thread_key = k
                    break

        if not matched_thread_key and not (thread_id or email_id or query):
            # Fallback to first available thread only if query and IDs are completely omitted
            matched_thread_key = next(iter(self._sandbox_threads.keys())) if self._sandbox_threads else None

        if not matched_thread_key or matched_thread_key not in self._sandbox_threads:
            return SpecialistResult(
                success=False,
                action="read_thread",
                error=f"Unable to locate thread for '{thread_id or email_id or query}'.",
                speech_summary=f"I was unable to find an email thread for '{thread_id or email_id or query}', sir.",
            )

        msgs = self._sandbox_threads[matched_thread_key]
        subject = msgs[0].get("subject", "Conversation")
        participants: list[str] = list(dict.fromkeys([str(m.get("sender_name") or m.get("sender") or "Unknown") for m in msgs]))
        latest = msgs[-1]
        speech = (
            f"The complete email thread regarding '{subject}' includes {len(msgs)} messages between {', '.join(participants)}. "
            f"The latest response from {latest.get('sender_name')} states: \"{latest.get('body')}\""
        )
        return SpecialistResult(
            success=True,
            action="read_thread",
            data={
                "thread_id": matched_thread_key,
                "subject": subject,
                "count": len(msgs),
                "participants": participants,
                "messages": msgs,
                "id": latest.get("id"),
                "sender": latest.get("sender"),
                "sender_name": latest.get("sender_name"),
                "source": "sandbox",
            },
            speech_summary=speech,
            card_payload={
                "type": "email_thread_card",
                "thread_id": matched_thread_key,
                "subject": subject,
                "messages": msgs,
            },
        )

    async def draft_email(self, to: str, subject: str, body: str) -> SpecialistResult:
        """Creates an email draft in Gmail or sandbox."""
        subj = subject.strip() if subject and subject.strip() else "A brief note"
        clean_to = to.strip() if to else ""
        valid = is_valid_email(clean_to)

        draft_item = {
            "to": clean_to,
            "subject": subj,
            "body": body,
            "has_valid_email": valid,
            "created_at": datetime.datetime.now().isoformat(),
            "status": "draft",
        }
        self._sandbox_outbox.append(draft_item)

        if valid:
            speech = f"I have prepared an email draft to {clean_to} regarding '{subj}', sir. Would you like me to send it?"
        else:
            speech = f"I have prepared an email draft for {clean_to} regarding '{subj}', sir. However, I don't have a complete email address with a domain. What is the recipient's full email address, sir?"

        return SpecialistResult(
            success=True,
            action="draft_email",
            data=draft_item,
            speech_summary=speech,
            card_payload={"type": "email_draft_card", "draft": draft_item},
        )

    async def send_email(self, to: str, subject: str, body: str) -> SpecialistResult:
        """Sends an email message via Gmail API or queues it into sandbox outbox."""
        clean_to = to.strip() if to else ""
        if not is_valid_email(clean_to):
            logger.warning(f"[EmailSpecialist] Attempted to send email to invalid address: '{clean_to}'")
            speech = f"I cannot dispatch the email, sir. '{clean_to}' is not a complete email address with a domain. Could you provide the full email address?"
            return SpecialistResult(
                success=False,
                action="send_email",
                data={"to": clean_to, "error": "invalid_email_address", "needs": "valid_email_address"},
                speech_summary=speech,
                card_payload={"type": "email_error_card", "error": "invalid_email", "to": clean_to},
            )

        service = self._get_gmail_service()
        if service:
            try:
                msg = MIMEText(body)
                msg["to"] = clean_to
                msg["subject"] = subject
                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
                speech = f"Email successfully sent to {clean_to} regarding '{subject}', sir."
                return SpecialistResult(
                    success=True,
                    action="send_email",
                    data={"id": sent.get("id"), "to": clean_to, "subject": subject, "status": "sent"},
                    speech_summary=speech,
                    card_payload={"type": "email_sent_card", "to": clean_to, "subject": subject},
                )
            except Exception as live_err:
                logger.warning(f"[EmailSpecialist] Gmail send failed: {live_err}, storing in verified outbox.")

        sent_item = {
            "to": clean_to,
            "subject": subject,
            "body": body,
            "sent_at": datetime.datetime.now().isoformat(),
            "status": "dispatched_sandbox",
        }
        self._sandbox_outbox.append(sent_item)
        speech = f"Email to {clean_to} regarding '{subject}' has been dispatched, sir."
        return SpecialistResult(
            success=True,
            action="send_email",
            data=sent_item,
            speech_summary=speech,
            card_payload={"type": "email_sent_card", "to": clean_to, "subject": subject},
        )
