#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
TARGET_DB_URL_DEFAULT = "https://app.notion.com/p/39673fbd1951801baa4dea29b16a155a?v=39673fbd19518011b206000c9f5cdcfb&source=copy_link"
NOTION_VERSION = "2022-06-28"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


class UserFacingError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def load_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env()


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        raise UserFacingError("요청 형식이 올바르지 않습니다.", 400)


def require_env(name, label):
    value = os.environ.get(name, "").strip()
    if not value:
        raise UserFacingError(f"{label} 환경변수가 설정되어 있지 않습니다.", 500)
    return value


def extract_notion_id(url):
    if not url or not url.strip():
        raise UserFacingError("노션 링크를 입력해 주세요.", 400)
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.netloc.lower()
    if "notion." not in host and "notion.site" not in host:
        raise UserFacingError("올바른 노션 링크를 입력해 주세요.", 400)

    candidates = re.findall(r"(?i)([0-9a-f]{32})", parsed.path + parsed.query)
    if not candidates:
        candidates = re.findall(
            r"(?i)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            parsed.path + parsed.query,
        )
    if not candidates:
        raise UserFacingError("노션 페이지 ID를 링크에서 찾을 수 없습니다.", 400)
    return normalize_uuid(candidates[-1])


def normalize_uuid(value):
    compact = value.replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", compact):
        raise UserFacingError("노션 ID 형식이 올바르지 않습니다.", 400)
    return f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:32]}"


def notion_request(method, path, payload=None):
    token = require_env("NOTION_TOKEN", "NOTION_TOKEN")
    url = f"https://api.notion.com/v1{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"[Notion API] {method} {path} failed: {exc.code} {detail}", file=sys.stderr)
        if exc.code in (401, 403):
            raise UserFacingError("노션 접근 권한이 없습니다. Integration 연결과 토큰 권한을 확인해 주세요.", 502)
        if exc.code == 404:
            raise UserFacingError("노션 페이지 또는 DB를 찾을 수 없습니다. 링크와 Integration 공유 여부를 확인해 주세요.", 404)
        raise UserFacingError("노션 API 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.", 502)
    except urllib.error.URLError as exc:
        print(f"[Notion API] network error: {exc}", file=sys.stderr)
        raise UserFacingError("노션 API에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.", 502)


def rich_text_plain(items):
    return "".join(item.get("plain_text", "") for item in items or [])


def property_to_text(prop):
    kind = prop.get("type")
    if kind == "title":
        return rich_text_plain(prop.get("title"))
    if kind == "rich_text":
        return rich_text_plain(prop.get("rich_text"))
    if kind == "select":
        return (prop.get("select") or {}).get("name", "")
    if kind == "multi_select":
        return ", ".join(item.get("name", "") for item in prop.get("multi_select", []))
    if kind == "status":
        return (prop.get("status") or {}).get("name", "")
    if kind == "date":
        date = prop.get("date") or {}
        return date.get("start", "")
    if kind == "url":
        return prop.get("url") or ""
    if kind == "number":
        return "" if prop.get("number") is None else str(prop.get("number"))
    if kind == "checkbox":
        return "true" if prop.get("checkbox") else "false"
    if kind == "people":
        return ", ".join(person.get("name", "") for person in prop.get("people", []))
    return ""


