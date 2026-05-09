"""P17 Phase 1 Day 4 — POST /agents/evaluate route 测试。

不真起 keep 完整 app(避免 db / keycloak 依赖),起一个 minimal FastAPI
sub-app 只挂 agents.router 跑 TestClient。验证 D 路径接口契约 + L3 兜底。
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from keep.api.routes.agents import router
from keep.agents import evaluator as evaluator_mod


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/agents", tags=["agents"])
    return app


def _candidate_payload() -> dict:
    return {
        "device_id": "f5-vlab-01",
        "device_kind": "f5",
        "title": "pool member down",
        "severity_hint": "critical",
        "metric": "f5.pool.member.health",
        "value_now": 0.0,
        "threshold": 1.0,
        "recent_samples": [1.0, 0.0, 0.0],
    }


def test_route_returns_alert_verdict_via_fallback(monkeypatch):
    """没配 LLM key → evaluate 走 fallback,route 仍回 200 + AlertVerdict。"""
    # 确保 env 没 key,evaluate 内部会走 fallback
    for k in (
        "OPSMIND_MINIMAX_API_KEY",
        "OPSMIND_DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)

    client = TestClient(_app())
    resp = client.post("/agents/evaluate", json=_candidate_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["should_alert"] is True  # critical → 必告(即使走 fallback)
    assert body["fallback_reason"] is not None
    assert len(body["reasoning_steps"]) >= 2  # P16.1 不变量
    assert len(body["runbook_steps"]) >= 2
    assert body["candidate"]["device_id"] == "f5-vlab-01"


def test_route_uses_evaluator_happy_path(monkeypatch):
    """Mock evaluator.evaluate → 验证 route 透传给 evaluate 的 candidate 正确。"""
    seen = {}

    async def fake_evaluate(candidate, ctx=None, **_kwargs):
        seen["candidate"] = candidate
        seen["ctx"] = ctx
        # 返一个最小合法 verdict
        from keep.agents.models import AlertVerdict

        return AlertVerdict(
            candidate=candidate,
            should_alert=False,
            confidence="high",
            severity="low",
            reason="单点尖刺,趋势已恢复",
            reasoning_steps=("看到一个高点", "之后两点恢复正常"),
            impact_analysis="无业务影响",
            runbook_steps=("无需操作", "持续观察"),
        )

    # 重要:patch 的是 routes/agents.py 里 import 的那个 evaluate 符号
    import keep.api.routes.agents as agents_route
    monkeypatch.setattr(agents_route, "evaluate", fake_evaluate)

    client = TestClient(_app())
    resp = client.post("/agents/evaluate", json=_candidate_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["should_alert"] is False
    assert body["fallback_reason"] is None  # happy path,无 fallback
    assert body["confidence"] == "high"
    # 验证 route 把 payload 完整透传给 evaluator
    assert seen["candidate"].device_id == "f5-vlab-01"
    assert seen["ctx"] is not None
    assert seen["ctx"].candidate.device_id == "f5-vlab-01"


def test_route_rejects_invalid_payload():
    """V2 强类型:severity_hint 不在 Literal 范围 → 422 不进 evaluator。"""
    client = TestClient(_app())
    bad = _candidate_payload()
    bad["severity_hint"] = "urgent"  # 不在 critical/high/medium/low
    resp = client.post("/agents/evaluate", json=bad)
    assert resp.status_code == 422


def test_route_rejects_missing_required_fields():
    client = TestClient(_app())
    resp = client.post("/agents/evaluate", json={"device_id": "x"})
    assert resp.status_code == 422
