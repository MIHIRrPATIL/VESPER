"""Unit Tests for GitHubSpecialist, EmailSpecialist, and Swarm Registry."""

import pytest
from backend.agent.registry import registry
from backend.agent.specialists.github_specialist import GitHubSpecialist
from backend.agent.specialists.email_specialist import EmailSpecialist


def test_specialist_registration():
    gh = registry.get("github")
    em = registry.get("email")

    assert gh is not None
    assert isinstance(gh, GitHubSpecialist)
    assert gh.name == "github"

    assert em is not None
    assert isinstance(em, EmailSpecialist)
    assert em.name == "email"


@pytest.mark.asyncio
async def test_email_specialist_list_unread():
    em = EmailSpecialist()
    res = await em.execute("list_unread_emails", {"max_results": 5})

    assert res.success is True
    assert res.action == "list_unread_emails"
    assert "count" in res.data
    assert "emails" in res.data
    assert len(res.speech_summary) > 0
    assert res.card_payload is not None
    assert res.card_payload["type"] == "email_list_card"


@pytest.mark.asyncio
async def test_email_specialist_search():
    em = EmailSpecialist()
    res = await em.execute("search_emails", {"query": "VESPER"})

    assert res.success is True
    assert res.action == "search_emails"
    assert "emails" in res.data
    assert res.data["count"] >= 1
    assert "VESPER" in res.speech_summary or "vesper" in res.speech_summary.lower()


@pytest.mark.asyncio
async def test_email_specialist_read():
    em = EmailSpecialist()
    res = await em.execute("read_email", {"email_id": "msg_001"})

    assert res.success is True
    assert res.data["id"] == "msg_001"
    assert "Rohit" in res.speech_summary or "rohit" in res.data["sender"]


@pytest.mark.asyncio
async def test_email_specialist_draft_and_send():
    em = EmailSpecialist()
    draft_res = await em.execute(
        "draft_email",
        {"to": "colleague@domain.com", "subject": "Quarterly Plan", "body": "Ready for review."},
    )
    assert draft_res.success is True
    assert draft_res.card_payload is not None
    assert draft_res.card_payload["type"] == "email_draft_card"

    send_res = await em.execute(
        "send_email",
        {"to": "colleague@domain.com", "subject": "Quarterly Plan", "body": "Dispatched."},
    )
    assert send_res.success is True
    assert "dispatched" in send_res.speech_summary.lower() or "sent" in send_res.speech_summary.lower()


@pytest.mark.asyncio
async def test_email_specialist_read_thread():
    em = EmailSpecialist()
    res = await em.execute("read_thread", {"thread_id": "thread_rohit_vesper"})

    assert res.success is True
    assert res.action == "read_thread"
    assert res.data["thread_id"] == "thread_rohit_vesper"
    assert res.data["count"] == 3
    assert len(res.data["messages"]) == 3
    assert res.card_payload is not None
    assert res.card_payload["type"] == "email_thread_card"
    assert "Rohit" in res.speech_summary


@pytest.mark.asyncio
async def test_github_specialist_tool_schemas():
    gh = GitHubSpecialist()
    schemas = gh.get_tool_schemas()
    names = [s["name"] for s in schemas]

    assert "get_repo_info" in names
    assert "search_code" in names
    assert "get_code_snippet" in names
    assert "solve_doubt" in names
    assert "list_issues" in names
    assert "get_recent_commits" in names


@pytest.mark.asyncio
async def test_github_specialist_repo_info_and_snippets():
    gh = GitHubSpecialist()
    res = await gh.execute("get_repo_info", {"repo": "MIHIRrPATIL/VESPER"})

    assert res.success is True
    assert res.data["repo"] == "MIHIRrPATIL/VESPER"
    assert "Python" in res.speech_summary or "VESPER" in res.speech_summary

    snip = await gh.execute(
        "get_code_snippet",
        {"repo": "MIHIRrPATIL/VESPER", "path": "README.md", "start_line": 1, "end_line": 5},
    )
    assert snip.success is True
    assert snip.card_payload is not None
    assert snip.card_payload["type"] == "github_snippet_card"
