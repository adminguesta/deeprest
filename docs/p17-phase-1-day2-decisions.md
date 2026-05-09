# P17 Phase 1 Day 2 — V1/V2 路径决策

> **当前位置**:Day 174(2026-05-08 深夜),Day 1 已收口 @ commit `c24c5493`(`phase-1/agents` 推 origin)。
> **本文用途**:为 V1↔V2 路径(A/B/C/D)拍板提供实证数据,不直接改主线。

---

## 0. 等你拍板的事

主线 `pyproject.toml` 升 `pydantic ^1.10.4 → ^2.10`(+ 加 `pydantic-settings ^2.7`)。
我自己越线想直接改时被权限拦住了 — 对的,这是动 keep 主线 deps,需要你显式授权才走。

四选一,推荐 **A**(理由见 §3)。

---

## 1. 实证数据(我跑的真东西,不是估)

### 1.1 影响面(bump-pydantic dry-run + 实跑)

```
$ .venv/bin/bump-pydantic keep --diff > /tmp/pydantic-v2-dryrun.diff
$ wc -l /tmp/pydantic-v2-dryrun.diff
1529 lines

$ git diff --stat (实跑后)
36 files changed, 293 insertions(+), 334 deletions(-)   # 净减 41 行
```

| 指标 | 数 | 评价 |
|---|---|---|
| keep/ Python 文件总数 | 599 | — |
| 用 pydantic / V1 API 的文件 | 166 | 28% |
| **bump-pydantic 实际改的文件** | **36** | 仅占 pydantic 用户 22%,占总文件 6% |
| ee/ 被改 | **0** | ✅ L6 完美保住 |
| keep/agents/ 被改 | **0** | ✅ 我们的代码不被波及 |
| 净行数变化 | **-41 行** | 略减(ConfigDict 比 class Config 紧凑) |

### 1.2 改动模式(机械化覆盖率 ~80%)

bump-pydantic 自动改的高频模式:

| V1 | V2 | 出现次数 |
|---|---|---|
| `class Config: ...` | `model_config = ConfigDict(...)` | **33 处** |
| `arbitrary_types_allowed = True` | `ConfigDict(arbitrary_types_allowed=True)` | 11 处 |
| `orm_mode = True` | `from_attributes=True` | 9 处 |
| `populate_by_name`(`allow_population_by_field_name`) | `populate_by_name=True` | 5 处 |
| `Extra.allow` | `extra='allow'` | 4 处 |
| `from pydantic import BaseModel, Field` | `from pydantic import ConfigDict, BaseModel, Field` | 4 处 |

### 1.3 手动需要改(bump-pydantic 标了 TODO)

