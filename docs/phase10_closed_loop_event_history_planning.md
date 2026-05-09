# Phase 10 — Closed-Loop Event History Planning (v2)

> **定位：** planning only。不实现，不跑实验。
> Phase 10 asks whether a digital individual can be shaped by a world-generated
> history, not merely by a designer-specified event schedule.

---

## 1. 背景

### Phase 9D 已完成并进入 master

| Stage | Conclusion |
|-------|-----------|
| 9D.1 | tag / capture / slow_weight plumbing passed |
| 9D.2 | behavior smoke caveated positive |
| 9D.2A/B/C | simultaneous caveat traced to geometry_projection_asymmetry |
| 9D.3 | geometry-aware 4-seed validation positive |

**9D 的核心结果：** 固定 schedule 下，短时 event-pair dW 可以通过
tag/capture/slow_weight 管线沉积为可验证的长期方向性结构。

**当前 master 状态：** `fbd32c5`，CI (pytest 275/275) 已加入，
tag `phase-9D-structural-consolidation` / `phase-9D-merged-mainline`。

### 为什么需要 Phase 10

9D 验证的是 "event order can be deposited as structure"。
但 9D 的 event schedule 是 **实验者预设的**：

```python
for i in range(n_pairs):
    schedule.append((t, "L", duration))
    schedule.append((t + gap, "R", duration))
```

真实的世界经历不是预设 schedule。下一个 event 发生什么、什么时候发生、
发生在哪一侧，应该受 system state 和 world state 影响。

**核心变化：从 open-loop designer schedule → closed-loop world feedback。**

### 术语映射

本项目中使用的术语与外部文献的对应关系：

| 本项目术语 | 外部对应术语 | 来源 |
|-----------|-------------|------|
| closed-loop event history | adaptive experiment / online decision policy / JITAI decision rule | MRT/JITAI, AAAI 2024 |
| matched open-loop replay | yoked replay / replay control / decoupled control | DeepLabStream 2021 |
| geometry-aware correction | shared nuisance baseline subtraction + unbiased geometry estimation | 无同名标准术语，工程组合 |
| scheduler | policy / decision rule / adaptive intervention | contextual bandit, JITAI |
| event log | decision log / propensity log / bandit logging | OBP, Vowpal Wabbit |

---

## 2. Phase 10 核心问题

```
Phase 9: 事件顺序能否沉积为方向性结构？
  → 能。证据链完整。

Phase 10: 世界状态反馈生成的事件历史，能否持续塑造结构？
  → 开放问题。

具体：
  world state → event generation → individual state change → future event probability
  这种闭环历史，能否产生可解释、可重复、可区分的长期结构沉积？
```

### 关键子问题

1. **闭环 vs 开环等价性：** 同样的事件序列，如果是 state-feedback 生成的，
   和 matched open-loop replay（相同事件，无反馈）产生的结构是否不同？
2. **历史分叉：** 同一初始状态 + 同一 world rule，不同 seed 产生的
   event history 是否分叉？分叉后的结构差异是否可测？
3. **反馈强度：** feedback 多强才能产生显著的结构差异？
   太弱 → 退化为开环；太强 → 不稳定/饱和。
4. **沉积积累：** 在闭环中，slow weight 是否持续累积，还是快速饱和？

### 核心假设

> **同一条事件历史，在原本适配它的 closed-loop state trajectory 中，
> 和在被解耦的 open-loop trajectory 中，是否产生结构差异。**

这不是在问"事件能不能塑造结构"（9D 已经回答了）。这是在问：
**"由世界状态反馈生成的事件历史"是否携带额外的结构塑造效应——
这种效应在事件被剥离了反馈上下文后（replay）会消失。**

---

## 3. 不做什么

- 不做游戏、不做 NPC
- 不做 LLM / 人格字段 / 语言层
- 不做意识声明
- 不做复杂社会模拟
- 不直接跳多智能体
- 不调参追结果
- 不把 Phase 9D 的结论改成 "足够"
- **不做完整 online RL / model-based scheduler**（Phase 10 最小实现用参数化随机调度器）

---

## 4. Phase 10A 分层路线

**核心原则：每一层只引入一个变量。失败时边界清晰。**

```
10A.0: design freeze + preregistration (本文档)
10A.1: scheduler plumbing smoke — 只验证 event generation，不开 plasticity
10A.2: closed-loop + 9C fast event-pair plasticity — 开 dW，不开 consolidation
10A.3: closed-loop + 9D slow consolidation — 开完整 9C+9D 管线
10A.4: 4-seed formal validation (ECS)
10A.5: diagnostics + write-up
```

