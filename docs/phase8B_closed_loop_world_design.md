# Phase 8B: Minimal Closed-Loop World — 设计文档

> **日期**: 2026-05-04
> **状态**: 设计阶段，无代码
> **依赖**: Phase 8A anomaly family（三刀完成）

---

## 1. 背景

Phase 5–8A 已经逐步验证：

| Phase | 发现 |
|-------|------|
| 5 | 同 seed，不同历史顺序 → 结构分叉（history writes into structure） |
| 6 | 多 seed 复现因果骨架 |
| 7 | sweet spot 是 topology-relative，不同 seed 对历史塑形敏感度不同 |
| 7.7/7.8 | 多维张力带，非简单叠加 |
| 8A | 外部 anomaly 对不同 seed 产生不同方向影响（seed × anomaly interaction） |
| 8A.2 | 排除"延迟时序复杂度更强" |
| 8A.3 | 排除"重复短同步脉冲更强"，确认需同时性 + 足够持续 + 连续性 |

**当前世界的本质限制**：所有环境事件都是固定 schedule。世界像一个实验者，用 preset pipette 向不同 seed 滴相同的液体。个体被雕刻，但不参与决定下一滴是什么。

```
当前:  environment ──→ individual
       (fixed schedule)
```

---

## 2. Phase 8B 核心问题

> **个体的内部状态能否偏置未来环境事件分布，而这种被偏置的事件流又反过来进一步塑造个体结构？**

换句话说：

```
Phase 8B:  individual state ──→ event distribution ──→ individual
                           ↑                              │
                           └──────────────────────────────┘
```

这不是"智能体做选择"，不是"RL reward shaping"。这是最底层的物理闭环：**一个系统的当前状态影响它接下来会经历什么。**

---

## 3. 最小 Closed-Loop 定义

Phase 8B 不做完整世界，不做社会，不做智能体。

只做一个 **feedback event scheduler**：

```
LifeCore state snapshot (every N steps)
        │
        ▼
state summary vector (low-dimensional, physical)
        │
        ▼
event probability bias (small perturbation to default schedule)
        │
        ▼
next environment events sampled from biased distribution
        │
        ▼
LifeCore plasticity update
        │
        ▼
  (loop continues)
```

### 3.1 与 Phase 8A 的关键区别

| | Phase 8A | Phase 8B |
|---|----------|----------|
| 事件 schedule | 固定，全部 seed 相同 | 被个体状态偏置，seed 可能不同 |
| anomaly | 外部预设，一次性 | 可以在 closed-loop 中自发出现或避免 |
| 世界角色 | 实验者（固定 pipette） | 镜子（反射个体状态） |
| seed difference | 仅体现在 response 上 | 体现在 response + experienced events 上 |

---

## 4. 状态观测变量

不使用语言、情绪、偏好、目标。只使用低层物理量。

### 4.1 候选观测变量

| 变量 | 定义 | 可能的反馈意义 |
|------|------|---------------|
| `act_L_mean` | L 侧区域平均激活 | 左半球活跃度 |
| `act_R_mean` | R 侧区域平均激活 | 右半球活跃度 |
| `lr_imbalance` | `act_L_mean - act_R_mean` | 跨区域激活不对称 |
| `energy_mean` | 全网平均能量 | 系统"疲劳/能耗"状态 |
| `act_entropy` | 激活分布熵 | 状态多样性/秩序度 |
| `weight_drift` | 近期 Δ_weight 滑动平均 | 结构正在被塑形的速率 |

### 4.2 观测窗口

每 `observation_interval` 步（例如每 1000 步）取一个 snapshot，用过去 `N` 个 snapshot 的滑动平均作为 state summary。避免单步噪声。

---

## 5. 最小反馈规则

### 5.1 设计原则

