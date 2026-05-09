# Phase 9C.4 — Integration Smoke Design

> **定位：** 验证 4f67e22 core skeleton 在显式开启后能否复现 9C.3 的基础机制行为。
> 不做正式实验，不做统计。这是 plumbing check，不是 validation。

---

## 1. 目标

验证这条链路能接通：

```
Environment.phi_vector(event, positions)
  → LifeCore.apply_event_pair_phi(phi)
    → plasticity_event_pair.apply_event_pair_update(trace, phi, weights, ...)
      → weight_cache 产生方向性 dW
```

如果这条链路在本地 seed=42 上与 diagnostic script 的 dW ledger 行为一致，则 plumbing 通过。

---

## 2. 固定参数（继承 9C.3）

| 参数 | 值 |
|------|-----|
| seed | 42 |
| gap | 500 |
| tau_trace | 1000 |
| target_event_update_l1 | 1e-4 |
| trace_gate_ref | 3e-2 |
| gate_power | 1.0 |
| rest_window | 5000 |
| num_pairs | 5 |
| gate_mode | soft_trace_gate |
| arms | L_then_R, R_then_L |

---

## 3. Schedule（每 arm）

```
warmup: 2000 steps
num_pairs: 5
pair_interval = gap + pulse_dur + rest_window
pulse_dur: 5 steps
rest_window: 5000
tail_buffer: 500 steps
total_steps = warmup + num_pairs * pair_interval + tail_buffer
```

## 4. Stimulus 定义

```
L stimulus: position=(-0.5, 0, 0), intensity=1.0, radius=0.6
R stimulus: position=(+0.5, 0, 0), intensity=1.0, radius=0.6
```

phi 由 `Environment.phi_vector(event, core._positions)` 生成。

---

## 5. 反作弊约束

- `apply_event_pair_update` 不接受 arm / L / R 标签
- phi 生成来自 `StimulusEvent`，不包含 order 知识
- dW ledger 归集在实验层（offline），更新路径不感知

---

## 6. Primary readout

- `acc_dW_OS` — L_then_R 与 R_then_L 的 dW DI 差
- `gate_w` / `gate_c` — 对内 / 跨对 gate
- `contamination_ratio` — 跨对 dW 占比
- `schedule_ok` — 事件计数校验

## 7. Acceptance criteria

- [ ] 默认配置下旧行为不变（regression 已由 pytest 243/243 保证）
- [ ] event_pair_plasticity_enabled=True 时链路不报错
- [ ] gate_w ≈ 1.0, gate_c ≪ gate_w（≥ 10x gap）
- [ ] acc_dW_OS 为正且方向与 9C.3 diagnostic 一致
- [ ] contamination < 0.05
- [ ] 0 NaN
- [ ] schedule_ok

## 8. 不接受

- [ ] 调参来凑指标
- [ ] 改 plasticity_event_pair 逻辑
- [ ] 在 update 路径加 arm 标签

---

## 9. 执行纪律

- 本地单 seed，不上 ECS
- 若预计超过 10 分钟，先汇报再决定
- 跑完仅汇报核心指标，不 commit 结果文件
- 如果 plumbing 不通，debug 不改机制公式
