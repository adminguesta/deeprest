"""DeepREST AlertEvaluator — P17 Phase 1 Day 3 实现(D 路径)。

D 路径核心契约:
- LLM 返回 strict JSON 文本 → `AlertVerdict.model_validate_json(text)` 一行解析
- schema 给 prompt 用:`AlertVerdict.model_json_schema()`(由 prompts/evaluator_system 注入)
- 不依赖 pydantic-ai(plan §A→D pivot)
- 直接复用 keep 已锁的 openai==1.37.1(provider-agnostic base_url)

不变量(plan §7):
- L3 LLM 不可达 → 规则兜底,**不抛**(verdict.fallback_reason 标原因)
- L2 audit 只 hash 不存 raw(Day 5-6 task,本文件留 hook)
- L7 这里就是 keep/agents/ 子包,合规

行数预算 < 350(老 DeepREST core/monitors/evaluator.py 是 ~610 行;
减掉 TSDBStore/IncidentStore 直接耦合,把 context 提到调用方传入 = ~250 行)。
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from keep.agents.audit_log import record_decision
from keep.agents.models import AlertVerdict, CandidateAlert
from keep.agents.prompts.evaluator_system import build_system_prompt

log = logging.getLogger(__name__)

SUPPRESSION_WINDOW_SEC = 300  # 同 metric+labels 5 分钟内不重复告(L3 规则兜底用)
LLM_REQUEST_TIMEOUT = 30      # LLM 请求 30s 超时(超时即走 fallback)


# ---- Context 模型(Phase 1 调用方提供,evaluator 不直接耦合 TSDB / IncidentStore)----


class HistoricalDecision(BaseModel):
    """过去 7 天同 metric+labels 的一条决策记录(给 LLM 看 baseline pattern)。"""

    model_config = ConfigDict(frozen=True)

    decided_at: str
    should_alert: bool
    severity: str


class RelatedIncident(BaseModel):
    """关联 incident(同 device 24h active)— 给 LLM 看影响范围。"""

    model_config = ConfigDict(frozen=True)

    incident_id: str
    severity: str
    status: str
    title: Optional[str] = None


class EvaluatorContext(BaseModel):
    """LLM prompt 用的上下文(由 route 层从 Keep DB 拼好后传入)。"""

    model_config = ConfigDict(frozen=True)

    candidate: CandidateAlert
    history: tuple[float, ...] = ()
    last_alert_at: Optional[datetime] = None
    in_business_hours: bool = True
    related_incidents: tuple[RelatedIncident, ...] = ()
    historical_decisions: tuple[HistoricalDecision, ...] = ()


# ---- Prompt 拼接 ----


def _build_user_prompt(ctx: EvaluatorContext) -> str:
    ca = ctx.candidate
    hist_str = ", ".join(f"{v:.2f}" for v in ctx.history[-10:]) or "(无历史)"
    last_alert_str = ctx.last_alert_at.isoformat() if ctx.last_alert_at else "(从未告过)"

    if ctx.related_incidents:
        rel_inc_lines = "\n".join(
            f"  - {r.incident_id} · severity={r.severity} · status={r.status}"
            + (f" · {r.title[:60]}" if r.title else "")
            for r in ctx.related_incidents[:5]
        )
    else:
        rel_inc_lines = "  (无)"

    if ctx.historical_decisions:
        hd = ctx.historical_decisions
        fired = sum(1 for d in hd if d.should_alert)
        hist_dec_str = (
            f"过去 7 天同样告警 {len(hd)} 次:真告 {fired} 次,抑制 {len(hd) - fired} 次。"
        )
    else:
        hist_dec_str = "(过去 7 天没有相同告警的决策记录)"

    return f"""\
## 候选告警
- 设备:{ca.device_id} ({ca.device_kind})
- 标题:{ca.title}
- metric:{ca.metric}
- 当前值:{ca.value_now:.2f}
- 阈值:{ca.threshold if ca.threshold is not None else "—"}
- detector:{ca.detector}
- 触发时间:{ca.detected_at.isoformat()}
- labels:{json.dumps(ca.labels, ensure_ascii=False)}
- severity_hint(规则建议):{ca.severity_hint}

## 历史采样(最近 10 点,升序)
{hist_str}

## 关联 incident(同 device 24h 内 active)
{rel_inc_lines}

## 历史告警 baseline
{hist_dec_str}

## 上下文
- 工作时间(UTC 06-22): {ctx.in_business_hours}
- 上次同 metric 告警时间:{last_alert_str}

