# Phase 9C.2 — soft_trace_gate + washout pilot notes

> **定位：** two-seed pilot positive trend，不是 formal validation。
> **结论：** soft_trace_gate + washout 在 seed42 和 seed999 上均产生低污染、方向一致的 event-pair directional dW 信号。9C-EPT 核心机制成立可能性明显上升。

---

## 1. 执行参数

| 参数 | 值 |
|------|-----|
| seeds | 42, 999 |
| gap | 500 |
| tau_trace | 1000 |
| target_event_update_l1 | 1e-4 |
| trace_gate_ref | 3e-2 |
| gate_power | 1.0 |
| rest_window | 5000 |
| num_pairs | 5 |
| gate_mode | soft_trace_gate only |
| arms | L_then_R, R_then_L, simultaneous, separated_control |
| 并行 | ECS 4 进程 (seed×arm 分组) |
| 总 wall time | ~19 min (ECS), ~92 min estimated (local) |

## 2. 主测结果 (L_then_R / R_then_L)

| Metric | seed42 | seed999 |
|--------|:------:|:------:|
| gate_w (LTR) | 1.000 | 1.000 |
| gate_w (RTL) | 1.000 | 1.000 |
| gate_c (LTR) | 0.027 | 0.028 |
| gate_c (RTL) | 0.023 | 0.029 |
| contam (LTR) | 0.017 | 0.016 |
| contam (RTL) | 0.009 | 0.015 |
| within_dW (LTR) | 4.95e-04 | 4.98e-04 |
| within_dW (RTL) | 4.99e-04 | 4.96e-04 |
| cross_dW (LTR) | 8.61e-06 | 8.24e-06 |
| cross_dW (RTL) | 4.37e-06 | 7.44e-06 |
| acc_dW_DI (LTR) | +0.966 | +0.967 |
| acc_dW_DI (RTL) | -0.983 | -0.971 |
| **acc_dW_OS** | **+1.949** | **+1.938** |
| OFF_OS | -2.54e-06 | -1.19e-05 |

- schedule_ok: 8/8 true
- NaN: 0
- saturation_frac: 0 (无连接触及 ±1 边界)

## 3. 对照结果

| Arm | seed42 acc_dW_DI | seed999 acc_dW_DI |
|-----|:--:|:--:|
| simultaneous | +0.163 | -0.365 |
| separated_control | -0.181 | +0.180 |

- 对照组产生的 directional ledger 信号远弱于主测组
- simultaneous 的 gate_w ≈ gate_c（~0.02），无时间不对称性
- separated_control 的 contamination ~0.4-0.6，符号跨 seed 不一致
- **结论：** controls produced smaller, seed-inconsistent directional ledger signals, not the strong seed-consistent OS pattern seen in sequential arms.

## 4. 跨 seed 一致性

| 指标 | 评估 |
|------|------|
| 低污染 | ✓ 两 seed 均 < 0.02 |
| gate_w ≈ 1.0 | ✓ 两 seed 完全一致 |
| gate_c ≈ 0.02-0.03 | ✓ 两 seed 一致 |
| acc_dW_OS 稳定性 | ✓ +1.949 vs +1.938（0.6% 差异） |
| 对照组无假阳性模式 | ✓ 信号弱且跨 seed 方向不一致 |

## 5. 证据链位置

```
9C.1 smoke  → plumbing passed, update magnitude underpowered
9C.1A       → L1 normalization destroys temporal discrimination
9C.1B       → directional dW exists (acc_dW_OS 11500x OFF), L1-norm is culprit
9C.1C       → soft_trace_gate restores temporal gating, contam drops 23x
9C.2 pilot  → soft_trace_gate + washout generalizes to seed999 (this note)
```

9C.2 的结果和 9C.1C 诊断证据完美衔接，没有出现 seed-specific 退化。

## 6. 局限性

- N=2 seeds，不是 formal 4-seed validation
- final_DI / final_OS 仍被稳态遮盖（但已分开报告，不作为主判据）
- 当前 washout rest=5000 等价于 trial-isolated schedule，未测试更密集调度
- 未在控制臂中检测到假阳性模式，但信号不完全为零

## 7. 下一步建议

- **先写 9C.3 validation design，不自动开跑**
- 9C.3 应考虑：4-seed validation, 固定 soft_trace_gate + washout, 可选增加 num_pairs sweep
- 不转 BTSP，不引入标签式更新
- final_DI 遮盖问题可以在 9C.3 后单独开诊断分支处理