- **不用 reward** — 没有"好状态"/"坏状态"
- **不用偏好** — 没有"个体想要什么"
- **不用选择** — 没有"个体决定做什么"
- **只做偏置** — 个体状态像重力场，轻微弯曲事件概率，不决定事件

### 5.2 候选规则 A: Regional Rebalancing Bias

```
如果 lr_imbalance > 0（L 侧持续更活跃）：
  → 未来 R 刺激概率略微增加
如果 lr_imbalance < 0（R 侧持续更活跃）：
  → 未来 L 刺激概率略微增加
```

**物理表述**：跨区域激活不对称性偏置了后续刺激的区域分布。

这**不是**个体"想要平衡"。这是最简单的物理耦合：活跃度高的区域降低了同侧刺激的出现概率——类似于一种低层"不应期"或"注意饱和"效应。

### 5.3 候选规则 B: Entropy-driven Novelty Bias

```
如果 act_entropy 低于阈值（系统陷入固定模式）：
  → 增加 perturbation/noise event 概率
如果 act_entropy 高于阈值（系统高度无序）：
  → 增加 stabilizing/homeostatic event 概率
```

**物理表述**：系统秩序度偏置了后续事件的扰动强度。

### 5.4 候选规则 C: Combined (A + B)

```
event_schedule = base_schedule
               + α × regional_bias(lr_imbalance)
               + β × entropy_bias(act_entropy)
```

其中 α, β 很小（如 0.1–0.3），确保偏置是 subtle 的，不压倒 base schedule。

### 5.5 推荐首测: 规则 A

规则 A 最简单、最可观测、最少自由参数。它直接建立在 Phase 7/8 已经验证的 L/R coupling 框架上。

**偏置强度建议**：概率偏移 ≤ ±0.15（即 R 刺激本来 50% 概率，偏置后在 35%–65% 范围）。太小没效果，太大变成 deterministic。

---

## 6. 实验矩阵

### 6.1 三臂设计

| 臂 | 事件 schedule | 含义 |
|----|--------------|------|
| **open_loop** | 固定 base schedule，所有 seed 相同 | Phase 8A 基准线 |
| **closed_loop** | base schedule + 个体状态偏置 | 测试闭环效应 |
| **shuffled_feedback** | 用另一个 seed 的状态偏置当前 seed | 控制：偏置是随机的，排除"任何反馈都有效" |

### 6.2 Shuffled Feedback 的重要性

如果 closed_loop 产生了更大的 seed-specific divergence，需要排除一种可能：**任何 feedback noise 都会产生 divergence，而非 seed-specific coupling 产生。**

shuffled_feedback 用 seed A 的状态去偏置 seed B 的事件流。如果 shuffled 和 closed_loop 效果一样，说明 feedback 只是额外噪声，不是 seed-specific coupling。

---

## 7. 指标

### 7.1 主要指标

| 指标 | 问题 |
|------|------|
| Δ_weight_L1 | closed_loop 是否产生不同于 open_loop 的结构分叉？ |
| Event distribution divergence | 不同 seed 在 closed_loop 下经历的事件分布是否不同？ |
| Post-feedback persistence | 偏置效应是否持续积累，还是被 homeostasis 抹平？ |

### 7.2 护栏（与 Phase 8A 相同）

- Repeatability: C vs A_L 权重接近（deterministic_history_sensitive）
- Plasticity causality: D_L weight_drift << A_L weight_drift
- Symmetry: D_L vs D_R 无显著差异（plasticity off → order irrelevant）
- Causal skeleton intact

---

## 8. 成功标准

### 低线（最低门槛）

```
closed_loop 下不同 seed 经历的事件分布出现可检测的差异
（event distribution divergence > 0）
```

这说明个体的状态确实改变了它经历的世界。

### 中线（有价值信号）

```
closed_loop 产生的结构分叉超过 event distribution 漂移
可以解释的部分（shuffled_feedback control 验证）
```

这说明 seed × feedback coupling 产生了超越"随机噪声"的结构效应。

