import unittest
from unittest.mock import patch
import app

PAGE = '38a73fbd195180a8af2fc5522f4e49ce'
VIEW = '20e73fbd195180ba973f000c22416153'
PAGE_UUID = app.normalize_uuid(PAGE)
LINK = f'https://app.notion.com/p/SDK-{PAGE}?v={VIEW}&source=copy_link'

class NotionTicketLinkTests(unittest.TestCase):
    def test_shared_ticket_link_ignores_view_id(self):
        self.assertEqual(app.extract_notion_id(LINK), PAGE_UUID)

    def test_hyphenated_page_precedes_compact_view(self):
        self.assertEqual(app.extract_notion_id(f'https://www.notion.so/SDK-{PAGE_UUID}?v={VIEW}'), PAGE_UUID)

    def test_direct_link_and_fragment(self):
        for suffix in ['', f'#{VIEW}', f'?source={VIEW}']:
            with self.subTest(suffix=suffix):
                self.assertEqual(app.extract_notion_id(f'https://www.notion.so/{PAGE}{suffix}'), PAGE_UUID)

    def test_explicit_opened_page_wins_over_database_and_view(self):
        self.assertEqual(app.extract_notion_id(f'https://www.notion.so/{VIEW}?v={VIEW}&p={PAGE}'), PAGE_UUID)

    def test_view_id_alone_is_not_a_page(self):
        with self.assertRaises(app.UserFacingError):
            app.extract_notion_id(f'https://www.notion.so/?v={VIEW}')

    def test_database_parser_keeps_database_path(self):
        self.assertEqual(app.extract_notion_database_id(f'https://www.notion.so/{VIEW}?p={PAGE}'), app.normalize_uuid(VIEW))

    def test_fetch_ticket_requests_page_not_view(self):
        page = {'properties': {'Title': {'type':'title','title':[{'plain_text':'SDK 티켓'}]}}}
        with patch.object(app, 'notion_request', return_value=page) as request, \
             patch.object(app, 'collect_blocks', return_value=['수정 내용']), \
             patch.object(app, 'collect_comments', return_value=([], [], '')):
            result = app.fetch_ticket(LINK)
        request.assert_called_once_with('GET', f'/pages/{PAGE_UUID}')
        self.assertEqual(result['page_id'], PAGE_UUID)
        self.assertIn('수정 내용', result['content'])

if __name__ == '__main__':
    unittest.main()