def block_to_text(block):
    kind = block.get("type")
    if not kind or kind not in block:
        return ""
    data = block[kind]
    if kind in {"paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "to_do", "quote", "callout"}:
        text = rich_text_plain(data.get("rich_text"))
        if kind == "heading_1":
            return f"# {text}"
        if kind == "heading_2":
            return f"## {text}"
        if kind == "heading_3":
            return f"### {text}"
        if kind == "bulleted_list_item":
            return f"- {text}"
        if kind == "numbered_list_item":
            return f"1. {text}"
        if kind == "to_do":
            return f"[{'x' if data.get('checked') else ' '}] {text}"
        if kind == "quote":
            return f"> {text}"
        return text
    if kind == "code":
        language = data.get("language", "")
        return f"```{language}\n{rich_text_plain(data.get('rich_text'))}\n```"
    if kind == "child_page":
        return data.get("title", "")
    if kind == "child_database":
        return data.get("title", "")
    if kind == "table_row":
        cells = [rich_text_plain(cell) for cell in data.get("cells", [])]
        return " | ".join(cells)
    return ""


def get_page_title(page):
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            title = rich_text_plain(prop.get("title"))
            if title:
                return title
    return "노션 티켓 요약"


def collect_blocks(block_id, depth=0):
    if depth > 8:
        return []
    results = []
    cursor = None
    while True:
        qs = f"?page_size=100"
        if cursor:
            qs += f"&start_cursor={urllib.parse.quote(cursor)}"
        data = notion_request("GET", f"/blocks/{block_id}/children{qs}")
        for block in data.get("results", []):
            text = block_to_text(block)
            if text:
                results.append(text)
            if block.get("has_children"):
                results.extend(collect_blocks(block["id"], depth + 1))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results


def fetch_ticket(url):
    page_id = extract_notion_id(url)
    page = notion_request("GET", f"/pages/{page_id}")
    title = get_page_title(page)
    property_lines = []
    for name, prop in page.get("properties", {}).items():
        text = property_to_text(prop)
        if text:
            property_lines.append(f"{name}: {text}")
    block_lines = collect_blocks(page_id)
    combined = "\n".join(property_lines + block_lines).strip()
    if not combined:
        raise UserFacingError("노션 본문이 비어 있어 분석할 수 없습니다.", 400)
    return {"page_id": page_id, "title": title, "content": combined}


def gemini_request(prompt, max_tokens=4096):
    api_key = require_env("GEMINI_API_KEY", "GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": max_tokens,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ],
    }
    last_error = None
    for attempt in range(3):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "\n".join(part.get("text", "") for part in parts).strip()
            if not text:
                print(f"[Gemini] empty response: {json.dumps(data, ensure_ascii=False)[:2000]}", file=sys.stderr)
                raise UserFacingError("Gemini 응답이 비어 있습니다. 다시 시도해 주세요.", 502)
            return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"[Gemini] HTTP {exc.code}: {detail}", file=sys.stderr)
            last_error = exc
            if exc.code in (400, 401, 403):
                raise UserFacingError("Gemini API Key 또는 모델 설정을 확인해 주세요.", 502)
            if exc.code == 429:
                raise UserFacingError("Gemini API 쿼터가 초과되었습니다. 잠시 후 다시 시도해 주세요.", 429)
        except urllib.error.URLError as exc:
            print(f"[Gemini] network error: {exc}", file=sys.stderr)
            last_error = exc
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    print(f"[Gemini] final failure: {last_error}", file=sys.stderr)
    raise UserFacingError("Gemini 응답 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.", 502)


def build_summary_prompt(title, content):
    return f"""
너는 시니어 QA와 서비스 기획 리뷰어다. 기획서가 부족한 노션 티켓을 읽고 QA가 바로 이해할 수 있게 분석 요약을 작성한다.

반드시 아래 Markdown 형식만 출력한다. 코드블록, 머리말, 부연 설명은 금지한다.

<aside>

**작업 내용 요약**

**목적**

- 해당 작업의 목적을 요약

**현상**

- 현재 발생 중인 문제 또는 기존 동작 요약

**개선 사항**

- 변경/개선되어야 하는 정책, 화면, 기능 요약

**검증 포인트**

- QA 관점에서 반드시 확인해야 할 항목 나열

**배경**

- 해당 작업이 필요한 사유 및 정책적 배경 요약

</aside>

각 섹션은 티켓 근거가 부족하면 "티켓 내 명시 없음"이라고 적고, 추정은 "추정:"으로 표시한다.

[티켓 제목]
{title}

[티켓 내용]
{content[:28000]}
""".strip()


def build_tc_prompt(title, summary, source_content):
    return f"""
너는 시니어 QA 리드다. 아래 티켓 요약을 기반으로 실제 실행 가능한 테스트 케이스를 작성한다.

규칙:
- Markdown Table 형식만 출력한다.
- 표 밖의 설명, 코드블록, 인사말은 금지한다.
- 하나의 TC에는 하나의 검증 목적만 포함한다.
- 정책, 예외, 데이터 정합성, 권한, 회귀 영향까지 고려한다.
- AOS / iOS / Comment 컬럼은 제목만 유지하고 각 행의 내용은 공란으로 둔다.
- Priority는 P1, P2, P3 중 하나만 사용한다.
- Type은 Functional, UI, UX, Negative, Boundary, Accessibility, Localization, Responsive 중 하나만 사용한다.

반드시 이 헤더를 사용한다:
| TC-ID | Priority | Type | Screen | Preconditions | Test Case | Description | Expected Result | AOS | iOS | Comment |
|---|---|---|---|---|---|---|---|---|---|---|

[티켓 제목]
{title}

[요약]
{summary}

[원문 참고]
{source_content[:12000]}
""".strip()


