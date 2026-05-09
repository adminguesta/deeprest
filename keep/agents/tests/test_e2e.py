"""P17 Phase 1 Day 6 — e2e 串测:HTTP POST /agents/evaluate → audit jsonl 落档。

这个 test 是 plan §2 Phase 1 验收口径"e2e:Keep webhook 收一条假 alert →
触发 /api/agents/evaluate → JSON 落档" 的核心证据。

不真起 keep 完整 backend(避免 db / keycloak 依赖),只挂 agents.router 到
minimal FastAPI sub-app + monkeypatch audit 路径到 tmp_path。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from keep.api.routes.agents import router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/agents", tags=["agents"])
    return app


# 模拟 Keep webhook 收到的告警 payload(F5 pool member down 场景)
KEEP_WEBHOOK_FIXTURE = {
    "device_id": "f5-vlab-prod-01",
    "device_kind": "f5",
    "title": "BIG-IP pool member 192.168.90.188:80 went down",
    "severity_hint": "critical",
    "metric": "f5.pool.member.health",
    "value_now": 0.0,
    "threshold": 1.0,
    "recent_samples": [1.0, 1.0, 0.0, 0.0, 0.0],
    "labels": {"pool": "pool_hack", "vs": "vs_hack"},
    "detector": "rule",
}


def test_e2e_http_post_to_audit_jsonl(tmp_path: Path, monkeypatch):
    """plan §2 Phase 1 验收:Keep webhook → POST /agents/evaluate → audit 落档。

    步骤:
      1. 模拟 Keep 收到一条 alert,POST 到 /agents/evaluate
      2. 验证 200 + AlertVerdict 含完整 P16.1 ReAct 字段
      3. 验证 keep/agents/audit/decisions.jsonl 落了一行 hash + 决策摘要
      4. 验证 L2 不变量:audit 文件不含 reasoning_steps / runbook_steps 文字
    """
    audit_path = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("OPSMIND_AUDIT_LOG_PATH", str(audit_path))
    # 强制走 fallback(不依赖外部 LLM)
    for k in (
        "OPSMIND_MINIMAX_API_KEY",
        "OPSMIND_DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)

    client = TestClient(_app())
    resp = client.post("/agents/evaluate", json=KEEP_WEBHOOK_FIXTURE)

    # ── HTTP 层契约 ──
    assert resp.status_code == 200
    body = resp.json()
    assert body["should_alert"] is True       # critical → 必告
    assert body["fallback_reason"] is not None  # 没 LLM,走 fallback
    # P16.1:即使 fallback 也要有 ReAct 结构化字段
    assert len(body["reasoning_steps"]) >= 2
    assert len(body["runbook_steps"]) >= 2
    # 入参原样回传(L4 精神:tool 不该改入参)
    assert body["candidate"]["device_id"] == "f5-vlab-prod-01"
    assert body["candidate"]["labels"] == {"pool": "pool_hack", "vs": "vs_hack"}

    # ── audit 落档(L2 不变量)──
    assert audit_path.exists(), "audit jsonl 应该被自动写入"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    # 决策摘要字段(允许)
    assert rec["device_id"] == "f5-vlab-prod-01"
    assert rec["metric"] == "f5.pool.member.health"
    assert rec["should_alert"] is True
    assert rec["severity"] == "critical"
    assert rec["is_fallback"] is True
    assert len(rec["hash"]) == 64  # SHA-256 hex

    # L2 关键断言:audit 文件**绝不**含 raw evidence(reasoning_steps 等)
    raw_audit_text = audit_path.read_text()
    assert "登录设备人工确认" not in raw_audit_text       # fallback runbook 文字
    assert "联系 SRE" not in raw_audit_text              # fallback runbook 文字
    assert "LLM 不可达" not in raw_audit_text             # fallback reason 文字


def test_e2e_multiple_alerts_audit_appends(tmp_path: Path, monkeypatch):
    """多条 alert 进来,audit jsonl 顺序追加,每条独立 hash。"""
    audit_path = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("OPSMIND_AUDIT_LOG_PATH", str(audit_path))
    for k in ("OPSMIND_MINIMAX_API_KEY", "OPSMIND_DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    client = TestClient(_app())

    # 3 条不同设备的 alert
    payloads = [
        {**KEEP_WEBHOOK_FIXTURE, "device_id": "f5-01"},
        {**KEEP_WEBHOOK_FIXTURE, "device_id": "f5-02", "severity_hint": "high"},
        {**KEEP_WEBHOOK_FIXTURE, "device_id": "linux-host-200", "device_kind": "linux",
         "metric": "linux.load.1m", "severity_hint": "low"},
    ]
    for p in payloads:
        r = client.post("/agents/evaluate", json=p)
        assert r.status_code == 200

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    recs = [json.loads(l) for l in lines]
    # 三条记录的 hash 各不相同(不同 device → 不同决策上下文)
    assert len({r["hash"] for r in recs}) == 3
    # 顺序 = 请求顺序
    assert [r["device_id"] for r in recs] == ["f5-01", "f5-02", "linux-host-200"]
    # severity_hint=low 在 fallback 下被抑制
    assert recs[2]["should_alert"] is False
