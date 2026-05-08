"""DeepREST AI evaluator — P17 Phase 1 Day 2-3 实现位。

Day 1 只占位。Day 2-3 用 Pydantic AI Agent 重写老 `core/monitors/evaluator.py`
(~700 行 → 目标 ≤ 400 行)。

Day 1 边界:
- 不引入 pydantic-ai 依赖(Pydantic V1/V2 冲突未决)
- 不实现 evaluate(),Day 2-3 接入
- 留 stub 接口,Day 4 `keep/api/routes/agents.py` 可以提前 import
"""
from __future__ import annotations

from .models import AlertVerdict, CandidateAlert


async def evaluate(candidate: CandidateAlert) -> AlertVerdict:
    """P17 Phase 1 evaluator stub — Day 2-3 用 Pydantic AI 实现。"""
    raise NotImplementedError(
        "Day 2-3 用 Pydantic AI 接入,见 docs/p17-keep-fork-pivot-plan.md §2"
    )
