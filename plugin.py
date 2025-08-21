#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CS2 HLTV插件 v3.0.0 - 诚实版本，不提供虚假数据
"""

from typing import List, Tuple, Type, Any, Optional, Dict, Set, Union
import asyncio
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field

# MaiBot imports
from maibot.plugin import BaseTool, BaseAction, BasePlugin

# 导入诚实的HLTV客户端
from .realistic_hltv_client import HonestHLTVPlugin

# 设置日志
logger = logging.getLogger("plugin")

# 全局诚实插件实例
honest_plugin = HonestHLTVPlugin()


# 保留旧的客户端类以兼容性（已弃用）
class HLTVAsyncClient:
    """已弃用：基于hltv-async-api的HLTV客户端，现在使用诚实版本"""
    
    def __init__(self):
        self.logger = logging.getLogger('plugin')
        self.logger.warning("HLTV数据获取受到严格限制，将返回诚实的结果")
    
    async def get_matches(self, days: int = 1, live_only: bool = False) -> List[Dict]:
        """重定向到诚实插件"""
        result = await honest_plugin.get_cs2_matches()
        return result.get('data', [])
    
    async def get_team_ranking(self, max_teams: int = 30) -> List[Dict]:
        """重定向到诚实插件"""
        result = await honest_plugin.get_team_rankings()
        return result.get('data', [])
    
    async def get_match_results(self, days: int = 7, max_results: int = 20) -> List[Dict]:
        """重定向到诚实插件"""
        result = await honest_plugin.get_match_results()
        return result.get('data', [])


# 全局客户端实例（向后兼容）
hltv_client = HLTVAsyncClient()


class GetCurrentMatchContextTool(BaseTool):
    """获取当前比赛上下文工具"""
    
    name = "GetCurrentMatchContextTool"
    description = "获取CS2比赛的实时上下文信息，包括比分、状态、参赛队伍等。当用户询问或谈论到特定战队的比赛情况时使用。"
    
    parameters = {
        "match_identifier": {
            "type": "string",
            "description": "比赛标识符，可以是战队名称、比赛ID或关键词",
            "required": True
        },
        "context_depth": {
            "type": "string", 
            "description": "上下文深度级别",
            "enum": ["basic", "detailed", "full"],
            "default": "basic"
        }
    }
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行工具"""
        match_identifier = function_args.get("match_identifier", "")
        context_depth = function_args.get("context_depth", "basic")
        
        try:
            # 获取所有比赛
            matches = await hltv_client.get_matches(days=1, live_only=False)
            
            if not matches:
                return {
                    "name": self.name,
                    "content": "由于HLTV反爬虫限制，无法获取实时比赛数据。请访问 https://www.hltv.org/matches 查看最新比赛信息。"
                }
            
            # 查找匹配的比赛
            target_match = None
            for match in matches:
                if (match_identifier.lower() in match.get('team1', '').lower() or 
                    match_identifier.lower() in match.get('team2', '').lower() or
                    match_identifier.lower() in match.get('event', '').lower()):
                    target_match = match
                    break
            
            if not target_match:
                return {
                    "name": self.name,
                    "content": f"未找到与 '{match_identifier}' 相关的比赛。由于HLTV限制，建议直接访问官网查看。"
                }
            
            # 根据深度返回不同详细程度的信息
            if context_depth == "basic":
                if target_match.status == "live":
                    content = f"【实时比赛】{target_match.team1} {target_match.score1}-{target_match.score2} {target_match.team2}\n更新时间: {datetime.now().strftime('%H:%M')}"
                else:
                    content = f"{target_match.team1} vs {target_match.team2} - {target_match.event} ({target_match.date} {target_match.time})"
            
            elif context_depth == "detailed":
                content = f"比赛: {target_match.team1} vs {target_match.team2}\n"
                content += f"赛事: {target_match.event}\n"
                content += f"时间: {target_match.date} {target_match.time}\n"
                content += f"状态: {'正在进行' if target_match.status == 'live' else '即将开始'}\n"
                content += f"星级: {'⭐' * target_match.rating}"
                
                if target_match.status == "live":
                    content += f"\n当前比分: {target_match.score1}-{target_match.score2}"
            
            else:  # full
                content = f"【详细比赛信息】\n"
                content += f"比赛ID: {target_match.match_id}\n"
                content += f"对阵: {target_match.team1} vs {target_match.team2}\n"
                content += f"赛事: {target_match.event}\n"
                content += f"时间: {target_match.date} {target_match.time}\n"
                content += f"重要程度: {target_match.rating}/5 星\n"
                content += f"状态: {'🔴 正在进行' if target_match.status == 'live' else '⏰ 即将开始'}\n"
                
                if target_match.status == "live":
                    content += f"实时比分: {target_match.team1} {target_match.score1} - {target_match.score2} {target_match.team2}\n"
                    content += f"最后更新: {datetime.now().strftime('%H:%M:%S')}"
            
            return {
                "name": self.name,
                "content": content
            }
            
        except Exception as e:
            logger.error(f"GetCurrentMatchContextTool执行失败: {e}")
            return {
                "name": self.name,
                "content": "获取比赛信息时出现错误，请稍后重试"
            }


