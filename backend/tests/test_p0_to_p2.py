"""Regression tests for implemented P0-P2 capabilities."""

from __future__ import annotations

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
from fusion.text_association import associate_native_text
from rendering.dxf_renderer import render_dxf_to_png
from rendering.tiling import create_tiles
from recognition.vlm_detector import VlmDetector
from recognition.vlm_detector import VlmDetection
from recognition.vision_pipeline import VisualDetectionError, detect_visual_components
from recognition.component_catalog import COMPONENT_CATALOG
from recognition.reference_icons import extract_excel_reference_icons, reference_icon_summary
from runtime.repository import create_run, update_run
from runtime.worker import _run_analysis
from service import analyze_drawing


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
            image = render_dxf_to_png(drawing, root / "drawing.png", dpi=72)
            tiles = create_tiles(image, root / "tiles", tile_size=256, overlap=32)
        self.assertTrue(tiles)

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

    def test_excel_embedded_icons_are_extracted_and_mapped_to_all_classes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            icons = extract_excel_reference_icons(cache_root=Path(temp_dir))
        self.assertEqual(len(icons), 21)
        self.assertEqual({icon.component_type for icon in icons}, {item.type for item in COMPONENT_CATALOG})
        self.assertTrue(all(icon.path.suffix == ".png" for icon in icons))
        summary = reference_icon_summary()
        self.assertEqual(summary["classes_with_icons"], 15)

    def test_vlm_prompt_uses_one_excel_reference_for_each_component_class(self):
        detector = VlmDetector()
        detector.use_excel_references = True
        detector.reference_limit = 15
        content = detector._reference_content()
        self.assertEqual(len(content), 30)
        self.assertIn("circuit_breaker", str(content))
        self.assertIn("visual references", detector._prompt(True))

    def test_native_text_rules_support_canonical_component_types(self):
        component = ComponentCandidate(
            id="cmp_1", type="circuit_breaker", cad_center=CadPoint(x=10, y=10), rotation_deg=0,
            confidence=0.9, evidence=ComponentEvidence(block_name="CIRCUIT_BREAKER", layer="0"),
        )
        texts = [NativeText(id="txt_1", content="QF1", entity_type="TEXT", layer="0", cad_position=CadPoint(x=11, y=10))]
        associated = associate_native_text([component], texts)
        self.assertEqual(associated[0].reference, "QF1")

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
