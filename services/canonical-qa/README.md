# Tech-DB Q&A 系统

基于向量检索 + GLM-5.2 的技术情报问答系统。

## 架构

```
用户提问 → bge-m3 嵌入 → 基线 + 上传增量索引混合检索 → Top-20 记录 → GLM-5.2 流式生成 → 带引用的回答
```

### 组件
- **嵌入模型**: bge-m3 (BAAI), 1024维, 本地 CPU 推理
- **增量资料**: 上传服务通过 `POST /api/index/upsert` 写入独立向量/BM25 索引；基线索引保持只读
- **增量持久化**: `/app/data/lightrag/incremental/index.pkl`，由 Compose 的 `qa_incremental_data` 卷保存
- **LLM**: GLM-5.2 (ZAI API), 用于回答生成
- **向量索引**: numpy 余弦相似度 (40K+ 记录)
- **知识图谱**: LightRAG 实体抽取 (节点数持续扩展中)
- **后端**: FastAPI + SSE 流式输出
- **前端**: HTML5 Canvas 力导向图可视化 + Markdown 渲染

## 文件结构

```
qa-backend/
├── config.py            # GLM-5.2 + bge-m3 配置
├── vector_index.py      # 向量索引构建脚本
├── server.py            # FastAPI 服务器 (端口 8765)
├── ingest.py            # LightRAG 实体抽取脚本 (知识图谱)
├── start_server.sh      # 启动服务器
├── watch_and_restart.sh # 监控索引构建并自动重启
├── expand_graph.sh      # 索引完成后自动扩展知识图谱
└── data/lightrag/
    ├── vector_index.pkl     # 向量索引 (numpy)
    └── graph-export.json    # 知识图谱数据
```

## 使用方法

### 门户服务器离线部署

0801 门户只调用本服务的检索、状态和图谱接口，回答生成由门户 API
通过公司内网模型完成。因此 `techdb-canonical-qa:0801` 在未配置 LLM
密钥时也能以检索模式启动。

发布镜像使用 `Dockerfile.release`，内置固定 revision 的 bge-m3、现有
向量/BM25 索引、图谱和 `all-records-lite.json`。构建时
`check_assets.py` 按 `qa-assets-manifest.json` 校验 SHA-256、文件大小、
记录数和向量维度。服务启动时还会把索引元数据重新映射到分片重建后的
记录顺序；任何记录无法匹配都会导致启动失败，避免返回错误引用。

服务器不运行 `setup.sh`，不从 Hugging Face 下载模型，也不通过
Cloudflare 或开发者本机转发。门户和 QA 容器在同一 Docker 网络内通过
`http://canonical-qa:8765` 通信。

### 上传资料索引接口

门户 API 在文件完成分类和文本解析后，向 canonical QA 发送一份文档的 chunk、77 类分类、密级、来源和 SHA-256。接口会为 chunk 生成 bge-m3 向量、重建增量 BM25，并原子替换同一 `document_id` 的旧版本：

```text
POST /api/index/upsert
X-TechDB-Index-Token: <TECHDB_QA_INDEX_TOKEN>
```

该接口只供同一 Docker 网络内的 API 服务使用。设置 `TECHDB_QA_INDEX_TOKEN` 后，未携带正确令牌的请求会被拒绝。

### 1. 构建向量索引
```bash
cd /home/rhett/tech-db-fresh
.venv/bin/python qa-backend/vector_index.py
```
预计耗时: 6-8 小时 (40K 记录, CPU)
增量保存: 每 50 批 (6400 条) 自动保存一次

### 2. 启动服务器
```bash
cd /home/rhett/tech-db-fresh
.venv/bin/python qa-backend/server.py
```
服务器运行在 http://localhost:8765

### 3. 访问前端
前端文件在项目根目录,通过 HTTP 服务器访问:
```bash
cd /home/rhett/tech-db-fresh
python3 -m http.server 8097
```
然后打开 http://localhost:8097, 点击"数据库问答"标签

### 4. 自动化运维
```bash
# 监控索引构建并自动重启服务器
nohup bash qa-backend/watch_and_restart.sh &

# 索引完成后自动扩展知识图谱 (300条记录)
nohup bash qa-backend/expand_graph.sh &
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat/stream` | POST | 流式问答 (SSE) |
| `/api/search` | GET | 快速向量搜索 (?q=关键词&top_k=10) |
| `/api/graph` | GET | 知识图谱数据 (?limit=200) |
| `/api/stats` | GET | 系统统计 |
| `/api/health` | GET | 健康检查 |

## 扩展知识图谱

运行 LightRAG 实体抽取来扩展知识图谱:
```bash
.venv/bin/python qa-backend/ingest.py --max 500 --resume
```
- `--max N`: 处理前 N 条相关记录
- `--batch N`: 每批插入数量 (默认 50)
- `--resume`: 从上次中断处继续

每条记录约 30-60 秒 (含 LLM 调用), 每 10 批自动导出图谱快照

## 前端功能

- **知识图谱可视化**: Canvas 力导向图, 支持拖拽/缩放/悬浮提示
- **多对话管理**: 创建/切换/删除对话, localStorage 持久化
- **流式回答**: 实时显示生成内容, 支持 Markdown 格式
- **来源引用**: [1][2] 内联引用, 点击跳转到引用详情
- **操作菜单**: 复制/重新生成/导出 Markdown
- **示例问题**: 预设问题引导用户提问
