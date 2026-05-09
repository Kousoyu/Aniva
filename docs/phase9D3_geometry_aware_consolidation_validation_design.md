# Phase 9D.3 — Geometry-Aware Consolidation Validation Design

> **定位：** formal validation protocol design。
> 9D.2 diagnostic chain 已完成：simultaneous +0.1635 = geometry_projection_asymmetry。
> 9D.3 不再问"河床有没有坡"，而是问"在已知河床有坡的情况下，
> 重复历史有没有额外刻出自己的沟痕"。

---

## 1. 背景

### 9D.1–9D.2 回顾

| Stage | Result | Key Finding |
|-------|--------|-------------|
| 9D.1 | plumbing passed | 7-gear chain 全部啮合 |
| 9D.2 | caveated positive | main signal strong (slow_OS +0.718), simultaneous +0.164 > |DI|<0.1 |
| 9D.2A | topology/phi/position/ordering ruled out | swapped, combined-phi — bias persists |
| 9D.2B.1 | decomposition | dW_DI = +0.1635, tag/capture/slow are lossless |
| 9D.2C | projection root | raw_DI = dW_DI = +0.1635, trace×phi geometry × directed topology |

**核心结论：** 9D consolidation pipeline 是干净的。simultaneous +0.1635 不是
mechanism-level false positive，是 combined L+R phi 场在有向 LR/RL 连接拓扑上
的固有几何投影不对称。

### 9D.3 的定位

9D.3 不再是"ability smoke"（9D.2），而是**带有 geometry-aware controls
的 formal validation**。目标：验证 ordered repeated event histories 是否在
已知几何基线之上产生显著的、方向正确的额外结构沉积。

**核心问题变了：**

```
旧: simultaneous |DI| < 0.1 ?     →  naive zero-baseline
新: ordered slow_DI > raw_projection_baseline ?  →  geometry-aware
```

---

## 2. 新指标

### 2.1 Geometry Baseline

```
geometry_baseline_DI = simultaneous combined-phi raw_projection_DI。

这是全局几何地形基线，不是每个 arm 各算一套不同的 baseline。
对于所有 ordered arms（L→R repeated, R→L repeated）和 simultaneous arm，
几何基线来自同一组 combined L+R phi 在 LR/RL 连接拓扑上的投影。

对于 seed=42 参考值（9D.2C 测量）：geometry_baseline_DI = +0.1635。

它代表当前 unit/stimulus/topology 场的固有几何坡度：
  - L→R raw = trace_L × phi_R  (L-hemi trace × R-hemi phi)
  - R→L raw = trace_R × phi_L  (R-hemi trace × L-hemi phi)
  - phi_R mass ≈ 1.8× phi_L mass → LR 投影天然大于 RL

这不是机制缺陷，是地形事实。
```

**为什么所有 arm 共享同一个 geometry baseline：**

simultaneous combined-phi arm 和 ordered repeated arms 的 trace 累积总质量相同
（都是 3 对 combined L+R phi 的累积）。在 raw eligibility 层面（trace[src] × phi[tgt]），
事件的应用顺序不影响累积质量——只影响 tag/capture/slow_weight 这些下游层的方向性。
因此 geometry baseline 对所有 arm 是同一个值。

### 2.2 Corrected Metrics

```
corrected_slow_DI = slow_DI - geometry_baseline_DI

geometry_baseline_DI 是 shared global constant（对给定 seed/unit_count），
不是 per-arm dynamic fitted value。

  - 如果 ordered arm 仅反映几何基线 → corrected_slow_DI ≈ 0
  - 如果 ordered arm 超过了基线 → corrected_slow_DI ≠ 0，
    方向由事件顺序决定
  - 如果 simultaneous corrected_slow_DI ≈ 0 → geometry correction 有效

corrected_slow_OS = corrected_slow_DI(L→R repeated) - corrected_slow_DI(R→L repeated)
  = (slow_DI_LR - baseline) - (slow_DI_RL - baseline)
  = slow_DI_LR - slow_DI_RL
  = original slow_OS

注意：geometry baseline 在 OS 中抵消。corrected_slow_OS = original slow_OS。
这意味着 corrected 指标主要影响 per-arm DI 判读，不影响整体方向分离度。
```

### 2.3 Excess Metrics

