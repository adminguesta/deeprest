"""DeepREST agent routes — P17 Phase 1 Day 4。

入口:`POST /agents/evaluate`(在 api.py include_router 时挂 prefix="/agents")。

L7 不变量:这是 plan §1 明确允许的"新文件"位置(keep/api/routes/agents.py),
所以 keep/api/api.py 加 1 行 include_router 不算"动主线 业务逻辑"。

Phase 1 简化(Day 4):
- 暂不接 keep AuthVerifier(避免拖 db/tenant/keycloak 依赖,Phase 2 补)
- ctx 只接受 candidate;related_incidents / historical_decisions 留 Phase 2
  接 Keep DB 时再拼(目前传空,evaluator 仍能跑)
- audit hash 留 Day 5-6 任务
"""
from __future__ import annotations

from fastapi import APIRouter

from keep.agents.evaluator import EvaluatorContext, evaluate
from keep.agents.models import AlertVerdict, CandidateAlert

router = APIRouter()


@router.post(
    "/evaluate",
    response_model=AlertVerdict,
    description=(
        "P17 Phase 1 — DeepREST AI evaluator entry. "
        "提交 CandidateAlert,返回 AlertVerdict(P16.1 ReAct 字段全填,LLM 不可达走规则兜底)。"
    ),
)
async def evaluate_alert(payload: CandidateAlert) -> AlertVerdict:
    ctx = EvaluatorContext(candidate=payload)
    return await evaluate(payload, ctx)
