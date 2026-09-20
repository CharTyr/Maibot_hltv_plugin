# HLTV 插件维护交接

**当前发布：v6.2.0**

仓库：<https://github.com/CharTyr/Maibot_hltv_plugin>

插件 ID：`chartyr.hltv-plugin`

运行形态：纯 Planner 工具插件；不主动发送群消息。

## 当前链路

```text
Planner tool call
  → hltv_scraper
  → Jina Reader（主通道，HTML；质询页识别 + 重试绕过缓存）
  → Tavily Extract（备选 HTML）
  → HLTV 页面解析与 TTL 缓存
  → 结构化工具结果
```

可选实时比分源由 `[live_data]` 控制。没有实时源数据时，按配置回退到 HLTV 静态页面。

## 文件职责

- `plugin.py`：SDK2 插件入口、配置模型、8 个 Planner 工具。
- `hltv_scraper.py`：HLTV 页面请求、解析和缓存。
- `live_providers.py`：BO3.gg、PandaScore 可选实时源。
- `config.toml.example`：唯一公开配置模板。
- `tests/test_project_contract.py`：发布号、配置 schema、模板和文档的一致性门。

## 配置与版本

- `PLUGIN_VERSION` 与 `_manifest.json` 是发布号，当前为 `6.2.0`。
- `CONFIG_SCHEMA_VERSION` 与 `config.toml.example` 的 `config_version` 是配置 schema，当前为 `6.1.0`。
- 运行时 `config.toml` 不进 Git。改 schema 前必须备份运行时配置，并确认 runner 的版本迁移行为不会重建用户配置。

## 发布步骤

1. 运行 `python3 -m unittest discover -s tests`、manifest JSON 校验和 Python 编译。
2. 在真实 MaiBot venv 加载插件，确认日志出现正确发布号，并用非敏感查询验收工具结果。
3. 检查 `git status` 为干净或仅包含本次发布文件。
4. 提交、推送 `main`，创建签名说明清楚的 Git tag 与 GitHub Release。
5. 回读远端 SHA、tag 和 Release；成功的 `git push` 不是验收。

## 常见坑

- 不要复活 `hltv-api.vercel.app`、`hltv-async-api` 或旧 Action 逻辑。
- 不要把 `.bak` 文件、token、`config.toml` 或抓取缓存提交进仓库。
- 解析成功不等于数据正确：比赛列表必须去重，赛事名和时间必须来自页面的真实属性。
- 榜外战队查询依赖站内搜索链（搜索页 → 队主页）；榜外结果没有积分或排名变化属正常，不要回填默认值。
- 线上插件只改 `plugins/hltv_plugin/`；不要为插件问题改 MaiBot `src/`。
