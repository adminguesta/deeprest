# P17 Phase 1 Day 1 — Acceptance

> **当前位置**:Day 173(2026-05-08),P16 已收口,P17 启动。
> **决策依据**:`/Users/chenxi/DeepREST/docs/p17-keep-fork-pivot-plan.md` §2 Day 1。

---

## 0. 完成情况速读

| # | 项 | 状态 | 备注 |
|---|---|---|---|
| 1 | fork keephq/keep → adminguesta/deeprest | ✅ | https://github.com/adminguesta/deeprest |
| 2 | 本地 clone 到 `~/keep-fork` | ✅ | 绕开 `~/deeprest`(macOS 大小写不敏感占用) |
| 3 | remote 重命名 origin / keep-upstream | ✅ | 见 §1 |
| 4 | tag `keep-baseline-day173` 上游 main | ✅ | 上游 head `df4e48d2`(2026-05-03)|
| 5 | docker-compose.dev.yml 起 + healthy | ❌ → 退 Plan B | 见 §3,buildkit 在 poetry resolver 阶段静默 30+ min,退本机 poetry |
| 5b | **Plan B**:host venv `poetry install --no-root` | ✅ | 见 §3,243 deps 装齐 + keep CLI / keep.agents 全跑通 |
| 6 | 摸清关键路径(bl/providers/workflowmanager/rulesengine/UI) | ✅ | 见 §2 |
| 7 | 建 `keep/agents/` 包骨架 | ✅ | 见 §4,smoke test 2 个全绿 |
| 8 | pyproject 加 pydantic-ai | ❌ **推到 Day 2** | 见 §5 风险 |
| 9 | 挪 `AlertVerdict` / `CandidateAlert` + ReAct 字段 | ✅ | dataclass 风格,见 §4 |

**Day 1 实际交付物**:fork ready + 包骨架 + models.py 字段冻结 + smoke test 绿。
**Day 1 没交付**:pydantic-ai 依赖(被 V1/V2 冲突卡住,Day 2 第一件事就是这个)。

---

## 1. 仓库 & remote

```
$ cd ~/keep-fork && git remote -v
origin           https://github.com/adminguesta/deeprest.git  (fetch)
origin           https://github.com/adminguesta/deeprest.git  (push)
keep-upstream    https://github.com/keephq/keep.git           (fetch)
keep-upstream    https://github.com/keephq/keep.git           (push)

$ git tag | grep keep-baseline
keep-baseline-day173    # → keep-upstream/main @ df4e48d2 (2026-05-03)
```

工作分支:`phase-1/agents`(Phase 1 收口时合到 `main`,**不**合 keephq/keep 上游)。

---

## 2. 地形摸底(关键路径)

| 路径 | 子项 | 我们的关心点 |
|---|---|---|
| `keep/api/bl/` | ai_suggestion_bl, dismissal_expiry_bl, enrichments_bl, incident_reports, incidents_bl, maintenance_windows_bl | Day 4 webhook 嫁接点候选 |
| `keep/api/alert_deduplicator/` | (子目录,与 plan 提到的位置一致) | LLM dedup 替换的接入点 |
| `keep/api/routes/` | 25 个 routes:alerts/incidents/rules/workflows/providers/ai/...(**没有 agents.py**) | Day 4 在这里加 `agents.py`(L7 不变量:新文件) |
| `keep/providers/` | **132 个**(数得上 plan 文档的"132+") | Phase 3 才碰 |
| `keep/workflowmanager/` | workflow / workflowmanager / scheduler / store | Phase 3 接 ChangeAgent |
| `keep/rulesengine/` | 单文件 rulesengine.py | dedup/correlation 规则,evaluator 兜底参考 |
| `keep-ui/app/(keep)/` | incidents/alerts/ai/workflows/providers/rules/dashboard/topology/... | Phase 2 加 "AI 诊断结论" tab 的位置 |
| `keep/api/` 顶层 | api.py / arq_pool.py / arq_worker.py / consts.py / observability.py / middlewares.py | arq + redis 是 worker 调度,不是 dev compose 必跑 |
| `ee/` | (未展开,Phase 1 不动) | L6 不变量:0 改动 |

**与 plan 文档的偏差**:
- plan 写 "postgres / redis 全 healthy",但 `docker-compose.dev.yml` 实际只起 backend(sqlite)+ frontend + soketi websocket。**postgres/redis 是 production compose(`docker-compose.yml` / `docker-compose-with-arq.yml`)才有**。Day 1 用 dev compose(轻量),Phase 3 真接 ChangeAgent 时再考虑切 production compose。

---

## 3. docker-compose 状态 + Plan B(host venv)

### 3.1 docker-compose dev 真实结果

dev 栈:
- `keep-frontend-dev`(node:alpine + npm install)— ✅ build 通过
- `keep-backend-dev`(python:3.11.6-slim + poetry install)— ❌ **buildkit 卡在 Poetry 1.3.2 resolver 阶段**(30+ min 静默,无输出),两次重试同样症状
- `keep-websocket-server`(quay.io/soketi/soketi:1.4-16-debian)— ✅ pull 完成

