## 1. 接口总览

当前后端注册了以下路由模块（均挂在 /api 前缀下）：

| 模块 | 路由文件 | 主要端点 |
|------|----------|----------|
| 认证 | auth.py | POST /auth/login, GET /auth/me, PATCH /auth/password |
| 健康检查 | health.py | GET /health |
| 领域 | domains.py | GET /domains |
| 情报条目 | info_items.py | GET /info-items, GET /info-items/alerts, 草稿/发布/预警 |
| Intake | intake.py | GET /intake/status |
| 参数观测 | parameter_observations.py | GET /parameter-observations |
| 仪表盘 | dashboards.py | GET /dashboards, GET /dashboards/{id}/content |
| 行业图景 | industry_map.py | GET /industry-map |
| 交付情报 | delivery_intel.py | GET /delivery-intel, GET /delivery-intel/meta |
| 问答状态与图谱 | assistant.py | GET /assistant/status, GET /assistant/graph, POST /assistant/query（兼容） |
| 门户流式问答 | assistant_stream.py | GET/POST /assistant/stream, GET /assistant/models |
| 对话管理 | conversations.py | GET/POST/DELETE /conversations, GET /conversations/{id}/messages |
| 资料上传 | uploads.py | GET/POST /uploads, 分类重试/人工修正/下载 |
| 用户管理 | users.py | GET/POST/PATCH/DELETE /users |

除 GET /health 外，所有接口要求 Bearer Token。

## 2. 基本约定

### 2.1 Base URL

本地通过 Docker 运行时：

```text
http://localhost:8000/api
```

前端实际通过 Nginx 代理访问：

```text
http://localhost:8080/api
```

### 2.2 认证方式

除 `GET /api/health` 与 `POST /api/auth/login` 外，其余接口均需要：

```http
Authorization: Bearer <access_token>
```

### 2.3 数据格式

- 请求体：`application/json`
- 响应体：JSON
- 删除或改密成功时，部分接口返回 `204 No Content`

### 2.4 常见状态码

| 状态码 | 含义 |
|---|---|
| `200` | 请求成功 |
| `201` | 创建成功 |
| `204` | 成功且无返回体 |
| `400` | 参数错误或业务校验失败 |
| `401` | 未认证、token 无效或已过期 |
| `403` | 无权限执行该操作 |
| `404` | 资源不存在 |
| `429` | 登录失败次数过多 |
| `500` | 服务端异常 |

## 3. 认证接口

## 3.1 登录

### `POST /api/auth/login`

说明：

- 使用用户名密码登录
- 成功后返回访问令牌
- 同一 IP 5 分钟内连续失败 5 次后会被限流

请求示例：

```json
{
  "username": "admin",
  "password": "your_password"
}
```

成功响应：

```json
{
  "access_token": "<token>",
  "token_type": "bearer"
}
```

失败响应示例：

```json
{
  "detail": "用户名或密码错误"
}
```

限流响应示例：

```json
{
  "detail": "登录失败次数过多，请 5 分钟后再试"
}
```

## 3.2 获取当前用户

### `GET /api/auth/me`

说明：

- 用于验证当前 token 是否有效
- 返回当前登录用户名

成功响应：

```json
{
  "username": "admin"
}
```

## 3.3 修改密码

### `PATCH /api/auth/password`

请求示例：

```json
{
  "current_password": "your_password",
  "new_password": "NewPass999"
}
```

成功响应：

- `204 No Content`

失败响应示例：

```json
{
  "detail": "当前密码错误"
}
```

```json
{
  "detail": "新密码不能少于6位"
}
```

说明：

- 修改密码后，旧 token 会失效
- 后端会在后续请求中返回 `401`，提示重新登录

## 4. 健康检查接口

## 4.1 服务健康

### `GET /api/health`

说明：

- 不需要认证
- 常用于部署后探活

成功响应：

```json
{
  "status": "ok"
}
```

## 5. 领域接口

## 5.1 获取领域树

### `GET /api/domains/tree`

说明：

- 需要认证
- 返回树形领域结构
- 当前树结构来自 `data/domains.json`

响应示例：

```json
[
  {
    "id": "DOM_CCUS_L1",
    "name": "CCUS",
    "level": 1,
    "parent_id": null,
    "sort_order": 10,
    "is_active": true,
    "children": [
      {
        "id": "DOM_CCUS_L2_CAPTURE",
        "name": "捕集或分离",
        "level": 2,
        "parent_id": "DOM_CCUS_L1",
        "children": []
      }
    ]
  }
]
```

