# CS2/CSGO HLTV Plugin for MaiBot

> 🛠️ **CS2/CSGO电竞数据工具插件** - 为MaiBot提供CS2/CSGO相关的上下文数据查询工具

## 🌟 核心特性

### 🔧 纯工具模式
- **数据提供**: 专注于为麦麦提供CS2/CSGO相关的上下文数据
- **无主动回复**: 不会主动发送消息或邀请语句
- **上下文支持**: 仅作为工具为麦麦的回复提供数据支持

### 📊 全面数据查询
- **选手信息**: 详细的选手统计数据（Rating、ADR、KAST、KPR等）
- **战队资料**: 战队排名、成员构成、历史表现
- **比赛数据**: 实时比赛状态、赛程安排、历史战绩

### 🔴 实时比赛监控
- **Live状态**: 获取进行中比赛的实时信息
- **即时更新**: 比分变化、地图进度、关键时刻
- **事件检测**: 识别重要比赛事件和时刻的最新信息
- **智能讨论参与**: 根据讨论类型提供相应的数据和分析
- **比赛事件检测**: 识别比分变化、比赛开始/结束等重要时刻
- **事件通知系统**: 重要比赛事件发生时主动通知

### 🧠 智能上下文分析
- **自动信息提取**: 从聊天内容中智能识别相关信息需求
- **多类型查询**: 支持选手、战队、比赛等多种查询类型
- **缓存优化**: 智能缓存机制，提升响应速度和用户体验

## 🛠️ 技术架构

