# 前沿技术情报与预警平台 - 开发任务板

> 规则：
> 1. 每次只允许完成一个 Block。
> 2. 未被标记为 [x] 的 Block 才可执行。
> 3. 不得修改已完成 Block 的功能，除非修复明确 bug。
> 4. 所有变更必须符合 spec.md 数据模型与字段命名。
> 5. 每个 Block 完成后必须输出：
>    - 变更文件列表
>    - 核心逻辑说明
>    - 本地验证步骤

---

# 当前阶段：V1.5 前端样机完善

---

## [x] Block 1 - localStorage 闭环跑通

### 目标
跑通完整流程：

上传 → AI建议 → 人工修正 → 发布 → 总表展示（基于 localStorage）

### 范围
- 不引入后端
- 不引入数据库
- 不修改字段结构
- 不大规模改 UI
- 允许补充趋势图面板 X/Y 轴名称与分度值（index.html）

### 要求
- 发布后写入 localStorage
- 状态从 draft → ai_suggested → published
- 总表页面读取 published 状态数据
- published 数据参与筛选

### 验收标准
- 刷新页面数据仍在（localStorage 持久）
- draft 数据不出现在总表
- published 才参与筛选
- 不报 console error

---

## [x] Block 2 - 指标抽取规则模块化

### 目标
实现 spec.md 中定义的规则抽取逻辑，并封装为独立模块

### 规则
1. 匹配正文中的数字（支持整数/小数/百分号）
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

### 要求
- 抽取逻辑放在独立文件（如 /lib/extractor.js）
- 页面只调用函数，不写复杂逻辑
- 不自动写入数据库
- 用户必须手动确认

### 验收标准
- 点击“提交并生成AI建议”能生成建议
- 多个指标时选最近
- 无匹配时返回空数组
- 不影响现有页面结构

---

## [x] Block 3 - 发布校验与预警规则强化

### 目标
实现发布前强校验逻辑

### 规则
发布时必须满足：

- title 非空
- content 非空
- 至少一个 domain
- 若开启预警：
    - alert_title 必填
    - alert_body 必填
    - reviewer_comment 必填

### 要求
- 封装为统一校验函数
- 不允许绕过校验发布
- 错误提示清晰

### 验收标准
- 缺少字段无法发布
- 关闭预警不需要填写 alert 字段
- 不影响 draft 保存

---

## [x] Bugfix Block - 详情页/工作台/领域树交互修复

### 目标
仅修复 bug + 小交互增强（不做 UI 重构）：

- 详情页支持从 localStorage drafts / published_items 查找
- dashboard 分级汇总表下钻过滤修复
- 左侧领域树路径展开与高亮

### 要求
- 不改变现有 UI 结构
- 保持现有数据结构与字段命名
- 只做最小必要改动

### 验收标准
- 详情页可打开本地草稿与本地发布条目
- 分级汇总表点击数字后只显示命中的条目
- 下钻后仅展开当前路径并高亮当前节点

---

## [x] Bugfix Block - 根目录选择实时高亮与趋势图更新

### 目标
修复根目录切换后需手动刷新才能更新高亮与趋势图的问题。

### 要求
- 根目录切换后立即刷新树高亮
- 趋势图面板自动使用当前领域范围
- 最小改动，不重构 UI

### 验收标准
- 切换根目录后高亮即时变化
- 趋势图无需手动刷新即更新

---

## [x] Block 4 - 总表合并与筛选稳定化

