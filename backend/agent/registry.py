"""VESPER Dynamic Specialist Tool Registry.

Tracks and orchestrates all active sub-agents in the cognitive swarm.
Allows Alfred to discover specialist capabilities dynamically without
hardcoding or bloating the system prompt.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agent.specialists.base import BaseSpecialist, SpecialistResult

logger = logging.getLogger("vesper.agent.registry")


class SpecialistRegistry:
    """Central registry for discovering and querying specialist sub-agents."""

    def __init__(self) -> None:
        self._specialists: Dict[str, BaseSpecialist] = {}

    def register(self, specialist: BaseSpecialist) -> None:
        """Registers a specialist agent into the swarm."""
        name = specialist.name.lower().strip()
        if name in self._specialists:
            logger.warning(f"[Registry] Overwriting existing specialist: {name}")
        self._specialists[name] = specialist
        logger.info(f"[Registry] Registered specialist: '{name}'")

    def unregister(self, name: str) -> Optional[BaseSpecialist]:
        """Removes a specialist agent by name."""
        return self._specialists.pop(name.lower().strip(), None)

    def get(self, name: str) -> Optional[BaseSpecialist]:
        """Retrieves a specialist agent by name."""
        return self._specialists.get(name.lower().strip())

    def list_specialists(self) -> List[BaseSpecialist]:
        """Returns all currently registered specialist instances."""
        return list(self._specialists.values())

    def get_capabilities_prompt(
        self,
        compact: bool = True,
        specialist_names: Optional[List[str]] = None,
    ) -> str:
        """Builds a token-efficient domain and action prompt for Alfred's Stage 1 Planner."""
        if not self._specialists:
            return "No specialist agents are currently active."

        specs = list(self._specialists.values())
        if specialist_names:
            target_set = {n.lower().strip() for n in specialist_names}
            matched = [s for s in specs if s.name.lower().strip() in target_set]
            if matched:
                specs = matched

        if not compact:
            lines = ["Available Specialists, Actions, and Tools:"]
            for spec in specs:
                lines.append(f"\n- {spec.name}: {spec.get_capabilities()}")
                tools = spec.get_tool_schemas()
                if tools:
                    lines.append("  Actions:")
                    for t in tools:
                        props = t.get("parameters", {}).get("properties", {})
                        params_str = ", ".join([f"{k}: {v.get('type', 'any')}" for k, v in props.items()])
                        lines.append(f"    - action: '{t['name']}'({params_str}) -> {t.get('description', '')}")
                else:
                    lines.append(f"  Capabilities: {spec.get_capabilities()}")
            return "\n".join(lines)

        # High-density compact format (saves ~75% tokens)
        lines = ["Available Specialists & Actions:"]
        for spec in specs:
            tools = spec.get_tool_schemas()
            actions_summary = []
            for t in tools:
                props = t.get("parameters", {}).get("properties", {})
                reqs = t.get("parameters", {}).get("required", [])
                p_list = [k if k in reqs else f"{k}?" for k in props]
                actions_summary.append(f"'{t['name']}'({', '.join(p_list)})")
            acts_str = " | ".join(actions_summary) if actions_summary else ""
            lines.append(f"- {spec.name}: {spec.get_capabilities()} -> Actions: [{acts_str}]")
        return "\n".join(lines)

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        """Collects all tool schemas across all registered specialists."""
        schemas: List[Dict[str, Any]] = []
        for spec in self._specialists.values():
            schemas.extend(spec.get_tool_schemas())
        return schemas

    async def execute_action(
        self, agent_name: str, action: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> SpecialistResult:
        """Dispatches an action to the designated specialist."""
        spec = self.get(agent_name)
        if not spec:
            err_msg = f"Specialist '{agent_name}' is not registered in the swarm."
            logger.error(f"[Registry] {err_msg}")
            return SpecialistResult(success=False, action=action, error=err_msg)

        try:
            result = await spec.execute(action, params, context)
            result.agent_name = agent_name  # Stamp for trace logging
            return result
        except Exception as e:
            logger.exception(f"[Registry] Error executing action '{action}' on specialist '{agent_name}': {e}")
            return SpecialistResult(success=False, action=action, agent_name=agent_name, error=str(e))



# Global default registry instance
registry = SpecialistRegistry()


def register_default_specialists(reg: SpecialistRegistry) -> None:
    """Registers standard production specialists into the swarm."""
    try:
        from backend.agent.specialists.task_specialist import TaskSpecialist
        reg.register(TaskSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load TaskSpecialist: {e}")

    try:
        from backend.agent.specialists.media_specialist import MediaSpecialist
        reg.register(MediaSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load MediaSpecialist: {e}")

    try:
        from backend.agent.specialists.research_specialist import ResearchSpecialist
        reg.register(ResearchSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load ResearchSpecialist: {e}")

    try:
        from backend.agent.specialists.crawl_specialist import CrawlSpecialist
        reg.register(CrawlSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load CrawlSpecialist: {e}")

    try:
        from backend.agent.specialists.finance_specialist import FinanceSpecialist
        reg.register(FinanceSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load FinanceSpecialist: {e}")

    try:
        from backend.agent.specialists.system_specialist import SystemSpecialist
        reg.register(SystemSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load SystemSpecialist: {e}")

    try:
        from backend.agent.specialists.memory_specialist import MemorySpecialist
        reg.register(MemorySpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load MemorySpecialist: {e}")

    try:
        from backend.agent.specialists.vision_specialist import VisionSpecialist
        reg.register(VisionSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load VisionSpecialist: {e}")

    try:
        from backend.agent.specialists.github_specialist import GitHubSpecialist
        reg.register(GitHubSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load GitHubSpecialist: {e}")

    try:
        from backend.agent.specialists.email_specialist import EmailSpecialist
        reg.register(EmailSpecialist())
    except Exception as e:
        logger.warning(f"[Registry] Could not load EmailSpecialist: {e}")


# Initialize default specialists
register_default_specialists(registry)