### 10A.0 — Design Freeze

- 冻结 scheduler 输入/输出契约
- 冻结 arms、metrics、success criteria
- 冻结 anti-cheat 边界
- 冻结 preregistration

### 10A.1 — Scheduler Plumbing Smoke

**只验证 state → event probability → event history 能跑通。**
不开 9C event-pair plasticity，不开 9D consolidation。

- 最小闭环：1-2 个 world variable + 参数化随机调度器
- 离散事件集：`E = {none, L, R, simultaneous}`
- 检查：
  - event 生成频率合理（不退化到 all-none 或 all-event）
  - event type 分布有变化（不全是 L 或全是 R）
  - 不同 seed 产生不同的 event history（分叉存在）
  - no NaN, no crash
- 输出：完整 event log（含 obs_hash, probs, u_draw, event）
- runtime: < 5 min local（无 plasticity 计算）
- seeds: 2 (42, 77)

### 10A.2 — Closed-Loop + 9C Fast Plasticity

**打开 event-pair dW，不开 9D consolidation。**
验证闭环事件历史能改变 fast weight trajectory。

- 开启 `event_pair_plasticity_enabled=True`
- 关闭 `consolidation_enabled=False`
- 与 matched open-loop replay 对比
- 与 random_event control 对比
- metrics: fast_weight_l1_change, fast_weight_per_region
- seeds: 2 (42, 77)
- runtime: ~8 min local per seed

### 10A.3 — Closed-Loop + 9D Slow Consolidation

**打开完整 9C+9D 管线。**
验证闭环事件历史能沉积到 slow structure。

- 开启 event-pair plasticity + consolidation
- matched open-loop replay + simultaneous + no_event controls
- primary metric: corrected structural distance
- seeds: 2 pilot → 4 formal
- runtime: ~12 min local per seed, ~3 min ECS 4P

### 10A.4 — 4-Seed Formal Validation

- ECS 4P 并行，4 seeds (42, 77, 123, 999)
- 固定 config，不可手工干预
- 自动 aggregate + bootstrap CI
- runtime: ~12-18 min ECS wall time

### 10A.5 — Diagnostics + Write-Up

- geometry-aware correction（如需要）
- ablation: 关 feedback / 延迟 feedback / stale-state control
- OPE sanity check（如 logged propensities 可用）
- event history divergence 可视化
- slow structure per-unit / per-region 热图

---

## 5. 调度器设计

### 调度器分层（从低风险到高风险）

| 档位 | 名称 | 描述 | Phase 10 使用 |
|------|------|------|-------------|
| 1 | 规则型 | `if f(obs_t) > τ: emit A else none` | 备用 |
| 2 | **参数化随机** | `p_t = softmax(g(obs_t; θ))`，采样离散事件 | **Phase 10 主选** |
| 3 | 上下文 bandit | 事件触发 + 在线更新 θ | 未来 |
| 4 | online RL / model-based | 完整学习循环 | 不做 |

**Phase 10 最小实现选第 2 档：参数化随机调度器。**
离散事件集 `E = {none, L, R, simultaneous}`，每个决策时刻输出概率分布。

### Scheduler 契约

```python
class Scheduler(Protocol):
    def propose(self, obs: "ObsView", t: int, hist: "HistView") -> "EventDist":
        """给定当前可见状态，输出事件分布。不做在线学习。"""
        ...

@dataclass
class EventDist:
    probs: dict[str, float]   # 包含 "none"，sum to 1
    metadata: dict[str, Any]  # logged but not used by replay
```

### 允许输入（Allowlist）

- 当前时刻 `t` 的 observable state
- bounded history view（仅在 `t` 时刻可见的部分）
- 当前 clock / phase id

### 禁止输入（Denylist）

- `arm_label` — scheduler 不知道自己在哪个实验组
- future observations — 无未来信息
- post-hoc summaries — 无后验统计
- validation metrics — 无目标指标
- `slow_weight_cache`, `tag_cache`, `connections` — 不能读内部结构
- **event history count** — scheduler 无记忆，不能数"我发了几个 event"

**Scheduler 的马尔可夫性：只看当前 state，不数历史。**
如果 scheduler 可以数 "我已经发了 3 次 L event"，那它就
有了隐式 designer schedule —— 只是把 `n_pairs=3` 写进了
scheduler 逻辑而不是顶层 schedule。这是 Phase 10 要消除的。

