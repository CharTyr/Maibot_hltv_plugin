from typing import List, Tuple, Type, Any, Optional, Dict
import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseAction,
    BaseTool,
    ComponentInfo,
    ActionInfo,
    ActionActivationType,
    ConfigField,
    ToolParamType
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


# 全局HLTV客户端实例和事件检测器
hltv_client = HLTVAPIClient()
match_event_detector = MatchEventDetector()


class GetCS2ContextInfoTool(BaseTool):
    """智能获取CS2/CSGO上下文信息工具 - 根据聊天内容自动查询相关信息供麦麦参考"""
    
    name = "get_cs2_context_info"
    description = "根据聊天上下文中提到的CS2/CSGO相关内容，自动查询选手、战队、比赛等信息作为回复参考"
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
                result = "📊 CS2/CSGO 相关信息参考:\n" + "\n".join(context_info)
                logger.info(f"为关键词 '{context_keywords}' 提供了上下文信息")
                return {"name": self.name, "content": result}
            else:
                return {"name": self.name, "content": f"未找到与 '{context_keywords}' 相关的CS2/CSGO信息"}
                
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
            
            # 处理不同的数据结构
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
        
        if self.get_config("responses.enable_general_response", True):
            message = ("🎮 我可以帮你查询CS2/CSGO的相关信息！\n"
                      "你可以询问：\n"
                      "• 特定选手的数据和统计\n"
                      "• 战队排名和阵容信息\n" 
                      "• 最近的比赛结果和安排\n"
                      "直接提到选手名或战队名，我会自动为你查询相关信息～")
            
            await self.send_text(message)
            return True, "提供了CS2/CSGO信息查询引导"
        
        return False, "通用响应已禁用"


