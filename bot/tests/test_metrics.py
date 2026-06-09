"""Tests for the lightweight metrics registry, instrumentation, and /metrics route."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services import gemini, metrics


class _FakeAPIError(Exception):
    def __init__(self, code=None, status=None, message=""):
        super().__init__(message or f"{code} {status}")
        self.code = code
        self.status = status


def _make_response(text: str):
    r = MagicMock()
    r.text = text
    return r


_SAMPLE = {
    "object_type": "wall",
    "risk_level": "MEDIUM",
    "risk_score": 0.6,
    "temperature_observations": [],
    "problems": [],
    "free_verdict": "ok",
    "premium_analysis": "x",
    "recommendations_brief": "y",
    "recommendations_detailed": [],
    "premium_teaser": "z",
}


@pytest.fixture(autouse=True)
def _clean():
    metrics.reset()
    gemini._client = None
    yield
    metrics.reset()
    gemini._client = None


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("src.services.gemini.asyncio.sleep", new=AsyncMock()) as m:
        yield m


# ── Registry primitives ──────────────────────────────────────────────────────


def test_empty_registry_renders_valid_empty():
    out = metrics.render()
    assert out == ""  # empty registry → valid empty exposition, no crash


def test_counter_increment_and_render():
    metrics.inc("photo_cache_total", {"result": "hit"})
    metrics.inc("photo_cache_total", {"result": "hit"})
    metrics.inc("photo_cache_total", {"result": "miss"})
    out = metrics.render()
    assert "# HELP photo_cache_total" in out
    assert "# TYPE photo_cache_total counter" in out
    assert 'photo_cache_total{result="hit"} 2' in out
    assert 'photo_cache_total{result="miss"} 1' in out


def test_histogram_sum_and_count():
    metrics.observe("gemini_request_duration_seconds", 0.5, {"model": "m"})
    metrics.observe("gemini_request_duration_seconds", 1.5, {"model": "m"})
    out = metrics.render()
    assert "# TYPE gemini_request_duration_seconds histogram" in out
    assert 'gemini_request_duration_seconds_sum{model="m"} 2' in out
    assert 'gemini_request_duration_seconds_count{model="m"} 2' in out


# ── Instrumentation: counters grow on helper calls ──────────────────────────


@pytest.mark.asyncio
async def test_gemini_ok_counts_request_and_duration():
    resp = _make_response(json.dumps(_SAMPLE))
    with patch("src.services.gemini._get") as g:
        g.return_value.aio.models.generate_content = AsyncMock(return_value=resp)
        await gemini.analyze_photo(b"img")
    out = metrics.render()
    assert 'gemini_requests_total{model="' in out
    assert 'outcome="ok"} 1' in out
    assert "gemini_request_duration_seconds_count" in out
    assert 'photo_analysis_total{kind="analyze",outcome="ok"} 1' in out


@pytest.mark.asyncio
async def test_gemini_retry_increments_retries_counter():
    resp = _make_response(json.dumps(_SAMPLE))
    gen = AsyncMock(
        side_effect=[
            _FakeAPIError(code=503, status="UNAVAILABLE"),
            _FakeAPIError(code=503, status="UNAVAILABLE"),
            resp,
        ]
    )
    with patch("src.services.gemini._get") as g:
        g.return_value.aio.models.generate_content = gen
        await gemini.analyze_photo(b"img")
    out = metrics.render()
    assert "gemini_retries_total{model=" in out
    # two transient failures → two retries recorded
    retry_line = [ln for ln in out.splitlines() if ln.startswith("gemini_retries_total")][0]
    assert retry_line.endswith(" 2")
    # succeeded after retries → outcome=retry
    assert 'outcome="retry"} 1' in out


@pytest.mark.asyncio
async def test_gemini_error_counts_error_outcome(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_fallback_model", None)
    gen = AsyncMock(side_effect=_FakeAPIError(code=503, status="UNAVAILABLE"))
    with patch("src.services.gemini._get") as g:
        g.return_value.aio.models.generate_content = gen
        await gemini.analyze_photo(b"img")
    out = metrics.render()
    assert 'outcome="error"} 1' in out
    assert 'photo_analysis_total{kind="analyze",outcome="api_error"} 1' in out


@pytest.mark.asyncio
async def test_gemini_fallback_counts_fallback_outcome(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_fallback_model", "fb-model")
    monkeypatch.setattr(gemini.settings, "gemini_model", "primary-model")
    resp = _make_response(json.dumps(_SAMPLE))

    async def _gen(*, model, contents, config=None):
        if model == "primary-model":
            raise _FakeAPIError(code=503, status="UNAVAILABLE")
        return resp

    with patch("src.services.gemini._get") as g:
        g.return_value.aio.models.generate_content = AsyncMock(side_effect=_gen)
        await gemini.analyze_photo(b"img")
    out = metrics.render()
    assert 'gemini_requests_total{model="fb-model",outcome="fallback"} 1' in out


@pytest.mark.asyncio
async def test_check_quality_reject_counts():
    qc = {"total_score": 30, "verdict": "БРАК", "reason": "blur", "tip": "steady", "object": "wall"}
    resp = _make_response(json.dumps(qc))
    with patch("src.services.gemini._get") as g:
        g.return_value.aio.models.generate_content = AsyncMock(return_value=resp)
        await gemini.check_quality(b"img")
    out = metrics.render()
    assert 'photo_analysis_total{kind="quality",outcome="quality_reject"} 1' in out


# ── Stub mode must not crash and must not increment via network ─────────────


@pytest.mark.asyncio
async def test_stub_mode_no_network_no_crash(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_stub", True)
    with patch("src.services.gemini._get") as g:
        # _get must never be called in stub mode
        await gemini.analyze_photo(b"img")
        await gemini.check_quality(b"img")
        g.assert_not_called()
    # render still valid (no request metrics produced via network path)
    assert metrics.render() == "" or "gemini_requests_total" not in metrics.render()


# ── /metrics route ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_metrics_route_returns_prometheus_text():
    from src.bot import _metrics_handler

    metrics.inc("photo_cache_total", {"result": "hit"})
    resp = await _metrics_handler(MagicMock())
    assert resp.status == 200
    assert resp.content_type == "text/plain"
    assert 'photo_cache_total{result="hit"} 1' in resp.text


@pytest.mark.asyncio
async def test_metrics_route_empty_registry_ok():
    from src.bot import _metrics_handler

    resp = await _metrics_handler(MagicMock())
    assert resp.status == 200
    assert resp.text == ""  # empty but valid, does not crash