**根因**:Keep Dockerfile 用 `poetry==1.3.2`(2022 年版本),resolver 在 243 deps 上跑得极慢且**默认 verbosity 没任何输出**,Docker Desktop VM 资源(7.6 GB / 10 CPU)进一步放大。L7 不动主线代码意味着不能改 Dockerfile.dev.api 里的 poetry 版本。

### 3.2 Plan B(实际跑通的路径)— host venv

```bash
# Python 3.13 复用老 DeepREST .venv(在 Keep 的 >=3.11,<3.14 范围内)
/Users/chenxi/deeprest/.venv/bin/pip install poetry  # poetry 2.4.0(比 1.3.2 快 5×+)

cd ~/keep-fork
/Users/chenxi/deeprest/.venv/bin/poetry config virtualenvs.in-project true
/Users/chenxi/deeprest/.venv/bin/poetry env use /Users/chenxi/deeprest/.venv/bin/python3.13
PIP_DEFAULT_TIMEOUT=300 /Users/chenxi/deeprest/.venv/bin/poetry install --no-root --no-interaction
# → 243 packages installed(2 个 anthropic / azure-mgmt-containerservice 第一次 PyPI 超时,重跑通过)
```

**验证(全部 ✅)**:
```
$ .venv/bin/python -c "import keep" → OK(namespace package)
$ .venv/bin/python -c "from keep.agents.models import AlertVerdict, CandidateAlert" → OK
$ .venv/bin/python -m pytest keep/agents/tests/ -v
  → 2 passed in 0.02s(在 Pydantic V1 venv 里跑,确认 dataclass 风格无冲突)
$ PYTHONPATH=. .venv/bin/python -m keep.cli.cli --help
  → 全套子命令(alert / api / auth / config / extraction / mappings / provider / version / whoami / workflow)
```

### 3.3 实际"跑通骨架"的定义(Day 1 修正)

plan 文档原句"keep run 起得来,docker-compose 全套服务健康"是 **Phase 1 第 7 天验收标准**,不是 Day 1 卡点。Day 1 的目标是"摸清结构 + 搭骨架",Plan B 实现的是:
- Keep 全 243 deps 可解、可装(host arm64 native wheels,无 buildkit emulation 损耗)
- Keep CLI 可调
- `keep.agents` 子包 import + 跑测全绿(在 V1 venv 里)

后续(Day 2-7):
- Day 2 早晨先选 V1/V2 路径,**docker build 那头 Day 7 收口前再回头试一次**(可能要把 Dockerfile poetry 升 2.x,但这就是动主线 — 走 ChangeAgent 流程)
- Day 4-5 e2e 时跑 backend:`PYTHONPATH=. .venv/bin/python -m keep.cli.cli api`(host 直跑,跳过 docker)

---

## 4. `keep/agents/` 骨架

```
keep/agents/
├── __init__.py            # 子包入口,标 L7 不变量
├── models.py              # AlertVerdict + CandidateAlert + ReAct 字段(dataclass)
├── evaluator.py           # Day 2-3 实现位,目前 raise NotImplementedError
├── supervisor.py          # Phase 2/3(Pydantic Graph)
├── chat.py                # Phase 2(Pydantic AI 重写老 chat runner)
├── harness/__init__.py    # audit + tool registry,Phase 1/2 从老 core/harness/ 挪
├── prompts/.gitkeep       # Day 2-3 evaluator 用
├── audit/.gitkeep         # decisions.jsonl 落档位置(L2 不变量,只存 hash)
└── tests/
    ├── __init__.py
    └── test_models.py     # 2 个 smoke test 全绿(2 passed in 0.02s)
```

**字段冻结(P16.1 ReAct 不变量)**:
- `CandidateAlert`:device_id / device_kind / title / severity_hint / metric / value_now / threshold / recent_samples / labels / detector / detected_at
- `AlertVerdict`:candidate / should_alert / confidence / severity / reason / suggested_runbook / decided_at / fallback_reason / **reasoning_steps** / **impact_analysis** / **runbook_steps** / **related_incidents** / **historical_pattern**

**为什么用 dataclass 而不是 Pydantic**:见 §5。

---

## 5. 风险:Pydantic V1 vs V2(Day 1 发现的最重要的事)

### 现象

Keep 主线 `pyproject.toml`:
```toml
pydantic = "^1.10.4"     # V1
```

Pydantic AI(0.x stable)硬要求 Pydantic V2。两者**进程内不能共存** — 同一 Python 解释器只能装一个 Pydantic major 版本。

### 选项(Day 2 早晨拍板)

