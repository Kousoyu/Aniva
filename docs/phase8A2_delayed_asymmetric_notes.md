# Phase 8A.2: Delayed Asymmetric Anomaly — 分析笔记

> **日期**: 2026-05-04
> **状态**: 完成，负结果 — delayed_asymmetric 不如 baseline_overlap 有效
> **依赖**: Phase 8A (baseline_overlap anomaly)

---

## 1. 目的

测试 **延迟不对称 anomaly**（L 先启动 75 步，R 后加入）是否比 Phase 8A 的 baseline_overlap（L+R 同时启动）产生更强的 seed-specific 轨迹分叉。

Phase 8A 发现 seed=999 在 baseline_overlap 下正响应最强（+1.99e-5，z=+1.41）。8A.2 的设计假设是：更复杂的时序 = 更像"异常事件" = 更大的差异化响应。

---

## 2. 设计

### 2.1 两种 anomaly variant

| | baseline_overlap (8A) | delayed_asymmetric (8A.2) |
|---|---|---|
| L onset | step 30000 | step 30000 |
| R onset | step 30000 | step 30075 |
| L duration | 150 | 300 |
| R duration | 300 | 225 |
| 重叠 | full overlap (150 steps) | partial overlap (225 steps) |
| 结构特征 | 同时启动，不同持续时间 | 错开启动，交错结束 |

### 2.2 参数

| 参数 | 值 |
|------|-----|
| Seeds | 42, 77, 123, 999 |
| Steps | 120,000 |
| Units | 300 |
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
| 42 | 1.04×10⁻⁴ | 8.15×10⁻⁵ | **−2.25×10⁻⁵** | −1.44 |
| 77 | 8.01×10⁻⁵ | 7.67×10⁻⁵ | −3.39×10⁻⁶ | +0.34 |
| 123 | 5.68×10⁻⁵ | 5.23×10⁻⁵ | −4.53×10⁻⁶ | +0.24 |
| 999 | 9.04×10⁻⁵ | 9.27×10⁻⁵ | **+2.21×10⁻⁶** | +0.86 |

**最高 |z| = 1.44，未达到 |z| > 1.5 的 formal outlier 门槛。**

### 3.3 Phase 8A vs 8A.2 对比

| Seed | 8A effect | 8A z | 8A.2 effect | 8A.2 z | 变化 |
|------|-----------|------|-------------|--------|------|
| 42 | −1.89×10⁻⁵ | −1.39 | −2.25×10⁻⁵ | −1.44 | 负效应微增 |
| 77 | +2.94×10⁻⁶ | +0.19 | −3.39×10⁻⁶ | +0.34 | **正→负反转** |
| 123 | −2.62×10⁻⁶ | −0.21 | −4.53×10⁻⁶ | +0.24 | 负效应微增 |
| 999 | **+1.99×10⁻⁵** | **+1.41** | **+2.21×10⁻⁶** | **+0.86** | **正响应暴跌 ~9x** |

### 3.4 关键观察

- seed=999 的 anomaly_effect 从 +1.99e-5 降到 +2.21e-6，下降了约 90%
- seed=77 的符号从正翻转为负
- 只有 seed=42 保持了方向一致的负响应
- delayed_asymmetric 产生了接近统一的抑制效应，而非差异化推力

---

## 4. 解读

### 4.1 delayed_asymmetric 为什么更弱？

delayed_asymmetric 设计的初衷是"更复杂的时序 = 更强的异常冲击"。结果相反。

从网络动力学角度解释：
- **baseline_overlap**：L+R 同时启动，两个区域在相空间中同时受到推力，产生**相干扰动**。这种相干性对不同拓扑结构（seed 42 的 well-tuned vs seed 999 的 under-coupled）产生差异化响应。
- **delayed_asymmetric**：L 先跑 75 步，已经稳定在新的吸引子附近，R 再加入时系统已经部分适应。结果是 L 支的"动量"吸收了 R 的冲击，系统平滑过渡而非分叉。

### 4.2 这意味着什么

有效的外部异常不是靠"时序复杂度"来产生差异化轨迹偏移，而是靠**跨区域同时性**。同时启动的脉冲创造了一个短暂的、无法被任何单区域独自吸收的相空间冲击——这就是为什么它对不同拓扑种子的作用方向不同。

delayed_asymmetric 给了系统"逐个处理"的空间，反而失去了差异化冲击力。

---

## 5. 结论

1. **delayed_asymmetric anomaly 不如 simultaneous overlap 有效。** seed=999 的正响应被压缩了 ~90%。
2. **跨区域同时启动可能是 anomaly 有效性的关键维度。** 不是"更复杂"，而是"更同步"。
3. **这是一条干净的负结果。** 它排除了"延迟时序 = 更强 anomaly"这个假设，缩小了 anomaly 搜索空间。
4. **未达到 formal outlier 标准。** 最高 |z|=1.44，略高于 8A 的 1.41 但仍低于 1.5。

---

## 6. 下一步

**不建议继续在 delayed_asymmetric 上加码。**

下一步更值得测的方向是 simultaneous overlap family：

- **A. full_overlap_300**: L+R 同时启动，各持续 300 步（消除持续时间不对称）
- **B. balanced_overlap**: L+R 强度平等（各 0.020），同时启动
- **C. repeated_micro_overlap**: 三次短同步脉冲，测试重复相干冲击的累积效应

当前倾向 **C**——不是简单加长或加强，而是改变异常事件的"模式"本身。

---

## 7. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase8A2_delayed_asymmetric_120k.csv` | 40 行合并结果 |
| `results/phase8A2_delayed_asymmetric_120k_seed*.csv` | 4 个单 seed CSV |
| `results/phase8A2_delayed_asymmetric_120k_summary.json` | 合并分析 JSON |
| `results/phase8A2_delayed_asymmetric_120k_seed*_summary.json` | 4 个单 seed 完整 JSON |
| `docs/phase8A2_delayed_asymmetric_notes.md` | 本文件 |
