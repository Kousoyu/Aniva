# Phase 8A: External Anomaly Perturbation — 分析笔记

> **日期**: 2026-05-04
> **状态**: 四 seed 完成，seed × anomaly interaction 方向性证据出现，未达 formal outlier
> **依赖**: Phase 7.7 (multi-seed topology-relative framework)

---

## 1. 目的

测试一个**结构上不同于常规 L/R 顺序流**的外部异常脉冲，是否会在不同 seed 上产生不同方向的轨迹偏移。

Phase 7.7/7.8 确立了 sweet spot 是 topology-relative 的多维窄带。Phase 8A 问的是：**一个外部事件能不能在特定 seed 上推一把，让它靠近或远离这个窄带？**

---

## 2. 设计

### 2.1 异常定义

异常不是一个更强的 L 或 R 刺激。它是跨区域、重叠、不对称的脉冲：

| 参数 | L 分支 | R 分支 |
|------|--------|--------|
| 强度 | 0.025 | 0.015 |
| 持续时间 | 150 | 300 |
| 触发步 | 30000 | 30000 |

两个脉冲同时从 step 30000 开始，R 持续两倍时长。这在结构上和正常流（L 独占 block → R 独占 block）完全不同。

### 2.2 参数

| 参数 | 值 |
|------|-----|
| Seeds | 42, 77, 123, 999 |
| Steps | 120,000 |
| Units | 300 |
| Groups | A_L, A_R, C, D_L, D_R |
| Homeostasis | on, target=0.30 |
| Backend | Numba plasticity |

### 2.3 两个 stream

- **normal_stream**: 常规 L/R 顺序流，无异常
- **anomaly_stream**: 常规流 + step 30000 插入异常脉冲

对比两个 stream 的 Δ_weight_L1，差异即为 anomaly_effect。

---

## 3. 结果

### 3.1 护栏

全部 4 seed 在 normal 和 anomaly 条件下 causal skeleton intact。C/A_L=0，D_L/D_R=0。

### 3.2 核心结果

| Seed | normal Δ_L1 | anomaly Δ_L1 | effect | z-score | 分叉等级变化 |
|------|-------------|--------------|--------|---------|-------------|
| 42 | 1.05×10⁻⁴ | 8.57×10⁻⁵ | **−1.89×10⁻⁵** | −1.39 | significant → emerging ↓ |
| 77 | 8.36×10⁻⁵ | 8.65×10⁻⁵ | +2.94×10⁻⁶ | +0.19 | 不变 |
| 123 | 5.29×10⁻⁵ | 5.03×10⁻⁵ | −2.62×10⁻⁶ | −0.21 | 不变 |
| 999 | 8.46×10⁻⁵ | 1.05×10⁻⁴ | **+1.99×10⁻⁵** | +1.41 | emerging → significant ↑ |

**最高 |z| = 1.41，未达到 |z| > 1.5 的 formal outlier 门槛。**

### 3.3 关键观察

```
seed=42:  significant → emerging   (anomaly 拉低)
seed=999: emerging   → significant  (anomaly 推高)
```

Anomaly 没有统一增强或抑制所有 seed。它对两个 seed 产生了方向相反的影响。

---

## 4. 解读

### 4.1 Seed × Anomaly Interaction

seed=999 在 normal 下不是最强种子（1.05e-4 属于 seed=42），但在 anomaly 下成为唯一达到 significant 的种子。这符合 Phase 8A 想抓的信号：**特殊轨迹不是 seed 静态属性，而是 seed × anomalous event 的交互产物。**

### 4.2 与拓扑相对框架一致

Phase 7.7 揭示：
- seed 42 已经在 sweet spot 附近，正常条件下达到最大 Δ_L1
- seed 999 是 L→R under-coupled 种子，先天缺乏跨区互动

Phase 8A 的结果：
- **seed 42**：异常脉冲在已经调谐的系统上是多余推力 → 推离 sweet spot → Δ_L1 下降
- **seed 999**：跨区重叠脉冲恰好补偿了它的先天 L→R 耦合不足 → 推近 sweet spot → Δ_L1 上升
- **seed 77/123**：各自处于稳定区 → 当前强度的 anomaly 不足以驱动显著偏移

### 4.3 为什么没有 formal outlier

- n=4 太小，z-score 对单种子波动敏感
- anomaly 是先验设计的固定脉冲，强度没有针对任何 seed 校准
- 当前 anomaly 是一次性事件，不是持续异常环境
- 没有 closed-loop：个体不能反过来改变后续事件积累

没有 formal outlier 不是失败——这是第一次扫描，基准线本身就有价值。

---

## 5. 与 Phase 7 的衔接

| Phase | 发现 | 8A 的印证 |
|-------|------|-----------|
| 7.6 | sweet spot 存在 | anomaly 可以推入/推出 sweet spot |
| 7.7 | sweet spot 是 topology-relative | anomaly 效果也是 topology-dependent |
| 7.8 | 多维窄带，非简单叠加 | anomaly 是外部推力，进一步证明带是窄的 |

Phase 7 建立了"地形图"，Phase 8A 扔了一颗石头，石头滚动的方向取决于它落在哪里——而不是统一往下滚或统一往上滚。

---

## 6. 局限

- n=4，不足以建立统计显著性
- 无 |z| > 1.5 的 formal outlier
- 仅一种 anomaly 设计
- anomaly 是固定脉冲，非闭环
- 未测试不同 anomaly_step 时间点
- 未测试 anomaly 组合（多次脉冲、不同间隔）

---

## 7. 结论

1. **Anomaly 对不同 seed 的影响方向不同。** seed=999 被 anomaly 推入 significant 分叉区，seed=42 反而从 significant 降到 emerging。
2. **未达到 formal outlier 标准。** 最高 |z|=1.41，低于 1.5 门槛。
3. **效果方向与 topology-relative 框架一致。** 跨区 anomaly 补偿了 under-coupled seed 的不足，干扰了 already-tuned seed 的平衡。
4. **这是方向性证据，不是证明。** 保守表述：Phase 8A 初步显示 seed × anomaly interaction 存在方向性差异，强度不足以产生 outlier。

---

## 8. 下一步

- **Phase 8A.2**: 更强的 anomaly variant（延长重叠时间、增大强度差），测试是否可以推近 formal outlier
- **Phase 8A.3**: 更多 seed（n≥8），提高统计分辨率
- **Phase 8B**: 在 anomaly 产生清晰 outlier 后再考虑 closed-loop

---

## 9. 输出文件

| 文件 | 内容 |
|------|------|
| `results/phase8_anomaly_perturbation_120k.csv` | 40 行逐组结果 |
| `results/phase8_anomaly_perturbation_120k_summary.json` | 完整结果 JSON（gitignored） |
| `docs/phase8_anomaly_perturbation_notes.md` | 本文件 |
