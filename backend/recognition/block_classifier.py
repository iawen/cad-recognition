"""Classify DXF Block names against the approved component catalog."""

from recognition.component_catalog import resolve_component_type


def classify_block(block_name: str) -> str | None:
    return resolve_component_type(block_name)