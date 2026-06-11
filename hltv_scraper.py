"""
HLTV Scraper - 直接集成到插件中的爬虫模块
使用 Tavily Extract API 获取页面，自动过 Cloudflare
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 尝试导入依赖
try:
    import requests as std_requests
    from bs4 import BeautifulSoup

    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    logger.warning(f"HLTV 爬虫依赖未安装: {e}")


# ============== 数据模型 ==============


@dataclass
class PlayerStats:
    """选手统计数据"""

    nickname: str
    team: str = ""
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    adr: float = 0.0
    kast: float = 0.0
    rating: float = 0.0
    headshots: int = 0
    first_kills: int = 0
    first_deaths: int = 0
    clutches: str = ""


@dataclass
class MapResult:
    """单张地图结果"""

    map_name: str
    team1_score: int = 0
    team2_score: int = 0
    team1_ct_score: int = 0
    team1_t_score: int = 0
    team2_ct_score: int = 0
    team2_t_score: int = 0
    team1_players: List[PlayerStats] = field(default_factory=list)
    team2_players: List[PlayerStats] = field(default_factory=list)
    stats_url: str = ""


@dataclass
class LiveMatch:
    """直播比赛实时数据"""

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


@dataclass
class MatchDetail:
    """比赛详情"""

    match_id: str
    team1: str
    team2: str
    team1_score: int = 0
    team2_score: int = 0
    event: str = ""
    date: str = ""
    status: str = "scheduled"
    format: str = ""
    maps: List[MapResult] = field(default_factory=list)
    team1_players: List[PlayerStats] = field(default_factory=list)
    team2_players: List[PlayerStats] = field(default_factory=list)
    veto: List[str] = field(default_factory=list)


@dataclass
class TeamInfo:
    """战队信息"""

    team_id: str
    name: str
    rank: int = 0
    points: int = 0
    change: str = ""
    country: str = ""
    players: List[str] = field(default_factory=list)
    coach: str = ""
    recent_results: List[str] = field(default_factory=list)


@dataclass
class PlayerInfo:
    """选手详细信息"""

    player_id: str
    nickname: str
    name: str = ""
    team: str = ""
    country: str = ""
    age: Optional[int] = None
    rating: float = 0.0
    dpr: float = 0.0
    kast: float = 0.0
    impact: float = 0.0
    adr: float = 0.0
    kpr: float = 0.0


# ============== 爬虫核心 ==============


class HLTVScraper:
    """HLTV 数据爬虫"""

    BASE_URL = "https://www.hltv.org"

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._cache_ttl = {
            "matches": 120,
            "rankings": 3600,
            "results": 600,
            "match_detail": 60,
            "player": 3600,
            "team": 1800,
        }
        self._tavily_api_key: str = ""

    def set_tavily_key(self, key: str):
        """设置 Tavily API Key"""
        self._tavily_api_key = key

    def _get_cache(self, key: str, cache_type: str = "matches") -> Optional[Any]:
        """获取缓存"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            ttl = self._cache_ttl.get(cache_type, 300)
            if datetime.now() - timestamp < timedelta(seconds=ttl):
                return data
        return None

    def _set_cache(self, key: str, value: Any):
        """设置缓存"""
        self._cache[key] = (value, datetime.now())

    async def _fetch(self, url: str, retries: int = 2) -> Optional[str]:
        """通过 Tavily Extract API 获取页面 HTML（自动过 Cloudflare）"""
        if not HAS_DEPENDENCIES:
            return None
        if not self._tavily_api_key:
            logger.warning("Tavily API Key 未配置，无法获取页面")
            return None

        for attempt in range(retries):
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: std_requests.post(
                        "https://api.tavily.com/extract",
                        json={"api_key": self._tavily_api_key, "urls": [url]},
                        timeout=45,
                    ),
                )
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        raw = results[0].get("raw_content", "")
                        if raw:
                            return raw
                    failed = data.get("failed", [])
                    if failed:
                        logger.warning(f"Tavily extract 失败: {failed}")
                else:
                    logger.warning(f"Tavily API 返回 {response.status_code}: {url}")
            except Exception as e:
                logger.error(f"Tavily 请求错误 (尝试 {attempt + 1}/{retries}): {e}")

            if attempt < retries - 1:
                await asyncio.sleep(1)

        return None
    async def get_matches(self) -> List[Dict[str, Any]]:
        """获取比赛列表"""
        cached = self._get_cache("matches_list", "matches")
        if cached:
            return cached

        html = await self._fetch(f"{self.BASE_URL}/matches")
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        matches = []

        for link in soup.select("a.match-teams"):
            try:
                href = link.get("href", "")
                if not href:
                    continue

                parts = href.split("/")
                match_id = parts[2] if len(parts) > 2 else ""

                # 队名在 .match-teamname 或 .match-team 下
                team_name_elems = link.select(".match-teamname")
                if not team_name_elems:
                    team_name_elems = link.select(".match-team")
                team1 = team_name_elems[0].get_text(strip=True) if len(team_name_elems) > 0 else "TBD"
                team2 = team_name_elems[1].get_text(strip=True) if len(team_name_elems) > 1 else "TBD"

                if not team1 or not team2:
                    continue

                parent = link.parent
                time_elem = parent.select_one(".match-time") if parent else None
                match_time = time_elem.get_text(strip=True) if time_elem else ""

                event = "-".join(parts[3:]).replace("-", " ").title() if len(parts) > 3 else ""
                is_live = "live" in str(link.get("class", [])).lower()

                matches.append({
                    "match_id": match_id,
                    "team1": team1,
                    "team2": team2,
                    "event": event,
                    "time": match_time,
                    "status": "live" if is_live else "scheduled",
                    "url": f"{self.BASE_URL}{href}",
                })
            except Exception as e:
                logger.debug(f"解析比赛失败: {e}")

        self._set_cache("matches_list", matches)
        return matches

    # ============== 直播比赛 ==============

    async def get_live_matches(self, fetch_details: bool = True) -> List[LiveMatch]:
        """获取正在进行的直播比赛"""
        cache_key = "live_matches"
        cached = self._get_cache(cache_key, "match_detail")
        if cached:
            return cached

        html = await self._fetch(f"{self.BASE_URL}/matches")
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        live_matches = []

        live_section = soup.select_one(".liveMatches")
        if not live_section:
            return []

        for match_container in live_section.select(".live-match-container"):
            try:
                live_match = self._parse_live_match(match_container)
                if live_match:
                    if fetch_details and live_match.url:
                        detailed = await self._fetch_live_match_detail(live_match)
                        if detailed:
                            live_match = detailed
                    live_matches.append(live_match)
            except Exception as e:
                logger.debug(f"解析直播比赛失败: {e}")

        self._set_cache(cache_key, live_matches)
        return live_matches

    async def _fetch_live_match_detail(self, live_match: LiveMatch) -> Optional[LiveMatch]:
        """从比赛详情页获取更准确的直播数据"""
        html = await self._fetch(live_match.url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        try:
            mapholders = soup.select(".mapholder")
            team1_maps_won = 0
            team2_maps_won = 0
            current_map = ""
            current_map_t1_score = 0
            current_map_t2_score = 0

            for mh in mapholders:
                map_name_elem = mh.select_one(".mapname")
                map_name = map_name_elem.get_text(strip=True) if map_name_elem else ""

                scores = mh.select(".results-team-score")
                if len(scores) >= 2:
                    t1_score_text = scores[0].get_text(strip=True)
                    t2_score_text = scores[1].get_text(strip=True)

                    if t1_score_text != "-" and t2_score_text != "-":
                        try:
                            t1_score = int(t1_score_text)
                            t2_score = int(t2_score_text)

                            if (t1_score >= 13 and t1_score - t2_score >= 2) or \
                               (t2_score >= 13 and t2_score - t1_score >= 2) or \
                               (t1_score >= 13 and t2_score >= 13 and abs(t1_score - t2_score) >= 2):
                                if t1_score > t2_score:
                                    team1_maps_won += 1
                                else:
                                    team2_maps_won += 1
                            else:
                                current_map = map_name
                                current_map_t1_score = t1_score
                                current_map_t2_score = t2_score
                        except ValueError:
                            pass

            format_elem = soup.select_one(".preformatted-text")
            match_format = ""
            if format_elem:
                text = format_elem.get_text(strip=True).lower()
                if "best of 5" in text:
                    match_format = "bo5"
                elif "best of 3" in text:
                    match_format = "bo3"
                elif "best of 1" in text:
                    match_format = "bo1"

            return LiveMatch(
                match_id=live_match.match_id,
                team1=live_match.team1,
                team2=live_match.team2,
                team1_map_score=team1_maps_won,
                team2_map_score=team2_maps_won,
                current_map=current_map,
                team1_round_score=current_map_t1_score,
                team2_round_score=current_map_t2_score,
                event=live_match.event,
                format=match_format or live_match.format,
                url=live_match.url,
            )
        except Exception as e:
            logger.error(f"获取直播比赛详情失败: {e}")
            return None

    def _parse_live_match(self, container) -> Optional[LiveMatch]:
        """解析直播比赛容器"""
        try:
            match_link = container.select_one("a.match-teams, a.match-info")
            if not match_link:
                return None

            href = match_link.get("href", "")
            parts = href.split("/")
            match_id = parts[2] if len(parts) > 2 else ""

            team_names = container.select(".match-teamname")
            team1 = team_names[0].get_text(strip=True) if len(team_names) > 0 else "TBD"
            team2 = team_names[1].get_text(strip=True) if len(team_names) > 1 else "TBD"

            map_scores = container.select(".map-score")
            team1_map_score = 0
            team2_map_score = 0
            if len(map_scores) >= 2:
                try:
                    t1_text = map_scores[0].get_text(strip=True).replace("(", "").replace(")", "")
                    t2_text = map_scores[1].get_text(strip=True).replace("(", "").replace(")", "")
                    team1_map_score = int(t1_text) if t1_text.isdigit() else 0
                    team2_map_score = int(t2_text) if t2_text.isdigit() else 0
                except Exception:
                    pass

            round_scores = container.select(".current-map-score")
            team1_round_score = 0
            team2_round_score = 0
            if len(round_scores) >= 2:
                try:
                    team1_round_score = int(round_scores[0].get_text(strip=True) or 0)
                    team2_round_score = int(round_scores[1].get_text(strip=True) or 0)
                except Exception:
                    pass

            event_elem = container.select_one(".match-event .text-ellipsis")
            event = event_elem.get_text(strip=True) if event_elem else ""

            format_elem = container.select_one(".match-meta")
            match_format = ""
            if format_elem:
                format_text = format_elem.get_text(strip=True).lower()
                if "bo3" in format_text:
                    match_format = "bo3"
                elif "bo5" in format_text:
                    match_format = "bo5"
                elif "bo1" in format_text:
                    match_format = "bo1"

            return LiveMatch(
                match_id=match_id,
                team1=team1,
                team2=team2,
                team1_map_score=team1_map_score,
                team2_map_score=team2_map_score,
                team1_round_score=team1_round_score,
                team2_round_score=team2_round_score,
                event=event,
                format=match_format,
                url=f"{self.BASE_URL}{href}",
            )
        except Exception as e:
            logger.debug(f"解析直播比赛失败: {e}")
            return None

    # ============== 比赛详情 ==============

    async def get_match_detail(self, match_id: str, match_url: str = None) -> Optional[MatchDetail]:
        """获取比赛详情"""
        cache_key = f"match_{match_id}"
        cached = self._get_cache(cache_key, "match_detail")
        if cached:
            return cached

        if not match_url:
            matches = await self.get_matches()
            for m in matches:
                if m["match_id"] == match_id:
                    match_url = m["url"]
                    break

            if not match_url:
                results = await self.get_results(max_results=50)
                for r in results:
                    if r["match_id"] == match_id:
                        match_url = r["url"]
                        break

        if not match_url:
            return None

        html = await self._fetch(match_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")
        detail = self._parse_match_detail(soup, match_id)

        if detail:
            self._set_cache(cache_key, detail)

        return detail

    def _parse_match_detail(self, soup: BeautifulSoup, match_id: str) -> Optional[MatchDetail]:
        """解析比赛详情页面"""
        try:
            teams = soup.select(".teamName")
            team1 = teams[0].get_text(strip=True) if len(teams) > 0 else "TBD"
            team2 = teams[1].get_text(strip=True) if len(teams) > 1 else "TBD"

            scores = soup.select(".team .won, .team .lost, .team .tie")
            team1_score = 0
            team2_score = 0
            if len(scores) >= 2:
                try:
                    team1_score = int(scores[0].get_text(strip=True))
                    team2_score = int(scores[1].get_text(strip=True))
                except Exception:
                    pass

            event_elem = soup.select_one(".event a")
            event = event_elem.get_text(strip=True) if event_elem else ""

            date_elem = soup.select_one(".date")
            date = date_elem.get_text(strip=True) if date_elem else ""

            format_elem = soup.select_one(".preformatted-text")
            match_format = ""
            if format_elem:
                text = format_elem.get_text(strip=True).lower()
                if "best of 5" in text:
                    match_format = "bo5"
                elif "best of 3" in text:
                    match_format = "bo3"
                elif "best of 1" in text:
                    match_format = "bo1"

            status = "finished"
            if soup.select_one(".countdown"):
                status = "scheduled"
            elif soup.select_one(".liveMatch, .live-match"):
                status = "live"

            maps = []
            for mapholder in soup.select(".mapholder"):
                map_result = self._parse_map_result(mapholder)
                if map_result:
                    maps.append(map_result)

            veto = []
            for veto_elem in soup.select(".veto-box .padding"):
                veto.append(veto_elem.get_text(strip=True))

            return MatchDetail(
                match_id=match_id,
                team1=team1,
                team2=team2,
                team1_score=team1_score,
                team2_score=team2_score,
                event=event,
                date=date,
                status=status,
                format=match_format,
                maps=maps,
                veto=veto,
            )
        except Exception as e:
            logger.error(f"解析比赛详情失败: {e}")
            return None

    def _parse_map_result(self, mapholder) -> Optional[MapResult]:
        """解析单张地图结果"""
        try:
            map_name_elem = mapholder.select_one(".mapname")
            map_name = map_name_elem.get_text(strip=True) if map_name_elem else "Unknown"

            scores = mapholder.select(".results-team-score")
            team1_score = int(scores[0].get_text(strip=True)) if len(scores) > 0 else 0
            team2_score = int(scores[1].get_text(strip=True)) if len(scores) > 1 else 0

            stats_link = mapholder.select_one("a[href*='mapstatsid']")
            stats_url = ""
            if stats_link:
                stats_url = f"{self.BASE_URL}{stats_link.get('href', '')}"

            return MapResult(
                map_name=map_name,
                team1_score=team1_score,
                team2_score=team2_score,
                stats_url=stats_url,
            )
        except Exception as e:
            logger.debug(f"解析地图结果失败: {e}")
            return None

    # ============== 地图统计 ==============

    async def get_map_stats(self, stats_url: str) -> Optional[Dict[str, Any]]:
        """获取地图详细统计（Scoreboard）"""
        if not stats_url:
            return None

        cache_key = f"mapstats_{stats_url}"
        cached = self._get_cache(cache_key, "match_detail")
        if cached:
            return cached

        html = await self._fetch(stats_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")
        stats = self._parse_map_stats(soup)

        if stats:
            self._set_cache(cache_key, stats)

        return stats

    async def get_map_stats_from_match(self, match_id: str, map_index: int = 0) -> Optional[Dict[str, Any]]:
        """从比赛详情页直接解析地图 Scoreboard（绕过 /stats/ 页面的 Cloudflare 拦截）

        Args:
            match_id: 比赛 ID
            map_index: 地图索引（从 0 开始）
        """
        cache_key = f"mapstats_inline_{match_id}_{map_index}"
        cached = self._get_cache(cache_key, "match_detail")
        if cached:
            return cached

        # 获取比赛详情页 HTML
        match_url = None
        matches = await self.get_matches()
        for m in matches:
            if m["match_id"] == match_id:
                match_url = m["url"]
                break
        if not match_url:
            results = await self.get_results(max_results=50)
            for r in results:
                if r["match_id"] == match_id:
                    match_url = r["url"]
                    break
        if not match_url:
            return None

        html = await self._fetch(match_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")
        stats = self._parse_inline_map_stats(soup, map_index)

        if stats:
            self._set_cache(cache_key, stats)

        return stats

    def _parse_inline_map_stats(self, soup: BeautifulSoup, map_index: int = 0) -> Optional[Dict[str, Any]]:
        """从比赛详情页解析内嵌的地图选手统计

        页面结构: .stats-content 区域按顺序为 [all maps, map1, map2, ...]
        每个地图区域有 6 个表格: team1总, team1_ct, team1_t, team2总, team2_ct, team2_t
        表格列: 选手名, K-D, eK-eD, Swing, ADR, eADR, KAST, eKAST, Rating3.0
        """
        try:
            stats_contents = soup.select(".stats-content")
            # 第 0 个是 all maps，实际地图从索引 1 开始
            target_idx = map_index + 1
            if target_idx >= len(stats_contents):
                return None

            sc = stats_contents[target_idx]
            tables = sc.select("table")
            # 每张地图 6 个表格: t1总, t1_ct, t1_t, t2总, t2_ct, t2_t
            if len(tables) < 4:
                return None

            result = {"team1": {"name": "", "players": []}, "team2": {"name": "", "players": []}}

            # 解析 team1 总数据（第 1 个表格）和 team2 总数据（第 4 个表格）
            for team_key, table_idx in [("team1", 0), ("team2", 3)]:
                table = tables[table_idx]
                rows = table.select("tr")
                if not rows:
                    continue

                # 第一行是表头行（队名 + 列名）
                header_cells = rows[0].select("td")
                if header_cells:
                    result[team_key]["name"] = header_cells[0].get_text(strip=True)

                # 后续行是选手数据
                for row in rows[1:]:
                    cells = row.select("td")
                    if len(cells) < 8:
                        continue

                    # 解析选手名
                    nick_elem = cells[0].select_one(".statsPlayerName")
                    nickname = nick_elem.get_text(strip=True) if nick_elem else cells[0].get_text(strip=True)
                    # 清理选手名（去掉真名部分）
                    if "'" in nickname:
                        # "Eduardo 'dumau' Wolkmer" -> "dumau"
                        parts = nickname.split("'")
                        if len(parts) >= 2:
                            nickname = parts[1]

                    # K-D 列
                    kd_text = cells[1].get_text(strip=True)
                    kills, deaths = 0, 0
                    if "-" in kd_text:
                        kd_parts = kd_text.split("-")
                        kills = int(kd_parts[0]) if kd_parts[0].isdigit() else 0
                        deaths = int(kd_parts[1]) if len(kd_parts) > 1 and kd_parts[1].isdigit() else 0

                    # ADR 列（索引 4）
                    adr_text = cells[4].get_text(strip=True) if len(cells) > 4 else "0"
                    try:
                        adr = float(adr_text)
                    except Exception:
                        adr = 0.0

                    # KAST 列（索引 6）
                    kast_text = cells[6].get_text(strip=True).replace("%", "") if len(cells) > 6 else "0"
                    try:
                        kast = float(kast_text)
                    except Exception:
                        kast = 0.0

                    # Rating3.0 列（最后一列）
                    rating_text = cells[-1].get_text(strip=True)
                    try:
                        rating = float(rating_text)
                    except Exception:
                        rating = 0.0

                    result[team_key]["players"].append(PlayerStats(
                        nickname=nickname,
                        kills=kills,
                        deaths=deaths,
                        assists=0,  # 详情页内嵌数据不含 assists
                        adr=adr,
                        kast=kast,
                        rating=rating,
                    ))

            return result
        except Exception as e:
            logger.error(f"解析内嵌地图统计失败: {e}")
            return None

    def _parse_map_stats(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """解析地图统计页面"""
        try:
            result = {"team1": {"name": "", "players": []}, "team2": {"name": "", "players": []}}

            tables = soup.select("table.stats-table.totalstats")

            for i, table in enumerate(tables[:2]):
                team_key = "team1" if i == 0 else "team2"

                first_header = table.select_one("thead th")
                if first_header:
                    result[team_key]["name"] = first_header.get_text(strip=True)

                players = self._parse_stats_table(table)
                result[team_key]["players"] = players

            return result
        except Exception as e:
            logger.error(f"解析地图统计失败: {e}")
            return None

    def _parse_stats_table(self, table) -> List[PlayerStats]:
        """解析选手统计表格"""
        players = []
        try:
            rows = table.select("tbody tr")
            for row in rows:
                cols = row.select("td")
                if len(cols) < 12:
                    continue

                player_elem = cols[0].select_one("a, .player-nick")
                nickname = player_elem.get_text(strip=True) if player_elem else cols[0].get_text(strip=True)

                ok_text = cols[1].get_text(strip=True)
                first_kills, first_deaths = 0, 0
                if ":" in ok_text:
                    parts = ok_text.split(":")
                    first_kills = int(parts[0].strip()) if parts[0].strip().isdigit() else 0
                    first_deaths = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 0

                kast_text = cols[4].get_text(strip=True).replace("%", "")
                kast = float(kast_text) if kast_text.replace(".", "").isdigit() else 0.0

                clutch_text = cols[6].get_text(strip=True)

                k_hs_text = cols[7].get_text(strip=True)
                k_match = re.match(r"(\d+)", k_hs_text)
                kills = int(k_match.group(1)) if k_match else 0
                hs_match = re.search(r"\((\d+)\)", k_hs_text)
                headshots = int(hs_match.group(1)) if hs_match else 0

                assists_text = cols[9].get_text(strip=True) if len(cols) > 9 else "0"
                assists_match = re.match(r"(\d+)", assists_text)
                assists = int(assists_match.group(1)) if assists_match else 0

                deaths_text = cols[10].get_text(strip=True) if len(cols) > 10 else "0"
                deaths_match = re.match(r"(\d+)", deaths_text)
                deaths = int(deaths_match.group(1)) if deaths_match else 0

                adr_text = cols[12].get_text(strip=True) if len(cols) > 12 else "0"
                try:
                    adr = float(adr_text)
                except Exception:
                    adr = 0.0

                rating_text = cols[-1].get_text(strip=True)
                try:
                    rating = float(rating_text)
                except Exception:
                    rating = 0.0

                players.append(PlayerStats(
                    nickname=nickname,
                    kills=kills,
                    deaths=deaths,
                    assists=assists,
                    kast=kast,
                    headshots=headshots,
                    rating=rating,
                    adr=adr,
                    first_kills=first_kills,
                    first_deaths=first_deaths,
                    clutches=clutch_text,
                ))
        except Exception as e:
            logger.debug(f"解析统计表格失败: {e}")

        return players

    # ============== 比赛结果 ==============

    async def get_results(self, max_results: int = 30) -> List[Dict[str, Any]]:
        """获取比赛结果"""
        cached = self._get_cache("results_list", "results")
        if cached:
            return cached[:max_results]

        html = await self._fetch(f"{self.BASE_URL}/results")
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        results = []

        for result_div in soup.select(".result-con"):
            try:
                link = result_div.select_one("a.a-reset")
                if not link:
                    continue

                href = link.get("href", "")
                parts = href.split("/")
                match_id = parts[2] if len(parts) > 2 else ""

                teams = result_div.select(".team")
                team1 = teams[0].get_text(strip=True) if len(teams) > 0 else "TBD"
                team2 = teams[1].get_text(strip=True) if len(teams) > 1 else "TBD"

                score_elem = result_div.select_one(".result-score")
                score1, score2 = 0, 0
                if score_elem:
                    score_text = score_elem.get_text(strip=True)
                    if "-" in score_text:
                        score_parts = score_text.split("-")
                        score1 = int(score_parts[0].strip()) if score_parts[0].strip().isdigit() else 0
                        score2 = int(score_parts[1].strip()) if len(score_parts) > 1 and score_parts[1].strip().isdigit() else 0

                event_elem = result_div.select_one(".event-name")
                event = event_elem.get_text(strip=True) if event_elem else ""

                results.append({
                    "match_id": match_id,
                    "team1": team1,
                    "team2": team2,
                    "score1": score1,
                    "score2": score2,
                    "event": event,
                    "winner": team1 if score1 > score2 else team2,
                    "url": f"{self.BASE_URL}{href}",
                })
            except Exception as e:
                logger.debug(f"解析结果失败: {e}")

        self._set_cache("results_list", results)
        return results[:max_results]

    # ============== 战队排名 ==============

    async def get_rankings(self, max_teams: int = 30) -> List[TeamInfo]:
        """获取战队排名"""
        cached = self._get_cache("rankings_list", "rankings")
        if cached:
            return cached[:max_teams]

        html = await self._fetch(f"{self.BASE_URL}/ranking/teams")
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        teams = []

        for team_div in soup.select(".ranked-team"):
            try:
                rank_elem = team_div.select_one(".position")
                rank = int(rank_elem.get_text(strip=True).replace("#", "")) if rank_elem else 0

                name_elem = team_div.select_one(".name")
                name = name_elem.get_text(strip=True) if name_elem else ""

                points_elem = team_div.select_one(".points")
                points_text = points_elem.get_text(strip=True) if points_elem else "0"
                points = int(re.sub(r"[^\d]", "", points_text))

                change_elem = team_div.select_one(".change")
                change = change_elem.get_text(strip=True) if change_elem else "-"

                link = team_div.select_one("a.moreLink")
                href = link.get("href", "") if link else ""
                team_id = href.split("/")[-2] if "/" in href else ""

                players = []
                for player_elem in team_div.select(".lineup-con .nick"):
                    players.append(player_elem.get_text(strip=True))

                teams.append(TeamInfo(
                    team_id=team_id,
                    name=name,
                    rank=rank,
                    points=points,
                    change=change,
                    players=players,
                ))
            except Exception as e:
                logger.debug(f"解析排名失败: {e}")

        self._set_cache("rankings_list", teams)
        return teams[:max_teams]

    # ============== 搜索 ==============

    async def search_team(self, name: str) -> Optional[TeamInfo]:
        """搜索战队"""
        teams = await self.get_rankings(max_teams=100)
        name_lower = name.lower()

        for team in teams:
            if name_lower in team.name.lower():
                return team
        return None


# 全局实例
scraper = HLTVScraper()
