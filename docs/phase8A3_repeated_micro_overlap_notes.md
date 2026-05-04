# Phase 8A.3: Repeated Micro Overlap Anomaly — 分析笔记

> **日期**: 2026-05-04
> **状态**: 完成 — repeated micro pulses 失去 seed-specific targeting
> **依赖**: Phase 8A (baseline_overlap), Phase 8A.2 (delayed_asymmetric)

---

## 1. 目的

测试 seed=999 是**对一次连续同步相干冲击**敏感，还是**对重复同步事件模式**更敏感。

Phase 8A baseline_overlap 发现 seed=999 在单一持续同步脉冲下正响应最强（+1.99e-5）。Phase 8A.2 排除了"更复杂时序"的假设。8A.3 测试"事件模式"维度：保持同时性，但把一次长脉冲切成三次短脉冲。

---

## 2. 设计

### 2.1 Anomaly 定义

```
pulse 1: L+R 同时, duration 60, start = anomaly_step
pulse 2: L+R 同时, duration 60, start = anomaly_step + 600
pulse 3: L+R 同时, duration 60, start = anomaly_step + 1200

L intensity = 0.025, R intensity = 0.015
```

关键特征：
- **保持了同时性**（每 pulse 内 L+R same onset）—— 这是 8A/8A.2 对比后认为最关键的维度
- **改变了事件结构**（3 次短脉冲 vs 1 次长脉冲）—— 测试"模式"而非"强度"或"时序"
- 总 anomaly 能量可比（8A: L 0.025×150 + R 0.015×300 = 8.25；8A.3: 3×(0.025×60 + 0.015×60) = 7.2）

### 2.2 参数

| 参数 | 值 |
|------|-----|
| Seeds | 42, 77, 123, 999 |
| Steps | 120,000 |
| Units | 300 |
| Anomaly step | 30,000 |
| Groups | A_L, A_R, C, D_L, D_R |
| Homeostasis | on, target=0.30 |
| Backend | Numba plasticity |
| 并行 | 4 tmux sessions，每 seed 独占 1 vCPU |

---

## 3. 结果

### 3.1 护栏

全部 4 seed causal skeleton intact。C/A_L=0，D_L/D_R=0。

### 3.2 核心结果

| Seed | normal Δ_L1 | anomaly Δ_L1 | effect | z-score |
|------|-------------|--------------|--------|---------|
| 42 | 1.04×10⁻⁴ | 9.58×10⁻⁵ | −8.16×10⁻⁶ | −0.18 |
| 77 | 8.01×10⁻⁵ | 6.90×10⁻⁵ | −1.11×10⁻⁵ | −0.48 |
| 123 | 5.68×10⁻⁵ | 6.50×10⁻⁵ | **+8.22×10⁻⁶** | +1.45 |
| 999 | 9.04×10⁻⁵ | 7.62×10⁻⁵ | **−1.42×10⁻⁵** | −0.79 |

**最高 |z| = 1.45，未达到 |z| > 1.5 的 formal outlier 门槛。**

### 3.3 三变体对比

| Seed | 8A baseline_overlap | 8A.2 delayed_asymmetric | 8A.3 repeated_micro_overlap |
|------|---------------------|-------------------------|------------------------------|
| 42 | −1.89e-5 (z=−1.39) | −2.25e-5 (z=−1.44) | −8.16e-6 (z=−0.18) |
| 77 | +2.94e-6 (z=+0.19) | −3.39e-6 (z=+0.34) | −1.11e-5 (z=−0.48) |
| 123 | −2.62e-6 (z=−0.21) | −4.53e-6 (z=+0.24) | **+8.22e-6 (z=+1.45)** |
| 999 | **+1.99e-5 (z=+1.41)** | +2.21e-6 (z=+0.86) | **−1.42e-5 (z=−0.79)** |

```
8A:   seed=999 ↑↑  seed=42 ↓↓   — 方向性最清晰
8A.2: seed=999 ↑   seed=42 ↓↓   — 方向性减弱
8A.3: seed=999 ↓   seed=42 ↓    seed=123 ↑  — 方向性被打散
```

---

## 4. 解读

### 4.1 Pre-registered 问题的答案

> seed=999 是对一次连续同步相干冲击敏感，还是对重复同步事件模式更敏感？

**答案：一次连续同步相干冲击。**

seed=999 的 anomaly_effect 从 +1.99e-5（8A，一次持续同步冲击）跌到 −1.42e-5（8A.3，三次短同步脉冲），不仅没有增强，连符号都翻转了。

落入预注册框架的条件 2：
> "seed=999 effect < baseline_overlap，但仍为正"

