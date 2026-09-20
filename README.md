# MaiBot HLTV 插件

> 面向 MaiBot 的 CS2 / CS:GO 赛事资料工具。只在 Planner 明确调用时查询，不主动向群聊推送消息。

**当前发布：v6.2.0**

它提供比赛列表、赛程详情、地图数据、赛果、世界排名、战队资料和实时比分查询。主数据来自 HLTV 页面；抓取链路优先使用 **Jina Reader** 读取页面 HTML（自动识别 Cloudflare 质询页并重试，重试绕过 Jina 缓存），遇到不可用时回退 **Tavily Extract**。

## 安装

在 MaiBot 仓库根目录执行：

```bash
git clone https://github.com/CharTyr/Maibot_hltv_plugin.git plugins/hltv_plugin
.venv/bin/pip install -r plugins/hltv_plugin/requirements.txt
if [ ! -e plugins/hltv_plugin/config.toml ]; then
  cp plugins/hltv_plugin/config.toml.example plugins/hltv_plugin/config.toml
fi
```

这段只会在首次安装时生成配置。升级已有部署时，**不要复制模板覆盖** `config.toml`；保留现有凭据和用户设置，只按发布说明手工补新增字段。

按需要编辑 `plugins/hltv_plugin/config.toml`，再重启 MaiBot，或等待运行环境的插件热重载完成。

`config.toml` 含可能的 Tavily / PandaScore 凭据，已被 Git 忽略，**不要提交**。

## 配置

`config.toml.example` 是唯一维护的模板。

- `[plugin]`：启用状态和配置 schema 版本。
- `[cache]`：比赛、赛果、排名等页面缓存时间。
- `[display]`：各类查询的默认展示数量。
- `[jina]`：Jina Reader 主抓取通道；默认开启，不需要 key。
- `[tavily]`：Jina 不可用时的 Extract 备选通道；可填写 API key，`base_url` 可改为兼容中转。
- `[live_data]`：可选实时比分源；默认关闭。

启用 `[live_data]` 时按 provider 额外安装：`bo3gg` 需要 `cs2api`，`pandascore` 需要 `aiohttp` 和有效的 PandaScore token。

配置里的 `config_version = "6.1.0"` 是**配置 schema 版本**，不是插件发布版本。除非模板字段发生迁移，不要为了跟发布号好看而改它。

## Planner 工具

| 工具 | 用途 |
| --- | --- |
| `hltv_get_matches` | 查询正在进行、即将开始的比赛 |
| `hltv_get_match_detail` | 查询比赛详情、比分、地图和 veto |
| `hltv_get_map_stats` | 查询单张地图的选手统计 |
| `hltv_get_results` | 查询近期赛果 |
| `hltv_get_rankings` | 查询 HLTV 战队排名 |
| `hltv_get_team_info` | 查询战队资料、成员与排名（支持榜外战队，自动站内搜索） |
| `hltv_get_live_matches` | 查询进行中的比赛 |
| `hltv_get_live_score` | 查询指定比赛的实时比分 |

## 数据与缓存

- **HLTV**：比赛、赛果、排名、战队和选手资料的原始来源。
- **Jina Reader**：默认 HTML 抓取通道，用于绕开 HLTV 的 Cloudflare 页面。
- **Tavily Extract**：Jina Reader 不可用时的备选 HTML 抓取通道。
- **实时源**：可选 BO3.gg 或 PandaScore；没有数据时可回退 HLTV 静态页面。

缓存时间见 `config.toml.example`。比赛列表和详情默认较短，排名与结果默认较长；不要把实时比分轮询间隔调得过低。

## 开发与验证

项目只依赖运行时的 MaiBot SDK；项目契约测试不需要联网：

```bash
python3 -m unittest discover -s tests
python3 -m json.tool _manifest.json >/dev/null
python3 -m compileall -q plugin.py hltv_scraper.py live_providers.py
```

发布前还应在实际 MaiBot venv 里加载插件，并用非敏感查询验证抓取链：比赛列表（Jina → Tavily 回退）与榜外战队（站内搜索兜底）。不要用“HTTP 200”代替工具结果验收。

## 维护约定

- 发布号只维护在 `PLUGIN_VERSION`、`_manifest.json`、README、CHANGELOG 与 HANDOVER。
- `config_version` 仅表示配置 schema，保持与 `config.toml.example` 一致。
- `*.bak` / `*.bak.*` 只允许放在仓库外的运维备份目录，不能留在工作树。
- 每个发布必须有 Git tag 和 GitHub Release。

## License

GPL-3.0-or-later。
