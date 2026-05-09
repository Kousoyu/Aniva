# Phase 7.6A: time_constant_std Active Manipulation — 分析笔记

> **日期**: 2026-05-03
> **状态**: 三点完成，不支持简单线性假设
> **依赖**: Phase 7.5 topology sensitivity (r≈+0.59 for time_constant_std)

---

## 1. 实验目的

Phase 7.5 在 n=11 种子间观察到 `time_constant_std` 与 `Δ_weight_L1` 的 Pearson r≈+0.59（方向性信号，未达统计显著）。

Phase 7.6A 的目标是：**固定 seed=42，主动操控 time_constant_std，测试其对 Δ_L1 的因果效应。** 如果 time_constant_std 是 Δ_L1 的因果驱动因素，操控应产生单调方向性响应。

---

## 2. 实验设计

### 2.1 操控方式

LifeCore 初始化后，在 step 运行前对 `core._time_constants` 做受控调整：

```
new_tc = mean_tc + (tc - mean_tc) * factor
clamp to [0.5, 1.5]
```

保持 mean 不变，只改变 std。

### 2.2 三个条件

| Condition | Factor | 实际 tc_mean | 实际 tc_std |
|-----------|--------|-------------|-------------|
| low_std | 0.3 | 1.0017 | 0.0361 |
| baseline | 1.0 | 1.0017 | 0.1205 |
| high_std | 2.0 | 1.0017 | 0.2410 |

### 2.3 实验参数

| 参数 | 值 |
|------|-----|
| Seed | 42 |
| Steps | 120,000 |
| Groups | A_L, A_R, C, D_L, D_R |
| Homeostasis | on, target=0.30 |
| Backend | Numba plasticity |

### 2.4 实验组定义（与 Phase 7.4 一致）

| 组 | 刺激序列 | Plasticity |
|----|---------|------------|
| A_L | L@300, R@1000 | on |
| A_R | R@300, L@1000 | on |
| C | 同 A_L | on |
| D_L | 同 A_L | off |
| D_R | 同 A_R | off |

---

## 3. 结果

### 3.1 护栏检查

| 检查项 | low_std | baseline | high_std |
|--------|---------|----------|----------|
| C vs A_L L1 | 0.0 | 0.0 | 0.0 |
| D_L vs D_R L1 | 0.0 | 0.0 | 0.0 |
| plasticity causal | ✅ | ✅ | ✅ |
| skeleton intact | True | True | True |

所有 causal gates 通过。操控未破坏系统的基本因果结构。

### 3.2 核心结果

| Condition | tc_std | Δ_weight_L1 | Bifurcation |
|-----------|--------|-------------|-------------|
| low_std | 0.0361 | 9.31×10⁻⁵ | emerging |
| baseline | 0.1205 | 1.05×10⁻⁴ | significant |
| high_std | 0.2410 | 7.73×10⁻⁵ | emerging |

### 3.3 趋势

**非单调（倒 U 形）。** baseline 峰值，两端均更低。

```
Δ_L1:  low_std < baseline > high_std
       9.3e-5   1.05e-4   7.7e-5
```

---

## 4. 解读

### 4.1 对 Phase 7.5 假设的修正

Phase 7.5 观察到的 `time_constant_std r≈+0.59` 若被解释为"tc_std 越大 → Δ_L1 越大"，则被本次主动操控实验**否定**。

主动操控（固定 seed，改变 tc_std）显示的是倒 U 形关系，而非单调增长。

### 4.2 可能的机制

**最优区间假说（sweet spot hypothesis）：**

- **tc_std 过低**（low_std, 0.036）：单元动力学过于均质。不同刺激序列引起的 activation 模式差异较小，plasticity 缺乏足够的"表达空间"来沉积历史差异。
- **tc_std 适中**（baseline, 0.120）：存在足够的动力学异质性，使不同刺激顺序在时间维度上产生可区分的 activation cascade，plasticity 能有效记录这些差异。
- **tc_std 过高**（high_std, 0.241）：单元响应速度过于分散。部分单元时间常数过大导致响应滞后，有效参与共同 plasticity 的单元子集缩小；信号在过于离散的时间尺度上传播，丧失了形成一致历史痕迹所需的协同性。

**观察到 high_std 的 mean_activation 最低**（0.293 vs baseline 0.306 vs low_std 0.311），这与"过于离散稀释有效信号"的假说一致。

### 4.3 Phase 7.5 相关性为什么存在？

n=11 种子间 tc_std 的变异范围与实验操控不同。种子间的 tc_std 来自 `rng.uniform(0.8, 1.2)` 的自然采样波动（std 约 0.115），而非主动扩缩。在自然范围内，tc_std 可能与其他特征（如 L→R connectivity、threshold 分布等）存在种子级别的协同变异，而这些协同变异才是 Δ_L1 的联合驱动因素。

换言之：Phase 7.5 的 r≈+0.59 反映的可能不是 tc_std 的单变量因果效应，而是 tc_std 与网络拓扑在种子间自然共变所产生的间接关联。

---

## 5. 结论

1. **time_constant_std 不是 Δ_weight_L1 的简单单调因果驱动因素。** 主动操控不支持线性正向假说。
2. **可能存在中间最优区间**，history-dependent structural divergence 需要适中的动力学异质性，而非越大越好。
3. **Aniva 在此表现出真实复杂系统的特征**——不是线性旋钮玩具，调节参数的效果受系统内部耦合关系的制约。
4. **Phase 7.5 的 r≈+0.59 更可能是多特征协同效应的种子间投影**，而非 tc_std 的独立因果效应。

---

## 6. 下一步

Phase 7.6B：L→R connectivity active manipulation。

Phase 7.5 中另一个强方向性信号是 `L_to_R_connection_count r≈-0.59`。现在 tc_std 已排除为独立单调驱动因素，L→R connectivity 成为下一个待测试的候选变量。

7.6B 设计原则：
- 只缩放已有 L→R 连接权重，不新增/删除连接
- 不翻转 sign
- 保持 causal skeleton 护栏
- 测 Δ_L1 是否随 L→R coupling 单调变化（预期负相关）

---

## 7. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase7_6_time_constant_120k.csv` | low_std + baseline 120k 逐组数据 |
| `results/phase7_6_high_std_120k.csv` | high_std 120k 逐组数据 |
| `results/phase7_6_high_std_120k.json` | high_std 完整结果 JSON |
| `docs/phase7_6_time_constant_manipulation_notes.md` | 本文件 |
