"""Deterministic native-text association for the P1 vector-first path."""

from __future__ import annotations

import math
import re

from domain.models import ComponentCandidate, NativeText


REFERENCE_PREFIXES = {
    # Common IEC/Chinese electrical-drawing designators. ATTRIB remains the
    # authoritative source; these expressions only score nearby native text.
    "circuit_breaker": ("QF", "Q"),
    "current_transformer": ("TA", "CT"),
    "voltage_transformer": ("TV", "PT"),
    "surge_arrester": ("YH", "SA"),
    "fuse": ("FU", "F"),
    "zero_sequence_current_transformer": ("TA0", "TA", "CT0"),
    "live_line_indicator": ("VP", "HL"),
    "earthing_switch": ("ES", "QES"),
    "ammeter": ("PA", "A"),
    "voltmeter": ("PV", "V"),
    "thermal_relay": ("FR", "KH"),
    "contactor": ("KM",),
    "capacitor": ("C",),
    "three_phase_shunt_capacitor_bank": ("CB", "C"),
    "transformer": ("T",),
}
VALUE_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:[kKmMuUnNpP](?:\s*(?:Ω|ohm|v|a|w|f|h))?|Ω|ohm|v|a|w|f|h)",
    re.IGNORECASE,
)


def _distance(component: ComponentCandidate, text: NativeText) -> float:
    if text.cad_position is None:
        return float("inf")
    return math.hypot(component.cad_center.x - text.cad_position.x, component.cad_center.y - text.cad_position.y)


def _reference_pattern(component_type: str) -> re.Pattern[str] | None:
    prefixes = REFERENCE_PREFIXES.get(component_type)
    if not prefixes:
        return None
    return re.compile(r"\b(?:" + "|".join(map(re.escape, prefixes)) + r")\s*\d+[A-Za-z0-9-]*\b", re.IGNORECASE)


def associate_component_texts(
    components: list[ComponentCandidate], texts: list[NativeText],
) -> tuple[list[ComponentCandidate], list[NativeText]]:
    """Associate relevant labels/values and discard unrelated drawing text.

    The VLM supplies ``component_type`` for visual text. Native DXF text has no
    type, so it must match the component's reference/value patterns. A text is
    retained only after it is claimed by one concrete component; this prevents
    title blocks and other unrelated labels from entering the public text list.
    """
    claimed_text_ids: set[str] = set()
    for component in components:
        attributes = component.evidence.attributes
        component.reference = attributes.get("TAG") or attributes.get("REF") or attributes.get("REFERENCE")
        component.value = attributes.get("VALUE") or attributes.get("VAL")
        pattern = _reference_pattern(component.type)
        nearby = sorted(
            (
                (item, _distance(component, item))
                for item in texts
                if item.id not in claimed_text_ids and (item.component_type is None or item.component_type == component.type)
            ),
            key=lambda item: item[1],
        )[:4]
        references = [(item, distance) for item, distance in nearby if pattern and pattern.search(item.content)]
        # A bare native value such as "10kV" also occurs in titles and revision
        # blocks. Retain values only when VLM has explicitly tied the text to
        # this component type; INSERT attributes remain authoritative otherwise.
        values = [
            (item, distance)
            for item, distance in nearby
            if item.component_type == component.type and VALUE_PATTERN.search(item.content)
        ]
        if references and not component.reference:
            best, best_distance = references[0]
            if len(references) == 1 or references[1][1] > best_distance * 1.25:
                component.reference = pattern.search(best.content).group(0).replace(" ", "")
                component.evidence.text_ids.append(best.id)
                best.component_id = component.id
                claimed_text_ids.add(best.id)
        if values and not component.value:
            best, best_distance = values[0]
            if len(values) == 1 or values[1][1] > best_distance * 1.25:
                component.value = VALUE_PATTERN.search(best.content).group(0)
                if best.id not in component.evidence.text_ids:
                    component.evidence.text_ids.append(best.id)
                best.component_id = component.id
                claimed_text_ids.add(best.id)
        if not component.reference and component.type in REFERENCE_PREFIXES:
            component.review_status = "pending"
            component.confidence = min(component.confidence, 0.75)
    retained = [item for item in texts if item.id in claimed_text_ids]
    return components, retained


def associate_native_text(components: list[ComponentCandidate], texts: list[NativeText]) -> list[ComponentCandidate]:
    """Compatibility wrapper for callers that only need mutated components."""
    associated, _ = associate_component_texts(components, texts)
    return associated