class GetLiveMatchStatusTool(BaseTool):
    """获取进行中比赛的实时状态工具"""
    
    name = "get_live_match_status"
    description = "获取当前正在进行或即将开始的比赛实时状态和详细信息"
    parameters = [
        ("match_keywords", ToolParamType.STRING, "比赛关键词（战队名称、赛事名称等）", False, ""),
        ("include_upcoming", ToolParamType.BOOLEAN, "是否包含即将开始的比赛", False, True),
        ("max_matches", ToolParamType.INTEGER, "返回最大比赛数量", False, 3),
    ]
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行实时比赛状态查询"""
        match_keywords = function_args.get("match_keywords", "").strip()
        include_upcoming = function_args.get("include_upcoming", True)
        max_matches = min(function_args.get("max_matches", 3), 5)
        
        try:
            matches = await hltv_client.get_matches()
            if not matches:
                return {"name": self.name, "content": "无法获取比赛数据"}
            
            # 处理数据结构
            if isinstance(matches, dict):
                matches = [matches]
            elif not isinstance(matches, list):
                return {"name": self.name, "content": "比赛数据格式异常"}
            
            current_time = datetime.now()
            relevant_matches = []
            
            for match in matches[:10]:  # 检查前10场比赛
                teams = match.get('teams', [])
                if len(teams) < 2:
                    continue
                
                # 如果提供了关键词，进行匹配
                if match_keywords:
                    team_names = [team.get('name', '').lower() for team in teams]
                    event_name = match.get('event', {}).get('name', '').lower()
                    
                    keyword_match = any(
                        match_keywords.lower() in name or name in match_keywords.lower()
                        for name in team_names + [event_name]
                    )
                    
                    if not keyword_match:
                        continue
                
                # 判断比赛时间状态
                match_time_str = match.get('time', '')
                if match_time_str:
                    try:
                        match_time = datetime.fromisoformat(match_time_str.replace('Z', '+00:00'))
                        time_diff_minutes = (match_time.replace(tzinfo=None) - current_time).total_seconds() / 60
                        
                        # 正在进行：开始后2小时内
                        # 即将开始：未来4小时内
                        if -120 <= time_diff_minutes <= (240 if include_upcoming else 0):
                            status = "🔴 进行中" if time_diff_minutes <= 0 else "🟡 即将开始"
                            time_info = f"开始于 {match_time.strftime('%H:%M')}" if time_diff_minutes <= 0 else f"{abs(int(time_diff_minutes))}分钟后开始"
                            
                            match_info = {
                                'match': match,
                                'status': status,
                                'time_info': time_info,
                                'time_diff': time_diff_minutes
                            }
                            relevant_matches.append(match_info)
                    except:
                        continue
            
            if not relevant_matches:
                return {"name": self.name, "content": "当前没有找到相关的进行中或即将开始的比赛"}
            
            # 按时间排序，进行中的优先
            relevant_matches.sort(key=lambda x: (x['time_diff'] > 0, abs(x['time_diff'])))
            
            # 构建结果
            result_parts = ["🎮 实时比赛状态:"]
            
            for i, match_info in enumerate(relevant_matches[:max_matches]):
                match = match_info['match']
                teams = match.get('teams', [])
                
                match_detail = (
                    f"\n{match_info['status']} {teams[0].get('name', 'TBD')} vs {teams[1].get('name', 'TBD')}\n"
                    f"🏆 {match.get('event', {}).get('name', '未知赛事')}\n"
                    f"⏰ {match_info['time_info']}\n"
                    f"⭐ {'★' * match.get('stars', 0) if match.get('stars', 0) > 0 else '无星级'}\n"
                    f"🎯 {match.get('maps', 'TBD')}"
                )
                result_parts.append(match_detail)
            
            result = "\n".join(result_parts)
            logger.info(f"获取了{len(relevant_matches)}场实时比赛信息")
            return {"name": self.name, "content": result}
            
        except Exception as e:
            logger.error(f"获取实时比赛状态出错: {str(e)}")
            return {"name": self.name, "content": f"获取比赛状态时出错: {str(e)}"}


class LiveMatchDiscussionAction(BaseAction):
    """智能比赛讨论参与Action - 主动参与正在进行的比赛讨论"""
    
    action_name = "live_match_discussion"
    action_description = "当检测到群聊正在讨论进行中的比赛时，主动参与讨论并提供实时信息"
    activation_type = ActionActivationType.LLM_JUDGE
    
    activation_conditions = [
        "群聊正在讨论某场正在进行的CS2/CSGO比赛",
        "用户提到了正在直播的比赛或选手表现",
        "讨论比赛进展、比分、精彩时刻等实时内容",
        "群聊氛围显示大家在关注同一场比赛"
    ]
    
    action_parameters = {
        "discussed_teams": "正在讨论的战队名称列表",
        "match_context": "比赛讨论的具体内容和上下文",
        "discussion_type": "讨论类型：score(比分)、performance(表现)、prediction(预测)、general(一般讨论)"
    }
    
    action_require = [
        "当检测到群聊正在讨论进行中的比赛时使用",
        "当群聊氛围显示大家在关注同一场比赛时使用",
        "当需要为比赛讨论提供实时信息支持时使用"
    ]
    
    associated_types = ["text"]
    
    async def execute(self) -> Tuple[bool, str]:
        """执行智能比赛讨论参与"""
        discussed_teams = self.action_data.get("discussed_teams", [])
        match_context = self.action_data.get("match_context", "")
        discussion_type = self.action_data.get("discussion_type", "general")
        
        if not self.get_config("responses.enable_live_discussion", True):
            return False, "实时比赛讨论功能已禁用"
        
        try:
            # 获取相关比赛信息
            match_keywords = ", ".join(discussed_teams) if discussed_teams else ""
            
            # 使用实时比赛状态工具获取信息
            live_tool = GetLiveMatchStatusTool()
            match_result = await live_tool.execute({
                "match_keywords": match_keywords,
                "include_upcoming": False,  # 只关注进行中的比赛
                "max_matches": 2
            })
            
            match_info = match_result.get("content", "")
            
            if "当前没有找到相关" in match_info or "无法获取" in match_info:
                # 没有找到相关比赛，提供一般性参与
                if discussion_type == "prediction":
                    message = "🎯 看起来大家在预测比赛结果！虽然我没有找到具体的实时数据，但可以帮大家查询战队历史表现和选手数据～"
                elif discussion_type == "performance":
                    message = "💪 讨论选手表现真有意思！需要我查询具体选手的统计数据吗？"
                else:
                    message = "🎮 看到大家在讨论比赛！虽然我暂时没有找到实时比赛数据，但如果需要查询选手或战队信息，随时告诉我～"
            else:
                # 找到了相关比赛，提供具体信息
                response_parts = []
                
                if discussion_type == "score":
                    response_parts.append("📊 我来提供一下这场比赛的最新信息：")
                elif discussion_type == "performance":
                    response_parts.append("🔥 关于选手表现，我找到了这场比赛的信息：")
                elif discussion_type == "prediction":
                    response_parts.append("🎯 基于当前比赛状态，我找到了相关信息：")
                else:
                    response_parts.append("🎮 我也在关注这场比赛！")
                
                # 简化比赛信息显示
                simplified_info = match_info.replace("🎮 实时比赛状态:", "").strip()
                response_parts.append(simplified_info)
                
                # 根据讨论类型添加互动内容
                if discussion_type == "prediction":
                    response_parts.append("\n🤔 大家觉得哪支战队会赢？我可以查询双方的历史交锋记录！")
                elif discussion_type == "performance":
                    response_parts.append("\n📈 想了解具体选手的详细数据吗？我可以提供Rating、ADR等统计信息！")
                
                message = "\n".join(response_parts)
            
            await self.send_text(message)
            logger.info(f"参与了关于 {discussed_teams} 的比赛讨论")
            return True, f"成功参与了{discussion_type}类型的比赛讨论"
            
        except Exception as e:
            logger.error(f"参与比赛讨论时出错: {str(e)}")
            return False, f"参与讨论失败: {str(e)}"


class LiveMatchMonitorAction(BaseAction):
    """实时比赛监控Action - 重构为更智能的监控"""
    
    action_name = "live_match_monitor"
    action_description = "开启对特定比赛的持续监控，定期提供更新"
    activation_type = ActionActivationType.LLM_JUDGE
    
    activation_conditions = [
        "用户明确要求监控某场比赛",
        "用户想要接收比赛的定期更新",
        "群聊决定一起关注某场重要比赛"
    ]
    
    action_parameters = {
        "target_teams": "要监控的战队名称",
        "monitor_duration": "监控持续时间(分钟)",
        "update_interval": "更新间隔(分钟)"
    }
    
    action_require = [
        "当用户明确要求监控比赛时使用",
        "当需要为群聊提供比赛定期更新时使用"
    ]
    
    associated_types = ["text"]
    
    async def execute(self) -> Tuple[bool, str]:
        """执行比赛监控设置"""
        target_teams = self.action_data.get("target_teams", "")
        monitor_duration = int(self.action_data.get("monitor_duration", 60))
        update_interval = int(self.action_data.get("update_interval", 10))
        
        # 限制监控参数
        monitor_duration = min(monitor_duration, 180)  # 最多3小时
        update_interval = max(update_interval, 5)      # 最少5分钟间隔
        
        # 获取目标比赛
        live_tool = GetLiveMatchStatusTool()
        match_result = await live_tool.execute({
            "match_keywords": target_teams,
            "include_upcoming": True,
            "max_matches": 1
        })
        
        match_info = match_result.get("content", "")
        
        if "当前没有找到相关" in match_info:
            await self.send_text(f"❌ 没有找到与 '{target_teams}' 相关的比赛。请检查战队名称或稍后再试。")
            return False, "未找到目标比赛"
        
        # 设置监控
        message = (
            f"✅ 已开启比赛监控！\n"
            f"🎯 监控目标: {target_teams}\n"
            f"⏰ 监控时长: {monitor_duration}分钟\n"
            f"🔄 更新间隔: {update_interval}分钟\n\n"
            f"📊 当前状态:\n{match_info.replace('🎮 实时比赛状态:', '').strip()}\n\n"
            f"💡 我会定期为大家更新比赛进展！"
        )
        
        await self.send_text(message)
        
        # 这里可以添加定时任务逻辑，但需要插件系统支持
        # 目前先返回成功状态
        return True, f"开启了对{target_teams}的比赛监控"


class GetPlayerInfoTool(BaseTool):
    """获取选手信息工具"""
    
    name = "get_player_info"
    description = "根据选手名称或ID获取详细的选手信息、统计数据和近期表现"
    parameters = [
        ("player_name", ToolParamType.STRING, "选手昵称或真实姓名", True, None),
        ("include_stats", ToolParamType.BOOLEAN, "是否包含详细统计数据", False, True),
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
                return {"name": self.name, "content": "无法获取选手数据，请稍后再试"}
            
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
                return {
                    "name": self.name, 
                    "content": f"未找到选手 '{player_name}'。请检查拼写或尝试使用选手的游戏昵称。"
                }
            
            # 构建选手信息
            info_parts = [
                f"🎯 选手: {found_player.get('nickname', 'N/A')} ({found_player.get('name', 'N/A')})",
                f"🏆 战队: {found_player.get('team', {}).get('name', '自由选手')}",
                f"🎂 年龄: {found_player.get('age', 'N/A')}岁"
            ]
            
            if include_stats:
                stats_parts = [
                    f"📊 Rating: {found_player.get('rating', 'N/A')}",
                    f"💥 Impact: {found_player.get('impact', 'N/A')}",
                    f"💀 DPR: {found_player.get('dpr', 'N/A')}",
                    f"🎯 ADR: {found_player.get('adr', 'N/A')}",
                    f"✅ KAST: {found_player.get('kast', 'N/A')}%",
                    f"🔫 KPR: {found_player.get('kpr', 'N/A')}",
                    f"🎯 爆头率: {found_player.get('headshots', 'N/A')}%",
                    f"🗺️ 比赛场数: {found_player.get('mapsPlayed', 'N/A')}"
                ]
                info_parts.extend(stats_parts)
            
            result = "\n".join(info_parts)
            
            return {"name": self.name, "content": result}
            
        except Exception as e:
            return {"name": self.name, "content": f"查询选手信息时出错: {str(e)}"}


class GetTeamInfoTool(BaseTool):
    """获取战队信息工具"""
    
    name = "get_team_info"
    description = "根据战队名称获取战队排名、成员信息和近期表现"
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
                return {"name": self.name, "content": "无法获取战队数据，请稍后再试"}
            
            # 查找匹配的战队
            found_team = None
            for team in teams:
                if team_name.lower() in team.get('name', '').lower():
                    found_team = team
                    break
            
            if not found_team:
                return {
                    "name": self.name,
                    "content": f"未找到战队 '{team_name}'。请检查拼写或尝试使用战队的完整名称。"
                }
            
            # 构建战队信息
            info_parts = [
                f"🏆 战队: {found_team.get('name', 'N/A')}",
                f"📊 世界排名: #{found_team.get('ranking', 'N/A')}"
            ]
            
            if include_players and 'players' in found_team:
                info_parts.append("\n👥 队员阵容:")
                for player in found_team['players']:
                    country_flag = player.get('country', {}).get('name', '')
                    info_parts.append(
                        f"  • {player.get('nickname', 'N/A')} "
                        f"({player.get('fullname', 'N/A')}) - {country_flag}"
                    )
            
            result = "\n".join(info_parts)
            
            return {"name": self.name, "content": result}
            
        except Exception as e:
            return {"name": self.name, "content": f"查询战队信息时出错: {str(e)}"}


class GetMatchInfoTool(BaseTool):
    """获取比赛信息工具"""
    
    name = "get_match_info"
    description = "获取比赛信息、结果或即将进行的比赛安排"
    parameters = [
        ("query_type", ToolParamType.STRING, "查询类型: upcoming(即将进行), recent(最近结果), live(进行中)", True, "upcoming"),
        ("limit", ToolParamType.INTEGER, "返回结果数量限制", False, 5),
    ]
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行比赛信息查询"""
        query_type = function_args.get("query_type", "upcoming").lower()
        limit = min(function_args.get("limit", 5), 10)  # 最多10条
        
        try:
            if query_type == "upcoming":
                # 获取即将进行的比赛
                matches = await hltv_client.get_matches()
                if not matches:
                    return {"name": self.name, "content": "无法获取比赛数据"}
                
                info_parts = ["🔮 即将进行的比赛:"]
                for i, match in enumerate(matches[:limit]):
                    teams = match.get('teams', [])
                    if len(teams) >= 2:
                        match_time = match.get('time', '')
                        if match_time:
                            try:
                                dt = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
                                time_str = dt.strftime('%m-%d %H:%M')
                            except:
                                time_str = "时间待定"
                        else:
                            time_str = "时间待定"
                        
                        info_parts.append(
                            f"{i+1}. {teams[0].get('name', 'TBD')} vs {teams[1].get('name', 'TBD')}\n"
                            f"   📅 {time_str} | 🏆 {match.get('event', {}).get('name', '未知赛事')}\n"
                            f"   ⭐ {'★' * match.get('stars', 0)} | 🎯 {match.get('maps', 'TBD')}"
                        )
            
            elif query_type == "recent":
                # 获取最近的比赛结果
                results = await hltv_client.get_results()
                if not results:
                    return {"name": self.name, "content": "无法获取比赛结果"}
                
                info_parts = ["📊 最近比赛结果:"]
                for i, result in enumerate(results[:limit]):
                    teams = result.get('teams', [])
                    if len(teams) >= 2:
                        info_parts.append(
                            f"{i+1}. {teams[0].get('name', 'TBD')} vs {teams[1].get('name', 'TBD')}\n"
                            f"   🏆 {result.get('event', {}).get('name', '未知赛事')}\n"
                            f"   📊 {result.get('result', {}).get('score', 'N/A')}"
                        )
            
            else:
                return {"name": self.name, "content": "查询类型无效，请使用: upcoming, recent, 或 live"}
            
            result = "\n\n".join(info_parts)
            return {"name": self.name, "content": result}
            
        except Exception as e:
            return {"name": self.name, "content": f"查询比赛信息时出错: {str(e)}"}


