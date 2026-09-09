"""VESPER Proactive Autonomous Swarm Package."""

from backend.agent.proactive.action_queue import ActionPriority, StagedAction, action_queue
from backend.agent.proactive.audit_logger import audit_logger
from backend.agent.proactive.briefing_manager import BriefingManager, briefing_manager
from backend.agent.proactive.calendar_sentry import calendar_sentry
from backend.agent.proactive.notification_evaluator import notification_evaluator
from backend.agent.proactive.system_sentry import system_sentry

__all__ = [
    "action_queue",
    "ActionPriority",
    "StagedAction",
    "audit_logger",
    "BriefingManager",
    "briefing_manager",
    "calendar_sentry",
    "notification_evaluator",
    "system_sentry",
]
