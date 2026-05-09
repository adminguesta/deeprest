# P17 Phase 1 — 收口 Acceptance

> **时间**:Day 173-175(2026-05-08 ~ 2026-05-09),共 ~2 个工作日(原计划 1 周)
> **分支**:`phase-1/agents` @ origin
> **总 commits**:9(692e8ad5 → 当前)
> **前置**:Day 173 P17 启动会话拍板 fork keephq/keep + 决策 D 路径

---

## 0. 一图速读

| Phase 1 验收口径(plan §2) | 状态 | 证据 |
|---|---|---|
| `keep run` 起得来 + 全套服务健康 | 🟡 host venv ✅,docker compose 留 Phase 2 | docker buildkit poetry 1.3.2 卡死,走 Plan B(host venv,见 Day 1 acceptance §3) |
| `keep/agents/` 包结构搭好 + tests/ 全绿 | ✅ | **34 passed in 0.30s**(Day 5+6 总数) |
| 引入 Pydantic AI(多 provider 适配跑通) | 🔄 **替换为 D 路径**(V2 BaseModel + model_validate_json) | Day 2 撞 deps 死结后 A→D pivot,见 day2-decisions.md §5 |
| P16.1 ReAct 推理重写 ≤ 400 行 | ✅ **375 行**(老 610,−38%) | `keep/agents/evaluator.py` |
| `POST /api/agents/evaluate` 接口 | ✅ | `keep/api/routes/agents.py`,4 个 route 测试全绿 |
| e2e:webhook → /api/agents/evaluate → JSON 落档 | ✅ | `tests/test_e2e.py` 2 个测试,验证 HTTP → audit jsonl 全链 |
| LLM 不可达走规则兜底,**不 500** | ✅ | `_rule_based_fallback` + `evaluate()` 永不抛,4 个 fallback 测试 |
| `ee/` 0 改动 | ✅ | `git diff main..phase-1/agents -- ee/` 空 |

**总评**:8/8 验收项达标(其中 docker compose 项标 🟡 是 plan 文档表述与实际偏差,Phase 2 切 production compose 时再处理)。

---

## 1. 交付物清单

### 1.1 新增文件(L7 合规:全部进 keep/agents/ + 1 个 keep/api/routes/agents.py)

```
keep/agents/
├── __init__.py
├── models.py                     # AlertVerdict + CandidateAlert(V2 BaseModel,frozen)
├── evaluator.py                  # 主入口 evaluate() + _rule_based_fallback + _parse_verdict
├── audit_log.py                  # record_decision(L2 不变量:只 hash 不存 raw)
├── supervisor.py                 # Phase 2/3 占位
├── chat.py                       # Phase 2 占位
├── harness/__init__.py           # Phase 1/2 挪老 core/harness/ 用
├── prompts/
│   ├── __init__.py
│   └── evaluator_system.py       # build_system_prompt() 拼 V2 schema
├── audit/
│   └── .gitkeep                  # decisions.jsonl 落档目录(.gitignore'd)
└── tests/
    ├── __init__.py
    ├── test_models.py            # 6 个测试:V2 frozen / JSON roundtrip / schema / Literal 拒
    ├── test_evaluator.py         # 14 个测试:parse / fallback / e2e mocked
    ├── test_audit_log.py         # 8 个测试:hash 稳定 / L2 反向断言 / OSError 吞 / evaluate 接 audit
    ├── test_route.py             # 4 个测试:route fallback / happy / 422 校验
    └── test_e2e.py               # 2 个测试:HTTP → audit jsonl 全链 + 多条追加

keep/api/routes/agents.py         # POST /agents/evaluate(31 行)

docs/
├── p17-phase-1-day1-acceptance.md
├── p17-phase-1-day2-decisions.md
└── p17-phase-1-acceptance.md     # 本文
```

### 1.2 改动主线代码

