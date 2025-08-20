from typing import List, Tuple, Type, Any, Optional, Dict
import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from src.plugin_system.base import (
    BasePlugin,
    BaseAction,
    BaseTool,
    ToolParamType,
    ConfigField
)
from src.plugin_system.apis import register_plugin
from src.plugin_system.base.component_types import (
    ComponentInfo,
    ActionInfo,
    ActionActivationType,
    ComponentType,
    ToolInfo
)

# 设置日志
logger = logging.getLogger("plugin")

@dataclass
class MatchEvent:
    """比赛事件数据类"""
    event_type: str  # "score_change", "map_change", "match_start", "match_end", "overtime"
    match_id: str
    team1: str
    team2: str
    old_score: Tuple[int, int]
    new_score: Tuple[int, int]
    timestamp: datetime
    description: str
    importance: int  # 1-5, 5为最重要

class MatchEventDetector:
    """比赛事件检测器 - 检测比分变化和重要事件"""
    
    def __init__(self):
        self.previous_matches: Dict[str, Dict] = {}
        self.event_history: List[MatchEvent] = []
        self.max_history = 100
    
    def _generate_match_id(self, match: Dict) -> str:
        """生成比赛唯一ID"""
        teams = match.get('teams', [])
        if len(teams) >= 2:
            team1 = teams[0].get('name', 'TBD')
            team2 = teams[1].get('name', 'TBD')
            event = match.get('event', {}).get('name', 'Unknown')
            return f"{team1}_vs_{team2}_{event}".replace(' ', '_')
        return f"match_{hash(str(match))}"
    
    def detect_events(self, current_matches: List[Dict]) -> List[MatchEvent]:
        """检测比赛事件"""
        events = []
        current_time = datetime.now()
        
        for match in current_matches:
            match_id = self._generate_match_id(match)
            teams = match.get('teams', [])
            
            if len(teams) < 2:
                continue
                
            team1_name = teams[0].get('name', 'TBD')
            team2_name = teams[1].get('name', 'TBD')
            current_score1 = teams[0].get('score', 0)
            current_score2 = teams[1].get('score', 0)
            
            # 检查是否是新比赛或比分变化
            if match_id in self.previous_matches:
                prev_match = self.previous_matches[match_id]
                prev_teams = prev_match.get('teams', [])
                
                if len(prev_teams) >= 2:
                    prev_score1 = prev_teams[0].get('score', 0)
                    prev_score2 = prev_teams[1].get('score', 0)
                    
                    # 检测比分变化
                    if (current_score1 != prev_score1 or current_score2 != prev_score2):
                        importance = self._calculate_score_importance(
                            (prev_score1, prev_score2), 
                            (current_score1, current_score2)
                        )
                        
                        event = MatchEvent(
                            event_type="score_change",
                            match_id=match_id,
                            team1=team1_name,
                            team2=team2_name,
                            old_score=(prev_score1, prev_score2),
                            new_score=(current_score1, current_score2),
                            timestamp=current_time,
                            description=f"{team1_name} {current_score1} - {current_score2} {team2_name}",
                            importance=importance
                        )
                        events.append(event)
                    
                    # 检测比赛结束
                    if self._is_match_finished(current_score1, current_score2) and \
                       not self._is_match_finished(prev_score1, prev_score2):
                        winner = team1_name if current_score1 > current_score2 else team2_name
                        event = MatchEvent(
                            event_type="match_end",
                            match_id=match_id,
                            team1=team1_name,
                            team2=team2_name,
                            old_score=(prev_score1, prev_score2),
                            new_score=(current_score1, current_score2),
                            timestamp=current_time,
                            description=f"比赛结束！{winner} 获胜",
                            importance=5
                        )
                        events.append(event)
            else:
                # 新比赛开始
                if current_score1 > 0 or current_score2 > 0:
                    event = MatchEvent(
                        event_type="match_start",
                        match_id=match_id,
                        team1=team1_name,
                        team2=team2_name,
                        old_score=(0, 0),
                        new_score=(current_score1, current_score2),
                        timestamp=current_time,
                        description=f"比赛开始：{team1_name} vs {team2_name}",
                        importance=3
                    )
                    events.append(event)
            
            # 更新比赛状态
            self.previous_matches[match_id] = match
        
        # 添加事件到历史记录
        self.event_history.extend(events)
        if len(self.event_history) > self.max_history:
            self.event_history = self.event_history[-self.max_history:]
        
        return events
    
    def _calculate_score_importance(self, old_score: Tuple[int, int], new_score: Tuple[int, int]) -> int:
        """计算比分变化的重要性"""
        old_diff = abs(old_score[0] - old_score[1])
        new_diff = abs(new_score[0] - new_score[1])
        total_rounds = sum(new_score)
        
        # 比赛关键时刻
        if total_rounds >= 15:  # 接近比赛结束
            return 4
        elif new_diff <= 1:  # 比分接近
            return 4
        elif old_diff > 3 and new_diff <= 2:  # 追分成功
            return 5
        elif total_rounds >= 10:  # 比赛中期
            return 3
        else:
            return 2
    
    def _is_match_finished(self, score1: int, score2: int) -> bool:
        """判断比赛是否结束"""
        return (score1 >= 16 or score2 >= 16) and abs(score1 - score2) >= 2
    
    def get_recent_events(self, minutes: int = 30) -> List[MatchEvent]:
        """获取最近的事件"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [event for event in self.event_history if event.timestamp >= cutoff_time]


class HLTVAPIClient:
    """HLTV API客户端，处理所有API调用和缓存"""
    
    def __init__(self, base_url: str = "https://hltv-api.vercel.app/api"):
        self.base_url = base_url
        self.cache = {}
        self.cache_ttl = {}
        
    async def _make_request(self, endpoint: str, cache_duration: int = 300) -> Optional[Dict]:
        """发起API请求，带缓存机制"""
        cache_key = endpoint
        current_time = time.time()
        
        # 检查缓存
        if cache_key in self.cache and cache_key in self.cache_ttl:
            if current_time < self.cache_ttl[cache_key]:
                return self.cache[cache_key]
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/{endpoint}") as response:
                    if response.status == 200:
                        data = await response.json()
                        # 缓存数据
                        self.cache[cache_key] = data
                        self.cache_ttl[cache_key] = current_time + cache_duration
                        logger.info(f"HLTV API请求成功: {endpoint}")
                        return data
                    else:
                        logger.warning(f"HLTV API请求失败，状态码: {response.status}, 端点: {endpoint}")
                        return None
        except asyncio.TimeoutError:
            logger.error(f"HLTV API请求超时: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"HLTV API请求异常: {endpoint}, 错误: {str(e)}")
            return None
    
    async def get_matches(self) -> Optional[List[Dict]]:
        """获取比赛列表"""
        return await self._make_request("matches.json", cache_duration=60)
    
    async def get_players(self) -> Optional[List[Dict]]:
        """获取选手列表"""
        return await self._make_request("players.json", cache_duration=600)
    
    async def get_player_by_id(self, player_id: int) -> Optional[Dict]:
        """根据ID获取选手详细信息"""
        return await self._make_request(f"player.json?id={player_id}", cache_duration=300)
    
    async def get_teams(self) -> Optional[List[Dict]]:
        """获取战队排名"""
        return await self._make_request("teams.json", cache_duration=600)
    
    async def get_team_by_id(self, team_id: int) -> Optional[Dict]:
        """根据ID获取战队详细信息"""
        return await self._make_request(f"team.json?id={team_id}", cache_duration=300)
    
    async def get_results(self) -> Optional[List[Dict]]:
        """获取比赛结果"""
        return await self._make_request("results.json", cache_duration=300)
    
    async def get_match_by_id(self, match_id: int) -> Optional[Dict]:
        """根据ID获取比赛详细信息"""
        return await self._make_request(f"match.json?id={match_id}", cache_duration=60)


# API基础URL常量
HLTV_API_BASE = "https://hltv-api.vercel.app/api"

# 全局HLTV客户端实例和事件检测器
hltv_client = HLTVAPIClient()
match_event_detector = MatchEventDetector()


class GetCS2ContextInfoTool(BaseTool):
    """智能上下文信息提取工具 - 根据关键词自动查询相关信息"""
    
    name = "get_cs2_context_info"
    description = "当用户提到、谈论到CS2/CSGO相关内容时，使用此工具自动查询相关选手、战队和比赛信息。适用于一般性CS2讨论、选手提及、战队讨论等场景"
    parameters = [
        ("context_keywords", ToolParamType.STRING, "从聊天上下文中提取的关键词（选手名、战队名、赛事名等）", True, None),
        ("query_type", ToolParamType.STRING, "查询类型：player（选手）、team（战队）、match（比赛）、auto（自动判断）", False, "auto"),
        ("include_recent_matches", ToolParamType.BOOLEAN, "是否包含最近比赛信息", False, True),
    ]
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行上下文信息查询"""
        context_keywords = function_args.get("context_keywords", "").strip()
        query_type = function_args.get("query_type", "auto").lower()
        include_recent_matches = function_args.get("include_recent_matches", True)
        
        if not context_keywords:
            return {"name": self.name, "content": "未提供有效的上下文关键词"}
        
        try:
            context_info = []
            keywords = [kw.strip() for kw in context_keywords.split(",") if kw.strip()]
            
            # 自动判断查询类型或按指定类型查询
            if query_type in ["player", "auto"]:
                player_info = await self._search_players(keywords)
                if player_info:
                    context_info.extend(player_info)
            
            if query_type in ["team", "auto"]:
                team_info = await self._search_teams(keywords)
                if team_info:
                    context_info.extend(team_info)
            
            if query_type in ["match", "auto"] and include_recent_matches:
                match_info = await self._get_recent_matches()
                if match_info:
                    context_info.extend(match_info)
            
            if context_info:
                result = "\n".join(context_info)
                logger.info(f"为关键词 '{context_keywords}' 提供了上下文信息")
                return {"name": self.name, "content": result}
            else:
                return {"name": self.name, "content": f"未找到与 '{context_keywords}' 相关的信息"}
                
        except Exception as e:
            logger.error(f"获取CS2上下文信息时出错: {str(e)}")
            return {"name": self.name, "content": f"查询CS2信息时出错: {str(e)}"}
    
    async def _search_players(self, keywords: List[str]) -> List[str]:
        """搜索选手信息"""
        try:
            players_data = await hltv_client.get_players()
            if not players_data:
                return []
            
            # 处理不同的数据结构
            if isinstance(players_data, dict):
                players = [players_data]
            else:
                players = players_data if isinstance(players_data, list) else []
            
            found_info = []
            for keyword in keywords:
                for player in players:
                    nickname = player.get('nickname', '').lower()
                    fullname = player.get('name', '').lower()
                    
                    if (keyword.lower() in nickname or 
                        keyword.lower() in fullname or
                        nickname in keyword.lower()):
                        
                        team_name = player.get('team', {}).get('name', '自由选手')
                        rating = player.get('rating', 'N/A')
                        age = player.get('age', 'N/A')
                        
                        info = (f"🎯 选手: {player.get('nickname', 'N/A')} "
                               f"({player.get('name', 'N/A')}) - {team_name}, "
                               f"Rating: {rating}, 年龄: {age}")
                        found_info.append(info)
                        break
            
            return found_info
        except Exception as e:
            logger.error(f"搜索选手信息出错: {str(e)}")
            return []
    
    async def _search_teams(self, keywords: List[str]) -> List[str]:
        """搜索战队信息"""
        try:
            teams_data = await hltv_client.get_teams()
            if not teams_data:
                return []
            
            # 处理不同的数据结构
            if isinstance(teams_data, dict):
                teams = [teams_data]
            else:
                teams = teams_data if isinstance(teams_data, list) else []
            
            found_info = []
            for keyword in keywords:
                for team in teams:
                    team_name = team.get('name', '').lower()
                    
                    if keyword.lower() in team_name:
                        ranking = team.get('ranking', 'N/A')
                        players_count = len(team.get('players', []))
                        
                        info = (f"🏆 战队: {team.get('name', 'N/A')} "
                               f"(排名: #{ranking}, 队员: {players_count}人)")
                        found_info.append(info)
                        break
            
            return found_info
        except Exception as e:
            logger.error(f"搜索战队信息出错: {str(e)}")
            return []
    
    async def _get_recent_matches(self) -> List[str]:
        """获取最近比赛信息"""
        try:
            matches = await hltv_client.get_matches()
            if not matches:
                return []
            
            # 处理数据结构
            if isinstance(matches, dict):
                matches = [matches]
            elif not isinstance(matches, list):
                return []
            
            match_info = []
            for i, match in enumerate(matches[:3]):  # 最多3场比赛
                teams = match.get('teams', [])
                if len(teams) >= 2:
                    event_name = match.get('event', {}).get('name', '未知赛事')
                    stars = '★' * match.get('stars', 0) if match.get('stars', 0) > 0 else '无星级'
                    
                    info = (f"🔴 比赛: {teams[0].get('name', 'TBD')} vs {teams[1].get('name', 'TBD')} "
                           f"({event_name}, {stars})")
                    match_info.append(info)
            
            return match_info
        except Exception as e:
            logger.error(f"获取比赛信息出错: {str(e)}")
            return []


