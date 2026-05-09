# Phase 9D.2C — Event-Pair Projection Diagnostic Design

> **定位：** 追查 simultaneous +0.1635 在 event-pair dW 层的根因。
> 9D.2B.1 已确认偏置在 Layer 1 (dW) 出现，tag/capture/slow_weight 不引入额外偏置。
> 本诊断检查 raw eligibility = trace[source] × phi[target] 在 LR/RL 子图上的投影。

---

## 1. 背景

### 9D.2B.1 关键发现

```
Layer 1 dW (pair 1):  dW_LR=2.58e-05  dW_RL=1.85e-05  dW_DI=+0.1635
Layer 2 tag:          tag_DI=+0.1635  (lossless)
Layer 4 slow:         slow_DI=+0.1635  (lossless)
```

dW_DI = +0.1635 在 pipeline 入口就存在。后续层忠实传递。

### 当前假设

```
combined L+R phi field
  → trace × phi Hebbian correlation
  → projected onto directed LR/RL connection masks
  → inherent projection asymmetry
  → dW_DI ≠ 0
```

### 问题

偏置是来自 `apply_event_pair_update` 内部的 normalization / clipping / L1 constraint，
还是来自 raw eligibility 本身的几何投影？

---

## 2. 候选诊断

### C1. Raw Eligibility Extraction

**目标：** 在 `apply_event_pair_update` 入口处，提取 raw eligibility 矩阵，
按 LR/RL mask 聚合，看 raw_DI 是否已经偏正。

**方法：**

```
在 simultaneous arm 的 Pair 1 (step 3500) 时：

1. 记录进入 apply_event_pair_update 的：
   - trace: O(N) array (来自过去 phi 积累)
   - phi: O(N) array (当前 combined L+R phi)

2. 对每条连接 (src → tgt)，计算 raw eligibility：
   raw_ij = trace[src] × phi[tgt]

3. 按 LR/RL mask 聚合：
   raw_LR_sum = sum(raw_ij for ij in LR connections)   (signed sum)
   raw_RL_sum = sum(raw_ij for ij in RL connections)
   raw_LR_l1  = sum(|raw_ij| for ij in LR connections)
   raw_RL_l1  = sum(|raw_ij| for ij in RL connections)

4. 计算两种 DI：
   raw_DI_sum  = (raw_LR_sum - raw_RL_sum) / (raw_LR_sum + raw_RL_sum + eps)
   raw_DI_l1   = (raw_LR_l1 - raw_RL_l1) / (raw_LR_l1 + raw_RL_l1 + eps)

5. 同时提取：
   raw_LR_mean = raw_LR_l1 / n_LR
   raw_RL_mean = raw_RL_l1 / n_RL
   raw_LR_pos_frac = fraction of raw_ij > 0 on LR
   raw_RL_pos_frac = fraction of raw_ij > 0 on RL
```

**判断：**
- `raw_DI_l1 ≈ +0.1635` → raw eligibility 已经偏置，
  `apply_event_pair_update` 只是忠实写入。根在 trace/phi geometry × mask projection。
- `raw_DI_l1 ≈ 0` 但 `dW_DI ≈ +0.1635` →
  `apply_event_pair_update` 内部的 normalization / L1 target constraint / gate
  在 LR/RL 子图上产生了不对称放大。
- `raw_DI_sum` 与 `raw_DI_l1` 符号不同 → dW 有正负混合，
  |dW| 操作改变方向性。

---

### C2. Source/Target Phi Decomposition

**目标：** 把 trace 和 phi 在 L-hemi 和 R-hemi 的分量拆开，
看 trace×phi 在四个方向子图 (LL, LR, RL, RR) 上的分布。

**方法：**

```
定义四个 unit mask：
  is_L_unit: position x < -0.1
  is_R_unit: position x > 0.1

trace_L = trace · is_L_unit  (trace at L-hemi units)
trace_R = trace · is_R_unit
phi_L   = phi · is_L_unit
phi_R   = phi · is_R_unit

四个连接子图：
  L→L: src∈L, tgt∈L  (not analyzed further)
  L→R: src∈L, tgt∈R  ← 关注
  R→L: src∈R, tgt∈L  ← 关注
  R→R: src∈R, tgt∈R  (not analyzed further)

对每个连接子图，计算：
  sum(trace[src] × phi[tgt]) / sum(|trace[src] × phi[tgt]|)

L→R 子图：
  src 主要在 L-hemi → trace 分量 ≈ trace_L
  tgt 主要在 R-hemi → phi 分量 ≈ phi_R
  但 trace 在 L-hemi 也有从 R-phi 泄漏的分量
  (trace 是过去 phi 的累加，而 past phi 是 combined L+R)

R→L 子图：
  src 主要在 R-hemi → trace 分量 ≈ trace_R
  tgt 主要在 L-hemi → phi 分量 ≈ phi_L
```

**判断：**
- 如果 `trace_L_mass` 与 `trace_R_mass` 不对称 →
  偏置来自 trace 在 L/R 半球的累积差异（过去 combined phi 的不对称沉积）。
- 如果 trace 对称但 `phi_L_mass ≠ phi_R_mass` →
  偏置来自当前 phi 的 L/R 不对称（phi_R mass = 1.8× phi_L mass）。
- 如果两者都对称但 raw_DI 仍偏置 →
  可能与连接权重分布 / 稀疏性 / per-connection degree 有关。

---

### C3. Matched-Mask Raw Eligibility

