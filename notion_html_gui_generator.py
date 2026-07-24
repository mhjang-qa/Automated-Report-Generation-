#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ModuleNotFoundError:
    tk = None
    ttk = None
    filedialog = None
    messagebox = None


NOTION_API_VERSION = "2022-06-28"
NOTION_DATA_SOURCE_API_VERSION = "2025-09-03"
DEFAULT_DEFECT_DB_URL = "https://app.notion.com/p/21473fbd1951800d8321fc2e34c2548e?v=21473fbd195180caab27000c0264da96&source=copy_link"
RESULT_KEYS = ("PASS", "FAIL", "NA")
OS_COLUMN_CANDIDATES = ("OS", "Platform", "플랫폼", "운영체제", "환경", "Device OS")
RESULT_COLUMN_CANDIDATES = (
    "결과", "Result", "RESULT", "테스트 결과", "Test Result",
    "검증 결과", "진행 결과", "Status", "상태", "Result Status"
)
OS_RESULT_COLUMN_ALIASES = {
    "AOS": ("AOS", "Android", "ANDROID", "안드로이드"),
    "iOS": ("iOS", "IOS", "아이폰", "아이오에스"),
}
DEFECT_COLUMN_CANDIDATES = {
    "version": ("목표버전", "Target Version", "Version", "버전", "Fix Version"),
    "target": ("타겟", "Target", "Platform", "OS", "플랫폼", "대상", "서비스"),
    "status": ("상태", "Status", "진행상태", "Progress"),
    "severity": ("심각도", "Severity"),
    "defect_type": ("결함 유형", "Type", "유형", "Category", "분류"),
    "priority": ("우선순위", "Priority", "중요도"),
    "feature": ("피처", "Feature", "기능", "ATM", "ATM 항목", "ATM항목", "ATM 구분", "ATM구분", "메뉴", "Project", "프로젝트", "Name", "이름", "제목", "Title"),
}
ATM_COLUMN_CANDIDATES = ("ATM", "ATM 항목", "ATM항목", "ATM 구분", "ATM구분")
END_STATUS_COLUMN_CANDIDATES = (
    "처리 결과", "종료 결과", "최종 상태", "End Status", "Resolution",
    "상태", "Status", "진행상태", "Progress", "결론", "Result"
)
TARGET_SORT_ORDER = ("AOS", "iOS", "Web", "Admin", "Server", "Common", "미분류")
RELATION_TITLE_CACHE = {}


def _load_env_file():
    env_path = Path(".env")
    if not env_path.exists():
        return

    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception as e:
        print(".env load error:", e)


def _hyphenate_notion_id(raw_id):
    clean = re.sub(r"[^0-9a-fA-F]", "", raw_id or "")
    if len(clean) != 32:
        return ""
    return f"{clean[:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:]}"


def parse_notion_link(notion_url: str) -> dict:
    """Notion URL에서 page_id 또는 database_id를 추출한다."""
    url = (notion_url or "").strip()
    if not url:
        raise ValueError("Notion 링크가 입력되지 않았습니다.")

    ids = re.findall(r"(?<![0-9a-fA-F])([0-9a-fA-F]{32})(?![0-9a-fA-F])", url)
    if not ids:
        ids = re.findall(
            r"(?<![0-9a-fA-F])([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?![0-9a-fA-F])",
            url,
        )
    if not ids:
        raise ValueError("Notion 링크에서 페이지 또는 데이터베이스 ID를 찾지 못했습니다.")

    notion_id = _hyphenate_notion_id(ids[0])
    if not notion_id:
        raise ValueError("Notion ID 형식이 올바르지 않습니다.")

    candidate_ids = []
    for raw_id in ids:
        candidate_id = _hyphenate_notion_id(raw_id)
        if candidate_id and candidate_id not in candidate_ids:
            candidate_ids.append(candidate_id)

    return {
        "notion_id": notion_id,
        "page_id": notion_id,
        "database_id": notion_id,
        "candidate_ids": candidate_ids,
        "source_url": url,
    }


def normalize_result(value: str) -> str:
    """PASS/FAIL/NA 결과값으로 정규화한다."""
    raw = "" if value is None else str(value)
    text = raw.strip()
    key = re.sub(r"[\s/_-]+", "", text).upper()
    clean = re.sub(r"[^A-Za-z가-힣]+", "", text).upper()

    if key in {"PASS", "PASSED", "성공", "통과", "정상", "OK"} or clean in {"PASS", "PASSED", "OK"}:
        return "PASS"
    if key in {"FAIL", "FAILED", "FAILURE", "실패", "불합격", "오류", "NG"} or clean in {"FAIL", "FAILED", "FAILURE", "NG"}:
        return "FAIL"
    if key in {"NA", "N/A", "NONE", "NULL", "미수행", "해당없음", "해당무", "제외", "미대상"} or clean in {"NA", "NAN", "NONE", "NULL"}:
        return "NA"
    if any(word in text for word in ("미수행", "해당없음", "해당 없음", "제외", "미대상")):
        return "NA"
    if not key:
        return "NA"
    return ""


def _canonical_os(value):
    text = str(value or "").strip()
    compact = re.sub(r"[\s/_-]+", "", text).upper()
    if compact in {"AOS", "ANDROID", "안드로이드"}:
        return "AOS"
    if compact in {"IOS", "IPHONE", "아이폰", "아이오에스"}:
        return "iOS"
    return text or "미분류"


def detect_os_result_columns(row: dict) -> dict:
    """OS 컬럼 방식 또는 AOS/iOS 결과 컬럼 방식을 감지한다."""
    keys = list(row.keys())
    lower_map = {str(k).strip().lower(): k for k in keys}
    compact_map = {re.sub(r"[\s/_()\[\]-]+", "", str(k).strip().lower()): k for k in keys}

    def compact(text):
        return re.sub(r"[\s/_()\[\]-]+", "", str(text or "").strip().lower())

    os_column = None
    for candidate in OS_COLUMN_CANDIDATES:
        found = lower_map.get(candidate.lower()) or compact_map.get(compact(candidate))
        if found:
            os_column = found
            break

    result_column = None
    for candidate in RESULT_COLUMN_CANDIDATES:
        found = lower_map.get(candidate.lower()) or compact_map.get(compact(candidate))
        if found:
            result_column = found
            break
    if not result_column:
        result_tokens = ("result", "status", "결과", "상태")
        for key in keys:
            key_compact = compact(key)
            if any(token in key_compact for token in result_tokens):
                result_column = key
                break

    os_result_columns = {}
    for os_name, aliases in OS_RESULT_COLUMN_ALIASES.items():
        for alias in aliases:
            found = lower_map.get(alias.lower()) or compact_map.get(compact(alias))
            if found:
                os_result_columns[os_name] = found
                break
        if os_name not in os_result_columns:
            for key in keys:
                key_compact = compact(key)
                if any(compact(alias) in key_compact for alias in aliases):
                    os_result_columns[os_name] = key
                    break

    if os_column and result_column:
        return {"mode": "os_column", "os_column": os_column, "result_column": result_column}
    if os_result_columns:
        return {"mode": "os_result_columns", "columns": os_result_columns}
    if result_column:
        return {"mode": "result_column", "result_column": result_column}
    return {"mode": "unknown"}


def aggregate_results_by_page(test_cases: list) -> dict:
    """페이지별, OS별 PASS/FAIL/NA 결과를 집계한다."""
    aggregated = {}

    for case in test_cases:
        page_name = case.get("page_name") or "제목 없음"
        row = case.get("row") or {}
        detected = detect_os_result_columns(row)
        aggregated.setdefault(page_name, {})

        if detected["mode"] == "os_column":
            os_name = _canonical_os(row.get(detected["os_column"]))
            result = normalize_result(row.get(detected["result_column"]))
            if not result:
                print("Skip unknown result:", row.get(detected["result_column"]), row)
                continue
            bucket = aggregated[page_name].setdefault(os_name, {key: 0 for key in RESULT_KEYS})
            bucket[result] += 1

        elif detected["mode"] == "os_result_columns":
            for os_name, column in detected["columns"].items():
                result = normalize_result(row.get(column))
                if not result:
                    print("Skip unknown result:", row.get(column), row)
                    continue
                bucket = aggregated[page_name].setdefault(os_name, {key: 0 for key in RESULT_KEYS})
                bucket[result] += 1

        elif detected["mode"] == "result_column":
            result = normalize_result(row.get(detected["result_column"]))
            if not result:
                print("Skip unknown result:", row.get(detected["result_column"]), row)
                continue
            os_name = (
                row.get("OS")
                or row.get("os")
                or row.get("_os")
                or _extract_os_from_text(page_name)
                or "미분류"
            )
            bucket = aggregated[page_name].setdefault(_canonical_os(os_name), {key: 0 for key in RESULT_KEYS})
            bucket[result] += 1

        else:
            print("Skip row without OS/result columns:", row)

    for page_name, os_map in aggregated.items():
        for os_name, counts in os_map.items():
            total = sum(counts.get(key, 0) for key in RESULT_KEYS)
            counts["TOTAL"] = total
            for key in RESULT_KEYS:
                counts[f"{key}_RATE"] = round((counts.get(key, 0) / total * 100), 1) if total else 0.0

    return aggregated


def _get_notion_token():
    _load_env_file()
    token = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
    if not token:
        raise ValueError(".env 또는 환경변수에 NOTION_TOKEN 또는 NOTION_API_KEY가 필요합니다.")
    return token


def _notion_request(method, path, payload=None, notion_version=NOTION_API_VERSION):
    token = _get_notion_token()
    url = f"https://api.notion.com/v1{path}"
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": notion_version,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print("Notion HTTP error:", e.code, detail)
        if e.code in {401, 403}:
            raise ValueError("Notion API 인증 실패 또는 페이지 접근 권한이 없습니다.") from e
        if e.code == 404:
            raise ValueError("Notion 페이지 또는 데이터베이스를 찾을 수 없습니다.") from e
        raise ValueError(f"Notion API 오류({e.code}): {detail[:300]}") from e
    except urllib.error.URLError as e:
        print("Notion network error:", e)
        raise ValueError(f"Notion 네트워크 오류: {e.reason}") from e


def _notion_paginated(method, path, payload=None, notion_version=NOTION_API_VERSION):
    results = []
    cursor = None
    while True:
        current_payload = dict(payload or {})
        if cursor:
            current_payload["start_cursor"] = cursor
        current_path = path
        if method == "GET" and cursor:
            separator = "&" if "?" in current_path else "?"
            current_path = f"{current_path}{separator}{urllib.parse.urlencode({'start_cursor': cursor})}"
        data = _notion_request(
            method,
            current_path,
            current_payload if method == "POST" else None,
            notion_version=notion_version,
        )
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return results


def _plain_text(parts):
    return "".join(part.get("plain_text", "") for part in parts or "").strip()


def _block_plain_text(block):
    btype = block.get("type")
    data = block.get(btype) or {}
    if btype == "table_row":
        return " ".join(_plain_text(cell) for cell in data.get("cells") or []).strip()
    return _plain_text(data.get("rich_text"))


