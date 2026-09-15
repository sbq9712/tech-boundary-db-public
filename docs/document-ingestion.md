# 上传资料：Docling Document Intelligence

上传 API、现有分类、Agentic RAG 和网页抓取保持兼容。Docling 是上传文档的唯一解析引擎；不再用独立的 PDF/Word/Excel 纯文本提取器，也不再按固定字符数切块。

## 流程与数据边界

`POST /api/uploads` → 原文件持久落盘 + PostgreSQL 上传记录 → 后台 Docling 转换 → HybridChunker → 原子发布资产包 → 原有分类 → canonical-qa bge-m3 / Vector + BM25 → Agentic RAG。

上传保持异步，返回原有 `count/files`，每条记录增加 `document_id`、`filename`、`chunks_count`、`status`、`document_assets`。初次返回并不表示可检索；列表轮询直到 `embedding_status=ready`。转换、分类或索引失败保留原文件和错误状态，使用现有分类/索引重试入口；进程重启继续原有 pending recovery。此改动不宣称新增了多进程任务队列。

- `app/document_ingestion/parser.py`：从安装版本的 `FormatToExtensions / FormatToMimeType` 动态发现格式，支持复合扩展名及 MIME 提示；最终文件内容由 Docling 验证。`GET /api/uploads/formats` 返回注册表。
- `docling_processor.py`：同一 DocumentConverter 处理数字文档、扫描件、图片。启用原生自动 OCR、表格结构、PDF 标题层级、图片导出和公式增强。禁止解析器读取引用的远程/本地外部资源。
- `chunker.py`：Docling HybridChunker，默认真实 `BAAI/bge-m3` tokenizer、512 token 预算、原生章节/语义边界；送入索引前不会再次切块。
- `metadata.py`：原有上传 UUID 即 document_id；chunk UUID 基于文档 ID、原文件校验和、原生 metadata、正文和 chunk 序号确定。保留所有相关页码、章节、Docling item `$ref` 和 bounding boxes。DOCX 等原生无页码时为 null，不伪造页码。
- `storage.py / service.py`：校验原文件 SHA-256；完整资产先写 staging、fsync，再原子发布。数据库只引用发布后的资产包；重试检查各文件 SHA/大小及 pipeline 配置后复用，否则重新转换。

持久目录复用 `TECHDB_UPLOAD_DIR`（Compose 中 `/app/uploads`）：

```text
objects/<prefix>/<uuid>.<ext>                 原文件，不变
 documents/<document_id>/<bundle_id>/
  document.md                               保留标题/列表/表格的 Markdown
  document.json                             原生 Docling JSON，嵌入图片
  chunks.jsonl                              稳定 chunk ID、正文与 metadata
  chunk_metadata.jsonl                      页码/章节/原文引用等 metadata
  conversion.json                           原生输入类型、OCR 可观测结果
  manifest.json                             来源、版本、SHA-256、大小、数量
```

`uploaded_files.document_assets` 是新 JSONB 字段（Alembic `0021_document_assets`），保存 bundle 引用及校验信息。旧记录不删除、不自动重建；按需使用现有重试入口升级。

Embedding 继续由 canonical-qa 生成，按 chunk ID 和 document ID 与原有持久向量矩阵关联，仍为 bge-m3 1024 维；不在 JSONL 中复制浮点向量。增量 BM25 和向量返回相同 provenance。回答保留 chunk 证据全文（受原有总上下文预算限制），而不只使用 UI 的短摘要；页面引用显示页码/章节。

知识图谱的实体/关系模型没有修改，也没有把 chunk 转为实体节点。未来可通过 `Entity → mentioned_in → Document → contains → Chunk`，再通过 Docling item 引用定位到原文；本轮不自动生成实体/关系。

## 安装和运行

项目使用 Python 3.11。`backend/requirements.txt` 固定 Docling 2.127.0 / docling-core 2.96.0 和兼容的推理依赖。Dockerfile 安装 CPU PyTorch、LibreOffice（旧 Office/RTF 转换）、ffmpeg（音视频）、字体及图像系统库。所有注册格式均交给 Docling 原生后端；音视频需要原生 ASR 模型，EBCDIC 等非自描述格式仍必须提供原生 layout 配置，不承诺从缺失信息中猜测结构。

直接 Python 开发环境可安装：

```bash
python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r backend/requirements.txt
cd backend
alembic upgrade head
```

首次在线使用 PDF/OCR/公式/音视频及 tokenizer 可能下载模型。Docling 初始化前设置 `ORT_DISABLE_TELEMETRY=1` 和 `HF_HUB_DISABLE_TELEMETRY=1`，并调用 ONNX 官方遥测关闭接口。上传文档不会发送到外部 Docling 服务；原有 AI 分类/回答仍调用你配置的 `TECHDB_AGENT_*` 服务。公司离线环境须预备模型，不会自动把文档转发到公网。

