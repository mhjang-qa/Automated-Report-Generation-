#!/usr/bin/env python3
import base64
import ipaddress
import json
import os
import re
import hashlib
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from notion_html_service import GenerateRequest, generate_report, list_target_versions


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
LOADING_DIR = ROOT / "logding"
TARGET_DB_URL_DEFAULT = "https://app.notion.com/p/39673fbd1951801baa4dea29b16a155a?v=39673fbd19518011b206000c9f5cdcfb&source=copy_link"
TARGET_DATABASE_ID_DEFAULT = "39673fbd-1951-801b-aa4d-ea29b16a155a"
PUBLIC_LANDING_URL_DEFAULT = "https://mhjang-qa.github.io/Automated-Report-Generation-/"
NOTION_VERSION = "2022-06-28"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
DEFAULT_GEMINI_FALLBACK_MODELS = "gemini-2.5-flash,gemini-3.1-flash-lite"
DEFAULT_SUMMARY_CONTENT_LIMIT = 12000
DEFAULT_TC_SOURCE_LIMIT = 6000
DEFAULT_GEMINI_429_COOLDOWN_SECONDS = 60
DEFAULT_NOTION_IMAGE_LIMIT = 4
DEFAULT_NOTION_IMAGE_MAX_BYTES = 4 * 1024 * 1024
DEFAULT_PIXEL_PROXY_MAX_BYTES = 2 * 1024 * 1024
GEMINI_429_MESSAGE = "Gemini API 사용 제한(429)이 발생했습니다. 쿼터 소진, 분당 요청 제한, 토큰 사용량 초과 중 하나일 수 있습니다. 잠시 후 다시 시도하거나 입력 본문을 줄여 주세요."
ACTIVE_ANALYZE_LOCK = threading.Lock()
ACTIVE_ANALYZE_KEYS = set()
GEMINI_LIMIT_LOCK = threading.Lock()
GEMINI_LIMIT_UNTIL = 0.0
GEMINI_LIMIT_REASON = ""
GEMINI_LIMIT_DETAILS = {}


