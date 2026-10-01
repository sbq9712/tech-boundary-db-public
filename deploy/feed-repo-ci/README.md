# tech-boundary-data-feed 独立校验 CI（五.2 预备件——未部署）

## 是什么
`validate.yml` 是给 **公开仓库 sbq9712/tech-boundary-data-feed** 的 GitHub
Actions 工作流：每次 push 到 main 时，用独立校验器
（scripts/validate_feed_package.py 的快照）逐个校验仓库内全部 .zip 增量包，
并核对 LATEST.json 索引与包文件的一一对应。任何绕过生成器的手工改动
（篡改 changes.json / manifest / 插包）会在 CI 上红掉。

## 为什么放这里
feed 仓库与生成器同源（本仓库 scripts/build_feed_package.py），但校验器
必须独立于生成器部署才有公开可信度。部署动作 = 把本目录两个文件复制到
feed 仓库 main 分支根目录：

    cp deploy/feed-repo-ci/validate.yml <feed-repo>/.github/workflows/validate.yml
    cp scripts/validate_feed_package.py <feed-repo>/scripts/validate_feed_package.py
    cd <feed-repo> && git add -A && git commit -m "ci: independent package validation" && git push

**部署需另行授权**（向公开仓库写入文件；本任务边界内不执行）。
部署后每次发布 push 都会自动跑校验；失败即说明包被改动或生成器/校验器契约漂移。

## 覆盖范围（校验器已实现）
- zip 安全（成员数/恶意路径/超大成员）
- manifest 必填键、records_sha256、record_count 对账
- changes_sha256 字节绑定（v 1→99 之类篡改即刻红）
- 发布序列自洽性（manifest_digest / chain / sequence）
- 记录白名单、id↔t|d|u、scd 五槽形态、公开来源准入（内网/凭据拒绝）
- changes 与 records 对账（key 一致、重复键、DELETE 不在 records 等）
