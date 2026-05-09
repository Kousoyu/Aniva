# Phase 10 — Closed-Loop Event History Planning

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
tag/capture/slow_weight 管线沉积为可验证的长期方向性结构。即使在
geometry_projection_asymmetry 存在的情况下，repeated ordered history
仍能在 baseline 之上产生额外方向性沉积。

**当前 master 状态：**
- `fbd32c5` — CI (pytest) 已加入
- tag: `phase-9D-structural-consolidation`, `phase-9D-merged-mainline`
- 275 tests pass

### 为什么需要 Phase 10

9D 验证的是 "event order can be deposited as structure"。
但 9D 的 event schedule 是 **实验者预设的**：

```python
for i in range(n_pairs):
    schedule.append((t, "L", duration))
    schedule.append((t + gap, "R", duration))
```

真实的世界经历不是预设 schedule。下一个 event 发生什么、什么时候发生、
发生在哪一侧，应该受 system state 和 world state 影响。这就是 Phase 10
要推进的核心变化：**从 open-loop designer schedule → closed-loop world feedback。**

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

1. **闭环 vs 开环等价性：** 同样数量、强度的事件序列，如果是
   state-feedback 生成的，和预设 schedule 产生的结构是否不同？
2. **历史分叉：** 同一初始状态 + 同一 world rule，不同 seed 产生的
   event history 是否分叉？分叉后的结构差异是否可测？
3. **反馈强度：** feedback 多强才能产生显著的结构差异？太弱 → 退化为
   开环；太强 → 不稳定/饱和。
4. **沉积积累：** 在闭环中，slow weight 是否持续累积，还是快速饱和？

---

## 3. 不做什么

- 不做游戏、不做 NPC
- 不做 LLM / 人格字段 / 语言层
- 不做意识声明
- 不做复杂社会模拟
- 不直接跳多智能体
- 不调参追结果
- 不把 Phase 9D 的结论改成 "足够"（9D 验证的是机制，Phase 10 验证的是闭环条件）

---

## 4. Phase 10A 最小路线

```
10A.0: closed-loop event scheduler design (design only)
10A.1: single-seed closed-loop smoke (local)
10A.2: open-loop vs closed-loop matched control
10A.3: 4-seed validation (ECS)
10A.4: geometry-aware / history-aware diagnostics
```

### 10A.0 — Scheduler Design

- 定义 `world_state` 的最小变量集合
- 定义 event generation rule：基于 state 的 event probability function
- event 被写成 `StimulusEvent` / phi（复用 Phase 9C 基础设施）
- 事件进入 event-pair plasticity 管线（Phase 9C）
- 长期沉积由 9D consolidation 负责

### 10A.1 — Single-Seed Closed-Loop Smoke

- 最小闭环：1 个 world variable + 简单的 state → event probability 映射
- 验证：闭环不爆炸、不 NaN、slow weight 有累积
- runtime: < 15 min local

### 10A.2 — Open-Loop vs Closed-Loop Matched Control

- 配对的实验设计：closed-loop run → 记录 event history →
  用同样的 event history 做 open-loop replay
- 比较 closed-loop 和 open-loop replay 的结构差异
- 核心假设：如果闭环仅是开环的随机化，closed ≈ open replay；
  如果闭环有 state-feedback 效应，closed ≠ open replay

### 10A.3 — 4-Seed Validation

- 标准 ECS 4P 并行，4 seeds (42, 77, 123, 999)
- 验证跨 seed 的一致性和可重复性

### 10A.4 — Diagnostics

- geometry-aware metrics（复用 9D.3 框架，如果需要）
- event history 分叉可视化
- slow structure per-unit / per-region 热图
- 开环 vs 闭环结构距离

---

## 5. 最小环境

### World State

```
world_state: 少数连续变量 (1-3 个)
例如:
  - region_activity_L
  - region_activity_R
  - recent_event_density

这些变量从 LifeCore state 中提取，不是自由参数。
```

### Event Generation