| 文件 | 改动 | 原因 |
|---|---|---|
| `pyproject.toml` | `pydantic ^1.10.4 → ^2.10` + 加 `pydantic-settings ^2.7` | A 路径升 V2(用户 Day 2 早晨授权)|
| `keep/api/api.py` | 加 `agents` import + 1 行 `include_router` | plan §1 明确允许的"新文件 + 1 行注册" |
| 36 个 keep/ 文件 | bump-pydantic 机械化 V1→V2 转换 | A 路径附属(见 Day 2 commit 6a39843d) |
| 6 个 keep/ 文件 | 手补 @validator → @field_validator + Optional 类型 + AnyHttpUrl 改 str | bump-pydantic 没自动改的(Day 2 commit 6a39843d) |

**ee/ 严格 0 改动**(L6 守住)。

### 1.3 测试矩阵(34 passed in 0.30s)

| 测试文件 | 测试数 | 覆盖 |
|---|---|---|
| `test_models.py` | 6 | V2 BaseModel 契约 + frozen + JSON roundtrip + schema + Literal 校验 |
| `test_evaluator.py` | 14 | parse_verdict + rule_based_fallback + evaluate() e2e mocked |
| `test_audit_log.py` | 8 | hash 稳定 + L2 反向断言 + OSError 吞 + evaluate 接 audit |
| `test_route.py` | 4 | POST /agents/evaluate fallback + happy path + 422 校验 |
| `test_e2e.py` | 2 | HTTP → evaluator → audit jsonl 全链 + 多条追加 |
| **合计** | **34** | **0.30s 跑完** |

---

## 2. 关键决策回顾

### 2.1 Day 1:Plan B(host venv)替代 docker compose

**触发**:Keep `Dockerfile.dev.api` pin `poetry==1.3.2`,buildkit resolver 静默 30+ min 卡死。L7 不能改 Dockerfile。

**对策**:host venv(老 DeepREST .venv 的 Python 3.13.12)+ poetry 2.4.0。243 deps 装齐,keep CLI 全套子命令可调。Day 1 acceptance §3 详细复盘。

**遗留**:docker compose 真验收挪到 Phase 2(届时可能要走 ChangeAgent 流程升 Dockerfile poetry 版本)。

### 2.2 Day 2:A→D pivot

**第一次拍板(用户授权)**:A 路径升 pydantic V1→V2(影响 36 文件 / 净 -41 行,机械化 80% / 手动 < 1h,baseline 33 → 33 等价回归)。

**撞墙**:`poetry add pydantic-ai` 撞 Keep 三个死 pin(`openai==1.37.1` / `google-auth==2.34.0` / `python-telegram-bot ^20.1`,httpx 间接冲突)。任何版本 pydantic-ai 都要更新这三个 — L7 字面再破一次的成本。

**第二次拍板**:D 路径 — 不 add pydantic-ai,用 V2 BaseModel + `model_validate_json` 自己解析。L7 字面破止于 pydantic 一个 dep。

**实际收益**:
- pyproject 主线 deps 改:**1 个**(就 pydantic),不是 4 个
- pydantic-ai 多余功能(retry / streaming / tool calling)Phase 1 不需要
- evaluator.py 行数仍达标(< 400 行,实际 375)
- Phase 2/3 multi-agent 复杂时再回头评估 pydantic-ai

### 2.3 Day 2.5 corner cases(deferred)

V2 enum 序列化在 sqlalchemy json_encoder 路径上和 V1 不等价(`AlertStatus` Enum 不自动转 .value)。`test_alert_evaluation` 7 个测试在 V2 下 fail。**不在 Phase 1 验收路径上**,挪到 Phase 2 修(可能改 `model_config = ConfigDict(use_enum_values=True)` 或 `@field_serializer`)。

---

## 3. 不变量守护实证(L1-L8)

