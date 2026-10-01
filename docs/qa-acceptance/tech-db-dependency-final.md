# tech-db / tech-db-fresh 依赖终报（八，2026-10-01，仅报告不执行）

## tech-boundary-db（本仓库）对 tech-db 的依赖：已解除

| 链路 | 状态 |
|---|---|
| 索引三源 | 可复现（管线发布视图 68,723 / 重建资产 68,523 / 增量卷），不读 tech-db |
| QA 离线导入链 | 完整（ZIP→watermark→canonical-qa），不读 tech-db |
| 水合/灾后恢复 | 纯本地源（七） |
| canonical-qa 镜像 | 自包含（Dockerfile.rebuilt + check_assets 门禁；bge-m3 模型在镜像内） |
| 门户 web | 静态资产+api，不依赖 tech-db |

**唯一外部依赖 = LLM API key**（无 key → retrieval-only 降级，链路可用）。

## 是否可安全手动删除 tech-db：构建/验收角度可以

- 本仓库全部验收（e2e 55/55、契约测试、镜像构建）均在 tech-db 缺席下执行通过；
- 删除 tech-db 不影响生产容器运行（现网容器与本仓库镜像链独立）。

**注意区分**：
- **tech-db**（旧 QA 引擎仓）——可删（由用户决策）；
- **tech-db-fresh**（宿主 8765 旧服务进程，pid 1067649）——按授权边界
  「不停用旧服务」，本轮未动；它作为对照基准仍可人工比对。
  若删除仓库后仍需对照，建议保留该进程直至新链路生产切换完成。

## 授权边界遵守声明

本轮未修改/删除 tech-db 与 tech-db-fresh，未停用旧服务，未修改引擎上游，
未写入 EDMUNDSdaONE，未清空数据库/资料/模型/索引/同步状态，
未执行 docker compose down -v。生产容器全程只读核验。
