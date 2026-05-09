# Phase 7.8: Combined Manipulation (tc_std × L→R) — 分析笔记

> **日期**: 2026-05-04
> **状态**: 2×2 完成，双维度存在干扰，非简单叠加
> **依赖**: Phase 7.7 (multi-seed topology-relative sweet spot)

---

## 1. 实验目的

Phase 7.7 表明 seed=123 在两个操控维度上都偏弱：单独增强 tc_std 或 L→R connectivity 都能提高 Δ_L1。

Phase 7.8 的目标：**测试两个单独有益的操控同时施加时，效果是叠加、协同还是互相抵消。**

---

## 2. 实验设计

### 2.1 2×2 条件

| Condition | tc_std factor | L→R factor | tc_std_after | L→R abs weight after |
|-----------|:---:|:---:|-------------|---------------------|
| baseline | 1.0 | 1.0 | 0.113 | 0.339 |
| high_std | 2.0 | 1.0 | 0.226 | 0.339 |
| lr_high | 1.0 | 2.0 | 0.113 | 0.528 |
| high_std+lr_high | 2.0 | 2.0 | 0.226 | 0.528 |

### 2.2 参数

| 参数 | 值 |
|------|-----|
| Seed | 123 |
| Steps | 120,000 |
| Units | 300 |
| Groups | A_L, A_R, C, D_L, D_R |
| Homeostasis | on, target=0.30 |
| Backend | Numba plasticity |

---

## 3. 结果

### 3.1 护栏

全部 4 条件 causal skeleton intact，C/A_L=0，D_L/D_R=0。

### 3.2 核心结果

| Condition | Δ_weight_L1 | vs baseline | Bifurcation |
|-----------|-------------|:-----------:|-------------|
| baseline | 5.29×10⁻⁵ | — | emerging |
| **high_std** | **7.11×10⁻⁵** | **+34%** | emerging |
| lr_high | 6.10×10⁻⁵ | +15% | emerging |
| high_std+lr_high | 6.24×10⁻⁵ | +18% | emerging |

### 3.3 排序

```
high_std (7.11e-5) > high_std+lr_high (6.24e-5) > lr_high (6.10e-5) > baseline (5.29e-5)
```

**Combined (6.24e-5) < high_std alone (7.11e-5)。**

---

## 4. 解读

### 4.1 拒绝简单叠加模型

如果两个维度独立叠加，预期 `combined ≈ high_std + lr_high - baseline` ≈ 7.92e-5。实际 6.24e-5，远低于叠加预期，甚至低于 high_std 单独。

**两个单独有益的操控组合后不是叠加，也不是协同——而是产生了干扰。**

### 4.2 多维张力窄带假说

可塑临界带（structural tension band）是一个**多维窄带**，不是一条直线上越来越高的坡。

- high_std 单独把 seed=123 推近 tc_std 维度的 sweet spot（7.11e-5）
- 在这个新位置同时加 lr_high → 系统在 L→R 维度也被推动，但整体反而偏离了多维最优区
- 类似在多峰地形上，一个方向再走一步是向上，但两个方向同时迈步可能踩偏

### 4.3 与 Phase 7.7 的衔接

Phase 7.7 表明 sweet spot 是 topology-relative。Phase 7.8 进一步表明：**sweet spot 还是 multi-dimensional。** 参数维度之间不是独立的——一个维度的"最优位置"取决于另一个维度的状态。

### 4.4 对 seed=123 的完整画像

| 操控 | Δ_L1 | 含义 |
|------|------|------|
| baseline | 5.29e-5 | 自然状态下远离 sweet spot |
| high_std | 7.11e-5 | 增强 tc 异质性有效，接近最优 |
| lr_high | 6.10e-5 | 增强 L→R 有效但效果较弱 |
| high_std+lr_high | 6.24e-5 | 双维度增强 → L→R 增强抵消了 tc 增强的部分收益 |

seed=123 不是"两个维度都缺"的简单补强对象，而是：tc_std 增强有效，但要配合适度的 L→R coupling（baseline 刚好，lr_high 过度）。

---

## 5. 多 seed 总览

| | seed=42 | seed=999 | seed=123 |
|---|---|---|---|
| tc_std 最优 | baseline | baseline | **high_std** |
| L→R 最优 | baseline | **lr_high** | **lr_high** |
| 组合特征 | 天然调谐 | tc 到位，L→R 不足 | 两维均偏弱，但 tc 增强效益更大 |
| 联合操控 | — | — | **combined < high_std alone** |

三种子从三个不同的山坡出发，各自的最优路径不同。

---

## 6. 结论

1. **Combined manipulation 产生干扰，而非叠加。** high_std+lr_high 的 Δ_L1 低于 high_std alone。
2. **可塑临界带是多维窄带。** 两个单独有益的操控方向组合起来，不一定更有益，甚至可能把系统推离局部最优区。
3. **种子间差异不是一维刻度。** 每个种子的"弱点"和"改善路径"是拓扑/动力学耦合的结果，不能简化为"缺什么补什么"。
4. **Aniva 的行为更像真实复杂系统的地形导航**——在多维参数空间中，每一步的方向选择取决于当前位置，同时迈两步可能还不如只迈对的一步。

---

## 7. 局限

- 仅 seed=123，未在其他种子上测试联合操控
- 仅 2×2 设计，未扫更细粒度（如 tc_std 1.5× + lr 1.5×）
- 未知组合干扰是特例还是一般规律
- 未测试 R→L 方向的对称联合操控

---

## 8. 下一步

- 可选：在 seed=999 上复现 combined test（L→R 不足的种子，预测可能不同）
- 可选：seed=123 局部小网格（tc 1.5×2, lr 1.5×2）
- Phase 8：异常扰动——在多维地形图基础上引入事件维度

---

## 9. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase7_8_seed123_combined_manipulation_120k.csv` | 四条件 120k 逐组数据 |
| `results/phase7_8_seed123_combined_manipulation_120k_summary.json` | 完整结果 JSON |
| `docs/phase7_8_combined_manipulation_notes.md` | 本文件 |
