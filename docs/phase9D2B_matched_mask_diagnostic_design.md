# Phase 9D.2B — Matched-Mask Diagnostic Design

> **定位：** candidate E diagnostic design，不启动 9D.3。
> 9D.2 仍保持 caveated positive，不改成 clean pass。
> simultaneous |DI| < 0.1 阈值不修改。

---

## 1. 背景

### 9D.2A 已完成排除

| Candidate | 假设 | 结论 |
|-----------|------|------|
| A | 初始拓扑 baseline 偏置 | baseline_fast_DI = +0.0096 — ruled out |
| B | Event-vector phi 覆盖不对称 | phi_mass R/L = 1.8× |
| C | 基线校正后消失 | corrected_DI = +0.154，仍 > 0.1 — ruled out |
| D | Stimulus 空间位置 | swapped L/R 后 slow_DI 完全不变 — ruled out |
| Ordering | 同一步 L/R 顺序 artifact | combined-phi 已消除 sequential，+0.1635 仍在 — ruled out |

### 当前未解释现象

```
simultaneous combined-phi slow_DI = +0.1635
超过预注册 |DI| < 0.1 阈值
```

### 剩余嫌疑方向

+0.1635 不来自 spatial/stimulus/ordering 层。剩余可能藏在：

1. **Mask / connection subset** — L→R 和 R→L 连接子图的结构差异
2. **Tag distribution** — |dW| 在 LR/RL 子图上的分布不均衡
3. **Capture aggregation** — capture 写入 slow_weight 时对某些连接子集有偏置
4. **Metric sensitivity** — slow_DI 公式在小 slow_l1 下的放大效应
5. **Consolidation false positive** — 机制层面真正产生了方向性假信号

---

## 2. 候选诊断

### E1. Matched LR/RL Connection Mask

**问题：** L→R (946) 和 R→L (938) 连接数相近（差 < 1%），但每条连接
的初始权重、度、参与事件-pair dW 的程度可能不同。直接在全部连接上
算 slow_DI 可能混入了子图结构差异。

**方法：**

```
1. 对每条连接计算：
   - initial_weight_abs = |w_init|
   - source_degree, target_degree

2. 贪婪匹配：
   - 对每个 L→R 连接，在 R→L 子图中找到
     最接近 initial_weight_abs 的连接（不重复匹配）
   - 或：对全量做 propensity score matching
     (propensity = percentile of |initial_weight|)

3. 构造 matched_mask：
   - matched_LR_ids: 被选中的 L→R 连接索引
   - matched_RL_ids: 被选中的 R→L 连接索引
   - n_matched_LR == n_matched_RL

4. 在 matched_mask 上重新计算 slow_DI：
   slow_LR_l1_matched = sum(|slow| * matched_mask_LR)
   slow_RL_l1_matched = sum(|slow| * matched_mask_RL)
   matched_slow_DI = (LR - RL) / (LR + RL + eps)
```

**判断：**
- `matched_slow_DI` 接近 0 → 原始 +0.1635 来自 LR/RL 子图的
  weight-distribution 差异被 slow_DI aggregation 放大。
- `matched_slow_DI` 仍约 +0.16 → 偏置不在 mask 层面，继续往下查。

**注意：** 匹配只在离线分析中做，不改变 train-time connection set。

---

### E2. Slow-Weight Baseline Normalization

**问题：** slow_DI = (slow_LR_l1 - slow_RL_l1) / (slow_LR_l1 + slow_RL_l1)
用绝对值比较，但 LR 和 RL 子图的初始 fast weight 总质量可能不同
（fast_LR_l1 = 470.65, fast_RL_l1 = 461.69，差 ~2%），这个差异
在 DI 公式中没有被归一化。

**方法：**

```
norm_LR = slow_LR_l1 / fast_LR_l1
norm_RL = slow_RL_l1 / fast_RL_l1
normalized_slow_DI = (norm_LR - norm_RL) / (norm_LR + norm_RL + eps)
```

**判断：**
- `normalized_slow_DI` 接近 0 → +0.1635 来自初始 fast weight mass 未归一化。
- `normalized_slow_DI` 仍约 +0.16 → 偏置不在初始质量差异。

**补充检查：**

```
norm_by_conn = (slow_LR_l1 / n_LR) / (slow_RL_l1 / n_RL)
# 比较 per-connection average slow weight
```

