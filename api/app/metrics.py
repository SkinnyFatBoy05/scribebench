from __future__ import annotations

import threading
from collections import Counter


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.jobs = Counter()
        self.requests = Counter()
        self.latency_count = 0
        self.latency_sum = 0.0
        self.input_tokens = 0
        self.output_tokens = 0

    def record_job(
        self, status: str, latency_ms: float, input_tokens: int, output_tokens: int
    ) -> None:
        with self._lock:
            self.jobs[status] += 1
            self.latency_count += 1
            self.latency_sum += latency_ms
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens

    def record_request(self, method: str, path: str, status: int) -> None:
        normalised = path if not path.startswith("/api/jobs/") else "/api/jobs/{id}"
        if normalised not in {
            "/api/jobs",
            "/api/jobs/{id}",
            "/api/cases",
            "/api/health",
            "/api/ready",
            "/api/models",
            "/metrics",
            "/api/auth/session",
            "/api/auth/login",
            "/api/auth/logout",
        }:
            normalised = "other"
        if method not in {"GET", "POST", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
            method = "OTHER"
        with self._lock:
            self.requests[(method, normalised, status)] += 1

    def render(self, queue_depth: int) -> str:
        with self._lock:
            lines = [
                "# HELP scribebench_queue_depth Jobs waiting in the in-process bounded queue.",
                "# TYPE scribebench_queue_depth gauge",
                f"scribebench_queue_depth {queue_depth}",
                "# HELP scribebench_jobs_total Completed job attempts by outcome.",
                "# TYPE scribebench_jobs_total counter",
            ]
            for status, count in sorted(self.jobs.items()):
                lines.append(f'scribebench_jobs_total{{status="{status}"}} {count}')
            lines.extend(
                [
                    "# HELP scribebench_tokens_total Approximate tokens processed by direction.",
                    "# TYPE scribebench_tokens_total counter",
                    f'scribebench_tokens_total{{direction="input"}} {self.input_tokens}',
                    f'scribebench_tokens_total{{direction="output"}} {self.output_tokens}',
                    "# HELP scribebench_job_latency_ms Job generation latency in milliseconds.",
                    "# TYPE scribebench_job_latency_ms summary",
                    f"scribebench_job_latency_ms_count {self.latency_count}",
                    f"scribebench_job_latency_ms_sum {self.latency_sum:.3f}",
                    "# HELP scribebench_http_requests_total HTTP requests by route and status.",
                    "# TYPE scribebench_http_requests_total counter",
                ]
            )
            for (method, path, status), count in sorted(self.requests.items()):
                lines.append(
                    "scribebench_http_requests_total"
                    f'{{method="{method}",path="{path}",status="{status}"}} {count}'
                )
        return "\n".join(lines) + "\n"