```
ordered_excess_LR_l1 = slow_LR_l1_ordered - slow_LR_l1_simultaneous
ordered_excess_RL_l1 = slow_RL_l1_ordered - slow_RL_l1_simultaneous
  - 测量重复有序历史相对于 simultaneous baseline 的额外沉积
  - 不强制要求 simultaneous 本身为零
```

### 2.4 Legacy Metrics (保留)

```
slow_DI, slow_OS, slow_l1_total
repeated_vs_single ratio
no_event slow_l1
saturation_frac
capture_count
tag_mass
NaN count
```

---

## 3. Arms

### Required (6 arms)

| Arm | Event Schedule | Purpose |
|-----|---------------|---------|
| L→R repeated | L then R, 3 pairs | ordered directional signal (L→R) |
| R→L repeated | R then L, 3 pairs | ordered directional signal (R→L) |
| L→R single | L then R, 1 pair | single-pair baseline |
| R→L single | R then L, 1 pair | single-pair baseline |
| simultaneous | L+R combined, 3 pairs | geometry baseline control |
| no_event | no events, 7500 steps | null control |

### Optional (按需启用)

| Arm | Purpose |
|-----|---------|
| matched_geometry_control | matched LR/RL mask simultaneous, 验证 mask-level 偏置 |
| shuffled_mask_control | shuffled LR/RL标签 simultaneous, null distribution |
| phi_symmetric_control | 使用对称 phi (调整 stimulus radius/intensity 使 phi_L_mass ≈ phi_R_mass) |

---

## 4. 成功标准 (Success Criteria)

### 4.1 Directional Pattern

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| corrected_slow_OS | > 0.3 | ordered arms show directional separation above geometry baseline |
| corrected_slow_DI(L→R repeated) | > 0 | direction matches event order (L→R) |
| corrected_slow_DI(R→L repeated) | < 0 | direction matches event order (R→L, opposite) |

**Directional magnitude asymmetry is reported but NOT used as a hard failure
criterion in 9D.3 first validation.** The phi field itself is asymmetric
(phi_R_mass ≈ 1.8× phi_L_mass), so |corrected_LR| and |corrected_RL| may
differ in magnitude even if the mechanism is working correctly. What matters
for 9D.3 is that both arms show direction-correct excess over the shared
geometry baseline — not that the excess is equal in size.

Secondary (reported, not hard-gated):
- ||corrected_LR| − |corrected_RL|| — reported as asymmetry metric
- If one arm passes and the other is borderline, report as asymmetric positive

### 4.2 Repeated > Single

| Criterion | Threshold |
|-----------|-----------|
| slow_l1(L→R repeated) / slow_l1(L→R single) | > 3.0 |
| slow_l1(R→L repeated) / slow_l1(R→L single) | > 3.0 |

### 4.3 Controls

| Criterion | Threshold | Note |
|-----------|-----------|------|
| simultaneous corrected_slow_DI | \|DI\| < 0.1 | geometry-corrected, not raw |
| no_event slow_l1 | = 0 (or < 1e-15) | must be zero |
| simultaneous slow_l1 > 0 | required | events must produce SOME plasticity |

### 4.4 Safety

| Criterion | Threshold |
|-----------|-----------|
| NaN count | 0 |
| slow_weight at max (saturation) | < 5% of connections |
| capture_count | ≥ 1 per arm with events |

### 4.5 Multi-Seed

| Criterion | Threshold |
|-----------|-----------|
| seeds | ≥ 4 (e.g., 42, 77, 123, 999) |
| seeds meeting all criteria | 4/4 (or ≥ 3/4 with caveat) |

---

## 5. 失败标准 (What Would Count as Negative)

| Scenario | Interpretation |
|----------|---------------|
| corrected_slow_DI ≈ 0 for ordered arms | ordered history has no effect beyond geometry |
| corrected_slow_DI(L→R) and corrected_slow_DI(R→L) same sign | directional signal absent or swamped |
| corrected simultaneous \|DI\| ≥ 0.1 | geometry correction insufficient |
| corrected_slow_OS < 0.3 | directional separation too weak |
| no_event slow_l1 > 0 | capture fires without events → mechanism leak |
| repeated ≤ single | no evidence of cumulative history effect |
| results vary wildly across seeds | mechanism is seed-unstable |
| slow_weight near clamp for > 10% connections | over-saturation → pipeline broken |

---

## 6. Geometry Baseline Computation