Compose 持久挂载 `external-data/document-models` 到 `/app/document-models`，`HF_HOME` 位于其中。可在联网的构建/准备环境使用 Docling 官方下载器：

```bash
docling-tools models download layout tableformer code_formula rapidocr -o /path/to/document-models/docling --rapidocr-backend-lang onnxruntime:ch
```

然后在本机未入 Git 的 `.env.local`（生产为 `.env`）配置：

```dotenv
TECHDB_DOCLING_ARTIFACTS_PATH=/app/document-models/docling
TECHDB_DOCUMENT_TOKENIZER=/app/document-models/bge-m3-tokenizer
TECHDB_DOCUMENT_CHUNK_TOKENS=512
TECHDB_DOCLING_FORMULAS=true
```

`TECHDB_DOCUMENT_TOKENIZER` 指向包含 tokenizer 配置和词表的本地目录；在线开发也可保持默认 `BAAI/bge-m3`。音视频模型按 Docling ASR 配置另行预备。Docling/PyTorch/OCR 模型不在普通 Git clone 中，不提交模型、上传文件或派生资产。

需要特殊格式原生配置时，`TECHDB_DOCLING_BACKEND_OPTIONS_FILE` 指向管理员控制的 JSON 文件，格式为 `{ "ebcdic": { ...原生 EbcdicBackendOptions... } }`。值用该格式的 Docling Pydantic 类型校验；不从上传内容加载配置，不允许开启外部资源抓取。配置内容不写进公开元数据，只保存校验和。修改模型或 backend 配置后重启 API。

**同时更新 canonical-qa 的代码层**，否则旧镜像的请求模型会丢弃 chunk metadata。已有固定资产镜像时，使用仓库现有增量构建路径（先保留基座镜像）：

```bash
cd ~/tech-boundary-db
docker tag techdb-canonical-qa:0801 techdb-canonical-qa:0801-base
docker build -f services/canonical-qa/qa-backend/Dockerfile.incremental --build-arg QA_BASE_IMAGE=techdb-canonical-qa:0801-base -t techdb-canonical-qa:0801 services/canonical-qa
docker compose --env-file .env.local up -d --force-recreate canonical-qa
bash ./start_with_local_ai.sh
```

上述镜像名针对默认 0801 配置；自定义 `TECHDB_IMAGE_TAG` 时对应替换。不会删除 PostgreSQL、uploads 或索引卷，禁止使用 `down -v`。没有 canonical 基座资产时，文档解析可单独测试，但 embedding 会明确失败并等待重试，不能冒充已可检索。

## 验证上传

登录管理员，在原有“上传资料”中选文件；可手动选业务分类，以便独立于 AI 分类服务验证解析。随后检查资料库状态、在知识库问答检索文件内容、查看引用页码/章节。

保留原文件下载：`GET /api/uploads/{document_id}/download`。
新增鉴权资产下载：`GET /api/uploads/{document_id}/assets/{asset}`，asset 为 `markdown / docling_json / chunks / chunk_metadata / manifest / conversion`。仍沿用现有登录授权；密级仍是现有标签，本轮没有另建权限规则。

确定性回归（实际 canonical 存储/检索 + embedding 替身）：

```bash
python -m pip install pytest jieba rank-bm25 reportlab==4.4.10
PYTHONPATH=backend python -m pytest -q backend/tests/test_document_ingestion.py backend/tests/test_upload_ingestion.py backend/tests/test_agent_service.py
```

六格式真实转换测试，现场生成纯合成普通 PDF、无文字层扫描 PDF、DOCX、PPTX、TXT 和表格 DOCX：

```bash
RUN_DOCLING_REAL_TESTS=1 PYTHONPATH=backend DOCLING_TEST_REPORT_DIR=reports/docling python -m pytest -q -s backend/tests/test_document_conversion_real.py
```

每份报告包含 document_id、file_type、chunk 数、OCR 是否观察到、Markdown 和 metadata 示例。扫描测试必须检测到真实 OCR 文本；不能只凭启用 OCR 开关判定成功。默认使用真实 bge-m3 tokenizer；`TEST_DOCUMENT_TOKENIZER=fixture` 仅用于离线转换合同测试，报告会明确标注替身，不能据此声称真实 tokenizer/embedding 验收。

`.github/workflows/document-ingestion.yml` 提供临时 PostgreSQL migration、回归测试和六格式真实转换验收，不需要公司数据库或 Secret，不部署服务。
