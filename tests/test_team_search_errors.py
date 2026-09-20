"""战队搜索必须区分抓取失败和确实没有搜索结果。"""

import unittest

from hltv_scraper import HLTVScraper, TeamSearchError


SEARCH_HTML = """
<html><body>
<a href="/team/12510/the-huns" data-result-type="TEAM" data-result-id="12510">The Huns</a>
</body></html>
"""
EMPTY_SEARCH_HTML = '<html><body><table class="table"></table></body></html>'


class TeamSearchErrorTests(unittest.IsolatedAsyncioTestCase):
    def _scraper_with(self, fetch):
        scraper = HLTVScraper()

        async def no_rankings(max_teams: int = 30):
            return []

        scraper.get_rankings = no_rankings
        scraper._fetch = fetch
        return scraper

    async def test_search_page_fetch_failure_is_not_not_found(self) -> None:
        async def fetch(url: str, retries: int = 3):
            return None

        scraper = self._scraper_with(fetch)

        with self.assertRaises(TeamSearchError):
            await scraper.search_team("The Huns")

    async def test_team_page_fetch_failure_is_not_unranked_team(self) -> None:
        async def fetch(url: str, retries: int = 3):
            return SEARCH_HTML if "/search?" in url else None

        scraper = self._scraper_with(fetch)

        with self.assertRaises(TeamSearchError):
            await scraper.search_team("The Huns")

    async def test_empty_search_page_still_means_not_found(self) -> None:
        async def fetch(url: str, retries: int = 3):
            return EMPTY_SEARCH_HTML

        scraper = self._scraper_with(fetch)

        self.assertIsNone(await scraper.search_team("Nobody FC"))


if __name__ == "__main__":
    unittest.main()
