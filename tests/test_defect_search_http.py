import http.cookiejar
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import app
from search.search_service import SearchService
from tests.test_defect_search import sample_docs


class SearchHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.service=SearchService(Path(cls.temp.name)/'http.db')
        cls.service.index.replace(sample_docs(),{'indexed_at':time.time(),'count':7})
        cls.service_patch=patch('app.get_defect_search',return_value=cls.service);cls.service_patch.start()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.AppHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
        cls.service_patch.stop();cls.temp.cleanup()
    def request(self,path,body=None,opener=None):
        data=json.dumps(body).encode() if body is not None else None
        request=urllib.request.Request(self.base+path,data=data,headers={'Content-Type':'application/json'})
        return (opener or urllib.request.build_opener()).open(request,timeout=3)
    def test_status_and_search(self):
        with patch.dict(os.environ,{'APP_LOGIN_PASSWORD':''}):
            with self.request('/api/defects/status') as r: self.assertTrue(json.load(r)['ready'])
            with self.request('/api/defects/search?q=Login') as r: self.assertGreater(json.load(r)['total'],0)
    def test_bad_query_and_offset(self):
        with patch.dict(os.environ,{'APP_LOGIN_PASSWORD':''}):
            for path in ['/api/defects/search?q=','/api/defects/search?q=abc&offset=oops']:
                with self.subTest(path=path),self.assertRaises(urllib.error.HTTPError) as ctx: self.request(path)
                self.assertEqual(ctx.exception.code,400)
    def test_password_session_cookie_and_rejected_login(self):
        with patch.dict(os.environ,{'APP_LOGIN_PASSWORD':'test-password'}):
            with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/defects/status')
            self.assertEqual(ctx.exception.code,401)
            jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            with self.request('/api/login',{'password':'test-password'},opener) as r:
                self.assertIn('HttpOnly',r.headers['Set-Cookie'])
            with self.request('/api/defects/status',opener=opener) as r:self.assertTrue(json.load(r)['ready'])
            with self.assertRaises(urllib.error.HTTPError) as ctx:self.request('/api/login',{'password':'wrong'})
            self.assertEqual(ctx.exception.code,401)
    def test_static_new_page_and_original_pages(self):
        for path in ['/?app=1','/app.js','/styles.css','/defect-search.js','/notion-open.html','/notion-open.js','/pixel-device.html','/logding/']:
            with self.subTest(path=path),self.request(path) as r:self.assertEqual(r.status,200)
    def test_refresh_endpoint_coalesces(self):
        with patch.dict(os.environ,{'APP_LOGIN_PASSWORD':''}),patch.object(self.service,'start_refresh',return_value=False):
            with self.request('/api/defects/refresh',{}) as r:self.assertFalse(json.load(r)['started'])


if __name__=='__main__':unittest.main()