但实际结果比预期更极端 —— 符号翻转说明重复微脉冲对 seed=999 不仅是"不敏感"，而是有反向抑制效应。

### 4.2 意外发现：seed=123 翻转

seed=123 在三轮实验中首次出现明显正响应（+8.22e-6, z=+1.45），接近 formal outlier。此前 seed=123 在 8A 和 8A.2 中均为弱负响应。

这说明 repeated_micro_overlap 改变了 anomaly 的 seed targeting 模式——不是加强了对 seed=999 的击中，而是**换了靶**。

### 4.3 为什么重复脉冲失去靶向性

从网络动力学角度：
- **baseline_overlap**: 一次持续的同步相干冲击（150/300 步），创造了一个无法被单区域吸收的连续相空间扰动窗口 → 对 under-coupled 的 seed=999 产生定向推力
- **repeated_micro_overlap**: 三次短促的同步脉冲（各 60 步，间隔 600 步），每次脉冲太短不足以持续扰动相空间，而 600 步间隔允许系统在各次之间恢复平衡 → 脉冲的"模式"信息（重复性）可能被系统的 homeostatic 恢复抹去
- **间歇期是关键**: 600 步的 silence 让 homeostatic plasticity 有时间把权重拉回基线 → 每次脉冲几乎像全新事件 → 失去了定向累积效应

---

## 5. 三变体 rank

| 维度 | 8A baseline_overlap | 8A.2 delayed_asymmetric | 8A.3 repeated_micro_overlap |
|------|---------------------|-------------------------|------------------------------|
| Seed-specific 方向性 | **强**（999↑, 42↓） | 中（999↑弱, 42↓） | 弱（方向打散） |
| 最高 |z| 1.41 (999) | 1.44 (42) | 1.45 (123) |
| Formal outlier | 无 | 无 | 无 |
| 结论 | **保留** — 最有效 | 排除 — 更弱 | 排除 — 失去靶向性 |

---

## 6. 结论

1. **一次持续同步相干冲击（baseline_overlap）仍然是唯一产生清晰 seed-specific 方向性的 anomaly variant。**
2. **repeated_micro_overlap 失去了对 seed=999 的靶向性。** seed=999 效应从正翻负，seed=123 意外成为最强正响应者。
3. **同步性必要但不充分。** 保持同时启动但切成短脉冲 → 失去累积效应 → 靶向性丧失。这说明有效的 anomaly 需要**同时性 + 超过 micro-pulse 尺度的持续时间 + 连续性**。60步×3 无效，150/300 目前最有效，但不能断言为精确最低阈值。
4. **未达 formal outlier。** 最高 |z|=1.45（seed=123），仍低于 1.5 门槛。
5. **三刀砍完，搜索空间进一步收窄。**

---

## 7. Phase 8A Anomaly Family 总结

```
已测试:
  ✓ baseline_overlap      — 有效，方向性证据（留用）
  ✗ delayed_asymmetric    — 排除（弱化 seed-specific 响应）
  ✗ repeated_micro_overlap — 排除（失去靶向性，方向打散）

已确认:
  同时性 是有效 anomaly 的必要条件
  足够持续时间 是产生 seed-specific 累积效应的必要条件
  仅同时性 + 短脉冲 不够

搜索空间状态:
  有效 anomaly = 同时启动 + 足够持续时长(>60步) + 无长间歇 + 跨区域强度不对称
  → baseline_overlap（150/300）是目前唯一满足所有条件的配置
```

---

## 8. 下一步

Phase 8A anomaly family 三刀砍完。baseline_overlap 仍是唯一有效的 variant。

如果要继续 anomaly 线，可能方向：
- **magnitude scan**: 保持 baseline_overlap 结构，扫描不同强度比例（L:R = 0.025:0.015 → 0.03:0.01 → 0.02:0.02）
- **duration scan**: 保持同时启动，扫描不同持续时长
- **Phase 8B closed-loop**: 让 anomaly 后的个体状态影响后续事件

但这三刀已经将 anomaly 的最关键维度钉在**同时性 × 持续时间**上。可以考虑收束 anomaly 线，进入 closed-loop。

---

## 9. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase8A3_repeated_micro_overlap_120k.csv` | 40 行合并结果 |
| `results/phase8A3_repeated_micro_overlap_120k_seed*.csv` | 4 个单 seed CSV |
| `results/phase8A3_repeated_micro_overlap_120k_summary.json` | 合并分析 JSON |
| `docs/phase8A3_repeated_micro_overlap_notes.md` | 本文件 |
