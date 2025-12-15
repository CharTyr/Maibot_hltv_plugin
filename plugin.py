#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CS2 HLTV插件 v5.2.0 - MaiBot 插件系统兼容版
直接集成爬虫，无需额外服务
"""

from typing import List, Tuple, Type, Optional, Any
from dataclasses import dataclass

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    ComponentInfo,
    ConfigField,
    ActionActivationType,
)
from src.common.logger import get_logger

# 导入内置爬虫
from .hltv_scraper import scraper, live_manager, HAS_DEPENDENCIES

logger = get_logger("HLTVPlugin")


# ============== Action 组件 ==============


class GetMatchesAction(BaseAction):
    """获取比赛列表 Action"""

    action_name = "hltv_get_matches"
    action_description = "获取CS2即将进行和正在进行的比赛列表，包括时间、战队、赛事信息"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "team_filter": "按战队名称过滤（可选）",
        "max_matches": "返回的最大比赛数量（默认10）",
    }

    action_require = [
        "当用户询问今天有什么CS2比赛时使用",
        "当用户询问最近的比赛安排时使用",
        "当用户想知道某个战队的比赛时使用",
        "当用户问有没有比赛可以看时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装。请运行: pip install curl_cffi beautifulsoup4 lxml"

        try:
            team_filter = self.action_data.get("team_filter", "")
            max_matches = int(self.action_data.get("max_matches", 10))

            matches = await scraper.get_matches()

            if team_filter:
                matches = [
                    m for m in matches
                    if team_filter.lower() in m["team1"].lower()
                    or team_filter.lower() in m["team2"].lower()
                ]

            if not matches:
                return True, "当前没有找到比赛信息"

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

            return True, content.strip()

        except Exception as e:
            logger.error(f"GetMatchesAction 执行失败: {e}")
            return False, f"获取比赛列表失败: {e}"


class GetMatchDetailAction(BaseAction):
    """获取比赛详情 Action"""

    action_name = "hltv_get_match_detail"
    action_description = "获取CS2比赛的详细信息，包括比分、地图、Veto等"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "match_id": "比赛ID（从比赛列表获取，可选）",
        "team_name": "战队名称（用于查找比赛，可选）",
    }

    action_require = [
        "当用户询问某场比赛的详细情况时使用",
        "当用户询问比赛比分时使用",
        "当用户想知道比赛的地图ban/pick时使用",
        "当用户问某场比赛打到哪了时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装"

        try:
            match_id = self.action_data.get("match_id", "")
            team_name = self.action_data.get("team_name", "")

            # 如果没有 match_id，通过战队名查找
            if not match_id and team_name:
                matches = await scraper.get_matches()
                for m in matches:
                    if team_name.lower() in m["team1"].lower() or team_name.lower() in m["team2"].lower():
                        match_id = m["match_id"]
                        break

            if not match_id:
                return False, "请提供比赛ID或战队名称"

            detail = await scraper.get_match_detail(match_id)
            if not detail:
                return False, f"未找到比赛 {match_id} 的详情"

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

            return True, content.strip()

        except Exception as e:
            logger.error(f"GetMatchDetailAction 执行失败: {e}")
            return False, f"获取比赛详情失败: {e}"


class GetMapStatsAction(BaseAction):
    """获取地图统计 Action (Scoreboard)"""

    action_name = "hltv_get_map_stats"
    action_description = "获取CS2比赛某张地图的详细统计数据（Scoreboard），包括选手K/D/A、ADR、Rating、KAST等"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "match_id": "比赛ID（可选）",
        "team_name": "战队名称（用于查找比赛，可选）",
        "map_index": "地图序号（从1开始，默认1）",
    }

    action_require = [
        "当用户询问比赛数据、选手表现时使用",
        "当用户想看Scoreboard时使用",
        "当用户问某个选手打得怎么样时使用",
        "当用户询问ADR、Rating、KAST等数据时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装"

        try:
            match_id = self.action_data.get("match_id", "")
            team_name = self.action_data.get("team_name", "")
            map_index = int(self.action_data.get("map_index", 1))

            # 查找比赛
            if not match_id and team_name:
                results = await scraper.get_results(max_results=20)
                for r in results:
                    if team_name.lower() in r["team1"].lower() or team_name.lower() in r["team2"].lower():
                        match_id = r["match_id"]
                        break

            if not match_id:
                return False, "请提供比赛ID或战队名称"

            # 获取比赛详情
            detail = await scraper.get_match_detail(match_id)
            if not detail or not detail.maps:
                return False, "未找到地图数据"

            if map_index < 1 or map_index > len(detail.maps):
                return False, f"地图序号无效，该比赛共 {len(detail.maps)} 张地图"

            map_result = detail.maps[map_index - 1]
            if not map_result.stats_url:
                return False, "该地图暂无详细统计数据"

            # 获取地图统计
            stats = await scraper.get_map_stats(map_result.stats_url)
            if not stats:
                return False, "获取地图统计失败"

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

            return True, content.strip()

        except Exception as e:
            logger.error(f"GetMapStatsAction 执行失败: {e}")
            return False, f"获取地图统计失败: {e}"


class GetMatchResultsAction(BaseAction):
    """获取比赛结果 Action"""

    action_name = "hltv_get_results"
    action_description = "获取最近的CS2比赛结果"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "team_filter": "按战队名称过滤（可选）",
        "max_results": "返回的最大结果数量（默认10）",
    }

    action_require = [
        "当用户询问比赛结果时使用",
        "当用户问谁赢了时使用",
        "当用户想知道某个战队最近战绩时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装"

        try:
            team_filter = self.action_data.get("team_filter", "")
            max_results = int(self.action_data.get("max_results", 10))

            results = await scraper.get_results(max_results=50)

            if team_filter:
                results = [
                    r for r in results
                    if team_filter.lower() in r["team1"].lower()
                    or team_filter.lower() in r["team2"].lower()
                ]

            if not results:
                msg = f"未找到{' ' + team_filter + ' 的' if team_filter else ''}比赛结果"
                return True, msg

            results = results[:max_results]

            content = f"📋 最近比赛结果 ({len(results)} 场):\n\n"
            for i, r in enumerate(results, 1):
                winner_mark = "🏆" if r["score1"] > r["score2"] else ""
                loser_mark = "🏆" if r["score2"] > r["score1"] else ""
                content += f"{i}. {winner_mark}{r['team1']} {r['score1']}-{r['score2']} {r['team2']}{loser_mark}\n"
                if r["event"]:
                    content += f"   赛事: {r['event'][:40]}\n"
                content += "\n"

            return True, content.strip()

        except Exception as e:
            logger.error(f"GetMatchResultsAction 执行失败: {e}")
            return False, f"获取比赛结果失败: {e}"


class GetTeamRankingsAction(BaseAction):
    """获取战队排名 Action"""

    action_name = "hltv_get_rankings"
    action_description = "获取CS2战队世界排名"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "max_teams": "返回的战队数量（默认10）",
    }

    action_require = [
        "当用户询问战队排名时使用",
        "当用户问哪个队最强时使用",
        "当用户想知道世界排名时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装"

        try:
            max_teams = int(self.action_data.get("max_teams", 10))
            teams = await scraper.get_rankings(max_teams=max_teams)

            if not teams:
                return False, "未获取到排名数据"

            content = f"🏆 CS2 战队世界排名 (Top {len(teams)}):\n\n"
            for team in teams:
                change_icon = "🔺" if "+" in team.change else ("🔻" if "-" in team.change else "➖")
                content += f"#{team.rank} {team.name} - {team.points}分 {change_icon}{team.change}\n"
                if team.players:
                    content += f"   选手: {', '.join(team.players[:5])}\n"

            return True, content.strip()

        except Exception as e:
            logger.error(f"GetTeamRankingsAction 执行失败: {e}")
            return False, f"获取排名失败: {e}"


class GetTeamInfoAction(BaseAction):
    """获取战队信息 Action"""

    action_name = "hltv_get_team_info"
    action_description = "获取CS2战队的详细信息，包括排名、积分、选手阵容等"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "team_name": "战队名称（必填）",
    }

    action_require = [
        "当用户询问某个战队信息时使用",
        "当用户想知道战队阵容时使用",
        "当用户问某个战队怎么样时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        team_name = self.action_data.get("team_name", "")

        if not team_name:
            return False, "请提供战队名称"

        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装"

        try:
            team = await scraper.search_team(team_name)

            if not team:
                return False, f"未找到战队: {team_name}"

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
                r for r in results
                if team_name.lower() in r["team1"].lower() or team_name.lower() in r["team2"].lower()
            ][:5]

            if team_results:
                content += f"\n📋 近期战绩:\n"
                for r in team_results:
                    result_icon = "✅" if r["winner"].lower() == team.name.lower() else "❌"
                    opponent = r['team2'] if team.name.lower() in r['team1'].lower() else r['team1']
                    content += f"  {result_icon} vs {opponent} ({r['score1']}-{r['score2']})\n"

            return True, content.strip()

        except Exception as e:
            logger.error(f"GetTeamInfoAction 执行失败: {e}")
            return False, f"获取战队信息失败: {e}"


class GetLiveMatchAction(BaseAction):
    """获取正在进行的比赛 Action"""

    action_name = "hltv_get_live_matches"
    action_description = "获取当前正在进行的CS2直播比赛的实时数据，包括地图比分和回合比分"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "team_filter": "按战队名称过滤（可选）",
    }

    action_require = [
        "当用户询问现在有什么比赛时使用",
        "当用户问有没有直播时使用",
        "当用户想看正在进行的比赛时使用",
        "当群友正在讨论某场直播比赛时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装"

        try:
            team_filter = self.action_data.get("team_filter", "")

            live_matches = await live_manager.get_live_matches()

            if team_filter:
                live_matches = [
                    m for m in live_matches
                    if team_filter.lower() in m.team1.lower() or team_filter.lower() in m.team2.lower()
                ]

            if not live_matches:
                msg = "🔴 当前没有正在进行的比赛"
                if team_filter:
                    msg += f"（{team_filter} 相关）"
                return True, msg

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

            return True, content.strip()

        except Exception as e:
            logger.error(f"GetLiveMatchAction 执行失败: {e}")
            return False, f"获取直播比赛失败: {e}"


class GetLiveScoreAction(BaseAction):
    """获取直播比赛实时比分 Action"""

    action_name = "hltv_get_live_score"
    action_description = "获取指定战队正在进行的比赛的实时比分"

    activation_type = ActionActivationType.LLM_JUDGE
    parallel_action = True

    action_parameters = {
        "team_name": "战队名称（必填）",
    }

    action_require = [
        "当群友正在讨论某场直播比赛时使用",
        "当用户询问某场比赛比分时使用",
        "当用户问打到几比几了时使用",
        "当用户想知道某个战队的比赛进度时使用",
    ]

    associated_types = ["text"]

    async def execute(self) -> Tuple[bool, str]:
        team_name = self.action_data.get("team_name", "")

        if not team_name:
            return False, "请提供战队名称"

        if not HAS_DEPENDENCIES:
            return False, "❌ HLTV 爬虫依赖未安装"

        try:
            live_matches = await live_manager.get_live_matches()

            target_match = None
            for m in live_matches:
                if team_name.lower() in m.team1.lower() or team_name.lower() in m.team2.lower():
                    target_match = m
                    break

            if not target_match:
                return True, f"❌ {team_name} 当前没有正在进行的比赛"

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

            if target_match.team1_map_score > target_match.team2_map_score:
                content += f"📈 {target_match.team1} 领先\n"
            elif target_match.team2_map_score > target_match.team1_map_score:
                content += f"📈 {target_match.team2} 领先\n"
            else:
                content += f"⚖️ 比分持平\n"

            content += f"━━━━━━━━━━━━━━━━━━━━\n"
            content += f"🏆 {target_match.event}"

            return True, content

        except Exception as e:
            logger.error(f"GetLiveScoreAction 执行失败: {e}")
            return False, f"获取实时比分失败: {e}"


# ============== 插件主类 ==============


@register_plugin
class CS2HLTVPlugin(BasePlugin):
    """CS2 HLTV插件 - 开箱即用的CS2数据查询"""

    plugin_name: str = "cs2_hltv_plugin"
    enable_plugin: bool = True
    dependencies: List[str] = []
    python_dependencies: List[str] = ["curl_cffi", "beautifulsoup4", "lxml"]
    config_file_name: str = "config.toml"

    config_section_descriptions = {
        "plugin": "插件基本信息",
        "live_data": "实时数据配置（可选）",
    }

    config_schema: dict = {
        "plugin": {
            "name": ConfigField(type=str, default="cs2_hltv_plugin", description="插件名称"),
            "version": ConfigField(type=str, default="5.2.0", description="插件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        "live_data": {
            "enabled": ConfigField(type=bool, default=False, description="是否启用实时数据源"),
            "provider": ConfigField(type=str, default="bo3gg", description="实时数据提供者"),
            "fallback_to_hltv": ConfigField(type=bool, default=True, description="失败时回退到HLTV"),
        },
    }

    async def on_load(self):
        """插件加载时初始化"""
        logger.info("[HLTVPlugin] CS2 HLTV插件 v5.2.0 已加载")

        if HAS_DEPENDENCIES:
            logger.info("[HLTVPlugin] ✓ 爬虫依赖已安装，插件功能正常")
        else:
            logger.warning("[HLTVPlugin] ✗ 爬虫依赖未安装，请运行: pip install curl_cffi beautifulsoup4 lxml")

        # 加载实时数据配置
        self._load_live_data_config()

    def _load_live_data_config(self):
        """加载实时数据配置"""
        try:
            live_config = self.config.get("live_data", {})
            if live_config.get("enabled", False):
                provider = live_config.get("provider", "bo3gg")
                live_manager.configure(
                    enabled=True,
                    provider=provider,
                    fallback_to_hltv=live_config.get("fallback_to_hltv", True),
                )
                logger.info(f"[HLTVPlugin] ✓ 实时数据已启用 (provider={provider})")
            else:
                logger.info("[HLTVPlugin] ℹ 实时数据未启用，使用 HLTV 静态数据")
        except Exception as e:
            logger.warning(f"[HLTVPlugin] 加载实时数据配置失败: {e}")

    async def on_unload(self):
        """插件卸载时清理"""
        await live_manager.close()
        logger.info("[HLTVPlugin] CS2 HLTV插件已卸载")

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件组件列表"""
        return [
            # 查询类 Action
            (GetMatchesAction.get_action_info(), GetMatchesAction),
            (GetMatchDetailAction.get_action_info(), GetMatchDetailAction),
            (GetMapStatsAction.get_action_info(), GetMapStatsAction),
            (GetMatchResultsAction.get_action_info(), GetMatchResultsAction),
            (GetTeamRankingsAction.get_action_info(), GetTeamRankingsAction),
            (GetTeamInfoAction.get_action_info(), GetTeamInfoAction),
            # 实时类 Action
            (GetLiveMatchAction.get_action_info(), GetLiveMatchAction),
            (GetLiveScoreAction.get_action_info(), GetLiveScoreAction),
        ]
