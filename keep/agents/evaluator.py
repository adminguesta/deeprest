"""DeepREST AI evaluator — P17 Phase 1 Day 3 实现位。

Day 1 占位 → Day 2 升 V2 BaseModel + 选 D 路径(不接 pydantic-ai,见
docs/p17-phase-1-day2-decisions.md §A→D)→ Day 3 写 evaluator 主体。

D 路径核心契约:
- LLM 返回 JSON 文本 → `AlertVerdict.model_validate_json(text)` 一行解析 + V2 强类型校验
- schema 给 prompt 用:`AlertVerdict.model_json_schema()`
- 不依赖 pydantic-ai 的 retry / streaming / tool calling — Phase 1 不需要
- 直接复用 keep 已锁的 openai==1.37.1 客户端(provider-agnostic 拼 base_url 即可)

Day 3 实现要点(见老 DeepREST `core/monitors/evaluator.py` 600 行,目标减到 < 350):
1. _build_user_prompt:CandidateAlert + 历史上下文 → prompt 文本
2. evaluate():调 LLM,model_validate_json 解析,失败走 _rule_based_fallback
3. L3 不变量:LLM 不可达 → 规则兜底,不抛(verdict.fallback_reason 标原因)
4. L2 不变量:audit hash 写 keep/agents/audit/decisions.jsonl(只 hash 不存 raw)
"""
from __future__ import annotations

from .models import AlertVerdict, CandidateAlert


async def evaluate(candidate: CandidateAlert) -> AlertVerdict:
    """P17 Phase 1 evaluator — Day 3 实现。"""
    raise NotImplementedError(
        "Day 3 实现:见 docs/p17-phase-1-day2-decisions.md §A→D"
    )
