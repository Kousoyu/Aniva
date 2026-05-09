# Phase 9C.4 — Full Integration Smoke Design

> **定位：** full integration smoke, not new validation.
> 验证 300-unit core path 是否能复现 9C.3 diagnostic script 的基础机制行为。
> 对照目标：9C.3 seed42 sequential arms。

---

## 1. 为什么 quick smoke 不足以解释方向性

| 维度 | quick smoke | 9C.3 diagnostic |
|------|:-----------:|:---------------:|
| unit_count | 50 | 300 |
| num_pairs | 2 | 5 |
| rest_window | 500 | 5000 |
| phi coverage | 1-3 units | ~70-90 units |
| trace_mass | ~0.006-0.01 | ~0.03-0.06 |
| gate | 0.17-0.51 | 1.0 (within) / 0.02-0.04 (cross) |
| L→R connections | ~30 | ~500-600 |

quick smoke 验证了**链路接通**（plumbing），但因网络极度稀疏，phi 到 trace 的信号量只有 9C.3 的 ~3-6%，gate 无法进入正常动态范围，方向性指标（acc_dW_OS、contamination）由随机拓扑主导，无解读意义。

**不需要从 quick smoke 的结果推断 300-unit behavior。** 需要 full smoke。

---

## 2. 目标

用 300-unit core path（`Environment.phi_vector` → `LifeCore.apply_event_pair_phi` → `plasticity_event_pair.apply_event_pair_update`）运行与 9C.3 seed42 sequential arms **完全相同的 schedule**，验证：

1. core path 的 dW ledger 行为与 diagnostic script 一致
2. gate_w ≈ 1.0, gate_c ≪ gate_w
3. contamination < 0.05
4. acc_dW_OS 强正
5. 0 NaN / 0 explosion

**这不是新 validation — 9C.3 已经做完 4-seed validation。** 这只是确认机制从 diagnostic script 搬进 core 后没有退化。

---

## 3. 固定参数

| 参数 | 值 | 出处 |
|------|-----|------|
| seed | 42 | 9C.3 seed 之一 |
| unit_count | 300 | 标准 scale |
| gap | 500 | 9C.1 |
| tau_trace | 1000 | 9C.1 |
| target_event_update_l1 | 1e-4 | 9C.1A |
| trace_gate_ref | 3e-2 | 9C.1C |
| gate_power | 1.0 | 9C.1C |
| rest_window | 5000 | washout |
| num_pairs | 5 | 9C.1 |
| gate_mode | soft_trace_gate | — |
| arms | L_then_R, R_then_L | sequential only |

---

## 4. Schedule（per arm）

```
warmup: 200 steps
num_pairs: 5
pair_interval = gap + pulse_dur + rest_window = 500 + 80 + 5000 = 5580
total_steps = 200 + 5 * 5580 + 200 = 28300
```

### Stimulus

```
L stimulus: position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5
R stimulus: position=(+0.5, 0.0, 0.0), intensity=0.02, radius=0.5
pulse_duration: 80 steps
```

---

## 5. 与 9C.3 diagnostic script 的对应关系

| 环节 | 9C.3 diagnostic (`exp9C1C_trace_gated_update.py`) | 9C.4 core path |
|------|--------------------------------------------------|----------------|
| trace 管理 | 实验脚本手动 `trace` numpy 数组 | `LifeCore._event_trace` |
| trace decay | 事件到达时 `trace *= exp(-dt/tau)` | 每步 `LifeCore.step()` 中 decay |
| phi 生成 | 实验脚本 `_compute_phi()` | `Environment.phi_vector()` |
| update 触发 | 实验脚本在 schedule step 检测并调用 `_apply_trace_gated_update()` | 实验脚本调用 `LifeCore.apply_event_pair_phi()` |
| gate 计算 | 实验脚本内联 | `plasticity_event_pair.apply_event_pair_update()` |
| dW 应用 | 实验脚本 per-connection loop | `apply_event_pair_update()` 向量化 |
| dW 方向分类 | 实验脚本 `_classify_connection()` | 实验脚本 offline（同逻辑） |
| Hebbian plasticity | **不启用** (`temporal_plasticity_enabled=False`) | **启用**（`plasticity_rate=0.0001`） |

