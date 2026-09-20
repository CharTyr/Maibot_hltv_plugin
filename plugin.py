"""
CS2 HLTV 电竞信息插件 v6.1.1 - 新版 maibot-plugin-sdk 适配
直接集成爬虫，无需额外服务
"""

from typing import List

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .hltv_scraper import HAS_DEPENDENCIES, LiveMatch, scraper
from .live_providers import LiveMatchData, create_live_provider


PLUGIN_VERSION = "6.2.0"
CONFIG_SCHEMA_VERSION = "6.1.0"


# ============== 配置模型 ==============


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default=CONFIG_SCHEMA_VERSION, description="配置 schema 版本")


class CacheConfig(PluginConfigBase):
    """缓存配置。"""

    __ui_label__ = "缓存"
    __ui_icon__ = "database"
    __ui_order__ = 1

    matches_ttl: int = Field(default=120, description="比赛数据缓存时间（秒）")
    rankings_ttl: int = Field(default=3600, description="排名数据缓存时间（秒）")
    results_ttl: int = Field(default=600, description="结果数据缓存时间（秒）")


class DisplayConfig(PluginConfigBase):
    """显示配置。"""

    __ui_label__ = "显示"
    __ui_icon__ = "monitor"
    __ui_order__ = 2

    default_matches: int = Field(default=5, description="默认显示的比赛数量")
    default_rankings: int = Field(default=10, description="默认显示的排名数量")
    default_results: int = Field(default=10, description="默认显示的结果数量")


class LiveDataConfig(PluginConfigBase):
    """实时数据配置。"""

    __ui_label__ = "实时数据"
    __ui_icon__ = "radio"
    __ui_order__ = 3

    enabled: bool = Field(default=False, description="是否启用实时数据功能")
    provider: str = Field(default="bo3gg", description="实时数据提供者 (bo3gg/pandascore)")
    fallback_to_hltv: bool = Field(default=True, description="失败时回退到HLTV静态数据")
    pandascore_token: str = Field(default="", description="PandaScore API token")


class TavilyConfig(PluginConfigBase):
    """Tavily API 配置。"""

    __ui_label__ = "Tavily"
    __ui_icon__ = "cloud"
    __ui_order__ = 4

    api_key: str = Field(default="", description="Tavily API Key (绕过 Cloudflare)")
    base_url: str = Field(
        default="https://api.tavily.com",
        description="Tavily 兼容 API 地址 (中转站填中转地址)",
    )


class JinaConfig(PluginConfigBase):
    """Jina Reader 配置。"""

    __ui_label__ = "Jina Reader"
    __ui_icon__ = "cloud"
    __ui_order__ = 5

    enabled: bool = Field(default=True, description="启用 Jina Reader 主抓取通道")
    base_url: str = Field(default="https://r.jina.ai", description="Jina Reader 地址")


