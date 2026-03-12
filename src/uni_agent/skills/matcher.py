from __future__ import annotations

from uni_agent.shared.models import SkillSpec


class SkillMatcher:
    def match(self, task: str, skills: list[SkillSpec]) -> list[SkillSpec]:
        task_lower = task.lower()
        scored: list[tuple[int, SkillSpec]] = []
        for skill in skills:
            score = skill.priority
            for trigger in skill.triggers:
                if trigger.lower() in task_lower:
                    score += 10
            if score > skill.priority:
                scored.append((score, skill))
        return [skill for _, skill in sorted(scored, key=lambda item: item[0], reverse=True)]

