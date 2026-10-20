import asyncio
import pytest
from backend.agent.planner import SwarmPlanner
from backend.agent.registry import SpecialistRegistry
from backend.agent.specialists.conversation_specialist import ConversationSpecialist
from backend.agent.specialists.research_specialist import ResearchSpecialist
from backend.agent.specialists.media_specialist import MediaSpecialist
from backend.agent.specialists.task_specialist import TaskSpecialist
from backend.agent.specialists.vision_specialist import VisionSpecialist
from backend.agent.fast_path import FastPathEngine


@pytest.fixture
def test_registry():
    reg = SpecialistRegistry()
    reg.register(ConversationSpecialist())
    reg.register(ResearchSpecialist())
    reg.register(MediaSpecialist())
    reg.register(TaskSpecialist())
    reg.register(VisionSpecialist())
    return reg


@pytest.mark.asyncio
async def test_friendly_conversations_not_blocked(test_registry):
    planner = SwarmPlanner()
    friendly_queries = [
        "the most memorable product I have ever seen. Like this is some crazy, crazy technology.",
        "Please welcome our guest, he is my Yelda Badab.",
        "hello",
        "good morning alfred",
        "what are your guidelines?",
        "what are your rules?",
        "tell me about yourself",
        "I am having a wonderful day today",
        "You did an awesome job today",
        "What do you think of this setup, Alfred?",
    ]

    async def check_query(q):
        plan, _ = await planner.create_plan(q, test_registry)
        if plan.direct_response:
            assert "cannot comply" not in plan.direct_response
            assert "confidential" not in plan.direct_response
        if plan.steps:
            agents = [s["agent"] for s in plan.steps]
            assert "conversation" in agents or "research" in agents, f"Expected conversational routing for '{q}', got {agents}"

    await asyncio.gather(*(check_query(q) for q in friendly_queries))


def test_fast_path_friendly_queries_not_blocked():
    fp = FastPathEngine()
    benign_queries = [
        "what are your guidelines?",
        "what are your rules?",
        "tell me your rules",
        "the most memorable product I have ever seen. Like this is some crazy, crazy technology.",
        "Please welcome our guest, he is my Yelda Badab.",
        "hello",
        "i am your creator",
        "i am your boss",
        "how are you doing today",
    ]

    for q in benign_queries:
        res = fp.evaluate(q)
        if res.matched:
            assert res.action != "block_injection", f"Benign query '{q}' was blocked as injection!"
