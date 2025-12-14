#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时数据提供者模块
支持 Playwright 和 BO3.gg (cs2api) 两种数据源
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("plugin")


@dataclass
class LiveMatchData:
    """实时比赛数据"""
    match_id: str
    team1: str
    team2: str
    team1_map_score: int = 0
    team2_map_score: int = 0
    current_map: str = ""
    team1_round_score: int = 0
    team2_round_score: int = 0
    event: str = ""
    format: str = ""
    url: str = ""
    # 扩展数据（来自 BO3.gg）
    team1_side: str = ""  # CT/T
    team2_side: str = ""
    round_phase: str = ""  # LIVE, FINISHED, etc.
    players: List[Dict[str, Any]] = None  # 选手实时数据

    def __post_init__(self):
        if self.players is None:
            self.players = []


class LiveDataProvider(ABC):
    """实时数据提供者基类"""

    @abstractmethod
    async def get_live_matches(self) -> List[LiveMatchData]:
        """获取所有直播比赛"""
        pass

    @abstractmethod
    async def get_match_live_data(self, match_id: str, url: str = "") -> Optional[LiveMatchData]:
        """获取指定比赛的实时数据"""
        pass

    @abstractmethod
    async def close(self):
        """关闭资源"""
        pass


# ============== BO3.gg Provider ==============

class BO3ggProvider(LiveDataProvider):
    """BO3.gg (cs2api) 实时数据提供者"""

    def __init__(self):
        self._api = None
        self._initialized = False

    async def _ensure_init(self):
        if self._initialized:
            return True
        try:
            from cs2api import CS2
            self._api = CS2()
            self._initialized = True
            logger.info("BO3.gg 实时数据提供者已初始化")
            return True
        except ImportError:
            logger.warning("cs2api 未安装，请运行: pip install cs2api")
            return False

    async def get_live_matches(self) -> List[LiveMatchData]:
        if not await self._ensure_init():
            return []

        try:
            response = await self._api.get_live_matches()
            results = response.get("results", [])
            
            matches = []
            for m in results:
                live_data = LiveMatchData(
                    match_id=str(m["id"]),
                    team1=m["team1"]["name"],
                    team2=m["team2"]["name"],
                    team1_map_score=m.get("team1_score", 0),
                    team2_map_score=m.get("team2_score", 0),
                    event=m.get("tournament", {}).get("name", ""),
                    format=f"bo{m.get('bo_type', 1)}",
                )

                # 如果有实时更新数据
                if "live_updates" in m:
                    lu = m["live_updates"]
                    live_data.current_map = lu.get("map_name", "")
                    live_data.team1_round_score = lu.get("team_1", {}).get("game_score", 0)
                    live_data.team2_round_score = lu.get("team_2", {}).get("game_score", 0)
                    live_data.team1_side = lu.get("team_1", {}).get("side", "")
                    live_data.team2_side = lu.get("team_2", {}).get("side", "")
                    live_data.round_phase = lu.get("round_phase", "")

                matches.append(live_data)

            return matches
        except Exception as e:
            logger.error(f"BO3.gg 获取直播比赛失败: {e}")
            return []

    async def get_match_live_data(self, match_id: str, url: str = "") -> Optional[LiveMatchData]:
        if not await self._ensure_init():
            return None

        try:
            # 先获取所有直播比赛
            matches = await self.get_live_matches()
            
            # 查找匹配的比赛
            for m in matches:
                if m.match_id == match_id:
                    # 尝试获取详细快照
                    if self._api:
                        try:
                            snapshot = await self._api.get_live_match_snapshot(int(match_id))
                            if snapshot:
                                m.players = self._parse_player_states(snapshot)
                        except:
                            pass
                    return m

            return None
        except Exception as e:
            logger.error(f"BO3.gg 获取比赛实时数据失败: {e}")
            return None

    def _parse_player_states(self, snapshot: Dict) -> List[Dict[str, Any]]:
        """解析选手状态"""
        players = []
        for team_key in ["team_one", "team_two"]:
            team_data = snapshot.get(team_key, {})
            team_name = team_data.get("name", "")
            for p in team_data.get("player_states", []):
                players.append({
                    "nickname": p.get("nickname", ""),
                    "team": team_name,
                    "kills": p.get("kills", 0),
                    "deaths": p.get("deaths", 0),
                    "assists": p.get("assists", 0),
                    "health": p.get("health", 0),
                    "is_alive": p.get("is_alive", False),
                    "rating": p.get("rating", 0),
                })
        return players

    async def close(self):
        if self._api:
            await self._api.close()
            self._api = None
            self._initialized = False


# ============== Playwright Provider ==============