def _extract_result_from_text(text):
    raw = str(text or "").strip()
    if not raw:
        return ""

    def from_fragment(fragment):
        result = normalize_result(fragment)
        if result:
            return result
        token_match = re.search(r"\b(PASS|PASSED|FAIL|FAILED|N/?A|NA|OK|NG)\b", fragment, flags=re.IGNORECASE)
        if token_match:
            return normalize_result(token_match.group(1))
        for korean, result_key in (
            ("미수행", "NA"),
            ("해당없음", "NA"),
            ("해당 없음", "NA"),
            ("통과", "PASS"),
            ("성공", "PASS"),
            ("실패", "FAIL"),
            ("오류", "FAIL"),
        ):
            if korean in fragment:
                return result_key
        return ""

    patterns = (
        r"(?:결과|테스트\s*결과|검증\s*결과|Result|Status|상태)\s*[:：=\-]?\s*([^\n\r,;/|]+)",
        r"(?:결과|테스트\s*결과|검증\s*결과|Result|Status|상태).*?\b(PASS|FAIL|N/?A|NA)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if not match:
            continue
        result = from_fragment(match.group(1))
        if result:
            return result

    if re.search(r"(?:결과|테스트\s*결과|검증\s*결과|Result|Status|상태)", raw, flags=re.IGNORECASE):
        return from_fragment(raw)
    return ""


def _extract_os_from_text(text):
    raw = str(text or "").strip()
    if not raw:
        return ""

    match = re.search(
        r"(?:\bOS\b|Platform|플랫폼|운영체제|환경)\s*[:：=\-]\s*([A-Za-z가-힣0-9_/\- ]+)",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        value = re.split(r"[,;/|\n\r]", match.group(1), maxsplit=1)[0].strip()
        os_name = _canonical_os(value)
        if os_name:
            return os_name

    compact = re.sub(r"[\s/_\-\[\]()]+" , "", raw).upper()
    if re.search(r"\bAOS\b|\bANDROID\b|안드로이드", raw, flags=re.IGNORECASE) or "AOS" in compact:
        return "AOS"
    if re.search(r"\bIOS\b|\bIPHONE\b|아이폰|아이오에스", raw, flags=re.IGNORECASE) or "IOS" in compact:
        return "iOS"
    return ""


def _relation_page_title(page_id):
    if not page_id:
        return ""
    if page_id in RELATION_TITLE_CACHE:
        return RELATION_TITLE_CACHE[page_id]
    try:
        page = _notion_request("GET", f"/pages/{page_id}")
        title = _page_title(page)
    except Exception as e:
        print("Relation title read skipped:", page_id, e)
        title = ""
    RELATION_TITLE_CACHE[page_id] = title
    return title


def _is_feature_property_name(name):
    compact = re.sub(r"\s+", "", str(name or "").strip().lower())
    if not compact:
        return False
    candidates = [*DEFECT_COLUMN_CANDIDATES["feature"], *ATM_COLUMN_CANDIDATES]
    candidate_compacts = {re.sub(r"\s+", "", candidate.lower()) for candidate in candidates}
    return compact in candidate_compacts or "atm" in compact


def _property_value(prop, property_name=""):
    ptype = prop.get("type")
    value = prop.get(ptype)
    if ptype == "title":
        return _plain_text(value)
    if ptype == "rich_text":
        return _plain_text(value)
    if ptype == "select":
        return (value or {}).get("name", "")
    if ptype == "multi_select":
        return ", ".join(item.get("name", "") for item in value or [])
    if ptype == "status":
        return (value or {}).get("name", "")
    if ptype == "checkbox":
        return "true" if value else "false"
    if ptype == "number":
        return "" if value is None else str(value)
    if ptype == "date":
        return (value or {}).get("start", "")
    if ptype == "relation":
        if not _is_feature_property_name(property_name):
            return ""
        titles = [_relation_page_title(item.get("id")) for item in value or []]
        return ", ".join(title for title in titles if title)
    if ptype == "formula":
        return _property_value({"type": value.get("type"), value.get("type"): value.get(value.get("type"))}, property_name) if value else ""
    if ptype == "rollup":
        if value and value.get("type") == "array":
            values = [
                _property_value({"type": item.get("type"), item.get("type"): item.get(item.get("type"))}, property_name)
                for item in value.get("array") or []
            ]
            return ", ".join(item for item in values if item)
        return json.dumps(value, ensure_ascii=False) if value else ""
    return str(value or "")


def _page_title(page):
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title = _property_value(prop)
            if title:
                return title
    return page.get("child_page", {}).get("title") or page.get("id", "제목 없음")


def _page_properties_to_row(page):
    return {name: _property_value(prop, name) for name, prop in (page.get("properties") or {}).items()}


def _data_source_ids_from_database(database_id):
    data = _notion_request(
        "GET",
        f"/databases/{database_id}",
        notion_version=NOTION_DATA_SOURCE_API_VERSION,
    )
    data_sources = data.get("data_sources") or []
    return [item.get("id") for item in data_sources if item.get("id")]


def _query_data_source(data_source_id):
    return _notion_paginated(
        "POST",
        f"/data_sources/{data_source_id}/query",
        {},
        notion_version=NOTION_DATA_SOURCE_API_VERSION,
    )


def _query_database(database_id):
    try:
        return _notion_paginated("POST", f"/databases/{database_id}/query", {})
    except ValueError as e:
        print("Database query fallback to data_sources:", e)

    rows = []
    data_source_ids = _data_source_ids_from_database(database_id)
    if not data_source_ids:
        raise ValueError(
            "Notion 데이터베이스의 data source 접근 권한이 없습니다. "
            "해당 DB 원본을 Notion Integration에 공유해주세요."
        )
    for data_source_id in data_source_ids:
        rows.extend(_query_data_source(data_source_id))
    return rows


def _list_block_children(block_id):
    return _notion_paginated("GET", f"/blocks/{block_id}/children")


def _iter_block_tree(block_id, max_depth=5):
    if max_depth < 0:
        return
    try:
        children = _list_block_children(block_id)
    except ValueError as e:
        print("Block children read skipped:", block_id, e)
        return
    for block in children:
        yield block
        if block.get("has_children"):
            yield from _iter_block_tree(block["id"], max_depth - 1)


def fetch_notion_children(notion_id: str) -> list:
    """입력된 Notion 페이지/DB의 하위 페이지를 조회한다."""
    children = []
    try:
        pages = _query_database(notion_id)
        for page in pages:
            if page.get("object") == "page":
                children.append({"id": page["id"], "title": _page_title(page), "page": page, "source": "database"})
        if children:
            return children
    except ValueError as e:
        print("Database query fallback to page children:", e)

    for block in _list_block_children(notion_id):
        btype = block.get("type")
        if btype == "child_page":
            children.append({"id": block["id"], "title": block.get("child_page", {}).get("title", "제목 없음"), "source": "child_page"})
        elif btype == "child_database":
            title = block.get("child_database", {}).get("title", "제목 없음")
            try:
                for page in _query_database(block["id"]):
                    children.append({"id": page["id"], "title": title, "page": page, "source": "child_database"})
            except ValueError as e:
                print("Child database query error:", e)
    return children


def _table_rows_from_blocks(page_id):
    rows = []
    for block in _iter_block_tree(page_id):
        if block.get("type") != "table":
            continue
        table_rows = [b for b in _list_block_children(block["id"]) if b.get("type") == "table_row"]
        if not table_rows:
            continue
        header_cells = table_rows[0].get("table_row", {}).get("cells", [])
        headers = [_plain_text(cell) or f"컬럼{i + 1}" for i, cell in enumerate(header_cells)]
        for table_row in table_rows[1:]:
            cells = table_row.get("table_row", {}).get("cells", [])
            row = {}
            for i, header in enumerate(headers):
                row[header] = _plain_text(cells[i]) if i < len(cells) else ""
            rows.append(row)
    return rows


def _checklist_rows_from_blocks(page_id):
    rows = []
    current_os = ""
    text_block_types = {
        "paragraph", "heading_1", "heading_2", "heading_3",
        "bulleted_list_item", "numbered_list_item", "to_do", "toggle", "quote", "callout",
    }

    for block in _iter_block_tree(page_id):
        btype = block.get("type")
        if btype not in text_block_types:
            continue

        text = _block_plain_text(block)
        if not text:
            continue

        detected_os = _extract_os_from_text(text)
        if detected_os:
            current_os = detected_os

        if btype != "to_do" and "결과" not in text and not re.search(r"Result|Status|상태", text, flags=re.IGNORECASE):
            continue

        result = _extract_result_from_text(text)
        if not result:
            continue

        os_name = detected_os or current_os or "미분류"
        rows.append({
            "OS": os_name,
            "결과": result,
            "체크리스트": text,
        })

    if rows:
        print(f"Checklist TC rows found: {len(rows)}")
    return rows


def fetch_test_cases_from_page(page_id: str, include_page_properties: bool = True) -> list:
    """하위 페이지 내 테스트 케이스 데이터를 조회한다."""
    rows = []
    if include_page_properties:
        try:
            page = _notion_request("GET", f"/pages/{page_id}")
            row = _page_properties_to_row(page)
            if detect_os_result_columns(row).get("mode") != "unknown":
                rows.append(row)
        except ValueError as e:
            print("Page property read skipped:", e)

    for block in _iter_block_tree(page_id):
        try:
            if block.get("type") == "child_database":
                for page in _query_database(block["id"]):
                    rows.append(_page_properties_to_row(page))
            elif block.get("type") == "link_to_page":
                link = block.get("link_to_page", {})
                if link.get("type") == "database_id" and link.get("database_id"):
                    for page in _query_database(link["database_id"]):
                        rows.append(_page_properties_to_row(page))
        except ValueError as e:
            print("Child database read skipped:", block.get("id"), e)

    try:
        rows.extend(_table_rows_from_blocks(page_id))
    except ValueError as e:
        print("Table block read skipped:", e)

    try:
        rows.extend(_checklist_rows_from_blocks(page_id))
    except ValueError as e:
        print("Checklist block read skipped:", e)

    return rows


def generate_html_report(aggregated_data: dict) -> str:
    """기존 HTML 폼과 동일한 형태로 HTML을 생성한다."""
    gui = NotionHtmlGeneratorGUI.__new__(NotionHtmlGeneratorGUI)
    return gui.build_tc_html_from_aggregated("OS별 테스트 결과", "", aggregated_data)


def _find_column(row, candidates):
    lower_map = {str(k).strip().lower(): k for k in row.keys()}
    for candidate in candidates:
        found = lower_map.get(candidate.lower())
        if found:
            return found
    compact_map = {re.sub(r"\s+", "", str(k).strip().lower()): k for k in row.keys()}
    for candidate in candidates:
        found = compact_map.get(re.sub(r"\s+", "", candidate.lower()))
        if found:
            return found
    return None


def _defect_columns(row):
    return {key: _find_column(row, candidates) for key, candidates in DEFECT_COLUMN_CANDIDATES.items()}


def _find_atm_column(row):
    column = _find_column(row, ATM_COLUMN_CANDIDATES)
    if column:
        return column
    for key in row.keys():
        compact = re.sub(r"\s+", "", str(key or "").strip().lower())
        if "atm" in compact:
            return key
    return None


def _query_rows_from_notion_database_or_page(notion_id):
    try:
        pages = _query_database(notion_id)
        rows = [_page_properties_to_row(page) for page in pages if page.get("object") == "page"]
        if rows:
            return rows
    except ValueError as e:
        print("Defect database direct query fallback:", e)
        if "data source 접근 권한" in str(e) or "접근 권한" in str(e):
            raise

    rows = []
    for child in fetch_notion_children(notion_id):
        page = child.get("page")
        if page:
            rows.append(_page_properties_to_row(page))
        try:
            rows.extend(fetch_test_cases_from_page(child["id"]))
        except ValueError as e:
            print("Defect child read skipped:", e)
    return rows


def fetch_defects_from_notion(defect_db_url: str) -> list:
    """결함 DB 링크에서 결함 현황 데이터를 조회한다."""
    parsed = parse_notion_link(defect_db_url)
    rows = []
    errors = []
    for candidate_id in parsed.get("candidate_ids", [parsed["notion_id"]]):
        try:
            rows = _query_rows_from_notion_database_or_page(candidate_id)
            if rows:
                break
        except ValueError as e:
            errors.append(str(e))
            print("Defect candidate skipped:", candidate_id, e)
    if not rows and errors:
        access_errors = [
            error for error in errors
            if "data source 접근 권한" in error or "접근 권한" in error or "shared with your integration" in error
        ]
        raise ValueError(access_errors[0] if access_errors else errors[0])
    defects = []
    for row in rows:
        columns = _defect_columns(row)
        defects.append({"row": row, "columns": columns})
    return defects


def normalize_end_status(value: str, allow_invalid: bool = True) -> str:
    text = str(value or "").strip()
    compact = re.sub(r"[\s/_()\\[\\]-]+", "", text).upper()
    if not compact:
        return "future"

    # "QA 검증 -회귀 (QA Verification)"는 운영 반영 후 검증 단계로,
    # END 리포트에서는 수정 정상 반영으로 집계한다.
    is_qa_regression = (
        "QA 검증" in text
        or "QA검증" in text
        or "QA Verification" in text
        or "QAVERIFICATION" in compact
        or ("QA" in compact and "회귀" in text)
    )
    if is_qa_regression:
        return "fixed"
    if any(word in text for word in ("추후", "보류", "다음", "차기", "미반영", "미수정", "예정", "대기")):
        return "future"
    if compact in {"DEFERRED", "PENDING", "LATER", "TODO", "OPEN", "INPROGRESS", "BACKLOG"}:
        return "future"

    if allow_invalid and any(word in text for word in ("결함아님", "결함 아님", "정상 동작", "재현불가", "중복", "기획")):
        return "invalid"
    if allow_invalid and compact in {"INVALID", "NOTABUG", "WONTFIX", "DUPLICATE", "ASIS"}:
        return "invalid"
    if compact in {"DONE", "RESOLVED", "CLOSED", "FIXED", "COMPLETE", "COMPLETED", "PASS"}:
        return "fixed"
    if any(word in text for word in ("완료", "해결", "종료", "수정완료", "반영완료", "정상 반영", "정상반영")):
        return "fixed"
    return "future"


def aggregate_end_defects(defects: list) -> dict:
    counts = {"total": 0, "fixed": 0, "future": 0, "invalid": 0}
    for defect in defects:
        row = defect.get("row") or {}
        columns = defect.get("columns") or _defect_columns(row)
        status_column = _find_column(row, END_STATUS_COLUMN_CANDIDATES) or columns.get("status")
        type_column = columns.get("defect_type")
        status_text = str(row.get(status_column, "") if status_column else "")
        type_text = str(row.get(type_column, "") if type_column else "")
        bucket = normalize_end_status(status_text)
        if bucket == "future" and not status_text.strip():
            bucket = normalize_end_status(type_text, allow_invalid=False)
        counts["total"] += 1
        counts[bucket] += 1
    return counts


def extract_target_versions(defects: list) -> list:
    """결함 데이터에서 목표버전 목록을 추출한다."""
    versions = set()
    missing_count = 0
    for defect in defects:
        row = defect.get("row") or {}
        version_column = (defect.get("columns") or {}).get("version") or _find_column(row, DEFECT_COLUMN_CANDIDATES["version"])
        if not version_column:
            missing_count += 1
            continue
        value = str(row.get(version_column, "")).strip()
        if value:
            for part in re.split(r"[,/]\s*", value):
                if part.strip():
                    versions.add(part.strip())
    if missing_count and not versions:
        raise ValueError("목표버전 컬럼을 찾지 못했습니다.")

    def version_key(value):
        chunks = re.split(r"(\d+)", value)
        return [int(c) if c.isdigit() else c.lower() for c in chunks]

    return sorted(versions, key=version_key)


def filter_defects_by_target_version(defects: list, target_version: str) -> list:
    """선택한 목표버전 기준으로 결함을 필터링한다."""
    target = str(target_version or "").strip()
    if not target:
        raise ValueError("목표버전을 선택해주세요.")

    filtered = []
    for defect in defects:
        row = defect.get("row") or {}
        version_column = (defect.get("columns") or {}).get("version") or _find_column(row, DEFECT_COLUMN_CANDIDATES["version"])
        if not version_column:
            continue
        values = [part.strip() for part in re.split(r"[,/]\s*", str(row.get(version_column, ""))) if part.strip()]
        if target in values or str(row.get(version_column, "")).strip() == target:
            filtered.append(defect)
    return filtered


def normalize_target(value: str) -> str:
    """타겟 값을 AOS/iOS/Web/Admin/Server/Common/미분류 등으로 정규화한다."""
    text = str(value or "").strip()
    compact = re.sub(r"[\s/_-]+", "", text).upper()
    if not compact:
        return "미분류"
    if compact in {"AOS", "ANDROID", "안드로이드"}:
        return "AOS"
    if compact in {"IOS", "IPHONE", "아이폰", "아이오에스"}:
        return "iOS"
    if compact in {"WEB", "MOBILEWEB", "웹", "모바일웹"}:
        return "Web"
    if compact in {"ADMIN", "BO", "BACKOFFICE", "관리자", "어드민"}:
        return "Admin"
    if compact in {"SERVER", "API", "BACKEND", "BE", "서버"}:
        return "Server"
    if compact in {"COMMON", "공통", "ALL"}:
        return "Common"
    return text


def normalize_defect_status(value: str) -> str:
    """결함 상태값을 Open/In Progress/Done 계열로 정규화한다."""
    text = str(value or "").strip()
    compact = re.sub(r"[\s/_-]+", "", text).upper()
    if compact in {"DONE", "RESOLVED", "CLOSED", "FIXED", "COMPLETE", "COMPLETED", "완료", "해결", "종료", "수정완료"}:
        return "Done"
    if compact in {"INPROGRESS", "PROGRESS", "DOING", "ONGOING", "진행중", "처리중", "수정중"}:
        return "In Progress"
    if compact in {"OPEN", "NEW", "TODO", "BACKLOG", "미처리", "오픈", "신규", ""}:
        return "Open"
    return "Open"


def _target_sort_key(target):
    if target in TARGET_SORT_ORDER:
        return (0, TARGET_SORT_ORDER.index(target), "")
    return (1, len(TARGET_SORT_ORDER), target.lower())


def aggregate_defects_by_target(defects: list) -> dict:
    """타겟별 결함 현황을 집계한다."""
    aggregated = {}
    for defect in defects:
        row = defect.get("row") or {}
        columns = defect.get("columns") or _defect_columns(row)
        target_column = columns.get("target")
        status_column = columns.get("status")
        severity_column = columns.get("severity")
        priority_column = columns.get("priority")
        version_column = columns.get("version")

        target = normalize_target(row.get(target_column, "") if target_column else "")
        status = normalize_defect_status(row.get(status_column, "") if status_column else "")
        severity = str(row.get(severity_column, "") if severity_column else "").strip() or "미분류"
        priority = str(row.get(priority_column, "") if priority_column else "").strip() or "미분류"
        version = str(row.get(version_column, "") if version_column else "").strip()

        bucket = aggregated.setdefault(
            target,
            {
                "target": target,
                "version": version,
                "total": 0,
                "open": 0,
                "in_progress": 0,
                "done": 0,
                "severity": {},
                "priority": {},
                "statuses": {},
            },
        )
        bucket["total"] += 1
        if status == "Done":
            bucket["done"] += 1
        elif status == "In Progress":
            bucket["in_progress"] += 1
        else:
            bucket["open"] += 1
        bucket["severity"][severity] = bucket["severity"].get(severity, 0) + 1
        bucket["priority"][priority] = bucket["priority"].get(priority, 0) + 1
        bucket["statuses"][status] = bucket["statuses"].get(status, 0) + 1

    return {key: aggregated[key] for key in sorted(aggregated.keys(), key=_target_sort_key)}


def extract_feature_name(value: str) -> str:
    text = str(value or "").strip()
    if _looks_like_relation_id_text(text):
        return "미분류"
    match = re.search(r"\[([^\]]+)\]", text)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return text or "미분류"


def _looks_like_relation_id_text(value):
    text = str(value or "").strip()
    if not text:
        return False
    if "'id':" in text or '"id":' in text:
        return True
    compact = re.sub(r"[^0-9a-fA-F]", "", text)
    return len(compact) == 32 and bool(re.fullmatch(r"[0-9a-fA-F-]+", text))


def _feature_value_from_row(row, columns):
    feature_column = (columns or {}).get("feature")
    primary = str(row.get(feature_column, "") if feature_column else "").strip()
    if primary and not _looks_like_relation_id_text(primary):
        return primary

    for key, value in row.items():
        if key == feature_column:
            continue
        text = str(value or "").strip()
        if not text or _looks_like_relation_id_text(text):
            continue
        if re.search(r"\[[^\]]+\]", text):
            return text

    for key, value in row.items():
        key_text = str(key).strip().lower()
        if key == feature_column or key_text in {"id", "issue id", "이슈 id", "상태", "status", "목표버전", "version", "심각도", "severity"}:
            continue
        text = str(value or "").strip()
        if text and not _looks_like_relation_id_text(text):
            return text
    return "미분류"


def _atm_value_from_row(row):
    atm_column = _find_atm_column(row)
    if not atm_column:
        return "비어있음"
    value = str(row.get(atm_column, "") or "").strip()
    return value if value else "비어있음"


def aggregate_features_from_defects(defects: list) -> dict:
    """선택한 결함 목록을 ATM 기준으로 집계한다."""
    aggregated = {}
    for defect in defects:
        row = defect.get("row") or {}
        feature = _atm_value_from_row(row)
        aggregated[feature] = aggregated.get(feature, 0) + 1
    return dict(sorted(aggregated.items(), key=lambda item: (-item[1], item[0])))


def defects_to_feature_lines(defects: list) -> str:
    """기존 FEA HTML 생성기가 읽을 수 있는 ATM 라인 형태로 변환한다."""
    lines = []
    for defect in defects:
        row = defect.get("row") or {}
        source = _atm_value_from_row(row)
        lines.append(source)
    return "\n".join(lines)


def defects_to_em_tsv(defects: list) -> str:
    """기존 EM HTML 생성기가 읽을 수 있는 TSV 형태로 변환한다."""
    headers = ["ATM", "ID", "결함 유형", "목표버전", "심각도"]
    lines = ["\t".join(headers)]
    for index, defect in enumerate(defects, start=1):
        row = defect.get("row") or {}
        columns = defect.get("columns") or _defect_columns(row)
        feature_column = columns.get("feature")
        type_column = columns.get("defect_type")
        version_column = columns.get("version")
        severity_column = columns.get("severity")
        id_column = _find_column(row, ("ID", "Issue ID", "이슈 ID", "Jira", "Ticket", "티켓", "Key"))

        values = [
            str(row.get(feature_column, "") if feature_column else "").strip(),
            str(row.get(id_column, "") if id_column else f"ISSUE-{index:03d}").strip(),
            str(row.get(type_column, "") if type_column else "").strip(),
            str(row.get(version_column, "") if version_column else "").strip(),
            str(row.get(severity_column, "") if severity_column else "").strip(),
        ]
        safe_values = [value.replace("\t", " ").replace("\r", " ").replace("\n", " ") for value in values]
        lines.append("\t".join(safe_values))
    return "\n".join(lines)


def generate_em_html_report(aggregated_defects: dict) -> str:
    """기존 HTML 폼과 동일한 스타일로 EM 리포트 HTML을 생성한다."""
    gui = NotionHtmlGeneratorGUI.__new__(NotionHtmlGeneratorGUI)
    return gui.build_em_html_from_aggregated("결함 집계 리포트", "", aggregated_defects)


def generate_fea_html_report(aggregated_features: dict) -> str:
    """기존 HTML 폼과 동일한 스타일로 FEA 리포트 HTML을 생성한다."""
    gui = NotionHtmlGeneratorGUI.__new__(NotionHtmlGeneratorGUI)
    lines = []
    for feature, count in aggregated_features.items():
        lines.extend([f"[{feature}]{feature}"] * count)
    return gui.build_fea_html("피처별 기준", "", "\n".join(lines))


class NotionHtmlGeneratorGUI:
    def __init__(self, root):
        print("__init__ start")

        self.root = root
        self.root.title("노션 임베드용 HTML 생성기")
        self.root.minsize(1200, 760)

        self.generated_html = ""

        self.build_style()
        self.build_variables()
        self.build_layout()
        self.bind_events()

        self.center_window(1400, 900)
        self.on_type_changed()

        self.root.after(100, self.force_show_window)

        print("__init__ end")

    def center_window(self, width=1400, height=900):
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        x = max((screen_width - width) // 2, 0)
        y = max((screen_height - height) // 2, 0)

        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def force_show_window(self):
        try:
            self.root.update_idletasks()
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.root.attributes("-topmost", True)
            self.root.after(700, lambda: self.root.attributes("-topmost", False))
        except Exception as e:
            print("force_show_window error:", e)

    def build_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TLabel", font=("Apple SD Gothic Neo", 11))
        style.configure("TButton", font=("Apple SD Gothic Neo", 11), padding=6)
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=4)
        style.configure("Header.TLabel", font=("Apple SD Gothic Neo", 15, "bold"))
        style.configure("Sub.TLabel", font=("Apple SD Gothic Neo", 10))
        style.configure("Section.TLabelframe.Label", font=("Apple SD Gothic Neo", 11, "bold"))
        style.configure("Hint.TLabel", font=("Apple SD Gothic Neo", 10), foreground="#666666")

    def build_variables(self):
        self.template_type = tk.StringVar(value="EM")
        self.title_var = tk.StringVar(value="결함 집계 리포트")
        self.version_var = tk.StringVar(value="5.20.0")
        self.filename_var = tk.StringVar(value="report_5.20.0.html")
        self.notion_link_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="대기 중")
        self.defect_db_link_var = tk.StringVar(value=DEFAULT_DEFECT_DB_URL)
        self.target_version_var = tk.StringVar(value="")
        self.defect_rows_cache = []
        self.defect_rows_cache_url = ""

        self.end_total_var = tk.StringVar(value="82")
        self.end_fixed_var = tk.StringVar(value="60")
        self.end_future_var = tk.StringVar(value="2")
        self.end_invalid_var = tk.StringVar(value="20")
        self.end_note_var = tk.StringVar(
            value="※ 차트 수치는 총합 기준으로 집계했으며, 별도 관리 메모는 필요 시 하단 설명에 기재합니다."
        )

        self.tc_aos_pass_var = tk.StringVar(value="214")
        self.tc_aos_fail_var = tk.StringVar(value="23")
        self.tc_aos_na_var = tk.StringVar(value="123")
        self.tc_ios_pass_var = tk.StringVar(value="177")
        self.tc_ios_fail_var = tk.StringVar(value="36")
        self.tc_ios_na_var = tk.StringVar(value="147")

    def build_layout(self):
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill="both", expand=True)

        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right = ttk.Frame(top)
        right.pack(side="right", fill="both", expand=True)

        ttk.Label(left, text="노션 임베드용 HTML 생성기", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="생성할 유형을 선택하고 입력값을 넣으면 HTML을 자동 생성합니다.",
            style="Sub.TLabel"
        ).pack(anchor="w", pady=(4, 12))

        top_action_row = ttk.Frame(left)
        top_action_row.pack(fill="x", pady=(0, 10))
        ttk.Button(
            top_action_row,
            text="HTML 생성",
            command=self.generate_html
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(
            top_action_row,
            text="파일로 저장",
            command=self.save_html
        ).pack(side="left", fill="x", expand=True)

        common_frame = ttk.LabelFrame(left, text="공통 설정", padding=10, style="Section.TLabelframe")
        common_frame.pack(fill="x", pady=(0, 10))

        row = ttk.Frame(common_frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="생성 유형", width=12).pack(side="left")
        self.type_combo = ttk.Combobox(
            row,
            textvariable=self.template_type,
            state="readonly",
            values=["EM", "END", "FEA", "TC"],
            width=20
        )
        self.type_combo.pack(side="left", fill="x", expand=True)

        row = ttk.Frame(common_frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="타이틀", width=12).pack(side="left")
        self.title_entry = ttk.Entry(row, textvariable=self.title_var, width=40)
        self.title_entry.pack(side="left", fill="x", expand=True)

        row = ttk.Frame(common_frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="버전", width=12).pack(side="left")
        self.version_entry = ttk.Entry(row, textvariable=self.version_var, width=40)
        self.version_entry.pack(side="left", fill="x", expand=True)

        row = ttk.Frame(common_frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="파일명", width=12).pack(side="left")
        self.filename_entry = ttk.Entry(row, textvariable=self.filename_var, width=40)
        self.filename_entry.pack(side="left", fill="x", expand=True)

        row = ttk.Frame(common_frame)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Notion 링크", width=12).pack(side="left")
        self.notion_entry = ttk.Entry(row, textvariable=self.notion_link_var, width=40)
        self.notion_entry.pack(side="left", fill="x", expand=True)

        self.dynamic_frame = ttk.LabelFrame(left, text="유형별 설정", padding=10, style="Section.TLabelframe")
        self.dynamic_frame.pack(fill="x", pady=(0, 10))

        self.dynamic_container = ttk.Frame(self.dynamic_frame)
        self.dynamic_container.pack(fill="both", expand=True)

        data_frame = ttk.LabelFrame(left, text="원본 데이터 입력", padding=10, style="Section.TLabelframe")
        data_frame.pack(fill="both", expand=True, pady=(0, 10))

        btn_row = ttk.Frame(data_frame)
        btn_row.pack(fill="x", pady=(0, 8))

        ttk.Button(btn_row, text="샘플 입력", command=self.load_sample_data).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="파일 불러오기", command=self.load_data_file).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="입력값 비우기", command=self.clear_data_text).pack(side="left")

        self.data_text = tk.Text(
            data_frame,
            wrap="word",
            height=18,
            font=("Menlo", 11),
            undo=True
        )
        self.data_text.pack(fill="both", expand=True)

        action_row = ttk.Frame(left)
        action_row.pack(fill="x", pady=(0, 10))

        ttk.Button(
            action_row,
            text="HTML 생성",
            command=self.generate_html
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(
            action_row,
            text="파일로 저장",
            command=self.save_html
        ).pack(side="left", fill="x", expand=True)

        status_frame = ttk.LabelFrame(left, text="처리 상태", padding=10, style="Section.TLabelframe")
        status_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            style="Hint.TLabel",
            wraplength=620,
            justify="left"
        ).pack(anchor="w", fill="x")

        preview_frame = ttk.LabelFrame(right, text="생성된 HTML", padding=10, style="Section.TLabelframe")
        preview_frame.pack(fill="both", expand=True)

        preview_btn_row = ttk.Frame(preview_frame)
        preview_btn_row.pack(fill="x", pady=(0, 8))
        ttk.Button(preview_btn_row, text="전체 복사", command=self.copy_html).pack(side="left")

        self.preview_text = tk.Text(
            preview_frame,
            wrap="none",
            font=("Menlo", 11),
            undo=False
        )
        self.preview_text.pack(fill="both", expand=True)

        x_scroll = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.preview_text.xview)
        y_scroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        x_scroll.pack(fill="x", side="bottom")
        y_scroll.pack(fill="y", side="right")

    def bind_events(self):
        self.type_combo.bind("<<ComboboxSelected>>", lambda e: self.on_type_changed())
        self.version_var.trace_add("write", self.on_version_changed)
        self.defect_db_link_var.trace_add("write", self.on_defect_link_changed)
        self.target_version_var.trace_add("write", self.on_target_version_changed)

    def on_defect_link_changed(self, *args):
        self.defect_rows_cache = []
        self.defect_rows_cache_url = ""

    def on_target_version_changed(self, *args):
        if self.template_type.get().strip().upper() in {"EM", "FEA"}:
            version = self.target_version_var.get().strip()
            if version and self.version_var.get().strip() != version:
                self.version_var.set(version)

    def on_version_changed(self, *args):
        template = self.template_type.get().strip().upper()
        version = self.version_var.get().strip()

        if template == "EM":
            self.filename_var.set(f"em_{version}.html")
        elif template == "END":
            self.filename_var.set(f"end_{version}.html")
        elif template == "FEA":
            self.filename_var.set(f"fea_{version}.html")
        elif template == "TC":
            self.filename_var.set(f"tc_{version}.html")

    def clear_dynamic_fields(self):
        for widget in self.dynamic_container.winfo_children():
            widget.destroy()

    def on_type_changed(self):
        self.clear_dynamic_fields()
        template = self.template_type.get().strip().upper()
        version = self.version_var.get().strip()

        if template == "EM":
            self.title_var.set("결함 집계 리포트")
            self.filename_var.set(f"em_{version}.html")
            self.build_em_fields()

        elif template == "END":
            self.title_var.set("전체 결함 현황")
            self.filename_var.set(f"end_{version}.html")
            self.build_end_fields()

        elif template == "FEA":
            self.title_var.set("피처별 기준")
            self.filename_var.set(f"fea_{version}.html")
            self.build_fea_fields()

        elif template == "TC":
            self.title_var.set(f"OS별 테스트 결과_{version}")
            self.filename_var.set(f"tc_{version}.html")
            self.build_tc_fields()

        self.load_sample_data()

    def build_em_fields(self):
        ttk.Label(
            self.dynamic_container,
            text="EM 유형은 결함 DB 링크에서 결함 현황을 조회하고 목표버전 기준으로 필터링합니다.",
            wraplength=620,
            justify="left"
        ).pack(anchor="w")

        row = ttk.Frame(self.dynamic_container)
        row.pack(fill="x", pady=(8, 4))
        ttk.Label(row, text="결함 DB 링크", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.defect_db_link_var, width=52).pack(side="left", fill="x", expand=True)

        row = ttk.Frame(self.dynamic_container)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="목표버전", width=12).pack(side="left")
        self.target_version_combo = ttk.Combobox(
            row,
            textvariable=self.target_version_var,
            values=[],
            width=22
        )
        self.target_version_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(row, text="목표버전 새로고침", command=self.refresh_target_versions).pack(side="left")

        ttk.Label(
            self.dynamic_container,
            text="Notion API 토큰이 없거나 링크를 비워두면 기존 원본 데이터 입력 방식으로 EM HTML을 생성할 수 있습니다.",
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(6, 0))

    def build_end_fields(self):
        ttk.Label(
            self.dynamic_container,
            text="Notion 링크를 입력하면 결함 DB에서 상태/처리 결과를 읽어 END 현황을 자동 집계합니다. 링크가 없으면 아래 수동 값을 사용합니다.",
            style="Hint.TLabel",
            wraplength=620,
            justify="left"
        ).pack(anchor="w", pady=(0, 8))
        self.create_labeled_entry(self.dynamic_container, "전체 건수", self.end_total_var)
        self.create_labeled_entry(self.dynamic_container, "수정 정상 반영", self.end_fixed_var)
        self.create_labeled_entry(self.dynamic_container, "추후 수정", self.end_future_var)
        self.create_labeled_entry(self.dynamic_container, "결함아님", self.end_invalid_var)
        self.create_labeled_entry(self.dynamic_container, "하단 노트", self.end_note_var, width=52)

    def build_fea_fields(self):
        ttk.Label(
            self.dynamic_container,
            text="FEA 유형은 결함 DB의 목표버전 기준으로 필터링한 뒤 ATM 항목으로 집계합니다.",
            wraplength=620,
            justify="left"
        ).pack(anchor="w")

        row = ttk.Frame(self.dynamic_container)
        row.pack(fill="x", pady=(8, 4))
        ttk.Label(row, text="결함 DB 링크", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.defect_db_link_var, width=52).pack(side="left", fill="x", expand=True)

        row = ttk.Frame(self.dynamic_container)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="목표버전", width=12).pack(side="left")
        self.target_version_combo = ttk.Combobox(
            row,
            textvariable=self.target_version_var,
            values=[],
            width=22
        )
        self.target_version_combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(row, text="목표버전 새로고침", command=self.refresh_target_versions).pack(side="left")

        ttk.Label(
            self.dynamic_container,
            text="목표버전을 선택하면 Notion 결함 DB의 ATM 항목 기준으로 생성하고, ATM이 비어 있으면 비어있음으로 집계합니다.",
            style="Hint.TLabel"
        ).pack(anchor="w", pady=(6, 0))

    def build_tc_fields(self):
        ttk.Label(
            self.dynamic_container,
            text="Notion 링크를 입력하면 하위 페이지의 테스트 케이스 데이터를 우선 집계합니다. 링크가 없으면 아래 수동 값을 사용합니다.",
            style="Hint.TLabel",
            wraplength=620,
            justify="left"
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self.dynamic_container, text="AOS 값").pack(anchor="w", pady=(0, 4))
        row1 = ttk.Frame(self.dynamic_container)
        row1.pack(fill="x", pady=(0, 8))
        self.create_inline_entry(row1, "PASS", self.tc_aos_pass_var)
        self.create_inline_entry(row1, "FAIL", self.tc_aos_fail_var)
        self.create_inline_entry(row1, "NA", self.tc_aos_na_var)

        ttk.Label(self.dynamic_container, text="iOS 값").pack(anchor="w", pady=(8, 4))
        row2 = ttk.Frame(self.dynamic_container)
        row2.pack(fill="x")
        self.create_inline_entry(row2, "PASS", self.tc_ios_pass_var)
        self.create_inline_entry(row2, "FAIL", self.tc_ios_fail_var)
        self.create_inline_entry(row2, "NA", self.tc_ios_na_var)

    def create_labeled_entry(self, parent, label, variable, width=22):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=12).pack(side="left")
        ttk.Entry(row, textvariable=variable, width=width).pack(side="left", fill="x", expand=True)

    def create_inline_entry(self, parent, label, variable, width=8):
        box = ttk.Frame(parent)
        box.pack(side="left", padx=(0, 8))
        ttk.Label(box, text=label).pack(side="left", padx=(0, 4))
        ttk.Entry(box, textvariable=variable, width=width).pack(side="left")

    def clear_data_text(self):
        self.data_text.delete("1.0", "end")

    def load_data_file(self):
        file_path = filedialog.askopenfilename(
            title="데이터 파일 선택",
            filetypes=[
                ("Text/CSV/TSV", "*.txt *.csv *.tsv"),
                ("HTML", "*.html"),
                ("All files", "*.*"),
            ]
        )
        if not file_path:
            return

        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = Path(file_path).read_text(encoding="utf-8-sig")

        self.data_text.delete("1.0", "end")
        self.data_text.insert("1.0", content)

    def load_sample_data(self):
        template = self.template_type.get().strip().upper()
        self.data_text.delete("1.0", "end")

        if template == "EM":
            sample = """ATM\tID\t결함 유형\t목표버전\t심각도
[GO Hanpass] 모바일 웹 제로페이 개발\tISSUE-430\tUX/UI\t5.20.0\tMajor
[기획] 친구초대 이벤트 관련 정책 및 UI변경 개발 요청\tISSUE-431\t기능\t5.20.0\tMajor
[GO Hanpass] 모바일 웹 제로페이 개발\tISSUE-439\t기능\t5.20.0\tCritical
[GO Hanpass] 모바일 웹 제로페이 개발\tISSUE-455\t텍스트\t5.20.0\tMinor
[월렛]무기명 월렛 발급 도입\tISSUE-517\t기능\t5.20.0\tCritical
[월렛]무기명 월렛 발급 도입\tISSUE-520\tUX/UI\t5.20.0\tMinor"""
            self.data_text.insert("1.0", sample)

        elif template == "END":
            sample = """설명용 메모
- 총 82건
- 수정 정상 반영 60건
- 추후 수정 2건
- 결함아님 20건"""
            self.data_text.insert("1.0", sample)

        elif template == "FEA":
            sample = """[제로페이] 모바일 웹 제로페이 개발
[친구초대] 친구초대 이벤트 관련 정책 및 UI변경 개발 요청
[제로페이] 모바일 웹 제로페이 개발
[택시-해외카드] 해외발행카드 (간편)결제 연동
[월렛-무기명]무기명 월렛 발급 도입
[월렛-무기명]무기명 월렛 발급 도입"""
            self.data_text.insert("1.0", sample)

        elif template == "TC":
            sample = """TC 유형은 우측 수치 입력값으로 생성됩니다.
빈칸은 NA 처리 기준으로 사용할 수 있습니다."""
            self.data_text.insert("1.0", sample)

    def get_text_data(self):
        return self.data_text.get("1.0", "end").strip()

    def parse_delimited_rows(self, raw_text):
        lines = [line for line in raw_text.splitlines() if line.strip()]
        if not lines:
            return []

        delimiter = "\t"
        if "\t" not in lines[0] and "," in lines[0]:
            delimiter = ","

        headers = [h.strip() for h in lines[0].split(delimiter)]
        rows = []

        for line in lines[1:]:
            cols = [c.strip() for c in line.split(delimiter)]
            row = {}
            for i, h in enumerate(headers):
                row[h] = cols[i] if i < len(cols) else ""
            rows.append(row)
        return rows

    def js_str(self, text):
        return json.dumps(text, ensure_ascii=False)

    def set_status(self, message):
        print(message)
        self.status_var.set(message)
        self.root.update_idletasks()

    def refresh_target_versions(self):
        try:
            defect_url = self.defect_db_link_var.get().strip()
            if not defect_url:
                raise ValueError("결함 DB 링크를 입력해주세요.")

            if self.defect_rows_cache and self.defect_rows_cache_url == defect_url:
                self.set_status("캐시된 결함 DB 데이터로 목표버전 목록 갱신 중")
            else:
                self.set_status("결함 DB에서 목표버전 목록 조회 중")
                self.defect_rows_cache = fetch_defects_from_notion(defect_url)
                self.defect_rows_cache_url = defect_url
            if not self.defect_rows_cache:
                raise ValueError("결함 DB에서 데이터를 찾지 못했습니다.")

            versions = extract_target_versions(self.defect_rows_cache)
            if not versions:
                raise ValueError("목표버전 값이 없습니다.")

            if hasattr(self, "target_version_combo"):
                self.target_version_combo.configure(values=versions)
            if self.target_version_var.get().strip() not in versions:
                self.target_version_var.set(versions[-1])
            self.version_var.set(self.target_version_var.get().strip())
            self.set_status(f"목표버전 {len(versions)}개 로딩 완료")

        except Exception as e:
            print("Target version refresh error:", e)
            self.set_status(f"목표버전 로딩 실패: {e}")
            messagebox.showerror("오류", f"목표버전 목록 조회 중 오류가 발생했습니다.\n\n{e}")

    def build_end_counts_from_notion(self, notion_url):
        self.set_status("END 결함 데이터 조회 중")
        defects = fetch_defects_from_notion(notion_url)
        if not defects:
            raise ValueError("END 집계에 사용할 결함 데이터가 없습니다.")

        version = self.version_var.get().strip()
        filtered = defects
        if version:
            try:
                filtered_by_version = filter_defects_by_target_version(defects, version)
                if filtered_by_version:
                    filtered = filtered_by_version
                    self.set_status(f"{version} END 데이터 필터링 완료")
                else:
                    print("END version filter matched no rows; using all defects:", version)
            except ValueError as e:
                print("END version filter skipped:", e)

        counts = aggregate_end_defects(filtered)
        if counts["total"] <= 0:
            raise ValueError("END 집계 결과가 비어 있습니다.")

        self.end_total_var.set(str(counts["total"]))
        self.end_fixed_var.set(str(counts["fixed"]))
        self.end_future_var.set(str(counts["future"]))
        self.end_invalid_var.set(str(counts["invalid"]))
        self.end_note_var.set(
            f"※ Notion 링크 기준 자동 집계: 전체 {counts['total']}건 / "
            f"수정 정상 반영 {counts['fixed']}건 / 추후 수정 {counts['future']}건 / 결함아님 {counts['invalid']}건"
        )
        return counts

    def build_em_aggregated_from_notion(self):
        defect_url = self.defect_db_link_var.get().strip()
        if not defect_url:
            raise ValueError("결함 DB 링크가 비어 있습니다.")

        target_version = self.target_version_var.get().strip()
        if not target_version:
            raise ValueError("EM 생성 전 목표버전을 선택해주세요.")

        defects = self.defect_rows_cache
        if not defects or self.defect_rows_cache_url != defect_url:
            self.set_status("결함 DB 조회 중")
            defects = fetch_defects_from_notion(defect_url)
            self.defect_rows_cache = defects
            self.defect_rows_cache_url = defect_url

        if not defects:
            raise ValueError("결함 DB에서 데이터를 찾지 못했습니다.")

        versions = extract_target_versions(defects)
        if hasattr(self, "target_version_combo"):
            self.target_version_combo.configure(values=versions)

        self.set_status(f"{target_version} 결함 필터링 중")
        filtered = filter_defects_by_target_version(defects, target_version)
        if not filtered:
            raise ValueError(f"선택한 목표버전({target_version})에 해당하는 결함이 없습니다.")

        aggregated = aggregate_defects_by_target(filtered)
        if not aggregated:
            raise ValueError("타겟별로 집계할 결함 데이터가 없습니다.")

        missing_target = any(not ((d.get("columns") or {}).get("target")) for d in filtered)
        if missing_target:
            print("Target column missing in one or more defect rows; using 미분류")
        return aggregated

    def build_em_tsv_from_notion(self):
        defect_url = self.defect_db_link_var.get().strip()
        if not defect_url:
            raise ValueError("결함 DB 링크가 비어 있습니다.")

        target_version = self.target_version_var.get().strip()
        if not target_version:
            raise ValueError("EM 생성 전 목표버전을 선택해주세요.")

        defects = self.defect_rows_cache
        if not defects or self.defect_rows_cache_url != defect_url:
            self.set_status("결함 DB 조회 중")
            defects = fetch_defects_from_notion(defect_url)
            self.defect_rows_cache = defects
            self.defect_rows_cache_url = defect_url

        if not defects:
            raise ValueError("결함 DB에서 데이터를 찾지 못했습니다.")

        versions = extract_target_versions(defects)
        if hasattr(self, "target_version_combo"):
            self.target_version_combo.configure(values=versions)

        self.set_status(f"{target_version} EM 데이터 필터링 중")
        filtered = filter_defects_by_target_version(defects, target_version)
        if not filtered:
            raise ValueError(f"선택한 목표버전({target_version})에 해당하는 결함이 없습니다.")

        tsv = defects_to_em_tsv(filtered)
        rows = self.parse_delimited_rows(tsv)
        if not any((row.get("결함 유형") or row.get("심각도")) for row in rows):
            raise ValueError("EM 집계에 필요한 결함 유형 또는 심각도 컬럼 값이 없습니다.")
        self.set_status(f"EM 결함 {len(filtered)}건 변환 완료")
        return tsv

    def build_fea_lines_from_notion(self):
        defect_url = self.defect_db_link_var.get().strip()
        if not defect_url:
            raise ValueError("결함 DB 링크가 비어 있습니다.")

        target_version = self.target_version_var.get().strip()
        if not target_version:
            raise ValueError("FEA 생성 전 목표버전을 선택해주세요.")

        defects = self.defect_rows_cache
        if not defects or self.defect_rows_cache_url != defect_url:
            self.set_status("결함 DB 조회 중")
            defects = fetch_defects_from_notion(defect_url)
            self.defect_rows_cache = defects
            self.defect_rows_cache_url = defect_url

        if not defects:
            raise ValueError("결함 DB에서 데이터를 찾지 못했습니다.")

        versions = extract_target_versions(defects)
        if hasattr(self, "target_version_combo"):
            self.target_version_combo.configure(values=versions)

        self.set_status(f"{target_version} ATM 데이터 필터링 중")
        filtered = filter_defects_by_target_version(defects, target_version)
        if not filtered:
            raise ValueError(f"선택한 목표버전({target_version})에 해당하는 ATM 데이터가 없습니다.")

        features = aggregate_features_from_defects(filtered)
        if not features:
            raise ValueError("ATM 기준으로 집계할 데이터가 없습니다.")

        self.set_status(f"ATM 구분 {len(features)}개 집계 완료")
        return defects_to_feature_lines(filtered)

    def build_tc_aggregated_from_notion(self, notion_url):
        parsed = parse_notion_link(notion_url)
        notion_id = parsed["notion_id"]
        self.set_status(f"Notion 하위 페이지 조회 중: {notion_id}")

        all_cases = []
        children = []
        candidate_errors = []

        for candidate_id in parsed.get("candidate_ids", [notion_id]):
            try:
                self.set_status(f"Notion DB 행 조회 중: {candidate_id}")
                pages = _query_database(candidate_id)
                for page in pages:
                    if page.get("object") != "page":
                        continue
                    title = _page_title(page)
                    row = _page_properties_to_row(page)
                    if detect_os_result_columns(row).get("mode") != "unknown":
                        all_cases.append({"page_name": title, "row": row})
                    for child_row in fetch_test_cases_from_page(page["id"], include_page_properties=False):
                        all_cases.append({"page_name": title, "row": child_row})
                if all_cases:
                    break
                if pages:
                    children = [
                        {"id": page["id"], "title": _page_title(page), "page": page, "source": "database"}
                        for page in pages
                        if page.get("object") == "page"
                    ]
                    break
            except ValueError as e:
                candidate_errors.append(str(e))
                print("TC database candidate skipped:", candidate_id, e)

        if not all_cases and not children:
            children = fetch_notion_children(notion_id)
            if not children:
                try:
                    page = _notion_request("GET", f"/pages/{notion_id}")
                    children = [{"id": notion_id, "title": _page_title(page), "page": page, "source": "root_page"}]
                except ValueError as e:
                    print("TC root page fallback skipped:", e)

        for index, child in enumerate(children, start=1):
            title = child.get("title") or "제목 없음"
            self.set_status(f"테스트 케이스 수집 중 ({index}/{len(children)}): {title}")
            rows = []
            page_row = child.get("page")
            if page_row:
                row = _page_properties_to_row(page_row)
                if detect_os_result_columns(row).get("mode") != "unknown":
                    rows.append(row)
            rows.extend(fetch_test_cases_from_page(child["id"], include_page_properties=not bool(page_row)))
            for row in rows:
                all_cases.append({"page_name": title, "row": row})

        if not all_cases and candidate_errors:
            access_errors = [
                error for error in candidate_errors
                if "data source 접근 권한" in error or "접근 권한" in error or "shared with your integration" in error
            ]
            if access_errors:
                raise ValueError(access_errors[0])

        if not all_cases:
            raise ValueError("테스트 케이스 컬럼을 찾지 못했습니다.")

        aggregated = aggregate_results_by_page(all_cases)
        if not any(os_map for os_map in aggregated.values()):
            raise ValueError("PASS/FAIL/NA로 집계 가능한 결과값이 없습니다.")
        return aggregated

    def generate_html(self):
        try:
            from notion_html_service import GenerateRequest, generate_report

            template = self.template_type.get().strip().upper()
            title = self.title_var.get().strip()
            version = self.version_var.get().strip()
            request = GenerateRequest(
                template_type=template,
                title=title,
                version=version,
                filename=self.filename_var.get().strip(),
                notion_url=self.notion_link_var.get().strip(),
                raw_text=self.get_text_data(),
                defect_db_url=self.defect_db_link_var.get().strip(),
                target_version=self.target_version_var.get().strip(),
                end_total=self.end_total_var.get().strip(),
                end_fixed=self.end_fixed_var.get().strip(),
                end_future=self.end_future_var.get().strip(),
                end_invalid=self.end_invalid_var.get().strip(),
                end_note=self.end_note_var.get().strip(),
                tc_aos_pass=self.tc_aos_pass_var.get().strip(),
                tc_aos_fail=self.tc_aos_fail_var.get().strip(),
                tc_aos_na=self.tc_aos_na_var.get().strip(),
                tc_ios_pass=self.tc_ios_pass_var.get().strip(),
                tc_ios_fail=self.tc_ios_fail_var.get().strip(),
                tc_ios_na=self.tc_ios_na_var.get().strip(),
            )
            generated = generate_report(request, status_callback=self.set_status)
            result = generated.html

            self.generated_html = result
            self.preview_text.delete("1.0", "end")
            self.preview_text.insert("1.0", result)
            messagebox.showinfo("완료", "HTML 생성이 완료되었습니다.")

        except Exception as e:
            print("HTML generate error:", e)
            self.set_status(f"생성 실패: {e}")
            messagebox.showerror("오류", f"HTML 생성 중 오류가 발생했습니다.\n\n{e}")

    def save_html(self):
        if not self.generated_html.strip():
            messagebox.showwarning("안내", "먼저 HTML 생성 버튼을 눌러주세요.")
            return

        default_name = self.filename_var.get().strip() or "output.html"
        file_path = filedialog.asksaveasfilename(
            title="HTML 저장",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            Path(file_path).write_text(self.generated_html, encoding="utf-8")
            self.set_status(f"저장 완료: {file_path}")
            messagebox.showinfo("저장 완료", f"저장되었습니다.\n{file_path}")
        except Exception as e:
            print("HTML save error:", e)
            self.set_status(f"저장 실패: {e}")
            messagebox.showerror("저장 오류", f"HTML 저장에 실패했습니다.\n\n{e}")

    def copy_html(self):
        content = self.preview_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("안내", "복사할 HTML이 없습니다.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        messagebox.showinfo("복사 완료", "생성된 HTML이 클립보드에 복사되었습니다.")

    def build_em_html_from_aggregated(self, title, version, aggregated_defects):
        rows = list((aggregated_defects or {}).values())
        total = sum(row.get("total", 0) for row in rows)
        open_total = sum(row.get("open", 0) for row in rows)
        progress_total = sum(row.get("in_progress", 0) for row in rows)
        done_total = sum(row.get("done", 0) for row in rows)

        severity_total = {}
        priority_total = {}
        for row in rows:
            for key, count in row.get("severity", {}).items():
                severity_total[key] = severity_total.get(key, 0) + count
            for key, count in row.get("priority", {}).items():
                priority_total[key] = priority_total.get(key, 0) + count

        def pct(value, base):
            return f"{(value / base * 100):.1f}%" if base else "0.0%"

        def top_items(mapping):
            entries = sorted(mapping.items(), key=lambda item: (-item[1], item[0]))
            return ", ".join(f"{html.escape(str(k))} {v}건" for k, v in entries[:3]) or "-"

        max_target = max([row.get("total", 0) for row in rows] or [1])
        target_rows = []
        for row in rows:
            count = row.get("total", 0)
            width = (count / max_target * 100) if max_target else 0
            target_rows.append(f"""
          <tr>
            <td>{html.escape(row.get("target", "미분류"))}</td>
            <td>{count}</td>
            <td>{row.get("open", 0)}</td>
            <td>{row.get("in_progress", 0)}</td>
            <td>{row.get("done", 0)}</td>
            <td>{pct(count, total)}</td>
          </tr>
          <tr class="bar-only">
            <td colspan="6">
              <div class="barbg"><div class="barfill" style="width:{width:.2f}%"></div></div>
            </td>
          </tr>""")

        severity_rows = []
        for key, count in sorted(severity_total.items(), key=lambda item: (-item[1], item[0])):
            severity_rows.append(f"""
          <tr>
            <td>{html.escape(str(key))}</td>
            <td>{count}</td>
            <td>{pct(count, total)}</td>
          </tr>""")

        priority_rows = []
        for key, count in sorted(priority_total.items(), key=lambda item: (-item[1], item[0])):
            priority_rows.append(f"""
          <tr>
            <td>{html.escape(str(key))}</td>
            <td>{count}</td>
            <td>{pct(count, total)}</td>
          </tr>""")

        title_text = f"{title}_{version}" if version else title
        html_str = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(title_text)}</title>
  <style>
    :root{{
      --bg:#ffffff;
      --text:#111827;
      --muted:#6b7280;
      --border:#e5e7eb;
      --card:#ffffff;
      --bar:#111827;
    }}
    *{{ box-sizing:border-box; }}
    body{{
      margin:0;
      background:var(--bg);
      color:var(--text);
      font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    }}
    .wrap{{ max-width:980px; margin:0 auto; padding:18px 16px 22px; }}
    .grid{{ display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start; }}
    .summary{{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:16px; }}
    .card{{
      background:var(--card);
      border:1px solid var(--border);
      border-radius:12px;
      box-shadow:0 2px 10px rgba(0,0,0,0.04);
      padding:14px;
    }}
    .head{{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
    .dot{{ width:6px;height:6px;border-radius:999px;background:var(--text); }}
    .title{{ font-size:13px; font-weight:900; letter-spacing:0.2px; }}
    .sub{{ margin-left:auto; font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums; }}
    .metric-name{{ font-size:11px; color:var(--muted); margin-bottom:6px; }}
    .metric-value{{ font-size:20px; font-weight:900; color:var(--text); }}

    table{{
      width:100%;
      border-collapse:collapse;
      font-size:12px;
      overflow:hidden;
      border-radius:10px;
    }}
    thead th{{
      text-align:left;
      padding:10px 10px;
      background:#f3f4f6;
      border-bottom:1px solid var(--border);
      font-weight:800;
      color:#374151;
    }}
    tbody td{{
      padding:9px 10px;
      border-bottom:1px solid var(--border);
      vertical-align:middle;
    }}
    tbody tr:nth-child(even):not(.bar-only){{ background:#fcfcfd; }}
    tbody tr.total{{ background:#f3f4f6; font-weight:900; }}
    .bar-only td{{ padding:0 10px 9px; border-bottom:1px solid var(--border); }}
    .barbg{{ height:10px; background:#eef2f7; border-radius:999px; overflow:hidden; border:1px solid #e7ebf2; }}
    .barfill{{ height:100%; width:0%; background:var(--bar); border-radius:999px; }}
    .note{{ margin-top:10px; font-size:11px; color:var(--muted); line-height:1.45; }}

    @media (max-width: 900px){{
      .grid{{ grid-template-columns:1fr; }}
      .summary{{ grid-template-columns:1fr 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="summary">
      <section class="card"><div class="metric-name">전체 결함</div><div class="metric-value">{total}</div></section>
      <section class="card"><div class="metric-name">Open</div><div class="metric-value">{open_total}</div></section>
      <section class="card"><div class="metric-name">In Progress</div><div class="metric-value">{progress_total}</div></section>
      <section class="card"><div class="metric-name">Done/Resolved/Closed</div><div class="metric-value">{done_total}</div></section>
    </div>

    <div class="grid">
      <section class="card">
        <div class="head">
          <span class="dot"></span>
          <div class="title">타겟별 결함 현황_{html.escape(version)}</div>
          <div class="sub">총 {total}건</div>
        </div>
        <table aria-label="타겟별 결함 현황 표">
          <thead>
            <tr>
              <th>타겟</th>
              <th>결함 수</th>
              <th>Open</th>
              <th>In Progress</th>
              <th>Done</th>
              <th>비율</th>
            </tr>
          </thead>
          <tbody>
            {''.join(target_rows)}
            <tr class="total"><td>총 합계</td><td>{total}</td><td>{open_total}</td><td>{progress_total}</td><td>{done_total}</td><td>100%</td></tr>
          </tbody>
        </table>
        <div class="note">
          * 정렬 기준: AOS → iOS → Web → Admin → Server → Common → 미분류 → 기타.
        </div>
      </section>

      <section class="card">
        <div class="head">
          <span class="dot"></span>
          <div class="title">심각도 기준_{html.escape(version)}</div>
          <div class="sub">{top_items(severity_total)}</div>
        </div>
        <table aria-label="심각도 표">
          <thead><tr><th>구분</th><th>건수</th><th>비율</th></tr></thead>
          <tbody>
            {''.join(severity_rows)}
            <tr class="total"><td>총 합계</td><td>{total}</td><td>100%</td></tr>
          </tbody>
        </table>
      </section>

      <section class="card">
        <div class="head">
          <span class="dot"></span>
          <div class="title">우선순위 기준_{html.escape(version)}</div>
          <div class="sub">{top_items(priority_total)}</div>
        </div>
        <table aria-label="우선순위 표">
          <thead><tr><th>구분</th><th>건수</th><th>비율</th></tr></thead>
          <tbody>
            {''.join(priority_rows)}
            <tr class="total"><td>총 합계</td><td>{total}</td><td>100%</td></tr>
          </tbody>
        </table>
      </section>
    </div>
  </div>
</body>
</html>"""
        return html_str

    def build_em_html(self, title, version, raw_text):
        rows = self.parse_delimited_rows(raw_text)
        if not rows:
            raise ValueError("EM 데이터가 비어 있습니다.")

        raw_tsv = raw_text

        html_str = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(title)}_{html.escape(version)}</title>
  <style>
    :root{{
      --bg:#ffffff;
      --text:#111827;
      --muted:#6b7280;
      --border:#e5e7eb;
      --card:#ffffff;
      --bar:#111827;
    }}
    *{{ box-sizing:border-box; }}
    body{{
      margin:0;
      background:var(--bg);
      color:var(--text);
      font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    }}
    .wrap{{ max-width:980px; margin:0 auto; padding:18px 16px 22px; }}
    .grid{{ display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start; }}
    .card{{
      background:var(--card);
      border:1px solid var(--border);
      border-radius:12px;
      box-shadow:0 2px 10px rgba(0,0,0,0.04);
      padding:14px;
    }}
    .head{{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
    .dot{{ width:6px;height:6px;border-radius:999px;background:var(--text); }}
    .title{{ font-size:13px; font-weight:900; letter-spacing:0.2px; }}
    .sub{{ margin-left:auto; font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums; }}

    table{{
      width:100%;
      border-collapse:collapse;
      font-size:12px;
      overflow:hidden;
      border-radius:10px;
    }}
    thead th{{
      text-align:left;
      padding:10px 10px;
      background:#f3f4f6;
      border-bottom:1px solid var(--border);
      font-weight:800;
      color:#374151;
    }}
    tbody td{{
      padding:9px 10px;
      border-bottom:1px solid var(--border);
      vertical-align:middle;
    }}
    tbody tr:nth-child(even){{ background:#fcfcfd; }}
    tbody tr.total{{ background:#f3f4f6; font-weight:900; }}

    .barwrap{{ margin-top:10px; display:flex; flex-direction:column; gap:8px; }}
    .barrow{{ display:grid; grid-template-columns:90px 1fr 64px; gap:10px; align-items:center; font-size:12px; }}
    .barname{{ font-weight:800; color:#374151; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .barbg{{ height:10px; background:#eef2f7; border-radius:999px; overflow:hidden; border:1px solid #e7ebf2; }}
    .barfill{{ height:100%; width:0%; background:var(--bar); border-radius:999px; }}
    .barval{{ text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }}

    .hi td{{ color:#ef4444; font-weight:900; }}
    .hi .barfill{{ background:#ef4444; }}

    @media (max-width: 900px){{
      .grid{{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="grid">
      <section class="card">
        <div class="head">
          <span class="dot"></span>
          <div class="title">심각도 기준_{html.escape(version)}</div>
          <div class="sub" id="totalCount1">총 0건</div>
        </div>
        <table aria-label="심각도 표">
          <thead>
            <tr>
              <th style="width:55%">구분</th>
              <th style="width:20%">건수</th>
              <th style="width:25%">비율</th>
            </tr>
          </thead>
          <tbody id="tbodySeverity"></tbody>
        </table>
        <div class="barwrap" id="barsSeverity"></div>
      </section>

      <section class="card">
        <div class="head">
          <span class="dot"></span>
          <div class="title">유형별 기준_{html.escape(version)}</div>
          <div class="sub" id="totalCount2">총 0건</div>
        </div>
        <table aria-label="유형 표">
          <thead>
            <tr>
              <th style="width:55%">구분</th>
              <th style="width:20%">건수</th>
              <th style="width:25%">비율</th>
            </tr>
          </thead>
          <tbody id="tbodyType"></tbody>
        </table>
        <div class="barwrap" id="barsType"></div>
      </section>
    </div>
  </div>

  <script>
    const RAW_TSV = {self.js_str(raw_tsv)};

    function parseTSV(tsv){{
      const lines = tsv.split(/\\r?\\n/).filter(Boolean);
      const header = lines.shift().split("\\t").map(s => s.trim());
      return lines.map(line => {{
        const cols = line.split("\\t");
        const obj = {{}};
        header.forEach((h, i) => obj[h] = (cols[i] ?? "").trim());
        return obj;
      }});
    }}

    function pct(n, total){{
      if(!total) return "0.0%";
      return (Math.round((n / total) * 1000) / 10).toFixed(1) + "%";
    }}

    function aggCount(rows, field){{
      const map = new Map();
      for(const r of rows){{
        const raw = (r[field] ?? "").trim();
        const key = raw || "(빈값)";
        map.set(key, (map.get(key) || 0) + 1);
      }}
      return map;
    }}

    function toEntries(map){{
      const arr = [];
      map.forEach((count, key) => arr.push({{ key, count }}));
      return arr.sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
    }}

    function renderTable(tbodyEl, entries, total){{
      tbodyEl.innerHTML = "";
      const max = entries.reduce((m, e) => Math.max(m, e.count), 0);
      const maxKeys = new Set(entries.filter(e => e.count === max).map(e => e.key));

      for(const e of entries){{
        const tr = document.createElement("tr");
        if(maxKeys.has(e.key)) tr.classList.add("hi");

        const td1 = document.createElement("td");
        td1.textContent = e.key;

        const td2 = document.createElement("td");
        td2.textContent = String(e.count);

        const td3 = document.createElement("td");
        td3.textContent = pct(e.count, total);

        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tbodyEl.appendChild(tr);
      }}

      const trT = document.createElement("tr");
      trT.className = "total";
      trT.innerHTML = `<td>총 합계</td><td>${{total}}</td><td>100%</td>`;
      tbodyEl.appendChild(trT);
    }}

    function renderBars(containerEl, entries, total){{
      containerEl.innerHTML = "";
      const max = entries.reduce((m, e) => Math.max(m, e.count), 0) || 1;
      const maxKeys = new Set(entries.filter(e => e.count === max).map(e => e.key));

      for(const e of entries){{
        const row = document.createElement("div");
        row.className = "barrow";
        if(maxKeys.has(e.key)) row.classList.add("hi");

        const name = document.createElement("div");
        name.className = "barname";
        name.title = e.key;
        name.textContent = e.key;

        const bg = document.createElement("div");
        bg.className = "barbg";

        const fill = document.createElement("div");
        fill.className = "barfill";
        fill.style.width = ((e.count / max) * 100).toFixed(2) + "%";
        bg.appendChild(fill);

        const val = document.createElement("div");
        val.className = "barval";
        val.textContent = `${{e.count}} · ${{pct(e.count, total)}}`;

        row.appendChild(name);
        row.appendChild(bg);
        row.appendChild(val);

        containerEl.appendChild(row);
      }}
    }}

    const rows = parseTSV(RAW_TSV);
    const total = rows.length;

    document.getElementById("totalCount1").textContent = `총 ${{total}}건`;
    document.getElementById("totalCount2").textContent = `총 ${{total}}건`;

    const sevEntries = toEntries(aggCount(rows, "심각도"));
    const typeEntries = toEntries(aggCount(rows, "결함 유형"));

    renderTable(document.getElementById("tbodySeverity"), sevEntries, total);
    renderBars(document.getElementById("barsSeverity"), sevEntries, total);

    renderTable(document.getElementById("tbodyType"), typeEntries, total);
    renderBars(document.getElementById("barsType"), typeEntries, total);
  </script>
</body>
</html>"""
        return html_str

    def build_end_html(self, title):
        total = int(self.end_total_var.get().strip() or 0)
        fixed = int(self.end_fixed_var.get().strip() or 0)
        future = int(self.end_future_var.get().strip() or 0)
        invalid = int(self.end_invalid_var.get().strip() or 0)
        note = self.end_note_var.get().strip()

        def pct(v, t):
            return f"{(v / t * 100):.1f}%" if t else "0.0%"

        html_str = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      padding: 12px;
      font-family: Arial, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
      background: #f5f6f8;
      color: #222;
      font-size: 11px;
    }}

    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    .page-title {{
      margin: 0 0 10px;
      font-size: 13px;
      font-weight: 800;
      line-height: 1.25;
    }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 10px;
    }}

    .summary-card {{
      background: #fff;
      border: 1px solid #e4e7ec;
      border-radius: 10px;
      padding: 10px 12px;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.035);
      min-height: 44px;
      display: flex;
      align-items: center;
      justify-content: flex-start;
    }}

    .summary-card strong {{
      font-size: 11px;
      line-height: 1.35;
      font-weight: 700;
    }}

    .chart-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 10px;
      align-items: start;
    }}

    .panel {{
      background: #fff;
      border: 1px solid #e4e7ec;
      border-radius: 12px;
      padding: 14px;
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.035);
      margin-bottom: 0;
    }}

    .panel h2,
    .panel h3 {{
      margin: 0 0 8px;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.25;
    }}

    .chart-box {{
      position: relative;
      width: 100%;
      height: 170px;
    }}

    .chart-box.donut {{
      height: 180px;
    }}

    .desc-box {{
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid #eef1f4;
    }}

    .desc-box p {{
      margin: 0 0 6px;
      font-size: 10px;
      line-height: 1.45;
      font-weight: 700;
    }}

    .desc-box ul {{
      margin: 0;
      padding-left: 14px;
    }}

    .desc-box li {{
      margin-bottom: 3px;
      font-size: 10px;
      line-height: 1.35;
    }}

    .note {{
      margin-top: 6px;
      font-size: 10px;
      color: #667085;
      line-height: 1.35;
    }}

    @media (max-width: 768px) {{
      body {{
        padding: 10px;
      }}

      .summary-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}

      .chart-grid {{
        grid-template-columns: 1fr;
      }}

      .panel {{
        padding: 12px;
      }}

      .chart-box {{
        height: 150px;
      }}

      .chart-box.donut {{
        height: 160px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="page-title">{html.escape(title)}</h1>

    <div class="summary-grid">
      <div class="summary-card">
        <strong>전체: {total}건</strong>
      </div>
      <div class="summary-card">
        <strong>수정 정상 반영: {fixed}건 ({pct(fixed, total)})</strong>
      </div>
      <div class="summary-card">
        <strong>추후 수정: {future}건 ({pct(future, total)})</strong>
      </div>
      <div class="summary-card">
        <strong>결함아님: {invalid}건 ({pct(invalid, total)})</strong>
      </div>
    </div>

    <div class="chart-grid">
      <div class="panel">
        <h2>막대 그래프</h2>
        <div class="chart-box">
          <canvas id="barChart"></canvas>
        </div>
      </div>

      <div class="panel">
        <h2>비율</h2>
        <div class="chart-box donut">
          <canvas id="doughnutChart"></canvas>
        </div>

        <div class="desc-box">
          <p>
            총 <strong>{total}건</strong> 중
            <strong>{fixed}건({pct(fixed, total)})</strong> 수정 정상 반영,
            <strong>{future}건</strong> 추후 수정,
            <strong>{invalid}건</strong> 결함아님
          </p>
          <div class="note">
            {html.escape(note)}
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const totalCount = {total};
    const fixedCount = {fixed};
    const futureCount = {future};
    const invalidCount = {invalid};

    const commonLegend = {{
      labels: {{
        font: {{
          size: 10,
          family: 'Arial, Apple SD Gothic Neo, Noto Sans KR, sans-serif'
        }},
        color: '#222',
        padding: 8
      }}
    }};

    new Chart(document.getElementById('barChart'), {{
      type: 'bar',
      data: {{
        labels: ['수정 정상 반영', '추후 수정', '결함아님'],
        datasets: [{{
          label: '건수',
          data: [fixedCount, futureCount, invalidCount],
          backgroundColor: ['#3FA9F5', '#FF5C8A', '#21C87A'],
          borderRadius: 5,
          borderSkipped: false
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: 'y',
        plugins: {{
          legend: {{
            position: 'bottom',
            ...commonLegend
          }},
          tooltip: {{
            titleFont: {{
              size: 10
            }},
            bodyFont: {{
              size: 10
            }},
            callbacks: {{
              label: function(context) {{
                const value = context.raw;
                const percent = ((value / totalCount) * 100).toFixed(1);
                return `${{context.label}}: ${{value}}건 (${{percent}}%)`;
              }}
            }}
          }}
        }},
        scales: {{
          x: {{
            beginAtZero: true,
            ticks: {{
              stepSize: 5,
              color: '#444',
              font: {{
                size: 10
              }}
            }},
            grid: {{
              color: '#e5e7eb'
            }}
          }},
          y: {{
            ticks: {{
              color: '#222',
              font: {{
                size: 10,
                weight: '700'
              }}
            }},
            grid: {{
              color: '#e5e7eb'
            }}
          }}
        }}
      }}
    }});

    new Chart(document.getElementById('doughnutChart'), {{
      type: 'doughnut',
      data: {{
        labels: ['수정 정상 반영', '추후 수정', '결함아님'],
        datasets: [{{
          data: [fixedCount, futureCount, invalidCount],
          backgroundColor: ['#3FA9F5', '#FF5C8A', '#21C87A'],
          borderColor: '#ffffff',
          borderWidth: 2,
          hoverOffset: 4
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        cutout: '62%',
        plugins: {{
          legend: {{
            position: 'bottom',
            ...commonLegend
          }},
          tooltip: {{
            titleFont: {{
              size: 10
            }},
            bodyFont: {{
              size: 10
            }},
            callbacks: {{
              label: function(context) {{
                const value = context.raw;
                const percent = ((value / totalCount) * 100).toFixed(1);
                return `${{context.label}}: ${{value}}건 (${{percent}}%)`;
              }}
            }}
          }}
        }}
      }},
      plugins: [{{
        id: 'centerText',
        beforeDraw(chart) {{
          const {{ width, height, ctx }} = chart;
          ctx.save();

          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';

          ctx.font = '700 10px Arial';
          ctx.fillStyle = '#666';
          ctx.fillText('전체', width / 2, height / 2 - 9);

          ctx.font = '800 16px Arial';
          ctx.fillStyle = '#111';
          ctx.fillText(`${{totalCount}}건`, width / 2, height / 2 + 10);

          ctx.restore();
        }}
      }}]
    }});
  </script>
</body>
</html>"""
        return html_str

    def build_fea_html(self, title, version, raw_text):
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            raise ValueError("FEA 데이터가 비어 있습니다.")

        raw_lines = "\n".join(lines)

        html_str = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(title)}_{html.escape(version)}</title>
  <style>
    :root{{
      --bg:#ffffff;
      --text:#111827;
      --muted:#6b7280;
      --border:#e5e7eb;
      --card:#ffffff;
      --bar:#111827;
    }}
    *{{ box-sizing:border-box; }}
    body{{
      margin:0;
      background:var(--bg);
      color:var(--text);
      font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    }}
    .wrap{{ max-width:980px; margin:0 auto; padding:18px 16px 22px; }}
    .card{{
      background:var(--card);
      border:1px solid var(--border);
      border-radius:12px;
      box-shadow:0 2px 10px rgba(0,0,0,0.04);
      padding:14px;
    }}
    .head{{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
    .dot{{ width:6px;height:6px;border-radius:999px;background:var(--text); }}
    .title{{ font-size:13px; font-weight:900; letter-spacing:0.2px; }}
    .sub{{
      margin-left:auto;
      font-size:12px;
      color:var(--muted);
      font-variant-numeric:tabular-nums;
    }}

    table{{
      width:100%;
      border-collapse:collapse;
      font-size:12px;
      overflow:hidden;
      border-radius:10px;
    }}
    thead th{{
      text-align:left;
      padding:10px 10px;
      background:#f3f4f6;
      border-bottom:1px solid var(--border);
      font-weight:800;
      color:#374151;
    }}
    tbody td{{
      padding:9px 10px;
      border-bottom:1px solid var(--border);
      vertical-align:middle;
    }}
    tbody tr:nth-child(even){{ background:#fcfcfd; }}
    tbody tr.total{{ background:#f3f4f6; font-weight:900; }}

    .barwrap{{ margin-top:10px; display:flex; flex-direction:column; gap:8px; }}
    .barrow{{ display:grid; grid-template-columns:90px 1fr 64px; gap:10px; align-items:center; font-size:12px; }}
    .barname{{ font-weight:800; color:#374151; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
    .barbg{{ height:10px; background:#eef2f7; border-radius:999px; overflow:hidden; border:1px solid #e7ebf2; }}
    .barfill{{ height:100%; width:0%; background:var(--bar); border-radius:999px; }}
    .barval{{ text-align:right; color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }}

    .hi td{{ color:#ef4444; font-weight:900; }}
    .hi .barfill{{ background:#ef4444; }}

    .note{{
      margin-top:10px;
      font-size:11px;
      color:var(--muted);
      line-height:1.45;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="card">
      <div class="head">
        <span class="dot"></span>
        <div class="title">{html.escape(title)}_{html.escape(version)}</div>
        <div class="sub" id="totalCount">총 0건</div>
      </div>

      <table aria-label="피처 표">
        <thead>
          <tr>
            <th>구분</th>
            <th style="width:90px">건수</th>
            <th style="width:90px">비율</th>
          </tr>
        </thead>
        <tbody id="tbodyFeature"></tbody>
      </table>

      <div class="barwrap" id="barsFeature"></div>

      <div class="note">
        * 집계 기준: ATM 항목의 전체 텍스트 기준으로 집계됩니다.<br/>
        * 표는 건수 내림차순으로 정렬됩니다.
      </div>
    </section>
  </div>

  <script>
    const RAW_LINES = {self.js_str(raw_lines)};

    function pct(n, total){{
      if(!total) return "0.0%";
      return (Math.round((n/total)*1000)/10).toFixed(1) + "%";
    }}

    function extractFeature(line){{
      const text = (line || "").trim();
      return text || "비어있음";
    }}

    function aggFeature(lines){{
      const map = new Map();
      for(const line of lines){{
        const key = extractFeature(line);
        map.set(key, (map.get(key) || 0) + 1);
      }}
      return map;
    }}

    function toEntries(map){{
      const arr = [];
      map.forEach((count, key) => arr.push({{ key, count }}));
      return arr.sort((a,b)=> b.count - a.count || a.key.localeCompare(b.key));
    }}

    function renderTable(tbodyEl, entries, total){{
      tbodyEl.innerHTML = "";
      const max = entries.reduce((m,e)=> Math.max(m, e.count), 0);
      const maxKeys = new Set(entries.filter(e=>e.count===max).map(e=>e.key));

      for(const e of entries){{
        const tr = document.createElement("tr");
        if(maxKeys.has(e.key)) tr.classList.add("hi");

        const td1 = document.createElement("td");
        td1.textContent = e.key;

        const td2 = document.createElement("td");
        td2.textContent = String(e.count);

        const td3 = document.createElement("td");
        td3.textContent = pct(e.count, total);

        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tbodyEl.appendChild(tr);
      }}

      const trT = document.createElement("tr");
      trT.className = "total";
      trT.innerHTML = `<td>총 합계</td><td>${{total}}</td><td>100%</td>`;
      tbodyEl.appendChild(trT);
    }}

    function renderBars(containerEl, entries, total){{
      containerEl.innerHTML = "";
      const max = entries.reduce((m,e)=> Math.max(m, e.count), 0) || 1;
      const maxKeys = new Set(entries.filter(e=>e.count===max).map(e=>e.key));

      for(const e of entries){{
        const row = document.createElement("div");
        row.className = "barrow";
        if(maxKeys.has(e.key)) row.classList.add("hi");

        const name = document.createElement("div");
        name.className = "barname";
        name.title = e.key;
        name.textContent = e.key;

        const bg = document.createElement("div");
        bg.className = "barbg";

        const fill = document.createElement("div");
        fill.className = "barfill";
        fill.style.width = ((e.count / max) * 100).toFixed(2) + "%";
        bg.appendChild(fill);

        const val = document.createElement("div");
        val.className = "barval";
        val.textContent = `${{e.count}} · ${{pct(e.count, total)}}`;

        row.appendChild(name);
        row.appendChild(bg);
        row.appendChild(val);

        containerEl.appendChild(row);
      }}
    }}

    const lines = RAW_LINES.split(/\\r?\\n/).map(s => s.trim()).filter(Boolean);
    const total = lines.length;

    document.getElementById("totalCount").textContent = `총 ${{total}}건`;

    const featEntries = toEntries(aggFeature(lines));
    renderTable(document.getElementById("tbodyFeature"), featEntries, total);
    renderBars(document.getElementById("barsFeature"), featEntries, total);
  </script>
</body>
</html>"""
        return html_str

    def build_tc_html_from_aggregated(self, title, version, aggregated_data):
        detected_os_names = set()
        for os_map in (aggregated_data or {}).values():
            for os_name in os_map.keys():
                detected_os_names.add(_canonical_os(os_name))

        totals = {
            "AOS": {"PASS": 0, "FAIL": 0, "NA": 0},
            "iOS": {"PASS": 0, "FAIL": 0, "NA": 0},
        }
        for os_map in (aggregated_data or {}).values():
            for os_name, counts in os_map.items():
                canonical = _canonical_os(os_name)
                if canonical not in totals:
                    continue
                for key in RESULT_KEYS:
                    totals[canonical][key] += int(counts.get(key, 0) or 0)

        if detected_os_names.issubset({"AOS", "iOS"}):
            return self.build_tc_html_from_counts(
                title,
                version,
                totals["AOS"]["PASS"],
                totals["AOS"]["FAIL"],
                totals["AOS"]["NA"],
                totals["iOS"]["PASS"],
                totals["iOS"]["FAIL"],
                totals["iOS"]["NA"],
            )

        def empty_counts():
            return {key: 0 for key in RESULT_KEYS}

        normalized_pages = {}
        total_by_os = {}
        for page_name, os_map in (aggregated_data or {}).items():
            normalized_pages[page_name] = {}
            for os_name, counts in os_map.items():
                current = empty_counts()
                for key in RESULT_KEYS:
                    current[key] = int(counts.get(key, 0) or 0)
                current["TOTAL"] = sum(current[key] for key in RESULT_KEYS)
                for key in RESULT_KEYS:
                    current[f"{key}_RATE"] = round((current[key] / current["TOTAL"] * 100), 1) if current["TOTAL"] else 0.0
                normalized_pages[page_name][os_name] = current

                total_bucket = total_by_os.setdefault(os_name, empty_counts())
                for key in RESULT_KEYS:
                    total_bucket[key] += current[key]

        overall = {"전체": {}}
        for os_name, counts in total_by_os.items():
            total = sum(counts.values())
            overall["전체"][os_name] = {
                "PASS": counts["PASS"],
                "FAIL": counts["FAIL"],
                "NA": counts["NA"],
                "TOTAL": total,
                "PASS_RATE": round((counts["PASS"] / total * 100), 1) if total else 0.0,
                "FAIL_RATE": round((counts["FAIL"] / total * 100), 1) if total else 0.0,
                "NA_RATE": round((counts["NA"] / total * 100), 1) if total else 0.0,
            }

        # TC embed output should stay compact. Unknown OS/result-only rows are
        # exposed in the summary as "미분류" instead of expanding every TC page.
        report_data = {"overall": overall, "pages": {}}
        data_json = json.dumps(report_data, ensure_ascii=False)
        title_text = f"{title}_{version}" if version else title

        html_str = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title_text)}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      padding: 24px;
      font-family: Arial, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
      background: #f5f6f8;
      color: #222;
      font-size: 12px;
    }}

    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    .title {{
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 24px 0;
      color: #1f2937;
    }}

    .section-title {{
      margin: 8px 0 12px;
      font-size: 14px;
      font-weight: 800;
      color: #1f2937;
    }}

    .card-wrap {{
      display: flex;
      flex-direction: column;
      gap: 24px;
      margin-bottom: 28px;
    }}

    .card {{
      width: 100%;
      background: #fff;
      border: 1px solid #d9dde3;
      border-radius: 18px;
      padding: 20px 20px 18px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.04);
      min-height: 360px;
    }}

    .card-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}

    .os-name {{
      font-size: 16px;
      font-weight: 700;
      color: #111827;
    }}

    .sum {{
      font-size: 12px;
      color: #6b7280;
      white-space: nowrap;
    }}

    .sum b {{
      color: #4b5563;
      font-weight: 700;
    }}

    .content {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 28px;
      padding-top: 8px;
    }}

    .chart-box {{
      width: 240px;
      height: 240px;
      position: relative;
    }}

    .legend {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 180px;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      color: #1f2937;
    }}

    .count {{
      color: #6b7280;
      font-weight: 600;
      margin-left: 2px;
    }}

    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
      flex: 0 0 10px;
    }}

    .pass {{ background: #0b7285; }}
    .fail {{ background: #e03131; }}
    .na {{ background: #f08c00; }}

    table {{
      width: 100%;
      margin-top: 18px;
      border-collapse: collapse;
      font-size: 12px;
    }}

    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid #e5e7eb;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}

    th:first-child, td:first-child {{
      text-align: left;
      font-weight: 700;
    }}

    thead th {{
      background: #f3f4f6;
      color: #374151;
      font-weight: 800;
    }}

    @media (max-width: 900px) {{
      .content {{
        flex-direction: column;
      }}

      .legend {{
        min-width: auto;
        width: 100%;
        align-items: center;
      }}

      .title {{
        font-size: 16px;
      }}

      .os-name,
      .sum,
      .legend-item {{
        font-size: 12px;
      }}

      .chart-box {{
        width: 220px;
        height: 220px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="title">{html.escape(title_text)}</h1>
    <div id="reportRoot"></div>
  </div>

  <script>
    const report = {data_json};
    const colors = {{ PASS: '#0b7285', FAIL: '#e03131', NA: '#f08c00' }};

    const centerTextPlugin = {{
      id: 'centerTextPlugin',
      afterDatasetsDraw(chart) {{
        const {{ ctx }} = chart;
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data || !meta.data.length) return;

        const total = chart.data.datasets[0].data.reduce((a, b) => a + b, 0);
        if (!total) return;

        meta.data.forEach((arc, index) => {{
          const value = chart.data.datasets[0].data[index];
          if (!value) return;

          const percent = Math.round((value / total) * 100);
          const angle = (arc.startAngle + arc.endAngle) / 2;
          const radius = (arc.outerRadius + arc.innerRadius) / 2;
          const x = arc.x + Math.cos(angle) * radius;
          const y = arc.y + Math.sin(angle) * radius;

          ctx.save();
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 10px Arial';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(percent + '%', x, y);
          ctx.restore();
        }});
      }}
    }};

    function pct(value, total) {{
      if (!total) return '0.0%';
      return (Math.round((value / total) * 1000) / 10).toFixed(1) + '%';
    }}

    function makeId(prefix) {{
      return prefix + '_' + Math.random().toString(36).slice(2);
    }}

    function renderSection(container, sectionTitle, osMap) {{
      const h2 = document.createElement('h2');
      h2.className = 'section-title';
      h2.textContent = sectionTitle;
      container.appendChild(h2);

      const wrap = document.createElement('div');
      wrap.className = 'card-wrap';
      container.appendChild(wrap);

      Object.entries(osMap).forEach(([osName, counts]) => {{
        const total = counts.TOTAL || counts.PASS + counts.FAIL + counts.NA;
        const canvasId = makeId('chart');

        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
          <div class="card-head">
            <div class="os-name">${{osName}}</div>
            <div class="sum">SUM <b>${{total}}</b></div>
          </div>
          <div class="content">
            <div class="chart-box"><canvas id="${{canvasId}}"></canvas></div>
            <div class="legend">
              <div class="legend-item"><span class="dot pass"></span>PASS <span class="count">${{counts.PASS}}건 · ${{pct(counts.PASS, total)}}</span></div>
              <div class="legend-item"><span class="dot fail"></span>FAIL <span class="count">${{counts.FAIL}}건 · ${{pct(counts.FAIL, total)}}</span></div>
              <div class="legend-item"><span class="dot na"></span>NA <span class="count">${{counts.NA}}건 · ${{pct(counts.NA, total)}}</span></div>
            </div>
          </div>
          <table aria-label="${{sectionTitle}} ${{osName}} 결과 표">
            <thead>
              <tr><th>구분</th><th>건수</th><th>비율</th></tr>
            </thead>
            <tbody>
              <tr><td>PASS</td><td>${{counts.PASS}}</td><td>${{pct(counts.PASS, total)}}</td></tr>
              <tr><td>FAIL</td><td>${{counts.FAIL}}</td><td>${{pct(counts.FAIL, total)}}</td></tr>
              <tr><td>NA</td><td>${{counts.NA}}</td><td>${{pct(counts.NA, total)}}</td></tr>
              <tr><td>전체</td><td>${{total}}</td><td>100%</td></tr>
            </tbody>
          </table>`;
        wrap.appendChild(card);

        new Chart(document.getElementById(canvasId), {{
          type: 'pie',
          data: {{
            labels: ['PASS', 'FAIL', 'NA'],
            datasets: [{{
              data: [counts.PASS, counts.FAIL, counts.NA],
              backgroundColor: [colors.PASS, colors.FAIL, colors.NA],
              borderColor: '#ffffff',
              borderWidth: 2,
              hoverOffset: 6
            }}]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            animation: {{ duration: 0 }},
            plugins: {{
              legend: {{ display: false }},
              tooltip: {{
                callbacks: {{
                  label(context) {{
                    const value = context.raw;
                    return `${{context.label}}: ${{value}}건 (${{pct(value, total)}})`;
                  }}
                }}
              }}
            }}
          }},
          plugins: [centerTextPlugin]
        }});
      }});
    }}

    const root = document.getElementById('reportRoot');
    renderSection(root, '요약', report.overall['전체'] || {{}});
    Object.entries(report.pages).forEach(([pageName, osMap]) => renderSection(root, pageName, osMap));
  </script>
</body>
</html>"""
        return html_str

    def build_tc_html_from_counts(self, title, version, aos_pass, aos_fail, aos_na, ios_pass, ios_fail, ios_na):
        title_text = title
        if version and not title.endswith(f"_{version}"):
            title_text = f"{title}_{version}"
        html_str = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title_text)}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      padding: 24px;
      font-family: Arial, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
      background: #f5f6f8;
      color: #222;
      font-size: 12px;
    }}

    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    .title {{
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 24px 0;
      color: #1f2937;
    }}

    .card-wrap {{
      display: flex;
      flex-direction: column;
      gap: 24px;
    }}

    .card {{
      width: 100%;
      background: #fff;
      border: 1px solid #d9dde3;
      border-radius: 18px;
      padding: 20px 20px 18px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.04);
      min-height: 360px;
    }}

    .card-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }}

    .os-name {{
      font-size: 16px;
      font-weight: 700;
      color: #111827;
    }}

    .sum {{
      font-size: 12px;
      color: #6b7280;
    }}

    .sum b {{
      color: #4b5563;
      font-weight: 700;
    }}

    .content {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 28px;
      padding-top: 8px;
    }}

    .chart-box {{
      width: 240px;
      height: 240px;
      position: relative;
    }}

    .legend {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 150px;
    }}

    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
      color: #1f2937;
    }}

    .count {{
      color: #6b7280;
      font-weight: 600;
      margin-left: 2px;
    }}

    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      display: inline-block;
      flex: 0 0 10px;
    }}

    .pass {{ background: #0b7285; }}
    .fail {{ background: #e03131; }}
    .na {{ background: #f08c00; }}

    @media (max-width: 900px) {{
      .content {{
        flex-direction: column;
      }}

      .legend {{
        min-width: auto;
        width: 100%;
        align-items: center;
      }}

      .title {{
        font-size: 16px;
      }}

      .os-name,
      .sum,
      .legend-item {{
        font-size: 12px;
      }}

      .chart-box {{
        width: 220px;
        height: 220px;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1 class="title">{html.escape(title_text)}</h1>

    <div class="card-wrap">
      <div class="card">
        <div class="card-head">
          <div class="os-name">AOS</div>
          <div class="sum">SUM <b id="aosSum"></b></div>
        </div>
        <div class="content">
          <div class="chart-box">
            <canvas id="aosChart"></canvas>
          </div>
          <div class="legend">
            <div class="legend-item"><span class="dot pass"></span>PASS <span class="count" id="aosPass"></span></div>
            <div class="legend-item"><span class="dot fail"></span>FAIL <span class="count" id="aosFail"></span></div>
            <div class="legend-item"><span class="dot na"></span>NA <span class="count" id="aosNa"></span></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div class="os-name">iOS</div>
          <div class="sum">SUM <b id="iosSum"></b></div>
        </div>
        <div class="content">
          <div class="chart-box">
            <canvas id="iosChart"></canvas>
          </div>
          <div class="legend">
            <div class="legend-item"><span class="dot pass"></span>PASS <span class="count" id="iosPass"></span></div>
            <div class="legend-item"><span class="dot fail"></span>FAIL <span class="count" id="iosFail"></span></div>
            <div class="legend-item"><span class="dot na"></span>NA <span class="count" id="iosNa"></span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const data = {{
      AOS: {{ PASS: {aos_pass}, FAIL: {aos_fail}, NA: {aos_na} }},
      IOS: {{ PASS: {ios_pass}, FAIL: {ios_fail}, NA: {ios_na} }}
    }};

    data.AOS.sum = data.AOS.PASS + data.AOS.FAIL + data.AOS.NA;
    data.IOS.sum = data.IOS.PASS + data.IOS.FAIL + data.IOS.NA;

    document.getElementById('aosSum').innerText = data.AOS.sum;
    document.getElementById('iosSum').innerText = data.IOS.sum;

    document.getElementById('aosPass').innerText = data.AOS.PASS;
    document.getElementById('aosFail').innerText = data.AOS.FAIL;
    document.getElementById('aosNa').innerText = data.AOS.NA;

    document.getElementById('iosPass').innerText = data.IOS.PASS;
    document.getElementById('iosFail').innerText = data.IOS.FAIL;
    document.getElementById('iosNa').innerText = data.IOS.NA;

    const centerTextPlugin = {{
      id: 'centerTextPlugin',
      afterDatasetsDraw(chart) {{
        const {{ ctx }} = chart;
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data || !meta.data.length) return;

        const total = chart.data.datasets[0].data.reduce((a, b) => a + b, 0);

        meta.data.forEach((arc, index) => {{
          const value = chart.data.datasets[0].data[index];
          if (!value) return;

          const percent = Math.round((value / total) * 100);
          const angle = (arc.startAngle + arc.endAngle) / 2;
          const radius = (arc.outerRadius + arc.innerRadius) / 2;
          const x = arc.x + Math.cos(angle) * radius;
          const y = arc.y + Math.sin(angle) * radius;

          ctx.save();
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 10px Arial';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(percent + '%', x, y);
          ctx.restore();
        }});
      }}
    }};

    function createPieChart(canvasId, osKey) {{
      const ctx = document.getElementById(canvasId);
      const chartData = data[osKey];

      return new Chart(ctx, {{
        type: 'pie',
        data: {{
          labels: ['PASS', 'FAIL', 'NA'],
          datasets: [{{
            data: [chartData.PASS, chartData.FAIL, chartData.NA],
            backgroundColor: ['#0b7285', '#e03131', '#f08c00'],
            borderColor: '#ffffff',
            borderWidth: 2,
            hoverOffset: 6
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          animation: {{
            duration: 0
          }},
          plugins: {{
            legend: {{
              display: false
            }},
            tooltip: {{
              callbacks: {{
                label: function(context) {{
                  const total = context.dataset.data.reduce((a, b) => a + b, 0);
                  const value = context.raw;
                  const percent = Math.round((value / total) * 100);
                  return `${{context.label}}: ${{value}}건 (${{percent}}%)`;
                }}
              }}
            }}
          }}
        }},
        plugins: [centerTextPlugin]
      }});
    }}

    createPieChart('aosChart', 'AOS');
    createPieChart('iosChart', 'IOS');
  </script>
</body>
</html>"""
        return html_str

    def build_tc_html(self, title, version):
        aos_pass = int(self.tc_aos_pass_var.get().strip() or 0)
        aos_fail = int(self.tc_aos_fail_var.get().strip() or 0)
        aos_na = int(self.tc_aos_na_var.get().strip() or 0)

        ios_pass = int(self.tc_ios_pass_var.get().strip() or 0)
        ios_fail = int(self.tc_ios_fail_var.get().strip() or 0)
        ios_na = int(self.tc_ios_na_var.get().strip() or 0)

        return self.build_tc_html_from_counts(
            title, version, aos_pass, aos_fail, aos_na, ios_pass, ios_fail, ios_na
        )


if __name__ == "__main__":
    if tk is None:
        raise SystemExit("tkinter가 설치되어 있지 않아 GUI를 실행할 수 없습니다. 웹 서버에서는 app.py를 실행하세요.")
    print("GUI starting...")
    root = tk.Tk()
    print("Tk created")
    app = NotionHtmlGeneratorGUI(root)
    print("App initialized")
    root.mainloop()
    print("GUI closed")
