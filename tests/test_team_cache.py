"""队主页瞬态失败不得把不完整 TeamInfo 写入长期缓存。"""

import unittest

from hltv_scraper import HLTVScraper


SEARCH_HTML = """
<html><body>
<a href="/team/12510/the-huns" data-result-type="TEAM" data-result-id="12510">The Huns</a>
</body></html>
"""

TEAM_HTML = """
<html><body>
<h1 class="profile-team-name">The Huns</h1>
<div class="profile-team-stat"><b>World ranking</b><span>#150</span></div>
</body></html>
"""


class TeamCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_team_page_is_not_cached_as_unranked(self) -> None:
        scraper = HLTVScraper()
        calls = []
        team_page_attempts = 0

        async def no_rankings(max_teams: int = 30):
            return []

        async def fetch(url: str, retries: int = 3):
            nonlocal team_page_attempts
            calls.append(url)
            if "/search?" in url:
                return SEARCH_HTML
            team_page_attempts += 1
            return None if team_page_attempts == 1 else TEAM_HTML

        scraper.get_rankings = no_rankings
        scraper._fetch = fetch

        first = await scraper.search_team("The Huns")
        second = await scraper.search_team("The Huns")

        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first.rank, 0)
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(second.rank, 150)
        self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
