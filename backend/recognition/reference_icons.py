"""Extract and normalize the supplied workbook's embedded symbol images.

The workbook is the authoritative user-supplied visual catalogue.  It is kept as
source data; extracted PNGs are a reproducible runtime cache rather than a
second manually maintained asset library.
"""

from __future__ import annotations

import io
import posixpath
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from recognition.component_catalog import COMPONENT_CATALOG, CATALOG_SOURCE

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
WORKBOOK_PATH = WORKSPACE_ROOT / CATALOG_SOURCE
CACHE_ROOT = WORKSPACE_ROOT / "backend" / "data" / "runtime" / "reference-icons"
_DRAWING_PATH = "xl/drawings/drawing1.xml"
_RELATIONSHIP_PATH = "xl/drawings/_rels/drawing1.xml.rels"
_NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
# This order is authoritative for the supplied spreadsheet rows. It is kept
# separate from COMPONENT_CATALOG because the latter deliberately orders
# overlapping aliases from specific to general types.
_EXCEL_COMPONENT_NAMES = (
    "断路器", "电流互感器", "电压互感器", "避雷器", "熔断器", "零序电流互感器",
    "带电显示器", "接地开关", "电流表", "电压表", "热继电器", "接触器", "电容器",
    "三相并联电容器组", "变压器",
)
_CATALOG_BY_NAME = {definition.display_name: definition for definition in COMPONENT_CATALOG}


@dataclass(frozen=True)
class ReferenceIcon:
    """One embedded workbook image mapped to a canonical component class."""

    component_type: str
    display_name: str
    source_member: str
    path: Path


def _relationship_targets(archive: ZipFile) -> dict[str, str]:
    root = ET.fromstring(archive.read(_RELATIONSHIP_PATH))
    targets: dict[str, str] = {}
    for relationship in root.findall("rel:Relationship", _NS):
        identifier = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if identifier and target:
            targets[identifier] = posixpath.normpath(posixpath.join("xl/drawings", target))
    return targets


def _anchors(archive: ZipFile) -> list[tuple[int, str]]:
    root = ET.fromstring(archive.read(_DRAWING_PATH))
    anchors: list[tuple[int, str]] = []
    for anchor in root:
        row = anchor.findtext("xdr:from/xdr:row", namespaces=_NS)
        blip = anchor.find(".//a:blip", _NS)
        relationship_id = blip.attrib.get(f"{{{_NS['r']}}}embed") if blip is not None else None
        if row is not None and relationship_id:
            anchors.append((int(row) + 1, relationship_id))
    return anchors


def extract_excel_reference_icons(*, cache_root: Path = CACHE_ROOT) -> list[ReferenceIcon]:
    """Extract every catalog-row PNG from the workbook into a runtime cache.

    Images outside rows 2--16 are ignored because those rows do not represent a
    supported component class. Existing cache files are reused when present.
    """
    if not WORKBOOK_PATH.is_file():
        raise RuntimeError(f"未找到元件图标工作簿：{WORKBOOK_PATH}")

    icons: list[ReferenceIcon] = []
    counters: dict[str, int] = {}
    seen_members: set[tuple[str, str]] = set()
    with ZipFile(WORKBOOK_PATH) as archive:
        targets = _relationship_targets(archive)
        for excel_row, relationship_id in _anchors(archive):
            catalog_index = excel_row - 2
            if not 0 <= catalog_index < len(_EXCEL_COMPONENT_NAMES):
                continue
            source_member = targets.get(relationship_id)
            if source_member is None or not source_member.startswith("xl/media/"):
                continue
            definition = _CATALOG_BY_NAME[_EXCEL_COMPONENT_NAMES[catalog_index]]
            if (definition.type, source_member) in seen_members:
                continue
            seen_members.add((definition.type, source_member))
            counters[definition.type] = counters.get(definition.type, 0) + 1
            suffix = Path(source_member).suffix.casefold() or ".png"
            target = cache_root / definition.type / f"reference-{counters[definition.type]}{suffix}"
            source_bytes = archive.read(source_member)
            if not target.is_file() or target.read_bytes() != source_bytes:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source_bytes)
            icons.append(ReferenceIcon(definition.type, definition.display_name, source_member, target))
    return icons


def reference_icon_summary() -> dict[str, object]:
    """Return public non-sensitive workbook extraction coverage metadata."""
    icons = extract_excel_reference_icons()
    counts = {definition.type: 0 for definition in COMPONENT_CATALOG}
    for icon in icons:
        counts[icon.component_type] += 1
    return {
        "source": CATALOG_SOURCE,
        "embedded_icon_count": len(icons),
        "classes_with_icons": sum(count > 0 for count in counts.values()),
        "counts_by_type": counts,
    }


def vlm_reference_images(*, max_per_type: int = 1, max_edge_px: int = 256) -> list[tuple[str, bytes]]:
    """Return compact PNG references in catalog order for multimodal prompts."""
    if max_per_type <= 0:
        return []
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow，无法准备 Excel 图标参考图。") from exc

    images: list[tuple[str, bytes]] = []
    used: dict[str, int] = {}
    for icon in extract_excel_reference_icons():
        if used.get(icon.component_type, 0) >= max_per_type:
            continue
        with Image.open(icon.path) as source:
            image = source.convert("RGB")
            image.thumbnail((max_edge_px, max_edge_px))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
        images.append((icon.component_type, buffer.getvalue()))
        used[icon.component_type] = used.get(icon.component_type, 0) + 1
    return images
