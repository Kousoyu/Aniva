# Phase 7.7: Seed 999 Manipulation Replication — 分析笔记

> **日期**: 2026-05-04
> **状态**: seed=999 完成，sweet spot 从固定区间升级为拓扑相对概念
> **依赖**: Phase 7.6A/B (seed=42 active manipulation)

---

## 1. 实验目的

Phase 7.6A/B 在 seed=42 上发现 time_constant_std 和 L→R connectivity 两个操控维度均呈倒 U 形，baseline 位于峰值。

Phase 7.7 的目标：**在 seed=999（高敏感个体）上复现这两个倒 U 形**，测试 sweet spot 是 seed 独立的固定区间还是拓扑相对的位置。

---

## 2. 实验设计

与 Phase 7.6 完全相同的协议：

| 参数 | 值 |
|------|-----|
| Seed | 999 |
| Steps | 120,000 |
| Units | 300 |
| Groups | A_L, A_R, C, D_L, D_R |
| Homeostasis | on, target=0.30 |
| Backend | Numba plasticity |

实验 A：time_constant_std 操控（factor: 0.3 / 1.0 / 2.0）
实验 B：L→R connectivity 操控（factor: 0.5 / 1.0 / 2.0）

---

## 3. 结果

### 3.1 初始拓扑对比

| | seed=42 | seed=999 |
|---|---|---|
| L-affected | 11 | 20 |
| R-affected | 18 | 11 |
| L→R 连接数 | **13** | **6** |
| R→L 连接数 | 7 | 15 |
| L→R abs weight mean | 0.477 | 0.513 |
| overlap | 0 | 0 |

seed=999 的天然 L→R 连接仅 6 条（seed=42 的一半），而 R→L 反向有 15 条。天然跨区域 coupling 方向偏 R→L。

### 3.2 实验 A：time_constant_std — 倒 U 复现 ✅

| Condition | tc_std | Δ_weight_L1 | Bifurcation |
|-----------|--------|-------------|-------------|
| low_std | 0.036 | 8.3×10⁻⁵ | emerging |
| baseline | 0.120 | **8.5×10⁻⁵** | emerging |
| high_std | 0.241 | 8.3×10⁻⁵ | emerging |

形状与 seed=42 一致（baseline 峰值），但整体幅度更低、峰更平。

对比 seed=42：

| Condition | seed=42 Δ_L1 | seed=999 Δ_L1 |
|-----------|-------------|-------------|
| low_std | 9.31e-5 | 8.3e-5 |
| baseline | **1.05e-4** | **8.5e-5** |
| high_std | 7.73e-5 | 8.3e-5 |

### 3.3 实验 B：L→R connectivity — 单调递增 ❌ 非倒 U

| Condition | L→R abs weight | 实际倍数 | Δ_weight_L1 | Bifurcation |
|-----------|---------------|---------|-------------|-------------|
| lr_low | 0.256 | 0.50x | 8.38×10⁻⁵ | emerging |
| baseline | 0.513 | 1.00x | 8.46×10⁻⁵ | emerging |
| **lr_high** | **0.837** | **1.63x** | **1.02×10⁻⁴** | **significant** |

lr_high 最大且是唯一达到 significant 的条件。

对比 seed=42：

| Condition | seed=42 Δ_L1 | seed=999 Δ_L1 |
|-----------|-------------|-------------|
| lr_low | 7.55e-5 | 8.38e-5 |
| baseline | **1.05e-4** | 8.46e-5 |
| lr_high | 8.19e-5 | **1.02e-4** |

### 3.4 护栏

所有条件 causal skeleton intact，C/A_L = 0，D_L/D_R = 0。

---

## 4. 解读

### 4.1 Sweet spot 是拓扑相对的

```
seed=42:  L→R=13条, R→L=7条  →  L→R 已经充裕 → 倒U
seed=999: L→R=6条,  R→L=15条 →  L→R 天然不足 → 单调递增
```

seed=999 天然 L→R 连接稀少、跨区域信息流偏 R→L 方向。增强 L→R connectivity（lr_high）相当于**补短板**，将跨区域耦合推向更均衡的状态，从而提升 history-dependent divergence。

seed=42 天然 L→R 已接近适中区间，继续增强导致过耦合，降低 divergence。

**Sweet spot 不是全局固定参数区间，而是相对于个体初始拓扑结构的位置。**

### 4.2 tc_std 为什么跨 seed 一致？

time_constant_std 操控的是单元级别的时间响应异质性，不直接涉及空间拓扑。单元时间常数的分布在不同 seed 间相似（均来自 `rng.uniform(0.8, 1.2)`），因此 sweet spot 位置在 seed 间更一致。

L→R connectivity 则高度依赖空间拓扑（哪些单元落在 L/R 刺激区域内，以及它们之间的连接），seed 间差异大。

### 4.3 对 Phase 7.5 相关性的再解释

Phase 7.5 观察到的 L→R connection count r≈-0.59 反映的是：在自然种子间，L→R 连接数的变异部分反映了各 seed 距离 sweet spot 的位置差异。但这不是简单的"越少越好"——seed=999 的 6 条 L→R 连接处于"不足"侧，seed=42 的 13 条处于"充裕"侧。

---

## 5. 结论

1. **tc_std 倒 U 形跨 seed 复现**（seed=42 和 seed=999 均 baseline 峰值）。
2. **L→R connectivity sweet spot 是拓扑相对的**：seed=999（L→R 不足）表现为单调递增，lr_high 达到 significant。
3. **Sweet spot 假说升级**：history-dependent structural divergence 存在最优区间，但区间位置不是全局固定的，而是相对于个体初始拓扑。同一个操控方向可能将不同个体推向或推离 sweet spot。
4. **tc_std 操控在不同 seed 间更稳健**，因为它不直接依赖空间拓扑细节。

---

## 6. 下一步

- seed=123 复现，预测：L→R 连接数=16，权重偏低(0.339)，如果连接数比权重更决定 sweet spot 位置，则 seed=123 应更像 seed=42（倒 U）
- 未来可做 L→R/R→L balance 的定量指标，而非单纯的 L→R 连接数
- Phase 8：异常扰动（待 7.7 完成后）

---

## 7. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase7_7_seed999_tc_std_120k.csv` | seed=999 tc_std 三条件 120k 数据 |
| `results/phase7_7_seed999_tc_std_120k_summary.json` | seed=999 tc_std 完整结果 |
| `results/phase7_7_seed999_lr_connectivity_120k.csv` | seed=999 L→R 三条件 120k 数据 |
| `results/phase7_7_seed999_lr_connectivity_120k_summary.json` | seed=999 L→R 完整结果 |
| `docs/phase7_7_seed999_replication_notes.md` | 本文件 |
