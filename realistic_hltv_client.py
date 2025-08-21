#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Honest HLTV client for MaiBot CS2 plugin (v3.0.0)

- Does not attempt to bypass HLTV.org anti-bot protections
- Returns empty datasets with clear user-facing messages
- No simulated or fake data
- Encourages users to use official channels when data is unavailable
"""
from __future__ import annotations

from typing import Any, Dict, List
import logging

logger = logging.getLogger("plugin")


class HonestHLTVPlugin:
    """Honest HLTV client facade.

    Exposes async methods expected by the plugin tools. These methods do not
    scrape HLTV.org. They simply return empty payloads with helpful messages,
    acknowledging HLTV's strict anti-bot policies.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger("plugin")
        self.logger.info("Using HonestHLTVPlugin: will not scrape HLTV.org; returns empty datasets with guidance.")

    async def get_cs2_matches(self) -> Dict[str, Any]:
        """Return an honest response for matches.

        Returns
        -------
        dict with keys:
          - message: str
          - data: list (empty)
          - source: str
        """
        msg = (
            "无法自动获取HLTV比赛数据（反爬虫限制）。"
            "请访问官方网站查看实时信息: https://www.hltv.org/matches"
        )
        return {
            "message": msg,
            "data": [],
            "source": "hltv"
        }

    async def get_team_rankings(self) -> Dict[str, Any]:
        """Return an honest response for team rankings."""
        msg = (
            "无法自动获取HLTV战队排名（反爬虫限制）。"
            "请访问: https://www.hltv.org/ranking/teams"
        )
        return {
            "message": msg,
            "data": [],
            "source": "hltv"
        }

    async def get_match_results(self) -> Dict[str, Any]:
        """Return an honest response for recent match results."""
        msg = (
            "无法自动获取HLTV比赛结果（反爬虫限制）。"
            "请访问: https://www.hltv.org/results"
        )
        return {
            "message": msg,
            "data": [],
            "source": "hltv"
        }
