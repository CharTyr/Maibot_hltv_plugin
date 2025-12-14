#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HLTV Scraper - 直接集成到插件中的爬虫模块
使用 curl_cffi 绕过 Cloudflare，无需额外服务
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache

logger = logging.getLogger("plugin")

# 尝试导入依赖
try:
    from curl_cffi import requests as curl_requests
    from bs4 import BeautifulSoup

    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    logger.warning(f"HLTV 爬虫依赖未安装: {e}")
    logger.warning("请运行: pip install curl_cffi beautifulsoup4 lxml")


# ============== 数据模型 ==============


@dataclass
class PlayerStats:
    """选手统计数据"""

    nickname: str
    team: str = ""
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    adr: float = 0.0  # Average Damage per Round
    kast: float = 0.0  # Kill/Assist/Survive/Trade %
    rating: float = 0.0  # HLTV 2.0 Rating
    headshots: int = 0
    first_kills: int = 0
    first_deaths: int = 0
    clutches: str = ""  # 1vX 成功次数


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
    team1_map_score: int = 0  # 地图比分 (e.g., 1-0)
    team2_map_score: int = 0
    current_map: str = ""  # 当前地图名
    team1_round_score: int = 0  # 当前地图回合比分
    team2_round_score: int = 0
    event: str = ""
    format: str = ""  # bo1, bo3, bo5
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
    status: str = "scheduled"  # live, scheduled, finished
    format: str = ""  # bo1, bo3, bo5
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
    dpr: float = 0.0  # Deaths per round
    kast: float = 0.0
    impact: float = 0.0
    adr: float = 0.0
    kpr: float = 0.0  # Kills per round


# ============== 爬虫核心 ==============