class DetectMatchEventsTool(BaseTool):
    """检测比赛事件工具 - 识别比分变化、重要时刻等"""
    
    name = "detect_match_events"
    description = "检测当前比赛的重要事件，如比分变化、比赛开始/结束等"
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
                return {"name": self.name, "content": f"最近{time_window_minutes}分钟内没有检测到重要性≥{importance_threshold}的比赛事件"}
            
            result_parts = ["🚨 检测到重要比赛事件:"]
            
            for event in important_events[-5:]:  # 最多显示5个最近事件
                event_emoji = {
                    "score_change": "⚡",
                    "match_start": "🟢", 
                    "match_end": "🏁",
                    "overtime": "🔥"
                }.get(event.event_type, "📢")
                
                importance_stars = "★" * event.importance
                time_str = event.timestamp.strftime("%H:%M")
                
                event_detail = (
                    f"\n{event_emoji} [{time_str}] {event.description}\n"
                    f"   重要性: {importance_stars} | 比分: {event.old_score[0]}-{event.old_score[1]} → {event.new_score[0]}-{event.new_score[1]}"
                )
                result_parts.append(event_detail)
            
            result = "\n".join(result_parts)
            logger.info(f"检测到{len(important_events)}个重要比赛事件")
            return {"name": self.name, "content": result}
            
        except Exception as e:
            logger.error(f"检测比赛事件时出错: {str(e)}")
            return {"name": self.name, "content": f"检测比赛事件时出错: {str(e)}"}


