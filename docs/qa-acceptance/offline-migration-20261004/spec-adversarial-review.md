# SPEC 对抗式审查（Claude 自审，步骤④）

## 质疑 1：readonly-agent 重建为 1018 是否引入新风险？
0801 正在运行且验证健康；重建后其 /app/app=6307112 全树。风险：新树中 readonly_agent.py
的导入面未变（核实过 15-17 行），但新 main.py/models 若在 0801 有 import 兼容问题——
不成立：readonly_agent 是独立 FastAPI app，不 import main。裁定：重建安全，
且离线模拟 A3 会实证健康。保留。

## 质疑 2：A13 文档上传在离线 sim 的分类环节是否被网关卡死？
上传→docling 解析（本地模型）→AI 分类（网关 LLM）→embedding（本地 bge-m3）。
网关不可用时：分类如何终态？若停在 processing 则 A13 无法到 embedding ready。
需在 sim 中实测并按实际行为断言（降级=manual/unclassified 亦可接受，如实记录）。
修正：A13 增加分支断言「网关不可用时分类终态可人工推进（后台分类状态可编辑）
或明确 pending 不阻塞 embedding」。——落 T7 执行时确认。

## 质疑 3：offsim 用 internal 网络后端口发布还能用吗？
docker --internal 网络仍允许端口发布（DNAT 不经 NAT 出向）。已在本会话规划并
将实证（A3 起不来立即暴露）。若真不行：退路=普通 bridge+iptables 不可用则改用
`--pull never`+断网模拟（在 sim 内 dns_policy=none 检查无外呼）。修正：T7 先起
最小容器验证端口发布，再全栈。

## 质疑 4：db_restore.sh 恢复目标卷如何指向 offsim 的独立卷？
脚本用 ${TECHDB_PG_VOLUME}，offsim 用不同 .env（独立目录部署副本）即可。需要
offsim 用「代码目录副本+独立 .env」方式而不是 -p 项目名覆盖——修正 T7 实现细节：
rsync 代码到 ~/offsim/app（浅拷贝，含解包数据资产），独立 .env，compose 默认项目名
=目录名 offsim。彻底隔离，避免 -p 与卷名混淆。

## 质疑 5：三件套快照的 uploads tar 是「容器视角 -C /app/uploads .」，db_restore
的解包目标/安全检查是否兼容？
核实 db_restore.sh:79-90：tar -tzf 绝对路径/../ 检查 + -tvzf 链接检查 +
--no-same-owner 解包到 staging 再搬运——`./` 相对成员兼容。OK。

## 质疑 6：升级模拟（T8）用 0801 镜像 alembic upgrade head 得到的是 0020 还是 0001→0020？
0801 镜像内 alembic 只含 ≤0020 版本文件（其树是旧的），upgrade head=其自身 head。
需先查 0801 镜像内 alembic/versions 最大号再断言（执行时记录）。若 0801 内 head
≠0020，以实测为准（公司真实库同样以其 0801 版本为基线，语义不变）。

## 质疑 7：QA_LLM_BASE_URL 公网默认
核实 canonical-qa config.py：API_KEY 回落 env 文件或 TECHDB_QA_LLM_API_KEY；
BASE_URL 默认值待核实（若公网 Z.AI 默认，公司侧不配就走公网失败——离线本身连不通，
行为=QA 生成失败但检索可用；文档明确配置公司网关）。T6 落实。

## 质疑 8：Release 资产数与命名
镜像 6 个≈9 分片+2×sha256 文件→资产过多（每文件一个 asset）。合并策略：每镜像
一个 .part.sha256 资产多余——把全部分片哈希并入单一 SHA256SUMS 资产，分片裸传。
修正 T10：资产=分片文件+SHA256SUMS+manifest.json（体积/用途/命令）。

## 质疑 9：deploy.sh 在 offsim 无 LLM key 会怎样？
deploy.sh 强制要求 TECHDB_AGENT_API_KEY 非占位——offsim .env 用假随机值即可过
校验（不实际调用）。OK（A16 验证不外呼）。

## 质疑 10：git 对 backup/ 目录
.gitignore 是否排除 backup/？T6 核实并补（防止把 69M 上传 tar 提交进 git）。

## 结论
SPEC 整体成立；修正点：Q3/Q4（offsim 用目录副本+独立 env）、Q8（SHA256SUMS 合并）、
Q2/A13 分支断言、Q6 以实测 head 为准、Q7 落实文档、Q10 gitignore。已并入执行。
