"""Local Docling document intelligence; independent of API and vector transport."""

import os

# Opt out before any Docling/ONNX native import: the API-only switch is too late
# to prevent ONNX Runtime's initialization telemetry on non-Windows platforms.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
