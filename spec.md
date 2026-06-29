# 前沿技术情报与预警平台 - 技术规格说明

> 过时提示：本文件为历史规格草案，仍包含“后端为未来能力”“独立 alerts / indicator_values 表”“旧版发布接口路径”等设计，**与当前实际代码和数据库实现不一致**。  
> 现行规格请优先参考：`数据字段与表结构.md`、`API接口说明.md`、`项目整体说明.md`。

版本：V1.5
架构：前端静态页面 + 后端 FastAPI + PostgreSQL（未来）

---

# 一、数据模型

## 1. domains

- id: varchar (PK)
- name: varchar
- parent_id: varchar (nullable, FK -> domains.id)

---

## 2. info_items

- id: UUID (PK)
- title: varchar (required)
- content: text (required)
- source_url: varchar (nullable)
- published_at: timestamp (nullable)
- created_at: timestamp
- updated_at: timestamp
- status: enum('draft','published')
- importance_score: int (1-5)
- is_new_tech: boolean
- comment: text (nullable)
- source_types: jsonb (array of string)
- info_types: jsonb (array of string)
- tags: jsonb (array of string)

---

## 3. info_item_domains

- info_item_id: UUID (FK -> info_items.id)
- domain_id: varchar (FK -> domains.id)
- is_primary: boolean

支持多领域归属。

---

## 4. indicator_defs

- id: varchar (PK)
- name: varchar
- unit_default: varchar
- data_type: enum('number','string')
- is_active: boolean

---

## 5. indicator_values

- id: UUID (PK)
- info_item_id: UUID (FK)
- indicator_id: varchar (FK -> indicator_defs.id)
- name: varchar
- value_number: numeric (nullable)
- value_string: varchar (nullable)
- unit: varchar
- source: enum('auto','manual')

---

## 6. alerts

- id: UUID (PK)
- info_item_id: UUID (FK)
- status: enum('active','dismissed')
- source: enum('auto','manual')
- manual_override: boolean
- alert_title: varchar
- alert_body: text
- reviewer_comment: text
- dismiss_reason: text
- alert_color: enum('yellow','orange','red')

---

# 二、核心业务规则

## 1. 状态机

draft → ai_suggested → published

- draft 状态不可参与统计
- published 才参与筛选和趋势图

---

## 2. 发布规则

发布时必须：

- title 非空
- content 非空
- 至少选择一个 domain
- 若开启预警：
    - alert_title 必填
    - alert_body 必填
    - reviewer_comment 必填

---

## 3. 指标抽取规则（当前阶段）

逻辑：

1. 从 content 中匹配数字（正则）
2. 检查数字前10个字符是否包含 indicator_defs.name
3. 若多个匹配，选择距离最近的
4. 生成结构：

{
  name,
  suggested_value,
  unit_default,
  confidence,
  evidence
}

用户可手动修改。

---

# 三、API 设计（未来后端）

## 获取领域树

GET /api/domains/tree

---

## 获取情报总表

GET /api/info-items

Query Params:
- domain_id
- from
- to
- source_types[]
- info_types[]
- importance_min
- importance_max
- has_active_alert
- has_comment
- q

---

## 保存草稿

POST /api/info-items/draft

---

## AI建议

POST /api/info-items/{id}/ai-suggest

---

## 发布

POST /api/info-items/{id}/publish

Body:
{
  indicator_values: [],
  alert: {
    enabled,
    alert_title,
    alert_body,
    reviewer_comment,
    alert_color
  }
}

---

# 四、错误返回格式

{
  code: string,
  message: string,
  details: object
}

---

# 五、当前阶段说明

当前版本为前端样机：

- 发布写入 localStorage
- 总表读取 json + localStorage 合并
- AI为规则抽取，不调用模型

后续替换为真实 API。
