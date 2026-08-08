"""Regression tests for implemented P0-P2 capabilities."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import ezdxf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import router
from domain.models import CadPoint, ComponentCandidate, ComponentEvidence, NativeText
from evaluation.audit import audit_drawings
from evaluation.coordinate_validation import validate_coordinate_round_trip
from fusion.text_association import associate_component_texts, associate_native_text
from rendering.dxf_renderer import render_dxf_region_to_png, render_dxf_regions_to_png
from rendering.regions import DrawingRegion, detect_drawing_regions, detect_frame_layout_regions
from rendering.tiling import create_cad_tiles
from recognition.vlm_detector import VlmDetector
from recognition.vlm_detector import VlmDetection
from recognition.component_evidence import load_component_evidence, visual_evidence_prompt
from recognition.template_detector import load_component_templates, template_matching_enabled
from recognition.vector_template_matcher import Segment, match_template, segments_from_dxf
from recognition.vision_pipeline import VisualDetectionError, detect_visual_components
from recognition.component_catalog import COMPONENT_CATALOG
from recognition.reference_icons import extract_excel_reference_icons, reference_icon_summary
from runtime.repository import create_run, get_run, list_events, update_run
from runtime.worker import _run_analysis
from service import analyze_drawing, render_dxf_base_maps
from ingest.dwg_converter import convert_dwg_to_dxf
from tools.vlm_capacitor_probe import _prepare_crop
from tools.split_dxf_frames import split_dxf_frames
from tools.split_dxf_layout_regions import split_dxf_layout_regions
from tools.match_dxf_component_templates import match_component_templates


class P0ToP2RegressionTests(unittest.TestCase):
    def setUp(self):
        # Unit tests must not call a locally configured external VLM endpoint.
        visual_detector = patch("service.detect_visual_components", return_value=[])
        visual_detector.start()
        self.addCleanup(visual_detector.stop)

    def _create_dxf(self, root: Path) -> Path:
        path = root / "electrical.dxf"
        document = ezdxf.new("R2018")
        document.blocks.new("CIRCUIT_BREAKER")
        insert = document.modelspace().add_blockref("CIRCUIT_BREAKER", (10, 20))
        insert.add_attrib("TAG", "QF1")
        document.modelspace().add_text("QF1", dxfattribs={"insert": (12, 22)})
        document.saveas(path)
        return path

    def test_p0_audit_and_coordinate_round_trip(self):
        coordinate_report = validate_coordinate_round_trip(
            CadPoint(x=0, y=0), CadPoint(x=100, y=50), 2000, 1000,
            [CadPoint(x=0, y=0), CadPoint(x=100, y=50), CadPoint(x=50, y=25), CadPoint(x=20, y=40)],
        )
        self.assertTrue(coordinate_report["passed"])
        with tempfile.TemporaryDirectory() as temp_dir:
            report = audit_drawings([self._create_dxf(Path(temp_dir))])
        self.assertEqual(report.successful_count, 1)
        self.assertEqual(report.block_component_count, 1)

    def test_p1_vector_recognition_and_api_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            drawing = self._create_dxf(Path(temp_dir))
            result = analyze_drawing(drawing)
            self.assertEqual(result.components[0].type, "circuit_breaker")
            self.assertEqual(result.components[0].reference, "QF1")
            self.assertEqual(result.components[0].evidence.catalog_name, "断路器")

            app = FastAPI()
            app.include_router(router)
            response = TestClient(app).post(
                "/api/drawing-recognition/analyze",
                files={"file": (drawing.name, drawing.read_bytes(), "application/dxf")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["component_count"], 1)

    def test_p2_render_and_tile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drawing = self._create_dxf(root)
            frame = DrawingRegion("frame", 0, 0, 100, 50)
            tiles = create_cad_tiles(frame, tile_size=256, overlap=32, reference_long_edge_px=512)
            rendered = render_dxf_regions_to_png(
                drawing,
                [(root / "tiles" / tile.name, tile.region) for tile in tiles],
                dpi=72,
                max_size_inches=256 / 72,
            )
            self.assertTrue(tiles)
            self.assertEqual(len(rendered), len(tiles))
            self.assertTrue(all(path.is_file() for path in rendered))

    def test_repository_persists_structured_current_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            drawing = self._create_dxf(Path(temp_dir))
            run = create_run(drawing.name, drawing)
            work = {
                "kind": "vlm_component_tile", "frame_index": 0, "frame_total": 2,
                "tile_index": 2, "tile_total": 8, "tile_name": "tile_003.png",
            }
            update_run(
                run["id"], status="running", phase="vlm_components", progress=54,
                message="正在识别主图框 1/2 的元器件区域 3/8。", work=work,
            )
            persisted = get_run(run["id"])
            events = list_events(run["id"])

        self.assertEqual(persisted["work"], work)
        self.assertEqual(events[-1]["work"], work)
        self.assertGreater(events[-1]["id"], 0)

    def test_task_stream_emits_frontend_snapshot_and_work_event(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_source = Path(temp_dir) / "missing.dxf"
            run = create_run("missing.dxf", missing_source)
            work = {"kind": "vlm_text_tile", "frame_index": 0, "frame_total": 1, "tile_index": 1, "tile_total": 4}
            update_run(
                run["id"], status="succeeded", phase="done", progress=100,
                message="图纸识别完成。", work=work,
            )
            app = FastAPI()
            app.include_router(router)
            response = TestClient(app).get(f"/api/drawing-recognition/runs/{run['id']}/stream")

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: progress", response.text)
        self.assertIn('"currentWork": {"kind": "vlm_text_tile"', response.text)

    def test_vector_template_matcher_finds_scaled_rotated_symbol(self):
        template = [
            Segment(0, 0, 0, 10),
            Segment(-5, 10, 0, 20),
            Segment(0, 20, 0, 30),
            Segment(-1, 19, 1, 21),
        ]
        # Template rotated 90 degrees, scaled by 0.1, and translated to (100, 50).
        target = [
            Segment(100, 50, 99, 50),
            Segment(99, 49.5, 98, 50),
            Segment(98, 50, 97, 50),
            Segment(98.1, 49.9, 97.9, 50.1),
            Segment(20, 20, 21, 20),
        ]

        matches = match_template(template, target, endpoint_tolerance=0.01)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_segments, 4)
        self.assertEqual(matches[0].template_segments, 4)
        self.assertAlmostEqual(matches[0].scale, 0.1)
        self.assertAlmostEqual(matches[0].rotation_deg, 90.0)

    def test_template_matching_can_be_disabled_by_environment(self):
        with patch.dict("os.environ", {"DRAWING_TEMPLATE_MATCHING_ENABLED": "false"}):
            self.assertFalse(template_matching_enabled())
            self.assertEqual(load_component_templates(), [])

    def test_per_frame_template_match_precedes_vlm_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_path = root / "breaker.dxf"
            template_document = ezdxf.new("R2018")
            template_layout = template_document.modelspace()
            template_layout.add_line((0, 0), (0, 10))
            template_layout.add_line((-5, 10), (0, 20))
            template_layout.add_line((0, 20), (0, 30))
            template_document.saveas(template_path)
            manifest_path = root / "templates.json"
            manifest_path.write_text(json.dumps({"templates": [{
                "component_type": "circuit_breaker", "path": "breaker.dxf", "min_confidence": 0.9,
            }]}), encoding="utf-8")

            drawing = root / "frames.dxf"
            document = ezdxf.new("R2018")
            layout = document.modelspace()
            for x_offset in (0, 100):
                layout.add_lwpolyline(
                    [(x_offset, 0), (x_offset + 80, 0), (x_offset + 80, 40), (x_offset, 40)], close=True,
                )
            layout.add_line((10, 5), (10, 15))
            layout.add_line((5, 15), (10, 25))
            layout.add_line((10, 25), (10, 35))
            document.saveas(drawing)

            component_detector = Mock(return_value=([], {"enabled": True}))
            progress_events: list[tuple[str, dict]] = []
            with (
                patch.dict("os.environ", {"DRAWING_TEMPLATE_MANIFEST": str(manifest_path)}),
                patch("service.detect_visual_components", component_detector),
            ):
                result = analyze_drawing(
                    drawing,
                    progress_callback=lambda phase, _progress, _message, work: progress_events.append((phase, work)),
                )

        self.assertEqual(result.summary["template_component_count"], 1)
        self.assertEqual(component_detector.call_count, 1)
        self.assertEqual(component_detector.call_args.kwargs["frame_contexts"][0][0], 1)
        self.assertTrue(any(phase == "template_match" for phase, _work in progress_events))

    def test_component_template_script_reports_multiple_cad_locations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_path = root / "circuit_breaker.dxf"
            template_document = ezdxf.new("R2018")
            template_layout = template_document.modelspace()
            template_layout.add_line((0, 0), (0, 10))
            template_layout.add_line((-5, 10), (0, 20))
            template_layout.add_line((0, 20), (0, 30))
            template_layout.add_line((-1, 19), (1, 21))
            template_document.saveas(template_path)

            main_path = root / "main.dxf"
            main_document = ezdxf.new("R2018")
            main_layout = main_document.modelspace()
            # Two copies of the template, each rotated 90 degrees and scaled by 0.1.
            for x_offset, y_offset in ((100, 50), (200, 80)):
                main_layout.add_line((x_offset, y_offset), (x_offset - 1, y_offset))
                main_layout.add_line((x_offset - 1, y_offset - 0.5), (x_offset - 2, y_offset))
                main_layout.add_line((x_offset - 2, y_offset), (x_offset - 3, y_offset))
                main_layout.add_line((x_offset - 1.9, y_offset - 0.1), (x_offset - 2.1, y_offset + 0.1))
            main_document.saveas(main_path)

            report = match_component_templates(
                main_path, [template_path], endpoint_tolerance=0.01, min_confidence=0.9,
            )

        self.assertEqual(report["total_accepted_match_count"], 2)
        self.assertEqual(report["templates"][0]["component_name"], "circuit_breaker")
        self.assertTrue(all(match["confidence"] >= 0.9 for match in report["templates"][0]["matches"]))

    def test_component_template_script_expands_insert_and_auto_scales(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_path = root / "symbol.dxf"
            template_document = ezdxf.new("R2018")
            template_document.modelspace().add_line((0, 0), (0, 10))
            template_document.modelspace().add_line((-5, 10), (0, 20))
            template_document.modelspace().add_line((0, 20), (0, 30))
            template_document.saveas(template_path)

            main_path = root / "main-insert.dxf"
            main_document = ezdxf.new("R2018")
            block = main_document.blocks.new("SYMBOL")
            block.add_line((0, 0), (0, 10))
            block.add_line((-5, 10), (0, 20))
            block.add_line((0, 20), (0, 30))
            main_document.modelspace().add_blockref("SYMBOL", (100, 50), dxfattribs={"xscale": 0.1, "yscale": 0.1, "rotation": 90})
            main_document.saveas(main_path)

            report = match_component_templates(main_path, [template_path], endpoint_tolerance=0.01, min_confidence=0.9)

        self.assertEqual(report["settings"]["scale_mode"], "automatic")
        self.assertGreater(report["target_segment_count"], 0)
        self.assertEqual(report["total_accepted_match_count"], 1)
        self.assertGreater(report["templates"][0]["matches"][0]["scale"], 0.01)

    def test_vector_template_matcher_matches_scaled_circles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_path = root / "circle-template.dxf"
            template_document = ezdxf.new("R2018")
            template_document.modelspace().add_circle((0, 0), 10)
            template_document.saveas(template_path)

            target_path = root / "circle-target.dxf"
            target_document = ezdxf.new("R2018")
            target_document.modelspace().add_circle((100, 50), 1)
            target_document.saveas(target_path)

            matches = match_template(segments_from_dxf(template_path), segments_from_dxf(target_path), min_scale=None, max_scale=None, endpoint_tolerance=0.01)

        self.assertEqual(len(matches), 1)
        self.assertAlmostEqual(matches[0].scale, 0.1)

    def test_vector_template_matcher_matches_scaled_arcs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_path = root / "arc-template.dxf"
            template_document = ezdxf.new("R2018")
            template_document.modelspace().add_arc((0, 0), 10, 0, 90)
            template_document.saveas(template_path)

            target_path = root / "arc-target.dxf"
            target_document = ezdxf.new("R2018")
            target_document.modelspace().add_arc((100, 50), 1, 0, 90)
            target_document.saveas(target_path)

            matches = match_template(segments_from_dxf(template_path), segments_from_dxf(target_path), min_scale=None, max_scale=None, endpoint_tolerance=0.01)

        self.assertEqual(len(matches), 1)
        self.assertAlmostEqual(matches[0].scale, 0.1)

    def test_realdwg_environment_switch_selects_sidecar(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            drawing = Path(temp_dir) / "drawing.dwg"
            drawing.write_bytes(b"placeholder")
            expected_dxf = Path(temp_dir) / "drawing.dxf"
            sidecar_temp = Mock()
            with (
                patch.dict("os.environ", {"DRAWING_USE_REALDWG": "true"}),
                patch("ingest.dwg_converter.convert_dwg_with_realdwg", return_value=(expected_dxf, sidecar_temp)) as sidecar,
            ):
                actual_dxf, actual_temp = convert_dwg_to_dxf(drawing)

        sidecar.assert_called_once_with(drawing)
        self.assertEqual(actual_dxf, expected_dxf)
        self.assertIs(actual_temp, sidecar_temp)

    def test_detects_large_rectangular_drawing_regions(self):
        document = ezdxf.new("R2018")
        layout = document.modelspace()
        for origin_x, origin_y in ((0, 60), (100, 60), (0, 0), (100, 0)):
            layout.add_lwpolyline(
                [(origin_x, origin_y), (origin_x + 80, origin_y), (origin_x + 80, origin_y + 40), (origin_x, origin_y + 40)],
                close=True,
            )

        regions = detect_drawing_regions(layout)

        self.assertEqual(len(regions), 4)
        self.assertEqual(regions[0].name, "region_01")
        self.assertEqual((regions[0].min_x, regions[0].min_y), (0.0, 60.0))
        self.assertEqual((regions[-1].min_x, regions[-1].min_y), (100.0, 0.0))

    def test_detects_title_layer_frames_in_large_modelspace(self):
        document = ezdxf.new("R2018")
        layout = document.modelspace()
        # Two 105 x 59 sheets within a 793 x 435 site-wide modelspace. The
        # normal global 18% threshold rejects them; TEL_TITLE should retain
        # their outer rectangles and suppress the nested inner borders.
        for origin_x in (0, 150):
            layout.add_lwpolyline(
                [(origin_x, 300), (origin_x + 105, 300), (origin_x + 105, 359), (origin_x, 359)],
                close=True, dxfattribs={"layer": "TEL_TITLE"},
            )
            layout.add_lwpolyline(
                [(origin_x + 2, 301), (origin_x + 103, 301), (origin_x + 103, 358), (origin_x + 2, 358)],
                close=True, dxfattribs={"layer": "TEL_TITLE"},
            )
        layout.add_line((0, 0), (793, 435))

        regions = detect_drawing_regions(layout)

        self.assertEqual(len(regions), 2)
        self.assertEqual((regions[0].min_x, regions[0].max_x), (0.0, 105.0))
        self.assertEqual((regions[1].min_x, regions[1].max_x), (150.0, 255.0))

    def test_split_dxf_frames_writes_one_png_and_manifest_per_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drawing = root / "frames.dxf"
            document = ezdxf.new("R2018")
            layout = document.modelspace()
            for origin_x in (0, 100):
                layout.add_lwpolyline(
                    [(origin_x, 0), (origin_x + 80, 0), (origin_x + 80, 40), (origin_x, 40)], close=True,
                )
            document.saveas(drawing)

            manifest = split_dxf_frames(drawing, root / "output", dpi=72)

            self.assertEqual(manifest["frame_count"], 2)
            self.assertFalse(manifest["used_modelspace_fallback"])
            self.assertTrue((root / "output" / "region_01.png").is_file())
            self.assertTrue((root / "output" / "region_02.png").is_file())
            self.assertTrue((root / "output" / "frames.json").is_file())

    def test_splits_main_frame_into_table_and_electrical_regions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drawing = root / "layout.dxf"
            document = ezdxf.new("R2018")
            layout = document.modelspace()
            layout.add_lwpolyline([(0, 0), (200, 0), (200, 100), (0, 100)], close=True)
            # A 3 x 3 table grid on the right. The left side must remain an
            # electrical work region after the table is removed.
            for x in (140, 160, 180, 200):
                layout.add_line((x, 10), (x, 70))
            for y in (10, 30, 50, 70):
                layout.add_line((140, y), (200, y))
            document.saveas(drawing)

            frame = detect_drawing_regions(layout)[0]
            subregions = detect_frame_layout_regions(layout, frame)
            manifest = split_dxf_layout_regions(drawing, root / "output", dpi=72, max_size_inches=2)

        tables = [item for item in subregions if item.kind == "table"]
        electrical = [item for item in subregions if item.kind == "electrical"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(electrical), 1)
        self.assertEqual((tables[0].region.min_x, tables[0].region.max_x), (140.0, 200.0))
        self.assertTrue(any(item.region.min_x == 0.0 and item.region.max_x == 140.0 for item in electrical))
        self.assertEqual(manifest["frame_count"], 1)
        self.assertTrue(any(item["kind"] == "table" for item in manifest["frames"][0]["subregions"]))

    def test_main_flow_extracts_quantities_from_confirmed_table_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drawing = root / "schedule.dxf"
            document = ezdxf.new("R2018")
            layout = document.modelspace()
            layout.add_lwpolyline([(0, 0), (200, 0), (200, 100), (0, 100)], close=True)
            for x in (120, 140, 160, 180):
                layout.add_line((x, 10), (x, 50))
            for y in (10, 20, 30, 40, 50):
                layout.add_line((120, y), (180, y))
            layout.add_text("电流表", dxfattribs={"insert": (125, 35)})
            layout.add_text("3", dxfattribs={"insert": (145, 35)})
            document.saveas(drawing)
            extraction = Mock(return_value={
                "component_count": 1,
                "components": [{"name": "电流表", "quantity": 3}],
                "notes": "mock table result", "raw_response": "{}",
            })
            with (
                patch("service.extract_component_quantities_from_native_texts", extraction),
            ):
                result = analyze_drawing(drawing)

        self.assertEqual(extraction.call_count, 1)
        self.assertIn("电流表", extraction.call_args.args[0])
        self.assertEqual(len(result.drawing["tables"]), 1)
        self.assertEqual(result.drawing["tables"][0]["components"][0]["quantity"], 3)

    def test_main_flow_falls_back_to_vlm_table_image_without_native_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drawing = root / "schedule-image.dxf"
            document = ezdxf.new("R2018")
            layout = document.modelspace()
            layout.add_lwpolyline([(0, 0), (200, 0), (200, 100), (0, 100)], close=True)
            for x in (120, 140, 160, 180):
                layout.add_line((x, 10), (x, 50))
            for y in (10, 20, 30, 40, 50):
                layout.add_line((120, y), (180, y))
            document.saveas(drawing)
            extraction = Mock(return_value={
                "component_count": 1,
                "components": [{"name": "电流表", "quantity": 3}],
                "notes": "mock image table result", "raw_response": "{}",
            })
            with patch("service.extract_component_quantities", extraction):
                result = analyze_drawing(drawing, render_output_dir=root / "renders")
            self.assertTrue(extraction.call_args.args[0].is_file())

        self.assertEqual(extraction.call_count, 1)
        self.assertEqual(result.drawing["tables"][0]["source"], "table_region_vlm_image")
        self.assertEqual(result.drawing["tables"][0]["components"][0]["quantity"], 3)

    def test_prefers_dense_lower_schedule_over_enclosing_schematic_rectangle(self):
        document = ezdxf.new("R2018")
        layout = document.modelspace()
        layout.add_lwpolyline([(0, 0), (200, 0), (200, 120), (0, 120)], close=True)
        # The schematic shares the schedule's left and right columns above it.
        for x in (20, 60, 100, 140, 180):
            layout.add_line((x, 10), (x, 110))
        layout.add_line((20, 110), (180, 110))
        layout.add_line((20, 50), (180, 50))
        # The actual component quantity schedule has many repeated rows below.
        for y in (10, 18, 26, 34, 42, 50):
            layout.add_line((20, y), (180, y))

        frame = detect_drawing_regions(layout)[0]
        tables = [item for item in detect_frame_layout_regions(layout, frame) if item.kind == "table"]

        self.assertEqual(len(tables), 1)
        self.assertEqual((tables[0].region.min_y, tables[0].region.max_y), (10.0, 50.0))

    def test_detects_frame_assembled_from_polyline_segments(self):
        document = ezdxf.new("R2018")
        layout = document.modelspace()
        for first, second in (
            ((0, 0), (50, 0)), ((50, 0), (100, 0)),
            ((100, 0), (100, 25)), ((100, 25), (100, 50)),
            ((100, 50), (50, 50)), ((50, 50), (0, 50)),
            ((0, 50), (0, 25)), ((0, 25), (0, 0)),
        ):
            layout.add_lwpolyline([first, second])

        regions = detect_drawing_regions(layout)

        self.assertEqual(len(regions), 1)
        self.assertEqual((regions[0].min_x, regions[0].min_y), (0.0, 0.0))
        self.assertEqual((regions[0].max_x, regions[0].max_y), (100.0, 50.0))

    def test_renders_detected_region_at_high_dpi(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drawing = self._create_dxf(root)
            region = DrawingRegion("region_01", 0, 10, 20, 30)
            image = render_dxf_region_to_png(drawing, root / "region.png", region, dpi=72, max_size_inches=2)
            self.assertTrue(image.exists())
            self.assertGreater(image.stat().st_size, 0)

    def test_persists_one_base_map_for_each_detected_frame(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drawing = self._create_dxf(root)
            base_images = render_dxf_base_maps(drawing, root / "base-maps", dpi=72)

            image_path = root / "base-maps" / base_images[0]["filename"]
            self.assertTrue(image_path.is_file())
            self.assertGreater(image_path.stat().st_size, 0)
        self.assertEqual(len(base_images), 1)
        self.assertEqual(base_images[0]["filename"], "modelspace.png")
        self.assertGreater(base_images[0]["image_width"], 0)
        self.assertGreater(base_images[0]["image_height"], 0)

    def test_frontend_result_endpoints(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            drawing = self._create_dxf(Path(temp_dir))
            run = create_run(drawing.name, drawing)
            update_run(
                run["id"], status="succeeded", phase="done", progress=100,
                message="图纸识别完成。", result=analyze_drawing(drawing).model_dump(),
            )
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)
            task = client.get(f"/api/recognition/{run['id']}")
            drawing = client.get(f"/api/recognition/{run['id']}/drawing")
            symbols = client.get(f"/api/recognition/{run['id']}/symbols")
            texts = client.get(f"/api/recognition/{run['id']}/texts")
            tables = client.get(f"/api/recognition/{run['id']}/tables")

        self.assertEqual(task.status_code, 200)
        self.assertEqual(task.json()["data"]["status"], "completed")
        self.assertEqual(task.json()["data"]["imageUrl"], f"/api/recognition/{run['id']}/drawing")
        self.assertGreater(task.json()["data"]["imageWidth"], 0)
        self.assertGreater(task.json()["data"]["imageHeight"], 0)
        self.assertEqual(drawing.status_code, 200)
        self.assertEqual(drawing.headers["content-type"], "image/png")
        self.assertEqual(symbols.status_code, 200)
        self.assertEqual(symbols.json()["data"][0]["name"], "QF1")
        self.assertEqual(symbols.json()["data"][0]["category"], "开关保护")
        self.assertGreaterEqual(symbols.json()["data"][0]["boundingBox"]["x"], 0)
        self.assertEqual(texts.status_code, 200)
        self.assertEqual(tables.json()["data"], [])

    def test_vlm_schema_parser_rejects_invalid_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "tile.png"
            from PIL import Image
            Image.new("RGB", (100, 80), "white").save(image_path)
            detections = VlmDetector._parse(
                '{"components":[{"type":"circuit_breaker","bbox":[10,20,50,60],"confidence":0.9,"rotation_deg":90},'
                '{"type":"invalid","bbox":[0,0,1,1],"confidence":1}]}',
                image_path,
            )
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "circuit_breaker")
        self.assertEqual(detections[0].center_x, 30)

    def test_vlm_text_schema_parser_rejects_invalid_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "frame.png"
            from PIL import Image
            Image.new("RGB", (100, 80), "white").save(image_path)
            texts = VlmDetector._parse_texts(
                '{"texts":[{"content":"QF1","component_type":"circuit_breaker","bbox":[10,20,50,40],"confidence":0.9},'
                '{"content":"","bbox":[0,0,1,1],"confidence":1}]}',
                image_path,
            )
        self.assertEqual(len(texts), 1)
        self.assertEqual(texts[0].content, "QF1")
        self.assertEqual(texts[0].center_x, 30)
        self.assertEqual(texts[0].component_type, "circuit_breaker")

    def test_vlm_probe_prepares_contrast_enhanced_upscaled_crop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            target = root / "crop.png"
            from PIL import Image
            Image.new("RGB", (100, 80), "#202830").save(source)

            _prepare_crop(source, target, (10, 20, 60, 50), scale=4)

            with Image.open(target) as crop:
                self.assertEqual(crop.size, (200, 120))

    def test_repository_sample_is_available_to_api(self):
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).get("/api/drawing-recognition/capabilities")
        self.assertTrue(response.json()["sample_available"])

    def test_component_catalog_matches_supplied_component_list(self):
        self.assertEqual(len(COMPONENT_CATALOG), 15)
        self.assertEqual(
            {item.display_name for item in COMPONENT_CATALOG},
            {"断路器", "电流互感器", "电压互感器", "避雷器", "熔断器", "零序电流互感器", "带电显示器", "接地开关", "电流表", "电压表", "热继电器", "接触器", "电容器", "三相并联电容器组", "变压器"},
        )

    def test_component_evidence_library_is_loaded_into_vlm_prompt(self):
        evidence = load_component_evidence()
        self.assertIn("circuit_breaker", evidence)
        self.assertIn("QF\\d+", evidence["circuit_breaker"]["label_patterns"])
        self.assertIn("text alone", visual_evidence_prompt(evidence))

        detector = VlmDetector()
        detector.component_evidence = evidence
        prompt = detector._prompt()
        self.assertIn("circuit_breaker", prompt)
        self.assertIn("QF\\d+", prompt)
        self.assertIn("Bounding boxes must cover the symbol, not its label", prompt)

    def test_excel_embedded_icons_are_extracted_and_mapped_to_all_classes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            icons = extract_excel_reference_icons(cache_root=Path(temp_dir))
        self.assertEqual(len(icons), 21)
        self.assertEqual({icon.component_type for icon in icons}, {item.type for item in COMPONENT_CATALOG})
        self.assertTrue(all(icon.path.suffix == ".png" for icon in icons))
        summary = reference_icon_summary()
        self.assertEqual(summary["classes_with_icons"], 15)

    def test_vlm_prompt_uses_feature_descriptions_without_reference_images(self):
        detector = VlmDetector()
        prompt = detector._prompt()
        self.assertIn("circuit_breaker", prompt)
        self.assertIn("Bounding boxes must cover the symbol, not its label", prompt)
        self.assertNotIn("visual references", prompt)

    def test_native_text_rules_support_canonical_component_types(self):
        component = ComponentCandidate(
            id="cmp_1", type="circuit_breaker", cad_center=CadPoint(x=10, y=10), rotation_deg=0,
            confidence=0.9, evidence=ComponentEvidence(block_name="CIRCUIT_BREAKER", layer="0"),
        )
        texts = [NativeText(id="txt_1", content="QF1", entity_type="TEXT", layer="0", cad_position=CadPoint(x=11, y=10))]
        associated = associate_native_text([component], texts)
        self.assertEqual(associated[0].reference, "QF1")

    def test_component_text_association_discards_unrelated_text(self):
        component = ComponentCandidate(
            id="cmp_1", type="circuit_breaker", cad_center=CadPoint(x=10, y=10), rotation_deg=0,
            confidence=0.9, evidence=ComponentEvidence(block_name="", layer="0"),
        )
        texts = [
            NativeText(id="qf", content="QF1", entity_type="VLM_TEXT", layer="VLM", source="vlm", component_type="circuit_breaker", cad_position=CadPoint(x=11, y=10)),
            NativeText(id="title", content="10kV 配电一次图", entity_type="VLM_TEXT", layer="VLM", source="vlm", component_type=None, cad_position=CadPoint(x=12, y=10)),
        ]

        components, retained = associate_component_texts([component], texts)

        self.assertEqual(components[0].reference, "QF1")
        self.assertEqual(components[0].evidence.text_ids, ["qf"])
        self.assertEqual(retained, [texts[0]])
        self.assertEqual(retained[0].component_id, "cmp_1")

    def test_visual_pipeline_falls_back_to_obb_after_vlm_failure(self):
        class ConfiguredObb:
            enabled = True
            model_identifier = "test-obb"

            @staticmethod
            def detect(_image_path: Path):
                return [VlmDetection("circuit_breaker", 0.8, 10, 10, 8, 8, 0)]

        detector = VlmDetector()
        detector.enabled = True
        detector.detect = Mock(side_effect=RuntimeError("vision endpoint rejected image"))
        with tempfile.TemporaryDirectory() as temp_dir:
            drawing = self._create_dxf(Path(temp_dir))
            with patch("recognition.vision_pipeline.ObbDetector", return_value=ConfiguredObb()):
                components, audit = detect_visual_components(drawing, detector=detector, include_audit=True)

        self.assertGreaterEqual(len(components), 1)
        self.assertEqual(components[0].type, "circuit_breaker")
        self.assertEqual(len(audit["fallbacks"]), 1)

    def test_worker_marks_serialized_result_as_succeeded(self):
        analysis = Mock()
        analysis.model_dump.return_value = {
            "summary": {"component_count": 1, "text_count": 2},
        }
        with (
            patch("runtime.worker.analyze_drawing", return_value=analysis),
            patch("runtime.worker.update_run") as update_run_mock,
        ):
            _run_analysis("run-123", Path("drawing.dxf"))

        self.assertEqual(update_run_mock.call_args_list[-1].kwargs["status"], "succeeded")
        self.assertEqual(update_run_mock.call_args_list[-1].kwargs["result"], analysis.model_dump.return_value)

    def test_visual_model_failure_keeps_vector_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            drawing = self._create_dxf(Path(temp_dir))
            with patch("service.detect_visual_components", side_effect=RuntimeError("VLM 请求失败，HTTP 状态码：400。")):
                result = analyze_drawing(drawing)

        self.assertEqual(result.summary["component_count"], 1)
        self.assertIn("视觉识别未执行", result.audit["limitations"][0])

    def test_visual_failure_persists_safe_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            drawing = self._create_dxf(Path(temp_dir))
            failure = VisualDetectionError("VLM 请求超时。", {"failed_tile": "tile_0_0.png", "tile_requests": [{"outcome": "timeout"}]})
            with patch("service.detect_visual_components", side_effect=failure):
                result = analyze_drawing(drawing)

        self.assertEqual(result.audit["visual_detection"]["failed_tile"], "tile_0_0.png")
        self.assertEqual(result.audit["visual_detection"]["tile_requests"][0]["outcome"], "timeout")


if __name__ == "__main__":
    unittest.main()
