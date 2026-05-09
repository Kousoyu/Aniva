# Phase 9C.2 — soft_trace_gate + washout pilot design

> **定位：** two-seed pilot，不是 formal validation。
> 目标：验证 9C.1C 诊断阳性是否能从 seed=42 扩展到 seed=42,999，确认 soft_trace_gate + washout 是否稳定产生 event-pair directional dW。

---

## 1. 背景

9C.1C 在 seed=42、rest=5000、soft_trace_gate 下得到：

| Arm | gate_w | gate_c | contamination | acc_dW_DI |
|-----|:------:|:------:|:------------:|:---------:|
| L_then_R | 1.000 | 0.027 | 0.017 | +0.966 |
| R_then_L | 1.000 | 0.023 | 0.009 | -0.983 |

- acc_dW_OS = +1.949，OFF_OS = -2.54e-06
- 跨对污染被压到 ~1%，对内信号保留

**待回答的问题：** 这个结果是否对 seed 敏感？simultaneous / separated_control 是否会产生假阳性？

---

## 2. 固定设置

| 参数 | 值 | 出处 |
|------|-----|------|
| seeds | 42, 999 | — |
| gap | 500 | 9C.1 |
| tau_trace | 1000 | 9C.1 |
| target_event_update_l1 | 1e-4 | 9C.1A calibration |
| trace_gate_ref | 3e-2 | 9C.1C |
| gate_power | 1.0 | 9C.1C |
| rest_window | 5000 | washout / trial-isolated |
| num_pairs | 5 | 9C.1 |
| gate_mode | **soft_trace_gate only** | 不跑 bare_l1_norm（引用 9C.1B 作为对照） |

## 3. 实验模式

| 模式 | 说明 |
|------|------|
| OFF | no plasticity，基线对照 |
| event_pair_softgate | soft_trace_gate event-pair update（主模式） |

## 4. Arms

| Arm | 含义 |
|-----|------|
| L_then_R | L 先 R 后，gap=500 |
| R_then_L | R 先 L 后，gap=500 |
| simultaneous | L 和 R 同时（假阳性检测） |
| separated_control | L 和 R 隔离（gap = interval/2，假阳性检测） |

## 5. Primary metrics

- `acc_dW_OS` — L_then_R 和 R_then_L 的 acc_dW_DI 差
- `within_pair_dW_L1` — 对内方向 dW 总量
- `cross_pair_dW_L1` — 跨对方向 dW 总量
- `contamination_ratio` — cross / (within + cross)
- `mean_gate_within_pair` — 对内事件平均 gate 值
- `mean_gate_cross_pair` — 跨对事件平均 gate 值
- `schedule_ok` — event_count_L == event_count_R == num_pairs
- `saturation_frac` — 权重触及 ±1 边界的连接比例

## 6. Secondary metrics

- `final_DI` — 最终权重结构的方向指数
- `final_OS` — L_then_R 和 R_then_L 的 final_DI 差
- `lr_weight_l1` — L→R 区域连接 l1 均值
- `rl_weight_l1` — R→L 区域连接 l1 均值
- `OFF_OS` — OFF baseline 的 OS

## 7. Success criteria

- [ ] 两个 seed 在 soft_trace_gate 下跨对污染均低（< 0.05）
- [ ] mean_gate_within_pair ≈ 1.0（热 trace 全量通过）
- [ ] mean_gate_cross_pair ≪ within gate（至少 10x 差距）
- [ ] L_then_R 和 R_then_L 的 acc_dW_DI 符号相反
- [ ] simultaneous 和 separated_control 不产生同等量级的方向性信号
- [ ] acc_dW_OS 显著高于 OFF baseline / 9C.1B bare_l1_norm reference

## 8. Failure criteria

- [ ] 仅 seed=42 通过，seed=999 不通过
- [ ] simultaneous / separated_control 显示与 L_then_R / R_then_L 相似的方向性
- [ ] 即使 washout 下 contamination 仍然高（≥ 0.3）
- [ ] final weight 仍不可见方向性（不是自动失败，但必须与 dW ledger 分开报告）
- [ ] 任何 NaN / 爆炸 / saturation 导致结果不可解读

## 9. 纪律

- **不在看到 seed 999 结果后调参。** 如果 seed 999 是阴性，如实记录，不回补重新调。
- **不自动启动 9C.3。** 9C.2 结束后等待判断。
- **不 pivot 到 BTSP。** 除非 9C.2 在此 pre-registered 设置下明确失败。
- **不加 LLM / reward / agent / goal / emotion / personality / language。**
- **不使用 bare_l1_norm（引用 9C.1B 作为历史对照即可）。**

## 10. 输出

- `results/phase9C2_softgate_washout_pilot.csv`
- `results/phase9C2_softgate_washout_pilot_summary.json`
- 脚本：`aniva/experiments/exp9C2_softgate_washout_pilot.py`
