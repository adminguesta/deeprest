"""P17 Day 1 — 最小 smoke test,确认 keep/agents/models.py 字段冻结契约。"""
from __future__ import annotations

from keep.agents.models import AlertVerdict, CandidateAlert


def test_candidate_alert_minimal_construct():
    c = CandidateAlert(
        device_id="f5-vlab-01",
        device_kind="f5",
        title="pool member down",
        severity_hint="high",
        metric="f5.pool.member.health",
        value_now=0.0,
    )
    assert c.detector == "rule"
    assert c.recent_samples == ()
    assert c.threshold is None


def test_alert_verdict_react_fields_default_empty():
    """P16.1 不变量:ReAct 字段默认空,但必须存在。"""
    c = CandidateAlert(
        device_id="linux-host-200",
        device_kind="linux",
        title="load high",
        severity_hint="medium",
        metric="linux.load.1m",
        value_now=12.5,
    )
    v = AlertVerdict(
        candidate=c,
        should_alert=True,
        confidence="medium",
        severity="medium",
        reason="负载持续偏高 5 分钟",
    )
    assert v.reasoning_steps == ()
    assert v.runbook_steps == ()
    assert v.related_incidents == ()
    assert v.impact_analysis is None
    assert v.historical_pattern is None
    assert v.fallback_reason is None