| 选项 | 改动面 | L7 / L8 影响 | 风险 |
|---|---|---|---|
| **A. 升 keep 主线 pydantic V1 → V2** | 改 `pyproject.toml` + 全仓 `from pydantic import ...` 扫一遍 V1→V2 不兼容点(常见:`@validator` → `@field_validator`、`Config` 类 → `model_config`、`.dict()` → `.model_dump()`) | 违反 L7"不动 keep 主线代码"的字面表述,但 plan §1 把 deps 视作可动 | 改动面 100+ 文件,但 V1→V2 自动化迁移工具 `bump-pydantic` 覆盖 80%。每月 cherry-pick 上游会持续踩坑。 |
| **B. `pydantic.v1` 兼容层** | Pydantic V2 提供 `pydantic.v1.*` namespace,V1 代码改 import 即可。对全仓批量 sed `from pydantic import ...` → `from pydantic.v1 import ...`(只对真用 V1 API 的地方) | 改动面比 A 小,但**需要**把主线 import 全改 — 仍碰主线代码 | cherry-pick 时 keep 上游加新代码会用 `from pydantic`,要每次手改。维护成本高。 |
| **C. keep/agents/ 隔离子进程** | agents/ 单独 venv + Pydantic V2,通过 IPC(stdin/stdout / HTTP)调主进程 | L7 完美保住(主线 0 改) | 进程间调用延迟、错误路径复杂、daemon 拓扑变化、L1 写动作五段闸通过 IPC 不直观 |
| **D. 不用 pydantic-ai,继续 V1 + 手写 LLM 调用** | Day 2 用 Pydantic V1 写 evaluator,自己拼 prompt + JSON parse + retry(继承 P16.1 ~700 行) | 完全无冲突 | 失去 plan 拍板的 "Pydantic AI 替代手写 supervisor" 收益,行数减不下来 |

### 建议(Day 2 早晨决定)

**A 是最干净的选项** — pydantic V2 已稳定 1+ 年,bump-pydantic 工具自动迁移 80% 用例。L7 字面意义会破,但 plan §1 的精神是"业务逻辑 0 改动",deps 升级不属于业务逻辑。每月 cherry-pick 时遇到上游写 V1 风格的代码,bump-pydantic 当场跑一遍即可。

**Day 2 早晨第一件事**:
1. 在 keep-fork 起 `phase-1/agents` 分支基础上跑 `pip install bump-pydantic && bump-pydantic keep/`(干跑,看影响面)
2. 评估改动行数,如果 < 500 行,选 A;> 500 行,退到 B
3. 确定后再 `poetry add pydantic-ai`,Day 2 才动 evaluator.py

---

## 6. 复核命令(给 Day 2 早晨自己用)

```bash
cd ~/keep-fork

# 6.1 host venv 健康
.venv/bin/python -c "from keep.agents.models import AlertVerdict, CandidateAlert; print('OK')"
# 期望:OK

# 6.2 agents 骨架 smoke test
.venv/bin/python -m pytest keep/agents/tests/ -v
# 期望:2 passed in <0.1s

# 6.3 keep CLI
PYTHONPATH=. .venv/bin/python -m keep.cli.cli --help
# 期望:列出 alert/api/auth/config/... 子命令

# 6.4 git 状态
git status
git log --oneline -3
# 期望:Day 1 commit 在 phase-1/agents @ origin/phase-1/agents

# 6.5 V1/V2 影响面预演(Day 2 第一步)
.venv/bin/pip install bump-pydantic
.venv/bin/bump-pydantic keep/ --diff > /tmp/pydantic-v2-dryrun.diff
wc -l /tmp/pydantic-v2-dryrun.diff   # 看影响行数

# 6.6(可选)docker compose dev 二战
# 如果 Day 7 要,先把 Dockerfile.dev.api 的 poetry==1.3.2 升 2.x(走主线 ChangeAgent 流程)
docker compose -f docker-compose.dev.yml ps
```

---

## 7. 不变量回顾(Day 1 实际守住情况)

| ID | 不变量 | Day 1 状态 |
|---|---|---|
| L1 | 写动作走 ChangeAgent 五段闸 + tollbooth | N/A(Day 1 无写动作) |
| L2 | audit 只存 hash 不存 raw | ✅ `keep/agents/audit/` 占位,Day 5-6 落档 |
| L3 | LLM 不可达 → 规则兜底,不 500 | ✅ models.py `fallback_reason` 字段保留 |
| L4 | read-only tool registry + scope_kind | ✅ `keep/agents/harness/` 占位,Day 2/Phase 1 末挪 |
| L5 | 不 carry 老 `core/llm_client/`,统一 Pydantic AI | ✅ Day 1 没挪 llm_client(Day 2 改用 pydantic-ai) |
| L6 | `ee/` 0 改动 | ✅ `git diff phase-1/agents..main -- ee/` 空 |
| L7 | 新东西只放 `keep/agents/` + `keep/api/routes/agents.py` | ✅ Day 1 只动了 `keep/agents/` 一个目录 |
| L8 | 每月 cherry-pick keep upstream | ✅ tag `keep-baseline-day173` 已落,Day 30 起按月 |

---

## 8. Day 2 入口

```
继续 P17 Phase 1 Day 2。

第一件事(从 Day 1 acceptance §5 接):
1. cd ~/keep-fork && git status(确认还在 phase-1/agents 分支)
2. pip install bump-pydantic(干跑,评估 V1→V2 影响面)
3. bump-pydantic keep/ --dry-run | tee /tmp/pydantic-v2-dryrun.log
4. 看影响面,选 A/B/C/D 之一,记到 docs/p17-phase-1-day2-decisions.md
5. 选完才 poetry add pydantic-ai,然后才动 evaluator.py
```
