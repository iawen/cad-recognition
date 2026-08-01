"""Regression tests for implemented P0-P2 capabilities."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ezdxf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import router
from domain.models import CadPoint
from evaluation.audit import audit_drawings
from evaluation.coordinate_validation import validate_coordinate_round_trip
from rendering.dxf_renderer import render_dxf_to_png
from rendering.tiling import create_tiles
from recognition.vlm_detector import VlmDetector
from runtime.repository import create_run, update_run
from service import analyze_drawing


class P0ToP2RegressionTests(unittest.TestCase):
    def _create_dxf(self, root: Path) -> Path:
        path = root / "electrical.dxf"
        document = ezdxf.new("R2018")
        document.blocks.new("RESISTOR")
        insert = document.modelspace().add_blockref("RESISTOR", (10, 20))
        insert.add_attrib("TAG", "R1")
        document.modelspace().add_text("R1 10k", dxfattribs={"insert": (12, 22)})
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
            self.assertEqual(result.components[0].reference, "R1")
            self.assertEqual(result.components[0].value, "10k")

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
            symbols = client.get(f"/api/recognition/{run['id']}/symbols")
            texts = client.get(f"/api/recognition/{run['id']}/texts")
            tables = client.get(f"/api/recognition/{run['id']}/tables")

        self.assertEqual(task.status_code, 200)
        self.assertEqual(task.json()["data"]["status"], "completed")
        self.assertEqual(symbols.status_code, 200)
        self.assertEqual(symbols.json()["data"][0]["category"], "resistor")
        self.assertGreaterEqual(symbols.json()["data"][0]["boundingBox"]["x"], 0)
        self.assertEqual(texts.status_code, 200)
        self.assertEqual(tables.json()["data"], [])

    def test_vlm_schema_parser_rejects_invalid_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "tile.png"
            from PIL import Image
            Image.new("RGB", (100, 80), "white").save(image_path)
            detections = VlmDetector._parse(
                '{"components":[{"type":"resistor","bbox":[10,20,50,60],"confidence":0.9,"rotation_deg":90},'
                '{"type":"invalid","bbox":[0,0,1,1],"confidence":1}]}',
                image_path,
            )
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "resistor")
        self.assertEqual(detections[0].center_x, 30)

    def test_repository_sample_is_available_to_api(self):
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).get("/api/drawing-recognition/capabilities")
        self.assertTrue(response.json()["sample_available"])


if __name__ == "__main__":
    unittest.main()