### 📡 API 集成
- **数据源**: HLTV 非官方 API (https://hltv-api.vercel.app/)
- **端点支持**: 选手、战队、比赛、结果等多种数据类型
- **错误处理**: 完整的超时、重试和异常处理机制
- **异步请求**: 基于 aiohttp 的高性能异步HTTP客户端

### 💾 智能缓存系统
- **多层级缓存**: 选手、战队、比赛数据分别缓存
- **TTL机制**: 可配置的缓存过期时间
- **内存优化**: 自动清理过期缓存，避免内存泄漏

### ⚡ 事件检测引擎
- **实时监控**: 持续监控比赛状态变化
- **事件分类**: 比分变化、比赛开始/结束、重要时刻识别
- **重要性评分**: 1-5级事件重要性自动评估
- **历史记录**: 保留最近100个事件的历史记录

### 🔧 插件组件架构
- **10个核心组件**: 5个工具 + 4个动作 + 1个插件主体
- **模块化设计**: 各功能模块独立，易于维护和扩展
- **配置驱动**: 丰富的配置选项，支持功能开关和参数调整

## 📋 插件组件详解

### 🔧 核心工具 (Tools)
1. **GetCS2ContextInfoTool** - 智能上下文信息提取
   - 自动从聊天内容提取CS2相关关键词
   - 提供选手、战队、比赛信息作为回复参考
   - 支持多种查询类型和智能匹配

2. **GetLiveMatchStatusTool** - 实时比赛状态查询
   - 获取进行中和即将开始的比赛信息
   - 支持关键词过滤和时间窗口设置
   - 提供详细的比赛状态和时间信息

3. **DetectMatchEventsTool** - 比赛事件检测
   - 识别比分变化、比赛开始/结束等重要事件
   - 事件重要性自动评分（1-5级）
   - 支持时间窗口和重要性阈值过滤

4. **GetPlayerInfoTool** - 选手信息查询
   - 详细的选手统计数据（Rating、ADR、KAST等）
   - 支持模糊匹配和多选手查询
   - 可选择是否包含详细统计信息

5. **GetTeamInfoTool** - 战队信息查询
   - 战队成员构成和基本信息
   - 近期表现和历史战绩
   - 支持战队名称模糊匹配

### 🎮 内部检测动作 (Actions)
1. **LiveMatchDiscussionAction** - 比赛讨论检测
   - 检测群聊中的比赛讨论（仅记录，不回复）
   - 为麦麦提供讨论上下文信息
   - 识别讨论意图和相关战队

2. **MatchEventNotificationAction** - 比赛事件检测
   - 检测重要比赛事件（仅记录，不通知）
   - 为麦麦提供事件上下文数据
   - 支持事件重要性评估

3. **CS2TopicDetectionAction** - CS2话题检测
   - 识别CS2/CSGO相关话题（仅记录，不回复）
   - 为麦麦提供话题上下文信息
   - 支持多种话题类型识别

4. **LiveMatchMonitorAction** - 比赛监控状态记录
   - 记录比赛关注请求（仅记录，不监控）
   - 为麦麦提供监控上下文信息

## ⚙️ 配置选项

### API 配置
```toml
[api]
base_url = "https://hltv-api.vercel.app/api"
request_timeout = 10
retry_attempts = 3
```

### 缓存配置
```toml
[cache]
player_cache_duration = 600  # 选手数据缓存10分钟
team_cache_duration = 600    # 战队数据缓存10分钟
match_cache_duration = 60    # 比赛数据缓存1分钟
```

### 工具配置
```toml
[tools]
max_results_per_query = 5          # 每次查询最大结果数
enable_detailed_stats = true       # 启用详细统计数据
enable_event_detection = true      # 启用事件检测功能
```

## 🚀 使用示例

### 工具数据输出格式

#### 选手信息工具输出
```
选手: ZywOo (Mathieu Herbaut) | 战队: Vitality | 国家: France | 年龄: 21
统计: Rating 1.33 | Impact 1.45 | DPR 0.65 | ADR 85.2 | KAST 76.8% | KPR 0.84
```

#### 战队信息工具输出
```
战队: Vitality | 排名: #1 | 国家: France
队员: ZywOo (France), apEX (France), dupreeh (Denmark), Magisk (Denmark), Spinx (Israel)
```

#### 实时比赛状态工具输出
```
进行中: Navi vs G2 | IEM Katowice 2024 | 08-20 14:30 | 比分: 12-8 | bo3
即将开始: Vitality vs FaZe | IEM Cologne 2024 | 08-20 20:00 | bo3
```

#### 比赛事件检测工具输出
```
[14:32] Navi vs G2 比分更新 | 重要性: 4/5 | 比分: 11-8 → 12-8
[14:28] 关键回合胜利 | 重要性: 3/5 | 比分: 10-8 → 11-8
```

#### 上下文信息工具输出
```
选手: s1mple (Oleksandr Kostyliev) | 战队: Navi | 国家: Ukraine | 年龄: 25
战队: Navi | 排名: #3 | 国家: Ukraine
进行中: Navi vs G2 | IEM Katowice 2024 | 08-20 14:30 | 比分: 12-8
```

## 📦 安装与部署

### 系统要求
- **MaiBot版本**: >= 0.10.0
- **Python版本**: >= 3.8
- **依赖包**: aiohttp
- **运行模式**: 纯工具模式（无主动消息）

### 安装步骤
1. **下载插件**
   ```bash
   git clone https://github.com/CharTyr/Maibot_hltv_plugin.git
   cd Maibot_hltv_plugin
   ```

2. **安装依赖**
   ```bash
   pip install aiohttp
   ```

3. **部署插件**
   ```bash
   cp -r cs2_hltv_plugin /path/to/MaiBot/plugins/
   ```

4. **重启MaiBot**
   ```bash
   # 重启MaiBot服务
   systemctl restart maibot  # 或其他重启方式
   ```

5. **验证安装**
   - 查看MaiBot日志确认插件加载成功
   - 工具将在后台为麦麦提供数据支持

### 配置文件
插件会自动创建配置文件 `config.toml`，可根据需要调整参数：
- API请求超时时间
- 缓存策略设置
- 工具功能开关

## 🔧 开发与测试

### 测试脚本
插件包含完整的测试脚本 `test_plugin.py`：
```bash
cd /path/to/MaiBot/plugins/cs2_hltv_plugin
python test_plugin.py
```

### 测试覆盖
- ✅ HLTV API连接测试
- ✅ 所有工具组件功能测试
- ✅ 所有检测组件加载测试
- ✅ 实时比赛状态测试
- ✅ 事件检测系统测试
- ✅ 缓存机制验证
- ✅ 纯工具模式验证

### 性能指标
- **API响应时间**: < 2秒
- **缓存命中率**: > 80%
- **内存使用**: < 30MB（纯工具模式）
- **并发支持**: 多群聊同时使用

## ⚙️ 配置说明

### 基本配置
```toml
[plugin]
name = "cs2_hltv_plugin"
version = "1.0.0"
enabled = true
```

### API 配置
```toml
[api]
base_url = "https://hltv-api.vercel.app/api"
request_timeout = 10
retry_attempts = 3
```

### 缓存配置
```toml
[cache]
player_cache_duration = 600    # 选手数据缓存10分钟
team_cache_duration = 600      # 战队数据缓存10分钟
match_cache_duration = 60      # 比赛数据缓存1分钟
```

### 响应配置
```toml
[responses]
enable_general_response = true      # 启用通用CS2话题响应
enable_auto_monitoring = false      # 启用自动比赛监控
max_results_per_query = 5          # 每次查询最大结果数
```

## 📦 依赖要求

### Python 依赖
- `aiohttp` - 异步HTTP客户端

### MaiBot 版本要求
- 最低版本: 0.10.0

## 🔧 安装指南

1. 将插件文件夹复制到 MaiBot 的 `plugins/` 目录下
2. 确保安装了 `aiohttp` 依赖：
   ```bash
   pip install aiohttp
   ```
3. 重启 MaiBot
4. 在配置文件中启用插件

## 🐛 故障排除

### 常见问题

**Q: 插件无法获取数据**
A: 检查网络连接和 HLTV API 可用性，查看日志中的错误信息

**Q: 响应速度慢**
A: 调整缓存配置，增加缓存时长减少API调用频率

**Q: 选手/战队搜索不到**
A: 尝试使用完整的英文名称或常用昵称

### 日志查看
插件使用标准的 Python logging 模块，日志级别包括：
- INFO: API请求成功信息
- WARNING: API请求失败警告
- ERROR: 请求超时或异常错误

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 来改进这个插件！

### 开发环境设置
1. Fork 项目仓库
2. 创建功能分支
3. 进行开发和测试
4. 提交 Pull Request

## 📄 许可证

本插件使用 GPL-v3.0-or-later 许可证。

## 🙏 致谢

- HLTV.org 提供的数据源
- hltv-api 项目提供的 API 接口
- MaiBot 开发团队的插件系统支持
