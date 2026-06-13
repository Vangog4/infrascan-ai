"""Lightweight in-process metrics registry (Prometheus text exposition).

No external dependency: a tiny registry of counters + histograms (sum/count only).
The bot is single-process asyncio, so plain int/float increments are safe — no locks.
Metrics live in memory and reset on restart (acceptable for process-level observability).

Usage:
    from src.services import metrics
    metrics.inc("gemini_requests_total", {"model": "x", "outcome": "ok"})
    metrics.observe("gemini_request_duration_seconds", 0.42, {"model": "x"})
    text = metrics.render()  # Prometheus exposition for GET /metrics
"""

from __future__ import annotations

# label-set key → value
_LabelKey = tuple[tuple[str, str], ...]

# Metric definitions: name → (type, help text)
_DEFS: dict[str, tuple[str, str]] = {
    "gemini_requests_total": (
        "counter",
        "Total Gemini generate_content calls by model and outcome",
    ),
    "gemini_retries_total": ("counter", "Total Gemini transient-error retries by model"),
    "gemini_request_duration_seconds": (
        "histogram",
        "Gemini generate_content latency in seconds (sum/count) by model",
    ),
    "photo_analysis_total": (
        "counter",
        "Photo analyze/quality results by kind and outcome",
    ),
    "photo_cache_total": ("counter", "Photo analysis cache lookups by result (hit/miss)"),
    "background_task_failures_total": (
        "counter",
        "Fire-and-forget background task failures by task name (e.g. save_report)",
    ),
}

# counters: name → {labelkey → value}
_counters: dict[str, dict[_LabelKey, float]] = {}
# histograms: name → {labelkey → [sum, count]}
_histograms: dict[str, dict[_LabelKey, list[float]]] = {}


def _key(labels: dict[str, str] | None) -> _LabelKey:
    if not labels:
        return ()
    return tuple(sorted(labels.items()))


def inc(name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
    """Increment a counter metric."""
    bucket = _counters.setdefault(name, {})
    k = _key(labels)
    bucket[k] = bucket.get(k, 0.0) + value


def observe(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    """Record an observation into a histogram metric (tracks sum + count)."""
    bucket = _histograms.setdefault(name, {})
    k = _key(labels)
    agg = bucket.setdefault(k, [0.0, 0.0])
    agg[0] += value
    agg[1] += 1.0


def reset() -> None:
    """Clear all metrics (used in tests)."""
    _counters.clear()
    _histograms.clear()


def _fmt_labels(k: _LabelKey) -> str:
    if not k:
        return ""
    inner = ",".join(f'{name}="{_escape(val)}"' for name, val in k)
    return "{" + inner + "}"


def _escape(val: str) -> str:
    return val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt_value(v: float) -> str:
    # Render whole floats without trailing .0 noise but keep fractions.
    if v == int(v):
        return str(int(v))
    return repr(v)


def render() -> str:
    """Render all metrics in Prometheus text exposition format.

    Empty registry → valid (empty) output; never raises.
    """
    lines: list[str] = []
    for name, (mtype, help_text) in _DEFS.items():
        counter_series = _counters.get(name)
        hist_series = _histograms.get(name)
        if not counter_series and not hist_series:
            continue
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {mtype}")
        if mtype == "counter" and counter_series:
            for k, v in sorted(counter_series.items()):
                lines.append(f"{name}{_fmt_labels(k)} {_fmt_value(v)}")
        elif mtype == "histogram" and hist_series:
            for k, (s, c) in sorted(hist_series.items()):
                lines.append(f"{name}_sum{_fmt_labels(k)} {_fmt_value(s)}")
                lines.append(f"{name}_count{_fmt_labels(k)} {_fmt_value(c)}")
    return "\n".join(lines) + ("\n" if lines else "")