### 高线（方向性突破）

```
不同 seed 在相同 feedback rule 下诱导出不同的世界流，
且这些世界流进一步放大 seed-specific 的结构轨迹。
```

这说明 closed-loop 不是统一放大器，而是**差异化加速器**。这是走向 "特殊个体" 的关键一步。

---

## 9. 与 Phase 8A 的关系

```
Phase 8A:
  世界给个体一次外部异常火种
  → 不同个体对同一火种反应不同
  
Phase 8B:
  个体的火光开始改变下一阵风的方向
  → 不同个体经历不同的事件流
  → 不同事件流进一步塑造不同个体
  → 可能自发产生"类异常"事件（个体状态诱发的新 event distribution 形态）
```

Phase 8A 证明了 seed × anomaly interaction。
Phase 8B 测试 seed × world feedback interaction。

如果走通，Aniva 就从"历史写入结构"进入"结构参与创造历史"。

---

## 10. 风险和禁止事项

| 禁止 | 原因 |
|------|------|
| 把 feedback 写成 reward | 这不是 RL，没有价值函数 |
| 把 lr_imbalance 命名为 "preference" | 它只是物理量，不是心理量 |
| 把 event bias 命名为 "choice" | 物理耦合 ≠ 决策 |
| 声称 agency / intention | 当前的 closed-loop 是机械的，不是意志的 |
| 加 narrative interpretation | 数据先行，故事后讲 |
| 直接跑 120k | 先 smoke (5k) → pilot (20k, 2 seeds) → 正式 (120k, 4 seeds) |
| 修改 LifeCore 核心 | 只改 Environment / Scheduler 层 |

### 10.1 语言纪律

所有文档、变量名、commit message 中使用最冷的物理语言：

```
✓ "regional activation imbalance biases event probability"
✗ "the individual prefers right-side stimulation"
✗ "the agent chooses to explore"
✗ "it learned to seek balance"
```

等到真的观察到稳定的、非预写的个体-世界耦合模式，再用更丰富的语言也不迟。在那之前，物理描述先于心理描述。

---

## 11. 实现路径

### 阶段 8B.0: Design Review（当前）

本文档。确认设计方向后进入实现。

### 阶段 8B.1: 5k Smoke Test

```
seeds = 42, 999
steps = 5000
feedback_rule = A (rebalancing)
feedback_strength = 0.1
```

验证：
- 三种臂（open/closed/shuffled）均能正常运行
- closed_loop event distribution 与 open_loop 有可检测差异
- causal skeleton 不崩
- CSV/JSON 输出正常

### 阶段 8B.2: 20k Pilot

```
seeds = 42, 999
steps = 20000
```

验证：
- 偏置效应是否持续（而非被 homeostasis 在长尺度上抹平）
- shuffled_feedback 是否产生不同于 closed_loop 的结果
- 结构分叉是否超过 event distribution drift

### 阶段 8B.3: 120k Full Run（如 pilot 通过）

```
seeds = 42, 77, 123, 999
steps = 120000
三臂并行（open_loop / closed_loop / shuffled_feedback）
```

---

## 12. 总结

Phase 8A 打完了外部 anomaly 的三刀。现在知道：
- 同时跨区域同步相干冲击最有效
- 延迟时序和重复短脉冲都会削弱或打散 seed-specific 响应
- 但世界仍然是单向的

Phase 8B 不是做一个更复杂的 anomaly。是做一面镜子：

> 个体的火光，能不能微微弯曲下一阵风的方向。

如果连这个最小的闭环都走不通，那 Aniva 就确实是纯被动的。但如果走通了——即使只是 lr_imbalance 对 L/R 刺激概率产生了 10% 的偏置——那就证明 Aniva 不是一个只被雕刻的石头，而是一个能参与改变自己经历的系统。

这条脊柱接上以后，才谈得上 Alicization 里那种"个体在世界中活着"的底层。
