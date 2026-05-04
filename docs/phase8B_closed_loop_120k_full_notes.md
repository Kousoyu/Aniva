# Phase 8B Closed-Loop World — 120k Full Run 分析

**Date:** 2026-05-04  
**Status:** 完成  
**Seeds:** 42, 77, 123, 999  
**Steps:** 120,000  
**Arms:** open_loop / closed_loop / shuffled_feedback

---

## 1. 实验配置

| 参数 | 值 |
|---|---|
| steps | 120,000 |
| event_interval | 200 |
| event_duration | 80 |
| base_p_L | 0.5 |
| feedback_gain | 2.5 |
| max_bias | 0.2 |
| feedback_interval | 200 |
| 总事件数/arm | ~599 |

每个 seed 有独立的 `base_rng_seed = 20260504 + seed` 生成不同的基础事件流。三个 arm 共享同一个基础事件流，closed_loop/shuffled_feedback 通过概率性 override 机制偏离基础流。

---

## 2. 事件分布

```
 seed                    arm      L     R   L_frac      final_wL1   mean_act
--------------------------------------------------------------------------------
   42              open_loop    278   321   0.4641   0.1970030981   0.324135
   42            closed_loop    276   323   0.4608   0.1970026586   0.298434
   42      shuffled_feedback    269   330   0.4491   0.1970023954   0.309172
   77              open_loop    285   314   0.4758   0.2028410506   0.315767
   77            closed_loop    291   308   0.4858   0.2028409278   0.318097
   77      shuffled_feedback    285   314   0.4758   0.2028410692   0.297539
  123              open_loop    273   326   0.4558   0.1951413845   0.319468
  123            closed_loop    264   335   0.4407   0.1951410014   0.305028
  123      shuffled_feedback    260   339   0.4341   0.1951405902   0.317582
  999              open_loop    299   300   0.4992   0.2007115812   0.268094
  999            closed_loop    297   302   0.4958   0.2007114795   0.257853
  999      shuffled_feedback    298   301   0.4975   0.2007115286   0.267910
```

### Δ vs open_loop

```
 seed                    arm       ΔL_frac             ΔwL1
------------------------------------------------------------
   42            closed_loop     -0.0033    -0.0000004395
   42      shuffled_feedback     -0.0150    -0.0000007026
   77            closed_loop     +0.0100    -0.0000001228
   77      shuffled_feedback     +0.0000    +0.0000000185
  123            closed_loop     -0.0150    -0.0000003831
  123      shuffled_feedback     -0.0217    -0.0000007943
  999            closed_loop     -0.0033    -0.0000001017
  999      shuffled_feedback     -0.0017    -0.0000000526
```

### 各 seed mean_lr_imbalance（来自 summary JSON）

```
 seed              arm    mean_lr_imbalance
------------------------------------------
   42        open_loop           +0.0383
   42      closed_loop           +0.0369
   42     shuffled_fb            +0.0387
   77        open_loop           -0.0197
   77      closed_loop           -0.0233
   77     shuffled_fb            -0.0211
  123        open_loop           +0.0448
  123      closed_loop           +0.0432
  123     shuffled_fb            +0.0487
  999        open_loop           +0.0167
  999      closed_loop           +0.0266
  999     shuffled_fb            +0.0143
```

---

## 3. 解读

### 3.1 事件级反馈生效

所有 4 个 seed 的 closed_loop arm 都产生了与 open_loop 不同的事件分布。ΔL_frac 范围 -0.015 到 +0.010（对应约 2-10 个事件的差异，在 ~599 个总事件中）。事件级反馈机制本身是可工作的。

### 3.2 方向因 seed 而异

- seed 42: 轻微 ↓L（-0.0033）
- seed 77: 轻微 ↑L（+0.0100）—— 注意这是唯一一个 L_frac 上升的 seed
- seed 123: 中度 ↓L（-0.0150）
- seed 999: 微小 ↓L（-0.0033）

不同拓扑产生不同的反馈方向，符合 seed-specific 预期。

### 3.3 结构级分歧未出现 — 核心发现

`final_weight_l1` 差异在 **1e-7 量级**（最大 ~8e-7），而 absolute weight_l1 值在 ~0.2。差异为基线的 **~0.0004%**。

换句话说：120,000 步的事件流差异，不足以在连接权重中留下可检测的痕迹。weight_l1 仍由初始拓扑主导，未被事件历史塑造。

