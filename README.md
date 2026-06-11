# CS2/CSGO HLTV Plugin for MaiBot

> 🎮 **CS2/CSGO电竞数据工具插件** - 开箱即用，支持可选实时数据源

## v5.1.0 特性

- ✅ **开箱即用** - 无需额外服务，插件直接集成爬虫
- ✅ **绕过 Cloudflare** - 使用 `curl_cffi` 模拟真实浏览器
- ✅ **丰富数据** - 比赛、排名、Scoreboard、选手统计
- ✅ **智能缓存** - 自动缓存数据，减少请求
- ✅ **可选实时数据** - 支持 Playwright、BO3.gg、PandaScore 三种实时数据源

## 安装

### 1. 安装基础依赖

```bash
pip install curl_cffi beautifulsoup4 lxml
```

### 2. 安装可选实时数据依赖（按需）

```bash
# BO3.gg (推荐，免费)
pip install cs2api

# PandaScore (需要 API token)
pip install aiohttp

# Playwright (需要安装浏览器)
pip install playwright
playwright install chromium
```

### 3. 复制插件

将 `Maibot_hltv_plugin` 文件夹复制到 MaiBot 的 `plugins/` 目录。

### 4. 配置（可选）

复制 `config_template.toml` 为 `config.toml`，按需修改配置。

### 5. 重启 MaiBot

插件会自动加载。

## 实时数据配置

默认情况下，插件使用 HLTV 静态数据（页面加载时的数据）。如需更准确的实时数据，可以启用以下数据源：

### 方案对比

| 数据源 | 优点 | 缺点 | 推荐场景 |
|--------|------|------|----------|
| **HLTV 静态** | 覆盖所有比赛，无需配置 | 数据可能延迟 | 默认使用 |
| **BO3.gg** | 免费，有选手实时数据 | 覆盖范围有限 | 主流赛事 |
| **PandaScore** | 专业 API，数据准确 | 需要 token，免费版无回合比分 | 商业应用 |
| **Playwright** | 获取真实实时数据 | 资源消耗大，需要浏览器 | 高精度需求 |

### 配置示例

```toml
[live_data]
enabled = true
provider = "bo3gg"  # 或 "pandascore", "playwright"
fallback_to_hltv = true

[live_data.pandascore]
api_token = "your_token_here"
```

## 工具列表

| 工具 | 说明 |
|------|------|
| `GetMatchesTool` | 获取比赛列表（即将开始/进行中） |
| `GetMatchDetailTool` | 获取比赛详情（比分、地图、Veto） |
| `GetMapStatsTool` | 获取地图 Scoreboard（K/D/A、ADR、Rating） |
| `GetMatchResultsTool` | 获取最近比赛结果 |
| `GetTeamRankingsTool` | 获取战队世界排名 |
| `GetTeamInfoTool` | 获取战队详细信息 |
| `GetLiveMatchTool` | 获取正在进行的比赛（支持实时数据） |
| `GetLiveScoreTool` | 获取指定比赛实时比分 |

## 示例输出

### 实时比分
```
🔴 实时比分 [bo3gg]

🎮 Galaxy vs WeWillWin
━━━━━━━━━━━━━━━━━━━━
📊 地图: 0 - 0 (BO3)
🗺️ 当前: Dust2
🎯 回合: 10 - 6
⚖️ 比分持平
━━━━━━━━━━━━━━━━━━━━
🏆 kleverr A Lyga Season 2 Finals
```

### Scoreboard
```
📊 Ancient Scoreboard
🏆 FaZe 5 - 13 Natus Vincere
📅 StarLadder Budapest Major 2025

【FaZe】
选手         K   A   D   ADR  KAST Rating
---------------------------------------------
jcobbb      10   4  11  72.6   61%   0.83
karrigan     8   6  14  60.3   67%   0.80
broky       10   5  13  58.2   72%   0.73
```

## 数据来源

- **HLTV.org** - 主要数据源，覆盖所有比赛
- **BO3.gg** - 可选实时数据源
- **PandaScore** - 可选实时数据源

## 缓存策略

| 数据类型 | 缓存时间 |
|----------|----------|
| 比赛列表 | 2 分钟 |
| 比赛详情 | 1 分钟 |
| 比赛结果 | 10 分钟 |
| 战队排名 | 1 小时 |
| 选手信息 | 1 小时 |

## 文件结构

```
Maibot_hltv_plugin/
├── plugin.py           # 插件主文件（工具定义）
├── hltv_scraper.py     # HLTV 爬虫模块
├── live_providers.py   # 实时数据提供者
├── _manifest.json      # 插件清单
├── config_template.toml
├── config.toml         # 用户配置（需自行创建）
└── README.md
```

## 故障排除

### 依赖未安装
```
❌ HLTV 爬虫依赖未安装。请运行: pip install curl_cffi beautifulsoup4 lxml
```

### 实时数据不可用
- BO3.gg 可能不覆盖小型赛事
- PandaScore 需要有效的 API token
- 启用 `fallback_to_hltv = true` 可回退到 HLTV 数据

### 请求被拦截
插件会自动重试最多 3 次。如果仍然失败，可能是临时限流，稍后再试。

## 许可证

GPL-v3.0-or-later
