# 前沿技术情报与预警平台 API 接口说明

> 更新时间：2026-05-14  
> 依据代码：`backend/app/routers/*.py`、`backend/app/schemas/*.py`

## 1. 接口总览

当前后端统一以 `/api` 作为前缀，按功能分为：

| 模块 | 说明 |
|---|---|
| `health` | 健康检查 |
| `auth` | 登录、当前用户、修改密码 |
| `domains` | 领域树 |
| `info-items` | 草稿、发布、详情、指标、预警 |

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

### `GET /api/assistant/status`

说明：

- 需要认证
- 客户端打开门户时调用，用于确认 `techdb-readonly` agent 和只读知识库挂载状态
- 当前会返回知识库路径、是否挂载、Markdown 文件数量等健康信息

响应字段：

| 字段 | 说明 |
|---|---|
| `status` | `ok` / `configured` / `error` |
| `mode` | bridge 模式，当前为 `http` |
| `agent` | 当前 agent 名称，预期为 `techdb-readonly` |
| `health` | readonly agent `/health` 返回内容 |

### `POST /api/assistant/query`

说明：

- 需要认证
- 前端门户通过此接口提交对话问题
- 后端已接入 `HermesAgentBridge` 适配层，默认通过 HTTP 调用独立 `techdb-readonly` agent 服务
- readonly agent 只做知识库/数据库只读查询，不编辑知识库、不运行 shell、不修改数据库
- readonly agent 当前是“检索 + LLM 生成回答”：先从只读 Markdown 知识库、情报表和仪表盘索引检索上下文，再调用 OpenAI-compatible Chat Completions 生成带引用回答
- 模型配置通过 `TECHDB_AGENT_API_KEY`、`TECHDB_AGENT_BASE_URL`、`TECHDB_AGENT_MODEL`、`TECHDB_AGENT_AI_TIMEOUT_SECONDS` 注入；不要把密钥写入项目文件
- 生产接入前仍需增加数据库只读账号、审计日志和更精细的检索排序

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
| `extra` | 只读 agent 的结构化结果，包含 `confidence`、`verified_facts`、`knowledge_documents`、`related_dashboards`、`citations` 等 |
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

## 16. 认证失败响应

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

## 15. 状态流转说明

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

## 16. 联调建议

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

