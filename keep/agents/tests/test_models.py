"""P17 Day 2 — keep/agents/models.py V2 BaseModel 契约 smoke test。

Day 1 用 stdlib dataclass 过渡,Day 2 升级到 Pydantic V2 BaseModel(D 路径)。
新增覆盖:V2 schema 生成 + JSON round-trip(LLM 返回 JSON 直接 model_validate_json)。
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

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


def test_models_are_frozen():
    """V2 frozen=True:不允许 mutate(对应老 dataclass(frozen=True))"""
    c = CandidateAlert(
        device_id="x",
        device_kind="f5",
        title="t",
        severity_hint="low",
        metric="m",
        value_now=1.0,
    )
    with pytest.raises(ValidationError):
        c.title = "mutated"  # type: ignore[misc]


def test_alert_verdict_json_roundtrip():
    """D 路径核心契约:LLM 返回 JSON → model_validate_json 一行解析 + 校验。"""
    c = CandidateAlert(
        device_id="f5-vlab-01",
        device_kind="f5",
        title="pool member down",
        severity_hint="high",
        metric="f5.pool.member.health",
        value_now=0.0,
        recent_samples=(1.0, 0.0, 0.0),
    )
    v = AlertVerdict(
        candidate=c,
        should_alert=True,
        confidence="high",
        severity="high",
        reason="连续 3 次健康检查失败",
        reasoning_steps=("看到 3 个 sample 全 0", "联想到 member 进程挂了", "决定真告"),
        runbook_steps=("登 BIG-IP", "重启 pool member", "验证健康检查"),
        impact_analysis="影响 vs_hack 的 80 端口业务",
    )
    # V2 序列化
    payload = v.model_dump_json()
    assert isinstance(payload, str)
    # V2 反序列化(LLM 返 JSON 时走这条路径)
    v2 = AlertVerdict.model_validate_json(payload)
    assert v2.should_alert is True
    assert len(v2.reasoning_steps) == 3
    assert v2.impact_analysis == "影响 vs_hack 的 80 端口业务"


def test_alert_verdict_schema_for_llm_prompt():
    """D 路径:把 schema 给 LLM prompt 用,确保 schema 包含所有 P16.1 ReAct 字段。"""
    schema = AlertVerdict.model_json_schema()
    props = schema["properties"]
    # P16.1 锁死的 ReAct 字段必须在 schema 里
    for required in (
        "reasoning_steps",
        "impact_analysis",
        "runbook_steps",
        "related_incidents",
        "historical_pattern",
        "fallback_reason",
        "should_alert",
        "confidence",
        "severity",
        "reason",
    ):
        assert required in props, f"missing schema field: {required}"


def test_invalid_severity_rejected():
    """V2 强类型:Literal 之外的值被拒(LLM 幻觉的兜底)。"""
    c = CandidateAlert(
        device_id="x",
        device_kind="f5",
        title="t",
        severity_hint="low",
        metric="m",
        value_now=1.0,
    )
    with pytest.raises(ValidationError):
        AlertVerdict(
            candidate=c,
            should_alert=True,
            confidence="high",
            severity="urgent",  # type: ignore[arg-type]  # 不在 Literal 里
            reason="x",
        )