class CS2TopicDetectionAction(BaseAction):
    """CS2/CSGO话题检测Action - 被动响应模式"""
    
    action_name = "cs2_topic_detection"
    action_description = "当明确询问CS2/CSGO信息时提供友好的引导回复"
    activation_type = ActionActivationType.LLM_JUDGE
    
    # LLM判断条件 - 更严格的触发条件
    activation_conditions = [
        "用户明确询问CS2/CSGO相关信息但没有具体指向",
        "用户表达对电竞信息的一般性兴趣",
        "用户询问如何获取CS2/CSGO数据"
    ]
    
    action_parameters = {
        "query_intent": "用户的查询意图描述"
    }
    
    action_require = [
        "当用户询问CS2/CSGO信息但不够具体时使用",
        "当用户需要引导如何获取电竞信息时使用"
    ]
    
    associated_types = ["text"]
    
    async def execute(self) -> Tuple[bool, str]:
        """执行友好引导回复"""
        query_intent = self.action_data.get("query_intent", "")
        
        try:
            logger.info(f"检测到CS2相关话题，可供上下文分析使用")
            return True, "CS2话题检测完成"
        except Exception as e:
            logger.error(f"CS2话题检测执行出错: {str(e)}")
            return False, f"话题检测失败: {str(e)}"


