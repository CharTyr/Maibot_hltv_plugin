#!/usr/bin/env python3
"""
CS2 HLTV Plugin Test Script
测试插件的各项功能，包括新增的实时比赛功能
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plugin import (
    HLTVAPIClient, 
    GetCS2ContextInfoTool,
    CS2TopicDetectionAction,
    GetPlayerInfoTool,
    GetTeamInfoTool,
    GetMatchInfoTool,
    GetLiveMatchStatusTool,
    LiveMatchDiscussionAction,
    LiveMatchMonitorAction,
    DetectMatchEventsTool,
    MatchEventNotificationAction,
    match_event_detector
)

async def test_hltv_api():
    """测试HLTV API连接"""
    print("🔍 测试HLTV API连接...")
    client = HLTVAPIClient()
    
    # 测试获取比赛数据
    matches = await client.get_matches()
    if matches:
        print(f"✅ 成功获取比赛数据，共{len(matches) if isinstance(matches, list) else 1}场比赛")
        if isinstance(matches, list) and matches:
            first_match = matches[0]
            teams = first_match.get('teams', [])
            if len(teams) >= 2:
                print(f"   示例比赛: {teams[0].get('name', 'N/A')} vs {teams[1].get('name', 'N/A')}")
            else:
                print(f"   示例比赛: {first_match.get('event', {}).get('name', 'N/A')}")
    else:
        print("❌ 无法获取比赛数据")
    
    # 测试获取选手数据
    players = await client.get_players()
    if players:
        print(f"✅ 成功获取选手数据，共{len(players) if isinstance(players, list) else 1}名选手")
        if isinstance(players, list) and players:
            first_player = players[0]
            print(f"   示例选手: {first_player.get('nickname', 'N/A')} ({first_player.get('team', {}).get('name', 'N/A')})")
    else:
        print("❌ 无法获取选手数据")
    
    print()

async def test_live_match_status_tool():
    """测试实时比赛状态工具"""
    print("🔴 测试GetLiveMatchStatusTool...")
    tool = GetLiveMatchStatusTool()
    
    # 测试获取所有实时比赛
    result = await tool.execute({
        "match_keywords": "",
        "include_upcoming": True,
        "max_matches": 3
    })
    print(f"所有实时比赛: {result['content'][:300]}...")
    
    # 测试特定战队的比赛
    result = await tool.execute({
        "match_keywords": "Navi",
        "include_upcoming": False,
        "max_matches": 2
    })
    print(f"Navi相关比赛: {result['content'][:200]}...")
    print()

async def test_context_info_tool():
    """测试上下文信息工具"""
    print("🔧 测试GetCS2ContextInfoTool...")
    tool = GetCS2ContextInfoTool()
    
    # 测试选手查询
    result = await tool.execute({
        "context_keywords": "s1mple, ZywOo",
        "query_type": "player",
        "include_recent_matches": False
    })
    print(f"选手查询结果: {result['content'][:200]}...")
    
    # 测试自动查询
    result = await tool.execute({
        "context_keywords": "Navi, G2",
        "query_type": "auto",
        "include_recent_matches": True
    })
    print(f"自动查询结果: {result['content'][:200]}...")
    print()

async def test_live_match_discussion_action():
    """测试实时比赛讨论Action"""
    print("💬 测试LiveMatchDiscussionAction...")
    
    # 这里只能测试Action的基本结构，因为它需要完整的MaiBot环境
    try:
        action_info = LiveMatchDiscussionAction.get_action_info()
        print(f"✅ LiveMatchDiscussionAction 信息: {action_info.name} - {action_info.description}")
        print(f"   触发条件: {action_info.trigger_condition}")
    except Exception as e:
        print(f"❌ LiveMatchDiscussionAction 测试失败: {e}")
    
    print()

async def test_plugin_loading():
    """测试插件组件加载"""
    print("📦 测试插件组件加载...")
    
    # 测试各个工具类的实例化
    tools = [
        ("GetCS2ContextInfoTool", GetCS2ContextInfoTool),
        ("GetLiveMatchStatusTool", GetLiveMatchStatusTool),
        ("GetPlayerInfoTool", GetPlayerInfoTool),
        ("GetTeamInfoTool", GetTeamInfoTool),
        ("GetMatchInfoTool", GetMatchInfoTool),
    ]
    
    actions = [
        ("CS2TopicDetectionAction", CS2TopicDetectionAction),
        ("LiveMatchDiscussionAction", LiveMatchDiscussionAction),
        ("LiveMatchMonitorAction", LiveMatchMonitorAction),
    ]
    
    for name, cls in tools:
        try:
            instance = cls()
            info = cls.get_tool_info()
            print(f"✅ {name}: {info.name} - {info.description}")
        except Exception as e:
            print(f"❌ {name} 加载失败: {e}")
    
    for name, cls in actions:
        try:
            # Actions需要更多参数，这里只测试类定义
            info = cls.get_action_info()
            print(f"✅ {name}: {info.name} - {info.description}")
        except Exception as e:
            print(f"❌ {name} 加载失败: {e}")
    
    print()

async def test_match_event_detection():
    """测试比赛事件检测功能"""
    print("⚡ 测试比赛事件检测...")
    
    # 测试DetectMatchEventsTool
    tool = DetectMatchEventsTool()
    result = await tool.execute({
        "importance_threshold": 2,
        "time_window_minutes": 60
    })
    print(f"事件检测结果: {result['content'][:300]}...")
    
    # 测试事件检测器的基本功能
    client = HLTVAPIClient()
    matches = await client.get_matches()
    
    if matches and isinstance(matches, list):
        print("🎯 测试事件检测器:")
        events = match_event_detector.detect_events(matches)
        print(f"   检测到 {len(events)} 个新事件")
        
        # 显示事件历史
        recent_events = match_event_detector.get_recent_events(60)
        print(f"   最近60分钟内共有 {len(recent_events)} 个事件")
        
        for i, match in enumerate(matches[:2]):
            teams = match.get('teams', [])
            if len(teams) >= 2:
                print(f"   比赛 {i+1}: {teams[0].get('name', 'TBD')} vs {teams[1].get('name', 'TBD')}")
                
                # 模拟比分变化检测
                score1 = teams[0].get('score', 0)
                score2 = teams[1].get('score', 0)
                if score1 > 0 or score2 > 0:
                    print(f"     当前比分: {score1} - {score2}")
                    if abs(score1 - score2) >= 5:
                        print(f"     🔥 检测到比分差距较大事件!")
                
                # 模拟地图信息
                maps = match.get('maps', 'TBD')
                if maps != 'TBD':
                    print(f"     地图: {maps}")
    else:
        print("❌ 无法获取比赛数据进行事件检测测试")
    
    print()

async def test_event_notification_action():
    """测试事件通知Action"""
    print("📢 测试MatchEventNotificationAction...")
    
    try:
        action_info = MatchEventNotificationAction.get_action_info()
        print(f"✅ MatchEventNotificationAction 信息: {action_info.name} - {action_info.description}")
    except Exception as e:
        print(f"❌ MatchEventNotificationAction 测试失败: {e}")
    
    print()

async def main():
    """主测试函数"""
    print("🎮 CS2 HLTV Plugin 完整功能测试开始\n")
    
    await test_hltv_api()
    await test_live_match_status_tool()
    await test_context_info_tool()
    await test_live_match_discussion_action()
    await test_plugin_loading()
    await test_match_event_detection()
    await test_event_notification_action()
    
    print("🎯 所有测试完成！")

if __name__ == "__main__":
    asyncio.run(main())
