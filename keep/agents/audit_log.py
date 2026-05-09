"""DeepREST agent audit log — P17 Phase 1 Day 5(L2 不变量)。

**L2 不变量**(plan §7):audit 只存 hash,**不存 raw evidence**。
- 不写 LLM 原始 prompt / response
- 不写 reasoning_steps 文字内容(LLM 可能泄敏感信息)
- 只写 candidate+verdict 的 SHA-256 hash + **决策结果摘要**(should_alert /
  severity / 是否走 fallback)— 用于事后审计 / 决策回放统计

落档目录默认 `keep/agents/audit/decisions.jsonl`(append-only),环境变量
`OPSMIND_AUDIT_LOG_PATH` 可覆盖(测试 / 多 tenant 场景)。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from keep.agents.models import AlertVerdict, CandidateAlert

log = logging.getLogger(__name__)

DEFAULT_AUDIT_DIR = Path(__file__).parent / "audit"
DEFAULT_AUDIT_FILE = DEFAULT_AUDIT_DIR / "decisions.jsonl"


def _resolve_audit_path() -> Path:
    env = os.environ.get("OPSMIND_AUDIT_LOG_PATH")
    if env:
        return Path(env)
    return DEFAULT_AUDIT_FILE


def _hash_payload(candidate: CandidateAlert, verdict: AlertVerdict) -> str:
    """计算 candidate + verdict 关键决策字段的 SHA-256(L2:hash 不可逆)。

    包含:device_id / metric / value_now / detected_at + should_alert /
    severity / confidence / fallback_reason 是否。
    **不**包含 reasoning_steps / runbook_steps / impact_analysis 文字
    (避免泄敏感)。
    """
    payload = {
        "device_id": candidate.device_id,
        "metric": candidate.metric,
        "value_now": candidate.value_now,
        "detected_at": candidate.detected_at.isoformat(),
        "should_alert": verdict.should_alert,
        "severity": verdict.severity,
        "confidence": verdict.confidence,
        "is_fallback": verdict.fallback_reason is not None,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def record_decision(
    candidate: CandidateAlert,
    verdict: AlertVerdict,
    *,
    audit_path: Path | None = None,
) -> dict[str, Any]:
    """落 audit 日志 + 返写入的记录(供测试断言)。

    返回 dict 仅供测试 / 调用方 inspection;持久层只追加一行 JSON 到 jsonl 文件。
    """
    path = audit_path or _resolve_audit_path()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "hash": _hash_payload(candidate, verdict),
        "device_id": candidate.device_id,        # 设备 ID 不算敏感(运维侧)
        "device_kind": candidate.device_kind,
        "metric": candidate.metric,
        "should_alert": verdict.should_alert,
        "severity": verdict.severity,
        "confidence": verdict.confidence,
        "is_fallback": verdict.fallback_reason is not None,
        # NOTE: 故意不写 reasoning_steps / runbook_steps / impact_analysis /
        # reason 等文字字段(L2 不存 raw evidence)
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        # L3 精神:audit 落盘失败也不抛 — 决策已经做了,日志丢了 SRE 能找回
        log.warning("audit log 落盘失败 path=%s err=%s", path, e)
    return record


__all__ = [
    "record_decision",
    "DEFAULT_AUDIT_FILE",
    "_hash_payload",  # 暴露给测试
]
