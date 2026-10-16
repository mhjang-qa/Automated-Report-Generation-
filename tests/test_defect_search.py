import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from search.models import Defect
from search.search_service import SearchService
from search.notion_indexer import map_page, blocks, collect
from search.keyword_extractor import extract
from search.synonym_manager import SynonymManager


def sample_docs():
    records = [
        ('password', '[로그인][비밀번호 변경][공통] 비밀번호 재설정 완료 후 재로그인 진행 시 인증 화면으로 회귀하는 현상', '공통', '로그인', '인증 화면으로 회귀', '비밀번호 재설정 후 로그인'),
        ('history', '홈에서 내역관리 진입불가', 'AOS', '내역관리', '화면안열림', '홈에서 내역관리 선택'),
        ('sheet', 'Android Bottom Sheet 닫기 시 홈으로 이동', 'AOS', '홈', '홈으로 이동', 'BS 열고 Close'),
        ('qr', 'QR 결제 다국어 미노출', '공통', '결제', '번역 표시되지 않음', 'QR 결제 화면 진입'),
        ('back', 'iOS Back Button 미동작', 'iOS', '설정', '뒤로가기 동작하지 않음', '뒤로가기 선택'),
        ('android-back', 'Android 뒤로가기 미동작', 'AOS', '설정', '뒤로가기 동작하지 않음', ''),
        ('other', '송금 수수료 계산 오류', 'AOS', '송금', '수수료 오계산', '송금액 입력'),
    ]
    docs=[]
    for i,(name,title,platform,screen,actual,steps) in enumerate(records):
        docs.append(Defect(id=f'{i+1:032x}',title=title,notion_url=f'https://www.notion.so/{i+1:032x}',
            platform=platform,screen=screen,actual=actual,steps=steps,
            body=title+' '+actual+' '+steps, severity='Major',status='Open',
            created_at='2026-10-01T00:00:00Z', target_version='5.23.0').to_dict())
    return docs


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.service=SearchService(Path(self.temp.name)/'test.db')
        self.docs=sample_docs()
        self.service.index.replace(self.docs,{'indexed_at':time.time(),'count':len(self.docs)})
    def tearDown(self): self.temp.cleanup()
    def top(self,q):
        result=self.service.search(q)
        self.assertTrue(result['results'], q)
        return result['results'][0]
    def test_required_qa_queries(self):
        cases=[('비밀번호 변경하고 로그인하면 튕김',0),('홈에서 내역관리 안들어가짐',1),
               ('AOS BS 닫으면 홈으로 감',2),('QR 결제 다국어 안나옴',3),('아이폰 뒤로가기 안됨',4),
               ('AOS 비밀번호 바꾸고 로그인하면 튕김',0)]
        for q,i in cases:
            with self.subTest(query=q): self.assertEqual(self.top(q)['id'],self.docs[i]['id'])
    def test_exact_title(self): self.assertEqual(self.top(self.docs[0]['title'])['score'],100)
    def test_partial_title(self): self.assertEqual(self.top('비밀번호 재설정 완료')['id'],self.docs[0]['id'])
    def test_screen_and_feature(self):
        for q in ['내역관리','내역 관리','홈에서 내역 관리','로그인','홈']:
            with self.subTest(query=q): self.assertTrue(self.service.search(q)['results'])
    def test_symptom_only(self): self.assertEqual(self.top('튕김')['id'],self.docs[0]['id'])
    def test_os_ranking(self):
        self.assertEqual(self.top('AOS 뒤로가기 안됨')['platform'],'AOS')
        self.assertEqual(self.top('iOS 뒤로가기 안됨')['platform'],'iOS')
    def test_typo(self): self.assertEqual(self.top('비밀번로')['id'],self.docs[0]['id'])
    def test_mixed_case_spaces_special_characters(self):
        for q in ['aNdRoId bottom sheet CLOSE','AOS / BS!!! 닫기','비밀 번호 변경 로그인 튕김','QR%_ 결제 다국어']:
            with self.subTest(query=q): self.assertTrue(self.service.search(q)['results'])
    def test_unknown_query(self): self.assertEqual(self.service.search('우주선양자중력제어장치')['total'],0)
    def test_special_only_empty_and_long(self):
        for q in ['','!!!%_*', 'a'*501]:
            with self.subTest(query=q), self.assertRaises(ValueError): self.service.search(q)
    def test_filters_dates_and_pagination(self):
        result=self.service.search('뒤로가기',{'platform':'iOS','severity':'Major','status':'Open','target_version':'5.23.0','date_from':'2026-09-01','date_to':'2026-10-10'})
        self.assertEqual(result['total'],1)
        self.assertEqual(self.service.search('뒤로가기',{'date_to':'2025-01-01'})['total'],0)
        first=self.service.search('뒤로가기',limit=1)
        second=self.service.search('뒤로가기',offset=1,limit=1)
        self.assertTrue(first['has_more'])
        self.assertNotEqual(first['results'][0]['id'], second['results'][0]['id'])
    def test_debug_opt_in(self):
        with patch.dict(os.environ,{'DEFECT_SEARCH_DEBUG':'false'}): self.assertNotIn('debug',self.service.search('로그인',debug=True))
        with patch.dict(os.environ,{'DEFECT_SEARCH_DEBUG':'true'}):
            result=self.service.search('로그인',debug=True)
            self.assertIn('keywords',result['debug'])
            self.assertIn('final_score',result['results'][0]['debug'])
    def test_duplicate_distinct_pages(self):
        docs=[dict(self.docs[0]),dict(self.docs[0],id='f'*32)]
        self.service.index.replace(docs,{'indexed_at':time.time(),'count':2})
        result=self.service.search('비밀번호')
        self.assertEqual(result['total'],2)
        self.assertIn('duplicate_of',result['results'][1])
    def test_refresh_failure_keeps_snapshot(self):
        self.service.collector=lambda *a: (_ for _ in ()).throw(ValueError('private detail'))
        self.service._refresh()
        self.assertEqual(self.service.status()['status'],'error')
        self.assertTrue(self.service.status()['ready'])
        self.assertEqual(self.top('로그인')['id'],self.docs[0]['id'])
        self.assertNotIn('private',self.service.status()['message'])
    def test_refresh_atomic_and_dedup(self):
        self.service.collector=lambda *a: ([self.docs[0],self.docs[0]],[],{'title':'이름'})
        self.service._refresh()
        self.assertEqual(self.service.status()['count'],1)
    def test_new_index_starts_async(self):
        service=SearchService(Path(self.temp.name)/'empty.db')
        entered=threading.Event(); release=threading.Event()
        def collector(*a):
            entered.set(); release.wait(3); return self.docs,[],{}
        service.collector=collector
        try:
            result=service.search('로그인')
            self.assertTrue(entered.wait(1))
            self.assertFalse(result['index']['ready'])
            self.assertFalse(service.start_refresh())
        finally:
            release.set()
            deadline=time.time()+3
            while service.status()['status']=='indexing' and time.time()<deadline: time.sleep(.01)
        self.assertTrue(service.status()['ready'])
    def test_abbreviation_word_boundaries(self):
        synonyms=SynonymManager()
        self.assertNotIn('바텀시트', synonyms.canonicalize('subscribe'))
        self.assertIn('홈',extract('AOS BS 닫으면 홈으로 감',synonyms))


