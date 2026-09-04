"""VESPER Specialists Module."""

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult
from backend.agent.specialists.crawl_specialist import CrawlSpecialist
from backend.agent.specialists.email_specialist import EmailSpecialist
from backend.agent.specialists.finance_specialist import FinanceSpecialist
from backend.agent.specialists.github_specialist import GitHubSpecialist
from backend.agent.specialists.media_specialist import MediaSpecialist
from backend.agent.specialists.memory_specialist import MemorySpecialist
from backend.agent.specialists.research_specialist import ResearchSpecialist
from backend.agent.specialists.system_specialist import SystemSpecialist
from backend.agent.specialists.task_specialist import TaskSpecialist
from backend.agent.specialists.task_triage import AsyncTaskTriageWorker
from backend.agent.specialists.vision_specialist import VisionSpecialist

__all__ = [
    "BaseSpecialist",
    "SpecialistResult",
    "TaskSpecialist",
    "MediaSpecialist",
    "ResearchSpecialist",
    "CrawlSpecialist",
    "FinanceSpecialist",
    "SystemSpecialist",
    "MemorySpecialist",
    "VisionSpecialist",
    "GitHubSpecialist",
    "EmailSpecialist",
    "AsyncTaskTriageWorker",
]

