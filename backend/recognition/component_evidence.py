"""Load human-maintained component evidence for visual prompt grounding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from recognition.component_catalog import supported_component_types

EVIDENCE_PATH = Path(__file__).resolve().parents[1] / "data" / "component-evidence.json"


def load_component_evidence(path: Path = EVIDENCE_PATH) -> dict[str, dict[str, tuple[str, ...] | str]]:
    """Load valid catalog evidence from the editable JSON file.

    Invalid or unknown entries are ignored so a partial local edit cannot block a
    drawing-analysis task. The catalog remains the authority for permitted types.
    """
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("components")
    if not isinstance(entries, dict):
        return {}
    allowed = set(supported_component_types())
    evidence: dict[str, dict[str, tuple[str, ...] | str]] = {}
    for component_type, value in entries.items():
        if component_type not in allowed or not isinstance(value, dict):
            continue
        label_patterns = tuple(item for item in value.get("label_patterns", []) if isinstance(item, str) and item.strip())
        visual_cues = tuple(item for item in value.get("visual_cues", []) if isinstance(item, str) and item.strip())
        confusion_notes = value.get("confusion_notes")
        if not visual_cues:
            continue
        evidence[component_type] = {
            "label_patterns": label_patterns,
            "visual_cues": visual_cues,
            "confusion_notes": confusion_notes.strip() if isinstance(confusion_notes, str) else "",
        }
    return evidence


def visual_evidence_prompt(evidence: dict[str, dict[str, tuple[str, ...] | str]] | None = None) -> str:
    """Serialize compact, bounded rules suitable for the visual detector prompt."""
    entries = evidence if evidence is not None else load_component_evidence()
    if not entries:
        return ""
    rules = []
    for component_type in supported_component_types():
        item = entries.get(component_type)
        if item is None:
            continue
        cues = "; ".join(item["visual_cues"])
        labels = ", ".join(item["label_patterns"])
        note = item["confusion_notes"]
        rule = f"- {component_type}: visual cues [{cues}]"
        if labels:
            rule += f"; adjacent-label patterns [{labels}]"
        if note:
            rule += f"; guardrail [{note}]"
        rules.append(rule)
    return (
        "Use these human-maintained component rules as corroborating evidence. "
        "A nearby readable label may increase confidence only when the symbol also matches its visual cues; "
        "never create a detection from text alone. Bounding boxes must cover the symbol, not its label.\n"
        + "\n".join(rules)
    )