Geometry baseline 是 **shared global constant**（对给定 seed/unit_count）。
计算一次，所有 arm 共用。离线计算，不进入机制。

```
1. 初始化 LifeCore（不做 step）。
2. 获取 source_indices, target_indices, positions。
3. 分类 LR/RL 连接。
4. 使用 simultaneous combined-phi schedule 模拟 trace 累积：
   - trace = zeros(N)
   - for each event pair (3 pairs):
       phi = phi_L + phi_R  (combined)
       trace += phi          (仅累积，不做 update)
5. 最终 trace = 所有 past combined phi 的总和。
6. 对最终 phi（最后一个 pair 的 combined phi）：
   raw_ij = trace[src] × phi[tgt]
7. geometry_baseline_DI = raw_DI on LR/RL masks。
   = (raw_LR_l1 - raw_RL_l1) / (raw_LR_l1 + raw_RL_l1 + eps)
```

**为什么 simultaneous schedule 足以作为全局 baseline：**
ordered repeated arms（L→R repeated, R→L repeated）的 phi 总累积质量与
simultaneous arm 相同（都是 3 对 L+R phi 的加和）。在 raw eligibility 层面，
累积顺序不影响总质量——只影响下游 tag/capture/slow_weight 层的方向性编码。
因此 simultaneous combined-phi 的 raw projection 是所有 arm 的共享几何基线。

**Single-pair arms：** geometry baseline ≈ 0（仅作近似）。
Single arms 的第一个事件 trace=0（无更新），第二个事件有 past trace 但总累积
只有 1 对 phi，质量远小于 3 对。Single arms 主要用于 repeated > single 的
slow_l1 ratio 比较（Section 4.2），不作为 corrected direction 的主要判据。

---

## 7. 与 9D.2 的关系

| Aspect | 9D.2 | 9D.3 |
|--------|------|------|
| 定位 | behavior smoke | formal validation |
| simultaneous control | raw |DI| < 0.1 | corrected |DI| < 0.1 |
| metric | slow_DI, slow_OS | + corrected_slow_DI, excess_l1 |
| seeds | 1 | ≥ 4 |
| geometry baseline | not used | arm-specific computation |
| 结论 | caveated positive | positive / negative (with evidence) |

**9D.2 的 caveated positive 不因 9D.3 而改变。** 9D.2 是历史记录，
9D.3 是在新认知（geometry_projection_asymmetry）上的新协议。

---

## 8. 边界

- 不修改 9D.2 结论
- 不修改 9D.2 原始 simultaneous |DI| < 0.1 阈值
- 不声称 digital life validation
- 不启动 9D.3 实验（本文档仅为 design）
- 不调参
- 不改机制公式（capture signal / tag / slow_weight 不变）
- geometry baseline 是离线计算，不进入 update/capture/consolidation 机制路径
- 不引入 reward / goal / agent / emotion / LLM

---

## 9. 与后续阶段的关系

- **9D.3 positive：** ordered history 在 geometry baseline 之上产生额外方向性 →
  consolidation 管线可进入 9D.4 更严格的 multi-scale / longer-history validation。
- **9D.3 negative：** corrected 指标与 baseline 无显著差异 →
  当前 consolidation 管线不能区分 ordered vs simultaneous history →
  需在 9D.3 后重新审视 capture gate 的时间粒度或 tag accumulation 机制。
- **9D.3 borderline：** 部分 seeds 通过、部分不通过 →
  报告为 borderline，不夸大为 positive，不隐藏为 negative。

---

## 10. Runtime & Execution

| Scope | Time | Platform |
|-------|------|----------|
| Single arm | ~120s | — |
| 6 arms × 1 seed | ~12 min | local (smoke / dev) |
| 6 arms × 4 seeds | ~48 min local, ~12 min parallel | **ECS required** |

**Default execution strategy:**

```
Single-seed smoke:    local (verify correctness, ~12 min)
4-seed validation:    ECS 4C8G, 4-process seed-level parallelism (~12 min)
```

Local single-seed must pass before ECS multi-seed run is submitted.
Results merged per seed, summary CSV + JSON uploaded.

## 11. 实现规划

```
docs/phase9D3_geometry_aware_consolidation_validation_design.md  ← 本文档 (v2)
aniva/experiments/exp9D3_geometry_aware_validation.py  (实现时创建)
```
