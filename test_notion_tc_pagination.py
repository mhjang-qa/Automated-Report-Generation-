import unittest

import notion_html_gui_generator as legacy
from notion_html_service import GenerateRequest, generate_report


class NotionTCPaginationTests(unittest.TestCase):
    def test_query_all_pages_collects_every_result(self):
        original_request = legacy._notion_request
        calls = []
        pages = [
            {"results": [{"id": f"row-{i}"} for i in range(100)], "has_more": True, "next_cursor": "c1"},
            {"results": [{"id": f"row-{i}"} for i in range(100, 200)], "has_more": True, "next_cursor": "c2"},
            {"results": [{"id": f"row-{i}"} for i in range(200, 250)], "has_more": False, "next_cursor": None},
        ]

        def fake_request(method, path, payload=None, notion_version=legacy.NOTION_API_VERSION):
            calls.append((method, path, payload))
            return pages[len(calls) - 1]

        try:
            legacy._notion_request = fake_request
            rows = legacy._notion_paginated("POST", "/databases/db/query", {})
        finally:
            legacy._notion_request = original_request

        self.assertEqual(len(rows), 250)
        self.assertEqual(calls[0][2]["page_size"], 100)
        self.assertEqual(calls[1][2]["start_cursor"], "c1")
        self.assertEqual(calls[2][2]["start_cursor"], "c2")

    def test_query_all_pages_over_1000_results(self):
        original_request = legacy._notion_request
        total = 1850
        calls = []

        def fake_request(method, path, payload=None, notion_version=legacy.NOTION_API_VERSION):
            calls.append((method, path, payload))
            cursor = int((payload or {}).get("start_cursor") or 0)
            next_cursor = cursor + 100
            chunk = [{"id": f"row-{i}"} for i in range(cursor, min(next_cursor, total))]
            return {
                "results": chunk,
                "has_more": next_cursor < total,
                "next_cursor": str(next_cursor) if next_cursor < total else None,
            }

        try:
            legacy._notion_request = fake_request
            rows = legacy._notion_paginated("POST", "/databases/db/query", {})
        finally:
            legacy._notion_request = original_request

        self.assertEqual(len(rows), 1850)
        self.assertGreater(len(calls), 18)
        self.assertEqual(calls[-1][2]["start_cursor"], "1800")

    def test_aggregation_uses_all_notion_rows(self):
        cases = []
        for index in range(1850):
            cases.append({
                "page_name": "TC DB",
                "row": {
                    "AOS": "PASS" if index < 1000 else "FAIL",
                    "iOS": "NA" if index < 500 else "PASS",
                },
            })

        aggregated = legacy.aggregate_results_by_page(cases)
        counts = aggregated["TC DB"]

        self.assertEqual(counts["AOS"]["TOTAL"], 1850)
        self.assertEqual(counts["AOS"]["PASS"], 1000)
        self.assertEqual(counts["AOS"]["FAIL"], 850)
        self.assertEqual(counts["iOS"]["TOTAL"], 1850)
        self.assertEqual(counts["iOS"]["PASS"], 1350)
        self.assertEqual(counts["iOS"]["NA"], 500)

    def test_manual_values_are_used_only_without_notion_data(self):
        result = generate_report(GenerateRequest(
            template_type="TC",
            title="TC",
            version="1.0",
            tc_aos_pass=1,
            tc_aos_fail=2,
            tc_aos_na=3,
            tc_ios_pass=4,
            tc_ios_fail=5,
            tc_ios_na=6,
        ))

        self.assertIn("AOS: { PASS: 1, FAIL: 2, NA: 3 }", result.html)
        self.assertIn("IOS: { PASS: 4, FAIL: 5, NA: 6 }", result.html)

    def test_notion_failure_does_not_generate_sample_250_result(self):
        with self.assertRaises(ValueError):
            generate_report(GenerateRequest(
                template_type="TC",
                title="TC",
                version="1.0",
                notion_url="not-a-notion-url",
                tc_aos_pass=250,
                tc_ios_pass=250,
            ))


if __name__ == "__main__":
    unittest.main()
