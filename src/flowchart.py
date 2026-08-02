"""Structured recipe steps -> Mermaid flowchart syntax."""

from __future__ import annotations


def to_mermaid(steps: list[dict]) -> str:
    lines = ["graph TD"]
    for step in steps:
        lines.append(f'    {step["id"]}["{_label(step)}"]')
    for step in steps:
        for dep in step.get("depends_on") or []:
            lines.append(f'    {dep} --> {step["id"]}')
    return "\n".join(lines)


def _label(step: dict) -> str:
    text = step["text"].replace('"', "'").replace("\n", " ")
    duration = step.get("duration_min")
    if duration:
        text += f" ({duration} min)"
    return text
