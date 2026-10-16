"""Read-only Notion collector, reusing the report generator's API/pagination."""
import os
import time
import re
import notion_html_gui_generator as legacy
from .models import Defect
from .query_normalizer import compact

ALIASES = {
    **{key: aliases for key, aliases in legacy.DEFECT_COLUMN_CANDIDATES.items()
       if key in {'severity', 'priority', 'status'}},
    'target_version': legacy.DEFECT_COLUMN_CANDIDATES['version'],
    'platform': ('OS', '운영체제', *legacy.DEFECT_COLUMN_CANDIDATES['target']),
    'screen': ('화면명', '화면', '메뉴명', '메뉴', '기능명', '기능', 'ATM', 'Feature'),
    'actual': ('실제결과', '실제 결과', 'Actual Result', 'Actual', '현상'),
    'expected': ('기대 결과', '예상결과', '예상 결과', 'Expected Result', 'Expected'),
    'steps': ('재현 단계', '재현절차', '재현 절차', 'Steps to Reproduce', 'Steps', '재현 방법'),
    'environment': ('환경정보', '발생 환경', '환경', 'Environment', 'Env'),
    'assignee': ('조치 담당자', '담당자', 'Assignee', '담당', 'Owner'),
    'created_at': ('생성 일시', '생성일시', '등록일', '생성일', 'Created', 'Created time'),
    'updated_at': ('수정일', '최종 수정일', 'Last edited time')
}


def map_page(page, resolve_relations=True):
    props = page.get('properties', {})
    row = {name: (legacy._property_value(prop, name) if resolve_relations or prop.get('type') != 'relation' else '')
           for name, prop in props.items()}
    # Existing legacy conversion stringifies people; search needs readable names.
    for name, prop in props.items():
        if prop.get('type') == 'people':
            row[name] = ', '.join(person.get('name', '') for person in prop.get('people', []) if person.get('name'))
    values, mapping = {}, {}
    for field, names in ALIASES.items():
        name = legacy._find_column(row, names)
        if name:
            values[field] = str(row.get(name) or '')
            mapping[field] = name
    title_prop = next(((name, p) for name, p in props.items() if p.get('type') == 'title'), None)
    title = str(row.get(title_prop[0]) or '') if title_prop else '제목 없음'
    if not values.get('platform'):
        detected = []
        if re.search(r'(?i)(?<![a-z])(?:aos|android)(?![a-z])|안드로이드', title):
            detected.append('AOS')
        if re.search(r'(?i)(?<![a-z])ios(?![a-z])|아이폰|아이오에스', title):
            detected.append('iOS')
        if '공통' in title:
            values['platform'] = '공통'
        elif detected:
            values['platform'] = ' / '.join(detected)
        if values.get('platform'):
            mapping['platform'] = '제목에서 추출 (OS 속성 없음)'
    if title_prop:
        mapping['title'] = title_prop[0]
    values['created_at'] = values.get('created_at') or page.get('created_time', '')
    values['updated_at'] = values.get('updated_at') or page.get('last_edited_time', '')
    return Defect(id=page['id'], title=title,
                  notion_url=page.get('url') or 'https://www.notion.so/' + page['id'].replace('-', ''),
                  body='\n'.join(f'{k}: {v}' for k, v in row.items() if v),
                  property_mapping=mapping, **values).to_dict()


def request(method, path, payload=None):
    for attempt in range(4):
        time.sleep(.35)  # Notion's average 3 requests/sec limit.
        try:
            return legacy._notion_request(method, path, payload)
        except ValueError as exc:
            if attempt == 3 or not any(str(code) in str(exc) for code in (429, 500, 502, 503, 504)):
                raise
            time.sleep(min(2**attempt, 8))