class HLTVPluginConfig(PluginConfigBase):
    """HLTV 插件完整配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    live_data: LiveDataConfig = Field(default_factory=LiveDataConfig)
    tavily: TavilyConfig = Field(default_factory=TavilyConfig)
    jina: JinaConfig = Field(default_factory=JinaConfig)


# ============== 实时数据管理器 ==============


class LiveDataManager:
    """实时数据管理器"""

    def __init__(self):
        self._provider = None
        self._provider_type = None
        self._enabled = False
        self._fallback_to_hltv = True

    def configure(self, enabled: bool = False, provider: str = "bo3gg",
                  fallback_to_hltv: bool = True, **kwargs):
        """配置实时数据管理器"""
        self._enabled = enabled
        self._fallback_to_hltv = fallback_to_hltv

        if enabled and provider != self._provider_type:
            self._provider = create_live_provider(provider, **kwargs)
            self._provider_type = provider

    async def get_live_matches(self) -> List[LiveMatch]:
        """获取直播比赛（优先使用实时数据源）"""
        if self._enabled and self._provider:
            try:
                live_data = await self._provider.get_live_matches()
                if live_data:
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
            except Exception:
                pass

        if self._fallback_to_hltv:
            return await scraper.get_live_matches()

        return []

    async def close(self):
        """关闭资源"""
        if self._provider:
            await self._provider.close()
            self._provider = None

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def provider_type(self) -> str:
        return self._provider_type or "hltv"


# ============== 插件主类 ==============


class CS2HLTVPlugin(MaiBotPlugin):
    """CS2 HLTV 电竞信息插件"""

    config_model = HLTVPluginConfig

    def __init__(self):
        super().__init__()
        self._live_manager = LiveDataManager()

    async def on_load(self) -> None:
        """插件加载"""
        if HAS_DEPENDENCIES:
            self.ctx.logger.info(f"CS2 HLTV 插件 v{PLUGIN_VERSION} 已加载，爬虫依赖正常")
        else:
            self.ctx.logger.warning("CS2 HLTV 插件已加载，但爬虫依赖未安装。请运行: pip install beautifulsoup4 lxml requests")

        # 应用缓存配置
        if self.config:
            scraper._cache_ttl["matches"] = self.config.cache.matches_ttl
            scraper._cache_ttl["rankings"] = self.config.cache.rankings_ttl
            scraper._cache_ttl["results"] = self.config.cache.results_ttl

            # 注入 Tavily API Key 与中转地址
            if self.config.tavily and self.config.tavily.api_key:
                scraper.set_tavily_key(self.config.tavily.api_key)
                scraper.set_tavily_base_url(getattr(self.config.tavily, "base_url", "") or "https://api.tavily.com")
                self.ctx.logger.info("Tavily 已配置 (备选通道)")

            # 注入 Jina Reader 主通道
            jina_cfg = getattr(self.config, "jina", None)
            if jina_cfg and getattr(jina_cfg, "enabled", True):
                scraper.set_jina_base_url(jina_cfg.base_url)
                self.ctx.logger.info(f"Jina Reader 主通道已启用 ({jina_cfg.base_url})")

            # 配置实时数据
            live_cfg = self.config.live_data
            if live_cfg.enabled:
                self._live_manager.configure(
                    enabled=True,
                    provider=live_cfg.provider,
                    fallback_to_hltv=live_cfg.fallback_to_hltv,
                    api_token=live_cfg.pandascore_token,
                )
                self.ctx.logger.info(f"实时数据已启用 (provider={live_cfg.provider})")

    async def on_unload(self) -> None:
        """插件卸载"""
        await self._live_manager.close()
        self.ctx.logger.info("CS2 HLTV 插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """配置热更新"""
        if scope == "self" and self.config:
            scraper._cache_ttl["matches"] = self.config.cache.matches_ttl
            scraper._cache_ttl["rankings"] = self.config.cache.rankings_ttl
            scraper._cache_ttl["results"] = self.config.cache.results_ttl

            live_cfg = self.config.live_data
            self._live_manager.configure(
                enabled=live_cfg.enabled,
                provider=live_cfg.provider,
                fallback_to_hltv=live_cfg.fallback_to_hltv,
                api_token=live_cfg.pandascore_token,
            )

    # ============== Tool 组件 ==============

    @Tool(
        "hltv_get_matches",
        description="获取CS2/CSGO电竞比赛列表（即将开始和进行中），含时间、战队、赛事。用于查询今天有什么比赛、比赛安排。",
        parameters=[
            ToolParameterInfo(name="team_filter", param_type=ToolParamType.STRING, description="按战队名称过滤（可选）", required=False),
            ToolParameterInfo(name="max_matches", param_type=ToolParamType.INTEGER, description="返回的最大比赛数量，默认10", required=False, default=10),
        ],
    )
    async def get_matches(self, team_filter: str = "", max_matches: int = 10, **kwargs):
        """获取比赛列表"""
        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装。请运行: pip install beautifulsoup4 lxml requests"}

        try:
            matches = await scraper.get_matches()

            if team_filter:
                matches = [
                    m for m in matches
                    if team_filter.lower() in m["team1"].lower()
                    or team_filter.lower() in m["team2"].lower()
                ]

            if not matches:
                return {"success": True, "content": "当前没有找到比赛信息"}

            matches = matches[:max_matches]

            content = f"CS2 比赛列表 ({len(matches)} 场):\n\n"
            for i, m in enumerate(matches, 1):
                status_icon = "[直播]" if m["status"] == "live" else "[预定]"
                content += f"{i}. {status_icon} {m['team1']} vs {m['team2']}\n"
                if m["time"]:
                    content += f"   时间: {m['time']}\n"
                if m["event"]:
                    content += f"   赛事: {m['event'][:50]}\n"
                content += "\n"

            return {"success": True, "content": content.strip()}
        except Exception as e:
            self.ctx.logger.error(f"获取比赛列表失败: {e}")
            return {"success": False, "content": f"获取比赛列表失败: {e}"}

    @Tool(
        "hltv_get_match_detail",
        description="获取CS2比赛详情：比分、地图Veto、赛制。用于查询某场比赛打到哪了、ban/pick情况。",
        parameters=[
            ToolParameterInfo(name="match_id", param_type=ToolParamType.STRING, description="比赛ID（从比赛列表获取，可选）", required=False),
            ToolParameterInfo(name="team_name", param_type=ToolParamType.STRING, description="战队名称（用于查找比赛，可选）", required=False),
        ],
    )
    async def get_match_detail(self, match_id: str = "", team_name: str = "", **kwargs):
        """获取比赛详情"""
        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装"}

        try:
            if not match_id and team_name:
                matches = await scraper.get_matches()
                for m in matches:
                    if team_name.lower() in m["team1"].lower() or team_name.lower() in m["team2"].lower():
                        match_id = m["match_id"]
                        break

            if not match_id:
                return {"success": False, "content": "请提供比赛ID或战队名称"}

            detail = await scraper.get_match_detail(match_id)
            if not detail:
                return {"success": False, "content": f"未找到比赛 {match_id} 的详情"}

            status_map = {"live": "[进行中]", "scheduled": "[即将开始]", "finished": "[已结束]"}
            status = status_map.get(detail.status, detail.status)

            content = f"比赛详情\n\n"
            content += f"{detail.team1} {detail.team1_score} - {detail.team2_score} {detail.team2}\n"
            content += f"状态: {status}\n"
            if detail.event:
                content += f"赛事: {detail.event}\n"
            if detail.format:
                content += f"赛制: {detail.format.upper()}\n"
            if detail.date:
                content += f"日期: {detail.date}\n"

            if detail.maps:
                content += f"\n地图 ({len(detail.maps)} 张):\n"
                for i, map_result in enumerate(detail.maps, 1):
                    content += f"  Map {i}: {map_result.map_name} - {map_result.team1_score}:{map_result.team2_score}\n"

            if detail.veto:
                content += f"\nVeto:\n"
                for v in detail.veto[:6]:
                    content += f"  - {v}\n"

            return {"success": True, "content": content.strip()}
        except Exception as e:
            self.ctx.logger.error(f"获取比赛详情失败: {e}")
            return {"success": False, "content": f"获取比赛详情失败: {e}"}

    @Tool(
        "hltv_get_map_stats",
        description="获取CS2比赛地图Scoreboard：选手K/D、ADR、KAST、Rating。用于查询选手表现、数据统计。",
        parameters=[
            ToolParameterInfo(name="match_id", param_type=ToolParamType.STRING, description="比赛ID（可选）", required=False),
            ToolParameterInfo(name="team_name", param_type=ToolParamType.STRING, description="战队名称（用于查找比赛，可选）", required=False),
            ToolParameterInfo(name="map_index", param_type=ToolParamType.INTEGER, description="地图序号（从1开始，默认1）", required=False, default=1),
        ],
    )
    async def get_map_stats(self, match_id: str = "", team_name: str = "", map_index: int = 1, **kwargs):
        """获取地图统计"""
        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装"}

        try:
            if not match_id and team_name:
                results = await scraper.get_results(max_results=20)
                for r in results:
                    if team_name.lower() in r["team1"].lower() or team_name.lower() in r["team2"].lower():
                        match_id = r["match_id"]
                        break

            if not match_id:
                return {"success": False, "content": "请提供比赛ID或战队名称"}

            detail = await scraper.get_match_detail(match_id)
            if not detail or not detail.maps:
                return {"success": False, "content": "未找到地图数据"}

            if map_index < 1 or map_index > len(detail.maps):
                return {"success": False, "content": f"地图序号无效，该比赛共 {len(detail.maps)} 张地图"}

            map_result = detail.maps[map_index - 1]

            # 优先尝试 stats 页面，失败则从详情页内嵌数据解析
            stats = None
            if map_result.stats_url:
                stats = await scraper.get_map_stats(map_result.stats_url)
            if not stats:
                stats = await scraper.get_map_stats_from_match(match_id, map_index - 1)
            if not stats:
                return {"success": False, "content": "该地图暂无详细统计数据"}

            content = f"{map_result.map_name} Scoreboard\n"
            content += f"{detail.team1} {map_result.team1_score} - {map_result.team2_score} {detail.team2}\n"
            content += f"{detail.event}\n\n"

            for team_key in ["team1", "team2"]:
                team_data = stats.get(team_key, {})
                team_name_display = team_data.get("name", team_key)
                players = team_data.get("players", [])

                content += f"[{team_name_display}]\n"
                content += f"{'选手':<10} {'K':>3} {'A':>3} {'D':>3} {'ADR':>5} {'KAST':>5} {'Rating':>6}\n"
                content += "-" * 45 + "\n"

                for p in players:
                    content += f"{p.nickname:<10} {p.kills:>3} {p.assists:>3} {p.deaths:>3} {p.adr:>5.1f} {p.kast:>4.0f}% {p.rating:>6.2f}\n"
                content += "\n"

            return {"success": True, "content": content.strip()}
        except Exception as e:
            self.ctx.logger.error(f"获取地图统计失败: {e}")
            return {"success": False, "content": f"获取地图统计失败: {e}"}

    @Tool(
        "hltv_get_results",
        description="获取最近CS2比赛结果和比分。用于查询谁赢了、某战队最近战绩。",
        parameters=[
            ToolParameterInfo(name="team_filter", param_type=ToolParamType.STRING, description="按战队名称过滤（可选）", required=False),
            ToolParameterInfo(name="max_results", param_type=ToolParamType.INTEGER, description="返回的最大结果数量，默认10", required=False, default=10),
        ],
    )
    async def get_results(self, team_filter: str = "", max_results: int = 10, **kwargs):
        """获取比赛结果"""
        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装"}

        try:
            results = await scraper.get_results(max_results=50)

            if team_filter:
                results = [
                    r for r in results
                    if team_filter.lower() in r["team1"].lower()
                    or team_filter.lower() in r["team2"].lower()
                ]

            if not results:
                msg = f"未找到{' ' + team_filter + ' 的' if team_filter else ''}比赛结果"
                return {"success": True, "content": msg}

            results = results[:max_results]

            content = f"最近比赛结果 ({len(results)} 场):\n\n"
            for i, r in enumerate(results, 1):
                winner_mark = "[胜]" if r["score1"] > r["score2"] else ""
                loser_mark = "[胜]" if r["score2"] > r["score1"] else ""
                content += f"{i}. {winner_mark}{r['team1']} {r['score1']}-{r['score2']} {r['team2']}{loser_mark}\n"
                if r["event"]:
                    content += f"   赛事: {r['event'][:40]}\n"
                content += "\n"

            return {"success": True, "content": content.strip()}
        except Exception as e:
            self.ctx.logger.error(f"获取比赛结果失败: {e}")
            return {"success": False, "content": f"获取比赛结果失败: {e}"}

    @Tool(
        "hltv_get_rankings",
        description="获取CS2/CSGO战队HLTV世界排名Top N。用于查询电竞战队哪个队最强、排名多少。",
        parameters=[
            ToolParameterInfo(name="max_teams", param_type=ToolParamType.INTEGER, description="返回的战队数量，默认10", required=False, default=10),
        ],
    )
    async def get_rankings(self, max_teams: int = 10, **kwargs):
        """获取战队排名"""
        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装"}

        try:
            teams = await scraper.get_rankings(max_teams=max_teams)

            if not teams:
                return {"success": False, "content": "未获取到排名数据"}

            content = f"CS2 战队世界排名 (Top {len(teams)}):\n\n"
            for team in teams:
                content += f"#{team.rank} {team.name} - {team.points}分 ({team.change})\n"
                if team.players:
                    content += f"   选手: {', '.join(team.players[:5])}\n"

            return {"success": True, "content": content.strip()}
        except Exception as e:
            self.ctx.logger.error(f"获取排名失败: {e}")
            return {"success": False, "content": f"获取排名失败: {e}"}

    @Tool(
        "hltv_get_team_info",
        description="获取CS2战队详情：排名、积分、选手阵容、近期战绩。用于查询某个战队怎么样。",
        parameters=[
            ToolParameterInfo(name="team_name", param_type=ToolParamType.STRING, description="战队名称", required=True),
        ],
    )
    async def get_team_info(self, team_name: str = "", **kwargs):
        """获取战队信息"""
        if not team_name:
            return {"success": False, "content": "请提供战队名称"}

        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装"}

        try:
            team = await scraper.search_team(team_name)
            if not team:
                return {"success": False, "content": f"未找到战队: {team_name}"}

            content = f"{team.name} 战队信息\n\n"
            if team.rank > 0:
                content += f"世界排名: #{team.rank}\n"
            else:
                content += "世界排名: 未上榜\n"
            if team.points > 0:
                content += f"积分: {team.points}\n"
            if team.change:
                content += f"排名变化: {team.change}\n"

            if team.players:
                content += f"\n选手阵容:\n"
                for p in team.players:
                    content += f"  - {p}\n"

            # 获取近期比赛
            results = await scraper.get_results(max_results=20)
            team_results = [
                r for r in results
                if team_name.lower() in r["team1"].lower() or team_name.lower() in r["team2"].lower()
            ][:5]

            if team_results:
                content += f"\n近期战绩:\n"
                for r in team_results:
                    result_icon = "[胜]" if r["winner"].lower() == team.name.lower() else "[负]"
                    opponent = r['team2'] if team.name.lower() in r['team1'].lower() else r['team1']
                    content += f"  {result_icon} vs {opponent} ({r['score1']}-{r['score2']})\n"

            return {"success": True, "content": content.strip()}
        except Exception as e:
            self.ctx.logger.error(f"获取战队信息失败: {e}")
            return {"success": False, "content": f"获取战队信息失败: {e}"}

    @Tool(
        "hltv_get_live_matches",
        description="获取当前正在进行的CS2直播比赛，含地图比分和回合比分。用于查询现在有什么比赛在打。",
        parameters=[
            ToolParameterInfo(name="team_filter", param_type=ToolParamType.STRING, description="按战队名称过滤（可选）", required=False),
        ],
    )
    async def get_live_matches(self, team_filter: str = "", **kwargs):
        """获取正在进行的比赛"""
        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装"}

        try:
            live_matches = await self._live_manager.get_live_matches()

            if team_filter:
                live_matches = [
                    m for m in live_matches
                    if team_filter.lower() in m.team1.lower() or team_filter.lower() in m.team2.lower()
                ]

            if not live_matches:
                msg = "当前没有正在进行的比赛"
                if team_filter:
                    msg += f"（{team_filter} 相关）"
                return {"success": True, "content": msg}

            source_info = f" [数据源: {self._live_manager.provider_type}]" if self._live_manager.is_enabled else ""

            content = f"正在进行的比赛 ({len(live_matches)} 场){source_info}:\n\n"
            for m in live_matches:
                content += f"{m.team1} vs {m.team2}\n"
                content += f"   地图比分: {m.team1_map_score} - {m.team2_map_score}"
                if m.format:
                    content += f" ({m.format.upper()})"
                content += "\n"
                if m.current_map:
                    content += f"   当前地图: {m.current_map}\n"
                if m.team1_round_score or m.team2_round_score:
                    content += f"   回合比分: {m.team1_round_score} - {m.team2_round_score}\n"
                if m.event:
                    content += f"   赛事: {m.event}\n"
                content += "\n"

            return {"success": True, "content": content.strip()}
        except Exception as e:
            self.ctx.logger.error(f"获取直播比赛失败: {e}")
            return {"success": False, "content": f"获取直播比赛失败: {e}"}

    @Tool(
        "hltv_get_live_score",
        description="获取指定战队正在进行的CS2直播比赛实时比分。用于查询某场比赛打到几比几了。",
        parameters=[
            ToolParameterInfo(name="team_name", param_type=ToolParamType.STRING, description="战队名称", required=True),
        ],
    )
    async def get_live_score(self, team_name: str = "", **kwargs):
        """获取实时比分"""
        if not team_name:
            return {"success": False, "content": "请提供战队名称"}

        if not HAS_DEPENDENCIES:
            return {"success": False, "content": "HLTV 爬虫依赖未安装"}

        try:
            live_matches = await self._live_manager.get_live_matches()

            target_match = None
            for m in live_matches:
                if team_name.lower() in m.team1.lower() or team_name.lower() in m.team2.lower():
                    target_match = m
                    break

            if not target_match:
                return {"success": True, "content": f"{team_name} 当前没有正在进行的比赛"}

            source_info = f" [{self._live_manager.provider_type}]" if self._live_manager.is_enabled else ""
            content = f"实时比分{source_info}\n\n"
            content += f"{target_match.team1} vs {target_match.team2}\n"
            content += f"{'=' * 20}\n"
            content += f"地图: {target_match.team1_map_score} - {target_match.team2_map_score}"
            if target_match.format:
                content += f" ({target_match.format.upper()})"
            content += "\n"

            if target_match.current_map:
                content += f"当前: {target_match.current_map}\n"

            if target_match.team1_round_score or target_match.team2_round_score:
                content += f"回合: {target_match.team1_round_score} - {target_match.team2_round_score}\n"

            if target_match.team1_map_score > target_match.team2_map_score:
                content += f"{target_match.team1} 领先\n"
            elif target_match.team2_map_score > target_match.team1_map_score:
                content += f"{target_match.team2} 领先\n"
            else:
                content += f"比分持平\n"

            content += f"{'=' * 20}\n"
            content += f"赛事: {target_match.event}"

            return {"success": True, "content": content}
        except Exception as e:
            self.ctx.logger.error(f"获取实时比分失败: {e}")
            return {"success": False, "content": f"获取实时比分失败: {e}"}


def create_plugin() -> CS2HLTVPlugin:
    """创建插件实例"""
    return CS2HLTVPlugin()
