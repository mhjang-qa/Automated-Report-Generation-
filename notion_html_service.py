#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""UI-independent report generation service.

This module is the bridge for a future web UI.  It keeps request/response data
plain Python objects and reuses the existing HTML templates without creating a
Tkinter window.
"""

from dataclasses import dataclass
from typing import Callable, Optional

import notion_html_gui_generator as legacy


StatusCallback = Optional[Callable[[str], None]]


@dataclass
class GenerateRequest:
    template_type: str
    title: str = ""
    version: str = ""
    filename: str = ""
    notion_url: str = ""
    raw_text: str = ""
    defect_db_url: str = ""
    target_version: str = ""
    end_total: int = 0
    end_fixed: int = 0
    end_future: int = 0
    end_invalid: int = 0
    end_note: str = ""
    tc_aos_pass: int = 0
    tc_aos_fail: int = 0
    tc_aos_na: int = 0
    tc_ios_pass: int = 0
    tc_ios_fail: int = 0
    tc_ios_na: int = 0


@dataclass
class GenerateResult:
    html: str
    template_type: str
    title: str
    version: str
    filename: str
    message: str = "생성 완료"


class ValueRef:
    """Small StringVar-compatible value holder for legacy template methods."""

    def __init__(self, value=""):
        self.value = "" if value is None else str(value)

    def get(self):
        return self.value

    def set(self, value):
        self.value = "" if value is None else str(value)


class LegacyReportAdapter:
    """Adapter that exposes the small surface used by legacy render methods."""

    def __init__(self, request: GenerateRequest, status_callback: StatusCallback = None):
        self.request = request
        self.status_callback = status_callback
        self.generated_html = ""
        self.template_type = ValueRef(request.template_type)
        self.title_var = ValueRef(request.title)
        self.version_var = ValueRef(request.version)
        self.filename_var = ValueRef(request.filename)
        self.notion_link_var = ValueRef(request.notion_url)
        self.defect_db_link_var = ValueRef(request.defect_db_url or legacy.DEFAULT_DEFECT_DB_URL)
        self.target_version_var = ValueRef(request.target_version)
        self.defect_rows_cache = []
        self.defect_rows_cache_url = ""

        self.end_total_var = ValueRef(request.end_total)
        self.end_fixed_var = ValueRef(request.end_fixed)
        self.end_future_var = ValueRef(request.end_future)
        self.end_invalid_var = ValueRef(request.end_invalid)
        self.end_note_var = ValueRef(request.end_note)

        self.tc_aos_pass_var = ValueRef(request.tc_aos_pass)
        self.tc_aos_fail_var = ValueRef(request.tc_aos_fail)
        self.tc_aos_na_var = ValueRef(request.tc_aos_na)
        self.tc_ios_pass_var = ValueRef(request.tc_ios_pass)
        self.tc_ios_fail_var = ValueRef(request.tc_ios_fail)
        self.tc_ios_na_var = ValueRef(request.tc_ios_na)

    def set_status(self, message):
        print(message)
        if self.status_callback:
            self.status_callback(message)

    def get_text_data(self):
        return self.request.raw_text or ""

    def parse_delimited_rows(self, raw_text):
        return legacy.NotionHtmlGeneratorGUI.parse_delimited_rows(self, raw_text)

    def js_str(self, text):
        return legacy.NotionHtmlGeneratorGUI.js_str(self, text)

    def build_tc_aggregated_from_notion(self, notion_url):
        return legacy.NotionHtmlGeneratorGUI.build_tc_aggregated_from_notion(self, notion_url)

    def build_em_html(self, title, version, raw_text):
        return legacy.NotionHtmlGeneratorGUI.build_em_html(self, title, version, raw_text)

    def build_end_html(self, title):
        return legacy.NotionHtmlGeneratorGUI.build_end_html(self, title)

    def build_fea_html(self, title, version, raw_text):
        return legacy.NotionHtmlGeneratorGUI.build_fea_html(self, title, version, raw_text)

    def build_tc_html_from_aggregated(self, title, version, aggregated_data):
        return legacy.NotionHtmlGeneratorGUI.build_tc_html_from_aggregated(self, title, version, aggregated_data)

    def build_tc_html_from_counts(self, title, version, aos_pass, aos_fail, aos_na, ios_pass, ios_fail, ios_na):
        return legacy.NotionHtmlGeneratorGUI.build_tc_html_from_counts(
            self, title, version, aos_pass, aos_fail, aos_na, ios_pass, ios_fail, ios_na
        )

    def build_tc_html(self, title, version):
        return legacy.NotionHtmlGeneratorGUI.build_tc_html(self, title, version)


def _template_defaults(template_type, version):
    template = (template_type or "").strip().upper()
    if template == "EM":
        return "결함 집계 리포트", f"em_{version}.html"
    if template == "END":
        return "전체 결함 현황", f"end_{version}.html"
    if template == "FEA":
        return "피처별 기준", f"fea_{version}.html"
    if template == "TC":
        return f"OS별 테스트 결과_{version}", f"tc_{version}.html"
    return "리포트", f"report_{version}.html"


def normalize_request(request: GenerateRequest) -> GenerateRequest:
    template = (request.template_type or "").strip().upper()
    version = (request.version or "").strip()
    default_title, default_filename = _template_defaults(template, version)
    request.template_type = template
    request.title = (request.title or default_title).strip()
    request.version = version
    request.filename = (request.filename or default_filename).strip()
    request.defect_db_url = (request.defect_db_url or legacy.DEFAULT_DEFECT_DB_URL).strip()
    request.notion_url = (request.notion_url or "").strip()
    request.target_version = (request.target_version or "").strip()
    return request


def build_end_counts_from_notion(request: GenerateRequest, adapter: LegacyReportAdapter):
    adapter.set_status("END 결함 데이터 조회 중")
    defects = legacy.fetch_defects_from_notion(request.notion_url)
    if not defects:
        raise ValueError("END 집계에 사용할 결함 데이터가 없습니다.")

    filtered = defects
    if request.version:
        filtered_by_version = legacy.filter_defects_by_target_version(defects, request.version)
        if filtered_by_version:
            filtered = filtered_by_version
            adapter.set_status(f"{request.version} END 데이터 필터링 완료")

    counts = legacy.aggregate_end_defects(filtered)
    if counts["total"] <= 0:
        raise ValueError("END 집계 결과가 비어 있습니다.")

    adapter.end_total_var.set(counts["total"])
    adapter.end_fixed_var.set(counts["fixed"])
    adapter.end_future_var.set(counts["future"])
    adapter.end_invalid_var.set(counts["invalid"])
    adapter.end_note_var.set(
        f"※ Notion 링크 기준 자동 집계: 전체 {counts['total']}건 / "
        f"수정 정상 반영 {counts['fixed']}건 / 추후 수정 {counts['future']}건 / 결함아님 {counts['invalid']}건"
    )
    return counts


def build_em_tsv_from_notion(request: GenerateRequest, adapter: LegacyReportAdapter):
    if not request.target_version:
        raise ValueError("EM 생성 전 목표버전을 선택해주세요.")
    adapter.set_status("결함 DB 조회 중")
    defects = legacy.fetch_defects_from_notion(request.defect_db_url)
    filtered = legacy.filter_defects_by_target_version(defects, request.target_version)
    if not filtered:
        raise ValueError(f"선택한 목표버전({request.target_version})에 해당하는 결함이 없습니다.")
    adapter.set_status(f"EM 결함 {len(filtered)}건 변환 완료")
    return legacy.defects_to_em_tsv(filtered)


def build_fea_lines_from_notion(request: GenerateRequest, adapter: LegacyReportAdapter):
    if not request.target_version:
        raise ValueError("FEA 생성 전 목표버전을 선택해주세요.")
    adapter.set_status("결함 DB 조회 중")
    defects = legacy.fetch_defects_from_notion(request.defect_db_url)
    filtered = legacy.filter_defects_by_target_version(defects, request.target_version)
    if not filtered:
        raise ValueError(f"선택한 목표버전({request.target_version})에 해당하는 ATM 데이터가 없습니다.")
    features = legacy.aggregate_features_from_defects(filtered)
    if not features:
        raise ValueError("ATM 기준으로 집계할 데이터가 없습니다.")
    adapter.set_status(f"ATM 구분 {len(features)}개 집계 완료")
    return legacy.defects_to_feature_lines(filtered)


def generate_report(request: GenerateRequest, status_callback: StatusCallback = None) -> GenerateResult:
    request = normalize_request(request)
    adapter = LegacyReportAdapter(request, status_callback=status_callback)
    adapter.set_status("HTML 생성 시작")

    if request.template_type == "EM":
        if request.defect_db_url and request.target_version:
            raw_tsv = build_em_tsv_from_notion(request, adapter)
            html = adapter.build_em_html(request.title, request.target_version, raw_tsv)
        else:
            html = adapter.build_em_html(request.title, request.version, request.raw_text)
    elif request.template_type == "END":
        if request.notion_url:
            build_end_counts_from_notion(request, adapter)
        html = adapter.build_end_html(request.title)
    elif request.template_type == "FEA":
        if request.defect_db_url and request.target_version:
            raw_lines = build_fea_lines_from_notion(request, adapter)
            html = adapter.build_fea_html(request.title, request.target_version, raw_lines)
        else:
            html = adapter.build_fea_html(request.title, request.version, request.raw_text)
    elif request.template_type == "TC":
        if request.notion_url:
            aggregated = adapter.build_tc_aggregated_from_notion(request.notion_url)
            html = adapter.build_tc_html_from_aggregated(request.title, request.version, aggregated)
        else:
            html = adapter.build_tc_html(request.title, request.version)
    else:
        raise ValueError("지원하지 않는 유형입니다.")

    adapter.set_status("생성 완료")
    return GenerateResult(
        html=html,
        template_type=request.template_type,
        title=request.title,
        version=request.version,
        filename=request.filename,
    )


def list_target_versions(defect_db_url: str):
    defects = legacy.fetch_defects_from_notion(defect_db_url or legacy.DEFAULT_DEFECT_DB_URL)
    return legacy.extract_target_versions(defects)
