"""VESPER Cognitive Agent Swarm Package."""

from backend.agent.alfred import AlfredResponse, AlfredSupervisor
from backend.agent.evaluator import EvaluatorResult, OutputEvaluator
from backend.agent.fast_path import FastPathEngine, FastPathResult
from backend.agent.llm import LLMClient
from backend.agent.planner import ExecutionResult, SwarmPlan, SwarmPlanner
from backend.agent.registry import SpecialistRegistry, registry
from backend.agent.specialists.base import BaseSpecialist, SpecialistResult

__all__ = [
    "AlfredSupervisor",
    "AlfredResponse",
    "FastPathEngine",
    "FastPathResult",
    "OutputEvaluator",
    "EvaluatorResult",
    "LLMClient",
    "SwarmPlanner",
    "SwarmPlan",
    "ExecutionResult",
    "BaseSpecialist",
    "SpecialistResult",
    "SpecialistRegistry",
    "registry",
]