### 随机数分离

```
env_rng  — 环境初始化、噪声（not replayed）
sched_rng — 调度器随机采样（logged, verifiable）
```

两个 RNG 独立 seed。replay 时只冻结 `sched_rng` 的 draw 结果
（通过 event log 中的 `u_draw` 字段），不重新采样。

### 事件日志 Schema

每个决策时刻至少记录：

```
run_id, arm, seed_env, seed_sched, code_sha, config_sha
t_decision, obs_hash, obs_schema_version
probs_json, u_draw, chosen_event, payload_hash
latency_ms, applied_ok
```

---

## 6. Matched Open-Loop Replay

### 严格定义

> **Matched open-loop replay**：先在 closed-loop 条件中记录完整事件轨迹
> `T = {(t_i, event_i, payload_i)}`；随后在 control 条件中由 replay player
> 按同一时间戳和同一载荷精确重放 `T`，同时 replay player 不得读取当前状态、
> 不得重新采样、不得基于 control 状态修改事件参数。
> 这样，closed-loop 与 replay 的唯一制度性差异就是**反馈环是否闭合**。

此定义来自神经科学中的 yoked control / replay control 范式
（DeepLabStream, 2021），其中 control 动物 "received the exact same
temporal stimulus as the paired experimental animal, decoupled from
its own head direction"。

### 伪代码

```python
# ── Closed-Loop ──
obs_t = sensor_view.read()
probs_t = scheduler.propose(obs_t, t, history_view)  # no arm_label, no future
u_t = rng_sched.random()
event_t = sample_event(probs_t, u_t)
logger.write(t=t, obs_hash=hash_obs(obs_t), probs=probs_t, u=u_t, event=event_t)
substrate.apply(event_t)

# ── Matched Open-Loop Replay ──
logged = trace_player.next(t)
assert logged.hash == hash(logged.t, logged.event, logged.payload)
# scheduler is DISABLED: no state read, no resampling, no re-decision
substrate.apply(logged.event, payload=logged.payload)
```

### "时序错位 = Signal" 的解释

在 closed-loop 中：`state_closed(t) → event(t)`。
在 open-loop replay 中：同一个 `event(t)` 被注入，但 unit 当前状态
是 `state_open(t)`，可能与 `state_closed(t)` 不同。

- 如果 closed-loop scheduler 只是随机 event generator，
  `state_closed(t)` 和 `state_open(t)` 的差异在统计上是噪声级别，
  replay 的结构距离应 ≈ 0。
- 如果 state feedback 有真实的 conditioning 效应，
  event 序列携带了对 `state_closed` trajectory 的"适配性"。
  当这个适配性在 open-loop 中被剥离 → 结构距离 ≠ 0。

**这个"不适配"正是我们要测量的 signal。**
Timing mismatch is a feature, not a bug.

### Replay 硬门槛

- `hash_mismatch_count == 0`
- `event_count_diff == 0`
- `timestamp_diff == 0`

如果 replay 不 exact，formal 结果无效。

---

## 7. Arms

| Arm | Event Source | Purpose |
|-----|-------------|---------|
| closed_loop | scheduler 从 state 在线生成 | 主实验臂 |
| matched_open_loop_replay | 回放 closed_loop 的 event log | 剥离反馈环的控制 |
| random_uniform_control | 同期望 event 数，均匀随机 timing/type | 随机基线 |
| simultaneous_geometry_control | combined L+R phi，固定 schedule | shared nuisance baseline |
| no_event_control | 无事件 | null baseline |

---

## 8. Metrics（分层）

### Layer 0 — Event History（scheduler 输出）

| Metric | 测量什么 |
|--------|---------|
| event_count | 事件总数 |
| event_type_distribution | {none, L, R, simultaneous} 比例 |
| inter_event_interval_mean / variance | 事件间隔 |
| event_history_divergence (cross-seed) | 不同 seed 的事件序列 JS/Wasserstein 距离 |

### Layer 1 — Fast Plasticity（9C only, 10A.2）

| Metric | 测量什么 |
|--------|---------|
| fast_weight_l1_change | vs no_event baseline |
| fast_weight_per_region (L/R/M) | 区域分解 |
| fast_weight_DI | 如有方向性信号 |

### Layer 2 — Slow Consolidation（9C+9D, 10A.3+）