---

### E3. Tag Distribution Diagnostic

**问题：** slow_weight 是 tag 触发 capture 后写入的。偏置可能产生在：
- (a) tag 产生阶段 — event-pair dW 本身在 LR 子图上更大
- (b) capture 写入阶段 — tag 虽然对称但 capture 对 LR/RL 触发不均

**方法：**

在 run_simultaneous_arm 结束后，同时提取：

```
tag_LR_l1 = sum(|tag| on L→R connections)
tag_RL_l1 = sum(|tag| on R→L connections)
tag_DI = (tag_LR_l1 - tag_RL_l1) / (tag_LR_l1 + tag_RL_l1 + eps)

capture_count_LR = number of captures on L→R connections
capture_count_RL = number of captures on R→L connections
```

同时逐对事件记录 snapshot：

```
for each event pair i (i=0,1,2):
    dW_LR_l1_after_i
    dW_RL_l1_after_i
    tag_LR_l1_after_i
    tag_RL_l1_after_i
    slow_LR_l1_after_i
    slow_RL_l1_after_i
```

**判断：**
- `tag_DI` 已经偏正（与 slow_DI 同号同量级）→ 偏置来自 tag production /
  event-pair dW。需要进一步查 event-pair update 的 LR/RL 非对称性。
- `tag_DI` 接近 0 但 `slow_DI` 偏正 → 偏置来自 capture gate /
  slow_weight write 对 LR 子图的偏好。
- 逐对 snapshot 能定位偏置从第几个 pair 开始出现。

---

### E4. Full Pipeline Decomposition

**问题：** consolidation pipeline 有 7 个齿轮。当前只看了最终的 slow_l1。
需要逐层看偏置的量级和方向。

**方法：**

对 L→R 和 R→L 子图分别计算以下指标（simultaneous arm 跑完后）：

```
Layer 0 (connection structure):
  n_LR, n_RL
  mean_|w_init|_LR, mean_|w_init|_RL
  mean_source_degree_LR, mean_source_degree_RL

Layer 1 (event-pair dW, by event pair):
  dW_LR_l1, dW_RL_l1  (per event pair)
  dW_DI = (dW_LR_l1 - dW_RL_l1) / (dW_LR_l1 + dW_RL_l1 + eps)

Layer 2 (tag, by event pair):
  tag_LR_l1, tag_RL_l1
  tag_DI

Layer 3 (capture signal):
  mean_capture_signal on LR-source units
  mean_capture_signal on RL-source units
  correlation(capture_signal, tag_mass) per connection

Layer 4 (slow_weight):
  slow_LR_l1, slow_RL_l1
  slow_DI
```

**判断：**
- 从 Layer 0 到 Layer 4 逐层追踪，找到偏置首次显著出现的层。
- 如果 dW_DI 已经偏正 → 问题在 event-pair plasticity 的计算方式。
- 如果 dW_DI ≈ 0 但 tag_DI 偏正 → 问题在 tag = |dW| 的绝对值操作
  （可能 dW 在 LR 和 RL 上分布对称但有一个长尾在某一侧，|dW| 把对称性打破了）。
- 如果 tag_DI ≈ 0 但 slow_DI 偏正 → 问题在 capture / slow_weight write。

---

### E5. Shuffled-Label Null Distribution

**问题：** slow_DI = +0.1635 本身是否显著？在小 slow_l1
（simultaneous total = 9.9e-5）下，DI 指标对微小差异敏感。
需要估计在"无真方向信号"的 null 假设下 DI 的分布。

**方法：**

```
1. 固定已跑完的 simultaneous arm 的 slow_weight 和 connection 信息不变。

2. 多次 shuffle（N=1000 或更多）：
   - 随机打乱 LR/RL 标签
   - 保持连接数不变，但重新 allocate "LR" / "RL" label
   - 每次 shuffle 后重新计算 slow_DI

3. 构建 null distribution：
   - null_mean_DI
   - null_std_DI
   - null_95pct
   - observed_slow_DI 在 null distribution 中的 percentile

4. 也做 matched-label shuffle：
   - 先在 LR 和 RL 子图中做 matched sampling
   - 再 shuffle matched labels
   - 看 matched + shuffled 的 null distribution
```