## 6. 情报对象结构

大多数情报相关接口都返回统一结构 `InfoItemOut`。

### 6.1 返回字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `uuid` | 记录 ID |
| `title` | `string` | 标题 |
| `content` | `string` | 正文 |
| `source_url` | `string/null` | 来源链接 |
| `published_at` | `datetime/null` | 发布时间 |
| `created_at` | `datetime` | 创建时间 |
| `updated_at` | `datetime` | 更新时间 |
| `status` | `string` | `draft` / `ai_suggested` / `published` |
| `importance_score` | `int` | 重要度 |
| `is_new_tech` | `bool` | 是否新技术 |
| `comment` | `string/null` | 评论/备注 |
| `source_types` | `string[]` | 来源类型 |
| `info_types` | `string[]` | 信息类型 |
| `tags` | `string[]` | 标签 |
| `domain_ids` | `string[]` | 领域 ID 列表 |
| `classification` | `string/null` | 密级 |
| `draft_data` | `object` | 扩展数据 |
| `alert_status` | `string/null` | 预警状态 |
| `alert_source` | `string/null` | 预警来源 |
| `alert_manual_override` | `bool` | 是否人工覆盖 |
| `alert_title` | `string/null` | 预警标题 |
| `alert_body` | `string/null` | 预警内容 |
| `alert_reviewer_comment` | `string/null` | 复核意见 |
| `alert_dismiss_reason` | `string/null` | 解除原因 |
| `alert_color` | `string/null` | 预警颜色 |
| `alert_expires_at` | `datetime/null` | 预警到期时间 |
| `last_modified_by` | `string/null` | 最后修改人 |
| `created_by` | `string/null` | 创建人 |

### 6.2 `draft_data` 常见结构

```json
{
  "indicators": [
    {
      "indicator_id": "IND_CCUS_CAPTURE_15",
      "name": "捕集率 (%)",
      "value": "92",
      "unit": "%",
      "keep": true
    }
  ],
  "duration": "month",
  "custom_expires_on": "2026-04-15",
  "manual_alert": true
}
```

## 7. 情报查询接口

## 7.1 查询情报列表

### `GET /api/info-items`

查询参数：

| 参数 | 必填 | 说明 |
|---|---|---|
| `status` | 否 | 逗号分隔的状态列表，默认 `published` |

示例：

```text
GET /api/info-items?status=published
GET /api/info-items?status=draft,ai_suggested
```

成功响应：

```json
[
  {
    "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "title": "示例情报",
    "status": "published",
    "domain_ids": ["DOM_CCUS_L4_CAPTURE_02_02"],
    "draft_data": {
      "indicators": []
    }
  }
]
```

## 7.2 查询草稿列表

### `GET /api/info-items/drafts`

说明：

- 返回 `draft` 与 `ai_suggested` 状态的记录
- 按 `updated_at` 倒序

## 7.3 查询单条情报

### `GET /api/info-items/{item_id}`

路径参数：

| 参数 | 说明 |
|---|---|
| `item_id` | 情报 UUID |

失败响应示例：

```json
{
  "detail": "info item not found"
}
```

## 7.4 查询单条草稿

### `GET /api/info-items/{item_id}/draft`

说明：

- 只有当该记录存在且状态属于草稿类时才返回成功

失败响应示例：

```json
{
  "detail": "draft not found"
}
```

## 8. 草稿接口

## 8.1 创建草稿

### `POST /api/info-items/draft`

请求字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | 是 | 标题，最短 1 个字符 |
| `content` | 是 | 正文，最短 1 个字符 |
| `source_url` | 否 | 来源链接 |
| `published_at` | 否 | 时间 |
| `importance_score` | 是 | 1-5 |
| `is_new_tech` | 否 | 是否新技术 |
| `comment` | 否 | 评论 |
| `source_types` | 否 | 来源类型数组 |
| `info_types` | 否 | 信息类型数组 |
| `tags` | 否 | 标签数组 |
| `domain_ids` | 是 | 至少一个四级领域 ID |
| `classification` | 否 | 密级 |
| `status` | 否 | 仅允许 `draft` 或 `ai_suggested` |
| `draft_data` | 否 | 指标和预警扩展信息 |
| `alert` | 否 | 预警对象 |

