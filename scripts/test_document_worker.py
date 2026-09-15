"""Real subprocess timeout/exit tests; no Docling model or uploaded document needed."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "backend/app/document_ingestion/runner.py"
spec = importlib.util.spec_from_file_location("document_runner", path)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class WorkerTests(unittest.TestCase):
    def test_timeout_kills_and_reaps_process(self):
        started = []
        original = subprocess.Popen

        def spawn(*args, **kwargs):
            process = original(*args, **kwargs)
            started.append(process)
            return process

        begin = time.monotonic()
        with patch.object(runner.subprocess, "Popen", spawn):
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run_worker([sys.executable, "-c", "import time; time.sleep(60)"], 0.2)
        self.assertLess(time.monotonic() - begin, 5)
        self.assertIsNotNone(started[0].returncode)

    def test_abnormal_exit_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "code=7"):
            runner.run_worker([sys.executable, "-c", "raise SystemExit(7)"], 5)

    def test_success_after_timed_out_worker(self):
        runner.run_worker([sys.executable, "-c", "pass"], 5)


if __name__ == "__main__":
    unittest.main()
