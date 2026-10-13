import unittest

import notion_html_gui_generator as legacy
from notion_html_service import GenerateRequest, generate_report


class NotionTCPaginationTests(unittest.TestCase):
    def test_app_renewal_target_versions_replace_legacy_versions(self):
        defects = [
            {"row": {"목표버전": "5.23.0"}, "columns": {"version": "목표버전"}},
            {"row": {"목표버전": "[Hanpass][앱개편][BO]"}, "columns": {"version": "목표버전"}},
            {"row": {"목표버전": "[Hanpass][앱개편][기획]"}, "columns": {"version": "목표버전"}},
            {"row": {"목표버전": "[Hanpass][앱개편][Native]"}, "columns": {"version": "목표버전"}},
        ]

        versions = legacy.extract_target_versions(defects)

        self.assertEqual(versions, [
            "[Hanpass][앱개편][Native]",
            "[Hanpass][앱개편][BO]",
            "[Hanpass][앱개편][기획]",
        ])

    def test_app_renewal_planning_fea_lines_are_count_only(self):
        defects = [
            {"row": {"ATM": "가입", "목표버전": "[Hanpass][앱개편][기획]"}, "columns": {"version": "목표버전"}},
            {"row": {"ATM": "송금", "목표버전": "[Hanpass][앱개편][기획]"}, "columns": {"version": "목표버전"}},
        ]

        lines = legacy.defects_to_fea_lines(defects, "[Hanpass][앱개편][기획]")

        self.assertEqual(lines.splitlines(), ["앱개편 기획", "앱개편 기획"])

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

    def test_expected_result_is_not_treated_as_execution_result(self):
        detected = legacy.detect_os_result_columns({
            "TC-ID": "TC-001",
            "Expected Result": "정상 처리",
            "Test Item": "버튼 클릭",
        })

        self.assertEqual(detected["mode"], "unknown")

    def test_development_status_done_is_not_countable_tc_result(self):
        self.assertFalse(legacy._row_has_countable_result({
            "TC Cnt": "2979",
            "개발상태": "완료",
            "Feature": "K-Trip",
        }))

    def test_bo_target_column_blank_counts_as_na(self):
        aggregated = legacy.aggregate_results_by_page([
            {"page_name": "HC", "row": {"TC-ID": "TC-001", "BO": ""}},
            {"page_name": "HC", "row": {"TC-ID": "TC-002", "BO": "PASS"}},
        ])

        self.assertEqual(aggregated["HC"]["BO"]["TOTAL"], 2)
        self.assertEqual(aggregated["HC"]["BO"]["NA"], 1)
        self.assertEqual(aggregated["HC"]["BO"]["PASS"], 1)

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

    def test_nested_child_pages_collect_tc_database_results(self):
        original_list_block_children = legacy._list_block_children
        original_query_database = legacy._query_database
        original_notion_request = legacy._notion_request

        blocks = {
            "root": [
                {
                    "id": "child-page-1",
                    "type": "child_page",
                    "has_children": True,
                    "child_page": {"title": "1차 메뉴"},
                }
            ],
            "child-page-1": [
                {
                    "id": "child-page-2",
                    "type": "child_page",
                    "has_children": True,
                    "child_page": {"title": "2차 메뉴"},
                }
            ],
            "child-page-2": [
                {
                    "id": "tc-db",
                    "type": "child_database",
                    "has_children": False,
                    "child_database": {"title": "TC"},
                }
            ],
        }
        pages = {
            "child-page-1": {"properties": {"Name": {"type": "title", "title": [{"plain_text": "1차 메뉴"}]}}},
            "child-page-2": {"properties": {"Name": {"type": "title", "title": [{"plain_text": "2차 메뉴"}]}}},
        }
        tc_pages = [
            {
                "id": "tc-1",
                "object": "page",
                "properties": {
                    "Name": {"type": "title", "title": [{"plain_text": "TC-1"}]},
                    "AOS": {"type": "select", "select": {"name": "PASS"}},
                    "iOS": {"type": "select", "select": {"name": "FAIL"}},
                },
            },
            {
                "id": "tc-2",
                "object": "page",
                "properties": {
                    "Name": {"type": "title", "title": [{"plain_text": "TC-2"}]},
                    "AOS": {"type": "select", "select": {"name": "NA"}},
                    "iOS": {"type": "select", "select": {"name": "PASS"}},
                },
            },
        ]

        def fake_list_block_children(block_id):
            return blocks.get(block_id, [])

        def fake_query_database(database_id):
            self.assertEqual(database_id, "tc-db")
            return tc_pages

        def fake_notion_request(method, path, payload=None, notion_version=legacy.NOTION_API_VERSION):
            page_id = path.rsplit("/", 1)[-1]
            return pages[page_id]

        try:
            legacy._list_block_children = fake_list_block_children
            legacy._query_database = fake_query_database
            legacy._notion_request = fake_notion_request

            records = legacy.fetch_test_case_records_from_page(
                "root",
                page_name="Root",
                include_page_properties=False,
            )
            aggregated = legacy.aggregate_results_by_page(records)
        finally:
            legacy._list_block_children = original_list_block_children
            legacy._query_database = original_query_database
            legacy._notion_request = original_notion_request

        self.assertEqual(len(records), 2)
        self.assertEqual(aggregated["2차 메뉴"]["AOS"]["PASS"], 1)
        self.assertEqual(aggregated["2차 메뉴"]["AOS"]["NA"], 1)
        self.assertEqual(aggregated["2차 메뉴"]["iOS"]["FAIL"], 1)
        self.assertEqual(aggregated["2차 메뉴"]["iOS"]["PASS"], 1)


if __name__ == "__main__":
    unittest.main()
