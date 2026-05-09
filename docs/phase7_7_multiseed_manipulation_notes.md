# Phase 7.7: Multi-Seed Active Manipulation — 分析笔记

> **日期**: 2026-05-04
> **状态**: 三种子六实验完成，sweet spot 确认为拓扑相对
> **依赖**: Phase 7.6A/B (seed=42 active manipulation)

---

## 1. 实验目的

Phase 7.6A/B 在 seed=42 上发现 time_constant_std 和 L→R connectivity 两个操控维度均呈倒 U 形，baseline 位于峰值。

Phase 7.7 的目标：**在 seed=999（高敏感）和 seed=123（弱敏感）上复现**，测试 sweet spot 是全局固定参数区间还是拓扑相对的位置。

---

## 2. 实验设计

与 Phase 7.6 完全相同的协议：

| 参数 | 值 |
|------|-----|
| Steps | 120,000 |
| Units | 300 |
| Groups | A_L, A_R, C, D_L, D_R |
| Homeostasis | on, target=0.30 |
| Backend | Numba plasticity |

实验 A：time_constant_std 操控（factor: 0.3 / 1.0 / 2.0）
实验 B：L→R connectivity 操控（factor: 0.5 / 1.0 / 2.0）

---

## 3. 初始拓扑

| | seed=42 | seed=999 | seed=123 |
|---|---|---|---|
| L-affected | 11 | 20 | 24 |
| R-affected | 18 | 11 | 18 |
| L→R 连接数 | 13 | 6 | 16 |
| R→L 连接数 | 7 | 15 | 23 |
| L→R abs weight mean | 0.477 | 0.513 | 0.339 |
| L→R 总耦合 (sum) | 6.20 | 3.08 | 5.43 |
| overlap | 0 | 0 | 0 |

---

## 4. 结果总览

### 4.1 实验 A：time_constant_std

| Condition | seed=42 Δ_L1 | seed=999 Δ_L1 | seed=123 Δ_L1 |
|-----------|-------------|-------------|-------------|
| low_std | 9.31e-5 | 8.3e-5 | 5.39e-5 |
| **baseline** | **1.05e-4** | **8.5e-5** | 5.29e-5 |
| high_std | 7.73e-5 | 8.3e-5 | **7.11e-5** |
| 趋势 | 倒U | 倒U (平) | high_std 胜 |

### 4.2 实验 B：L→R connectivity

| Condition | seed=42 Δ_L1 | seed=999 Δ_L1 | seed=123 Δ_L1 |
|-----------|-------------|-------------|-------------|
| lr_low | 7.55e-5 | 8.38e-5 | 5.07e-5 |
| **baseline** | **1.05e-4** | 8.46e-5 | 5.29e-5 |
| lr_high | 8.19e-5 | **1.02e-4** | **6.10e-5** |
| 趋势 | 倒U | 单调↗ | 单调↗ |

### 4.3 护栏

全部 18 个 condition（3 seed × 6 experiments × 3 conditions）causal skeleton intact，C/A_L=0，D_L/D_R=0。

---

## 5. 核心发现

### 5.1 Sweet spot 是拓扑相对的

```
seed=42:  两个维度 baseline 都在峰值 → 先天调谐最优
seed=999: tc_std baseline 在峰值，L→R 不足 → 单向偏离
seed=123: 两个维度 baseline 都不是最优 → 双向偏离
```

**Sweet spot 不是全局固定参数区间，而是相对于个体初始拓扑的位置。**

### 5.2 同一操控，不同种子响应不同

high_std（增加 tc 异质性）：
- seed=42 → Δ_L1 下降（推离 sweet spot）
- seed=999 → Δ_L1 略低于 baseline（推离）
- seed=123 → Δ_L1 上升（推向 sweet spot）

lr_high（增强 L→R 耦合）：
- seed=42 → Δ_L1 下降（过耦合）
- seed=999 → Δ_L1 显著上升，达 significant（补短板）
- seed=123 → Δ_L1 上升（补短板，但整体仍低）

### 5.3 tc_std 维度更稳健，L→R 维度更依赖拓扑

tc_std 操控的是单元级别的时间响应异质性，在不同 seed 间较一致（seed=42 和 999 均为倒 U）。L→R connectivity 高度依赖空间拓扑，seed 间差异大。

### 5.4 弱敏感个体不是天花板低，是基线位置偏

seed=123 在 Phase 7.5 中被标记为较弱敏感个体。但操控实验显示：给它更强的动态异质性（high_std）或更强的 L→R 耦合（lr_high），Δ_L1 都能提升。**它的 baseline 不是天花板，而是因地形的相对位置偏低。**

---

## 6. 对 Phase 7.6 结论的修正

Phase 7.6 在 seed=42 上观察到的倒 U 形**不是普适固定曲线**，而是 seed=42 这一个体在当前地形上的一个局部切片。

跨 seed 后，每个操控维度的响应取决于个体初始拓扑在该维度上相对于 sweet spot 的位置。相同操控可能让某些个体远离峰顶，也可能把另一些个体推近峰顶。

---

## 7. 意义

History-dependent structural divergence 不由单一参数的绝对值决定，而由**个体是否处于可塑临界带（structural tension band）**决定。这个带的位置不是全局固定的，而是由初始拓扑、动力学状态和参数交互共同定义的。

Aniva 在此表现出真实复杂系统的特征：**个体差异不只是在同一个地形上位置不同，而是每个个体的地形本身就不同。**

---

## 8. 局限

- 仅 3 个 seed，不足以估计群体分布
- 仅两个操控维度，未知是否有其他关键维度
- 操控是独立的，未测试 tc_std × L→R 交互效应
- 未测试 R→L 方向的对称操控
- baseline 的定义依赖于自然随机初始化，不同 seed 的"自然状态"本身就不同

---

## 9. 下一步

1. **联合操控**：tc_std × L→R connectivity，测试交互效应
2. **定向 seed 筛选**：按拓扑位置（L→R 总耦合）选 seed，而非随机
3. **Phase 8**：外部异常扰动，在地形图更清晰后引入事件维度

---

## 10. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase7_7_seed999_tc_std_120k.csv` | seed=999 tc_std 数据 |
| `results/phase7_7_seed999_tc_std_120k_summary.json` | seed=999 tc_std 完整结果 |
| `results/phase7_7_seed999_lr_connectivity_120k.csv` | seed=999 L→R 数据 |
| `results/phase7_7_seed999_lr_connectivity_120k_summary.json` | seed=999 L→R 完整结果 |
| `results/phase7_7_seed123_lr_connectivity_120k.csv` | seed=123 L→R 数据 |
| `results/phase7_7_seed123_lr_connectivity_120k_summary.json` | seed=123 L→R 完整结果 |
| `results/phase7_7_seed123_tc_std_120k.csv` | seed=123 tc_std 数据 |
| `results/phase7_7_seed123_tc_std_120k_summary.json` | seed=123 tc_std 完整结果 |
| `docs/phase7_7_multiseed_manipulation_notes.md` | 本文件 |
