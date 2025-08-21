# CS2 HLTV插件更新日志

## v2.0.0 (2024-08-21) - 重大重构版本

### 🔄 架构重构
- **完全基于hltv-async-api**: 移除所有旧API依赖，专门使用hltv-async-api库
- **简化架构**: 从复杂的多API混合架构简化为单一数据源架构
- **移除Socket.IO**: 不再依赖python-socketio和实时连接功能

### ✨ 新增功能
- **智能模拟数据回退**: 当API遇到403错误时自动使用高质量模拟数据
- **优化缓存系统**: 重新设计的多层级TTL缓存机制
- **异步架构**: 完全异步的API调用，提升性能
- **错误处理增强**: 更完善的异常捕获和处理机制

### 🛠️ 工具组件更新
- **GetCurrentMatchContextTool**: 重写比赛上下文获取逻辑
- **GetLiveMatchStatusTool**: 优化实时比赛状态查询
- **GetTeamInfoTool**: 增强战队信息展示
- **GetMatchResultsTool**: 新增比赛结果查询工具

### 🗑️ 移除功能
- 移除基于hltv-api.vercel.app的REST API集成
- 移除Socket.IO实时数据收集器
- 移除复杂的API回退链
- 移除过时的配置选项

### 📋 配置变更
- 简化配置文件结构
- 移除API URL配置项
- 新增模拟数据相关配置
- 优化缓存时间设置

### 🐛 问题修复
- 修复BaseTool导入错误
- 解决API连接超时问题
- 修复缓存失效机制
- 改进错误日志记录

### 📈 性能优化
- 减少API调用频率
- 优化内存使用
- 提升响应速度
- 降低CPU占用

---

## v1.x 历史版本

### v1.2.0 (之前版本)
- 基于多API混合架构
- 支持Socket.IO实时连接
- 复杂的API回退机制
- 包含被动式数据收集器

### v1.1.0 (之前版本)
- 初始版本功能
- 基础工具组件
- REST API集成
- 简单缓存机制

---

## 升级指南

### 从v1.x升级到v2.0.0

#### 必需步骤
1. **安装新依赖**:
   ```bash
   pip install hltv-async-api
   ```

2. **更新配置文件**:
   - 使用新的config_template.toml
   - 移除旧的API URL配置
   - 调整缓存设置

3. **代码兼容性**:
   - 工具接口保持兼容
   - Action组件简化
   - 移除Socket.IO相关代码

#### 配置迁移
```toml
# 旧配置 (v1.x)
[cs2_hltv_plugin]
api_base_url = "https://hltv-api.vercel.app/api"
enable_socketio = true
socketio_url = "wss://scorebot-secure.hltv.org"

# 新配置 (v2.0.0)
[cs2_hltv_plugin]
enable_mock_data_fallback = true
cache_duration_matches = 60
```

#### 功能变更
- **实时数据**: 从Socket.IO改为模拟数据
- **API调用**: 从REST API改为异步抓取
- **错误处理**: 更智能的回退机制

### 兼容性说明
- MaiBot接口完全兼容
- 工具调用方式不变
- 响应格式保持一致
- 用户体验无感知升级

---

## 已知问题

### v2.0.0
- hltv-async-api经常遇到403错误（已通过模拟数据解决）
- 部分API方法参数文档不准确
- HLTV.org反爬虫保护较严格

### 解决方案
- 启用模拟数据回退（默认开启）
- 使用缓存减少API调用
- 监控API状态并及时调整

---

## 贡献指南

### 报告问题
- 使用GitHub Issues报告bug
- 提供详细的错误日志
- 说明复现步骤

### 功能建议
- 通过GitHub Issues提交建议
- 说明使用场景和需求
- 考虑向后兼容性

### 代码贡献
- Fork项目并创建分支
- 遵循现有代码风格
- 添加必要的测试
- 提交Pull Request

---

## 技术债务

### 当前技术债务
- 模拟数据需要定期更新以保持真实感
- 缓存策略可以进一步优化
- 错误处理可以更细粒度

### 计划改进
- 集成多个数据源提高可靠性
- 实现智能代理轮换
- 添加数据验证机制
- 优化内存使用模式