def clean_markdown_table(text):
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    table = [line for line in lines if line.lstrip().startswith("|") and line.rstrip().endswith("|")]
    if len(table) < 2:
        raise UserFacingError("TC 생성 결과가 Markdown Table 형식이 아닙니다. 다시 생성해 주세요.", 502)
    expected = "| TC-ID | Priority | Type | Screen | Preconditions | Test Case | Description | Expected Result | AOS | iOS | Comment |"
    if normalize_table_line(table[0]) != normalize_table_line(expected):
        raise UserFacingError("TC 생성 결과의 컬럼 형식이 올바르지 않습니다. 다시 생성해 주세요.", 502)
    return "\n".join(table)


def normalize_table_line(line):
    return re.sub(r"\s+", " ", line.strip())


def ensure_target_database():
    target = os.environ.get("NOTION_TARGET_DATABASE_ID", "").strip()
    if not target:
        target_url = os.environ.get("NOTION_TARGET_DB_URL", TARGET_DB_URL_DEFAULT).strip()
        target = extract_notion_id(target_url)
    db = notion_request("GET", f"/databases/{normalize_uuid(target)}")
    props = db.get("properties", {})
    title_name = None
    for name, prop in props.items():
        if prop.get("type") == "title":
            title_name = name
            break
    if not title_name:
        raise UserFacingError("대상 노션 DB에 제목 속성이 없습니다.", 502)

    required = {
        "원본 노션 링크": {"url": {}},
        "요약 상태": {"select": {"options": [{"name": "요약 완료", "color": "green"}, {"name": "실패", "color": "red"}]}},
        "생성 일시": {"date": {}},
        "TC 생성 여부": {"checkbox": {}},
    }
    missing = {name: spec for name, spec in required.items() if name not in props}
    if missing:
        notion_request("PATCH", f"/databases/{normalize_uuid(target)}", {"properties": missing})
        db = notion_request("GET", f"/databases/{normalize_uuid(target)}")
    return normalize_uuid(target), title_name, db


def rt(text, bold=False):
    text = str(text or "")
    if len(text) > 1900:
        text = text[:1897] + "..."
    return [{"type": "text", "text": {"content": text}, "annotations": {"bold": bool(bold)}}]


def paragraph(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": rt(text)}} if text else {"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}


def heading(text, level=2):
    block_type = f"heading_{level}"
    return {"object": "block", "type": block_type, block_type: {"rich_text": rt(text, True)}}


def bullet(text):
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rt(text)}}


def code_block(text, language="markdown"):
    chunks = chunk_text(text, 1900)
    if len(chunks) == 1:
        rich = rt(chunks[0])
    else:
        rich = [{"type": "text", "text": {"content": chunk}} for chunk in chunks[:50]]
    return {"object": "block", "type": "code", "code": {"rich_text": rich, "language": language}}


def chunk_text(text, size):
    text = text or ""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def summary_blocks(summary):
    return [
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "📝"},
                "rich_text": rt("작업 내용 요약", True),
                "children": markdown_summary_children(summary),
            },
        }
    ]


def markdown_summary_children(summary):
    children = []
    for raw in summary.splitlines():
        line = raw.strip()
        if not line or line in {"<aside>", "</aside>"}:
            continue
        if line.startswith("**") and line.endswith("**"):
            children.append(heading(line.strip("*"), 3))
        elif line.startswith("- "):
            children.append(bullet(line[2:]))
        else:
            children.append(paragraph(line.replace("**", "")))
    return children or [paragraph(summary)]