class CollectorTests(unittest.TestCase):
    def test_missing_properties_and_real_mapping(self):
        page={'id':'a'*32,'properties':{'결함명':{'type':'title','title':[{'plain_text':'로그인 오류'}]},'심각도':{'type':'select','select':{'name':'Major'}}}}
        document=map_page(page)
        self.assertEqual(document['title'],'로그인 오류')
        self.assertEqual(document['severity'],'Major')
        self.assertEqual(document['property_mapping']['title'],'결함명')
        self.assertFalse(document['assignee'])
    def test_nested_paginated_blocks_and_sections(self):
        def text(id,kind,value,children=False):return {'id':id,'type':kind,kind:{'rich_text':[{'plain_text':value}]},'has_children':children}
        pages=[{'results':[text('h','heading_2','재현절차'),text('p','paragraph','로그인',True)],'has_more':True,'next_cursor':'next'},
               {'results':[text('inner','paragraph','비밀번호 변경')],'has_more':False},
               {'results':[text('a','heading_2','실제결과'),text('b','paragraph','튕김')],'has_more':False}]
        with patch('search.notion_indexer.request',side_effect=pages): sections,ids=blocks('page')
        self.assertIn(('steps','비밀번호 변경'),sections)
        self.assertIn(('actual','튕김'),sections)
        self.assertIn('inner',ids)
    def test_incremental_skip_unchanged_and_deletion(self):
        page={'id':'a'*32,'object':'page','properties':{},'last_edited_time':'2026-10-01'}
        old=map_page(page);old['body']='preserved body'
        with patch('search.notion_indexer.legacy._query_database',return_value=[page]),patch('search.notion_indexer.blocks') as block:
            docs,_,_=collect('https://www.notion.so/'+'a'*32,lambda *a:None,{old['id']:old})
        block.assert_not_called()
        self.assertEqual(docs[0]['body'],'preserved body')
    def test_comment_permission_failure_is_warning(self):
        page={'id':'a'*32,'object':'page','properties':{}}
        with patch.dict(os.environ,{'DEFECT_SEARCH_COMMENTS':'true'}), patch('search.notion_indexer.legacy._query_database',return_value=[page]),patch('search.notion_indexer.blocks',return_value=([],[])),patch('search.notion_indexer.request',side_effect=ValueError('no comments permission')):
            docs,warnings,_=collect('https://www.notion.so/'+'a'*32,lambda *a:None)
        self.assertEqual(len(docs),1)
        self.assertTrue(warnings)


