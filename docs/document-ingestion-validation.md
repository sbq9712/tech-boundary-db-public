# Docling 文档摄取验收记录

被测代码提交：`7dde1bac069efbc80055cd3d1568a9cb2d3fe174`。输入均为测试现场生成的合成文档，不含公司或用户资料。

## 已执行的验证

- [真实 GitHub Actions](https://github.com/sbq9712/tech-boundary-db/actions/runs/34925046969)：**success**。
- Python 3.11，按 `backend/requirements.txt` 安装；`pip check` 无依赖冲突。
- 临时 PostgreSQL 16：`alembic upgrade head` 实际成功，包含 `0021_document_assets`。
- CI 回归/合同测试：**78 passed**；六格式真实转换：**6 passed**（25.63 秒）。
- 云端工作区另执行可独立运行的后端回归：**94 passed**；六格式真实转换：**6 passed**（198.57 秒，包含模型准备）。上述用例与 CI 有重叠，不能相加为独立用例数。
- Ruff（新增模块及测试）、Python compileall、app.js 语法检查通过。

真实转换使用 Docling 2.127.0、docling-core 2.96.0、原生布局/OCR/表格流水线、HybridChunker 和真实 bge-m3 tokenizer。每份输入都验证 original_file、Markdown、Docling JSON、chunks、chunk_metadata 存在，且重复执行复用完整、校验正确的资产。

以下 ID 是合成测试 ID；转换用例本身没有通过网页向业务数据库创建资料记录。

| 文件 | document_id | 原生格式 | chunks | OCR 是否实际触发 |
|---|---|---|---:|---|
| plain.txt | `84557779-3286-5a1e-85c7-90fb46a98c13` | md | 1 | 不适用/未观察到 |
| report.docx | `db90774e-d4b8-5b66-bf0f-89f28e504525` | docx | 1 | 不适用/未观察到 |
| slides.pptx | `10208d1d-a313-5ee8-a410-571b6054c4a0` | pptx | 1 | 不适用/未观察到 |
| table.docx | `46ba9b84-7bfb-5689-be2e-e5023744b4a9` | docx | 1 | 不适用/未观察到 |
| digital.pdf | `68c8d65b-5def-5632-9cd2-d263bcb69699` | pdf | 1 | 否 |
| scan.pdf | `cbd58188-319e-583b-bba6-51a65ce73638` | pdf | 1 | 是 |

TXT 使用 Docling 原生 Markdown 后端，因此 input_format 为 md；原文件名/MIME 独立保存。DOCX 无原生页码时为 null，保留章节与 Docling item 引用，不制造页码。

## Markdown 示例

### plain.txt

```markdown
# Synthetic evidence

Synthetic battery evidence: capacity retention is 95 percent after 100 cycles.
```

### report.docx

```markdown
## Synthetic evidence

Synthetic battery evidence: capacity retention is 95 percent after 100 cycles.
```

### slides.pptx

```markdown
# Synthetic evidence

- Synthetic battery evidence: capacity retention is 95 percent after 100 cycles.
```

### table.docx

```markdown
## Synthetic results

| Metric   | Value      |
|----------|------------|
| Capacity | 95 percent |
| Cycles   | 100        |
```

### digital.pdf

```markdown
## Synthetic evidence

Synthetic battery evidence: capacity retention is 95 percent after 100 cycles.
```

### scan.pdf

```markdown
SCANNED SYNTHETIC EVIDENCE Battery capacity retention: 95 percent Test duration: 100 cycles
```

## 扫描 PDF 的 provenance 示例

```json
{
  "document_id": "cbd58188-319e-583b-bba6-51a65ce73638",
  "chunk_id": "8e06b29b-dd85-52d9-bb54-66a529f1383b",
  "source_file": "scan.pdf",
  "page_number": 1,
  "section_title": "",
  "chunk_index": 0,
  "provenance": [
    {
      "doc_ref": "#/texts/0",
      "provenance": [
        {
          "bbox": {
            "b": 177.33333333333334,
            "coord_origin": "BOTTOMLEFT",
            "l": 22.666666666666668,
            "r": 373.6666666666667,
            "t": 300
          },
          "charspan": [
            0,
            91
          ],
          "page_no": 1
        }
      ]
    }
  ],
  "original_url": "/api/uploads/cbd58188-319e-583b-bba6-51a65ce73638/download"
}
```

六份完整 JSON 测试报告包含各自的 chunk metadata，可从上述 CI 的 `synthetic-document-conversion-reports` artifact 下载。生产上传生成的完整资产通过鉴权 `/api/uploads/{document_id}/assets/{asset}` 下载。

## 验证边界

- canonical 向量/BM25 持久存储、重载、删除及 provenance 传递使用确定性 embedding 替身。**没有宣称真实 bge-m3 embedding、完整 0801 索引或公司环境已验收。**
- 失败重试/状态推进用例使用 Session 替身；PostgreSQL migration 是真实执行，两者不可混称。
- 云端未运行依赖现有业务种子数据的 `test_api_endpoints.py`，以及需要已启动 web 的 `test_portal_ui_contract.py`；没有启动用户的 Docker 环境或部署公司服务器。
- 音视频、iWork、EBCDIC 等其余原生格式由注册表动态接入、安装对应依赖/提供原生配置，本次没有逐一转换验收这些格式。
- ONNX 初始化前使用官方 `ORT_DISABLE_TELEMETRY=1`，另关闭 ONNX API 遥测及 Hugging Face 遥测；转换不向外部文档解析服务发送上传内容。

安装、模型准备和现有 canonical 镜像代码层更新见 [document-ingestion.md](document-ingestion.md)。
