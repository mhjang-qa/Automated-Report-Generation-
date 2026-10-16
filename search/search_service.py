import hashlib
import os
import threading
import time
from pathlib import Path
from difflib import SequenceMatcher
import notion_html_gui_generator as legacy
from .synonym_manager import SynonymManager
from .keyword_extractor import extract
from .query_normalizer import compact
from .semantic_matcher import similarities
from .ranking import rank
from .local_index import LocalIndex
from .notion_indexer import collect


class SearchService:
    def __init__(self, path=None, collector=collect):
        self.synonyms = SynonymManager()
        self.lock = threading.Lock()
        self.collector = collector
        self.url = os.environ.get('NOTION_DEFECT_DATABASE_URL', legacy.DEFAULT_DEFECT_DB_URL)
        # Separate caches by source and credentials without storing tokens in metadata.
        token = os.environ.get('NOTION_TOKEN') or os.environ.get('NOTION_API_KEY', '')
        scope = hashlib.sha256((self.url + token + repr(self.synonyms.groups) + os.environ.get('DEFECT_SEARCH_COMMENTS', 'false') + 'v2').encode()).hexdigest()[:20]
        root = Path(__file__).resolve().parents[1]
        self.index = LocalIndex(path or root/'data'/f'defects-{scope}.sqlite3', self.synonyms)
        self.state = {'status': 'idle', 'processed': 0, 'total_pages': 0, 'message': ''}
        self.retry_at = 0

    def status(self):
        snapshot = self.index.snapshot()
        with self.lock:
            state = dict(self.state)
        return {**snapshot, **state, 'ready': bool(snapshot.get('indexed_at')),
                'count': snapshot.get('count', 0), 'comments_enabled': os.environ.get('DEFECT_SEARCH_COMMENTS', 'false').lower() == 'true'}

    def start_refresh(self):
        with self.lock:
            if self.state['status'] == 'indexing':
                return False
            if time.time() < self.retry_at:
                return False
            self.state = {'status': 'indexing', 'processed': 0, 'total_pages': 0, 'message': 'Notion 결함 색인을 만드는 중입니다.'}
        threading.Thread(target=self._refresh, daemon=True).start()
        return True

    def _progress(self, count, total, mapping, initial=None):
        if initial is not None and not self.index.snapshot():
            self.index.replace(initial, {'indexed_at': time.time(), 'count': len(initial),
                'content_status': 'properties_only', 'warnings': [], 'source': self.url})
        with self.lock:
            self.state.update(processed=count, total_pages=total)

    def _refresh(self):
        try:
            snapshot = self.index.snapshot()
            previous = self.index.all_documents() if snapshot.get('content_status', 'complete') == 'complete' else {}
            documents, warnings, mapping = self.collector(self.url, self._progress, previous)
            unique = {document['id']: document for document in documents}
            self.index.replace(list(unique.values()), {'indexed_at': time.time(), 'count': len(unique),
                'warnings': warnings, 'property_mapping': mapping, 'source': self.url, 'content_status': 'complete'})
            with self.lock:
                self.state.update(status='ready', message='색인 갱신 완료')
        except Exception:
            # Never send tokens, upstream error bodies or defect contents to the browser/logs.
            with self.lock:
                self.state.update(status='error', message='Notion 색인 생성에 실패했습니다. 토큰, DB 공유 권한, 네트워크 연결을 확인하세요.')
                self.retry_at = time.time()+30

    def search(self, query, filters=None, offset=0, limit=20, debug=False):
        started = time.perf_counter()
        if not isinstance(query, str) or len(query) > 500:
            raise ValueError('검색어는 500자 이내로 입력해 주세요.')
        query = query.strip()
        if not compact(query):
            raise ValueError('검색할 제목, 화면명 또는 현상을 입력해 주세요.')
        if offset < 0 or offset > 10000 or not 1 <= limit <= 100:
            raise ValueError('결과 범위가 올바르지 않습니다.')
        snapshot = self.index.snapshot()
        ttl = max(60, int(os.environ.get('DEFECT_SEARCH_TTL_SECONDS', '3600')))
        if not snapshot or snapshot.get('content_status') == 'properties_only' or time.time()-snapshot.get('indexed_at', 0) > ttl:
            self.start_refresh()
        state = self.status()
        if not state['ready']:
            return {'query': query, 'total': 0, 'results': [], 'has_more': False, 'index': state}
        keywords = extract(query, self.synonyms)
        candidates = self.index.candidates(query, keywords)
        texts = [self.synonyms.canonicalize(' '.join(d.get(k, '') for k in ('title','screen','actual','steps','body'))) for d in candidates]
        semantic = similarities(self.synonyms.canonicalize(query), texts)
        results = []
        for doc, cosine in zip(candidates, semantic):
            ranked = rank(doc, query, keywords, self.synonyms, cosine)
            if not ranked.pop('_relevant'):
                continue
            if not self._passes(doc, filters or {}):
                continue
            detail = ranked.pop('_debug')
            result = {k:v for k,v in doc.items() if k not in {'body','comments','property_mapping','steps','expected','actual'}}
            result.update(ranked)
            result['snippet'] = self._snippet(doc, keywords)
            result['match_label'] = ('매우 높은 일치' if ranked['score'] >= 90 else '높은 일치' if ranked['score'] >= 80 else '관련 결함' if ranked['score'] >= 65 else '참고 가능')
            if debug and os.environ.get('DEFECT_SEARCH_DEBUG', 'false').lower() == 'true':
                result['debug'] = detail
            results.append(result)
        results.sort(key=lambda r: (-r['score'], r['id']))
        # Duplicate warnings compare distinct pages, not merely their query scores.
        for index, result in enumerate(results):
            for other in results[max(0,index-20):index]:
                ratio = SequenceMatcher(None, compact(result['title']), compact(other['title']), autojunk=False).ratio()
                if ratio >= .90:
                    result['duplicate_of'] = other['id']
                    result['duplicate_label'] = '매우 유사한 기존 결함' if ratio >= .97 else '유사 결함'
                    break
        facets = {}
        # Facets from unfiltered candidate records so selecting a filter does not erase other options.
        for name in ('platform','severity','status','target_version'):
            facets[name] = sorted({d.get(name) for d in candidates if d.get(name)})
        response = {'query':query, 'total':len(results), 'results':results[offset:offset+limit],
                    'offset':offset, 'has_more': offset+limit<len(results), 'facets':facets,
                    'index':state, 'candidate_limit':500, 'candidate_limit_reached':len(candidates)==500,
                    'duration_ms':round((time.perf_counter()-started)*1000, 2)}
        if debug and os.environ.get('DEFECT_SEARCH_DEBUG', 'false').lower() == 'true':
            response['debug'] = {'original_query':query,'normalized_query':self.synonyms.canonicalize(query),
                'keywords':keywords,'synonyms':self.synonyms.expanded(keywords), 'candidate_count':len(candidates),
                'semantic_method':'synonym-normalized character TF-IDF cosine; no embeddings', 'duration_ms':response['duration_ms']}
        return response

    def _passes(self, doc, filters):
        for name in ('platform','severity','status','target_version'):
            expected = filters.get(name)
            if not expected:
                continue
            actual = doc.get(name, '')
            if name == 'platform':
                if compact(self.synonyms.canonicalize(expected)) not in compact(self.synonyms.canonicalize(actual)):
                    return False
            elif actual != expected:
                return False
        date = doc.get('created_at', '')[:10]
        if filters.get('date_from') and (not date or date < filters['date_from']):
            return False
        if filters.get('date_to') and (not date or date > filters['date_to']):
            return False
        return True

    @staticmethod
    def _snippet(doc, keywords):
        text = doc.get('actual') or doc.get('body') or doc['title']
        locations = [text.lower().find(k.lower()) for k in keywords if k.lower() in text.lower()]
        start = max(0, min(locations, default=0)-60)
        return ('…' if start else '') + text[start:start+280] + ('…' if len(text)>start+280 else '')
