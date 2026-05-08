# Phase 9C.4 — Integration Smoke Notes

> **定位：** plumbing check, not scientific validation.
> 验证 core skeleton 链路接通，不验证 9C.3 指标复现。

---

## 1. 目的

确认 `4f67e22` 的 core skeleton 在显式开启后三条链路能接通：

```
Environment.phi_vector → LifeCore.apply_event_pair_phi → plasticity_event_pair.apply_event_pair_update
```

---

## 2. 参数

| 参数 | 值 |
|------|-----|
| mode | quick |
| unit_count | 50 |
| seed | 42 |
| gap | 500 |
| tau_trace | 1000 |
| num_pairs | 2 |
| rest_window | 500 |
| gate_mode | soft_trace_gate |
| target | 1e-4 |
| trace_gate_ref | 3e-2 |
| gate_power | 1.0 |
| arms | L_then_R, R_then_L |

---

## 3. 结果

| 检查项 | 结果 |
|--------|:--:|
| schedule_ok | ALL (2/2) |
| phi_nonzero | yes |
| ledger_nonempty | yes (4 entries/arm) |
| trace_mass nonzero | yes |
| gate computed | yes |
| dW_l1 nonzero | yes |
| NaN | none |
| CSV complete | yes |
| JSON complete | yes |
| runtime | ~2.5s |

---

## 4. 重要说明

quick mode 下 unit_count=50，stimulus radius=0.5 在 [-1,1]^3 空间中仅覆盖 1-3 个单元，
trace_mass 极小，方向性指标（acc_dW_OS / within / cross）无解读意义。

**本 smoke 不尝试复现 9C.3 acc_dW_OS。** 正式 full integration smoke 应使用 300 units +
rest=5000 参数，单独设计为 core path vs diagnostic script 对照实验。

---

## 5. 结论

Core skeleton 链路接通，plumbing passed。`event_pair_plasticity_enabled=False` 时
旧行为不受影响（pytest 243/243）。
