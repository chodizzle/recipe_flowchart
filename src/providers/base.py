"""Shared interface and structured-output contract for recipe-extraction providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

RECIPE_STEPS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "The recipe's title"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Short unique step id, e.g. 's1'"},
                    "text": {"type": "string", "description": "One imperative instruction"},
                    "duration_min": {
                        "type": ["number", "null"],
                        "description": "Active or wait time in minutes, or null if not stated/estimable",
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of steps that must finish before this one can start. Empty if it can start immediately.",
                    },
                },
                "required": ["id", "text", "duration_min", "depends_on"],
            },
        },
    },
    "required": ["title", "steps"],
}

EXTRACTION_INSTRUCTIONS = (
    "You are extracting structured step data from a recipe. Read the recipe "
    "(text or a photo of one, possibly handwritten and mixing languages) and break it "
    "into discrete steps. For each step, identify which other steps it depends on "
    "(depends_on) -- meaning it cannot start until those finish. Steps with no shared "
    "dependency chain should have no overlapping depends_on so they read as independent "
    "and can run in parallel (e.g. 'boil pasta' and 'make sauce' are usually independent "
    "until a step that combines them). Keep step text short and imperative. Use "
    "duration_min for stated or clearly implied active/wait times; use null if not "
    "stated. Assign short sequential ids like s1, s2, ..."
)


@dataclass
class ExtractionResult:
    provider: str
    model: str
    title: str
    steps: list[dict]
    input_tokens: int
    output_tokens: int
    latency_s: float
    estimated_cost_usd: float


class Provider(ABC):
    name: str

    @abstractmethod
    def extract_from_text(self, text: str, model: str) -> ExtractionResult: ...

    @abstractmethod
    def extract_from_image(self, image_path: Path, model: str) -> ExtractionResult: ...
