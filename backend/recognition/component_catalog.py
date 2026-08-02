"""Authoritative electrical-component catalog from the supplied icon workbook.

The catalog was transcribed from ``data/图标资料/电气元件对应名称260731.xlsx``.
Reference DWG/WMF files remain outside the package so they can be expanded
without publishing them as application assets. Their presence is reported as
evidence, but they are not yet used as trainable visual templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


CATALOG_SOURCE = "data/图标资料/电气元件对应名称260731.xlsx"
REFERENCE_ROOT = Path(__file__).resolve().parents[2] / "data" / "图标资料"


@dataclass(frozen=True)
class ComponentDefinition:
    """One approved detection class and its terminology/reference assets."""

    type: str
    display_name: str
    category: str
    aliases: tuple[str, ...]
    reference_stem: str | None = None

    def reference_assets(self) -> dict[str, str]:
        """Return supplied matching DWG/WMF files when this catalog row has them."""
        if self.reference_stem is None:
            return {}
        matches = {
            path.suffix.casefold(): path
            for path in REFERENCE_ROOT.glob(f"{self.reference_stem}.*")
            if path.suffix.casefold() in {".dwg", ".wmf"}
        }
        return {
            suffix.lstrip("."): str(path.relative_to(REFERENCE_ROOT.parents[1]).as_posix())
            for suffix, path in matches.items()
        }


# Order matters for overlapping aliases: specific classes precede their parents.
COMPONENT_CATALOG: tuple[ComponentDefinition, ...] = (
    ComponentDefinition("zero_sequence_current_transformer", "零序电流互感器", "互感器", ("zero sequence current transformer", "zero-sequence current transformer", "零序电流互感器")),
    ComponentDefinition("three_phase_shunt_capacitor_bank", "三相并联电容器组", "电能变换", ("three phase shunt capacitor bank", "three-phase shunt capacitor bank", "三相并联电容器组")),
    ComponentDefinition("circuit_breaker", "断路器", "开关保护", ("circuit breaker", "breaker", "断路器"), "【1】断路器1"),
    ComponentDefinition("current_transformer", "电流互感器", "互感器", ("current transformer", "电流互感器"), "【2】电流互感器 (gb4728_8_3D.2-1)"),
    ComponentDefinition("voltage_transformer", "电压互感器", "互感器", ("voltage transformer", "potential transformer", "电压互感器")),
    ComponentDefinition("surge_arrester", "避雷器", "过压保护", ("surge arrester", "lightning arrester", "避雷器"), "【4】避雷器 (gb4728_9_6.12)"),
    ComponentDefinition("fuse", "熔断器", "开关保护", ("fuse", "熔断器"), "【5】熔断器一般符号 (gb4728_9_6.1)"),
    ComponentDefinition("live_line_indicator", "带电显示器", "一次附属", ("live line indicator", "voltage presence indicator", "带电显示器")),
    ComponentDefinition("earthing_switch", "接地开关", "开关保护", ("earthing switch", "grounding switch", "接地开关")),
    ComponentDefinition("ammeter", "电流表", "测量仪器", ("ammeter", "电流表")),
    ComponentDefinition("voltmeter", "电压表", "测量仪器", ("voltmeter", "voltage meter", "电压表"), "【10】电压表 (gb4728_10_2.1)"),
    ComponentDefinition("thermal_relay", "热继电器", "开关保护", ("thermal relay", "热继电器"), "【11】热继电器的驱动器件 (gb4728_9_3.13)"),
    ComponentDefinition("contactor", "接触器", "开关保护", ("contactor", "接触器")),
    ComponentDefinition("capacitor", "电容器", "电能变换", ("capacitor", "电容器"), "【13】电容器一般符号 (gb4728_5_2.1)"),
    ComponentDefinition("transformer", "变压器", "电能变换", ("transformer", "变压器"), "【15】星形、三角形连接的三相变压器"),
)

_BY_TYPE = {item.type: item for item in COMPONENT_CATALOG}


def get_component_definition(component_type: str) -> ComponentDefinition | None:
    return _BY_TYPE.get(component_type)


def resolve_component_type(value: str) -> str | None:
    """Resolve a Block/model label to an approved canonical detection type."""
    normalized = value.casefold().replace("-", "_").strip()
    if normalized in _BY_TYPE:
        return normalized
    for definition in COMPONENT_CATALOG:
        terms = (definition.display_name, *definition.aliases)
        if any(term.casefold() in normalized for term in terms):
            return definition.type
    return None


def supported_component_types() -> tuple[str, ...]:
    return tuple(item.type for item in COMPONENT_CATALOG)


def catalog_capabilities() -> list[dict[str, object]]:
    """Public, non-sensitive catalog metadata for clients and evaluation tools."""
    return [
        {
            "type": item.type,
            "name": item.display_name,
            "category": item.category,
            "reference_assets": item.reference_assets(),
        }
        for item in COMPONENT_CATALOG
    ]