请求示例：

```json
{
  "title": "测试草稿",
  "content": "测试正文",
  "source_url": "https://example.com",
  "published_at": "2026-03-07T00:00:00Z",
  "importance_score": 4,
  "is_new_tech": true,
  "comment": "测试备注",
  "source_types": ["产业新闻"],
  "info_types": ["技术"],
  "tags": ["测试"],
  "domain_ids": ["DOM_CCUS_L4_CAPTURE_02_02"],
  "classification": "内部",
  "status": "draft",
  "draft_data": {
    "manual_alert": false,
    "duration": "month",
    "indicators": []
  },
  "alert": null
}
```

校验规则：

- `status` 只能为 `draft` 或 `ai_suggested`
- `domain_ids` 必须存在且全部为四级叶子节点
- 若开启预警，必须补齐预警字段

## 8.2 更新草稿

### `PUT /api/info-items/{item_id}/draft`

说明：

- 请求结构与“创建草稿”相同
- 仅允许更新草稿状态记录

失败响应：

```json
{
  "detail": "draft not found"
}
```

## 9. 发布接口

## 9.1 发布情报

### `POST /api/info-items/publish`

请求字段与草稿大体相同，额外支持：

| 字段 | 说明 |
|---|---|
| `draft_id` | 从已有草稿直接发布时使用 |
| `revision_of` | 发布修订稿时使用，指向原已发布记录 |

请求示例：

```json
{
  "title": "测试发布",
  "content": "捕集率达到 92%，再生能耗 2.3 GJ/tCO2",
  "source_url": "https://example.com",
  "published_at": "2026-03-09T00:00:00Z",
  "importance_score": 5,
  "is_new_tech": true,
  "comment": "待持续跟踪",
  "source_types": ["产业新闻"],
  "info_types": ["技术"],
  "tags": ["捕集率", "能耗"],
  "domain_ids": ["DOM_CCUS_L4_CAPTURE_02_02"],
  "classification": "内部",
  "draft_id": null,
  "revision_of": null,
  "draft_data": {
    "manual_alert": true,
    "duration": "month",
    "indicators": [
      {
        "indicator_id": "",
        "name": "捕集率 (%)",
        "value": "92",
        "unit": "",
        "keep": true
      }
    ]
  },
  "alert": {
    "enabled": true,
    "alert_title": "测试预警",
    "alert_body": "建议关注该技术指标变化",
    "reviewer_comment": "人工确认后发布",
    "alert_color": "orange",
    "expires_at": "2026-06-01T00:00:00Z"
  }
}
```

关键行为：

- 新发布记录的 `status` 会被置为 `published`
- 若带 `draft_id`，后端会把该草稿转为发布态
- 若带 `revision_of`，后端会在成功发布后删除原发布记录
- 若 `draft_data.indicators` 中只传了名称，后端会尝试自动补齐 `indicator_id`

失败场景示例：

```json
{
  "detail": "some domain_ids do not exist"
}
```

```json
{
  "detail": "domain_ids must all be level-4 leaf domains: DOM_CCUS_L3_CAPTURE_02"
}
```

```json
{
  "detail": "expires_at must be in the future"
}
```

```json
{
  "detail": "无权替换该已发布情报：revision_of 关联的记录不属于当前用户"
}
```

## 10. 删除接口

## 10.1 删除情报/草稿

### `DELETE /api/info-items/{item_id}`

说明：

- 草稿和已发布记录都走同一个删除接口
- 成功返回 `204 No Content`

失败响应：

```json
{
  "detail": "info item not found"
}
```

## 11. 指标接口

## 11.1 更新指标

### `PATCH /api/info-items/{item_id}/indicators`

请求结构：

```json
{
  "indicators": [
    {
      "indicator_id": "IND_CCUS_CAPTURE_15",
      "name": "捕集率 (%)",
      "value": "92",
      "unit": "%",
      "keep": true
    }
  ]
}
```

说明：

- 实际会写回到 `draft_data.indicators`
- 后端会再次按领域过滤和归一化

## 12. 详情编辑接口

## 12.1 更新详情字段

### `PATCH /api/info-items/{item_id}/details`

请求字段：