**判断：**
- observed +0.1635 在 null distribution 的 95th percentile 以内 →
  slow_DI 在小 slow_l1 下固有噪声，+0.1635 不显著。
- observed 显著高于 null → 存在稳定的 consolidation-level directionality，
  即使在 simultaneous control 中也产生方向性 slow weight。
- matched + shuffled 后 null 收紧 → 验证 mask matching 的有效性。

---

## 3. Decision Rules

优先级：E3 (tag trace) → E4 (full decomposition) → E1 (matched mask) → E2 (normalization) → E5 (shuffle null)

```
1. tag_DI 已偏正
   → 偏置源头在 event-pair dW / tag 产生阶段
   → 检查 event_pair_update 中 trace·phi correlation
      在 L→R vs R→L connection 上的非对称性
   → 可能原因：
     a. dW 分布的 skew 在一个子图上更重（|dW| 放大）
     b. phi 向量在 source/target 上的投影不对称
     c. trace 积累的方向性（即使 combined phi，trace 也可能偏）

2. tag_DI ≈ 0 但 slow_DI 偏正
   → 偏置在 capture / slow_weight write 阶段
   → 检查 capture_signal 在 LR vs RL source units 上的差异
   → 可能原因：
     a. energy/trace gate 对 L-hemi vs R-hemi units 不同
     b. capture threshold 在某一侧更容易达到
     c. slow_weight write 的 magnitude 有方向性

3. matched_mask + normalized 后 slow_DI 接近 0
   → 原始 +0.1635 是 mask + metric aggregation 的组合效应
   → 9D.2 simultaneous caveat 可解释为 analysis-level artifact
   → 9D.3 可直接推进，带上 matched mask + normalized DI 作为辅助指标

4. shuffled null 下 observed DI 不显著
   → +0.1635 在小 slow_l1 下不构成显著偏离
   → simultaneous control 实际是干净的
   → 可考虑将 simultaneous |DI| 阈值从 0.1 放宽到 0.2
     （⚠️ 不推荐，违反预注册原则；仅作为理解性记录）

5. 所有 E1-E5 都无法解释 +0.1635
   → 确认存在 consolidation false positive
   → 需要在 9D.3 前重新审视 capture gate / tag accumulation 的方向性保证
   → 考虑加 directionally-symmetric capture 或 tag normalization
```

---

## 4. 实现计划

```
aniva/experiments/exp9D2B_matched_mask_diagnostic.py  (实现时创建)
```

所需功能：

```
measure_tag_distribution(cfg) → tag_LR_l1, tag_RL_l1, tag_DI
  (从已跑完的 simultaneous arm 的 tag_cache 提取)

measure_pipeline_decomposition(cfg) → dict of layer-by-layer metrics
  (逐层 dW/tag/slow 分解)

construct_matched_mask(connections, n_matched) → matched_indices
  (基于 initial |weight| 匹配)

compute_matched_slow_DI(slow_weights, matched_mask) → float

compute_normalized_slow_DI(slow, fast, is_LR, is_RL) → float

shuffle_null_distribution(slow_weights, is_LR, is_RL, n_shuffles) → stats
```

所有诊断优先做离线 analysis，不修改 `update/capture/consolidation` 机制。

---

## 5. 边界

- 不修改 9D.2 阈值
- 不把 9D.2 改写成 clean pass
- 不启动 9D.3
- 不调参
- 不改机制公式（capture signal / tag / slow_weight 不变）
- 所有 E 诊断优先做离线 analysis
- arm/L/R labels 只用于离线 metric grouping
- 不引入 reward / goal / agent / emotion / LLM

---

## 6. 与后续阶段的关系

- **9D.2B 完成诊断** → 判明 simultaneous +0.1635 的真正来源
- **诊断为 mask/metric artifact** → 9D.3 推进，带上 matched/normalized DI
  作为辅助指标
- **诊断为 tag/capture-level bias** → 9D.3 前需修复 tag directionality 或
  capture symmetry
- **诊断为 consolidation false positive** → 9D.3 前需重新审视 capture gate
  设计
- **诊断 inconclusive** → 9D.3 保留 simultaneous arm，将所有 E 指标作为
  covariates

---

## 7. 文件规划

```
docs/phase9D2B_matched_mask_diagnostic_design.md  ← 本文档
aniva/experiments/exp9D2B_matched_mask_diagnostic.py  (实现时创建)
```
