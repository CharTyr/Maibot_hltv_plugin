"""抓取通道回归：主通道的瞬态坏页不能立刻把比赛列表打成空。"""

import unittest
from unittest.mock import AsyncMock, patch

from hltv_scraper import HLTVScraper


MATCHES_HTML = """
<a class="match-teams" href="/matches/1234567/alpha-vs-beta">
  <span class="match-teamname">Alpha</span>
  <span class="match-teamname">Beta</span>
</a>
"""


class JinaRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_matches_retries_jina_before_falling_back(self) -> None:
        scraper = HLTVScraper()
        calls = {"jina": 0, "tavily": 0}

        async def transient_jina(_url: str, no_cache: bool = False):
            calls["jina"] += 1
            return None if calls["jina"] < 3 else MATCHES_HTML

        async def unexpected_tavily(_url: str):
            calls["tavily"] += 1
            return None

        scraper._fetch_via_jina = transient_jina
        scraper._fetch_via_tavily = unexpected_tavily
        scraper._tavily_api_key = "test-only"

        with patch("hltv_scraper.asyncio.sleep", new_callable=AsyncMock):
            matches = await scraper.get_matches()

        self.assertEqual(calls, {"jina": 3, "tavily": 0})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["match_id"], "1234567")


if __name__ == "__main__":
    unittest.main()