class PlaywrightProvider(LiveDataProvider):
    """Playwright 实时数据提供者"""

    def __init__(self, headless: bool = True, browser: str = "chromium", timeout: int = 30):
        self._headless = headless
        self._browser_type = browser
        self._timeout = timeout * 1000  # 转换为毫秒
        self._browser = None
        self._context = None
        self._initialized = False

    async def _ensure_init(self):
        if self._initialized:
            return True
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            
            if self._browser_type == "firefox":
                self._browser = await self._playwright.firefox.launch(headless=self._headless)
            elif self._browser_type == "webkit":
                self._browser = await self._playwright.webkit.launch(headless=self._headless)
            else:
                self._browser = await self._playwright.chromium.launch(headless=self._headless)
            
            self._context = await self._browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            self._initialized = True
            logger.info(f"Playwright 实时数据提供者已初始化 (browser={self._browser_type})")
            return True
        except ImportError:
            logger.warning("playwright 未安装，请运行: pip install playwright && playwright install")
            return False
        except Exception as e:
            logger.error(f"Playwright 初始化失败: {e}")
            return False

    async def get_live_matches(self) -> List[LiveMatchData]:
        if not await self._ensure_init():
            return []

        try:
            page = await self._context.new_page()
            
            # 访问页面
            await page.goto("https://www.hltv.org/matches", timeout=self._timeout, wait_until="domcontentloaded")
            
            # 等待 Cloudflare 挑战完成（如果有）
            try:
                # 检查是否有 Cloudflare 挑战
                cf_challenge = await page.query_selector("div#challenge-running, div.cf-browser-verification")
                if cf_challenge:
                    logger.info("检测到 Cloudflare 挑战，等待...")
                    await page.wait_for_selector(".liveMatches", timeout=60000)
                else:
                    await page.wait_for_selector(".liveMatches", timeout=self._timeout)
            except:
                # 如果没有直播比赛区域，可能页面还在加载
                await asyncio.sleep(3)
            
            matches = []
            live_containers = await page.query_selector_all(".live-match-container")
            
            for container in live_containers:
                try:
                    match_data = await self._parse_live_match_element(page, container)
                    if match_data:
                        matches.append(match_data)
                except Exception as e:
                    logger.debug(f"解析直播比赛失败: {e}")

            await page.close()
            return matches
        except Exception as e:
            logger.error(f"Playwright 获取直播比赛失败: {e}")
            return []

    async def _parse_live_match_element(self, page, container) -> Optional[LiveMatchData]:
        """解析直播比赛元素"""
        try:
            # 获取队伍名称
            team_names = await container.query_selector_all(".match-teamname")
            team1 = await team_names[0].inner_text() if len(team_names) > 0 else "TBD"
            team2 = await team_names[1].inner_text() if len(team_names) > 1 else "TBD"

            # 获取比赛链接
            link = await container.query_selector("a")
            href = await link.get_attribute("href") if link else ""
            match_id = href.split("/")[2] if "/" in href else ""

            # 获取地图比分
            map_scores = await container.query_selector_all(".map-score")
            t1_map = 0
            t2_map = 0
            if len(map_scores) >= 2:
                t1_text = await map_scores[0].inner_text()
                t2_text = await map_scores[1].inner_text()
                t1_map = int(t1_text) if t1_text.isdigit() else 0
                t2_map = int(t2_text) if t2_text.isdigit() else 0

            # 获取回合比分
            round_scores = await container.query_selector_all(".current-map-score")
            t1_round = 0
            t2_round = 0
            if len(round_scores) >= 2:
                t1_text = await round_scores[0].inner_text()
                t2_text = await round_scores[1].inner_text()
                t1_round = int(t1_text) if t1_text.isdigit() else 0
                t2_round = int(t2_text) if t2_text.isdigit() else 0

            # 获取赛事
            event_elem = await container.query_selector(".match-event .text-ellipsis")
            event = await event_elem.inner_text() if event_elem else ""

            return LiveMatchData(
                match_id=match_id,
                team1=team1.strip(),
                team2=team2.strip(),
                team1_map_score=t1_map,
                team2_map_score=t2_map,
                team1_round_score=t1_round,
                team2_round_score=t2_round,
                event=event.strip(),
                url=f"https://www.hltv.org{href}",
            )
        except Exception as e:
            logger.debug(f"解析元素失败: {e}")
            return None

    async def get_match_live_data(self, match_id: str, url: str = "") -> Optional[LiveMatchData]:
        if not await self._ensure_init():
            return None

        if not url:
            return None

        try:
            page = await self._context.new_page()
            await page.goto(url, timeout=self._timeout)
            
            # 等待比分加载
            await page.wait_for_selector(".mapholder", timeout=self._timeout)
            
            # 解析比赛数据
            match_data = await self._parse_match_page(page, match_id, url)
            
            await page.close()
            return match_data
        except Exception as e:
            logger.error(f"Playwright 获取比赛实时数据失败: {e}")
            return None

    async def _parse_match_page(self, page, match_id: str, url: str) -> Optional[LiveMatchData]:
        """解析比赛详情页面"""
        try:
            # 获取队伍名称
            team_names = await page.query_selector_all(".teamName")
            team1 = await team_names[0].inner_text() if len(team_names) > 0 else "TBD"
            team2 = await team_names[1].inner_text() if len(team_names) > 1 else "TBD"

            # 获取赛事
            event_elem = await page.query_selector(".event a")
            event = await event_elem.inner_text() if event_elem else ""

            # 解析地图信息
            mapholders = await page.query_selector_all(".mapholder")
            t1_maps_won = 0
            t2_maps_won = 0
            current_map = ""
            t1_round = 0
            t2_round = 0

            for mh in mapholders:
                map_name_elem = await mh.query_selector(".mapname")
                map_name = await map_name_elem.inner_text() if map_name_elem else ""
                
                scores = await mh.query_selector_all(".results-team-score")
                if len(scores) >= 2:
                    t1_text = await scores[0].inner_text()
                    t2_text = await scores[1].inner_text()
                    
                    if t1_text != "-" and t2_text != "-":
                        try:
                            t1_score = int(t1_text)
                            t2_score = int(t2_text)
                            
                            # 判断地图是否结束
                            if (t1_score >= 13 and t1_score - t2_score >= 2) or \
                               (t2_score >= 13 and t2_score - t1_score >= 2):
                                if t1_score > t2_score:
                                    t1_maps_won += 1
                                else:
                                    t2_maps_won += 1
                            else:
                                # 当前进行中的地图
                                current_map = map_name
                                t1_round = t1_score
                                t2_round = t2_score
                        except ValueError:
                            pass

            return LiveMatchData(
                match_id=match_id,
                team1=team1.strip(),
                team2=team2.strip(),
                team1_map_score=t1_maps_won,
                team2_map_score=t2_maps_won,
                current_map=current_map,
                team1_round_score=t1_round,
                team2_round_score=t2_round,
                event=event.strip(),
                url=url,
            )
        except Exception as e:
            logger.error(f"解析比赛页面失败: {e}")
            return None

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, '_playwright') and self._playwright:
            await self._playwright.stop()
        self._initialized = False