| Metric | 测量什么 |
|--------|---------|
| slow_weight_l1_total | slow weight 总质量 |
| corrected_slow_DI | 如复现方向性分析，减去 geometry baseline |
| slow_weight_per_region | 区域分解 |

### Layer 3 — Cross-Layer（closed vs open）

| Metric | 测量什么 |
|--------|---------|
| open_vs_closed fast structural distance | 10A.2: replay 后的 fast weight 差异 |
| open_vs_closed slow structural distance | 10A.3+: replay 后的 slow weight 差异 |
| corrected_effect | observed_effect − shared_nuisance_baseline |

### Controls

| Metric | 测量什么 |
|--------|---------|
| no_event_residual | null baseline 的残留 |
| simultaneous_baseline_abs | shared nuisance 的规模 |
| nan_count | 必须为 0 |
| replay_hash_mismatch_count | 必须为 0 |

### 统计汇报

- **bootstrap CI**：对 seed-level effect 做 nonparametric bootstrap
- **seed-level sign consistency**：`n_positive / n_seeds`，不只是 aggregate mean
- 如果 seed 数不足做 CI，报告全部 seed 的 individual summary，不做假均值

---

## 9. Success Criteria（分阶段）

### 协议层（所有阶段必须通过）

| Criterion | Threshold | 强制 |
|-----------|-----------|------|
| replay exactness | hash_mismatch_count == 0 | **HARD** |
| 日志完整性 | 所有必填字段齐全 | **HARD** |
| no NaN | 0 | **HARD** |
| no explosion | max_abs < clamp | **HARD** |

### 10A.1 — Scheduler Plumbing（2 seeds）

| Criterion | Threshold |
|-----------|-----------|
| event_count > 0 | qualitative |
| event type 分布不退化 | 不全是一种 event |
| 不同 seed 产生不同 history | qualitative |
| 不 crash | — |

→ 输出判断：**"scheduler produces varied, non-degenerate event patterns"**

### 10A.2 — Fast Plasticity（2 seeds）

| Criterion | Threshold |
|-----------|-----------|
| fast_weight 与 no_event baseline 有差异 | qualitative |
| 差异不由 event count 单独解释 | matched control |
| 不爆炸 | — |

→ 输出判断：**"closed-loop events change fast weight trajectory"**

### 10A.3 — Slow Consolidation（2 seeds pilot / 4 seeds formal）

| Criterion | Threshold | 阶段 |
|-----------|-----------|------|
| corrected structural distance (closed vs replay) > 0 | measurable | pilot |
| 差异不由 event count / intensity / total stimulus 解释 | matched control | pilot |
| simultaneous corrected | ≤ ε_sim | pilot |
| no_event residual | ≤ ε_null | pilot |
| ≥ 3/4 seeds 方向或机制一致 | — | **formal only** |

### 10A.4 — Formal（4 seeds）

与 10A.3 相同，但 seed 数 ≥ 4，且:
- ≥ 3/4 seeds 方向一致
- bootstrap CI 支持非零差异
- 所有 config/code hash 已记录

---

## 10. Anti-Cheat Boundaries

### 编译时（静态）

1. **Scheduler 函数签名不含 `arm_label`。** 单元测试强制执行。
2. **Scheduler 不能导入/访问** `slow_weight_cache`, `tag_cache`,
   `connections`, `plasticity_consolidation` 内部状态。
3. **Event log schema 不包含** future timestamps, post-hoc summaries,
   validation metrics, arm-level aggregates。

### 运行时（动态）

4. **Scheduler 不能读取 event history count。** 无记忆，只看当前 state。
5. **Scheduler 不能根据 desired outcome 调事件。** 没有 reward / target。
6. **Replay player 不读 state，不重新采样。** 纯播放。
7. **不允许根据实验组硬编码 event。** 同一个 scheduler rule 用于所有 arm。
8. **Diagnostics offline only。** 不可在线影响 event 选择。

### 事后（审计）

9. **每个 primary metric 有对应的 nuisance baseline。**
10. **所有 formal run 带 `code_sha + config_sha + seed_env + seed_sched`。**
11. **Smoke 不判断"科学成败"，只判断"协议过关"。**
12. **Formal 结果由 aggregate 脚本统一算，不在 notebook 里手改。**

---

## 11. Runtime Policy