**关键差异：** 9C.4 core path 中 Hebbian plasticity 是一直开着的（正常 LifeCore.step），而 9C.3 diagnostic 关闭了 temporal_plasticity。Hebbian 会产生连续微小 dW，叠加在 event-pair dW 上。full smoke 需要检查 Hebbian 共存是否会淹没 event-pair 方向性信号。

若 Hebbian 噪声显著影响方向性，这是合理发现（不是 bug），应如实记录，后续可通过调节 `plasticity_rate` 或 `event_pair_target_update_l1` 的比例来平衡。

---

## 6. 成功标准

- [ ] schedule_ok: all true（L=5, R=5 per arm）
- [ ] mean_gate_within ≈ 1.0（≥ 0.95）
- [ ] mean_gate_cross < 0.05
- [ ] gate_cross / gate_within ≥ 10x gap
- [ ] contamination_ratio < 0.05（per arm）
- [ ] acc_dW_OS > 0（方向与 9C.3 一致为正）
- [ ] 0 NaN
- [ ] 0 weight explosion（|weight| ≤ 1.0 全程）
- [ ] CSV / JSON 输出完整

9C.3 seed42 reference:

| Metric | 9C.3 seed42 |
|--------|:-----------:|
| acc_dW_OS | +1.949 |
| contam (max) | 0.017 |
| gate_w | 1.000 |
| gate_c | 0.023-0.027 |

**不要求 bit-identical。** 允许 Hebbian 共存导致的合理偏差。若 acc_dW_OS 降至 < 0.5 或 contamination > 0.1，视为需要调查的信号。

---

## 7. 失败标准

- [ ] acc_dW_OS ≤ 0（方向性丢失）
- [ ] contamination > 0.1（跨对污染严重）
- [ ] gate_w < 0.5（核心 gating 失效）
- [ ] gate_c > 0.1（跨对 gate 过高）
- [ ] NaN / explosion
- [ ] 事后调参才通过

失败时不自动 pivot。先诊断是 plumbing bug 还是 Hebbian 共存比例问题。

---

## 8. 边界声明

| 验证了什么 | 没验证什么 |
|-----------|-----------|
| core path 在 300-unit 下复现 9C.3 基础行为 | 多 seed 泛化（那是 9C.3 的事） |
| Hebbian + event-pair 共存不爆炸 | 最优 Hebbian/event-pair 比例 |
| seed42 single-arm 行为 | seed77/123/999 |
| 链路完整性和参数流正确 | 机制是否在各种 gap/tau/num_pairs 下鲁棒 |

---

## 9. Runtime 估算

- 9C.3 on ECS: ~9 min per arm（300 units, ~28300 steps, ~4500 connections）
- 9C.4 core path 结构一致（LifeCore.step 完全相同），per-arm 时间应接近
- 2 arms × ~9 min = **~18 min on ECS 4-core**
- 本地 Windows：预计 ~25-40 min per arm，**总计 50-80 min**

**默认上 ECS。** 本地不硬跑。

---

## 10. ECS 执行策略

- 2 arms × 1 seed = 2 个独立进程
- 每进程独立日志：`logs/phase9C4_full_integration_smoke_seed42_{arm}.log`
- 每 arm 独立 CSV（合并为最终文件）
- 执行前确认 ECS 状态、同步代码
- 跑完合并结果、停机、commit

---

## 11. 输出

- `results/phase9C4_full_integration_smoke_seed42_seq.csv`
- `results/phase9C4_full_integration_smoke_seed42_seq_summary.json`
- `aniva/experiments/exp9C4_full_integration_smoke.py`

---

## 12. 纪律

- 先写 design → commit → 再实现脚本 → 再上 ECS 跑
- 不调参
- 不改机制公式
- 不在 update 路径加 arm label
- 不自动 9D
- 失败如实记录，不事后解释为成功
