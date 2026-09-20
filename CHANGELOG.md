# 更新日志

本项目遵循语义化版本。`config_version` 是配置 schema 版本，和发布号分开维护。

## v6.2.0 — 2026-09-20

### 战队查询覆盖扩展

- `hltv_get_team_info` 支持榜外战队：世界排名榜未命中时回退 HLTV 站内搜索页，优先精确匹配，再读取队主页资料。
- 队主页解析名称、地区、世界排名与现役阵容；阵容优先读 JSON-LD `athlete`，回退 `.nickname-container`，占位符（`?`）不进入结果。
- 战队信息展示适配榜外数据：无排名、积分或排名变化时按实际情况省略。

### 抓取通道抗抖动

- 主通道显式识别 Cloudflare 质询页（HTTP 200 但无数据内容的假页面），识别后作废并重试，不再进入解析流程。
- 失败重试强制绕过 Jina 内部缓存（`x-no-cache`），避免命中质询页等坏缓存条目后反复无效重试。

## v6.1.1 — 2026-09-20

### 数据质量与可用性

- Jina Reader 成为优先 HTML 抓取通道，用于稳定读取 HLTV 页面。
- 主通道遇到无效页面时最多重试两次，每次间隔 5 秒；全部失败后才回退 Tavily Extract。
- Tavily Extract 降为备选通道，并支持通过 `base_url` 接入兼容中转。
- 比赛列表按 `match_id` 去重。
- 赛事名读取 `data-event-headline`，开赛时间读取 `data-unix`。
- 比赛列表与实时查询共用 `/matches` HTML 缓存。
- 直播比赛详情并发抓取，减少等待时间。
- veto 按步骤逐行输出；解析失败改为 warning，便于排障。

### 项目维护

- 统一发布元数据、README、交接文档与配置模板。
- 仅保留 `config.toml.example` 作为公开模板。
- 增加项目契约测试，防止发布号、模板和文档再次漂移。

## v6.1.0 — 2026-06-12

- 使用 Tavily Extract 替代 `curl_cffi` 作为 Cloudflare 页面读取方案。
- 完成新版 MaiBot Plugin SDK 适配。

## 历史说明

早期 v1–v5 文档描述过 Vercel HLTV API、`hltv-async-api`、模拟数据和旧 Action 模型。这些链路均已退役，不应作为当前部署依据。