class RealTemplateTests(unittest.TestCase):
    def test_actual_table_template_and_appendix_exclusion(self):
        def row(id, *cells):
            return {'id':id,'type':'table_row','table_row':{'cells':[[{'plain_text':t}] for t in cells]}}
        data={'results':[
            row('a','재현 단계 (Steps to Reproduce)','화면 진입'),
            row('b','실제 결과 (Actual Result)','버튼 미동작'),
            row('c','기대 결과 (Expected Result)','정상 이동'),
            row('d','환경정보 (Environment)','iOS'),
            {'id':'e','type':'heading_3','heading_3':{'rich_text':[{'plain_text':'Appendix'}]}},
            row('f','P1','로그인 오류 결제 실패 강제 종료')], 'has_more':False}
        with patch('search.notion_indexer.request',return_value=data): sections,_=blocks('page')
        self.assertIn(('actual','버튼 미동작'),sections)
        self.assertIn(('steps','화면 진입'),sections)
        self.assertIn(('expected','정상 이동'),sections)
        self.assertIn(('environment','iOS'),sections)
        self.assertFalse(any('로그인 오류' in text for _,text in sections))
    def test_assignee_real_property_and_inferred_os(self):
        page={'id':'a'*32,'properties':{
            '결함 제목':{'type':'title','title':[{'plain_text':'[AOS][홈] 버튼 미동작'}]},
            '조치 담당자':{'type':'people','people':[{'name':'QA tester'}]}}}
        doc=map_page(page)
        self.assertEqual(doc['assignee'],'QA tester')
        self.assertEqual(doc['platform'],'AOS')

class ProgressiveIndexTests(unittest.TestCase):
    def test_initial_metadata_available_during_body_crawl(self):
        with tempfile.TemporaryDirectory() as directory:
            service=SearchService(Path(directory)/'progress.db')
            def collector(url,progress,previous):
                progress(0,1,{},[sample_docs()[0]])
                self.assertTrue(service.status()['ready'])
                self.assertEqual(service.status()['content_status'],'properties_only')
                return [sample_docs()[0]],[],{}
            service.collector=collector
            service._refresh()
            self.assertEqual(service.status()['content_status'],'complete')
    def test_incremental_keeps_body_derived_environment_and_os(self):
        page={'id':'a'*32,'object':'page','properties':{},'last_edited_time':'2026-10-01'}
        old=map_page(page);old['environment']='iOS device';old['platform']='iOS'
        with patch('search.notion_indexer.legacy._query_database',return_value=[page]),patch('search.notion_indexer.blocks') as read:
            docs,_,_=collect('https://www.notion.so/'+'a'*32,lambda *a:None,{old['id']:old})
        read.assert_not_called()
        self.assertEqual(docs[0]['environment'],'iOS device')
        self.assertEqual(docs[0]['platform'],'iOS')

if __name__=='__main__': unittest.main()