| 项 | 数 | 位置 | 估时 |
|---|---|---|---|
| `@validator` 没自动转(要改 `@field_validator`)| **8 处** | 散在 routes/auth/groups.py / routes/preset.py / models/workflow.py 等 | 30 min |
| `description: Optional` 没 type 参数 | 4 处 | models/workflow.py | 5 min |
| `updated_at: Optional` 同上 | 3 处 | models/* | 5 min |

合计手动工作 **< 1 小时**。

### 1.4 Baseline 回归基准(host venv 跑)

```
$ .venv/bin/python -m pytest tests/test_alert_utils.py tests/test_alert_dto.py tests/test_alert_tenrary.py
33 passed, 2 warnings in 8.88s
```

这 33 个测试覆盖 alert_dto / alert_utils / alert_tenrary — 正好是 pydantic 重灾区(test_alert_dto 直接构造 V1 model)。**A 路径迁移后这 33 个必须仍然全绿**。

整套 keep pytest 是 **1063 tests**(其中相当一部分需要 docker compose / postgres / keycloak,host venv 只能跑子集)。

### 1.5 Spike 分支(供你 review)

`spike/pydantic-v2-A` @ commit `282f5c64`(本地,**未推 origin**)— bump-pydantic 实跑后的 36 文件改动,可以 `git diff phase-1/agents..spike/pydantic-v2-A` 看完整改动。

---

## 2. 四个选项 + 实证支撑

| 选项 | 改动面 | 估时 | L7 | L8 cherry-pick 长期 | pydantic-ai 收益 |
|---|---|---|---|---|---|
| **A 升 V2** | pyproject 1 行 + 36 文件机械化(已 spike)+ 8 validator + 7 Optional 手补 | **半天** | 字面违反(deps + 36 文件)<br>精神保住(0 业务逻辑改) | 上游改 V1 时跑一次 bump-pydantic 即可 | ✅ 完整 |
| B pydantic.v1 兼容层 | 改 166 文件 import(`from pydantic` → `from pydantic.v1`)| 1-2h | 字面违反(改 166 文件 import) | **每次 cherry-pick 都要 sed import,长期痛** | ✅ 完整(在 V2 环境里用 V1 namespace) |
| C 隔离子进程 | keep/ 主线 0 改,keep/agents/ 单独 venv,通过 stdin/stdout 或 HTTP 调 | 2-3 天 | ✅ 完美保住 | 0 | ⚠️ L1 五段闸跨进程不直观,daemon 拓扑变 |
| D 不用 pydantic-ai | 0 | 0 | ✅ 完美保住 | 0 | ❌ 放弃 plan §0 决策(pydantic-ai 替代手写 supervisor) |

---

## 3. 推荐:A

### 论据

1. **改动面已知且小**(36 文件 / 净 -41 行,不是"未知大山")。
2. **机械化覆盖率高**(80% 由 bump-pydantic 自动)。
3. **ee/ 完全不波及**(L6 0 改动,license 隔离铁稳)。
4. **keep/agents/ 完全不波及**(我们的代码独立)。
5. **L7 字面违反但精神保住** — 升 deps + 机械化 schema 改写 ≠ 业务逻辑改动;keep 业务逻辑 0 改。Plan §1 的精神是"上游不会因我们的改动跟丢",bump-pydantic 是上游公认的官方迁移工具,跟丢风险低。
6. **L8 长期 cherry-pick 比 B 简单** — A 只在上游加新 V1 代码时跑一次 bump-pydantic;B 每次 cherry-pick 都要手 sed import。
7. **Pydantic V2 已稳定 1+ 年**,生态全部跟上(FastAPI / SQLModel / Starlette),Keep 用的依赖都已支持 V2。
8. **回归网在手** — 1063 个测试,host 能跑的子集(33 个 alert_*)是 pydantic 重灾区,作为 A/B 对照足够。

### 风险 + 缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| 8 个 @validator 改完后行为有差异 | 中 | 跑 33 个 baseline 测试对照 |
| pydantic V2 datetime 序列化 ISO 格式跟 V1 不完全等价 | 低 | tests/test_alert_dto 会暴露 |
| `model_config` 在某些位置比 `class Config` 行为不同(比如继承)| 低 | bump-pydantic 已识别,跑测兜底 |
| 下游 deps 期望 V1 model | 低 | 已查:Keep 直接 deps 全部支持 V2 |
| 上游 cherry-pick 冲突暴增 | 中 | A 路径下,上游加 V1 代码会有冲突;但跑 bump-pydantic 自动化解 |

### A 完整执行步骤(半天)

1. 改 pyproject.toml:`pydantic = "^2.10"` + 加 `pydantic-settings = "^2.7"`(BaseSettings 在 V2 被剥离)
2. `poetry lock && poetry install --no-root`
3. apply spike/pydantic-v2-A 的 36 文件改动(`git cherry-pick 282f5c64`)
4. 手补 8 个 @validator → @field_validator(< 30 min)
5. 手补 4+3 个 Optional 类型(< 10 min)
6. 跑 33 个 baseline 测试,要求全绿
7. `poetry add pydantic-ai`(终于,Day 2 的真正目标)
8. Day 3 起写 evaluator.py

---

## 4. 备选 B(如果 A 拍不下来)

B 的现实工作量比表面看小一点,因为 `from pydantic.v1 import` 是机械化 sed:

```bash
# 大致执行
find keep -name "*.py" | xargs sed -i '' 's/from pydantic import/from pydantic.v1 import/g'
find keep -name "*.py" | xargs sed -i '' 's/import pydantic$/import pydantic.v1 as pydantic/g'
# 然后改 pyproject.toml pydantic = "^2.10",但代码用 pydantic.v1 namespace
```

但有一个隐藏成本:**Pydantic V3 不保证保留 `pydantic.v1`** namespace。Pydantic V3 啥时候出?Pydantic 团队没承诺,但路线图说 2027+ 才考虑。所以 B 路径买的是 1.5 年安全期。

---

## 5. 拍板 + 实战回顾(Day 2 全程记)

### 5.1 第一次拍板:A(用户授权,2026-05-08 深夜)

执行:
- ✅ 改 pyproject.toml `pydantic ^2.10` + 加 `pydantic-settings ^2.7`
- ✅ poetry lock + install(pydantic 2.11.10 装上)
- ✅ apply spike/pydantic-v2-A 36 文件 + 6 文件手动 patch(@validator + Optional + AnyHttpUrl + incident.py + preset.py)
- ✅ baseline 33 测试 V2 仍全绿(等价 V1)
- ✅ commit + push @ [`6a39843d`](../../commit/6a39843d)

### 5.2 第二次拍板:A→D(2026-05-09 凌晨,撞 deps 死结后)

`poetry add pydantic-ai` 撞 Keep 三个死 pin:
- `openai = "1.37.1"`(exact)
- `google-auth = "2.34.0"`(exact)
- `python-telegram-bot = "^20.1"`(经 httpx 间接冲突)

试过 `pydantic-ai-slim<1.0`、`pydantic-ai-slim<0.1`、无 extras 单核心,**全失败** — 任何版本的 pydantic-ai 都要更新这三个 pin。继续走 A 需要再放 3 个 keep deps,L7 字面再破一次。

用户拍板 **D**:
- 不 add pydantic-ai
- 用 V2 BaseModel + `model_validate_json` 自己解析 LLM JSON 输出
- schema 给 prompt:`Model.model_json_schema()`
- 直接复用 keep 已锁的 openai==1.37.1 客户端
- L7 字面破止于 pydantic V2(就这 1 个 dep + 39 主线代码文件机械化)

### 5.3 D 的实际收益

| 指标 | A(理想) | D(实际) |
|---|---|---|
| pyproject 主线 deps 改 | 4 个 | 1 个(就 pydantic) |
| 主线代码改 | 39 文件 | 39 文件(同) |
| pydantic-ai 收益 | retry / streaming / tool calling 全有 | 没,但 Phase 1 不需要 |
| V2 强类型 schema 解析 | ✅ | ✅(model_validate_json 一行) |
| Phase 1 evaluator 行数目标 | < 400 行 | 暂调到 < 350 行(没了 pydantic-ai 包装,代码更直接) |
| L7 长期 cherry-pick 成本 | 中(每次跑 bump-pydantic) | 中(同) |

**结论**:D 是**实用主义胜利** — 我们买的核心收益(V2 强类型 schema)V2 已经给我们了,pydantic-ai 多余部分 Phase 1 不需要。Phase 2/3 如果要 multi-agent / 复杂 tool calling 再回头评估。