| 阶段 | 平台 | Seeds | 估时 | 备注 |
|------|------|-------|------|------|
| 10A.1 (plumbing) | local | 2 | < 5 min | 无 plasticity |
| 10A.2 (fast) | local | 2 | ~8 min/seed | 9C only |
| 10A.3 pilot (slow) | local | 2 | ~12 min/seed | 完整 9C+9D |
| 10A.3 formal (slow) | ECS 4P | 4 | ~12-18 min wall | 并行 |
| 10A.4 (formal) | ECS 4P | 4 | ~12-18 min wall | 并行 |

- ECS: `i-7xvduf6m2y77m915mhr5`, 4C8G, cn-guangzhou
- 实验前确认 IP，跑完收结果关机
- 本地 smoke 允许简化日志；formal 不允许
- CI (push/PR): 只跑 tests + tiny smoke；formal 手动触发

---

## 12. 与 Phase 9D 的关系

| Aspect | Phase 9D | Phase 10A |
|--------|----------|-----------|
| Event source | designer-specified schedule | state-feedback scheduler |
| Question | can event order deposit? | can world history shape? |
| Event generation | fixed L/R paired | world_state → probability → event |
| Key control | simultaneous, no_event | + matched open-loop replay |
| Metrics | slow_DI, corrected_slow_DI | + event_history_divergence, open_vs_closed distance, replay exactness |
| Seeds | 4 (formal) | 2 (pilot) → 4 (formal) |
| Status | completed, in master | planning v2 |

9D 证明：固定 schedule 下，事件顺序能沉积为长期结构。

Phase 10 要问：**如果事件不是设计师写的，而是世界状态反馈生成的——
这种"活的历史"是否还能刻进骨头？以及，把历史从它生长的 feedback context
里剥离出来（replay）后，塑造效应是否消失？**

**9D 是骨头会记住。Phase 10 是：世界能不能持续雕刻这副骨头。**

---

## 13. Pre-Registration 模板

以下模板应在 10A.0 设计冻结时填入具体数值并 commit：

```markdown
# Phase 10 Pre-registration

## Research question
Does a world-generated closed-loop event history induce structural
differentiation beyond (a) matched open-loop replay and
(b) shared nuisance baselines?

## Design
- Arms: closed_loop, matched_open_loop_replay, random_uniform_control,
  simultaneous_geometry_control, no_event_control
- Seeds: [42, 77, 123, 999]
- Horizon: <fixed steps or event budget>
- Runtime tiers: local smoke → ECS formal

## Scheduler contract
Allowed: current observable state at time t, bounded history view
  available at t, current clock / phase id
Disallowed: arm_label, future observations, post-hoc summaries,
  validation metrics, any field generated after decision time,
  slow_weight_cache, tag_cache, connections, event history count

## Primary criteria
1. replay_hash_mismatch_count = 0
2. |simultaneous_corrected_effect| ≤ ε_sim
3. |no_event_effect| ≤ ε_null
4. corrected_effect(closed vs replay) > 0 in ≥ 3/4 seeds
5. nan_count = 0, no explosion

## Claim boundary
A positive result means:
- closed-loop event history produced a reproducible structural effect
  above matched replay and nuisance baselines.
A positive result does NOT mean:
- digital life validated
- consciousness, sentience, subjectivity, or personhood established
- general intelligence or autonomous agency established
```

---

## 14. 参考

### 项目内
- `docs/phase9D_summary.md` — 9D evidence chain
- `docs/phase9D_to_phase10_transition.md` — transition rationale
- `docs/phase9D3_geometry_aware_consolidation_validation_design.md` — geometry-aware design
- `aniva/experiments/exp9D3_geometry_aware_validation.py` — runner reference

### 外部方法学
- DeepLabStream (Schweihoff et al., 2021, Communications Biology) — yoked replay control
- MRT/JITAI (Klasnja et al., 2022) — micro-randomized trial, adaptive intervention
- Adaptive Bandit Experiments (AAAI 2024) — online adaptation with side-by-side comparison
- Reproducible workflow for online AI (arXiv 2025 preprint) — full-lifecycle reproducibility
- Open Bandit Pipeline — OPE, bootstrap CI, policy comparison
- Deep RL that Matters (Henderson et al., 2018) — few-run variance, significance reporting
- Statistical Precipice (Agarwal et al., 2021) — IQM, interval estimates, performance profiles
- Mitigating Bias in Adaptive Data Gathering (arXiv:1806.02329) — adaptive sampling bias
- Anytime-Valid Causal Inference on MAB (arXiv:2311.05794) — anytime-valid design