class HLTVScraper:
    """HLTV 数据爬虫"""

    BASE_URL = "https://www.hltv.org"

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._cache_ttl = {
            "matches": 120,  # 2 分钟
            "rankings": 3600,  # 1 小时
            "results": 600,  # 10 分钟
            "match_detail": 60,  # 1 分钟（直播时需要频繁更新）
            "player": 3600,  # 1 小时
            "team": 1800,  # 30 分钟
        }

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

    async def _fetch(self, url: str, retries: int = 3) -> Optional[str]:
        """获取页面内容（带重试）"""
        if not HAS_DEPENDENCIES:
            return None

        for attempt in range(retries):
            try:
                # 添加随机延迟避免被限流
                if attempt > 0:
                    await asyncio.sleep(1 + attempt)
                
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, lambda: curl_requests.get(url, impersonate="chrome", timeout=30)
                )
                if response.status_code == 200:
                    return response.text
                elif response.status_code == 403:
                    logger.warning(f"请求被拦截 (尝试 {attempt + 1}/{retries}): {url}")
                    continue
                else:
                    logger.warning(f"请求失败: {url} -> {response.status_code}")
            except Exception as e:
                logger.error(f"请求错误: {url} -> {e}")
        
        return None

    # ============== 比赛列表 ==============

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

        # 解析比赛链接
        for link in soup.select("a.match-teams"):
            try:
                href = link.get("href", "")
                if not href:
                    continue

                parts = href.split("/")
                match_id = parts[2] if len(parts) > 2 else ""

                team1_elem = link.select_one(".team1")
                team2_elem = link.select_one(".team2")
                team1 = team1_elem.get_text(strip=True) if team1_elem else "TBD"
                team2 = team2_elem.get_text(strip=True) if team2_elem else "TBD"

                if not team1 or not team2:
                    continue

                parent = link.parent
                time_elem = parent.select_one(".match-time") if parent else None
                match_time = time_elem.get_text(strip=True) if time_elem else ""

                # 从 URL 提取赛事名
                event = "-".join(parts[3:]).replace("-", " ").title() if len(parts) > 3 else ""

                # 检查是否直播
                is_live = "live" in str(link.get("class", [])).lower()

                matches.append(
                    {
                        "match_id": match_id,
                        "team1": team1,
                        "team2": team2,
                        "event": event,
                        "time": match_time,
                        "status": "live" if is_live else "scheduled",
                        "url": f"{self.BASE_URL}{href}",
                    }
                )
            except Exception as e:
                logger.debug(f"解析比赛失败: {e}")

        self._set_cache("matches_list", matches)
        logger.info(f"获取到 {len(matches)} 场比赛")
        return matches

    # ============== 直播比赛 ==============

    async def get_live_matches(self, fetch_details: bool = True) -> List[LiveMatch]:
        """获取正在进行的直播比赛（实时数据，短缓存）
        
        Args:
            fetch_details: 是否获取详情页面以获取更准确的地图比分
        """
        cache_key = "live_matches"
        cached = self._get_cache(cache_key, "match_detail")  # 使用短缓存
        if cached:
            return cached

        html = await self._fetch(f"{self.BASE_URL}/matches")
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        live_matches = []

        # 查找直播比赛区域
        live_section = soup.select_one(".liveMatches")
        if not live_section:
            return []

        for match_container in live_section.select(".live-match-container"):
            try:
                live_match = self._parse_live_match(match_container)
                if live_match:
                    # 如果需要详情，从比赛详情页获取更准确的数据
                    if fetch_details and live_match.url:
                        detailed = await self._fetch_live_match_detail(live_match)
                        if detailed:
                            live_match = detailed
                    live_matches.append(live_match)
            except Exception as e:
                logger.debug(f"解析直播比赛失败: {e}")

        self._set_cache(cache_key, live_matches)
        logger.info(f"获取到 {len(live_matches)} 场直播比赛")
        return live_matches

    async def _fetch_live_match_detail(self, live_match: LiveMatch) -> Optional[LiveMatch]:
        """从比赛详情页获取更准确的直播数据"""
        html = await self._fetch(live_match.url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        try:
            # 获取地图信息
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
                    
                    # 检查是否是正在进行的地图（比分不是 "-"）
                    if t1_score_text != "-" and t2_score_text != "-":
                        try:
                            t1_score = int(t1_score_text)
                            t2_score = int(t2_score_text)
                            
                            # 判断地图是否已结束（一方达到 13+ 且领先 2 分以上，或加时赛结束）
                            if (t1_score >= 13 and t1_score - t2_score >= 2) or \
                               (t2_score >= 13 and t2_score - t1_score >= 2) or \
                               (t1_score >= 13 and t2_score >= 13 and abs(t1_score - t2_score) >= 2):
                                # 地图已结束
                                if t1_score > t2_score:
                                    team1_maps_won += 1
                                else:
                                    team2_maps_won += 1
                            else:
                                # 这是当前正在进行的地图
                                current_map = map_name
                                current_map_t1_score = t1_score
                                current_map_t2_score = t2_score
                        except ValueError:
                            pass

            # 获取赛制
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
            # 获取比赛链接和ID
            match_link = container.select_one("a.match-teams, a.match-info")
            if not match_link:
                return None

            href = match_link.get("href", "")
            parts = href.split("/")
            match_id = parts[2] if len(parts) > 2 else ""

            # 获取队伍名称
            team_names = container.select(".match-teamname")
            team1 = team_names[0].get_text(strip=True) if len(team_names) > 0 else "TBD"
            team2 = team_names[1].get_text(strip=True) if len(team_names) > 1 else "TBD"

            # 获取地图比分 (总比分)
            map_scores = container.select(".map-score")
            team1_map_score = 0
            team2_map_score = 0
            if len(map_scores) >= 2:
                try:
                    t1_text = map_scores[0].get_text(strip=True).replace("(", "").replace(")", "")
                    t2_text = map_scores[1].get_text(strip=True).replace("(", "").replace(")", "")
                    team1_map_score = int(t1_text) if t1_text.isdigit() else 0
                    team2_map_score = int(t2_text) if t2_text.isdigit() else 0
                except:
                    pass

            # 获取当前地图回合比分
            round_scores = container.select(".current-map-score")
            team1_round_score = 0
            team2_round_score = 0
            if len(round_scores) >= 2:
                try:
                    team1_round_score = int(round_scores[0].get_text(strip=True) or 0)
                    team2_round_score = int(round_scores[1].get_text(strip=True) or 0)
                except:
                    pass

            # 获取赛事
            event_elem = container.select_one(".match-event .text-ellipsis")
            event = event_elem.get_text(strip=True) if event_elem else ""

            # 获取赛制
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
        """获取比赛详情（包含 Scoreboard）"""
        cache_key = f"match_{match_id}"
        cached = self._get_cache(cache_key, "match_detail")
        if cached:
            return cached

        # 如果没有提供 URL，尝试从比赛列表和结果列表中查找
        if not match_url:
            # 先从比赛列表查找
            matches = await self.get_matches()
            for m in matches:
                if m["match_id"] == match_id:
                    match_url = m["url"]
                    break
            
            # 如果没找到，从结果列表查找
            if not match_url:
                results = await self.get_results(max_results=50)
                for r in results:
                    if r["match_id"] == match_id:
                        match_url = r["url"]
                        break

        # 如果还是没有 URL，无法获取详情
        if not match_url:
            logger.warning(f"未找到比赛 {match_id} 的 URL")
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
            # 获取队伍名称
            teams = soup.select(".teamName")
            team1 = teams[0].get_text(strip=True) if len(teams) > 0 else "TBD"
            team2 = teams[1].get_text(strip=True) if len(teams) > 1 else "TBD"

            # 获取比分
            scores = soup.select(".team .won, .team .lost, .team .tie")
            team1_score = 0
            team2_score = 0
            if len(scores) >= 2:
                try:
                    team1_score = int(scores[0].get_text(strip=True))
                    team2_score = int(scores[1].get_text(strip=True))
                except:
                    pass

            # 获取赛事
            event_elem = soup.select_one(".event a")
            event = event_elem.get_text(strip=True) if event_elem else ""

            # 获取日期
            date_elem = soup.select_one(".date")
            date = date_elem.get_text(strip=True) if date_elem else ""

            # 获取比赛格式
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

            # 判断状态
            status = "finished"
            if soup.select_one(".countdown"):
                status = "scheduled"
            elif soup.select_one(".liveMatch, .live-match"):
                status = "live"

            # 解析地图
            maps = []
            for mapholder in soup.select(".mapholder"):
                map_result = self._parse_map_result(mapholder)
                if map_result:
                    maps.append(map_result)

            # 解析 Veto
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

            # 获取半场比分
            half_scores = mapholder.select(".results-center-half-score")
            t1_ct, t1_t, t2_ct, t2_t = 0, 0, 0, 0
            # 解析半场比分逻辑...

            # 获取统计链接
            stats_link = mapholder.select_one("a[href*='mapstatsid']")
            stats_url = ""
            if stats_link:
                stats_url = f"{self.BASE_URL}{stats_link.get('href', '')}"

            return MapResult(
                map_name=map_name,
                team1_score=team1_score,
                team2_score=team2_score,
                team1_ct_score=t1_ct,
                team1_t_score=t1_t,
                team2_ct_score=t2_ct,
                team2_t_score=t2_t,
                stats_url=stats_url,
            )
        except Exception as e:
            logger.debug(f"解析地图结果失败: {e}")
            return None

    # ============== 地图统计（Scoreboard） ==============

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

    def _parse_map_stats(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """解析地图统计页面"""
        try:
            result = {"team1": {"name": "", "players": []}, "team2": {"name": "", "players": []}}

            # 解析统计表格（只取 totalstats 表格，跳过 CT/T 分开的表格）
            tables = soup.select("table.stats-table.totalstats")
            
            for i, table in enumerate(tables[:2]):
                team_key = "team1" if i == 0 else "team2"
                
                # 从表头获取队伍名称
                first_header = table.select_one("thead th")
                if first_header:
                    result[team_key]["name"] = first_header.get_text(strip=True)
                
                # 解析选手数据
                players = self._parse_stats_table(table)
                result[team_key]["players"] = players

            return result
        except Exception as e:
            logger.error(f"解析地图统计失败: {e}")
            return None

    def _parse_stats_table(self, table) -> List[PlayerStats]:
        """解析选手统计表格
        
        表格结构 (18列):
        [0] 选手名
        [1] Op.K-D (Opening K-D)
        [2] Op.eK-eD
        [3] MKs (Multi-kills)
        [4] KAST
        [5] eKAST
        [6] 1vsX (Clutches)
        [7] K(hs) (Kills with headshots)
        [8] eK(hs)
        [9] A(f) (Assists with flash)
        [10] D(t) (Deaths with trade)
        [11] eD(t)
        [12] ADR
        [13] eADR
        [14] KAST (duplicate)
        [15] eKAST (duplicate)
        [16] Swing
        [17] Rating3.0
        """
        players = []
        try:
            rows = table.select("tbody tr")
            for row in rows:
                cols = row.select("td")
                if len(cols) < 12:
                    continue

                # [0] 选手名
                player_elem = cols[0].select_one("a, .player-nick")
                nickname = player_elem.get_text(strip=True) if player_elem else cols[0].get_text(strip=True)

                # [1] Opening K-D
                ok_text = cols[1].get_text(strip=True)
                first_kills, first_deaths = 0, 0
                if ":" in ok_text:
                    parts = ok_text.split(":")
                    first_kills = int(parts[0].strip()) if parts[0].strip().isdigit() else 0
                    first_deaths = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 0

                # [4] KAST
                kast_text = cols[4].get_text(strip=True).replace("%", "")
                kast = float(kast_text) if kast_text.replace(".", "").isdigit() else 0.0

                # [6] 1vsX (Clutches)
                clutch_text = cols[6].get_text(strip=True)

                # [7] K(hs)
                k_hs_text = cols[7].get_text(strip=True)
                k_match = re.match(r"(\d+)", k_hs_text)
                kills = int(k_match.group(1)) if k_match else 0
                hs_match = re.search(r"\((\d+)\)", k_hs_text)
                headshots = int(hs_match.group(1)) if hs_match else 0

                # [9] A(f) - Assists
                assists_text = cols[9].get_text(strip=True) if len(cols) > 9 else "0"
                assists_match = re.match(r"(\d+)", assists_text)
                assists = int(assists_match.group(1)) if assists_match else 0

                # [10] D(t) - Deaths
                deaths_text = cols[10].get_text(strip=True) if len(cols) > 10 else "0"
                deaths_match = re.match(r"(\d+)", deaths_text)
                deaths = int(deaths_match.group(1)) if deaths_match else 0

                # [12] ADR
                adr_text = cols[12].get_text(strip=True) if len(cols) > 12 else "0"
                try:
                    adr = float(adr_text)
                except:
                    adr = 0.0

                # [17] Rating (最后一列)
                rating_text = cols[-1].get_text(strip=True)
                try:
                    rating = float(rating_text)
                except:
                    rating = 0.0

                players.append(
                    PlayerStats(
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
                    )
                )
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
                        parts = score_text.split("-")
                        score1 = int(parts[0].strip()) if parts[0].strip().isdigit() else 0
                        score2 = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 0

                event_elem = result_div.select_one(".event-name")
                event = event_elem.get_text(strip=True) if event_elem else ""

                results.append(
                    {
                        "match_id": match_id,
                        "team1": team1,
                        "team2": team2,
                        "score1": score1,
                        "score2": score2,
                        "event": event,
                        "winner": team1 if score1 > score2 else team2,
                        "url": f"{self.BASE_URL}{href}",
                    }
                )
            except Exception as e:
                logger.debug(f"解析结果失败: {e}")

        self._set_cache("results_list", results)
        logger.info(f"获取到 {len(results)} 场比赛结果")
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

                # 获取选手
                players = []
                for player_elem in team_div.select(".lineup-con .player .text-ellipsis"):
                    players.append(player_elem.get_text(strip=True))

                teams.append(
                    TeamInfo(
                        team_id=team_id,
                        name=name,
                        rank=rank,
                        points=points,
                        change=change,
                        players=players,
                    )
                )
            except Exception as e:
                logger.debug(f"解析排名失败: {e}")

        self._set_cache("rankings_list", teams)
        logger.info(f"获取到 {len(teams)} 支战队排名")
        return teams[:max_teams]

    # ============== 选手信息 ==============

    async def get_player_info(self, player_id: str) -> Optional[PlayerInfo]:
        """获取选手详细信息"""
        cache_key = f"player_{player_id}"
        cached = self._get_cache(cache_key, "player")
        if cached:
            return cached

        html = await self._fetch(f"{self.BASE_URL}/stats/players/{player_id}")
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")
        player = self._parse_player_info(soup, player_id)

        if player:
            self._set_cache(cache_key, player)

        return player

    def _parse_player_info(self, soup: BeautifulSoup, player_id: str) -> Optional[PlayerInfo]:
        """解析选手信息页面"""
        try:
            nickname_elem = soup.select_one(".summaryNickname")
            nickname = nickname_elem.get_text(strip=True) if nickname_elem else ""

            name_elem = soup.select_one(".summaryRealname")
            name = name_elem.get_text(strip=True) if name_elem else ""

            team_elem = soup.select_one(".SummaryTeamname a")
            team = team_elem.get_text(strip=True) if team_elem else ""

            # 获取统计数据
            stats = {}
            for stat_box in soup.select(".summaryStatBreakdownDataValue"):
                stat_name = stat_box.find_previous_sibling(class_="summaryStatBreakdownSubHeader")
                if stat_name:
                    stats[stat_name.get_text(strip=True).lower()] = stat_box.get_text(strip=True)

            rating = float(stats.get("rating 2.0", "0").replace(",", ".") or "0")
            dpr = float(stats.get("deaths / round", "0").replace(",", ".") or "0")
            kast = float(stats.get("kast", "0").replace("%", "").replace(",", ".") or "0")
            impact = float(stats.get("impact", "0").replace(",", ".") or "0")
            adr = float(stats.get("damage / round", "0").replace(",", ".") or "0")
            kpr = float(stats.get("kills / round", "0").replace(",", ".") or "0")

            return PlayerInfo(
                player_id=player_id,
                nickname=nickname,
                name=name,
                team=team,
                rating=rating,
                dpr=dpr,
                kast=kast,
                impact=impact,
                adr=adr,
                kpr=kpr,
            )
        except Exception as e:
            logger.error(f"解析选手信息失败: {e}")
            return None

    # ============== 搜索 ==============

    async def search_team(self, name: str) -> Optional[TeamInfo]:
        """搜索战队"""
        teams = await self.get_rankings(max_teams=100)
        name_lower = name.lower()

        for team in teams:
            if name_lower in team.name.lower():
                return team
        return None


# ============== 实时数据管理器 ==============


class LiveDataManager:
    """实时数据管理器 - 整合多个数据源"""

    def __init__(self):
        self._provider = None
        self._provider_type = None
        self._enabled = False
        self._fallback_to_hltv = True

    def configure(
        self,
        enabled: bool = False,
        provider: str = "bo3gg",
        fallback_to_hltv: bool = True,
        **provider_kwargs
    ):
        """配置实时数据管理器
        
        Args:
            enabled: 是否启用实时数据
            provider: 提供者类型 ("playwright" 或 "bo3gg")
            fallback_to_hltv: 当实时数据不可用时是否回退到 HLTV 静态数据
            **provider_kwargs: 提供者特定的配置参数
        """
        self._enabled = enabled
        self._fallback_to_hltv = fallback_to_hltv

        if enabled and provider != self._provider_type:
            # 关闭旧的提供者
            if self._provider:
                asyncio.create_task(self._provider.close())
            
            # 创建新的提供者
            try:
                from .live_providers import create_live_provider
                self._provider = create_live_provider(provider, **provider_kwargs)
                self._provider_type = provider
                logger.info(f"实时数据提供者已配置: {provider}")
            except Exception as e:
                logger.error(f"创建实时数据提供者失败: {e}")
                self._provider = None
                self._provider_type = None

    async def get_live_matches(self) -> List[LiveMatch]:
        """获取直播比赛（优先使用实时数据源）"""
        # 如果启用了实时数据且提供者可用
        if self._enabled and self._provider:
            try:
                live_data = await self._provider.get_live_matches()
                if live_data:
                    # 转换为 LiveMatch 格式
                    return [
                        LiveMatch(
                            match_id=m.match_id,
                            team1=m.team1,
                            team2=m.team2,
                            team1_map_score=m.team1_map_score,
                            team2_map_score=m.team2_map_score,
                            current_map=m.current_map,
                            team1_round_score=m.team1_round_score,
                            team2_round_score=m.team2_round_score,
                            event=m.event,
                            format=m.format,
                            url=m.url,
                        )
                        for m in live_data
                    ]
            except Exception as e:
                logger.warning(f"实时数据获取失败: {e}")

        # 回退到 HLTV 静态数据
        if self._fallback_to_hltv:
            return await scraper.get_live_matches()
        
        return []

    async def get_match_live_data(self, match_id: str, url: str = "") -> Optional[LiveMatch]:
        """获取指定比赛的实时数据"""
        if self._enabled and self._provider:
            try:
                live_data = await self._provider.get_match_live_data(match_id, url)
                if live_data:
                    return LiveMatch(
                        match_id=live_data.match_id,
                        team1=live_data.team1,
                        team2=live_data.team2,
                        team1_map_score=live_data.team1_map_score,
                        team2_map_score=live_data.team2_map_score,
                        current_map=live_data.current_map,
                        team1_round_score=live_data.team1_round_score,
                        team2_round_score=live_data.team2_round_score,
                        event=live_data.event,
                        format=live_data.format,
                        url=live_data.url,
                    )
            except Exception as e:
                logger.warning(f"实时数据获取失败: {e}")

        # 回退到 HLTV
        if self._fallback_to_hltv:
            matches = await scraper.get_live_matches()
            for m in matches:
                if m.match_id == match_id:
                    return m

        return None

    async def close(self):
        """关闭资源"""
        if self._provider:
            await self._provider.close()
            self._provider = None

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def provider_type(self) -> Optional[str]:
        return self._provider_type


# 全局实例
scraper = HLTVScraper()
live_manager = LiveDataManager()