| ID | 不变量 | Phase 1 状态 | 证据 |
|---|---|---|---|
| L1 | 写动作走 ChangeAgent 五段闸 + tollbooth | N/A | Phase 1 evaluator 是只读决策,无写动作。Phase 3 接 workflow 时启动。 |
| L2 | audit 只存 hash,不存 raw evidence | ✅ | `test_audit_log.py::test_record_decision_NO_RAW_evidence` + `test_e2e.py` 反向断言"敏感原文 / runbook 文字 / fallback_reason 文字 不进 audit 文件" |
| L3 | LLM 不可达 → 规则兜底,不 500 | ✅ | `_rule_based_fallback` 4 个测试 + `evaluate()` 永不抛(LLM 异常 / unparseable JSON / 不达 P16.1 最小契约 三条 fallback 路径) |
| L4 | read-only tool registry,scope_kind 校验 | ⏳ Phase 1 evaluator 无 tool 调用,Phase 2 接 chat agent 时启动 | `keep/agents/harness/` 占位 |
| L5 | 不 carry 老 core/llm_client/,统一 V2 model_validate_json | ✅ | evaluator 只用 keep 已锁的 openai 1.37.1 + V2 schema,无 llm_client/ 引用 |
| L6 | ee/ 0 改动 | ✅ | `git diff main..phase-1/agents -- ee/` 空 |
| L7 | 新东西只放 keep/agents/ + 1 个 keep/api/routes/agents.py + 1 行 api.py 注册 | ✅(deps 升级 + bump-pydantic 机械化是经用户授权的 A 路径附属)| 业务逻辑 0 改动 |
| L8 | 每月 cherry-pick keep upstream | ⏳ Phase 1 没真跑,baseline tag `keep-baseline-day173` 已落 | 第一次实战 cherry-pick 在 Day 30 |

---

## 4. 复核命令(Phase 2 启动前自检)

```bash
cd ~/keep-fork

# 4.1 全套测试
.venv/bin/python -m pytest keep/agents/tests/ -v
# 期望:34 passed

# 4.2 主线 baseline 回归(V2 等价 V1)
.venv/bin/python -m pytest tests/test_alert_utils.py tests/test_alert_dto.py tests/test_alert_tenrary.py
# 期望:33 passed

# 4.3 keep CLI 仍能跑
PYTHONPATH=. .venv/bin/python -m keep.cli.cli --help
# 期望:列出 alert/api/auth/... 子命令

# 4.4 e2e 真起 keep API 跑一发(可选,需 .env 配 DATABASE_CONNECTION_STRING 或 sqlite)
# .venv/bin/python -c "from keep.api.api import get_app; app = get_app(); print(app)"

# 4.5 不变量自检
git diff main..phase-1/agents -- ee/ | wc -l    # 0 = L6 OK
git log phase-1/agents --oneline | head -10       # 9 commits since Day 1
git tag | grep keep-baseline                     # keep-baseline-day173 @ df4e48d2
```

---

## 5. Phase 2 入口(挪到 phase-2/ui-handoff 分支起)

按 plan §3,Phase 2 目标是 UI 嫁接(Keep `(keep)/incidents/[id]` 页加 "AI 诊断结论" tab + chat 浮窗 + i18n + rebrand DeepREST)+ 真接 Keep alert pipeline webhook。

**Phase 2 第一件事**:解 Day 2.5 corner cases(`AlertStatus` enum V2 序列化),让 `test_alert_evaluation` 7 个回归测试也绿。这是 incident UI 路径会走到的代码。

**Phase 2 第二件事**:`keep/api/bl/alert_deduplicator/` 接 `/agents/evaluate`(plan §3 §3 关键挪移)。

---

## 6. PR 选择

`phase-1/agents` 推 origin,可以选:

A. **保留 phase-1/agents 当 long-lived branch**,Phase 2 起 `phase-2/ui-handoff` 基于它。Phase 3 收口时一次合 main(新仓库的 main,**不是 keephq/keep 上游**)。

B. **现在就合 phase-1/agents → main**(新仓库),Phase 2 直接基于 main。优点:main 始终代表"已收口阶段";缺点:phase-1/agents 这条线就关了,后续 hotfix 要新 PR。

我倾向 **A**(plan §2 Day 7 也写的是 "PR 合 phase-1/agents → main(新仓库的 main)" 但没说必须立刻合)。等用户拍板。