class UserFacingError(Exception):
    def __init__(self, message, status=400, extra=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra or {}


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
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
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


def env_int(name, default, minimum=1):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[Config] {name} must be an integer. Using default {default}.", file=sys.stderr)
        return default
    if value < minimum:
        print(f"[Config] {name} must be >= {minimum}. Using default {default}.", file=sys.stderr)
        return default
    return value


def env_csv(name, default=""):
    raw = os.environ.get(name, default).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def unique_ordered(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def log_event(request_id, message):
    print(f"[request_id={request_id}] {message}", file=sys.stderr)


def parse_gemini_error_body(body):
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}
    error = data.get("error") or {}
    parsed = {
        "status": error.get("status"),
        "message": error.get("message"),
        "code": error.get("code"),
        "violations": [],
        "retryDelaySeconds": None,
    }
    for detail in error.get("details", []) or []:
        detail_type = detail.get("@type", "")
        if detail_type.endswith("RetryInfo") and detail.get("retryDelay"):
            parsed["retryDelaySeconds"] = parse_retry_delay_seconds(detail.get("retryDelay"))
        violations = detail.get("violations") or detail.get("quotaViolations") or []
        for violation in violations:
            parsed["violations"].append(
                {
                    "quotaMetric": violation.get("quotaMetric"),
                    "quotaId": violation.get("quotaId"),
                    "quotaDimensions": violation.get("quotaDimensions"),
                    "quotaValue": violation.get("quotaValue"),
                }
            )
    if parsed["retryDelaySeconds"] is None and parsed["message"]:
        match = re.search(r"retry in ([0-9.]+)s", parsed["message"], re.IGNORECASE)
        if match:
            parsed["retryDelaySeconds"] = max(1, int(float(match.group(1)) + 0.999))
    return parsed


def parse_retry_delay_seconds(value):
    if not value:
        return None
    text = str(value).strip()
    if text.isdigit():
        return max(1, int(text))
    match = re.fullmatch(r"([0-9.]+)s", text)
    if match:
        return max(1, int(float(match.group(1)) + 0.999))
    return None


def summarize_gemini_limit(parsed):
    violations = parsed.get("violations") or []
    quota_ids = " ".join(str(item.get("quotaId") or "") for item in violations)
    metrics = " ".join(str(item.get("quotaMetric") or "") for item in violations)
    if "PerDay" in quota_ids:
        return "Gemini 일일 요청 한도 또는 무료 티어 한도에 도달했습니다."
    if "PerMinute" in quota_ids or "input_token_count" in metrics:
        return "Gemini 분당 요청/토큰 제한에 도달했습니다."
    if parsed.get("status") == "RESOURCE_EXHAUSTED":
        return "Gemini 프로젝트 사용 제한에 도달했습니다."
    return "Gemini API 사용 제한이 발생했습니다."


def gemini_limit_state():
    with GEMINI_LIMIT_LOCK:
        remaining = max(0, int(GEMINI_LIMIT_UNTIL - time.time() + 0.999))
        return {
            "available": remaining <= 0,
            "retryAfterSeconds": remaining,
            "reason": GEMINI_LIMIT_REASON,
            "details": GEMINI_LIMIT_DETAILS,
        }


def set_gemini_limit_cooldown(request_id, parsed, retry_after=None):
    global GEMINI_LIMIT_UNTIL, GEMINI_LIMIT_REASON, GEMINI_LIMIT_DETAILS
    retry_seconds = parse_retry_delay_seconds(retry_after) if retry_after else None
    retry_seconds = retry_seconds or parsed.get("retryDelaySeconds")
    retry_seconds = retry_seconds or env_int("GEMINI_429_COOLDOWN_SECONDS", DEFAULT_GEMINI_429_COOLDOWN_SECONDS)
    retry_seconds = max(1, retry_seconds)
    reason = summarize_gemini_limit(parsed)
    with GEMINI_LIMIT_LOCK:
        GEMINI_LIMIT_UNTIL = max(GEMINI_LIMIT_UNTIL, time.time() + retry_seconds)
        GEMINI_LIMIT_REASON = reason
        GEMINI_LIMIT_DETAILS = {
            "status": parsed.get("status"),
            "code": parsed.get("code"),
            "violations": parsed.get("violations") or [],
        }
    log_event(request_id, f"Gemini cooldown enabled seconds={retry_seconds} reason={reason}")
    return retry_seconds, reason


def gemini_limit_error_payload(retry_seconds, reason):
    message = (
        f"{GEMINI_429_MESSAGE} 현재 Gemini 호출을 약 {retry_seconds}초 동안 일시 중지했습니다. "
        f"원인: {reason}"
    )
    return UserFacingError(
        message,
        429,
        {
            "geminiUnavailable": True,
            "retryAfterSeconds": retry_seconds,
            "reason": reason,
        },
    )


def raise_if_gemini_limited(request_id, operation):
    state = gemini_limit_state()
    if state["available"]:
        return
    log_event(
        request_id,
        f"Gemini {operation} blocked by cooldown retry_after={state['retryAfterSeconds']} reason={state['reason']}",
    )
    raise gemini_limit_error_payload(state["retryAfterSeconds"], state["reason"])


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


def extract_notion_database_id(url):
    if not url or not url.strip():
        raise UserFacingError("대상 노션 DB URL이 설정되어 있지 않습니다.", 500)
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.netloc.lower()
    if "notion." not in host and "notion.site" not in host:
        raise UserFacingError("대상 노션 DB URL 형식이 올바르지 않습니다.", 500)

    path_candidates = re.findall(r"(?i)([0-9a-f]{32})", parsed.path)
    if not path_candidates:
        path_candidates = re.findall(
            r"(?i)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
            parsed.path,
        )
    if path_candidates:
        return normalize_uuid(path_candidates[-1])
    return extract_notion_id(url)


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


def block_to_image(block):
    if block.get("type") != "image" or "image" not in block:
        return None
    data = block["image"]
    source_type = data.get("type")
    url = ""
    if source_type == "file":
        url = (data.get("file") or {}).get("url", "")
    elif source_type == "external":
        url = (data.get("external") or {}).get("url", "")
    if not url:
        return None
    return {
        "block_id": block.get("id", ""),
        "source_type": source_type or "unknown",
        "url": url,
        "caption": rich_text_plain(data.get("caption")),
    }


def get_page_title(page):
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            title = rich_text_plain(prop.get("title"))
            if title:
                return title
    return "노션 티켓 요약"


def collect_blocks(block_id, depth=0, images=None):
    if depth > 8:
        return []
    if images is None:
        images = []
    results = []
    cursor = None
    while True:
        qs = f"?page_size=100"
        if cursor:
            qs += f"&start_cursor={urllib.parse.quote(cursor)}"
        data = notion_request("GET", f"/blocks/{block_id}/children{qs}")
        for block in data.get("results", []):
            image = block_to_image(block)
            if image:
                images.append(image)
                caption = image["caption"] or "캡션 없음"
                results.append(f"[이미지 {len(images)}] {caption}")
            text = block_to_text(block)
            if text:
                results.append(text)
            if block.get("has_children"):
                results.extend(collect_blocks(block["id"], depth + 1, images))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results


def infer_image_mime(url, content_type=""):
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    supported = {"image/png", "image/jpeg", "image/webp", "image/gif"}
    if mime in supported:
        return mime
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".webp"):
        return "image/webp"
    if path.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def fetch_image_for_gemini(image, request_id, index):
    max_bytes = env_int("NOTION_IMAGE_MAX_BYTES", DEFAULT_NOTION_IMAGE_MAX_BYTES)
    req = urllib.request.Request(image["url"], method="GET", headers={"User-Agent": "Silce-QA/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            content_length = int(resp.headers.get("Content-Length", "0") or "0")
            if content_length and content_length > max_bytes:
                log_event(
                    request_id,
                    f"Notion image skipped index={index} reason=content_length_too_large bytes={content_length} max_bytes={max_bytes}",
                )
                return None
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                log_event(
                    request_id,
                    f"Notion image skipped index={index} reason=download_too_large bytes>{max_bytes}",
                )
                return None
    except urllib.error.HTTPError as exc:
        log_event(request_id, f"Notion image fetch failed index={index} status={exc.code}")
        return None
    except urllib.error.URLError as exc:
        log_event(request_id, f"Notion image fetch network failed index={index}: {exc}")
        return None
    mime_type = infer_image_mime(image["url"], content_type)
    if not mime_type.startswith("image/"):
        log_event(request_id, f"Notion image skipped index={index} reason=unsupported_mime mime={mime_type}")
        return None
    log_event(
        request_id,
        f"Notion image prepared index={index} mime={mime_type} bytes={len(raw)} caption_length={len(image.get('caption') or '')}",
    )
    return {
        "mime_type": mime_type,
        "data": base64.b64encode(raw).decode("ascii"),
        "caption": image.get("caption") or "",
        "source_type": image.get("source_type") or "unknown",
    }


def prepare_gemini_images(images, request_id):
    image_limit = env_int("NOTION_IMAGE_LIMIT", DEFAULT_NOTION_IMAGE_LIMIT, minimum=0)
    if image_limit <= 0 or not images:
        return []
    prepared = []
    for index, image in enumerate(images[:image_limit], start=1):
        prepared_image = fetch_image_for_gemini(image, request_id, index)
        if prepared_image:
            prepared.append(prepared_image)
    if len(images) > image_limit:
        log_event(request_id, f"Notion images limited total={len(images)} sent={len(prepared)} limit={image_limit}")
    return prepared


def fetch_ticket(url):
    page_id = extract_notion_id(url)
    page = notion_request("GET", f"/pages/{page_id}")
    title = get_page_title(page)
    property_lines = []
    for name, prop in page.get("properties", {}).items():
        text = property_to_text(prop)
        if text:
            property_lines.append(f"{name}: {text}")
    images = []
    block_lines = collect_blocks(page_id, images=images)
    combined = "\n".join(property_lines + block_lines).strip()
    if not combined:
        raise UserFacingError("노션 본문이 비어 있어 분석할 수 없습니다.", 400)
    return {"page_id": page_id, "title": title, "content": combined, "images": images}


def gemini_request(prompt, max_tokens=4096, request_id="-", operation="gemini", images=None):
    raise_if_gemini_limited(request_id, operation)
    primary_key = require_env("GEMINI_API_KEY", "GEMINI_API_KEY")
    api_keys = [("GEMINI_API_KEY", primary_key)]
    secondary_key = os.environ.get("GEMINI_API_KEY_2", "").strip()
    if secondary_key:
        api_keys.append(("GEMINI_API_KEY_2", secondary_key))
    primary_model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
    fallback_models = env_csv("GEMINI_FALLBACK_MODELS", DEFAULT_GEMINI_FALLBACK_MODELS)
    models = unique_ordered([primary_model, *fallback_models])
    parts = [{"text": prompt}]
    for index, image in enumerate(images or [], start=1):
        caption = image.get("caption") or "캡션 없음"
        parts.append({"text": f"[이미지 {index} 설명]\n{caption}"})
        parts.append(
            {
                "inline_data": {
                    "mime_type": image["mime_type"],
                    "data": image["data"],
                }
            }
        )
    payload = {
        "contents": [{"role": "user", "parts": parts}],
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
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    log_event(
        request_id,
        (
            f"Gemini {operation} payload prompt_length={len(prompt)} payload_bytes={len(payload_bytes)} "
            f"image_count={len(images or [])} max_tokens={max_tokens} models={','.join(models)}"
        ),
    )
    last_user_error = None
    last_429_parsed = None
    last_429_retry_after = None
    total_combos = len(models) * len(api_keys)
    combo_index = 0
    for model in models:
        for key_name, api_key in api_keys:
            combo_index += 1
            is_final_combo = combo_index == total_combos
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
            )
            for attempt in range(3):
                req = urllib.request.Request(
                    url,
                    data=payload_bytes,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                try:
                    log_event(
                        request_id,
                        f"Gemini {operation} request model={model} key_label={key_name} attempt={attempt + 1}",
                    )
                    with urllib.request.urlopen(req, timeout=90) as resp:
                        log_event(
                            request_id,
                            f"Gemini {operation} HTTP status={resp.status} model={model} key_label={key_name}",
                        )
                        data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates") or []
                    log_event(
                        request_id,
                        f"Gemini {operation} response candidates={len(candidates)} model={model} key_label={key_name}",
                    )
                    if not candidates:
                        log_event(request_id, f"Gemini {operation} no candidates response_head={json.dumps(data, ensure_ascii=False)[:2000]}")
                        raise UserFacingError("Gemini 응답이 비어 있습니다. 다시 시도해 주세요.", 502)
                    finish_reason = candidates[0].get("finishReason")
                    if finish_reason:
                        log_event(request_id, f"Gemini {operation} finishReason={finish_reason} model={model} key_label={key_name}")
                    if finish_reason == "MAX_TOKENS":
                        raise UserFacingError("Gemini 응답이 길이 제한으로 중단되었습니다. 입력 본문을 줄이거나 다시 시도해 주세요.", 502)
                    if finish_reason in {"SAFETY", "RECITATION"}:
                        raise UserFacingError("Gemini 응답이 안전 정책 또는 인용 제한으로 중단되었습니다. 입력 내용을 조정해 다시 시도해 주세요.", 502)
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "\n".join(part.get("text", "") for part in parts).strip()
                    if not text:
                        log_event(request_id, f"Gemini {operation} empty text response_head={json.dumps(data, ensure_ascii=False)[:2000]}")
                        raise UserFacingError("Gemini 응답이 비어 있습니다. 다시 시도해 주세요.", 502)
                    if key_name != "GEMINI_API_KEY" or model != primary_model:
                        log_event(
                            request_id,
                            f"Gemini {operation} request succeeded with fallback model={model} key_label={key_name}",
                        )
                    return text
                except urllib.error.HTTPError as exc:
                    detail = exc.read().decode("utf-8", errors="replace")
                    retry_after = exc.headers.get("Retry-After")
                    log_event(
                        request_id,
                        f"Gemini {operation} HTTP status={exc.code} model={model} key_label={key_name} retry_after={retry_after}",
                    )
                    if exc.code == 429:
                        parsed = parse_gemini_error_body(detail)
                        last_429_parsed = parsed
                        last_429_retry_after = retry_after
                        log_event(request_id, f"Gemini {operation} 429 body={detail}")
                        log_event(request_id, f"Gemini {operation} 429 parsed={json.dumps(parsed, ensure_ascii=False)}")
                        retry_seconds = parse_retry_delay_seconds(retry_after) or parsed.get("retryDelaySeconds") or env_int(
                            "GEMINI_429_COOLDOWN_SECONDS",
                            DEFAULT_GEMINI_429_COOLDOWN_SECONDS,
                        )
                        last_user_error = gemini_limit_error_payload(retry_seconds, summarize_gemini_limit(parsed))
                        if not is_final_combo:
                            log_event(request_id, f"Gemini {operation} 429 failover to next model/key after model={model} key_label={key_name}")
                            break
                        retry_seconds, reason = set_gemini_limit_cooldown(request_id, parsed, retry_after)
                        last_user_error = gemini_limit_error_payload(retry_seconds, reason)
                        raise last_user_error
                    if exc.code == 400:
                        last_user_error = UserFacingError(f"Gemini 모델 설정을 확인해 주세요. 실패 모델: {model}", 502)
                        if not is_final_combo:
                            log_event(request_id, f"Gemini {operation} 400 failover to next model/key after model={model} key_label={key_name}")
                            break
                        raise last_user_error
                    if exc.code in (401, 403):
                        raise UserFacingError(f"{key_name} 권한 또는 Gemini API 설정을 확인해 주세요.", 502)
                    last_user_error = UserFacingError("Gemini API 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.", 502)
                    if exc.code == 503:
                        if attempt < 2:
                            sleep_s = 1.5 * (2 ** attempt)
                            log_event(request_id, f"Gemini {operation} 503 retry model={model} key_label={key_name} sleep={sleep_s}")
                            time.sleep(sleep_s)
                            continue
                        if not is_final_combo:
                            log_event(request_id, f"Gemini {operation} 503 failover to next model/key after model={model} key_label={key_name}")
                            break
                    raise last_user_error
                except urllib.error.URLError as exc:
                    log_event(request_id, f"Gemini {operation} network error model={model} key_label={key_name}: {exc}")
                    last_user_error = UserFacingError("Gemini API에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.", 502)
                    if attempt < 2:
                        sleep_s = 1.5 * (2 ** attempt)
                        log_event(request_id, f"Gemini {operation} network retry model={model} key_label={key_name} sleep={sleep_s}")
                        time.sleep(sleep_s)
                        continue
                    if not is_final_combo:
                        log_event(request_id, f"Gemini {operation} network failover to next model/key after model={model} key_label={key_name}")
                        break
                    raise last_user_error
                except UserFacingError:
                    raise
    if last_user_error:
        if last_429_parsed:
            retry_seconds, reason = set_gemini_limit_cooldown(request_id, last_429_parsed, last_429_retry_after)
            raise gemini_limit_error_payload(retry_seconds, reason)
        raise last_user_error
    raise UserFacingError("Gemini 응답 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.", 502)


def build_summary_prompt(title, content):
    content_limit = env_int("SUMMARY_CONTENT_LIMIT", DEFAULT_SUMMARY_CONTENT_LIMIT)
    limited_content = content[:content_limit]
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
{limited_content}
""".strip()


def build_tc_prompt(title, summary, source_content):
    source_limit = env_int("TC_SOURCE_LIMIT", DEFAULT_TC_SOURCE_LIMIT)
    limited_source = source_content[:source_limit]
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
{limited_source}
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


def markdown_table_to_rows(text):
    clean = clean_markdown_table(text)
    rows = []
    for line in clean.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        rows.append(cells)
    if len(rows) < 2:
        raise UserFacingError("TC 표로 변환할 데이터가 부족합니다. 다시 생성해 주세요.", 502)
    width = len(rows[0])
    normalized = []
    for row in rows:
        if len(row) < width:
            row = row + [""] * (width - len(row))
        elif len(row) > width:
            row = row[: width - 1] + [" | ".join(row[width - 1 :])]
        normalized.append(row)
    return normalized


def normalize_table_line(line):
    return re.sub(r"\s+", " ", line.strip())


def ensure_target_database():
    target = os.environ.get("NOTION_TARGET_DATABASE_ID", "").strip()
    if not target:
        target_url = os.environ.get("NOTION_TARGET_DB_URL", TARGET_DB_URL_DEFAULT).strip()
        if target_url == TARGET_DB_URL_DEFAULT:
            target = TARGET_DATABASE_ID_DEFAULT
        else:
            target = extract_notion_database_id(target_url)
    target = normalize_uuid(target)
    try:
        db = notion_request("GET", f"/databases/{target}")
    except UserFacingError as exc:
        if exc.status == 404:
            raise UserFacingError(
                f"대상 노션 DB({target})를 찾을 수 없습니다. 해당 DB를 Notion Integration에 공유했는지 확인해 주세요.",
                404,
            )
        raise
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
        notion_request("PATCH", f"/databases/{target}", {"properties": missing})
        db = notion_request("GET", f"/databases/{target}")
    return target, title_name, db


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


def table_block(rows):
    width = len(rows[0])
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": [table_row(row, width, is_header=(index == 0)) for index, row in enumerate(rows)],
        },
    }


def table_row(cells, width, is_header=False):
    normalized = (cells + [""] * width)[:width]
    return {
        "object": "block",
        "type": "table_row",
        "table_row": {"cells": [rt(cell, bold=is_header) for cell in normalized]},
    }


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
        normalized = line.replace("*", "").strip()
        if normalized == "작업 내용 요약":
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
    rows = markdown_table_to_rows(tc_markdown)
    children = [heading("테스트 케이스 - 초안", 2), table_block(rows)]
    notion_request("PATCH", f"/blocks/{page_uuid}/children", {"children": children})
    try:
        notion_request("PATCH", f"/pages/{page_uuid}", {"properties": {"TC 생성 여부": {"checkbox": True}}})
    except UserFacingError:
        print("[Notion API] TC checkbox update skipped", file=sys.stderr)
    page = notion_request("GET", f"/pages/{page_uuid}")
    return {"page_id": page_uuid, "url": page.get("url", "")}


def analyze_ticket(payload):
    request_id = uuid.uuid4().hex[:12]
    source_url = (payload.get("url") or "").strip()
    log_event(request_id, f"/api/analyze start sourceUrl={source_url}")
    extract_notion_id(source_url)
    raise_if_gemini_limited(request_id, "summary")
    analyze_key = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    with ACTIVE_ANALYZE_LOCK:
        if analyze_key in ACTIVE_ANALYZE_KEYS:
            log_event(request_id, f"/api/analyze duplicate blocked sourceUrl={source_url}")
            raise UserFacingError("이미 동일한 노션 링크 분석이 진행 중입니다. 잠시 후 다시 확인해 주세요.", 409)
        ACTIVE_ANALYZE_KEYS.add(analyze_key)
    try:
        ticket = fetch_ticket(source_url)
        summary_limit = env_int("SUMMARY_CONTENT_LIMIT", DEFAULT_SUMMARY_CONTENT_LIMIT)
        sent_content_length = min(len(ticket["content"]), summary_limit)
        prompt = build_summary_prompt(ticket["title"], ticket["content"])
        gemini_images = prepare_gemini_images(ticket.get("images") or [], request_id)
        log_event(
            request_id,
            (
                f"/api/analyze notion sourcePageId={ticket['page_id']} title={ticket['title']} "
                f"content_length={len(ticket['content'])} sent_content_length={sent_content_length} "
                f"prompt_length={len(prompt)} image_blocks={len(ticket.get('images') or [])} "
                f"sent_images={len(gemini_images)}"
            ),
        )
        summary = gemini_request(
            prompt,
            max_tokens=4096,
            request_id=request_id,
            operation="summary",
            images=gemini_images,
        )
        if "작업 내용 요약" not in summary or "검증 포인트" not in summary:
            log_event(request_id, "summary parse failed: required headings missing")
            raise UserFacingError("요약 결과 파싱에 실패했습니다. 다시 시도해 주세요.", 502)
        log_event(request_id, f"/api/analyze success summary_length={len(summary)}")
        return {
            "requestId": request_id,
            "sourceUrl": source_url,
            "sourcePageId": ticket["page_id"],
            "title": ticket["title"],
            "sourceContent": ticket["content"],
            "summary": summary,
        }
    finally:
        with ACTIVE_ANALYZE_LOCK:
            ACTIVE_ANALYZE_KEYS.discard(analyze_key)


def create_tc(payload):
    request_id = uuid.uuid4().hex[:12]
    title = (payload.get("title") or "노션 티켓").strip()
    summary = (payload.get("summary") or "").strip()
    source_content = (payload.get("sourceContent") or "").strip()
    if not summary:
        raise UserFacingError("먼저 분석 요약을 생성해 주세요.", 400)
    tc_limit = env_int("TC_SOURCE_LIMIT", DEFAULT_TC_SOURCE_LIMIT)
    prompt = build_tc_prompt(title, summary, source_content)
    log_event(
        request_id,
        f"/api/generate-tc title={title} source_content_length={len(source_content)} sent_source_length={min(len(source_content), tc_limit)} prompt_length={len(prompt)}",
    )
    tc = gemini_request(prompt, max_tokens=8192, request_id=request_id, operation="tc")
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


def login(payload):
    configured = os.environ.get("APP_LOGIN_PASSWORD", "")
    password = str(payload.get("password") or "")
    if configured and password != configured:
        raise UserFacingError("비밀번호가 올바르지 않습니다.", 401)
    return {"authenticated": True}


def _embed_int(payload, key, default=0):
    raw = payload.get(key, default)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise UserFacingError(f"{key} 값은 숫자여야 합니다.", 400)


def generate_embed_html(payload):
    request = GenerateRequest(
        template_type=payload.get("templateType") or payload.get("template_type") or "",
        title=payload.get("title") or "",
        version=payload.get("version") or "",
        filename=payload.get("filename") or "",
        notion_url=payload.get("notionUrl") or payload.get("notion_url") or "",
        raw_text=payload.get("rawText") or payload.get("raw_text") or "",
        defect_db_url=payload.get("defectDbUrl") or payload.get("defect_db_url") or "",
        target_version=payload.get("targetVersion") or payload.get("target_version") or "",
        end_total=_embed_int(payload, "endTotal", 82),
        end_fixed=_embed_int(payload, "endFixed", 60),
        end_future=_embed_int(payload, "endFuture", 2),
        end_invalid=_embed_int(payload, "endInvalid", 20),
        end_note=payload.get("endNote") or "※ 차트 수치는 총합 기준으로 집계했습니다.",
        tc_aos_pass=_embed_int(payload, "tcAosPass", 214),
        tc_aos_fail=_embed_int(payload, "tcAosFail", 23),
        tc_aos_na=_embed_int(payload, "tcAosNa", 123),
        tc_ios_pass=_embed_int(payload, "tcIosPass", 177),
        tc_ios_fail=_embed_int(payload, "tcIosFail", 36),
        tc_ios_na=_embed_int(payload, "tcIosNa", 147),
    )
    result = generate_report(request)
    return {
        "html": result.html,
        "templateType": result.template_type,
        "title": result.title,
        "version": result.version,
        "filename": result.filename,
        "message": result.message,
    }


def embed_target_versions(payload):
    defect_url = payload.get("defectDbUrl") or payload.get("defect_db_url") or ""
    versions = list_target_versions(defect_url)
    return {"versions": versions}


def parse_figma_url(figma_url):
    raw = (figma_url or "").strip()
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        raise UserFacingError("Figma URL 형식이 올바르지 않습니다.", 400)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in {"figma.com", "www.figma.com"}:
        raise UserFacingError("Figma URL은 https://www.figma.com/design/... 형식이어야 합니다.", 400)
    parts = [part for part in parsed.path.split("/") if part]
    file_key = ""
    frame_name = ""
    for index, part in enumerate(parts):
        if part in {"file", "design"} and index + 1 < len(parts):
            file_key = parts[index + 1]
            if index + 2 < len(parts):
                frame_name = urllib.parse.unquote(parts[index + 2])
            break
    if not file_key:
        raise UserFacingError("Figma file key를 찾지 못했습니다.", 400)
    params = urllib.parse.parse_qs(parsed.query)
    node_id = (params.get("node-id") or [""])[0].replace("-", ":")
    return {"fileKey": file_key, "nodeId": node_id, "frameName": frame_name}


def figma_api_request(path, query=None):
    token = os.environ.get("FIGMA_ACCESS_TOKEN") or os.environ.get("FIGMA_TOKEN") or ""
    if not token.strip():
        raise UserFacingError("FIGMA_ACCESS_TOKEN 환경변수가 설정되어 있지 않습니다.", 500)
    url = "https://api.figma.com/v1" + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"X-Figma-Token": token.strip()})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = "Figma API 호출에 실패했습니다."
        if exc.code in {401, 403}:
            message = "Figma 접근 권한이 없습니다. 토큰 권한과 파일 공유 상태를 확인해 주세요."
        elif exc.code == 404:
            message = "Figma 파일 또는 노드를 찾지 못했습니다."
        elif exc.code == 429:
            message = "Figma API 호출 제한에 도달했습니다. 잠시 후 다시 시도해 주세요."
        raise UserFacingError(message, exc.code)
    except urllib.error.URLError as exc:
        raise UserFacingError(f"Figma API 연결에 실패했습니다: {exc.reason}", 502)


def walk_figma_nodes(node):
    yield node
    for child in node.get("children") or []:
        yield from walk_figma_nodes(child)


def figma_parse(payload):
    return parse_figma_url(payload.get("figmaUrl") or payload.get("figma_url") or "")


def figma_frames(payload):
    parsed = parse_figma_url(payload.get("figmaUrl") or payload.get("figma_url") or "") if payload.get("figmaUrl") or payload.get("figma_url") else {}
    file_key = payload.get("fileKey") or payload.get("file_key") or parsed.get("fileKey")
    if not file_key:
        raise UserFacingError("Figma file key가 필요합니다.", 400)
    data = figma_api_request(f"/files/{file_key}")
    frames = []
    for node in walk_figma_nodes(data.get("document") or {}):
        if node.get("type") not in {"FRAME", "COMPONENT", "INSTANCE"}:
            continue
        box = node.get("absoluteBoundingBox") or {}
        if not box:
            continue
        frames.append(
            {
                "id": node.get("id", ""),
                "name": node.get("name", ""),
                "width": round(float(box.get("width") or 0)),
                "height": round(float(box.get("height") or 0)),
            }
        )
    return {"frames": frames}


def figma_render(payload):
    parsed = parse_figma_url(payload.get("figmaUrl") or payload.get("figma_url") or "") if payload.get("figmaUrl") or payload.get("figma_url") else {}
    file_key = payload.get("fileKey") or payload.get("file_key") or parsed.get("fileKey")
    node_id = payload.get("nodeId") or payload.get("node_id") or parsed.get("nodeId")
    if not file_key or not node_id:
        raise UserFacingError("Figma file key와 node-id가 필요합니다.", 400)
    data = figma_api_request(
        f"/images/{file_key}",
        {"ids": node_id, "format": "png", "scale": str(payload.get("scale") or "1")},
    )
    image_url = (data.get("images") or {}).get(node_id)
    if not image_url:
        raise UserFacingError("Figma 이미지 생성에 실패했습니다. node-id를 확인해 주세요.", 502)
    try:
        with urllib.request.urlopen(image_url, timeout=60) as response:
            image_bytes = response.read()
    except urllib.error.URLError as exc:
        raise UserFacingError(f"Figma PNG 다운로드에 실패했습니다: {exc.reason}", 502)
    if len(image_bytes) > env_int("FIGMA_IMAGE_MAX_BYTES", 8 * 1024 * 1024):
        raise UserFacingError("Figma 이미지가 허용 크기를 초과했습니다.", 413)
    data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    return {
        "fileKey": file_key,
        "nodeId": node_id,
        "frameName": parsed.get("frameName", ""),
        "imageDataUrl": data_url,
        "byteLength": len(image_bytes),
    }


def validate_pixel_page_url(raw_url):
    raw = (raw_url or "").strip()
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        raise UserFacingError("실제 웹 URL 형식이 올바르지 않습니다.", 400)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UserFacingError("실제 웹 URL은 http 또는 https 전체 주소여야 합니다.", 400)
    host = (parsed.hostname or "").lower()
    allowed_hosts = env_csv("PIXELAUDIT_ALLOWED_HOSTS")
    if allowed_hosts and host not in {item.lower() for item in allowed_hosts}:
        raise UserFacingError(f"{host} 도메인은 PixelAudit 허용 목록에 없습니다.", 403)
    if host in {"localhost", "0.0.0.0"} or host.endswith(".localhost"):
        raise UserFacingError("localhost URL은 PixelAudit 프록시에서 차단됩니다.", 403)
    try:
        address_infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UserFacingError("실제 웹 URL의 호스트를 해석하지 못했습니다.", 400)
    for info in address_infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise UserFacingError("실제 웹 URL의 IP 주소를 확인하지 못했습니다.", 400)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise UserFacingError("내부망/로컬 IP로 해석되는 URL은 PixelAudit 프록시에서 차단됩니다.", 403)
    return parsed


def pixel_page_check(payload):
    raw_url = payload.get("url") or payload.get("pageUrl") or payload.get("page_url") or ""
    parsed = validate_pixel_page_url(raw_url)
    request = urllib.request.Request(
        urllib.parse.urlunparse(parsed),
        method="HEAD",
        headers={"User-Agent": "PixelAudit/1.0"},
    )
    headers = {}
    status = 0
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = {key.lower(): value for key, value in exc.headers.items()}
    except urllib.error.URLError:
        request = urllib.request.Request(urllib.parse.urlunparse(parsed), headers={"User-Agent": "PixelAudit/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
            headers = {key.lower(): value for key, value in response.headers.items()}
    x_frame_options = headers.get("x-frame-options", "")
    csp = headers.get("content-security-policy", "")
    blocked = bool(x_frame_options) or "frame-ancestors" in csp.lower()
    return {
        "status": status,
        "embeddable": not blocked,
        "xFrameOptions": x_frame_options,
        "contentSecurityPolicy": csp,
        "proxyUrl": "/api/pixel/proxy?url=" + urllib.parse.quote(urllib.parse.urlunparse(parsed), safe=""),
        "reason": "iframe 차단 헤더가 감지되었습니다." if blocked else "",
    }


def fetch_pixel_proxy(raw_url):
    parsed = validate_pixel_page_url(raw_url)
    request = urllib.request.Request(urllib.parse.urlunparse(parsed), headers={"User-Agent": "PixelAudit/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "text/html; charset=utf-8")
            limit = env_int("PIXEL_PROXY_MAX_BYTES", DEFAULT_PIXEL_PROXY_MAX_BYTES)
            body = response.read(limit + 1)
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        raise UserFacingError(f"실제 웹 URL 요청에 실패했습니다. HTTP {exc.code}", exc.code)
    except urllib.error.URLError as exc:
        raise UserFacingError(f"실제 웹 URL 연결에 실패했습니다: {exc.reason}", 502)
    if len(body) > env_int("PIXEL_PROXY_MAX_BYTES", DEFAULT_PIXEL_PROXY_MAX_BYTES):
        raise UserFacingError("프록시 응답 크기가 허용 범위를 초과했습니다.", 413)
    if "text/html" in content_type.lower():
        text = body.decode("utf-8", errors="replace")
        base_tag = f'<base href="{urllib.parse.quote(final_url, safe=":/?#[]@!$&\'()*+,;=%")}">'
        if re.search(r"<head[^>]*>", text, flags=re.IGNORECASE):
            text = re.sub(r"(<head[^>]*>)", r"\1" + base_tag, text, count=1, flags=re.IGNORECASE)
        else:
            text = base_tag + text
        body = text.encode("utf-8")
        content_type = "text/html; charset=utf-8"
    return body, content_type


def landing_redirect_enabled(handler, parsed):
    params = urllib.parse.parse_qs(parsed.query)
    if params.get("app") == ["1"]:
        return False
    if os.environ.get("ENABLE_PUBLIC_LANDING_REDIRECT", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    host = (handler.headers.get("Host") or "").lower()
    if host.startswith("127.0.0.1") or host.startswith("localhost"):
        return False
    return True


class AppHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in {"/", "/api/health", "/favicon.ico"}:
            status = 204 if path == "/favicon.ico" else 200
            self.send_response(status)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            json_response(self, 200, {"ok": True, "status": "running", "ready": True})
            return
        if path == "/api/gemini-status":
            state = gemini_limit_state()
            json_response(
                self,
                200,
                {
                    "ok": True,
                    "available": state["available"],
                    "retryAfterSeconds": state["retryAfterSeconds"],
                    "reason": state["reason"],
                },
            )
            return
        if path == "/api/pixel/proxy":
            self.serve_pixel_proxy(parsed)
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/":
            if landing_redirect_enabled(self, parsed):
                self.redirect_to_public_landing()
                return
            self.serve_file(
                STATIC_DIR / "index.html",
                "text/html; charset=utf-8",
                cache_control="public, max-age=60",
            )
            return
        if path == "/logding" or path == "/logding/":
            self.serve_file(
                LOADING_DIR / "index.html",
                "text/html; charset=utf-8",
                cache_control="public, max-age=300",
            )
            return
        if path.startswith("/logding/"):
            loading_path = (LOADING_DIR / path.removeprefix("/logding/")).resolve()
            if LOADING_DIR in loading_path.parents and loading_path.exists() and loading_path.is_file():
                self.serve_file(
                    loading_path,
                    self.content_type_for(loading_path),
                    cache_control="public, max-age=300",
                )
                return
        static_path = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR in static_path.parents and static_path.exists() and static_path.is_file():
            self.serve_file(
                static_path,
                self.content_type_for(static_path),
                cache_control="public, max-age=60",
            )
            return
        json_response(self, 404, {"ok": False, "message": "요청한 페이지를 찾을 수 없습니다."})

    def redirect_to_public_landing(self):
        landing_url = os.environ.get("PUBLIC_LANDING_URL", PUBLIC_LANDING_URL_DEFAULT).strip() or PUBLIC_LANDING_URL_DEFAULT
        self.send_response(302)
        self.send_header("Location", landing_url)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        try:
            payload = read_json_body(self)
            if self.path == "/api/analyze":
                result = analyze_ticket(payload)
            elif self.path == "/api/login":
                result = login(payload)
            elif self.path == "/api/register-summary":
                result = register_summary(payload)
            elif self.path == "/api/generate-tc":
                result = create_tc(payload)
            elif self.path == "/api/upload-tc":
                page_id = payload.get("pageId") or payload.get("notionPageId")
                result = upload_tc(page_id, payload.get("tcMarkdown") or "")
            elif self.path == "/api/embed-html":
                result = generate_embed_html(payload)
            elif self.path == "/api/embed-target-versions":
                result = embed_target_versions(payload)
            elif self.path == "/api/pixel/figma-parse":
                result = figma_parse(payload)
            elif self.path == "/api/pixel/figma-frames":
                result = figma_frames(payload)
            elif self.path == "/api/pixel/figma-render":
                result = figma_render(payload)
            elif self.path == "/api/pixel/page-check":
                result = pixel_page_check(payload)
            else:
                raise UserFacingError("지원하지 않는 요청입니다.", 404)
            json_response(self, 200, {"ok": True, **result})
        except UserFacingError as exc:
            json_response(self, exc.status, {"ok": False, "message": exc.message, **exc.extra})
        except Exception:
            traceback.print_exc()
            json_response(self, 500, {"ok": False, "message": "처리 중 오류가 발생했습니다. 서버 로그를 확인해 주세요."})

    def serve_pixel_proxy(self, parsed):
        try:
            params = urllib.parse.parse_qs(parsed.query)
            raw_url = (params.get("url") or [""])[0]
            body, content_type = fetch_pixel_proxy(raw_url)
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except UserFacingError as exc:
            body = f"<html><body><p>{exc.message}</p></body></html>".encode("utf-8")
            self.send_response(exc.status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def serve_file(self, path, content_type, cache_control="no-store"):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def content_type_for(self, path):
        if path.suffix == ".css":
            return "text/css; charset=utf-8"
        if path.suffix == ".js":
            return "application/javascript; charset=utf-8"
        if path.suffix == ".html":
            return "text/html; charset=utf-8"
        if path.suffix == ".svg":
            return "image/svg+xml"
        return "text/plain; charset=utf-8"

    def log_message(self, fmt, *args):
        print(f"[Web] {self.address_string()} {fmt % args}", file=sys.stderr)


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AppHandler)
    print(f"Automated Report Generation running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
