#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CS2 HLTV插件 v5.1.0 - 支持可选实时数据
直接集成爬虫，无需额外服务
可选启用 Playwright 或 BO3.gg 实时数据源
"""

from typing import List, Type, Any
import logging
from datetime import datetime

# MaiBot imports
from maibot.plugin import BaseTool, BaseAction, BasePlugin

# 导入内置爬虫和实时数据管理器
from .hltv_scraper import scraper, live_manager, HAS_DEPENDENCIES

# 设置日志
logger = logging.getLogger("plugin")


# ============== 工具定义 ==============


class GetMatchesTool(BaseTool):
    """获取比赛列表工具"""

    name = "GetMatchesTool"
    description = "获取CS2即将进行和正在进行的比赛列表。当用户询问今天有什么比赛、最近比赛安排时使用。"

    parameters = {
        "team_filter": {
            "type": "string",
            "description": "按战队名称过滤（可选）",
            "required": False,
        },
        "max_matches": {
            "type": "integer",
            "description": "返回的最大比赛数量",
            "default": 10,
        },
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        team_filter = function_args.get("team_filter", "")
        max_matches = function_args.get("max_matches", 10)

        if not HAS_DEPENDENCIES:
            return {
                "name": self.name,
                "content": "❌ HLTV 爬虫依赖未安装。请运行: pip install curl_cffi beautifulsoup4 lxml",
            }

        try:
            matches = await scraper.get_matches()

            if team_filter:
                matches = [
                    m
                    for m in matches
                    if team_filter.lower() in m["team1"].lower()
                    or team_filter.lower() in m["team2"].lower()
                ]

            if not matches:
                return {"name": self.name, "content": "当前没有找到比赛信息"}

            matches = matches[:max_matches]

            content = f"📅 CS2 比赛列表 ({len(matches)} 场):\n\n"
            for i, m in enumerate(matches, 1):
                status_icon = "🔴" if m["status"] == "live" else "⏰"
                content += f"{i}. {status_icon} {m['team1']} vs {m['team2']}\n"
                if m["time"]:
                    content += f"   时间: {m['time']}\n"
                if m["event"]:
                    content += f"   赛事: {m['event'][:50]}\n"
                content += "\n"

            return {"name": self.name, "content": content.strip()}

        except Exception as e:
            logger.error(f"GetMatchesTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取比赛列表失败: {e}"}


class GetMatchDetailTool(BaseTool):
    """获取比赛详情工具（包含 Scoreboard）"""

    name = "GetMatchDetailTool"
    description = "获取CS2比赛的详细信息，包括比分、地图、Veto等。当用户询问某场比赛的详细情况、比分时使用。"

    parameters = {
        "match_id": {
            "type": "string",
            "description": "比赛ID（从比赛列表获取）",
            "required": False,
        },
        "team_name": {
            "type": "string",
            "description": "战队名称（用于查找比赛）",
            "required": False,
        },
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        match_id = function_args.get("match_id", "")
        team_name = function_args.get("team_name", "")

        if not HAS_DEPENDENCIES:
            return {
                "name": self.name,
                "content": "❌ HLTV 爬虫依赖未安装",
            }

        try:
            # 如果没有 match_id，通过战队名查找
            if not match_id and team_name:
                matches = await scraper.get_matches()
                for m in matches:
                    if team_name.lower() in m["team1"].lower() or team_name.lower() in m["team2"].lower():
                        match_id = m["match_id"]
                        break

            if not match_id:
                return {"name": self.name, "content": "请提供比赛ID或战队名称"}

            detail = await scraper.get_match_detail(match_id)
            if not detail:
                return {"name": self.name, "content": f"未找到比赛 {match_id} 的详情"}

            # 构建输出
            status_map = {"live": "🔴 进行中", "scheduled": "⏰ 即将开始", "finished": "✅ 已结束"}
            status = status_map.get(detail.status, detail.status)

            content = f"📊 比赛详情\n\n"
            content += f"🏆 {detail.team1} {detail.team1_score} - {detail.team2_score} {detail.team2}\n"
            content += f"状态: {status}\n"
            if detail.event:
                content += f"赛事: {detail.event}\n"
            if detail.format:
                content += f"赛制: {detail.format.upper()}\n"
            if detail.date:
                content += f"日期: {detail.date}\n"

            # 地图信息
            if detail.maps:
                content += f"\n🗺️ 地图 ({len(detail.maps)} 张):\n"
                for i, map_result in enumerate(detail.maps, 1):
                    content += f"  Map {i}: {map_result.map_name} - {map_result.team1_score}:{map_result.team2_score}\n"

            # Veto 信息
            if detail.veto:
                content += f"\n📋 Veto:\n"
                for v in detail.veto[:6]:
                    content += f"  • {v}\n"

            return {"name": self.name, "content": content.strip()}

        except Exception as e:
            logger.error(f"GetMatchDetailTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取比赛详情失败: {e}"}


class GetMapStatsTool(BaseTool):
    """获取地图统计工具（Scoreboard）"""

    name = "GetMapStatsTool"
    description = "获取CS2比赛某张地图的详细统计数据（Scoreboard），包括选手K/D/A、ADR、Rating、KAST等。当用户询问比赛数据、选手表现、Scoreboard时使用。"

    parameters = {
        "match_id": {
            "type": "string",
            "description": "比赛ID",
            "required": False,
        },
        "team_name": {
            "type": "string",
            "description": "战队名称（用于查找比赛）",
            "required": False,
        },
        "map_index": {
            "type": "integer",
            "description": "地图序号（从1开始，默认1）",
            "default": 1,
        },
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        match_id = function_args.get("match_id", "")
        team_name = function_args.get("team_name", "")
        map_index = function_args.get("map_index", 1)

        if not HAS_DEPENDENCIES:
            return {"name": self.name, "content": "❌ HLTV 爬虫依赖未安装"}

        try:
            # 查找比赛
            if not match_id and team_name:
                # 先从结果中查找
                results = await scraper.get_results(max_results=20)
                for r in results:
                    if team_name.lower() in r["team1"].lower() or team_name.lower() in r["team2"].lower():
                        match_id = r["match_id"]
                        break

            if not match_id:
                return {"name": self.name, "content": "请提供比赛ID或战队名称"}

            # 获取比赛详情
            detail = await scraper.get_match_detail(match_id)
            if not detail or not detail.maps:
                return {"name": self.name, "content": "未找到地图数据"}

            if map_index < 1 or map_index > len(detail.maps):
                return {"name": self.name, "content": f"地图序号无效，该比赛共 {len(detail.maps)} 张地图"}

            map_result = detail.maps[map_index - 1]
            if not map_result.stats_url:
                return {"name": self.name, "content": "该地图暂无详细统计数据"}

            # 获取地图统计
            stats = await scraper.get_map_stats(map_result.stats_url)
            if not stats:
                return {"name": self.name, "content": "获取地图统计失败"}

            # 构建 Scoreboard
            content = f"📊 {map_result.map_name} Scoreboard\n"
            content += f"🏆 {detail.team1} {map_result.team1_score} - {map_result.team2_score} {detail.team2}\n"
            content += f"📅 {detail.event}\n\n"

            for team_key in ["team1", "team2"]:
                team_data = stats.get(team_key, {})
                team_name_display = team_data.get("name", team_key)
                players = team_data.get("players", [])

                content += f"【{team_name_display}】\n"
                content += f"{'选手':<10} {'K':>3} {'A':>3} {'D':>3} {'ADR':>5} {'KAST':>5} {'Rating':>6}\n"
                content += "-" * 45 + "\n"

                for p in players:
                    content += f"{p.nickname:<10} {p.kills:>3} {p.assists:>3} {p.deaths:>3} {p.adr:>5.1f} {p.kast:>4.0f}% {p.rating:>6.2f}\n"
                content += "\n"

            return {"name": self.name, "content": content.strip()}

        except Exception as e:
            logger.error(f"GetMapStatsTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取地图统计失败: {e}"}


class GetMatchResultsTool(BaseTool):
    """获取比赛结果工具"""

    name = "GetMatchResultsTool"
    description = "获取最近的CS2比赛结果。当用户询问比赛结果、谁赢了时使用。"

    parameters = {
        "team_filter": {
            "type": "string",
            "description": "按战队名称过滤（可选）",
            "required": False,
        },
        "max_results": {
            "type": "integer",
            "description": "返回的最大结果数量",
            "default": 10,
        },
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        team_filter = function_args.get("team_filter", "")
        max_results = function_args.get("max_results", 10)

        if not HAS_DEPENDENCIES:
            return {"name": self.name, "content": "❌ HLTV 爬虫依赖未安装"}

        try:
            results = await scraper.get_results(max_results=50)

            if team_filter:
                results = [
                    r
                    for r in results
                    if team_filter.lower() in r["team1"].lower()
                    or team_filter.lower() in r["team2"].lower()
                ]

            if not results:
                msg = f"未找到{' ' + team_filter + ' 的' if team_filter else ''}比赛结果"
                return {"name": self.name, "content": msg}

            results = results[:max_results]

            content = f"📋 最近比赛结果 ({len(results)} 场):\n\n"
            for i, r in enumerate(results, 1):
                winner_mark = "🏆" if r["score1"] > r["score2"] else ""
                loser_mark = "🏆" if r["score2"] > r["score1"] else ""
                content += f"{i}. {winner_mark}{r['team1']} {r['score1']}-{r['score2']} {r['team2']}{loser_mark}\n"
                if r["event"]:
                    content += f"   赛事: {r['event'][:40]}\n"
                content += "\n"

            return {"name": self.name, "content": content.strip()}

        except Exception as e:
            logger.error(f"GetMatchResultsTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取比赛结果失败: {e}"}


class GetTeamRankingsTool(BaseTool):
    """获取战队排名工具"""

    name = "GetTeamRankingsTool"
    description = "获取CS2战队世界排名。当用户询问排名、哪个队最强时使用。"

    parameters = {
        "max_teams": {
            "type": "integer",
            "description": "返回的战队数量",
            "default": 10,
        }
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        max_teams = function_args.get("max_teams", 10)

        if not HAS_DEPENDENCIES:
            return {"name": self.name, "content": "❌ HLTV 爬虫依赖未安装"}

        try:
            teams = await scraper.get_rankings(max_teams=max_teams)

            if not teams:
                return {"name": self.name, "content": "未获取到排名数据"}

            content = f"🏆 CS2 战队世界排名 (Top {len(teams)}):\n\n"
            for team in teams:
                change_icon = "🔺" if "+" in team.change else ("🔻" if "-" in team.change else "➖")
                content += f"#{team.rank} {team.name} - {team.points}分 {change_icon}{team.change}\n"
                if team.players:
                    content += f"   选手: {', '.join(team.players[:5])}\n"

            return {"name": self.name, "content": content.strip()}

        except Exception as e:
            logger.error(f"GetTeamRankingsTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取排名失败: {e}"}


class GetTeamInfoTool(BaseTool):
    """获取战队信息工具"""

    name = "GetTeamInfoTool"
    description = "获取CS2战队的详细信息，包括排名、积分、选手阵容等。当用户询问某个战队时使用。"

    parameters = {
        "team_name": {
            "type": "string",
            "description": "战队名称",
            "required": True,
        }
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        team_name = function_args.get("team_name", "")

        if not team_name:
            return {"name": self.name, "content": "请提供战队名称"}

        if not HAS_DEPENDENCIES:
            return {"name": self.name, "content": "❌ HLTV 爬虫依赖未安装"}

        try:
            team = await scraper.search_team(team_name)

            if not team:
                return {"name": self.name, "content": f"未找到战队: {team_name}"}

            content = f"🎮 {team.name} 战队信息\n\n"
            content += f"世界排名: #{team.rank}\n"
            content += f"积分: {team.points}\n"
            content += f"排名变化: {team.change}\n"

            if team.players:
                content += f"\n👥 选手阵容:\n"
                for p in team.players:
                    content += f"  • {p}\n"

            # 获取近期比赛
            results = await scraper.get_results(max_results=20)
            team_results = [
                r
                for r in results
                if team_name.lower() in r["team1"].lower() or team_name.lower() in r["team2"].lower()
            ][:5]

            if team_results:
                content += f"\n📋 近期战绩:\n"
                for r in team_results:
                    result_icon = "✅" if r["winner"].lower() == team.name.lower() else "❌"
                    content += f"  {result_icon} vs {r['team2'] if team.name.lower() in r['team1'].lower() else r['team1']} ({r['score1']}-{r['score2']})\n"

            return {"name": self.name, "content": content.strip()}

        except Exception as e:
            logger.error(f"GetTeamInfoTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取战队信息失败: {e}"}


class GetLiveMatchTool(BaseTool):
    """获取正在进行的比赛工具（实时数据）"""

    name = "GetLiveMatchTool"
    description = "获取当前正在进行的CS2直播比赛的实时数据，包括地图比分和回合比分。当用户询问现在有什么比赛、直播、比分多少时使用。适合实时讨论场景。"

    parameters = {
        "team_filter": {
            "type": "string",
            "description": "按战队名称过滤（可选）",
            "required": False,
        }
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        team_filter = function_args.get("team_filter", "")

        if not HAS_DEPENDENCIES:
            return {"name": self.name, "content": "❌ HLTV 爬虫依赖未安装"}

        try:
            # 使用实时数据管理器（如果启用）
            live_matches = await live_manager.get_live_matches()

            if team_filter:
                live_matches = [
                    m
                    for m in live_matches
                    if team_filter.lower() in m.team1.lower() or team_filter.lower() in m.team2.lower()
                ]

            if not live_matches:
                msg = "🔴 当前没有正在进行的比赛"
                if team_filter:
                    msg += f"（{team_filter} 相关）"
                return {"name": self.name, "content": msg}

            # 显示数据源信息
            source_info = ""
            if live_manager.is_enabled:
                source_info = f" [数据源: {live_manager.provider_type}]"

            content = f"🔴 正在进行的比赛 ({len(live_matches)} 场){source_info}:\n\n"
            for m in live_matches:
                content += f"🎮 {m.team1} vs {m.team2}\n"
                content += f"   📊 地图比分: {m.team1_map_score} - {m.team2_map_score}"
                if m.format:
                    content += f" ({m.format.upper()})"
                content += "\n"
                if m.current_map:
                    content += f"   🗺️ 当前地图: {m.current_map}\n"
                if m.team1_round_score or m.team2_round_score:
                    content += f"   🎯 回合比分: {m.team1_round_score} - {m.team2_round_score}\n"
                if m.event:
                    content += f"   🏆 {m.event}\n"
                content += "\n"

            return {"name": self.name, "content": content.strip()}

        except Exception as e:
            logger.error(f"GetLiveMatchTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取直播比赛失败: {e}"}


class GetLiveScoreTool(BaseTool):
    """获取直播比赛实时比分工具"""

    name = "GetLiveScoreTool"
    description = "获取指定战队正在进行的比赛的实时比分。当群友正在讨论某场直播比赛、询问比分时使用。"

    parameters = {
        "team_name": {
            "type": "string",
            "description": "战队名称",
            "required": True,
        }
    }

    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        team_name = function_args.get("team_name", "")

        if not team_name:
            return {"name": self.name, "content": "请提供战队名称"}

        if not HAS_DEPENDENCIES:
            return {"name": self.name, "content": "❌ HLTV 爬虫依赖未安装"}

        try:
            # 使用实时数据管理器
            live_matches = await live_manager.get_live_matches()

            # 查找相关比赛
            target_match = None
            for m in live_matches:
                if team_name.lower() in m.team1.lower() or team_name.lower() in m.team2.lower():
                    target_match = m
                    break

            if not target_match:
                return {
                    "name": self.name,
                    "content": f"❌ {team_name} 当前没有正在进行的比赛",
                }

            # 构建实时比分信息
            source_info = f" [{live_manager.provider_type}]" if live_manager.is_enabled else ""
            content = f"🔴 实时比分{source_info}\n\n"
            content += f"🎮 {target_match.team1} vs {target_match.team2}\n"
            content += f"━━━━━━━━━━━━━━━━━━━━\n"
            content += f"📊 地图: {target_match.team1_map_score} - {target_match.team2_map_score}"
            if target_match.format:
                content += f" ({target_match.format.upper()})"
            content += "\n"

            if target_match.current_map:
                content += f"🗺️ 当前: {target_match.current_map}\n"

            if target_match.team1_round_score or target_match.team2_round_score:
                content += f"🎯 回合: {target_match.team1_round_score} - {target_match.team2_round_score}\n"

            # 判断领先情况
            if target_match.team1_map_score > target_match.team2_map_score:
                content += f"📈 {target_match.team1} 领先\n"
            elif target_match.team2_map_score > target_match.team1_map_score:
                content += f"📈 {target_match.team2} 领先\n"
            else:
                content += f"⚖️ 比分持平\n"

            content += f"━━━━━━━━━━━━━━━━━━━━\n"
            content += f"🏆 {target_match.event}"

            return {"name": self.name, "content": content}

        except Exception as e:
            logger.error(f"GetLiveScoreTool 执行失败: {e}")
            return {"name": self.name, "content": f"获取实时比分失败: {e}"}


# ============== Action ==============


class CS2TopicDetectionAction(BaseAction):
    """CS2话题检测Action - 检测群聊中的CS2相关话题"""

    name = "CS2TopicDetectionAction"
    description = "检测群聊中的CS2相关话题讨论，识别是否在讨论比赛、战队或选手"

    # CS2 相关关键词
    TEAM_KEYWORDS = [
        "navi", "faze", "vitality", "astralis", "g2", "spirit", "furia", "mouz",
        "liquid", "cloud9", "c9", "ence", "heroic", "big", "og", "nip", "fnatic",
        "falcons", "mongolz", "pain", "imperial", "mibr", "aurora", "eternal fire",
    ]

    PLAYER_KEYWORDS = [
        "s1mple", "zywoo", "m0nesy", "donk", "niko", "device", "ropz", "twistzz",
        "electronic", "b1t", "jl", "broky", "rain", "karrigan", "fallen", "coldzera",
    ]

    GAME_KEYWORDS = [
        "cs2", "csgo", "cs", "反恐精英", "hltv", "major", "比赛", "战队", "选手",
        "排名", "rating", "adr", "kast", "ace", "clutch", "eco", "force buy",
        "地图", "inferno", "mirage", "nuke", "ancient", "anubis", "vertigo", "dust2",
    ]

    LIVE_KEYWORDS = [
        "直播", "live", "比分", "几比几", "谁赢", "打到", "领先", "落后", "加时",
        "半场", "换边", "经济", "手枪局", "枪局",
    ]

    async def execute(self, message_data: dict) -> dict:
        message_content = message_data.get("content", "").lower()

        # 检测各类关键词
        detected_teams = [kw for kw in self.TEAM_KEYWORDS if kw in message_content]
        detected_players = [kw for kw in self.PLAYER_KEYWORDS if kw in message_content]
        detected_game = [kw for kw in self.GAME_KEYWORDS if kw in message_content]
        detected_live = [kw for kw in self.LIVE_KEYWORDS if kw in message_content]

        is_cs2_topic = bool(detected_teams or detected_players or detected_game)
        is_live_discussion = bool(detected_live) and is_cs2_topic

        result = {
            "detected": is_cs2_topic,
            "is_live_discussion": is_live_discussion,
            "teams": detected_teams,
            "players": detected_players,
            "game_terms": detected_game,
            "live_terms": detected_live,
        }

        if is_cs2_topic:
            logger.info(f"检测到CS2话题: teams={detected_teams}, players={detected_players}, live={is_live_discussion}")

        return result


# ============== 插件主类 ==============


class CS2HLTVPlugin(BasePlugin):
    """CS2 HLTV插件主类"""

    name = "cs2_hltv_plugin"
    version = "5.1.0"
    description = "CS2/CSGO数据查询插件：开箱即用，支持可选实时数据源（Playwright/BO3.gg）"

    dependencies = []

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("plugin")

    async def on_plugin_load(self):
        """插件加载时的初始化"""
        self.logger.info("CS2 HLTV插件 v5.1.0 已加载")

        if HAS_DEPENDENCIES:
            self.logger.info("✓ 爬虫依赖已安装，插件功能正常")
        else:
            self.logger.warning("✗ 爬虫依赖未安装，请运行: pip install curl_cffi beautifulsoup4 lxml")

        # 加载实时数据配置
        self._load_live_data_config()

    def _load_live_data_config(self):
        """加载实时数据配置"""
        try:
            import tomllib
            from pathlib import Path

            config_path = Path(__file__).parent / "config.toml"
            if config_path.exists():
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)

                live_config = config.get("live_data", {})
                if live_config.get("enabled", False):
                    provider = live_config.get("provider", "bo3gg")
                    provider_config = live_config.get(provider, {})

                    live_manager.configure(
                        enabled=True,
                        provider=provider,
                        fallback_to_hltv=live_config.get("fallback_to_hltv", True),
                        **provider_config
                    )
                    self.logger.info(f"✓ 实时数据已启用 (provider={provider})")
                else:
                    self.logger.info("ℹ 实时数据未启用，使用 HLTV 静态数据")
            else:
                self.logger.info("ℹ 未找到配置文件，使用默认设置")
        except Exception as e:
            self.logger.warning(f"加载实时数据配置失败: {e}")

    async def on_plugin_unload(self):
        """插件卸载时的清理"""
        # 关闭实时数据管理器
        await live_manager.close()
        self.logger.info("CS2 HLTV插件已卸载")

    def get_tools(self) -> List[Type[BaseTool]]:
        """返回工具列表"""
        return [
            # 查询类工具
            GetMatchesTool,
            GetMatchDetailTool,
            GetMapStatsTool,
            GetMatchResultsTool,
            GetTeamRankingsTool,
            GetTeamInfoTool,
            # 实时类工具
            GetLiveMatchTool,
            GetLiveScoreTool,
        ]

    def get_actions(self) -> List[Type[BaseAction]]:
        """返回Action列表"""
        return [CS2TopicDetectionAction]


# 导出插件类
plugin_class = CS2HLTVPlugin
