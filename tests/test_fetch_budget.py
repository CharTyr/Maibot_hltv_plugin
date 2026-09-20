"""抓取重试必须受单 URL deadline 约束。"""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from hltv_scraper import HLTVScraper


class FetchBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_stops_when_total_deadline_is_exhausted(self) -> None:
        scraper = HLTVScraper()
        scraper._fetch_deadline_seconds = 0.01
        calls = []

        async def slow_jina(url: str, no_cache: bool = False):
            calls.append(no_cache)
            await real_sleep(0.05)
            return None

        real_sleep = asyncio.sleep
        scraper._fetch_via_jina = slow_jina

        with patch("hltv_scraper.asyncio.sleep", new_callable=AsyncMock):
            result = await scraper._fetch("https://www.hltv.org/matches", retries=3)

        self.assertIsNone(result)
        self.assertEqual(calls, [False])


if __name__ == "__main__":
    unittest.main()