**目标：** 在 matched LR/RL connection mask 上计算 raw eligibility，
排除连接数量和初始权重分布差异。

**方法：**

```
1. 从 LR 和 RL 子图中按 |initial_weight| 最近邻匹配采样
   (同 9D.2B E1 方法)

2. 在 matched mask 上计算：
   raw_LR_l1_matched
   raw_RL_l1_matched
   raw_DI_matched

3. 也做按 connection count 归一化的版本：
   raw_LR_per_conn = raw_LR_l1 / n_LR
   raw_RL_per_conn = raw_RL_l1 / n_RL
   raw_DI_per_conn = (raw_LR_per_conn - raw_RL_per_conn)
                     / (raw_LR_per_conn + raw_RL_per_conn + eps)

4. 也做按 fast_weight_mass 归一化的版本：
   raw_LR_norm = raw_LR_l1 / fast_LR_l1
   raw_RL_norm = raw_RL_l1 / fast_RL_l1
   raw_DI_norm = (raw_LR_norm - raw_RL_norm)
                 / (raw_LR_norm + raw_RL_norm + eps)
```

**判断：**
- `raw_DI_matched ≈ 0` → 原始 +0.1635 来自 mask 结构差异（连接数/权重分布），
  不是 trace/phi 场本身的方向性。
- `raw_DI_per_conn ≈ 0` → 偏置来自 per-connection 数量差异。
- `raw_DI_norm ≈ 0` → 偏置来自初始 fast weight mass 差异。
- 三者都仍偏正 → trace/phi 场在当前 directed topology 上确有方向投影偏置。

---

### C4. Raw → dW Transformation Trace

**目标：** 检查 `apply_event_pair_update` 内部从 raw eligibility
到最终 dW 的变换步骤，定位哪一步在 LR/RL 上产生了不对称。

**方法：**

```
在 apply_event_pair_update 内部插入诊断 hooks (仅 9D.2C 使用)：

1. raw_ij = trace[src] × phi[tgt]                  (raw eligibility)
2. eligibility = gate(raw_ij)                       (gate function)
3. dW_raw = eligibility × some_rate                 (scaled update)
4. dW = L1_normalize(dW_raw, target_l1)             (L1 constraint)
5. weight += dW                                     (apply)

每一步后在 LR/RL 子图上计算 l1 和 DI：

  step1 raw_DI
  step2 gated_DI
  step3 scaled_DI
  step4 L1_normalized_DI
  step5 final dW_DI (same as Layer 1 in 9D.2B.1)
```

**判断：**
- 偏置在哪一步首次出现（或显著放大）→ 定位到具体变换。
- 如果 L1 normalization 把小的 asymmetry 放大 →
  L1 constraint 对不对称输入敏感。
- 如果 gate 函数改变了 LR/RL 的相对大小 → gate 行为不对称。

---

## 3. Decision Rules

优先级：C1 (raw eligibility) → C2 (source/target decomposition) → C3 (matched mask) → C4 (step trace)

```
1. raw_DI_l1 ≈ +0.1635
   → 偏置在 raw eligibility 层已存在
   → C2: 拆解 trace_L/R × phi_L/R 贡献
   → 如果 trace_R_mass > trace_L_mass → trace 累积不对称
   → 如果 phi_R_mass > phi_L_mass → phi 场不对称 (1.8×)
   → 两者共同导致 L→R vs R→L 投影的 geometric imbalance

2. raw_DI_l1 ≈ 0 but dW_DI ≈ +0.1635
   → 偏置在 apply_event_pair_update 内部引入
   → C4: 逐步追踪 raw → gate → scale → L1_norm → dW
   → 定位具体变换步骤

3. matched-mask raw_DI ≈ 0
   → 原始偏置是 mask aggregation artifact
   → 9D.2 simultaneous caveat 可解释为 analysis-level 而非 mechanism-level
   → 9D.3 推进时可带 matched mask DI 作为辅助指标

4. 所有 C1-C3 后 raw_DI 仍然偏正
   → combined simultaneous 场在 directed topology 上天然有方向投影
   → 这是 physics，不是 bug
   → 考虑：simultaneous near-zero threshold 是否对 combined-phi 场景过严
   → (⚠️ 不修改阈值，仅作为理解性记录)
   → 或：设计真正 null 的 simultaneous control
     (e.g. phi = gaussian noise with matched mass)
```

---

## 4. 实现计划

```
aniva/experiments/exp9D2C_projection_diagnostic.py  (实现时创建)
```

所需功能：

- `extract_raw_eligibility(life_core, trace, phi, is_LR, is_RL)` → raw_DI 等
- `decompose_source_target(trace, phi, positions)` → trace_L/R_mass, phi_L/R_mass
- `compute_matched_raw_DI(raw_ij, is_LR, is_RL, fast_weights)` → matched raw_DI
- (如需 C4) 临时 hooks 在 `apply_event_pair_update` 内部

优先实现 C1 和 C2（不需要修改机制代码），C3 和 C4 按需启用。

---

## 5. 边界

- 不修改 9D.2 阈值
- 不把 9D.2 改写成 clean pass
- 不启动 9D.3
- 不调参
- 不改机制公式
- arm/L/R labels 仅用于离线 grouping
- 如需要 C4 的 step-by-step trace，该 hooks 仅用于诊断，不进入主路径

---

## 6. 文件规划

```
docs/phase9D2C_event_pair_projection_diagnostic_design.md  ← 本文档
aniva/experiments/exp9D2C_projection_diagnostic.py  (实现时创建)
```