class GetLiveMatchStatusTool(BaseTool):
    """获取实时比赛状态工具"""
    
    name = "GetLiveMatchStatusTool"
    description = "获取当前正在进行的CS2比赛状态。当用户询问现在有什么比赛或想了解实时比赛情况时使用。"
    
    parameters = {
        "match_keywords": {
            "type": "string",
            "description": "比赛关键词过滤（可选）",
            "required": False
        },
        "include_upcoming": {
            "type": "array",
            "items": {"type": "boolean"},
            "description": "是否包含即将开始的比赛",
            "default": None
        },
        "max_matches": {
            "type": "integer",
            "description": "最大返回比赛数量",
            "default": None
        }
    }
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行工具"""
        match_keywords = function_args.get("match_keywords", "")
        include_upcoming = function_args.get("include_upcoming", [True])
        max_matches = function_args.get("max_matches", 5)
        
        # 处理include_upcoming参数
        include_upcoming_bool = include_upcoming[0] if include_upcoming else True
        
        try:
            # 获取比赛数据
            matches = await hltv_client.get_matches(days=1, live_only=False)
            
            # 过滤比赛
            filtered_matches = []
            for match in matches:
                # 关键词过滤
                if match_keywords:
                    if not (match_keywords.lower() in match.team1.lower() or 
                           match_keywords.lower() in match.team2.lower() or
                           match_keywords.lower() in match.event.lower()):
                        continue
                
                # 状态过滤
                if match.status == "live":
                    filtered_matches.append(match)
                elif include_upcoming_bool and match.status == "scheduled":
                    filtered_matches.append(match)
            
            if not filtered_matches:
                return {
                    "name": self.name,
                    "content": "当前没有找到符合条件的比赛"
                }
            
            # 限制数量
            if max_matches:
                filtered_matches = filtered_matches[:max_matches]
            
            # 构建响应
            content = f"找到 {len(filtered_matches)} 场比赛:\n\n"
            
            for i, match in enumerate(filtered_matches, 1):
                status_icon = "🔴" if match.status == "live" else "⏰"
                content += f"{i}. {status_icon} {match.team1} vs {match.team2}\n"
                content += f"   赛事: {match.event}\n"
                
                if match.status == "live":
                    content += f"   比分: {match.score1}-{match.score2} (进行中)\n"
                else:
                    content += f"   时间: {match.date} {match.time}\n"
                
                content += f"   重要程度: {'⭐' * match.rating}\n\n"
            
            return {
                "name": self.name,
                "content": content.strip()
            }
            
        except Exception as e:
            logger.error(f"GetLiveMatchStatusTool执行失败: {e}")
            return {
                "name": self.name,
                "content": "获取比赛状态时出现错误，请稍后重试"
            }


class GetTeamInfoTool(BaseTool):
    """获取战队信息工具"""
    
    name = "GetTeamInfoTool"
    description = "获取CS2战队的详细信息，包括排名、积分、近期表现等。当用户询问特定战队信息时使用。"
    
    parameters = {
        "team_name": {
            "type": "string",
            "description": "战队名称",
            "required": True
        },
        "include_ranking": {
            "type": "array",
            "items": {"type": "boolean"},
            "description": "是否包含排名信息",
            "default": None
        }
    }
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行工具"""
        team_name = function_args.get("team_name", "")
        include_ranking = function_args.get("include_ranking", [True])
        
        # 处理include_ranking参数
        include_ranking_bool = include_ranking[0] if include_ranking else True
        
        try:
            content = f"【{team_name} 战队信息】\n\n"
            
            if include_ranking_bool:
                # 获取战队排名
                teams = await hltv_client.get_team_ranking(max_teams=30)
                
                team_info = None
                for team in teams:
                    if team_name.lower() in team.get('title', '').lower():
                        team_info = team
                        break
                
                if team_info:
                    content += f"世界排名: #{team_info.get('rank', 'N/A')}\n"
                    content += f"积分: {team_info.get('points', 'N/A')}\n"
                    content += f"排名变化: {team_info.get('change', '-')}\n\n"
                else:
                    content += f"未找到 {team_name} 的排名信息\n\n"
            
            # 获取近期比赛
            matches = await hltv_client.get_matches(days=7, live_only=False)
            team_matches = []
            
            for match in matches:
                if (team_name.lower() in match.team1.lower() or 
                    team_name.lower() in match.team2.lower()):
                    team_matches.append(match)
            
            if team_matches:
                content += "近期比赛:\n"
                for match in team_matches[:3]:
                    status = "进行中" if match.status == "live" else f"{match.date} {match.time}"
                    content += f"• {match.team1} vs {match.team2} ({match.event}) - {status}\n"
            else:
                content += "暂无近期比赛信息\n"
            
            return {
                "name": self.name,
                "content": content
            }
            
        except Exception as e:
            logger.error(f"GetTeamInfoTool执行失败: {e}")
            return {
                "name": self.name,
                "content": f"获取 {team_name} 信息时出现错误，请稍后重试"
            }


