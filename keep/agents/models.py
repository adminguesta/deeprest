"""DeepREST agent 共享模型 — P17 Phase 1 Day 1。

从老 DeepREST `core/monitors/models.py` 挪过来,字段定义与 P16.1 完全一致(不变量)。

**为什么用 stdlib dataclass 而不是 Pydantic**:Keep 主线 pyproject 锁的是
`pydantic = "^1.10.4"`(V1),而 Pydantic AI 要求 V2。Day 1 暂不引入 pydantic
依赖,Day 2 决定 V1↔V2 兼容方案后再改写。dataclass 风格保证 0 新依赖、0 主线
冲突,Day 2 改写时只需替换装饰器即可。

字段冻结清单(改字段需要走 ChangeAgent 五段闸):
- `CandidateAlert`:监控器送 LLM 评估的候选告警
- `AlertVerdict`:LLM 拍板结果 + ReAct 多步推理(P16.1 锁死字段)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


DeviceKind = Literal["f5", "linux"]


@dataclass(frozen=True)
class CandidateAlert:
    """监控器初步判断"可能要告警"的候选,送 LLM AlertEvaluator 决策。

    `severity_hint` 是规则层建议(critical/high/medium),LLM 可降级 / 升级 / 抑制。
    `recent_samples` 给 LLM 看 N 点历史,做趋势判断。
    """

    device_id: str
    device_kind: DeviceKind
    title: str
    severity_hint: Literal["critical", "high", "medium", "low"]
    metric: str
    value_now: float
    threshold: float | None = None
    recent_samples: tuple[float, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)
    detector: str = "rule"
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AlertVerdict:
    """LLM AlertEvaluator 的判定结果 — 决定要不要真告 + 给运维上下文。

    P16.1 ReAct 字段冻结(reasoning_steps / impact_analysis / runbook_steps /
    related_incidents / historical_pattern)— Day 2 用 Pydantic AI 重写时这些
    字段必须保留,否则破坏 evaluator 的不变量。
    """

    candidate: CandidateAlert
    should_alert: bool
    confidence: Literal["low", "medium", "high"]
    severity: Literal["critical", "high", "medium", "low"]
    reason: str
    suggested_runbook: str | None = None
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fallback_reason: str | None = None
    reasoning_steps: tuple[str, ...] = ()
    impact_analysis: str | None = None
    runbook_steps: tuple[str, ...] = ()
    related_incidents: tuple[str, ...] = ()
    historical_pattern: str | None = None


__all__ = [
    "DeviceKind",
    "CandidateAlert",
    "AlertVerdict",
]