请按 system prompt 给的 strict JSON schema 输出 — 必须含 reasoning_steps(≥2 条)
+ impact_analysis(必填)+ runbook_steps(≥2 条)。\
"""


# ---- 规则兜底(L3 不变量)----


def _rule_based_fallback(
    ctx: EvaluatorContext,
    *,
    fallback_reason: str,
) -> AlertVerdict:
    """LLM 不可达时的规则兜底。

    P16.1:即使走规则兜底也填一组**最小可用**的结构化字段(reasoning_steps /
    impact_analysis / runbook_steps),让 UI 不会出现"AI 完全沉默"的空白卡。
    """
    ca = ctx.candidate
    sev = ca.severity_hint
    now = datetime.now(timezone.utc)
    in_suppress = (
        ctx.last_alert_at is not None
        and (now - ctx.last_alert_at).total_seconds() < SUPPRESSION_WINDOW_SEC
    )

    if sev == "critical":
        should = True
    elif sev in ("high", "medium"):
        should = not in_suppress
    else:
        should = False

    reason = (
        f"LLM 不可达走规则兜底:severity_hint={sev}"
        + (f",在 {SUPPRESSION_WINDOW_SEC}s 抑制窗口内 → 抑制" if in_suppress else "")
    )

    reasoning_steps: tuple[str, ...] = (
        f"🔍 当前值 {ca.value_now:.2f}"
        + (f"(阈值 {ca.threshold})" if ca.threshold is not None else ""),
        f"🧠 LLM 不可达({fallback_reason}),只能按 severity_hint={sev} 走规则兜底",
        f"🎯 决定:{'告' if should else '抑制'}"
        + ("(在抑制窗口内)" if in_suppress and not should else ""),
    )
    runbook_steps: tuple[str, ...] = (
        "1. 登录设备人工确认现状(LLM 不可达,缺自动洞察)",
        "2. 联系 SRE 检查 LLM 通道(API key / base_url / 配额)",
    )

    impact_analysis = None
    if ctx.related_incidents:
        ids = ", ".join(r.incident_id for r in ctx.related_incidents[:3])
        impact_analysis = (
            f"该设备目前 {len(ctx.related_incidents)} 条 active incident(如 {ids}),需关注上下游影响"
        )

    historical_pattern = None
    if ctx.historical_decisions:
        fired = sum(1 for d in ctx.historical_decisions if d.should_alert)
        historical_pattern = (
            f"过去 7 天同样告警 {len(ctx.historical_decisions)} 次,真告 {fired} 次"
        )

    return AlertVerdict(
        candidate=ca,
        should_alert=should,
        confidence="low",
        severity=sev,
        reason=reason,
        suggested_runbook=None,
        fallback_reason=fallback_reason,
        reasoning_steps=reasoning_steps,
        impact_analysis=impact_analysis,
        runbook_steps=runbook_steps,
        related_incidents=tuple(r.incident_id for r in ctx.related_incidents),
        historical_pattern=historical_pattern,
    )


# ---- LLM JSON 文本解析(D 路径核心)----


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.+?\})\s*```", re.DOTALL)


def _strip_markdown_fence(text: str) -> str:
    """LLM 时不时违规给 ```json 包裹,容忍一下挖出来。"""
    if not text:
        return text
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1)
    text = text.strip()
    if text.startswith("{"):
        return text
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j > i:
        return text[i : j + 1]
    return text


def _parse_verdict(
    raw_text: str, *, candidate: CandidateAlert
) -> Optional[AlertVerdict]:
    """LLM JSON → AlertVerdict(D 路径:V2 model_validate_json 一行)。

    返回 None 表示解析失败(调用方走 fallback)。LLM 偶尔不回 candidate 字段,
    我们手补回去(candidate 是入参,不该让 LLM 修改 / 幻觉)。
    """
    cleaned = _strip_markdown_fence(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.warning("LLM JSON 解析失败:%s,raw[:200]=%r", e, cleaned[:200])
        return None
    if not isinstance(data, dict):
        return None
    # candidate 入参权威,LLM 别瞎填
    data["candidate"] = candidate.model_dump()
    # 这两个字段 LLM 不该填(prompt 里也禁了),系统接管
    data.pop("decided_at", None)
    data.pop("fallback_reason", None)
    try:
        return AlertVerdict.model_validate(data)
    except ValidationError as e:
        log.warning("AlertVerdict V2 校验失败:%s", e)
        return None


# ---- LLM 调用(provider-agnostic OpenAI-compat)----


def _resolve_llm_config() -> Optional[dict[str, str]]:
    """按优先级:MINIMAX → DEEPSEEK → OPENAI → ANTHROPIC → None(走 fallback)。

    Phase 1 用 env;Phase 2 接 keep secret manager。
    """
    cands = [
        ("OPSMIND_MINIMAX_API_KEY", "OPSMIND_MINIMAX_BASE_URL", "OPSMIND_MINIMAX_MODEL"),
        ("OPSMIND_DEEPSEEK_API_KEY", "OPSMIND_DEEPSEEK_BASE_URL", "OPSMIND_DEEPSEEK_MODEL"),
        ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
    ]
    defaults = {
        "OPSMIND_MINIMAX_BASE_URL": "https://api.minimax.chat/v1",
        "OPSMIND_MINIMAX_MODEL": "MiniMax-Text-01",
        "OPSMIND_DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
        "OPSMIND_DEEPSEEK_MODEL": "deepseek-chat",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_MODEL": "gpt-4o-mini",
    }
    for key_env, base_env, model_env in cands:
        api_key = os.environ.get(key_env)
        if not api_key:
            continue
        return {
            "api_key": api_key,
            "base_url": os.environ.get(base_env, defaults.get(base_env, "")),
            "model": os.environ.get(model_env, defaults.get(model_env, "")),
        }
    return None


async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """OpenAI-compat 异步调用(用 keep 已装的 openai 1.37.1)。"""
    from openai import AsyncOpenAI  # local import 避免 module-level 失败

    cfg = _resolve_llm_config()
    if cfg is None:
        raise RuntimeError("no LLM provider configured (set OPSMIND_MINIMAX_API_KEY etc.)")

    client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    resp = await client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        timeout=LLM_REQUEST_TIMEOUT,
        temperature=0.2,  # decision 类任务低温,减少幻觉
    )
    content = resp.choices[0].message.content or ""
    return content


# ---- 主入口 ----


async def evaluate(
    candidate: CandidateAlert,
    ctx: Optional[EvaluatorContext] = None,
    *,
    _llm_call=None,  # test seam:让 mock 替换 _call_llm
    audit: bool = True,  # 测试可关掉避免污染默认 audit 文件
) -> AlertVerdict:
    """P17 Phase 1 evaluator 主入口。

    用法:
        verdict = await evaluate(candidate, ctx)

    L3 不变量:任何异常 → `_rule_based_fallback`,**永不抛**给调用方。
    L2 不变量:每个决策落 audit hash(`keep.agents.audit_log.record_decision`),
    可用 `audit=False` 关掉(单元测试、批量 backfill 等场景)。
    """
    if ctx is None:
        ctx = EvaluatorContext(candidate=candidate)
    if ctx.candidate != candidate:
        # 入参歧义:以 candidate 为准
        ctx = ctx.model_copy(update={"candidate": candidate})

    system_prompt = build_system_prompt()
    user_prompt = _build_user_prompt(ctx)

    llm_call = _llm_call or _call_llm
    verdict: Optional[AlertVerdict] = None
    try:
        raw = await llm_call(system_prompt, user_prompt)
    except Exception as e:
        log.warning("LLM 调用失败 → fallback:%s", e)
        verdict = _rule_based_fallback(ctx, fallback_reason=f"LLM call error: {e}")
    else:
        parsed = _parse_verdict(raw, candidate=candidate)
        if parsed is None:
            verdict = _rule_based_fallback(
                ctx, fallback_reason="LLM returned unparseable JSON"
            )
        elif (
            len(parsed.reasoning_steps) < 2
            or len(parsed.runbook_steps) < 2
            or not parsed.impact_analysis
        ):
            # P16.1 不变量:reasoning_steps / runbook_steps 至少 2 条,impact_analysis 必填
            log.warning(
                "LLM 返结构不达 P16.1 最小契约 → fallback (reasoning=%d / runbook=%d / impact=%s)",
                len(parsed.reasoning_steps),
                len(parsed.runbook_steps),
                bool(parsed.impact_analysis),
            )
            verdict = _rule_based_fallback(
                ctx, fallback_reason="LLM output failed P16.1 minimum contract"
            )
        else:
            verdict = parsed

    # L2:audit 落档(只 hash,不存 raw)
    if audit:
        try:
            record_decision(candidate, verdict)
        except Exception as e:  # 防御:audit 失败也不影响 verdict 返回
            log.warning("audit record_decision 失败:%s", e)

    return verdict


__all__ = [
    "EvaluatorContext",
    "HistoricalDecision",
    "RelatedIncident",
    "evaluate",
    "_rule_based_fallback",  # 暴露给测试
    "_parse_verdict",        # 暴露给测试
    "build_system_prompt",
]
