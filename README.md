# Finance Agent · 金融问数

基于 **NL2SQL** 的金融智能数据查询系统，参考尚硅谷「掌柜问数」架构，面向银行业务场景（存款、贷款、理财、渠道、风控等）定制。

用户用自然语言提问，系统自动完成关键词提取 → 元数据召回 → SQL 生成 → 校验修正 → 执行查询，并通过 Web 界面流式展示处理过程与结果。

## 功能特性

- **自然语言问数**：如「各分行存款余额是多少？」
- **多路知识召回**：字段 / 指标向量检索（Qdrant）+ 字段取值全文检索（Elasticsearch）
- **LangGraph 工作流**：13 步 Agent 流水线，支持并行召回与 SQL 自动修正
- **SQL 安全校验**：执行前通过 MySQL `EXPLAIN` 校验，失败时 LLM 最多修正 3 次
- **流式 Web 界面**：SSE 实时展示处理步骤、SQL 与查询结果表格

## 技术栈

| 组件 | 用途 |
|------|------|
| LangGraph + LangChain | Agent 编排与 LLM 调用 |
| FastAPI | REST / SSE API + 静态前端 |
| MySQL (`finance` / `financemeta`) | 业务库 + 元数据知识库 |
| Qdrant | 字段、指标向量索引 |
| Elasticsearch | 维表字段取值全文索引 |
| TEI (`BAAI/bge-large-zh-v1.5`) | 中文 Embedding |
| DeepSeek | SQL 生成与修正 |

## 系统架构

```
用户问题 (NL)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  阶段 1 · 理解      extract_keywords (LLM 提取关键词)    │
├─────────────────────────────────────────────────────────┤
│  阶段 2 · 召回      recall_column   → Qdrant 字段向量    │
│                     recall_metric   → Qdrant 指标向量    │
│                     recall_value    → ES 取值全文        │
│                     merge_retrieved_info → 合并元数据    │
├─────────────────────────────────────────────────────────┤
│  阶段 3 · 精炼      filter_table / filter_metric (LLM)  │
│                     add_extra_context / build_context   │
├─────────────────────────────────────────────────────────┤
│  阶段 4 · SQL       generate_sql → validate_sql (EXPLAIN)│
│                     └─失败→ correct_sql (最多3次)        │
│                     execute_sql → 返回结果               │
└─────────────────────────────────────────────────────────┘
```

## 环境要求

- Python **3.12+**
- [uv](https://github.com/astral-sh/uv) 包管理器
- 可访问的 MySQL 8、Qdrant、Elasticsearch、TEI Embedding 服务
- DeepSeek API Key

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/dinghaojie0515/finance-agent.git
cd finance-agent
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置服务连接

```bash
cp conf/app_config.yaml.example conf/app_config.yaml
```

编辑 `conf/app_config.yaml`，填写数据库、Qdrant、ES、Embedding、DeepSeek 等连接信息。

> **注意**：`conf/app_config.yaml` 已加入 `.gitignore`，请勿将含密钥的配置提交到 Git。

### 4. 初始化元数据库

导入业务库 DDL（`sql/finance.sql`）后，初始化元数据库：

```bash
uv run python init_meta_db.py
```

### 5. 构建元数据知识库

将 `conf/meta_config.yaml` 中的表、字段、指标写入 MySQL / Qdrant / ES：

```bash
uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
```

构建完成后可校验 ES 索引：

```bash
uv run python -m app.scripts.verify_es_values -c conf/meta_config.yaml
```

### 6. 启动服务

```bash
uv run fastapi dev app/main.py
```

浏览器访问：**http://127.0.0.1:8000/**

## API 说明

### `POST /api/v1/query`

流式查询（SSE）。

**请求：**

```json
{ "query": "各分行存款余额是多少？" }
```

**SSE 事件类型：**

| type | 说明 |
|------|------|
| `step` | 节点完成及摘要，如召回数量 |
| `sql` | 生成的 SQL |
| `result` | 查询结果（JSON 数组） |
| `message` | 辅助消息 |
| `done` | 流程结束 |

### `GET /health`

健康检查。

### `GET /docs`

Swagger API 文档。

## 项目结构

```
finance-agent/
├── conf/
│   ├── app_config.yaml.example   # 配置模板（复制为 app_config.yaml）
│   └── meta_config.yaml          # 表/字段/指标元数据定义
├── sql/
│   ├── finance.sql               # 金融业务库 DDL
│   └── financemeta.sql           # 元数据库 DDL
├── prompts/                      # LLM Prompt 模板
├── static/
│   └── index.html                # Web 问数界面
├── app/
│   ├── main.py                   # FastAPI 入口
│   ├── agent/                    # LangGraph 状态机
│   ├── api/                      # 路由与依赖注入
│   ├── clients/                  # 外部服务客户端
│   ├── repositories/             # 数据访问层
│   ├── services/                 # 元数据知识库构建
│   └── scripts/                  # 离线脚本
├── init_meta_db.py
├── pyproject.toml
└── uv.lock
```

## 示例问题

- 各分行存款余额是多少？
- 本月新增个人账户数有多少？
- 北京地区 active 状态的机构有哪些？
- 各渠道交易金额汇总
- 理财赎回金额按产品统计

## 常见问题

**Q: 构建知识库时 Qdrant / TEI 超时？**  
A: 远程服务不稳定时可换网络，或调大 `qdrant_client_manager` / `embedding_client_manager` 中的 timeout；Embedding 已内置重试。

**Q: 查询只显示 SQL 没有结果？**  
A: 确认服务已更新到最新版（SSE 结果序列化已支持 Decimal 类型）；结果表格在页面下方 SQL 面板右侧。

**Q: 401 Authentication Fails？**  
A: 检查 `conf/app_config.yaml` 中 `llm.api_key` 是否为有效的 DeepSeek Key。

## 许可证

MIT License（见 [LICENSE](LICENSE)）

## 致谢

- 尚硅谷「掌柜问数」课程架构参考
- [data_agent](https://github.com) 参考实现