def create_summary_page(source_url, title, summary, tc_generated=False):
    db_id, title_name, _ = ensure_target_database()
    payload = {
        "parent": {"database_id": db_id},
        "properties": {
            title_name: {"title": rt(title or "노션 티켓 요약")},
            "원본 노션 링크": {"url": source_url},
            "요약 상태": {"select": {"name": "요약 완료"}},
            "생성 일시": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
            "TC 생성 여부": {"checkbox": bool(tc_generated)},
        },
        "children": summary_blocks(summary),
    }
    page = notion_request("POST", "/pages", payload)
    return {"page_id": page["id"], "url": page.get("url", "")}


def upload_tc(page_id, tc_markdown):
    if not page_id:
        raise UserFacingError("TC를 업로드할 노션 페이지 정보가 없습니다. 먼저 노션 등록을 완료해 주세요.", 400)
    page_uuid = normalize_uuid(page_id)
    clean = clean_markdown_table(tc_markdown)
    children = [heading("테스트 케이스", 2), code_block(clean, "markdown")]
    notion_request("PATCH", f"/blocks/{page_uuid}/children", {"children": children})
    try:
        notion_request("PATCH", f"/pages/{page_uuid}", {"properties": {"TC 생성 여부": {"checkbox": True}}})
    except UserFacingError:
        print("[Notion API] TC checkbox update skipped", file=sys.stderr)
    page = notion_request("GET", f"/pages/{page_uuid}")
    return {"page_id": page_uuid, "url": page.get("url", "")}


def analyze_ticket(payload):
    source_url = (payload.get("url") or "").strip()
    ticket = fetch_ticket(source_url)
    summary = gemini_request(build_summary_prompt(ticket["title"], ticket["content"]), max_tokens=4096)
    if "작업 내용 요약" not in summary or "검증 포인트" not in summary:
        raise UserFacingError("요약 결과 파싱에 실패했습니다. 다시 시도해 주세요.", 502)
    return {
        "sourceUrl": source_url,
        "sourcePageId": ticket["page_id"],
        "title": ticket["title"],
        "sourceContent": ticket["content"],
        "summary": summary,
    }


def create_tc(payload):
    title = (payload.get("title") or "노션 티켓").strip()
    summary = (payload.get("summary") or "").strip()
    source_content = (payload.get("sourceContent") or "").strip()
    if not summary:
        raise UserFacingError("먼저 분석 요약을 생성해 주세요.", 400)
    tc = gemini_request(build_tc_prompt(title, summary, source_content), max_tokens=8192)
    return {"tcMarkdown": clean_markdown_table(tc)}


def register_summary(payload):
    source_url = (payload.get("sourceUrl") or payload.get("url") or "").strip()
    title = (payload.get("title") or "노션 티켓 요약").strip()
    summary = (payload.get("summary") or "").strip()
    if not source_url:
        raise UserFacingError("원본 노션 링크가 없습니다. 먼저 분석 요약을 생성해 주세요.", 400)
    if not summary:
        raise UserFacingError("저장할 요약 결과가 없습니다.", 400)
    return create_summary_page(source_url, title, summary, False)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        static_path = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR in static_path.parents and static_path.exists() and static_path.is_file():
            content_type = "text/plain; charset=utf-8"
            if static_path.suffix == ".css":
                content_type = "text/css; charset=utf-8"
            elif static_path.suffix == ".js":
                content_type = "application/javascript; charset=utf-8"
            self.serve_file(static_path, content_type)
            return
        json_response(self, 404, {"ok": False, "message": "요청한 페이지를 찾을 수 없습니다."})

    def do_POST(self):
        try:
            payload = read_json_body(self)
            if self.path == "/api/analyze":
                result = analyze_ticket(payload)
            elif self.path == "/api/register-summary":
                result = register_summary(payload)
            elif self.path == "/api/generate-tc":
                result = create_tc(payload)
            elif self.path == "/api/upload-tc":
                page_id = payload.get("pageId") or payload.get("notionPageId")
                result = upload_tc(page_id, payload.get("tcMarkdown") or "")
            else:
                raise UserFacingError("지원하지 않는 요청입니다.", 404)
            json_response(self, 200, {"ok": True, **result})
        except UserFacingError as exc:
            json_response(self, exc.status, {"ok": False, "message": exc.message})
        except Exception:
            traceback.print_exc()
            json_response(self, 500, {"ok": False, "message": "처리 중 오류가 발생했습니다. 서버 로그를 확인해 주세요."})

    def serve_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[Web] {self.address_string()} {fmt % args}", file=sys.stderr)


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"Automated Report Generation running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
