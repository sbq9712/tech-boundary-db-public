# 上传分类采用 LLM 读代表性正文 + 健壮匹配，不使用 embedding 分类

## 背景

上传资料需归入广度追踪 77 项分类目录。原实现调用公司内网 GLM 模型，对资料**前 12000 字**做单次分类，并要求模型返回的 `primary_category` 与目录字符串**逐字相等**，无重试。服务器实测出现两类问题：大文件偶发传输失败（已定位为公司网关 `client_max_body_size` 默认 1MB，已于网关侧解决）；以及分类频繁失败。

调研后确认两个硬约束：canonical-qa 只暴露 `/api/index/upsert` 与检索接口，**没有独立的 `/api/embed`**；分类目录是**纯路径字符串，无 description / keywords**。

## 决策

分类继续由 LLM 完成，但做两件事：

1. **喂对内容**：分类输入由"前 12000 字"改为整篇**代表性采样**（头/中/尾 4:3:3，预算 `CLASSIFICATION_BUDGET_CHARS = 40_000`），避免 PDF 封面、目录、引言主导模型判断。
2. **健壮化匹配与重试**：目录命中改为"精确 → 归一化（去引号/标点/空白）→ `difflib` ≥0.9 模糊"三级；模型返回非合法 JSON 时正则抠最外层 `{...}` 兜底；调用加指数退避重试（仅重试超时 / 429 / 5xx / 坏响应形状，非重试 4xx 立即抛），接上此前已定义但未使用的 `TECHDB_AGENT_MAX_RETRIES` / `TECHDB_AGENT_RETRY_BASE_DELAY_SECONDS`；失败时把模型原始返回（截断 300 字）写入 `classification_error` 便于排查。

## 为什么不用 embedding 分类

考虑过"先 embedding 再按相似度分类"（文档向量 vs 类目原型向量）及"embedding 召回 top-k 再交 LLM 裁决"的混合方案，放弃，原因：

- 分类目录是裸路径，语义弱，需另行为 77 个类目造原型向量（描述或代表文档），是额外工程。
- canonical-qa 无 `/api/embed`，要走 embedding 分类还得新增对外向量接口，或在 API 侧另起一个 bge-m3。
- 同事此前用 embedding 做分类实测**准确率不理想**，与本仓库"裸路径类目"的弱点一致。
- LLM 分类顺带产出标题、密级、来源等元数据，纯 embedding 分类拿不到。

embedding 仍照旧用于检索（bge-m3 增量索引），只是不参与分类决策。

## 后续可能 revisit

若 LLM 分类在"代表性采样 + 健壮匹配 + 重试"之下仍不达标，再评估混合方案（embedding 召回候选 + LLM 在小范围裁决）。届时需先补齐 embed 接口与类目原型。
