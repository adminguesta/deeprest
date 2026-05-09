"""P17 Phase 1 Day 5 — audit_log.py 测试(L2 不变量)。

L2 不变量验证:audit 日志**只存 hash**,**不存 raw evidence**。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from keep.agents.audit_log import _hash_payload, record_decision
from keep.agents.evaluator import evaluate
from keep.agents.models import AlertVerdict, CandidateAlert


def _candidate() -> CandidateAlert:
    return CandidateAlert(
        device_id="f5-vlab-01",
        device_kind="f5",
        title="pool member down",
        severity_hint="high",
        metric="f5.pool.member.health",
        value_now=0.0,
        threshold=1.0,
    )


def _verdict(c: CandidateAlert, *, sensitive_text: str = "") -> AlertVerdict:
    return AlertVerdict(
        candidate=c,
        should_alert=True,
        confidence="high",
        severity="high",
        reason=f"敏感解释 {sensitive_text}",
        reasoning_steps=(
            f"看到敏感证据 {sensitive_text}",
            "联想到上下游",
            "决定告",
        ),
        impact_analysis=f"内部业务 {sensitive_text}",
        runbook_steps=("登设备", "重启 pool"),
    )


def test_hash_is_stable_for_same_input():
    c = _candidate()
    v = _verdict(c)
    assert _hash_payload(c, v) == _hash_payload(c, v)


def test_hash_changes_when_decision_changes():
    c = _candidate()
    v1 = _verdict(c)
    v2 = AlertVerdict(**{**v1.model_dump(), "should_alert": False})
    assert _hash_payload(c, v1) != _hash_payload(c, v2)


def test_record_decision_writes_jsonl(tmp_path: Path):
    c = _candidate()
    v = _verdict(c, sensitive_text="VPN-PROD-CRED-12345")
    audit_path = tmp_path / "decisions.jsonl"

    rec = record_decision(c, v, audit_path=audit_path)

    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    on_disk = json.loads(lines[0])
    assert on_disk == rec  # in-memory 和 落盘等价


def test_record_decision_NO_RAW_evidence(tmp_path: Path):
    """L2 核心:reasoning_steps / runbook_steps / reason / impact_analysis 文字
    **绝不**进 audit 文件(可能含敏感内部信息)。"""
    c = _candidate()
    sensitive = "VPN-PROD-CRED-12345"
    v = _verdict(c, sensitive_text=sensitive)
    audit_path = tmp_path / "decisions.jsonl"

    record_decision(c, v, audit_path=audit_path)
    raw = audit_path.read_text(encoding="utf-8")

    assert sensitive not in raw, f"L2 违反:敏感原文 {sensitive!r} 进了 audit 文件"
    # reason 字段也不应该进
    assert "敏感解释" not in raw
    # 兜底:reasoning_steps 文字也不应该进
    assert "联想到上下游" not in raw

    # 但应该有 hash + 决策摘要
    parsed = json.loads(raw.splitlines()[0])
    assert "hash" in parsed and len(parsed["hash"]) == 64  # SHA-256 hex
    assert parsed["should_alert"] is True
    assert parsed["severity"] == "high"
    assert parsed["is_fallback"] is False


def test_record_decision_appends(tmp_path: Path):
    c = _candidate()
    v = _verdict(c)
    audit_path = tmp_path / "decisions.jsonl"
    record_decision(c, v, audit_path=audit_path)
    record_decision(c, v, audit_path=audit_path)
    record_decision(c, v, audit_path=audit_path)
    assert len(audit_path.read_text().splitlines()) == 3


def test_record_decision_swallows_io_error(tmp_path: Path, monkeypatch):
    """L3 精神:audit 落盘失败不该抛(决策已经做了)。"""
    c = _candidate()
    v = _verdict(c)

    def fail_open(self, *a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "open", fail_open)
    # 不抛即 pass
    rec = record_decision(c, v, audit_path=tmp_path / "d.jsonl")
    assert "hash" in rec  # 仍然返记录(in-memory)


@pytest.mark.asyncio
async def test_evaluate_writes_audit_when_audit_true(tmp_path: Path, monkeypatch):
    """evaluate() audit=True(默认)走 record_decision,环境变量切到临时文件。"""
    audit_path = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("OPSMIND_AUDIT_LOG_PATH", str(audit_path))

    c = _candidate()

    async def boom(system, user):
        raise TimeoutError("LLM 超时")

    v = await evaluate(c, _llm_call=boom)  # audit 默认 True
    assert v.fallback_reason is not None

    assert audit_path.exists()
    rec = json.loads(audit_path.read_text().splitlines()[0])
    assert rec["device_id"] == "f5-vlab-01"
    assert rec["is_fallback"] is True
    # L2 不变量:fallback_reason 文字不进 audit
    assert "LLM call error" not in audit_path.read_text()


@pytest.mark.asyncio
async def test_evaluate_audit_false_skips_log(tmp_path: Path, monkeypatch):
    audit_path = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("OPSMIND_AUDIT_LOG_PATH", str(audit_path))

    c = _candidate()

    async def boom(system, user):
        raise TimeoutError("x")

    await evaluate(c, _llm_call=boom, audit=False)
    assert not audit_path.exists()