class GetLiveMatchStatusTool(BaseTool):
    """获取进行中比赛的实时状态工具"""
    
    name = "get_live_match_status"
    description = "当用户询问、谈论到实时比赛情况、正在进行的比赛、今天的比赛或即将开始的比赛时使用。可根据战队名称过滤特定比赛"
    parameters = [
        ("match_keywords", ToolParamType.STRING, "比赛关键词（战队名称、赛事名称等）", False, ""),
        ("include_upcoming", ToolParamType.BOOLEAN, "是否包含即将开始的比赛", False, True),
        ("max_matches", ToolParamType.INTEGER, "返回最大比赛数量", False, 10),
    ]
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行实时比赛状态查询"""
        match_keywords = function_args.get("match_keywords", "").strip()
        include_upcoming = function_args.get("include_upcoming", True)
        max_matches = function_args.get("max_matches", 10)
        
        try:
            # 获取实时比赛数据
            matches_data = await self._fetch_live_matches(match_keywords, include_upcoming, max_matches)
            return {"name": self.name, "content": matches_data}
        except Exception as e:
            logger.error(f"获取实时比赛状态失败: {e}")
            return {"name": self.name, "content": "获取实时比赛状态失败"}
    
    async def _fetch_live_matches(self, keywords: str, include_upcoming: bool, max_matches: int) -> str:
        """获取实时比赛数据"""
        try:
            # 获取实时比赛
            live_url = f"{hltv_client.base_url}/matches"
            params = {"live": "true"}
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(live_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        matches = data.get("matches", [])
                        
                        # 过滤关键词
                        if keywords:
                            filtered_matches = []
                            for match in matches:
                                team1 = match.get("team1", {}).get("name", "").lower()
                                team2 = match.get("team2", {}).get("name", "").lower()
                                event = match.get("event", {}).get("name", "").lower()
                                if keywords.lower() in team1 or keywords.lower() in team2 or keywords.lower() in event:
                                    filtered_matches.append(match)
                            matches = filtered_matches
                        
                        # 限制数量
                        matches = matches[:max_matches]
                        
                        if not matches:
                            return "当前没有进行中的比赛"
                        
                        # 格式化输出
                        result = []
                        for match in matches:
                            team1_name = match.get("team1", {}).get("name", "未知")
                            team2_name = match.get("team2", {}).get("name", "未知")
                            event_name = match.get("event", {}).get("name", "未知赛事")
                            status = match.get("status", "未知状态")
                            
                            result.append(f"{team1_name} vs {team2_name} - {event_name} ({status})")
                        
                        return "\n".join(result)
                    else:
                        return "无法获取比赛数据"
        except Exception as e:
            logger.error(f"获取实时比赛数据失败: {e}")
            return "获取比赛数据时发生错误"

class GetPlayerInfoTool(BaseTool):
    """获取选手信息工具"""
    
    name = "get_player_info"
    description = "当用户询问、谈论到特定选手的信息、数据、统计、表现或排名时使用。支持选手昵称和真实姓名查询，可获取Rating、ADR、KAST等详细统计"
    parameters = [
        ("player_name", ToolParamType.STRING, "选手昵称或真实姓名", True, None),
        ("include_stats", ToolParamType.BOOLEAN, "是否包含详细统计数据", False, True),
        ("include_achievements", ToolParamType.BOOLEAN, "是否包含选手成就", False, False),
    ]
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行选手信息查询"""
        player_name = function_args.get("player_name", "").strip()
        include_stats = function_args.get("include_stats", True)
        
        if not player_name:
            return {"name": self.name, "content": "请提供选手名称"}
        
        try:
            # 获取选手列表
            players = await hltv_client.get_players()
            if not players:
                return {"name": self.name, "content": "无法获取选手数据"}
            
            # 查找匹配的选手
            found_player = None
            for player in players:
                nickname = player.get('nickname', '').lower()
                fullname = player.get('name', '').lower()
                
                if (player_name.lower() in nickname or 
                    player_name.lower() in fullname or
                    nickname in player_name.lower()):
                    found_player = player
                    break
            
            if not found_player:
                return {"name": self.name, "content": f"未找到选手 '{player_name}'"}
            
            # 构建选手信息
            result_parts = []
            
            # 基本信息
            nickname = found_player.get('nickname', 'N/A')
            fullname = found_player.get('name', 'N/A')
            country = found_player.get('country', 'N/A')
            team = found_player.get('team', 'N/A')
            age = found_player.get('age', 'N/A')
            
            basic_info = f"选手: {nickname} ({fullname}) | 战队: {team} | 国家: {country} | 年龄: {age}"
            result_parts.append(basic_info)
            
            # 详细统计（如果可用且请求包含）
            if include_stats and 'stats' in found_player:
                stats = found_player['stats']
                rating = stats.get('rating', 'N/A')
                adr = stats.get('adr', 'N/A')
                kast = stats.get('kast', 'N/A')
                impact = stats.get('impact', 'N/A')
                kpr = stats.get('kpr', 'N/A')
                dpr = stats.get('dpr', 'N/A')
                
                stats_info = f"统计: Rating {rating} | Impact {impact} | DPR {dpr} | ADR {adr} | KAST {kast}% | KPR {kpr}"
                result_parts.append(stats_info)
            
            result = "\n".join(result_parts)
            
            return {"name": self.name, "content": result}
            
        except Exception as e:
            return {"name": self.name, "content": f"查询选手信息时出错: {str(e)}"}


