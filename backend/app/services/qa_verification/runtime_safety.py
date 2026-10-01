"""canonical-qa 移植版最小 runtime_safety（2026-09-30，五.1）。

旧仓库 runtime_safety.py（817 行）承载 RequestCancelled / 执行护栏 / 预算
等完整请求运行时。移植 answer_repair（BoundedRepairLoop）只需要其中的
可取消异常类型——本模块仅保留该语义契约，其余护栏由 FastAPI/SSE 层的
asyncio 取消语义承担。非完整迁移，勿在此追加护栏实现。
"""


class RequestCancelled(Exception):
    """请求已被客户端取消 / 服务端判定超时——终止一切后续处理。

    与旧仓库 runtime_safety.RequestCancelled 同名同语义：BoundedRepairLoop
    及验证链对该异常一律 re-raise，绝不吞掉后伪装成验证通过。"""