**这件事本身是重要的信息：** 在当前参数下，事件级闭合回路写入结构的速度极慢。120k 步不够看。

### 3.4 shuffled_feedback 未与 closed_loop 清晰分离

两个关键 case：
- **seed=42**: shuffled ΔL_frac = **-0.0150**（比 closed_loop 的 -0.0033 大 4.5 倍）
- **seed=123**: shuffled ΔL_frac = **-0.0217**（比 closed_loop 的 -0.0150 大 50%）

shuffled_feedback 使用的是与 closed_loop 相同的 bias 分布，只是时间顺序被打乱。如果 state-timed feedback 真的在产生更"针对性"的事件偏差，closed_loop 应该表现出更大（或更结构性一致）的 ΔL_frac。实际结果恰恰相反——随机排序的 bias 产生了更大的 ΔL_frac。

这意味着：**在 120k 尺度上，观察到的 ΔL_frac 主要是 bias 分布本身的统计效应，而非 state-timed coupling 带来的增量价值。** 时间特异性尚未被证明。

---

## 4. 成功标准评估

根据实验前制定的 success criteria：

| 标准 | 状态 | 说明 |
|---|---|---|
| closed_loop ≠ open_loop（事件分布） | ✅ 通过 | 所有 4 seed 都有 ΔL_frac |
| closed_loop ≠ shuffled_feedback（时间特异性） | ❌ 未通过 | shuffled 的效应等于甚至大于 closed_loop |
| seed-specific 方向 | ⚠️ 部分 | 不同 seed 方向确实不同，但幅度小且 shuffled 未分离 |
| 结构性差异（Δfinal_weight_l1） | ❌ 未通过 | ΔwL1 在 1e-7 量级，可忽略 |

---

## 5. 为什么结构分歧未出现

几个可能的原因：

1. **event_interval 太长，事件密度低。** 120k 步只产生 ~599 个事件窗口，每个窗口 80 步。closed_loop 偏离 open_loop 2-10 个事件，占总量 0.3-1.7%。这种微小的输入差异摊到 120k 步的 plasticity 动态里，几乎不会留下痕迹。

2. **plasticity 的慢时间尺度。** 在 Aniva 当前动力学里，连接权重的变化由长期的 pre-post 相关性驱动。几十个事件差异在 120k 步的背景下，信号太小。

3. **lr_imbalance 波动大。** 看 mean_lr_imbalance，不同 arm 之间的平均值差异很小（~0.002），但 system lr_imbalance 本身在运行时波动。bias 的 sign 可能在运行中频繁翻转，导致 override 方向不持续指向同一侧。

---

## 6. 下一步方向

不急着做决定，下面列几个可能的路线：

**A. 延长步数（如 500k）**
- 最直接的做法。如果结构分歧需要更长时间积累，那就给它更多时间。
- 风险：浪费计算资源。如果 mechanism 本身太弱，长度不会修复它。

**B. 增强 feedback 强度（gain 2.5→10, max_bias 0.2→0.4）**
- 增大 override 概率和偏差幅度，在同样步数内产生更显著的事件分布差异。
- 风险：过强的 bias 可能掩盖细粒度的 state-timing 效应。

**C. 缩短 feedback loop（event_interval 200→100）**
- 双倍事件密度，增加结构性影响的可能窗口。
- 风险：事件重叠，前后事件互相干扰。

**D. 换 state variable**
- 目前用 lr_imbalance（左-右激活差），它波动大、sign 常翻。尝试用更稳定的 state 变量，如 rolling average lr_imbalance 或 energy asymmetry。
- 这本质上是改善信噪比。

**E. 接受当前结果，转其他方向**
- Phase 8B 已经验证了"state→environment→state" 这条回路在事件级可工作。
- 结构分歧可能需要 Phase 9+ 的更强 plasticity 机制，而不是在当前框架内硬堆参数。

---

## 7. 记录

- 120k × 3 arms × 4 seeds = 1,440,000 模拟步的总计算量
- 云机耗时约 30 min（4 seed 并行，每 seed 3 arm 串行）
- CSV 和 summary JSON 已拉取到本地 `results/`
- 这次实验的核心收获不是"闭环回路有效"，而是"120k 步不足以留下结构痕迹"——这为后续实验规模的选择提供了关键校准点