class GetTeamInfoTool(BaseTool):
    """获取战队信息工具"""
    
    name = "get_team_info"
    description = "当用户询问、谈论到特定战队的信息、排名、成员阵容或表现时使用。支持战队名称模糊匹配，可获取世界排名、队员构成等信息"
    parameters = [
        ("team_name", ToolParamType.STRING, "战队名称", True, None),
        ("include_players", ToolParamType.BOOLEAN, "是否包含队员信息", False, True),
    ]
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行战队信息查询"""
        team_name = function_args.get("team_name", "").strip()
        include_players = function_args.get("include_players", True)
        
        if not team_name:
            return {"name": self.name, "content": "请提供战队名称"}
        
        try:
            # 获取战队列表
            teams = await hltv_client.get_teams()
            if not teams:
                return {"name": self.name, "content": "无法获取战队数据"}
            
            # 查找匹配的战队
            found_team = None
            for team in teams:
                if team_name.lower() in team.get('name', '').lower():
                    found_team = team
                    break
            
            if not found_team:
                return {"name": self.name, "content": f"未找到战队 '{team_name}'"}
            
            # 构建战队信息
            result_parts = []
            
            # 基本信息
            name = found_team.get('name', 'N/A')
            country = found_team.get('country', 'N/A')
            ranking = found_team.get('ranking', 'N/A')
            
            basic_info = f"战队: {name} | 排名: #{ranking} | 国家: {country}"
            result_parts.append(basic_info)
            
            # 队员信息
            if 'players' in found_team and found_team['players']:
                players_list = []
                for player in found_team['players']:
                    player_name = player.get('nickname', player.get('name', 'Unknown'))
                    player_country = player.get('country', 'N/A')
                    players_list.append(f"{player_name} ({player_country})")
                players_info = f"队员: {', '.join(players_list)}"
                result_parts.append(players_info)
            
            result = "\n".join(result_parts)
            
            return {"name": self.name, "content": result}
            
        except Exception as e:
            return {"name": self.name, "content": f"查询战队信息时出错: {str(e)}"}


class GetMatchInfoTool(BaseTool):
    """获取比赛信息工具"""
    
    name = "get_match_info"
    description = "当用户询问、谈论到特定比赛的信息、结果、详情时使用。可查询比赛的基本信息、比分、时间等"
    parameters = [
        ("match_keywords", ToolParamType.STRING, "比赛关键词（战队名称、赛事名称等）", True, None),
        ("include_results", ToolParamType.BOOLEAN, "是否包含比赛结果", False, True),
        ("max_matches", ToolParamType.INTEGER, "返回最大比赛数量", False, 5),
    ]
    
    @staticmethod
    def get_tool_info():
        return ToolInfo(
            name="get_match_info",
            description="当用户询问、谈论到特定比赛的信息、结果、详情时使用。可查询比赛的基本信息、比分、时间等",
            component_type=ComponentType.TOOL,
            tool_parameters=[
                ("match_keywords", ToolParamType.STRING, "比赛关键词（战队名称、赛事名称等）", True, None),
                ("include_results", ToolParamType.BOOLEAN, "是否包含比赛结果", False, True),
                ("max_matches", ToolParamType.INTEGER, "返回最大比赛数量", False, 5),
            ]
        )
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行比赛信息查询"""
        match_keywords = function_args.get("match_keywords", "").strip()
        include_results = function_args.get("include_results", True)
        max_matches = function_args.get("max_matches", 5)
        
        if not match_keywords:
            return {"name": self.name, "content": "请提供比赛关键词"}
        
        try:
            # 获取比赛数据
            matches_data = await self._fetch_match_info(match_keywords, include_results, max_matches)
            return {"name": self.name, "content": matches_data}
        except Exception as e:
            logger.error(f"获取比赛信息失败: {e}")
            return {"name": self.name, "content": "获取比赛信息失败"}
    
    async def _fetch_match_info(self, keywords: str, include_results: bool, max_matches: int) -> str:
        """获取比赛信息数据"""
        try:
            # 获取比赛数据
            matches_url = f"{hltv_client.base_url}/matches"
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(matches_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        matches = data.get("matches", [])
                        
                        # 过滤关键词
                        filtered_matches = []
                        for match in matches:
                            team1 = match.get("team1", {}).get("name", "").lower()
                            team2 = match.get("team2", {}).get("name", "").lower()
                            event = match.get("event", {}).get("name", "").lower()
                            if keywords.lower() in team1 or keywords.lower() in team2 or keywords.lower() in event:
                                filtered_matches.append(match)
                        
                        # 限制数量
                        filtered_matches = filtered_matches[:max_matches]
                        
                        if not filtered_matches:
                            return "未找到相关比赛信息"
                        
                        # 格式化输出
                        result = []
                        for match in filtered_matches:
                            team1_name = match.get("team1", {}).get("name", "未知")
                            team2_name = match.get("team2", {}).get("name", "未知")
                            event_name = match.get("event", {}).get("name", "未知赛事")
                            date = match.get("date", "未知时间")
                            
                            match_info = f"{team1_name} vs {team2_name} - {event_name} ({date})"
                            
                            if include_results and "result" in match:
                                result_info = match.get("result", {})
                                if result_info:
                                    score = result_info.get("score", "")
                                    if score:
                                        match_info += f" | 比分: {score}"
                            
                            result.append(match_info)
                        
                        return "\n".join(result)
                    else:
                        return "无法获取比赛数据"
        except Exception as e:
            logger.error(f"获取比赛信息失败: {e}")
            return "获取比赛数据时发生错误"


class DetectMatchEventsTool(BaseTool):
    """检测比赛事件工具 - 识别比分变化、重要时刻等"""
    
    name = "detect_match_events"
    description = "当用户询问、谈论到CS比赛事件、比分变化、比赛亮点或重要时刻时使用。可检测比赛开始/结束、比分更新等事件，并按重要性评级"
    parameters = [
        ("importance_threshold", ToolParamType.INTEGER, "事件重要性阈值（1-5），只返回达到此重要性的事件", False, 3),
        ("time_window_minutes", ToolParamType.INTEGER, "检测时间窗口（分钟），只返回此时间内的事件", False, 30),
    ]
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        importance_threshold = function_args.get("importance_threshold", 3)
        time_window_minutes = function_args.get("time_window_minutes", 30)
        
        try:
            # 获取当前比赛数据
            matches = await hltv_client.get_matches()
            if not matches:
                return {"name": self.name, "content": "无法获取比赛数据"}
            
            if isinstance(matches, dict):
                matches = [matches]
            
            # 检测事件
            events = match_event_detector.detect_events(matches)
            
            # 获取最近的重要事件
            recent_events = match_event_detector.get_recent_events(time_window_minutes)
            important_events = [e for e in recent_events if e.importance >= importance_threshold]
            
            if not important_events:
                return {"name": self.name, "content": "当前时间窗口内没有检测到重要比赛事件"}
            
            result_parts = []
            
            for event in important_events:
                # 时间格式化
                time_str = event.timestamp.strftime("%H:%M")
                
                event_detail = f"[{time_str}] {event.description} | 重要性: {event.importance}/5 | 比分: {event.old_score[0]}-{event.old_score[1]} → {event.new_score[0]}-{event.new_score[1]}"
                result_parts.append(event_detail)
            
            result = "\n".join(result_parts)
            logger.info(f"检测到{len(important_events)}个重要比赛事件")
            return {"name": self.name, "content": result}
            
        except Exception as e:
            logger.error(f"检测比赛事件时出错: {str(e)}")
            return {"name": self.name, "content": f"检测比赛事件时出错: {str(e)}"}


class MatchEventNotificationAction(BaseAction):
    """比赛事件检测记录（仅用于上下文分析）"""
    
    name = "match_event_notification"
    description = "检测重要比赛事件并记录，提供上下文信息"
    activation_type = ActionActivationType.LLM_JUDGE
    
    @classmethod
    def get_action_info(cls) -> ActionInfo:
        from src.plugin_system.base.component_types import ComponentType
        return ActionInfo(
            name=cls.name,
            component_type=ComponentType.ACTION,
            description=cls.description,
            activation_type=cls.activation_type,
            llm_judge_prompt="当需要检测CS2/CSGO比赛事件时触发此动作"
        )
    
    async def execute(self) -> Tuple[bool, str]:
        try:
            # 获取当前比赛数据并检测事件
            matches = await hltv_client.get_matches()
            if not matches:
                return False, "无法获取比赛数据"
            
            if isinstance(matches, dict):
                matches = [matches]
            
            # 检测新事件
            events = match_event_detector.detect_events(matches)
            
            # 过滤重要事件
            important_events = [e for e in events if e.importance >= 4]
            
            logger.info(f"检测到{len(important_events)}个重要比赛事件，可供上下文分析使用")
            return True, f"比赛事件检测完成，发现{len(important_events)}个重要事件"
            
        except Exception as e:
            logger.error(f"检测比赛事件时出错: {str(e)}")
            return False, f"事件检测失败: {str(e)}"


class LiveMatchDiscussionAction(BaseAction):
    """实时比赛讨论检测（仅记录模式）"""
    
    name = "live_match_discussion"
    description = "检测用户对实时比赛的讨论，仅用于上下文分析"
    activation_type = ActionActivationType.NEVER
    
    @staticmethod
    def get_action_info() -> ActionInfo:
        return ActionInfo(
            name="live_match_discussion",
            description="检测用户对实时比赛的讨论，仅用于上下文分析",
            component_type=ComponentType.ACTION,
            activation_type=ActionActivationType.NEVER
        )
    
    async def execute(self, context: dict) -> tuple[bool, str]:
        """仅记录，不执行任何操作"""
        return True, "比赛讨论检测完成"


class LiveMatchMonitorAction(BaseAction):
    """实时比赛监控状态记录（仅记录模式）"""
    
    name = "live_match_monitor"
    description = "监控实时比赛状态变化，仅用于上下文分析"
    activation_type = ActionActivationType.NEVER
    
    @staticmethod
    def get_action_info() -> ActionInfo:
        return ActionInfo(
            name="live_match_monitor",
            description="监控实时比赛状态变化，仅用于上下文分析",
            component_type=ComponentType.ACTION,
            activation_type=ActionActivationType.NEVER
        )
    
    async def execute(self, context: dict) -> tuple[bool, str]:
        """仅记录，不执行任何操作"""
        return True, "比赛监控状态记录完成"


@register_plugin
class CS2HLTVPlugin(BasePlugin):
    """CS2/CSGO HLTV信息插件"""
    
    plugin_name = "cs2_hltv_plugin"
    enable_plugin = True
    dependencies = []
    python_dependencies = ["aiohttp"]
    config_file_name = "config.toml"
    
    def __init__(self, plugin_dir: str):
        """初始化CS2 HLTV插件"""
        super().__init__(plugin_dir)
    
    config_section_descriptions = {
        "plugin": "插件基本配置",
        "api": "HLTV API配置", 
        "cache": "数据缓存配置",
        "responses": "响应行为配置"
    }
    
    config_schema = {
        "plugin": {
            "name": ConfigField(type=str, default="cs2_hltv_plugin", description="插件名称"),
            "version": ConfigField(type=str, default="1.0.0", description="插件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        "api": {
            "base_url": ConfigField(
                type=str, 
                default="https://hltv-api.vercel.app/api", 
                description="HLTV API基础URL"
            ),
            "request_timeout": ConfigField(type=int, default=10, description="API请求超时时间(秒)"),
            "retry_attempts": ConfigField(type=int, default=3, description="API请求重试次数"),
        },
        "cache": {
            "player_cache_duration": ConfigField(type=int, default=600, description="选手数据缓存时间(秒)"),
            "team_cache_duration": ConfigField(type=int, default=600, description="战队数据缓存时间(秒)"),
            "match_cache_duration": ConfigField(type=int, default=60, description="比赛数据缓存时间(秒)"),
        },
        "responses": {
            "enable_general_response": ConfigField(type=bool, default=True, description="启用通用CS2话题响应"),
            "enable_live_discussion": ConfigField(type=bool, default=True, description="启用实时比赛讨论参与"),
            "enable_event_notifications": ConfigField(type=bool, default=True, description="启用比赛事件通知"),
            "enable_auto_monitoring": ConfigField(type=bool, default=False, description="启用自动比赛监控"),
            "max_results_per_query": ConfigField(type=int, default=5, description="每次查询最大结果数"),
        }
    }
    
    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (GetCS2ContextInfoTool.get_tool_info(), GetCS2ContextInfoTool),  # 智能上下文信息工具
            (GetLiveMatchStatusTool.get_tool_info(), GetLiveMatchStatusTool),  # 实时比赛状态工具
            (DetectMatchEventsTool.get_tool_info(), DetectMatchEventsTool),  # 比赛事件检测工具
            (LiveMatchDiscussionAction.get_action_info(), LiveMatchDiscussionAction),  # 智能比赛讨论参与
            (MatchEventNotificationAction.get_action_info(), MatchEventNotificationAction),  # 比赛事件通知
            (CS2TopicDetectionAction.get_action_info(), CS2TopicDetectionAction),
            (LiveMatchMonitorAction.get_action_info(), LiveMatchMonitorAction),
            (GetPlayerInfoTool.get_tool_info(), GetPlayerInfoTool),
            (GetTeamInfoTool.get_tool_info(), GetTeamInfoTool),
            (GetMatchInfoTool.get_tool_info(), GetMatchInfoTool),
        ]
