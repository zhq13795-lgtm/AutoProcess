import unittest

from fastapi.testclient import TestClient

from app.engine import create_sample
from app.main import RECIPES, RUNS, app


class ApiTests(unittest.TestCase):
    def setUp(self):
        RECIPES.clear()
        RUNS.clear()
        self.client = TestClient(app)

    def test_upload_process_reuse_and_download(self):
        sample = create_sample("EU")
        files = {"file": ("input.xlsx", sample, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        inspected = self.client.post("/api/inspect", data={"region": "EU"}, files=files)
        self.assertEqual(inspected.status_code, 200)
        self.assertEqual([sheet["kind"] for sheet in inspected.json()["sheets"]], ["sales", "inventory"])

        first = self.client.post("/api/process", data={"region": "EU"}, files=files)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["sheets"][0]["reused"])
        self.assertEqual(first.json()["sheets"][0]["rows_out"], 2)

        second = self.client.post("/api/process", data={"region": "EU"}, files=files)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["sheets"][0]["reused"])
        download = self.client.get(f"/api/download/{second.json()['run_id']}")
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download.content.startswith(b"PK"))

    def test_invalid_workbook_is_rejected(self):
        response = self.client.post(
            "/api/process",
            data={"region": "NA"},
            files={"file": ("broken.xlsx", b"not a workbook")},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
