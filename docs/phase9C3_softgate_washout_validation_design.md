# Phase 9C.3 — soft_trace_gate + washout validation design

> **定位：** formal validation design，不是立即运行。
> 目标：验证 9C.2 two-seed pilot positive trend 是否能扩展到更多 seeds，排除 seed-specific artifact 和 control false positive。

---

## 1. 背景

9C.2 pilot 在 seed42 和 seed999 上得到：

| Metric | seed42 | seed999 |
|--------|:------:|:------:|
| acc_dW_OS | +1.949 | +1.938 |
| contam (max) | 0.017 | 0.016 |
| gate_w | 1.000 | 1.000 |
| gate_c | 0.023-0.027 | 0.028-0.029 |

**待验证的问题：**
- 这个信号是否会扩展到 seed 77 和 seed 123？
- 四 seed 下对照组是否仍保持干净？
- 是否存在仅在某些 seed 上出现的退化模式？

---

## 2. 继承机制（从 9C.2 锁定，不改）

| 机制要素 | 规定 |
|----------|------|
| 更新核 | event-pair pulse vector × O(N) trace |
| gate 模式 | **soft_trace_gate only** |
| gate 公式 | `dW = target * gate * raw / raw_l1`，`gate = min(1, trace_mass/ref)^power` |
| 反作弊 | 更新路径中无 arm 标签、无 L/R 标签、无 order 知识 |
| 对照 | bare_l1_norm 不跑（引用 9C.1B 作为历史对照） |

---

## 3. 固定参数

| 参数 | 值 | 出处 |
|------|-----|------|
| seeds | **42, 77, 123, 999** | Phase 9 四 seed 标准集 |
| gap | 500 | 9C.1 |
| tau_trace | 1000 | 9C.1 |
| target_event_update_l1 | 1e-4 | 9C.1A |
| trace_gate_ref | 3e-2 | 9C.1C |
| gate_power | 1.0 | 9C.1C |
| rest_window | 5000 | washout / trial-isolated |
| num_pairs | 5 | 9C.1 |
| gate_mode | soft_trace_gate only | — |

---

## 4. 实验模式

| 模式 | 说明 |
|------|------|
| OFF | no plasticity，基线对照 |
| event_pair_softgate | soft_trace_gate event-pair update（主模式） |

---

## 5. Arms

| Arm | 含义 | 用途 |
|-----|------|------|
| L_then_R | L 先 R 后，gap=500 | 主测 |
| R_then_L | R 先 L 后，gap=500 | 主测 |
| simultaneous | L 和 R 同时 | 假阳性检测 |
| separated_control | L 和 R 隔离（gap = interval/2） | 假阳性检测 |

---

## 6. Primary metrics

- `acc_dW_OS` — 主测 arms 的 acc_dW_DI 差（核心指标）
- `contamination_ratio` — cross / (within + cross)
- `mean_gate_within` — 对内事件平均 gate
- `mean_gate_cross` — 跨对事件平均 gate
- `within_pair_dW_L1` — 对内 dW 总量
- `cross_pair_dW_L1` — 跨对 dW 总量
- control arm directional consistency — simultaneous / separated_control 的 acc_dW_DI 跨 seed 稳定性
- `schedule_ok` — 计数器校验
- `saturation_frac` — 边界饱和比
- NaN check — 任何 NaN 直接判定失败

---

## 7. Secondary metrics

- `final_DI` — 最终权重 DI
- `final_OS` — 主测 arm 的 final_DI 差
- `OFF_OS` — OFF baseline OS
- `lr_weight_l1` / `rl_weight_l1` — 区域连接强度
- `mean_trace_mass` — 平均 trace 量

---

## 8. Success criteria

- [ ] 4 个 seed 中 ≥ 3 个满足：contamination < 0.05
- [ ] acc_dW_OS 在 ≥ 3 个 seed 上保持正向且显著高于 OFF baseline（≥ 100x）
- [ ] mean_gate_within ≈ 1.0 跨所有 seed
- [ ] mean_gate_cross ≪ mean_gate_within（至少 10x 差距）跨所有 seed
- [ ] simultaneous gate_w ≈ gate_c（无时间不对称），acc_dW_DI 跨 seed 方向不一致
- [ ] separated_control contamination > 0.2，acc_dW_DI 跨 seed 方向不一致
- [ ] 0 NaN，0 explosion，saturation_frac 可接受
- [ ] schedule_ok 全部通过

---

## 9. Failure criteria

- [ ] 仅 seed42 和 seed999 通过，seed77 或 seed123 明显退化
- [ ] 对照组出现稳定跨 seed 方向性信号
- [ ] 即使 washout 下 contamination 在多个 seed 上 ≥ 0.1
- [ ] 任何 NaN / 爆炸 / saturation 使结果不可解读
- [ ] final_DI 不可见方向性不是自动失败（与 dW ledger 分开判定）
- [ ] 依赖事后调参才通过

---

## 10. Execution plan（执行时再确认）

- ECS 4-seed 并行（4 进程，每 seed 一个进程跑所有 4 arms）
- 预计 total wall time ~46 min（ECS 4 核并行）
- 每 seed 独立 CSV/JSON/log
- 跑完合并、汇报、commit

---

## 11. 纪律

- **不在看到验证结果后调参。** 任何失败都如实记录。
- **不自动启动 9C.4。** 验证完成后等待判断。
- **不 pivot 到 BTSP。** 除非 9C.3 在此 locked 设置下明确全面失败。
- **不加 LLM / reward / agent / goal / emotion / personality / language。**
- **不使用 bare_l1_norm。**
- **final_DI/OS 遮盖不被视为机制失败，但必须如实报告。**

---

## 12. 预期输出

- `results/phase9C3_validation.csv` — 合并后
- `results/phase9C3_validation_summary.json`
- `docs/phase9C3_softgate_washout_validation_notes.md` — 跑后分析
- 脚本：`aniva/experiments/exp9C3_softgate_washout_validation.py`