### 目标
实现 data/*.json + localStorage 合并读取

### 要求
- published 数据统一进入同一数组
- 支持：
    - domain 筛选
    - 时间筛选
    - source_types
    - info_types
    - 是否有预警
    - 是否有 comment
- 所有筛选基于 published

### 验收标准
- 筛选组合不会报错
- 筛选结果稳定
- 不影响页面性能

---

## [x] Bugfix Block - 上传复核预警生效与颜色选择

### 目标
修复上传&复核页强制开启预警后发布未生效的问题，并补充预警颜色选择。

### 要求
- 强制开启预警后发布需写入预警数据
- 发布时记录预警颜色
- 不改变现有 UI 结构，只做最小必要改动

### 验收标准
- 上传&复核页点击“强制开启预警”，发布后在详情页显示预警
- 预警颜色可选且在详情页展示一致

---

## [x] PageChange Block - 详情页布局与修订稿回流

### 目标
按页面改版要求调整详情页、总表、上传复核页交互：

- 详情页正文上移，详细信息下移
- 删除详情页快速跳转块
- 创建修订稿按钮移到顶部操作区并回流到上传&复核
- 总表增加删除情报按钮
- 上传页支持上传者调整密级

### 范围
- info_detail.html
- info_table.html
- upload_review.html

### 验收标准
- 详情页显示顺序为：标题信息 → 正文 → 指标 → 详细信息
- 详情页右侧不再显示快速跳转块
- 点击“创建修订稿”可带原始信息进入上传&复核页编辑
- 修订稿发布会生成新的情报 ID，不覆盖原情报
- 情报总表“新增/编辑预警”旁边有“删除情报”按钮
- 上传&复核页可编辑并保存 `classification`（密级）

---

# V1.6 - 后端与数据库落地

---

## [x] Block 5 - FastAPI 后端骨架

### 目标
创建最小可运行后端框架，为后续数据库接入做准备。

### 要求
- 建立标准 FastAPI 项目结构（如 app/main.py、routers、schemas 等）
- 实现 GET /api/health 接口，返回 { "status": "ok" }
- 实现 GET /api/domains/tree 接口（暂时从现有 data/domains.json 读取）
- 实现 GET /api/info-items 接口（暂时从 data/*.json 或 mock 数据返回，不做复杂筛选）
- 提供 docker-compose 支持（仅包含 api 服务，不接数据库）
- 提供最基本的 pytest 用例（至少包含 health 接口测试）

### 验收标准
- docker compose up -d --build 成功
- 访问 http://localhost:8000/api/health 返回 200
- /api/domains/tree 返回 JSON 数据
- pytest 通过

---

## [x] Block 6 - PostgreSQL 接入

### 目标
实现真实数据库存储

### 要求
- 建立 models
- 建立 migrations
- 连接 PostgreSQL
- 发布写入数据库
- 总表读取数据库

### 验收标准
- 发布数据进入数据库
- 重启容器数据仍在
- localStorage 不再使用

---

## [x] Block 7 - 草稿/预警后端化与批量上传增强

### 目标
补齐草稿与预警后端能力，并增强批量上传与模板说明，避免前端回填丢失与字段理解偏差。

### 要求
- 草稿保存时必须保留并可回填“之前选择的技术区域（domains）”，不得丢失。
- `alerts` 后端化：预警数据通过后端接口统一读写，不再依赖前端本地模拟状态。
- `drafts` 后端化：草稿创建、更新、列表、详情改为后端存储与查询。
- 批量上传支持 Excel `.xlsx` 文件（除现有 CSV 外）。
- 在“草稿批量上传页”新增“下载 CSV 说明模板”按钮，模板需包含：
  - 不同中文 domain 对应的英文填写字段说明；
  - 当前不同领域已预设 indicator 列表及其对应单位说明。

### 验收标准
- 保存草稿后刷新页面或重新进入编辑页，已选技术区域完整回显。
- 预警编辑与读取均通过后端接口完成，前端刷新后状态一致。
- 草稿不依赖 localStorage，后端重启后数据仍在数据库。
- 批量上传页可成功解析并导入 `.xlsx` 文件。
- 草稿批量上传页可下载 CSV 说明文件，内容包含 domain 中英文字段映射与各领域预设 indicator/单位。

### 本地验证结果（2026-03-08）
- `docker compose up -d --build` 启动通过（api + db）。
- `docker compose run --rm api pytest -q` 通过（`5 passed`）。
- 接口联调通过：
  - `GET /api/health` -> 200
  - `POST /api/info-items/draft` -> 201
  - `GET /api/info-items/drafts` -> 200
  - `GET /api/info-items/{id}/draft` -> 200
  - `POST /api/info-items/publish`（带 `draft_id`）-> 201
  - `PATCH /api/info-items/{id}/alert` -> 200

### Block 7 补充现状（2026-03-08 晚间）
- 已修复批量“直接发布”路径 500 问题（非 `draft_id` 发布时的 `flush` 顺序错误）：
  - 文件：`backend/app/routers/info_items.py`
- `excel_import.html` 批量导入宽容性已增强：
  - `.xlsx` 日期归一化（含 Excel 序列号）；
  - 多分隔符支持（`;`/`；`/`,`/`，`）；
  - 布尔值兼容（`true/1/yes/y/是`）；
  - 批量失败回显具体错误。
- 容器内集成验证补充通过：
  - 模拟 xlsx 批量生成草稿：2/2 成功；
  - 模拟 xlsx 批量直接发布：2/2 成功；
  - `/api/health` 返回 `{"status":"ok"}`。

---

## [x] Bugfix Block - 分页 / 指标ID / Web联调修复

### 目标
仅修复当前使用中的交互与链路问题，不做架构重构：

- 首页工作台展开列表增加翻页
- 情报总表增加翻页
- 上传复核页领域树布局微调
- 修复“指标已输入/已发布但详情不显示”
- 将指标从名称匹配升级为 `indicator_id` 贯穿
- 增加可用于浏览器联调的 `web` 静态服务

### 要求
- 不改变现有页面主体结构
- 保持 `spec.md` 字段命名约束
- 上传页、批量导入、发布、详情展示的指标链路统一保留 `indicator_id`
- 输入指标时应按预设指标名给出提示
- Docker 环境下可直接通过浏览器访问前端页面并联调后端 API

### 验收标准
- 首页工作台右侧展开列表在条目较多时可上一页/下一页翻页
- 情报总表在条目较多时可翻页，并在筛选变化后回到第一页
- 上传复核页领域树中 `+/-`、复选框、文字间距更紧凑
- 单条上传与 CSV 批量发布后，详情页能正确显示指标
- 预设指标输入后可绑定 `indicator_id`，详情页优先按 `indicator_id` 识别
- `docker compose up -d --build` 后可通过 `web` 服务访问静态页面，并通过同源访问 `/api/health`

### 本地验证结果（2026-03-16）
- `docker compose up -d --build` 通过（api + db + web）。
- `docker compose run --rm api pytest -q` 通过（`7 passed`）。
- `docker compose ps` 显示：
  - `api` Up
  - `db` Up / healthy
  - `web` Up
- 容器内联调通过：
  - `http://127.0.0.1/index.html` 可返回静态页面 HTML
  - `http://127.0.0.1/api/health` 返回 `{"status":"ok"}`

### Block 补充修复（2026-03-16）
- 已修复：指标输入框点击预设提示名后，继续填写数值并直接发布，详情页仍不显示指标的问题。
- 根因：
  - 指标名称虽然显示为预设名，但发布前未必稳定绑定到正确的 `indicator_id`；
  - 详情页优先按 `indicator_id` 识别时，这类指标会被漏掉。
- 修复方式：
  - 上传页在输入阶段即尝试同步预设绑定；
  - 保存草稿、预览、发布前统一重新归一化指标，确保写入：
    - `indicator_id`
    - 规范名称
    - 默认单位
- 回归验证：
  - `docker compose build api`
  - `docker compose run --rm api pytest -q` -> `7 passed`

---

## [x] User Added Block - CCUS 分类与指标口径重构

### 目标
基于 `CCUS分类和指标单位.xlsx` 重构 CCUS 技术领域，并按 CCUS 二级分类收紧可录入指标范围。

### 要求
- 保持 `CCUS` 为一级分类；
- 参考 Excel 的 `分类` sheet，将：
  - `Level1` 映射为 2 级分类；
  - `Level2` 映射为 3 级分类；
  - `Level3` 映射为 4 级分类；
- 指标字典改为读取 Excel 其余 sheet 的表头：
  - sheet 名对应 CCUS 二级分类；
  - 指标名后的括号内容作为默认单位；
- CCUS 下每个二级分类只能录入其对应 sheet 的指标；
- 上传复核页、批量导入、后端保存三层口径保持一致；
- 变更需记录到 `md` 文件。

### 验收标准
- `/api/domains/tree` 返回新的 CCUS 2/3/4 级树；
- `data/indicator_defs.json` 仅保留 Excel 对应的 CCUS 指标，并带单位；
- 选择某个 CCUS 叶子领域后，上传页只能选择该二级分类允许的指标；
- 批量导入时，跨 CCUS 二级分类的指标不能通过；
- 后端最终保存时会过滤掉不属于当前 CCUS 二级分类的指标。

### 本地验证结果（2026-03-24）
- `docker compose up -d --build` 通过；
- `docker compose run --rm api pytest -q` 通过（`9 passed`）；
- `docker compose ps` 显示：
  - `api` Up
  - `db` Up / healthy
  - `web` Up
- 同源联调通过：
  - `http://127.0.0.1:8080/index.html` 可返回页面；
  - `http://127.0.0.1:8080/api/health` 返回 `{"status":"ok"}`。

---

## [x] User Added Bugfix Block - 上传复核指标选择 / 批量导入指标命中修复

### 目标
修复上传&复核页指标下拉可见但无法切换的问题，并修正批量导入中指标名称命中与 `CO₂`/`CO2` 兼容性问题。

### 要求
- 上传&复核页选择预设指标时，切换后应稳定绑定到新指标，而不是回退为原先第一项；
- 批量导入按当前 CCUS 二级领域匹配预设指标：
  - 允许使用该二级领域下全部预设指标；
  - 支持按完整指标名或 `match_name` 命中；
- `CO₂` 中的角标 `₂` 在 CSV 模板/说明中改为普通 `2`，同时保留导入兼容；
- 变更需记录到 `md` 文件；
- 完成后补充测试并验证。

### 验收标准
- 上传&复核页切换指标下拉后，页面显示与最终提交的 `indicator_id` 一致；
- 批量导入中，当前 CCUS 二级领域内的预设指标可正常命中，不再误报“指标 1 未命中预设指标”；
- CSV 模板与说明文件中的 `CO₂` 示例改为 `CO2`；
- 回归测试通过。

### 本地验证结果（2026-03-25）
- `docker compose run --rm api pytest -q` 通过（`9 passed`）。

---

## [x] User Added Bugfix Block - 批量导入仅允许四级领域 / 发布后列表可见

### 目标
修复批量导入对领域层级校验缺失的问题，确保只允许四级领域；同时补齐回归验证，保证批量发布后的数据可出现在首页工作台和情报总表对应的数据源里。

### 要求
- 批量导入预览与提交时，`domains` 只能填写四级领域 ID，1/2/3 级领域必须直接报错；
- 后端保存/发布接口也要拒绝非四级领域，避免前端绕过；
- 补充测试验证：批量发布后的数据能从 `/api/info-items?status=published` 查询到；
- 变更需记录到 `md` 文件。

### 验收标准
- 批量导入时填写一级、二级、三级领域 ID，不可显示“通过”；
- 直接发布接口传入非四级领域会返回 400；
- 批量发布完成后，首页工作台和情报总表使用的已发布列表接口可以查到新数据；
- 回归测试通过。

### 本地验证结果（2026-03-25）
- `docker compose build api` 通过；
- `docker compose run --rm api pytest -q` 通过（`12 passed`）。

---

## [x] User Added Bugfix Block - 多领域指标并集与批量导入多领域分隔说明

### 目标
确保同一条情报选择多个领域时，可使用这些领域所属 CCUS 二级领域的指标并集；批量导入明确支持在 `domains` 字段中用英文分号 `;` 分隔多个领域。

### 要求
- 单条上传/发布时，若 `domain_ids` 同时包含多个 CCUS 叶子领域，则允许保留这些领域所属二级分类的全部预设指标并集；
- 批量导入模板与页面说明明确 `domains` 支持多个领域，格式为英文分号 `;` 分隔；
- 变更需记录到 `md` 文件并补充测试。

### 验收标准
- 同一条情报同时选择“捕集”与“运输”等多个叶子领域时，可同时保存两侧允许的预设指标；
- 批量导入页面与模板示例清楚说明多个领域 ID 的分隔方式；
- 回归测试通过。

### 本地验证结果（2026-03-25）
- `docker compose build api` 通过；
- `docker compose run --rm api pytest -q` 通过（`12 passed`）。

---

# 执行顺序

Block 必须按顺序执行：

1 → 2 → 3 → Bugfix → 4 → 5 → 6 → 7 → Bugfix

user可以再中间任何时刻增加block

---

# Agent 执行指令模板

当执行时必须：

- 只完成当前未打勾的 Block
- 不修改其他 Block
- 小步提交（1-3 commit）

- 所有测试通过后才声明完成