# ============== PandaScore Provider ==============

class PandaScoreProvider(LiveDataProvider):
    """PandaScore API 实时数据提供者"""

    BASE_URL = "https://api.pandascore.co"

    def __init__(self, api_token: str = ""):
        self._token = api_token
        self._headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}

    async def _request(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """发送 API 请求"""
        import aiohttp
        
        url = f"{self.BASE_URL}{endpoint}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.warning(f"PandaScore API 请求失败: {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"PandaScore API 错误: {e}")
            return None

    async def get_live_matches(self) -> List[LiveMatchData]:
        if not self._token:
            logger.warning("PandaScore API token 未配置")
            return []

        data = await self._request("/csgo/matches/running")
        if not data:
            return []

        matches = []
        for m in data:
            opponents = m.get("opponents", [])
            t1 = opponents[0].get("opponent", {}).get("name", "TBD") if len(opponents) > 0 else "TBD"
            t2 = opponents[1].get("opponent", {}).get("name", "TBD") if len(opponents) > 1 else "TBD"
            
            # 获取比分
            results = m.get("results", [])
            t1_score = 0
            t2_score = 0
            for r in results:
                team_id = r.get("team_id")
                score = r.get("score", 0)
                if len(opponents) > 0 and opponents[0].get("opponent", {}).get("id") == team_id:
                    t1_score = score
                elif len(opponents) > 1 and opponents[1].get("opponent", {}).get("id") == team_id:
                    t2_score = score

            # 获取当前地图信息
            games = m.get("games", [])
            current_map = ""
            t1_round = 0
            t2_round = 0
            for g in games:
                if g.get("status") == "running":
                    map_info = g.get("map", {})
                    current_map = map_info.get("name", "") if map_info else ""
                    # PandaScore 免费版可能没有回合比分
                    break

            # 获取赛制
            bo_type = m.get("number_of_games", 1)
            match_format = f"bo{bo_type}"

            matches.append(LiveMatchData(
                match_id=str(m.get("id", "")),
                team1=t1,
                team2=t2,
                team1_map_score=t1_score,
                team2_map_score=t2_score,
                current_map=current_map,
                team1_round_score=t1_round,
                team2_round_score=t2_round,
                event=m.get("league", {}).get("name", ""),
                format=match_format,
            ))

        return matches

    async def get_match_live_data(self, match_id: str, url: str = "") -> Optional[LiveMatchData]:
        # PandaScore 免费版不支持单场比赛详情
        matches = await self.get_live_matches()
        for m in matches:
            if m.match_id == match_id:
                return m
        return None

    async def close(self):
        pass


# ============== 工厂函数 ==============

def create_live_provider(provider_type: str, **kwargs) -> Optional[LiveDataProvider]:
    """创建实时数据提供者
    
    Args:
        provider_type: "playwright", "bo3gg", 或 "pandascore"
        **kwargs: 提供者特定的配置参数
    
    Returns:
        LiveDataProvider 实例，如果创建失败返回 None
    """
    if provider_type == "playwright":
        return PlaywrightProvider(
            headless=kwargs.get("headless", True),
            browser=kwargs.get("browser", "chromium"),
            timeout=kwargs.get("timeout", 30),
        )
    elif provider_type == "bo3gg":
        return BO3ggProvider()
    elif provider_type == "pandascore":
        return PandaScoreProvider(
            api_token=kwargs.get("api_token", ""),
        )
    else:
        logger.warning(f"未知的实时数据提供者: {provider_type}")
        return None