class GetMatchResultsTool(BaseTool):
    """获取比赛结果工具"""
    
    name = "GetMatchResultsTool"
    description = "获取最近的CS2比赛结果。当用户询问比赛结果或想了解最近比赛情况时使用。"
    
    parameters = {
        "days": {
            "type": "integer",
            "description": "查询最近几天的结果",
            "default": 3
        },
        "team_filter": {
            "type": "string",
            "description": "战队名称过滤（可选）",
            "required": False
        },
        "max_results": {
            "type": "integer",
            "description": "最大返回结果数量",
            "default": 10
        }
    }
    
    async def execute(self, function_args: dict[str, Any]) -> dict[str, Any]:
        """执行工具"""
        days = function_args.get("days", 3)
        team_filter = function_args.get("team_filter", "")
        max_results = function_args.get("max_results", 10)
        
        try:
            results = await hltv_client.get_match_results(days=days, max_results=max_results)
            
            if not results:
                return {
                    "name": self.name,
                    "content": "未找到最近的比赛结果"
                }
            
            # 过滤结果
            if team_filter:
                filtered_results = []
                for result in results:
                    if (team_filter.lower() in result.get('team1', '').lower() or
                        team_filter.lower() in result.get('team2', '').lower()):
                        filtered_results.append(result)
                results = filtered_results
            
            if not results:
                return {
                    "name": self.name,
                    "content": f"未找到与 '{team_filter}' 相关的比赛结果"
                }
            
            content = f"最近 {days} 天的比赛结果:\n\n"
            
            for i, result in enumerate(results[:max_results], 1):
                team1 = result.get('team1', 'TBD')
                team2 = result.get('team2', 'TBD')
                score1 = result.get('score1', '0')
                score2 = result.get('score2', '0')
                event = result.get('event', 'Unknown Event')
                
                # 判断胜负
                winner = team1 if int(score1) > int(score2) else team2
                content += f"{i}. {team1} {score1}-{score2} {team2}\n"
                content += f"   胜者: {winner} | 赛事: {event}\n\n"
            
            return {
                "name": self.name,
                "content": content.strip()
            }
            
        except Exception as e:
            logger.error(f"GetMatchResultsTool执行失败: {e}")
            return {
                "name": self.name,
                "content": "获取比赛结果时出现错误，请稍后重试"
            }


# Action组件（仅记录，不主动发送消息）
class CS2TopicDetectionAction(BaseAction):
    """CS2话题检测Action"""
    
    name = "CS2TopicDetectionAction"
    description = "检测群聊中的CS2相关话题讨论"
    
    async def execute(self, message_data: dict) -> dict:
        """执行Action - 仅记录，不发送消息"""
        message_content = message_data.get("content", "").lower()
        
        cs2_keywords = [
            "cs2", "csgo", "反恐精英", "hltv", "major", "比赛", "战队",
            "navi", "faze", "vitality", "astralis", "g2", "spirit"
        ]
        
        detected_keywords = [kw for kw in cs2_keywords if kw in message_content]
        
        if detected_keywords:
            logger.info(f"检测到CS2话题: {detected_keywords}")
        
        return {"detected": len(detected_keywords) > 0, "keywords": detected_keywords}


class CS2HLTVPlugin(BasePlugin):
    """CS2 HLTV插件主类"""
    
    name = "cs2_hltv_plugin"
    version = "3.0.0"
    description = "CS2/CSGO数据查询插件：目前无法绕过HLTV反爬虫，不提供模拟/虚假数据，受限时返回引导信息"
    
    dependencies = []
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("plugin")
    
    async def on_plugin_load(self):
        """插件加载时的初始化"""
        self.logger.info("CS2 HLTV插件 v3.0.0 已加载（诚实版：不抓取、不绕过反爬虫、无模拟数据）")
        self.logger.info("当HLTV数据受限时，工具将返回空结果与官方渠道指引。")
    
    async def on_plugin_unload(self):
        """插件卸载时的清理"""
        self.logger.info("CS2 HLTV插件已卸载")
    
    def get_tools(self) -> List[Type[BaseTool]]:
        """返回工具列表"""
        return [
            GetCurrentMatchContextTool,
            GetLiveMatchStatusTool,
            GetTeamInfoTool,
            GetMatchResultsTool
        ]
    
    def get_actions(self) -> List[Type[BaseAction]]:
        """返回Action列表"""
        return [
            CS2TopicDetectionAction
        ]


# 导出插件类
plugin_class = CS2HLTVPlugin
