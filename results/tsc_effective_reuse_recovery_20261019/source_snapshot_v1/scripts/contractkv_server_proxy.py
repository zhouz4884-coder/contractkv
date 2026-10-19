#!/usr/bin/env python3
"""OpenAI-compatible ContractKV proxy for forwarding chat requests to vLLM."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.contractkv_decision_logger import DecisionLogger
from scripts.contractkv_policy_runtime import ContractKVRuntime


def forward_chat_completion(base_url: str, request: dict[str, Any], timeout: float = 120.0) -> tuple[int, bytes, float]:
    url = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(request).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
    return status, body, (time.perf_counter() - started) * 1000


class ContractKVProxy:
    def __init__(
        self,
        vllm_base_url: str,
        runtime: ContractKVRuntime,
        request_log: Path | str,
        decision_log: Path | str,
        timeout: float = 120.0,
    ):
        self.vllm_base_url = vllm_base_url.rstrip("/")
        self.runtime = runtime
        self.request_logger = DecisionLogger(request_log)
        self.decision_logger = DecisionLogger(decision_log)
        self.timeout = timeout

    def handle_chat_completion(self, request: dict[str, Any]) -> tuple[int, bytes, dict[str, Any]]:
        started = time.perf_counter()
        decision, timings = self.runtime.decide(request)
        logging_ms = self.decision_logger.write({"request": {"model": request.get("model")}, "decision": decision, "timings": timings})
        status, body, upstream_ms = forward_chat_completion(self.vllm_base_url, request, self.timeout)
        proxy_overhead_ms = (time.perf_counter() - started) * 1000 - upstream_ms
        request_row = {
            "model": request.get("model", ""),
            "status": status,
            "upstream_ms": upstream_ms,
            "proxy_overhead_ms": proxy_overhead_ms,
            "logging_ms": logging_ms,
            "policy": self.runtime.policy,
        }
        self.request_logger.write(request_row)
        return status, body, request_row


def make_handler(proxy: ContractKVProxy):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path not in {"/v1/chat/completions", "/chat/completions"}:
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            status, body, _ = proxy.handle_chat_completion(request)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8010)
    parser.add_argument("--vllm-base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--policy", default="ContractKV-Joint", choices=["ContractKV-Joint", "ContractKV-Indep"])
    parser.add_argument("--request-log", default="results/runtime/contractkv_proxy_requests.jsonl")
    parser.add_argument("--decision-log", default="results/runtime/contractkv_decision_logs.jsonl")
    args = parser.parse_args()

    runtime = ContractKVRuntime(policy=args.policy)
    proxy = ContractKVProxy(args.vllm_base_url, runtime, args.request_log, args.decision_log)
    server = ThreadingHTTPServer((args.listen_host, args.listen_port), make_handler(proxy))
    print(f"READY ContractKV proxy http://{args.listen_host}:{args.listen_port}/v1 -> {args.vllm_base_url}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