| 字段 | 说明 |
|---|---|
| `source_url` | 来源链接 |
| `source_types` | 来源类型数组 |
| `info_types` | 信息类型数组 |
| `tags` | 标签数组 |
| `comment` | 评论 |
| `classification` | 密级 |

请求示例：

```json
{
  "source_url": "https://example.com/updated",
  "source_types": ["产业新闻", "企业公告"],
  "info_types": ["技术"],
  "tags": ["更新", "演示"],
  "comment": "已补充背景说明",
  "classification": "内部"
}
```

## 13. 预警接口

## 13.1 新增/编辑/解除预警

### `PATCH /api/info-items/{item_id}/alert`

开启预警请求示例：

```json
{
  "enabled": true,
  "alert_title": "重点关注",
  "alert_body": "建议跟踪关键指标、成本与落地节奏",
  "reviewer_comment": "人工编辑",
  "alert_color": "red",
  "expires_at": "2026-06-30T00:00:00Z"
}
```

解除预警请求示例：

```json
{
  "enabled": false,
  "dismiss_reason": "该事项已完成验证，无需继续预警"
}
```

校验规则：

- 当 `enabled = true` 时：
  - `alert_title` 必填
  - `alert_body` 必填
  - `reviewer_comment` 必填
  - `expires_at` 如果传入，则必须晚于当前时间

接口行为：

- 开启预警后：
  - `alert_status = active`
  - `alert_source = manual`
  - `alert_manual_override = true`
- 关闭预警后：
  - `alert_status = dismissed`
  - 清空标题、内容、颜色、到期时间
  - 保留 `alert_dismiss_reason`

## 14. Intake 与信息源占位接口

> 第一阶段仅定义信息进入系统的接口边界，暂不实现完整自动采集、付费数据库接管或 crawler。

## 14.1 Intake 状态

### `GET /api/intake/status`

说明：

- 需要认证
- 返回三类信息进入系统的能力边界：从服务器获取信息、自动化扒取信息、直接上传信息
- 用于核心门户展示当前 intake 能力状态

响应字段：

| 字段 | 说明 |
|---|---|
| `status` | 当前占位接口状态 |
| `message` | 阶段说明 |
| `channels` | 信息进入渠道列表 |
| `non_goals` | 第一阶段不做的采集能力 |

## 14.2 Intake Schema

### `GET /api/intake/schema`

说明：

- 需要认证
- 返回未来统一 intake item 的字段边界
- 用于后续对接人工上传、同事整理材料、服务器文件、crawler、付费数据库摘录等来源

当前 schema 包括：

- 必填字段：`channel`、`title`、`source_type`、`submitted_by`、`submitted_at`、`confidentiality`、`review_status`
- 可选字段：`source_url`、`source_path`、`original_text`、`summary`、`technology_node_candidates`、`industry_node_candidates`、`parameter_candidates`、`attachments` 等

## 14.3 信息源总览

### `GET /api/sources`

说明：

- 需要认证
- 返回当前可用的信息进入路径和未来信息源类型
- 当前可用路径主要是 `upload_review.html` 与 `excel_import.html`

## 15. 对话门户与仪表盘接口

0801 门户问答由三部分组成：门户后端负责认证和用户会话，`TECHDB_QA_SERVICE_URL` 指向的 canonical QA 服务负责既有 bge-m3 + 向量 + BM25 检索，公司 OpenAI-compatible 网关负责回答生成。当前门户不使用旧 Markdown、sources、parameters 或 Chatbot 包做检索回退。

### `GET /api/assistant/status`

说明：

- 需要认证
- 客户端打开门户时调用，用于确认 canonical QA 服务配置与索引就绪状态
- 未配置时仍返回 200，并以 `status=unconfigured` 明确说明；不会切换到旧知识源

响应字段：

| 字段 | 说明 |
|---|---|
| `status` | `unconfigured` / `error` / `assets_missing` / `ok` |
| `configured` | 是否配置了 `TECHDB_QA_SERVICE_URL` |
| `ready` | 向量、BM25 和记录下标映射校验是否同时就绪 |
| `provider` | 固定为 `sbq9712/tech-db canonical hybrid retrieval` |
| `required_assets` | 服务运行所需的模型、索引和记录资产 |
| `message` | 面向用户的状态说明 |
| `stats` | 就绪或已连接时的记录、索引、映射和图谱统计 |

