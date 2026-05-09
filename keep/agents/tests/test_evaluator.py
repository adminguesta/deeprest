"""P17 Phase 1 Day 3 — evaluator.py 测试。

覆盖:
1. _parse_verdict:strict / markdown 包裹 / 不合法 JSON / V2 schema 校验失败
2. _rule_based_fallback:critical / high suppress / low / 含 ReAct 字段
3. evaluate() e2e:mock LLM 走完整路径 + LLM 异常走 fallback + LLM 输出不达 P16.1 最小契约
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from keep.agents.evaluator import (
    EvaluatorContext,
    HistoricalDecision,
    RelatedIncident,
    _parse_verdict,
    _rule_based_fallback,
    evaluate,
)
from keep.agents.models import AlertVerdict, CandidateAlert


# ---- fixtures ----


def _candidate(severity: str = "high") -> CandidateAlert:
    return CandidateAlert(
        device_id="f5-vlab-01",
        device_kind="f5",
        title="pool member down",
        severity_hint=severity,
        metric="f5.pool.member.health",
        value_now=0.0,
        threshold=1.0,
        recent_samples=(1.0, 0.0, 0.0),
    )


def _good_llm_payload(c: CandidateAlert) -> str:
    """LLM 应该返的 strict JSON。"""
    return json.dumps(
        {
            "candidate": c.model_dump(mode="json"),
            "should_alert": True,
            "confidence": "high",
            "severity": "high",
            "reason": "连续 3 次健康检查失败",
            "reasoning_steps": [
                "🔍 看到 3 个 sample 全 0",
                "🧠 联想到 pool member 进程挂了",
                "🎯 决定真告",
            ],
            "impact_analysis": "影响 vs_hack 的 80 端口业务",
            "runbook_steps": [
                "1. 登 BIG-IP 看 pool member 状态",
                "2. 重启进程 / 切流到备 member",
            ],
            "suggested_runbook": "登 BIG-IP 切流",
        }
    )


# ---- _parse_verdict ----


def test_parse_verdict_strict_json():
    c = _candidate()
    v = _parse_verdict(_good_llm_payload(c), candidate=c)
    assert v is not None
    assert v.should_alert is True
    assert len(v.reasoning_steps) == 3
    assert v.impact_analysis.startswith("影响")


def test_parse_verdict_markdown_wrapped():
    """LLM 经常违规给 ```json ... ``` 包裹。"""
    c = _candidate()
    payload = _good_llm_payload(c)
    wrapped = f"好的,这是结果:\n```json\n{payload}\n```\n希望有用!"
    v = _parse_verdict(wrapped, candidate=c)
    assert v is not None
    assert v.should_alert is True


def test_parse_verdict_invalid_json_returns_none():
    c = _candidate()
    assert _parse_verdict("this is not json", candidate=c) is None


def test_parse_verdict_invalid_severity_returns_none():
    """V2 强类型:severity 不在 Literal 范围 → None(让调用方走 fallback)。"""
    c = _candidate()
    bad = json.dumps(
        {
            "candidate": c.model_dump(mode="json"),
            "should_alert": True,
            "confidence": "high",
            "severity": "urgent",  # 不在 Literal
            "reason": "x",
            "reasoning_steps": ["a", "b"],
            "impact_analysis": "x",
            "runbook_steps": ["1", "2"],
        }
    )
    assert _parse_verdict(bad, candidate=c) is None


def test_parse_verdict_overrides_candidate_and_strips_decided_at():
    """LLM 哪怕乱填 candidate / decided_at,以入参权威 + 系统盖时间戳。"""
    c = _candidate()
    bad_candidate = c.model_copy(update={"device_id": "ATTACKER"}).model_dump(mode="json")
    payload = json.dumps(
        {
            "candidate": bad_candidate,  # LLM 乱填 — 应该被忽略
            "should_alert": True,
            "confidence": "high",
            "severity": "high",
            "reason": "x",
            "reasoning_steps": ["a", "b"],
            "impact_analysis": "x",
            "runbook_steps": ["1", "2"],
            "decided_at": "2020-01-01T00:00:00+00:00",  # LLM 乱填 — 应该忽略
            "fallback_reason": "我编的",  # LLM 乱填 — 应该忽略
        }
    )
    v = _parse_verdict(payload, candidate=c)
    assert v is not None
    assert v.candidate.device_id == "f5-vlab-01"  # 不是 ATTACKER
    assert v.fallback_reason is None
    # decided_at 由系统填,不会是 2020
    assert v.decided_at.year >= 2025


# ---- _rule_based_fallback ----


def test_fallback_critical_always_alerts():
    c = _candidate("critical")
    ctx = EvaluatorContext(candidate=c)
    v = _rule_based_fallback(ctx, fallback_reason="LLM 502")
    assert v.should_alert is True
    assert v.severity == "critical"
    assert v.confidence == "low"
    assert v.fallback_reason == "LLM 502"


def test_fallback_high_in_suppression_window_suppresses():
    c = _candidate("high")
    just_now = datetime.now(timezone.utc) - timedelta(seconds=60)  # 1min 前刚告
    ctx = EvaluatorContext(candidate=c, last_alert_at=just_now)
    v = _rule_based_fallback(ctx, fallback_reason="timeout")
    assert v.should_alert is False  # 5min 抑制窗内
    assert "抑制窗口" in v.reason


def test_fallback_low_suppresses():
    c = _candidate("low")
    ctx = EvaluatorContext(candidate=c)
    v = _rule_based_fallback(ctx, fallback_reason="x")
    assert v.should_alert is False


def test_fallback_includes_react_fields_p16_1():
    """L3 + P16.1:即使兜底也要给 ReAct 结构化字段(reasoning_steps + runbook_steps + impact)。"""
    c = _candidate("critical")
    ctx = EvaluatorContext(
        candidate=c,
        related_incidents=(
            RelatedIncident(
                incident_id="INC-100", severity="high", status="firing", title="vs_hack down"
            ),
        ),
        historical_decisions=(
            HistoricalDecision(decided_at="2026-05-01T00:00:00+00:00", should_alert=True, severity="high"),
            HistoricalDecision(decided_at="2026-05-02T00:00:00+00:00", should_alert=False, severity="low"),
        ),
    )
    v = _rule_based_fallback(ctx, fallback_reason="LLM 不可达")
    assert len(v.reasoning_steps) >= 2
    assert len(v.runbook_steps) >= 2
    assert v.impact_analysis is not None
    assert "INC-100" in v.impact_analysis
    assert v.historical_pattern is not None
    assert "INC-100" in v.related_incidents


# ---- evaluate() e2e with mocked LLM ----


@pytest.mark.asyncio
async def test_evaluate_e2e_happy_path():
    c = _candidate("high")
    ctx = EvaluatorContext(candidate=c)

    async def fake_llm(system, user):
        # 验证 system prompt 包含 schema(就是 D 路径核心)
        assert "AlertVerdict JSON schema" in system
        assert "reasoning_steps" in system
        # 验证 user prompt 包含候选告警
        assert "f5-vlab-01" in user
        assert "f5.pool.member.health" in user
        return _good_llm_payload(c)

    v = await evaluate(c, ctx, _llm_call=fake_llm)
    assert v.fallback_reason is None  # LLM 成功路径,fallback_reason 应空
    assert v.should_alert is True
    assert len(v.reasoning_steps) == 3
    assert v.confidence == "high"


@pytest.mark.asyncio
async def test_evaluate_llm_exception_falls_back():
    c = _candidate("critical")
    ctx = EvaluatorContext(candidate=c)

    async def boom(system, user):
        raise TimeoutError("LLM 超时")

    v = await evaluate(c, ctx, _llm_call=boom)
    # L3 不抛,走 fallback
    assert v.fallback_reason is not None
    assert "LLM call error" in v.fallback_reason
    assert v.should_alert is True  # critical 必告
    assert v.confidence == "low"


@pytest.mark.asyncio
async def test_evaluate_llm_returns_garbage_falls_back():
    c = _candidate("medium")
    ctx = EvaluatorContext(candidate=c)

    async def garbage(system, user):
        return "hi I'm just chatting, no JSON"

    v = await evaluate(c, ctx, _llm_call=garbage)
    assert v.fallback_reason == "LLM returned unparseable JSON"


@pytest.mark.asyncio
async def test_evaluate_llm_violates_p16_1_minimum_falls_back():
    """P16.1 不变量:reasoning_steps < 2 条 / impact_analysis 缺 → 走 fallback。"""
    c = _candidate("high")
    ctx = EvaluatorContext(candidate=c)

    async def thin(system, user):
        return json.dumps(
            {
                "candidate": c.model_dump(mode="json"),
                "should_alert": True,
                "confidence": "high",
                "severity": "high",
                "reason": "x",
                "reasoning_steps": ["just one"],   # < 2 条
                "impact_analysis": "",             # 空
                "runbook_steps": ["a"],            # < 2 条
            }
        )

    v = await evaluate(c, ctx, _llm_call=thin)
    assert v.fallback_reason == "LLM output failed P16.1 minimum contract"


@pytest.mark.asyncio
async def test_evaluate_uses_default_context_when_none():
    """没传 ctx 也能跑(默认 EvaluatorContext)。"""
    c = _candidate("low")
    v = await evaluate(c, _llm_call=None)  # 没 LLM 配置 → fallback
    # 没配 LLM → fallback,low 抑制
    assert v.fallback_reason is not None
    assert v.should_alert is False
