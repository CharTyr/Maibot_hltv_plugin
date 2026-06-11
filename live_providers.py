"""
实时数据提供者模块
支持 Playwright、BO3.gg (cs2api)、PandaScore 三种数据源
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    team1_side: str = ""
    team2_side: str = ""
    round_phase: str = ""
    players: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.players is None:
            self.players = []


class LiveDataProvider(ABC):
    """实时数据提供者基类"""

    @abstractmethod
    async def get_live_matches(self) -> List[LiveMatchData]:
        pass

    @abstractmethod
    async def get_match_live_data(self, match_id: str, url: str = "") -> Optional[LiveMatchData]:
        pass

    @abstractmethod
    async def close(self):
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
            matches = await self.get_live_matches()
            for m in matches:
                if m.match_id == match_id:
                    if self._api:
                        try:
                            snapshot = await self._api.get_live_match_snapshot(int(match_id))
                            if snapshot:
                                m.players = self._parse_player_states(snapshot)
                        except Exception:
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


# ============== PandaScore Provider ==============


class PandaScoreProvider(LiveDataProvider):
    """PandaScore API 实时数据提供者"""

    BASE_URL = "https://api.pandascore.co"

    def __init__(self, api_token: str = ""):
        self._token = api_token
        self._headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}

    async def _request(self, endpoint: str, params: dict = None) -> Optional[Any]:
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

            games = m.get("games", [])
            current_map = ""
            for g in games:
                if g.get("status") == "running":
                    map_info = g.get("map", {})
                    current_map = map_info.get("name", "") if map_info else ""
                    break

            bo_type = m.get("number_of_games", 1)

            matches.append(LiveMatchData(
                match_id=str(m.get("id", "")),
                team1=t1,
                team2=t2,
                team1_map_score=t1_score,
                team2_map_score=t2_score,
                current_map=current_map,
                event=m.get("league", {}).get("name", ""),
                format=f"bo{bo_type}",
            ))

        return matches

    async def get_match_live_data(self, match_id: str, url: str = "") -> Optional[LiveMatchData]:
        matches = await self.get_live_matches()
        for m in matches:
            if m.match_id == match_id:
                return m
        return None

    async def close(self):
        pass


# ============== 工厂函数 ==============


def create_live_provider(provider_type: str, **kwargs) -> Optional[LiveDataProvider]:
    """创建实时数据提供者"""
    if provider_type == "bo3gg":
        return BO3ggProvider()
    elif provider_type == "pandascore":
        return PandaScoreProvider(api_token=kwargs.get("api_token", ""))
    else:
        logger.warning(f"未知的实时数据提供者: {provider_type}")
        return None
