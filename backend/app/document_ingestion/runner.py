"""Bounded ingestion worker. A hung native model must not occupy API threads forever."""

import json
import logging
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)


def run_worker(command, timeout):
    """Kill and reap the worker (including native converter children) on timeout."""
    process = subprocess.Popen(command, start_new_session=os.name == "posix")
    try:
        code = process.wait(timeout=timeout)
    except BaseException:
        if process.poll() is None:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
        process.wait()
        raise
    if code:
        raise RuntimeError(f"文档解析进程异常退出（code={code}）；请检查 API 日志和内存限制")


def ingest(**kwargs):
    timeout = float(os.getenv("TECHDB_DOCUMENT_TIMEOUT_SECONDS", "900"))
    if not math.isfinite(timeout) or not 1 <= timeout <= 7200:
        raise ValueError("TECHDB_DOCUMENT_TIMEOUT_SECONDS 必须在 1 到 7200 秒之间")
    document_id = kwargs["document_id"]
    logger.info("Document %s: starting isolated ingestion; timeout=%ss", document_id, timeout)
    with tempfile.TemporaryDirectory(prefix="techdb-ingestion-") as directory:
        request = Path(directory) / "request.json"
        output = Path(directory) / "result.json"
        request.write_text(json.dumps(kwargs, default=str), encoding="utf-8")
        try:
            run_worker(
                [sys.executable, "-m", "app.document_ingestion.runner", str(request), str(output)],
                timeout,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error("Document %s: ingestion timeout; worker terminated", document_id)
            raise TimeoutError(
                f"文档解析超时（{timeout:g} 秒），解析进程已终止。"
                "原文件保留；请检查 API 日志中的解析/分块阶段后重试。"
            ) from exc
        if not output.is_file():
            raise RuntimeError("文档解析进程未产出结果；请检查 API 日志")
        result = json.loads(output.read_text(encoding="utf-8"))
        return result[0], result[1], result[2]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from .service import ingest as convert_and_store

    values = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    values["root"] = Path(values["root"])
    values["original"] = Path(values["original"])
    result = convert_and_store(**values)
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
