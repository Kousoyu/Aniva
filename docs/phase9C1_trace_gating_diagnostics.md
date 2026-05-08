# Phase 9C.1 — Event-Pair Trace Diagnostic Notes

> 诊断笔记，非论文。记录 9C.1 smoke → 9C.1A → 9C.1B → 9C.1C 四个子阶段的发现链。
> 最终结论：soft_trace_gate 恢复了 trace decay 作为时间门控，跨对污染下降 23x，方向性 dW 信号保留。

---

## 9C.1 — Smoke（原始 event-pair update）

**目的：** 验证 plumbing（trace decay、phi 计算、schedule、update 管线）能跑通。

**设置：** fixed gap=500, sweep tau=[80,200,500,1000,1500], eta=0.01, num_pairs=5, rest=500

**发现：**
- Plumbing passed — schedule 正确、trace decay 正确、phi 计算正确
- DI 变化在 1e-6 到 5e-6 量级，而初始权重 l1 约 0.067
- **update magnitude 欠了 6-10 个数量级**
- eta=0.01 用于 trace * phi 乘积（~1e-4 到 1e-3），出来的 dW 在 1e-6 到 1e-8

**结论：** 管线通了，增益不足。不要写 9C 失败结论。

---

## 9C.1A — Update-Gain Calibration（L1 归一化）

**目的：** 解耦 update 幅度和 trace/phi scale，让 dW 的量级可控。

**公式：** `raw[k] = trace[src] * phi[tgt]` → `dW = target_l1 * raw / sum(|raw|)`

**设置：** fixed tau=1000, sweep target_l1=[1e-6, 1e-5, 1e-4, 1e-3]

**关键发现：**

| target_l1 | OS (L_then_R - R_then_L) |
|-----------|---------------------------|
| 1e-6      | -2.83e-05 (~OFF)          |
| 1e-5      | -2.76e-05 (~OFF)          |
| 1e-4      | -2.61e-05 (~OFF)          |
| 1e-3      | -3.08e-05 (~OFF)          |

- OS 在所有 target 下都紧贴 OFF baseline (-3.19e-05)
- **update 幅度不再欠功率，但方向性信号消失了**
- L1 归一化完全抹除了 trace 量级差异的影响：不管 trace 是热（刚有事件）还是凉（decay 了 5000 步），dW 的 absolute sum 都一样

**假设（需要验证）：**
1. 跨对污染 — 上一对的 trace 残留在下一对触发时还在
2. 事件向量太宽 — phi 覆盖了 L/R 边界，导致 L→R 和 R→L 都收到类似 dW
3. 稳态/初始偏置遮盖 — 初始权重不对称，微小 dW 被稳态拉回

---

## 9C.1B — Directional Ledger Diagnostic（方向账本）

**目的：** 逐事件追踪方向性 dW，区分 within-pair 和 cross-pair 贡献。两个消融实验。

**公式（来自 arm 定义）：**
- L_then_R：within = dW_LR（L trace × R phi），cross = dW_RL（R trace × L phi）
- R_then_L：within = dW_RL（R trace × L phi），cross = dW_LR（L trace × R phi）

**设置：** tau=1000, target_l1=1e-4, num_pairs=5

### Baseline（rest=500）

| Arm       | within    | cross     | contam | acc_dW_DI |
|-----------|-----------|-----------|--------|-----------|
| L_then_R  | 3.06e-04  | 3.22e-04  | 0.513  | -0.025    |
| R_then_L  | 4.32e-04  | 1.87e-04  | 0.302  | -0.395    |

- **acc_dW_OS = +0.37**（acc_dW_DI_LTR - acc_dW_DI_RTL）
- OFF_OS = -3.19e-05
- **acc_dW_OS 是 OFF_OS 的 ~11500 倍** — 方向性 dW 真实存在！
- 但 cross 和 within 相当（contam 0.3-0.5），互相抵消
- final_OS 仍然是 ~-3e-05 — 被稳态遮盖

### 消融 1：No Homeostasis

- final_w_l1 大 4-5x，但 OS 仍在 1e-7 量级
- **稳态不是唯一遮盖因素** — 即使去掉，OS 仍不可见

