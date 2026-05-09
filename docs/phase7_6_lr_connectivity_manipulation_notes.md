# Phase 7.6B: L→R Connectivity Active Manipulation — 分析笔记

> **日期**: 2026-05-03
> **状态**: 三点完成，不支持简单线性假设
> **依赖**: Phase 7.5 topology sensitivity (r≈-0.59 for L→R connection count)

---

## 1. 实验目的

Phase 7.5 在 n=11 种子间观察到 `L_to_R_connection_count` 与 `Δ_weight_L1` 的 Pearson r≈-0.59（方向性信号，未达统计显著）。

Phase 7.6B 的目标是：**固定 seed=42，主动操控 L→R 连接权重，测试其对 Δ_L1 的因果效应。**

Phase 7.6A 已排除 `time_constant_std` 作为独立单调因果驱动因素（倒 U 形）。7.6B 测试第二个候选变量。

---

## 2. 实验设计

### 2.1 操控方式

- 按空间坐标识别 L-affected 和 R-affected 两组单元
- 找出所有 L→R 方向的连接（源在 L 侧、目标在 R 侧）
- 对找到的 L→R 连接权重按 factor 缩放
- Clamp 到 [-1.0, 1.0]
- **不新增/删除连接，不翻转 sign**
- R→L 方向连接不受影响

### 2.2 三个条件

| Condition | Factor | 实际 L→R abs weight mean | 实际倍数 |
|-----------|--------|--------------------------|----------|
| lr_low | 0.5 | 0.238 | 0.50x |
| baseline | 1.0 | 0.477 | 1.00x |
| lr_high | 2.0 | 0.752 | 1.58x |

lr_high 未达到 2.0x，因为部分连接权重放大后撞到 [-1.0, 1.0] clamp 上限，加上 homeostasis 抵抗。

### 2.3 连接拓扑

| 指标 | 值 |
|------|-----|
| L→R 连接数 | 13 |
| R→L 连接数 | 7 |
| L-affected 单元数 | 11 |
| R-affected 单元数 | 18 |
| 重叠单元 | 0 |

L→R 连接仅 13 条（共约 90,000 条连接中），但跨区域连接本身就稀少。

### 2.4 实验参数

| 参数 | 值 |
|------|-----|
| Seed | 42 |
| Steps | 120,000 |
| Units | 300 |
| Groups | A_L, A_R, C, D_L, D_R |
| Homeostasis | on, target=0.30 |
| Backend | Numba plasticity |

---

## 3. 结果

### 3.1 护栏检查

| 检查项 | lr_low | baseline | lr_high |
|--------|--------|----------|----------|
| C vs A_L L1 | 0.0 | 0.0 | 0.0 |
| D_L vs D_R L1 | 0.0 | 0.0 | 0.0 |
| plasticity causal | ✅ | ✅ | ✅ |
| skeleton intact | True | True | True |

### 3.2 核心结果

| Condition | L→R abs weight | Δ_weight_L1 | Bifurcation |
|-----------|----------------|-------------|-------------|
| lr_low | 0.238 | 7.55×10⁻⁵ | emerging |
| baseline | 0.477 | 1.05×10⁻⁴ | significant |
| lr_high | 0.752 | 8.19×10⁻⁵ | emerging |

### 3.3 趋势

**非单调（倒 U 形）。** baseline 峰值，两端均更低。

```
Δ_L1:  lr_low < baseline > lr_high
       7.6e-5  1.05e-4   8.2e-5
```

### 3.4 与 7.6A 的对称性

| | 7.6A (tc_std) | 7.6B (L→R conn) |
|---|---|---|
| low | 9.31e-5 | 7.55e-5 |
| **baseline** | **1.05e-4** | **1.05e-4** |
| high | 7.73e-5 | 8.19e-5 |
| 形状 | 倒U | 倒U |

两个不同参数的主动操控，baseline Δ_L1 精确相同（1.05×10⁻⁴），均在自然参数下达到峰值。

---

## 4. 解读

### 4.1 对 Phase 7.5 假设的修正

Phase 7.5 观察到的 L→R connection count r≈-0.59 若被解释为"更少 L→R 连接 → 更大 Δ_L1"，则被本次主动操控实验**否定**。

主动操控显示的是倒 U 形关系，而非单调关系。

### 4.2 Sweet spot 假说

结果支持"history-dependent structural divergence 需要适中动力学异质性与适中跨区域耦合"的 sweet spot 假说：

- **L→R coupling 过低**（lr_low）：L 和 R 区域间的交互不足，刺激序列的时序差异无法充分通过跨区域信号传播形成差异化的 activation 模式。
- **L→R coupling 适中**（baseline）：恰好足够的跨区域信息流，使刺激顺序能在网络层面产生可区分的动态历史痕迹。
- **L→R coupling 过高**（lr_high）：L 和 R 过度同步，刺激的时序信息被"抹平"——无论先刺激哪边，过强的跨区域耦合使两区域快速趋同，降低了 order-specific divergence。

### 4.3 注意：lr_low 下 mean_activation 排序异常

在 plasticity-on 组中，lr_low 的 A_L 与 A_R 之间 activation 差为 0.0172，而 baseline 为 -0.0091（A_R 反而更高）。lr_low 下 A_L > A_R，baseline 下 A_R > A_L。这暗示 L→R coupling 的强度可能翻转了刺激顺序对 activation 的影响方向。

### 4.4 Phase 7.5 相关性为什么存在？

与 7.6A 同理：Phase 7.5 观察到的 r≈-0.59 反映的不是 L→R connectivity 的单变量因果效应，而是 L→R 连接数在种子间与其他特征（如 tc_std、threshold 分布、拓扑细节等）的协同变异。

---

## 5. 结论

1. **L→R connectivity 不是 Δ_weight_L1 的简单单调因果驱动因素。** 主动操控不支持"越少 L→R 连接 = 越大 divergence"的假说。
2. **倒 U 形关系**，与 7.6A 的 time_constant_std 操控结果一致。
3. **7.6A 和 7.6B 共同指向 sweet spot 假说**：在 seed=42 当前实验设置下，baseline 同时位于 time_constant_std 与 L→R connectivity 两个操控维度的高分叉区间。history-dependent structural divergence 对偏离自然初始化状态的操控均表现为抑制。
4. **Aniva 的网络结构不是线性旋钮集合**——不同参数维度的操控在系统层面收敛到同一个非单调响应模式，这是一致性信号。

---

## 6. 局限

- 仅在 seed=42 上测试
- lr_high 实际仅 1.58x，未达目标 2.0x（受 clamp 限制）
- 跨区域连接数量少（13条），操控的统计效力受限
- 需要多 seed 复现确认 sweet spot 的 seed 独立性

---

## 7. 下一步

- 在 seed=999 或 seed=77 上复现 7.6A / 7.6B，测试 sweet spot 是否跨 seed 成立
- 联合操控 tc_std × L→R connectivity，测试是否存在交互效应
- Phase 8：外部异常扰动实验

---

## 8. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase7_6_lr_connectivity_120k.csv` | 三条件 120k 逐组数据 |
| `results/phase7_6_lr_connectivity_120k_summary.json` | 完整结果 JSON |
| `docs/phase7_6_lr_connectivity_manipulation_notes.md` | 本文件 |