def blocks(page_id):
    sections, block_ids = [], []
    def visit(block_id, depth, section='body'):
        if depth > 30:
            raise ValueError('본문 중첩이 30단계를 초과하여 색인을 중단했습니다.')
        cursor = None
        appendix_level = None
        while True:
            from urllib.parse import urlencode
            query = {'page_size': 100}
            if cursor:
                query['start_cursor'] = cursor
            data = request('GET', f'/blocks/{block_id}/children?' + urlencode(query))
            for block in data.get('results', []):
                kind = block.get('type', '')
                content = block.get(kind) or {}
                block_ids.append(block['id'])
                text = legacy._plain_text(content.get('rich_text', []))
                if kind.startswith('heading_'):
                    level = int(kind[-1])
                    if re.match(r'(?i)^(appendix|부록|작성\s*가이드|심각도\s*기준)', text.strip()):
                        appendix_level = level
                        continue
                    if appendix_level is not None and level <= appendix_level:
                        appendix_level = None
                if appendix_level is not None:
                    continue
                if kind == 'table_row':
                    cells = [legacy._plain_text(cell) for cell in content.get('cells', [])]
                    label = compact(cells[0]) if cells else ''
                    target = next((field for field in ('steps','actual','expected','screen','environment','platform')
                                   if any(compact(alias) in label for alias in ALIASES[field])), None)
                    if target and len(cells) > 1:
                        sections.append((target, ' | '.join(cells[1:])))
                        continue
                    text = ' | '.join(cells)
                    if cells and cells[0] in {'구분', '항목'}:
                        continue
                if kind.startswith('heading_'):
                    section = 'body'
                    for field in ('steps', 'actual', 'expected', 'screen'):
                        if any(compact(alias) in compact(text) for alias in ALIASES[field]):
                            section = field
                            break
                if text:
                    sections.append((section, text))
                # Child pages and linked databases are separate records, not this page's body.
                if block.get('has_children') and kind not in {'child_page', 'child_database'}:
                    visit(block['id'], depth+1, section)
            if not data.get('has_more'):
                break
            cursor = data.get('next_cursor')
            if not cursor:
                raise ValueError('Notion 본문 페이지네이션 cursor가 누락되었습니다.')
    visit(page_id, 0)
    return sections, block_ids


def collect(database_url, progress, previous=None):
    parsed = legacy.parse_notion_link(database_url)
    # Actual page objects retain IDs, URLs, titles and timestamps, unlike report-only rows.
    pages = legacy._query_database(parsed['notion_id'])
    documents, warnings, mappings = [], [], {}
    if not previous:
        # A first-use title/property index is available while the slower body crawl runs.
        initial = [map_page(page, resolve_relations=False) for page in pages
                   if page.get('object') == 'page' and not page.get('archived') and not page.get('in_trash')]
        progress(0, len(initial), {}, initial)
    previous = previous or {}
    for index, page in enumerate(pages):
        if page.get('object') != 'page' or page.get('archived') or page.get('in_trash'):
            continue
        document = map_page(page)
        old = previous.get(document['id'])
        if old and document.get('updated_at') and old.get('updated_at') == document['updated_at'] and os.environ.get('DEFECT_SEARCH_COMMENTS', 'false').lower() != 'true':
            # Property metadata is still refreshed; unchanged bodies need no extra API calls.
            for field in ('body', 'steps', 'actual', 'expected', 'comments'):
                document[field] = old.get(field, document[field])
            for field in ('environment', 'platform'):
                if not document.get(field):
                    document[field] = old.get(field, '')
        else:
            sections, block_ids = blocks(document['id'])
            for field, text in sections:
                if field in {'environment', 'platform'}:
                    if not document.get(field):
                        document[field] = text
                else:
                    document[field] = (document.get(field, '') + '\n' + text).strip()
                if field != 'body':
                    document['body'] += '\n' + text
            if os.environ.get('DEFECT_SEARCH_COMMENTS', 'false').lower() == 'true':
                comment_text = []
                for block_id in [document['id'], *block_ids]:
                    try:
                        cursor = None
                        while True:
                            from urllib.parse import urlencode
                            params = {'block_id': block_id, 'page_size': 100}
                            if cursor:
                                params['start_cursor'] = cursor
                            data = request('GET', '/comments?' + urlencode(params))
                            comment_text.extend(legacy._plain_text(c.get('rich_text', [])) for c in data.get('results', []))
                            if not data.get('has_more'):
                                break
                            cursor = data.get('next_cursor')
                            if not cursor:
                                raise ValueError('댓글 cursor 누락')
                    except ValueError:
                        warnings.append('일부 댓글을 읽지 못했습니다. comment read 권한과 API 지원을 확인하세요.')
                        break
                document['comments'] = '\n'.join(comment_text)
        if not document.get('platform'):
            environment = document.get('environment', '')
            detected = []
            if re.search(r'(?i)\baos\b|\bandroid\b|안드로이드', environment):
                detected.append('AOS')
            if re.search(r'(?i)\bios\b|아이폰|아이오에스', environment):
                detected.append('iOS')
            if detected:
                document['platform'] = ' / '.join(detected)
                document['property_mapping']['platform'] = '본문 환경정보에서 추출'
        mappings.update(document['property_mapping'])
        documents.append(document)
        progress(index+1, len(pages), mappings)
    return documents, list(dict.fromkeys(warnings)), mappings
