"""Unit tests for Title Normalization, HTML Speech Sanitization, and Camera Gateway Routes."""

import pytest
from backend.agent.title_normalizer import (
    build_action,
    classify_action_type,
    extract_time_phrase,
    normalize_title,
)
from backend.agent.specialists.email_specialist import EmailSpecialist
from backend.voice.tts.normalizer import SpeechNormalizer
from backend.gateway.app import create_app
from fastapi.testclient import TestClient


def test_title_normalizer_core():
    # 1. Remind me with conversational prefix and trailing time
    raw = "Remind me to go pick up my mom at 5.45 today."
    action = build_action(raw)
    assert action.action_type == "reminder"
    assert action.title == "Pick up my mom"
    assert action.time_phrase is not None and "5.45" in action.time_phrase

    # 2. Add task without time
    raw2 = "add a task to clean the kitchen"
    action2 = build_action(raw2)
    assert action2.action_type == "task"
    assert action2.title == "Clean the kitchen"

    # 3. Calendar event
    raw3 = "schedule sync meeting with Rohit tomorrow at 4pm"
    action3 = build_action(raw3)
    assert action3.action_type == "event"
    assert "meeting with Rohit" in action3.title.lower() or "sync" in action3.title.lower()
    assert action3.time_phrase is not None and "4pm" in action3.time_phrase


def test_email_and_tts_html_stripping():
    sample_html = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN">\n'
        '<html dir="ltr" xmlns="http://www.w3.org/1999/xhtml">\n'
        '<head><style type="text/css">p { color: red; }</style><script>alert(1);</script></head>\n'
        '<body><p>Hello Mihir,&#39;s application has been updated!&nbsp;&zwnj;</p></body></html>'
    )

    # 1. EmailSpecialist._clean_html_to_text
    clean_email = EmailSpecialist._clean_html_to_text(sample_html)
    assert "<!DOCTYPE" not in clean_email
    assert "<html" not in clean_email
    assert "<style" not in clean_email
    assert "alert" not in clean_email
    assert "Hello Mihir,'s application has been updated!" in clean_email

    # 2. SpeechNormalizer.normalize_for_speech
    clean_spoken = SpeechNormalizer.normalize_for_speech(sample_html)
    assert "<!DOCTYPE" not in clean_spoken
    assert "<html" not in clean_spoken
    assert "<style" not in clean_spoken
    assert "alert" not in clean_spoken
    assert "Hello Mihir" in clean_spoken


def test_camera_gateway_status():
    app = create_app()
    client = TestClient(app)
    res = client.get("/api/camera/status")
    assert res.status_code == 200
    data = res.json()
    assert "available" in data
    assert "available_indices" in data


@pytest.mark.asyncio
async def test_temporal_awareness_and_task_filtering():
    import datetime
    from backend.agent.specialists.task_specialist import TaskSpecialist
    from backend.data.models import TaskModel
    from backend.data.repositories.tasks import TaskRepository

    class MockRepo(TaskRepository):
        def __init__(self):
            super().__init__(client=None)
            now = datetime.datetime.now().astimezone()
            yesterday = now - datetime.timedelta(days=1)
            self._items = [
                TaskModel(
                    id="t_past_1",
                    user_id="default_user",
                    title="Past Task From Yesterday",
                    done=False,
                    priority="normal",
                    created_at=yesterday,
                ),
                TaskModel(
                    id="t_today_1",
                    user_id="default_user",
                    title="Task Created Today",
                    done=False,
                    priority="high",
                    created_at=now,
                ),
                TaskModel(
                    id="t_overdue_1",
                    user_id="default_user",
                    title="Overdue Task",
                    done=False,
                    priority="high",
                    deadline=yesterday,
                    created_at=yesterday - datetime.timedelta(days=2),
                ),
            ]

        def list(self, *args, **kwargs):
            return list(self._items)

    spec = TaskSpecialist(repo=MockRepo())
    agenda = await spec.execute("get_daily_agenda", {"date": "today"})
    assert agenda.success is True
    today_titles = [t["title"] for t in agenda.data["tasks"]]
    # Strictly today's task must be present, past and overdue tasks must NOT be in today's task list!
    assert "Task Created Today" in today_titles
    assert "Past Task From Yesterday" not in today_titles
    assert "Overdue Task" not in today_titles
    assert agenda.data["backlog_count"] >= 1
    assert agenda.data["overdue_count"] >= 1
    assert "Task Created Today" in agenda.speech_summary

    # Test list_tasks with date="today"
    list_res = await spec.execute("list_tasks", {"date": "today"})
    assert list_res.success is True
    list_titles = [t["title"] for t in list_res.data["tasks"]]
    assert "Task Created Today" in list_titles
    assert "Past Task From Yesterday" not in list_titles

