import unittest

from app.engine import WORKFLOW, create_output, create_sample, fingerprint, identify_kind, read_sheets


class WorkbookPipelineTests(unittest.TestCase):
    def test_each_region_processes_sales_and_inventory(self):
        for region in ("EU", "NA", "APAC"):
            with self.subTest(region=region):
                sheets = read_sheets(create_sample(region))
                self.assertEqual(len(sheets), 2)
                results = []
                for sheet in sheets:
                    kind = identify_kind(sheet["name"], sheet["headers"])
                    state = WORKFLOW.invoke(
                        {
                            "region": region,
                            "kind": kind,
                            "headers": sheet["headers"],
                            "rows": sheet["rows"],
                            "cached_mapping": None,
                            "trace": [],
                            "errors": [],
                        }
                    )
                    self.assertEqual(state["errors"], [])
                    self.assertEqual(len(state["output"]), 2)
                    self.assertEqual(len(state["trace"]), 4)
                    results.append({"kind": kind, "output": state["output"]})
                self.assertEqual(results[0]["output"][0][3], 238.8)
                self.assertEqual(len(read_sheets(create_output(results))), 2)

    def test_missing_column_fails_validation(self):
        state = WORKFLOW.invoke(
            {
                "region": "EU",
                "kind": "sales",
                "headers": ["Article", "Units"],
                "rows": [["SAMPLE-001", 3]],
                "cached_mapping": None,
                "trace": [],
                "errors": [],
            }
        )
        self.assertIn("unit_price", state["errors"][0])
        self.assertEqual(state["trace"][-1]["status"], "failed")

    def test_recipe_key_changes_with_headers(self):
        first = fingerprint("EU", "sales", ["Article", "Units", "Net Price"])
        second = fingerprint("EU", "sales", ["Article", "Stock", "Net Price"])
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