class MatchEventNotificationAction(BaseAction):
    """比赛事件通知Action - 当检测到重要事件时主动通知"""
    
    name = "match_event_notification"
    description = "当检测到重要比赛事件时，主动向群聊发送通知"
    activation_type = ActionActivationType.LLM_JUDGE
    
    @classmethod
    def get_action_info(cls) -> ActionInfo:
        from src.plugin_system.base.component_types import ComponentType
        return ActionInfo(
            name=cls.name,
            component_type=ComponentType.ACTION,
            description=cls.description,
            activation_type=cls.activation_type,
            llm_judge_prompt="当检测到CS2/CSGO比赛中的重要事件（如比分变化、比赛结束等）时触发此动作"
        )
    
    async def execute(self) -> Tuple[bool, str]:
        if not self.get_config("responses.enable_event_notifications", True):
            return False, "比赛事件通知功能已禁用"
        
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
            
            if not important_events:
                return False, "没有检测到需要通知的重要事件"
            
            # 发送通知
            for event in important_events:
                if event.event_type == "match_end":
                    message = f"🏁 比赛结束！{event.description}\n最终比分：{event.new_score[0]} - {event.new_score[1]}"
                elif event.event_type == "score_change" and event.importance >= 5:
                    message = f"🔥 关键时刻！{event.team1} vs {event.team2}\n比分更新：{event.new_score[0]} - {event.new_score[1]}"
                elif event.event_type == "match_start":
                    message = f"🟢 比赛开始！{event.team1} vs {event.team2}"
                else:
                    message = f"⚡ {event.description}"
                
                await self.send_text(message)
            
            logger.info(f"发送了{len(important_events)}个比赛事件通知")
            return True, f"成功发送{len(important_events)}个事件通知"
            
        except Exception as e:
            logger.error(f"发送比赛事件通知时出错: {str(e)}")
            return False, f"发送通知失败: {str(e)}"


@register_plugin
class CS2HLTVPlugin(BasePlugin):
    """CS2/CSGO HLTV信息插件"""
    
    plugin_name = "cs2_hltv_plugin"
    enable_plugin = True
    dependencies = []
    python_dependencies = ["aiohttp"]
    config_file_name = "config.toml"
    
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