### `GET /api/assistant/models`

返回门户模型选择器可用的 `default_model` 与 `models`。模型列表由 `TECHDB_AGENT_MODEL` 和 `TECHDB_AGENT_ALLOWED_MODELS` 控制。

### `GET /api/assistant/graph?limit=200`

代理 canonical QA 的 `/api/graph`，返回 `nodes` 和 `edges`。`limit` 范围 1-500；服务未配置、不可达或契约不兼容时返回 503。

### `POST /api/assistant/stream`

当前门户的正式问答入口。请求示例：

```json
{
  "query": "固态电池最新研究进展有哪些？",
  "session_id": null,
  "model": "GLM-5.2",
  "regenerate": false,
  "retry": false
}
```

- `session_id` 为空时，首次发送才创建当前用户的新会话，并在响应头 `X-Conversation-Id` 返回会话 ID。
- `regenerate=true` 只重新生成当前会话最后一条成功回答；成功后替换该回答，旧 agent run 审计记录保留。
- `retry=true` 只重试最后一条已持久化但失败的问题，不重复写入用户消息。
- `model` 必须位于允许列表，非法值返回 400。

响应为 `text/event-stream`：

| 事件 | 主要字段 | 说明 |
|---|---|---|
| `status` | `stage`, `message` | `retrieving` / `analyzing` / `generating` / `retrying` |
| `token` | `content` | 模型增量文本 |
| `done` | `response`, `citations`, `session_id`, `model`, `retrieval_summary`, `regenerated` | 成功结束并持久化回答 |
| `error` | `code`, `error`, `retryable`（可选） | 检索或模型失败；失败问题保留供重试 |

`GET /api/assistant/stream` 保留同等能力，用 query string 传参；门户使用 POST，避免把问题文本放入 URL。

### 会话管理

| 端点 | 说明 |
|---|---|
| `GET /api/conversations` | 返回当前用户最近更新的 50 个会话 |
| `POST /api/conversations` | 显式创建空会话；门户通常由首次发送自动创建 |
| `DELETE /api/conversations/{session_id}` | 删除当前用户会话及其消息/agent runs；其他用户得到 404 |
| `GET /api/conversations/{session_id}/messages?limit=40` | 返回当前用户会话消息，范围 1-200 |
| `POST /api/conversations/{session_id}/messages` | 兼容性消息写入接口；正式问答由 stream 接口自动持久化 |

### `POST /api/assistant/query`

说明：

- 需要认证
- 这是 `HermesAgentBridge` / `readonly-agent` 的旧兼容入口，不是 0801 门户使用的正式问答接口
- 保留它是为了避免破坏旧调用方；后续确认无调用方后可独立下线

请求示例：

```json
{
  "query": "Bloom Energy SOFC 用作 AIDC 电源，当前最大技术边界是什么？",
  "context": "portal"
}
```

响应字段：

| 字段 | 说明 |
|---|---|
| `status` | 接口状态 |
| `mode` | `mock` / `cli` / `http` |
| `message` | bridge 状态说明 |
| `query` | 后端接收到的问题 |
| `response` | agent 或 bridge 返回内容 |
| `extra` | 兼容 readonly-agent 的结构化结果 |
| `suggested_next_steps` | 后续接入建议 |
| `error` | 错误信息，正常为 `null` |

### `GET /api/dashboards`

说明：

- 需要认证
- 返回技术仪表盘总表数据
- 当前为第一阶段轻量接口，用于前端实装仪表盘检索并预留服务器数据交互边界

查询参数：

| 参数 | 说明 |
|---|---|
| `q` | 可选，按技术名称、范围、核心指标关键词检索 |

响应字段：

| 字段 | 说明 |
|---|---|
| `items` | 仪表盘列表 |
| `total` | 返回数量 |

单个 `item` 字段：

| 字段 | 说明 |
|---|---|
| `id` | 仪表盘标识 |
| `name` | 技术/行业对象名称 |
| `scope` | 适用范围 |
| `metrics` | 核心指标列表 |
| `status` | 当前维护状态 |

## 16. 资料上传与分类

以下接口均要求登录；上传、重试和人工修正额外要求管理员角色。

### `GET /api/uploads/taxonomy`

返回当前分类目录 ID、版本、127 项完整输出、125 项业务分类，以及“未分类/不相关”两个结果标签。

### `POST /api/uploads`

