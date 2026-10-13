import unittest
import threading
import json
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import app


class EmbedErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        with app.EMBED_JOBS_LOCK:
            app.EMBED_JOBS.clear()

    def test_embed_generation_value_error_is_user_facing_400(self):
        with mock.patch("app.generate_report", side_effect=ValueError("TC 전체 데이터를 모두 조회하지 못했습니다.")):
            with self.assertRaises(app.UserFacingError) as ctx:
                app.generate_embed_html({"templateType": "TC", "notionUrl": "https://app.notion.com/p/abc"})

        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("TC 전체 데이터를 모두 조회하지 못했습니다", ctx.exception.message)

    def test_http_job_returns_before_generation_and_delivers_result(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def generate(payload, status_callback=None):
            status_callback("nested TC")
            entered.set()
            release.wait(5)
            return {"html": "<html>TC</html>", "filename": "tc.html"}

        original_run = app.run_embed_job

        def run(*args):
            try:
                original_run(*args)
            finally:
                finished.set()

        server = ThreadingHTTPServer(("127.0.0.1", 0), app.AppHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with mock.patch("app.generate_embed_html", side_effect=generate), mock.patch("app.run_embed_job", side_effect=run):
                request = urllib.request.Request(base + "/api/embed-jobs", data=b'{"templateType":"TC"}', headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=2) as response:
                    job = json.load(response)
                self.assertTrue(entered.wait(2))
                duplicate = app.start_embed_job({"templateType": "TC"})
                self.assertEqual(duplicate["jobId"], job["jobId"])
                with urllib.request.urlopen(base + "/api/embed-jobs/" + job["jobId"], timeout=2) as response:
                    pending = json.load(response)
                self.assertEqual(pending["status"], "running")
                self.assertEqual(pending["message"], "nested TC")
                release.set()
                self.assertTrue(finished.wait(2))
                with urllib.request.urlopen(base + "/api/embed-jobs/" + job["jobId"], timeout=2) as response:
                    completed = json.load(response)
                self.assertEqual(completed["result"]["html"], "<html>TC</html>")
                self.assertEqual(completed["status"], "completed")
        finally:
            release.set()
            finished.wait(5)
            server.shutdown()
            server.server_close()
            thread.join()

    def test_job_keeps_user_facing_error(self):
        with app.EMBED_JOBS_LOCK:
            app.EMBED_JOBS["test"] = {"status": "running", "updatedAt": app.time.monotonic()}
        with mock.patch("app.generate_embed_html", side_effect=app.UserFacingError("TC 조회 실패", 400)):
            app.run_embed_job("test", {})
        result = app.get_embed_job("test")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["message"], "TC 조회 실패")

    def test_login_rejects_incorrect_password(self):
        with mock.patch.dict(app.os.environ, {"APP_LOGIN_PASSWORD": "test-password"}):
            with self.assertRaises(app.UserFacingError) as ctx:
                app.login({"password": "wrong"})
            self.assertEqual(ctx.exception.status, 401)
            self.assertTrue(app.login({"password": "test-password"})["authenticated"])


if __name__ == "__main__":
    unittest.main()
