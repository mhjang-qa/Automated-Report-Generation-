import unittest
from unittest import mock

import app


class EmbedErrorHandlingTests(unittest.TestCase):
    def test_embed_generation_value_error_is_user_facing_400(self):
        with mock.patch("app.generate_report", side_effect=ValueError("TC 전체 데이터를 모두 조회하지 못했습니다.")):
            with self.assertRaises(app.UserFacingError) as ctx:
                app.generate_embed_html({"templateType": "TC", "notionUrl": "https://app.notion.com/p/abc"})

        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("TC 전체 데이터를 모두 조회하지 못했습니다", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
