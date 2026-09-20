# 更新日志

本项目遵循语义化版本。`config_version` 是配置 schema 版本，和发布号分开维护。

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