`multipart/form-data`。`files` 可重复，不限制份数、单文件或单批大小。可选字段：`title`、`confidentiality`、`source_type`、`note`、`primary_category`。批量上传不能填写共享标题。上传时同步校验文本可提取性：无法提取文本（如扫描版/纯图片 PDF、加密文档、空文档）的文件会被整批拒绝（HTTP 422），并在 `detail` 中逐个列出文件名与原因。

`confidentiality` 只接受 `公开`、`内部`、`管理员`。历史值（如“付费来源”“秘密”）兼容导入时归一为 `内部`；AI 自动补齐只允许 `公开` 或 `内部`，`管理员` 需要上传者明确选择。密级当前仅作元数据标签，不单独改变下载权限；“付费数据库”属于 `source_type`，不是密级。

文件先持久落盘并登记 SHA-256。未手工指定分类时返回 `pending`，后台再调用内网/本地模型分类；分类完成后提取全文（不限长）、按 2000 字符/200 重叠分块，并调用 canonical QA 内部 embedding 接口写入增量索引。分类失败或 embedding 失败都不会删除文件。

### `DELETE /api/uploads/{file_id}`

仅管理员。三处同步删除：canonical-qa 增量索引（幂等，未索引视为成功）→ 落盘文件 → 数据库记录。索引删除失败时返回 502 且资料保持原状；资料不存在返回 404。成功返回 `{"ok":true,"removed_chunks":N,"index_skipped":false}`。

### `GET /api/uploads`

查询参数：`limit`、`offset`、`source_type`、`primary_category`、`classification_status`。响应包含总数 `count` 和 `files`；每条记录另返回 `embedding_status`、`embedding_model`、`embedding_dim`、`chunk_count`、`embedding_error` 和 `ingestion_status`。

### `POST /api/uploads/{id}/classification/retry`

把已落盘资料重新置为 `pending` 并启动后台分类。`pending/processing` 状态下重复调用不会创建并行任务。

### `POST /api/uploads/{id}/embedding/retry`

管理员重试已分类文件的 embedding 和增量索引写入。索引失败不会修改分类结果；同一文件重复重试会替换其旧 chunk，不产生重复记录。

### `PUT /api/uploads/{id}/classification`

人工修正示例：

```json
{
  "primary_category": "通用技术/材料工程/特种功能材料/催化材料",
  "secondary_categories": [],
  "reason": "管理员复核"
}
```

主分类必须精确匹配 127 项目录（树上任意节点均可人工指定），辅助分类最多 3 项且只能使用 125 个业务叶子分类。

### `GET /api/uploads/{id}/download`

鉴权流式下载，响应使用 RFC 5987 UTF-8 文件名。实体缺失时返回 410 并把存储状态记为 `missing`。

## 17. 认证失败响应

当前后端认证失败常见返回包括：

```json
{
  "detail": "Not authenticated"
}
```

```json
{
  "detail": "Invalid or expired token"
}
```

```json
{
  "detail": "密码已修改，请重新登录"
}
```

## 18. 状态流转说明

当前情报主状态流转如下：

```text
新建草稿 -> draft
提交建议 -> ai_suggested
发布 -> published
发布修订稿 -> 新记录 published + 原记录删除
```

预警状态流转如下：

```text
无预警 -> active -> dismissed
```

上传资料状态流转如下：

```text
文件落盘 -> pending -> processing -> classified | unclassified | irrelevant
                                  \-> failed -> pending（管理员重试）
历史记录 -> legacy_unclassified -> pending（管理员重试）
```

## 19. 联调建议

如果要做前后端联调，建议按以下顺序验证：

1. `POST /api/auth/login`
2. `GET /api/auth/me`
3. `GET /api/domains/tree`
4. `POST /api/info-items/draft`
5. `GET /api/info-items/drafts`
6. `POST /api/info-items/publish`
7. `GET /api/info-items?status=published`
8. `GET /api/info-items/{id}`
9. `PATCH /api/info-items/{id}/alert`
10. `PATCH /api/info-items/{id}/details`
11. `PATCH /api/info-items/{id}/indicators`
12. `DELETE /api/info-items/{id}`
13. `GET /api/uploads/taxonomy`
14. `POST /api/uploads`（手工指定分类做无模型烟雾测试）
15. `GET /api/uploads/{id}/download`