```
event_probability = f(world_state)
event_type = g(world_state)
event_timing = h(world_state, last_event_time)

f, g, h 是简单函数（affine / sigmoid / threshold），不是学习模型。
event 被编码为 Stimulus + phi。
```

### Event History → Structure

```
event → Environment.phi_vector → LifeCore.apply_event_pair_phi
  → event-pair dW (Phase 9C)
  → tag accumulation
  → capture signal → slow_weight write (Phase 9D)
```

不新增机制。复用 9C + 9D 管线。

---

## 6. Primary Metrics

| Metric | What It Measures |
|--------|-----------------|
| event_history_divergence | 同 seed 不同 run / 不同 seed 同 rule 的事件序列差异 |
| slow_structure_l1 | slow weight 总质量 |
| corrected_slow_DI | 如有方向性分析，复用 9D.3 geometry-aware metric |
| open_vs_closed structural distance | closed-loop 与 matched open-loop replay 的结构距离 |
| same-seed reproducibility | 同 seed 多次 run 的结果一致性 |
| cross-seed robustness | 不同 seed 的方向/幅度一致性 |
| no_event / random_event controls | 基线控制 |

---

## 7. Success Criteria

### 7.1 Primary

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| closed ≠ open replay structure | measurable L1 or DI difference | state feedback has effect beyond random event ordering |
| difference not explained by event count/intensity/total stimulus | matched control | rules out trivial confounds |
| slow_weight 不爆炸 | max_abs < clamp | pipeline stable under closed loop |
| no NaN | 0 | — |

### 7.2 Secondary (Reported, Not Gated)

| Criterion | Threshold |
|-----------|-----------|
| 4-seed ≥ 3/4 方向或机制一致 | qualitative |
| same-seed reproducibility | qualitative |
| 累计 event 数在合理范围内 | no event explosion |

---

## 8. Anti-Cheat Boundaries

- **Scheduler 不能读取 arm label。** event generation 不知道自己在哪个实验组。
- **Scheduler 不能直接写目标结构。** event generation 输出 event，不输出 slow_weight。
- **Event generation 只能通过当前 state / world variables。** 无历史回望，无 oracle。
- **不允许根据实验组硬编码 event。** 同一个 scheduler rule 用于所有 arm。
- **不允许把 desired outcome 写进 reward / gate / target。** 没有 reward。
- **Diagnostics offline only。** 不可在线影响 event 选择。

---

## 9. Runtime Policy

| Scope | Platform | Notes |
|-------|----------|-------|
| Single-seed quick smoke | local | < 15 min |
| 4-seed validation | ECS 4P | ~12-18 min wall time |
| Matched control pairs | ECS parallel | per-seed pair parallel |

ECS: `i-7xvduf6m2y77m915mhr5`, 4C8G, cn-guangzhou.
实验前确认 IP，跑完收结果关机。

---

## 10. 与 Phase 9D 的关系

| Aspect | Phase 9D | Phase 10A |
|--------|----------|-----------|
| Event source | designer-specified schedule | state-feedback scheduler |
| Question | can event order deposit? | can world history shape? |
| Event generation | fixed L/R paired | world_state → probability → event |
| Metrics | slow_DI, corrected_slow_DI | + event_history_divergence, open_vs_closed distance |
| Control | simultaneous, no_event | + matched open-loop replay |
| Status | completed, in master | planning |

9D 证明事件顺序能沉积为长期结构。
10A 要测试事件历史由系统状态反馈生成时，是否还能沉积为结构——
以及这个结构与 open-loop replay 是否可区分。

**9D 是骨头会记住。Phase 10 要问：世界能不能持续雕刻这副骨头。**

---

## 11. 参考

- `docs/phase9D_summary.md` — 9D evidence chain
- `docs/phase9D_to_phase10_transition.md` — transition rationale
- `docs/phase9D3_geometry_aware_consolidation_validation_design.md` — geometry-aware design
- `aniva/experiments/exp9D3_geometry_aware_validation.py` — runner reference
