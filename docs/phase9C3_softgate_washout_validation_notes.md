# Phase 9C.3 — soft_trace_gate + washout validation notes

> **定位：** formal validation positive under pre-registered setup (commit 28224ec)。
> 不是 broader digital-life validation。这是对 9C-EPT + soft_trace_gate + washout 事件对塑性机制在 dW ledger 层面的 formal 验证。

---

## 1. 执行信息

| 项 | 值 |
|---|-----|
| 预注册 commit | 28224ec |
| 执行日期 | 2026-05-08 |
| 环境 | 阿里云 ECS (4 vCPU, 8 GiB)，两波 × 4 进程并行 |
| 总 wall time | ~38 min |

## 2. 参数

| 参数 | 值 |
|------|-----|
| seeds | 42, 77, 123, 999 |
| gap | 500 |
| tau_trace | 1000 |
| target_event_update_l1 | 1e-4 |
| trace_gate_ref | 3e-2 |
| gate_power | 1.0 |
| rest_window | 5000 |
| num_pairs | 5 |
| gate_mode | soft_trace_gate only |
| arms | L_then_R, R_then_L, simultaneous, separated_control |

## 3. 主测结果

| Seed | acc_dW_OS | contam (max) | gate_w | gate_c range | LTR acc_dW_DI | RTL acc_dW_DI |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| 42 | **+1.949** | 0.017 | 1.000 | 0.023–0.027 | +0.966 | -0.983 |
| 77 | **+1.936** | 0.021 | 1.000 | 0.026–0.030 | +0.957 | -0.979 |
| 123 | **+1.920** | 0.021 | 1.000 | 0.040–0.042 | +0.958 | -0.962 |
| 999 | **+1.938** | 0.016 | 1.000 | 0.028–0.029 | +0.967 | -0.971 |

- schedule_ok: 16/16
- NaN: 0
- saturation_frac: 0

## 4. 对照结果

| Seed | simultaneous acc_dW_DI | sep_control acc_dW_DI | sim gate_w≈gate_c? |
|------|:--:|:--:|:--:|
| 42 | +0.163 | -0.181 | ✓ (0.019≈0.019) |
| 77 | -0.198 | -0.236 | ✓ (0.021≈0.021) |
| 123 | -0.284 | +0.207 | ✓ (0.031≈0.031) |
| 999 | -0.365 | +0.180 | ✓ (0.021≈0.021) |

Simultaneous 和 separated_control 的 acc_dW_DI 符号跨 seed 不一致，未出现稳定假阳性模式。

## 5. Success criteria 判定

| 准则 | 要求 | 实际 | 结果 |
|------|------|------|:--:|
| contam < 0.05 | ≥3/4 seeds | 4/4 (max 0.021) | ✓ |
| acc_dW_OS positive | ≥3/4 seeds | 4/4 (+1.920–1.949) | ✓ |
| gate_w ≈ 1.0 | all seeds | 4/4 精确 1.000 | ✓ |
| gate_c ≪ gate_w | ≥10x gap | 23–43x | ✓ |
| simultaneous gate_w ≈ gate_c | all seeds | 4/4 | ✓ |
| controls no stable false-positive | cross-seed inconsistent | 符号不一致 | ✓ |
| NaN / explosion | 0 | 0 | ✓ |
| schedule_ok | all | 16/16 | ✓ |

**4/4 seeds 通过全部 success criteria。0 failure criteria 触发。**

## 6. 证据链

```
9C.1  → trace overlap passed plumbing, update too weak
9C.1A → L1 normalization fixed magnitude, destroyed temporal discrimination
9C.1B → directional dW exists in ledger, bare L1 re-amplifies stale traces
9C.1C → soft_trace_gate restored temporal gating
9C.2  → two-seed pilot positive (42, 999)
9C.3  → four-seed formal validation positive (42, 77, 123, 999)
```

## 7. 局限性

- N=4 seeds，不是更大规模 validation
- final_DI / final_OS 仍被稳态遮盖（已分开报告，不作为主判据）
- 当前仅限于 fixed gap=500, tau=1000, num_pairs=5, rest=5000
- 未测试更密集调度或更长序列

## 8. 后续建议

**不自动启动 9C.4。** 先写 Phase 9C.4 / Phase 9D planning note。

候选方向：
1. 将 soft_trace_gate 并入 core plasticity 路径，不再留在诊断脚本
2. 测试 gap / tau / num_pairs 的鲁棒性
3. 9D：结构固化 / STC-like 长程层
4. BTSP 保留为后备，不再作为立即 pivot