### 消融 2：Long Rest（rest=5000）

| Arm       | within    | cross     | contam | acc_dW_DI |
|-----------|-----------|-----------|--------|-----------|
| L_then_R  | 4.95e-04  | 3.22e-04  | 0.394  | +0.213    |
| R_then_L  | 4.99e-04  | 1.87e-04  | 0.273  | -0.454    |

- dW_RL 在 L pulse 时仍然精确 8.04e-05 — **即使 rest=5000，trace_R 已经比 trace_L 小 90x**
- 这证明了 L1 归一化抹平了时间门控：不管 trace 多冷，sum(|raw|) 变小，scale 变大，dW 总量不变

**L1 归一化是罪魁祸首。**

---

## 9C.1C — Trace-Gated Update（trace 门控归一化）

**目的：** 把 trace decay 恢复为时间门控，同时保持 update 幅度可控。

**三种 gate 模式：**

| 模式 | 公式 | 效果 |
|------|------|------|
| bare_l1_norm | `dW = target * raw / raw_l1` | 9C.1B 复现，无门控 |
| **soft_trace_gate** | `gate = min(1, trace_mass/ref)^power` → `dW = target * gate * raw / raw_l1` | **主机制** |
| hard_threshold | gate=1 if trace_mass > threshold else 0 | 消融对照 |

### rest=500（所有 mode）

三个 mode 结果完全相同（gate_w=1.0, gate_c=1.0） — trace_mass 在 500 步内从 ~0.03 跌到 ~0.0008，但所有 update 都发生在 trace=0.03 时（第一个事件的 trace=0 被跳过）。500 步 rest 不够，门控无法区分。

### rest=5000 — soft_trace_gate（**关键结果**）

```
[soft_trace_gate] L_then_R: within=4.95e-04  cross=8.61e-06  contam=0.017  gate_w=1.000  gate_c=0.027  trace_mass=1.88e-02
[soft_trace_gate] R_then_L: within=4.99e-04  cross=4.37e-06  contam=0.009  gate_w=1.000  gate_c=0.023  trace_mass=3.28e-02
acc_dW_OS=+1.9485  final_OS=-5.74e-06  OFF_OS=-2.54e-06
```

**解读：**
- **跨对污染下降 23x**：contam 从 0.394 → 0.017（L_then_R），0.273 → 0.009（R_then_L）
- **within-pair 信号完全保留**：4.95e-04 / 4.99e-04（和 bare_l1_norm 相同）
- **acc_dW_OS 翻 3 倍**：+0.666 → +1.949
- **gate 机制正确发挥作用**：
  - gate_c（跨对，冷 trace ~0.0008）：约 0.02-0.03，几乎把 dW 压到 0
  - gate_w（对内，热 trace ~0.03）：1.0，dW 全量通过
- **final_OS 仍然是 -5.74e-06**：方向性 dW 被稳态机制抵消

---

## 综合结论

### 三件已知的事

1. **方向性 dW 信号真实存在。** 9C.1B 账本显示 acc_dW_OS 是 OFF_OS 的 11500x。
2. **跨对污染是 L1 归一化的产物，不是机制问题。** 归一化对冷 trace 和热 trace 一视同仁。soft_trace_gate 修复了这一点。
3. **final_OS 不反映方向性 dW。** 稳态/初始偏置遮盖了结构中的方向性信号。

### 待解决问题

- `acc_dW_OS = +1.949` 但 `final_OS = -5.74e-06` — 方向性 dW 被稳态拉回
- 当前 DI 只看 L→R 和 R→L 区域连接的 l1 均值，这个指标对方向性不敏感
- 需要更好的 final-weight 指标，或者接受 acc_dW 作为主要度量

### 9C.2 方向建议

- 使用 soft_trace_gate（trace_gate_ref=3e-2, gate_power=1.0）
- 使用 washout schedule（rest=5000 等价于单对隔离）
- 考虑关掉稳态或使用不同的 final-weight 指标
- 不要引入 BTSP、不要引入标签式更新逻辑
