"""DeepREST agent 共享模型 — P17 Phase 1 Day 2 改写为 Pydantic V2 BaseModel。

字段定义与 P16.1 完全一致(冻结清单见类注释)。

**Day 1 起就用 stdlib dataclass 过渡,Day 2 升 V2 后换 BaseModel**:
- frozen=True(对应 dataclass(frozen=True))
- 强类型 + V2 schema 自动生成(`Model.model_json_schema()`)
- LLM 返回 JSON → `AlertVerdict.model_validate_json(text)` 直接解析(替代手写 JSON parse)
- Pydantic AI 暂不引入(决策见 docs/p17-phase-1-day2-decisions.md §A→D)

字段冻结清单(改字段需走 ChangeAgent 五段闸):
- `CandidateAlert`:监控器送 LLM 评估的候选告警
- `AlertVerdict`:LLM 拍板结果 + ReAct 多步推理(P16.1 锁死字段)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


DeviceKind = Literal["f5", "linux"]


class CandidateAlert(BaseModel):
    """监控器初步判断"可能要告警"的候选,送 LLM AlertEvaluator 决策。

    `severity_hint` 是规则层建议(critical/high/medium),LLM 可降级 / 升级 / 抑制。
    `recent_samples` 给 LLM 看 N 点历史,做趋势判断。
    """

    model_config = ConfigDict(frozen=True)

    device_id: str
    device_kind: DeviceKind
    title: str
    severity_hint: Literal["critical", "high", "medium", "low"]
    metric: str
    value_now: float
    threshold: Optional[float] = None
    recent_samples: tuple[float, ...] = ()
    labels: dict[str, str] = Field(default_factory=dict)
    detector: str = "rule"
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AlertVerdict(BaseModel):
    """LLM AlertEvaluator 的判定结果 — 决定要不要真告 + 给运维上下文。

    P16.1 ReAct 字段冻结(reasoning_steps / impact_analysis / runbook_steps /
    related_incidents / historical_pattern)— Day 3 写 evaluator.py 时这些
    字段必须保留,否则破坏 evaluator 的不变量。

    **D 路径设计要点**(不接 pydantic-ai):
    - LLM 返回 JSON 文本 → `AlertVerdict.model_validate_json(text)` 一行解析 + 校验
    - schema 自动生成给 prompt:`AlertVerdict.model_json_schema()`
    """

    model_config = ConfigDict(frozen=True)

    candidate: CandidateAlert
    should_alert: bool
    confidence: Literal["low", "medium", "high"]
    severity: Literal["critical", "high", "medium", "low"]
    reason: str
    suggested_runbook: Optional[str] = None
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    fallback_reason: Optional[str] = None
    # P16.1 — Mini-ReAct 多步推理(LLM 综合后给 SRE 视角的洞察)
    reasoning_steps: tuple[str, ...] = ()
    impact_analysis: Optional[str] = None
    runbook_steps: tuple[str, ...] = ()
    related_incidents: tuple[str, ...] = ()
    historical_pattern: Optional[str] = None


__all__ = [
    "DeviceKind",
    "CandidateAlert",
    "AlertVerdict",
]
