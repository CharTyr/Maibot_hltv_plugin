"""v6.2.0 声明行为的真实回归覆盖。"""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "hltv_plugin_contract_test"


def _install_sdk_stub() -> None:
    sdk = types.ModuleType("maibot_sdk")

    def field(*, default=None, default_factory=None, **kwargs):
        return default_factory() if default_factory is not None else default

    class PluginConfigBase:
        pass

    class MaiBotPlugin:
        def __init__(self):
            self.ctx = SimpleNamespace(logger=SimpleNamespace(
                info=lambda *args, **kwargs: None,
                warning=lambda *args, **kwargs: None,
                error=lambda *args, **kwargs: None,
            ))
            self.config = None

    def tool(*args, **kwargs):
        def decorate(function):
            return function

        return decorate

    sdk.Field = field
    sdk.MaiBotPlugin = MaiBotPlugin
    sdk.PluginConfigBase = PluginConfigBase
    sdk.Tool = tool

    sdk_types = types.ModuleType("maibot_sdk.types")

    class ToolParameterInfo:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    sdk_types.ToolParameterInfo = ToolParameterInfo
    sdk_types.ToolParamType = SimpleNamespace(STRING="string", INTEGER="integer")
    sys.modules["maibot_sdk"] = sdk
    sys.modules["maibot_sdk.types"] = sdk_types


def _load_modules():
    _install_sdk_stub()
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE_NAME] = package
    plugin_module = importlib.import_module(f"{PACKAGE_NAME}.plugin")
    scraper_module = importlib.import_module(f"{PACKAGE_NAME}.hltv_scraper")
    return plugin_module, scraper_module


PLUGIN, SCRAPER = _load_modules()


class PluginRenderingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = PLUGIN.CS2HLTVPlugin()
        self.original_scraper = PLUGIN.scraper

    def tearDown(self) -> None:
        PLUGIN.scraper = self.original_scraper

    @staticmethod
    def _fake_scraper(team, results=()):
        class FakeScraper:
            async def search_team(self, name):
                return team

            async def get_results(self, max_results=20):
                return list(results)

        return FakeScraper()

    async def test_unranked_team_omits_unknown_numeric_fields(self) -> None:
        team = SCRAPER.TeamInfo(
            team_id="12510",
            name="The Huns",
            rank=0,
            points=0,
            change="",
            players=["nin9"],
        )
        PLUGIN.scraper = self._fake_scraper(team)

        result = await self.plugin.get_team_info("The Huns")

        self.assertTrue(result["success"])
        self.assertIn("世界排名: 未上榜", result["content"])
        self.assertIn("nin9", result["content"])
        self.assertNotIn("积分:", result["content"])
        self.assertNotIn("排名变化:", result["content"])

    async def test_ranked_team_keeps_available_numeric_fields(self) -> None:
        team = SCRAPER.TeamInfo(
            team_id="7020",
            name="Spirit",
            rank=1,
            points=1000,
            change="+1",
        )
        PLUGIN.scraper = self._fake_scraper(team)

        result = await self.plugin.get_team_info("Spirit")

        self.assertTrue(result["success"])
        self.assertIn("世界排名: #1", result["content"])
        self.assertIn("积分: 1000", result["content"])
        self.assertIn("排名变化: +1", result["content"])

    async def test_fetch_failure_is_reported_as_query_failure(self) -> None:
        error = PLUGIN.TeamSearchError("获取战队搜索页失败: The Huns")

        class FailingScraper:
            async def search_team(self, name):
                raise error

        PLUGIN.scraper = FailingScraper()

        result = await self.plugin.get_team_info("The Huns")

        self.assertFalse(result["success"])
        self.assertIn("战队查询失败", result["content"])
        self.assertNotIn("未找到战队", result["content"])

    async def test_slow_team_query_returns_timeout_instead_of_hanging(self) -> None:
        class SlowScraper:
            async def search_team(self, name):
                await asyncio.sleep(0.05)
                return None

        PLUGIN.scraper = SlowScraper()
        old_timeout = PLUGIN.TEAM_INFO_STEP_TIMEOUT_SECONDS
        PLUGIN.TEAM_INFO_STEP_TIMEOUT_SECONDS = 0.01
        try:
            result = await self.plugin.get_team_info("The Huns")
        finally:
            PLUGIN.TEAM_INFO_STEP_TIMEOUT_SECONDS = old_timeout

        self.assertFalse(result["success"])
        self.assertEqual(result["content"], "战队信息查询超时，请稍后重试")


CHALLENGE_HTML = """<html><head><title>Just a moment...</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>
</head><body>Cloudflare</body></html>"""
GOOD_HTML = '<html><body><a class="match-teams" href="/matches/1/a-vs-b">A</a></body></html>'


class FetchRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_challenge_is_discarded_and_retry_uses_no_cache(self) -> None:
        scraper = SCRAPER.HLTVScraper()
        scraper._fetch_deadline_seconds = 1.0
        responses = [CHALLENGE_HTML, GOOD_HTML]
        request_headers = []

        class FakeResponse:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

        def fake_get(url, headers=None, timeout=None):
            request_headers.append(dict(headers or {}))
            return FakeResponse(responses.pop(0))

        with patch(f"{PACKAGE_NAME}.hltv_scraper.std_requests") as requests_mock:
            requests_mock.get.side_effect = fake_get
            with patch(f"{PACKAGE_NAME}.hltv_scraper.asyncio.sleep", new_callable=AsyncMock):
                result = await scraper._fetch("https://www.hltv.org/matches", retries=2)

        self.assertEqual(result, GOOD_HTML)
        self.assertEqual(len(request_headers), 2)
        self.assertNotIn("x-no-cache", request_headers[0])
        self.assertEqual(request_headers[1]["x-no-cache"], "true")

    async def test_jina_failure_falls_back_to_tavily(self) -> None:
        scraper = SCRAPER.HLTVScraper()
        scraper._fetch_deadline_seconds = 1.0
        scraper._tavily_api_key = "test-key"
        calls = []

        async def failed_jina(url, no_cache=False):
            calls.append(("jina", no_cache))
            return None

        async def tavily(url):
            calls.append(("tavily", None))
            return GOOD_HTML

        scraper._fetch_via_jina = failed_jina
        scraper._fetch_via_tavily = tavily

        with patch(f"{PACKAGE_NAME}.hltv_scraper.asyncio.sleep", new_callable=AsyncMock):
            result = await scraper._fetch("https://www.hltv.org/matches", retries=3)

        self.assertEqual(result, GOOD_HTML)
        self.assertEqual(calls, [
            ("jina", False),
            ("jina", True),
            ("jina", True),
            ("tavily", None),
        ])


if __name__ == "__main__":
    unittest.main()
