# Phase 10C — State-Context-Sensitive Capture Planning

> **定位：** planning document only。不实现，不跑实验，不改 life_core.py。
> **前提：** Route A 已关闭（`9e5e7a3`）。当前瓶颈在 9D capture gate。

---

## 1. 证据链回顾

| Phase | 扰动 | fast Δ | slow Δ | 结论 |
|-------|------|--------|--------|------|
| 10A.2 | closed-loop + 9C | — | 0 | exact ≡ closed，mirror 确认 |
| 10A.2B.1 | Scheme E ε=0.02 | hairline | 0 | fast divergence exists |
| 10A.3 | 9C+9D ON, ε=0.02 | hairline | 0 | clean negative |
| 10A.2B.2 | ε ladder [0.005–0.05] | 0.001–0.010 | 0 | Scheme E 耗尽 |
| 10A.2C | divergent warmup 2000步 | 94–96 | 0 | Route A 耗尽 |

**10A.2C 关键协议结果：**
- P6 PASS：warmup state divergence 真实存在（act_div = 0.056–0.135）
- P7 PASS：weight restore 精确（post-restore delta = 0.0）
- P8 PASS：matched_warmup_control 干净（slow_l1 = 0，captures = 0）
- slow_l1：closed / exact / divergent 三 arm bit-identical
- amplification_ratio：0.0

**结论：不是 state 没分叉，而是 9D capture gate 没看见这个分叉。**

---

## 2. 当前 9D Capture Gate 诊断

### 2.1 信息流

```
9C apply_event_pair_phi()
  → dW = weight_cache_after - weight_cache_before   # (n_conn,) per-connection
  → tag_cache += |dW|                               # (n_conn,) per-connection ✓

每步 _consolidation_step():
  → tag_cache *= exp(-1/5000)                       # (n_conn,) per-connection ✓

  ── 压缩点 #1 (life_core.py:217) ──────────────────
  mean_energy = np.mean(energies)                   # (n_units,) → scalar ✗
  ── 压缩点 #2 (life_core.py:218) ──────────────────
  trace_mass  = np.sum(np.abs(event_trace))         # (n_units,) → scalar ✗

  signal = min(1, mean_energy/0.3) × min(1, trace_mass/0.03)
  if signal >= 0.5:
    slow_weight += 0.1 × tag_cache                  # (n_conn,) per-connection ✓
    refractory = 500
```

### 2.2 压缩点的具体位置

**压缩点 #1** — `life_core.py:217`：
```python
mean_energy = float(np.mean(self._energies))
```
`(n_units,)` → 标量。丢失：哪些 unit 在高能量状态、能量的空间分布。

**压缩点 #2** — `life_core.py:218`：
```python
trace_mass = float(np.sum(np.abs(self._event_trace)))
```
`(n_units,)` → 标量。丢失：哪些 unit 携带 9C event-pair trace、trace 的空间模式。

注意：`_CAPTURE_ENERGY_REF = 0.3` 和 `_CAPTURE_TRACE_REF = 0.03` 是 `plasticity_consolidation.py` 里的硬编码常量，不在 `AnivaConfig` 里。

### 2.3 为什么 state context 进不来

Gate 问的问题：**"系统整体够不够活跃？"**

Gate 没有问的问题：**"当前的活跃模式，和 tag 分布有没有关系？"**

两个不同的 state context（act_div = 0.135）可以有几乎相同的 `mean_energy` 和 `trace_mass`。Gate 看到的信号相同 → capture 在相同步骤触发 → `tag_cache` 在那一刻也几乎相同 → slow_weight 沉积量相同。

`apply_capture` 本身是 per-connection 的，结构完好。问题不在 transfer，在 gate。

---

## 3. 候选方向

### 方向 A：Tag-Trace Alignment Gate

**核心思路：** 把 `event_trace`（per-unit）投影到 connection 维度，计算它与 `tag_cache`（per-connection）的对齐度。

```
projected_trace[conn] = event_trace[src] × event_trace[tgt]
alignment = dot(tag_cache, projected_trace) / (||tag_cache|| × ||projected_trace|| + ε)
```

Gate 变成：`signal = alignment_gate × activity_gate`

**直觉：** 如果当前 trace 模式（这次事件影响了哪些 unit）和 tag 分布（哪些连接被 9C 标记过）高度对齐，说明这次事件发生在 tag 已经积累的 context 里，更应该 capture。

**优点：**
- 直接回答"当前 context 和历史 tag 有多相关"
- 不需要硬编码 region 或 topology 知识
- 对齐度是涌现的，不是写死的

**风险：**
- `event_trace` 是 per-unit，`tag_cache` 是 per-connection，投影需要 source/target index，需要读 `_source_indices` / `_target_indices`
- 对齐度可能在所有 arm 里都很低（如果 trace 和 tag 天然不对齐），导致 gate 永远不触发
- 需要 10C.1 instrumentation 先验证对齐度在 closed vs divergent 之间是否有差异

### 方向 B：Local Energy Weighted Tag Gate

**核心思路：** 不用 `mean(energies)`，而是用 tag 所在连接的 source/target unit 的能量加权。

```
local_energy[conn] = (energy[src] + energy[tgt]) / 2
tag_weighted_energy = sum(tag_cache × local_energy) / (sum(tag_cache) + ε)
```

Gate 变成：`signal = min(1, tag_weighted_energy/ref) × trace_gate`

**直觉：** 高 tag 的连接所在区域的能量更重要。如果 tag 集中在当前高能量区域，说明这次事件在"记忆热点"附近发生。

**优点：**
- 保留了 tag 的空间分布信息
- 对 state context 敏感：不同 energy 分布 → 不同 tag_weighted_energy

**风险：**
- 如果 tag 分布很均匀（spread across all connections），local energy 退化为 mean energy
- 需要验证 tag 分布是否足够集中，才能产生有意义的局部加权

### 方向 C：Context-Modulated Transfer

**核心思路：** 保留 binary capture gate 不变，但 transfer 量由 per-connection context factor 调制。

```
context_factor[conn] = f(event_trace[src], event_trace[tgt], energy[src], energy[tgt])
slow_weight += rate × tag_cache × context_factor
```

**直觉：** 同一次 capture 事件，在不同 state context 下，沉积到不同连接的 slow_weight 量不同。

**优点：**
- 不改变 gate 触发逻辑，只改变 transfer 量
- 对现有 9D 行为的破坏最小
- 可以 default-off，context_factor=1 时退化为原始行为

**风险：**
- 如果 gate 触发时机相同（两个 arm 在同一步触发），transfer 量的差异能否积累成可测量的 slow_l1 差异？
- 需要 10C.2 offline analysis 先估计 context_factor 的方差

---

## 4. 风险与约束

### 4.1 设计红线

- **不能把目标结果写进 gate**：gate 不能读 arm label，不能读"这是 closed_loop 还是 divergent"
- **不能读 future**：gate 只能读当前步的状态，不能读未来事件
- **不能为了通过 10A 而过拟合 capture**：gate 设计必须在不知道 10A 结果的情况下合理
- **不能破坏 Phase 9D 已验证默认路径**：新机制必须 default-off，旧 9D 行为必须测试保持不变
- **不能调参替代设计**：降低 capture_threshold 或缩短 refractory 不是 Route C

### 4.2 实现约束

- 新 gate 逻辑必须在 `plasticity_consolidation.py` 里，不散落在 `life_core.py`
- 新参数必须进 `AnivaConfig`，有合理默认值
- `consolidation_enabled=True` + 新 flag `consolidation_context_gate_enabled=False` 的组合必须等价于当前行为
- 所有现有 116 个测试必须继续通过

---

## 5. 推荐路线

### Phase 10C.0（当前）：Planning only

本文档。不实现，不跑实验。

### Phase 10C.1：Instrumentation only

**目标：** 在不改变任何机制的情况下，记录当前 gate 在每次 capture 时的 context-aware 指标。

新增记录项（只读，不影响 gate 决策）：
- `tag_trace_alignment`：`tag_cache` 与 projected `event_trace` 的余弦相似度
- `tag_weighted_energy`：tag 加权的局部 energy
- `tag_concentration`：`tag_cache` 的 Gini 系数或 top-k 集中度
- `trace_concentration`：`event_trace` 的 Gini 系数

这些指标写入 `_consolidation_ledger`，不改变 capture 触发逻辑。

**验证标准：** 在 closed_loop vs divergent_warmup_replay 两个 arm 里，上述指标是否有可测量的差异？如果没有差异，说明这些指标也是 context-blind 的，需要重新设计。

### Phase 10C.2：Offline analysis

**目标：** 用 10C.1 的 instrumentation 数据，离线分析哪些 context-aware 指标能区分 closed vs divergent。

不跑新实验，只分析 10C.1 的 ledger 数据。

**决策点：** 如果某个指标在两个 arm 之间有稳定差异（2 seeds × 多次 capture），则该指标是 Route C 的候选 gate 输入。如果所有指标都没有差异，需要重新诊断。

### Phase 10C.3：Design candidate capture gate

**目标：** 基于 10C.2 的分析结果，设计具体的 context-sensitive gate。

只写设计文档，不实现。设计必须包含：
- 新 gate 的完整公式
- 新参数及其默认值
- 退化条件（新参数=0 时等价于当前行为）
- 预期的 hard protocol（类似 P6/P7/P8）

### Phase 10C.4：Plumbing smoke

**目标：** 实现新 gate，default-off，验证：
- 所有 116 个现有测试通过
- `context_gate_enabled=False` 时行为与当前完全一致
- `context_gate_enabled=True` 时 gate 能正常触发（不崩溃，不 NaN）

### Phase 10C.5：2-seed pilot

**目标：** 用 2 seeds 跑 closed_loop vs divergent_warmup_replay，观察新 gate 是否产生 slow_l1 差异。

**成功标准：** `Δ(closed-divergent)_slow > 0`，且 amplification_ratio > 0。

### Phase 10C.6：4-seed validation

**目标：** 用 4 seeds 验证 10C.5 的结果是否跨 seed 稳定。

---

## 6. 当前决策

**下一步：Phase 10C.1 instrumentation。**

先给 gate 装传感器，再决定怎么换门锁。

理由：
- 我们知道 gate 看不见局部状态，但不知道哪种"眼睛"最可靠
- 10C.1 的 instrumentation 数据会直接告诉我们哪个候选方向（A/B/C）有信号
- 如果 tag-trace alignment 在 closed vs divergent 之间没有差异，方向 A 就不值得实现
- 先观察，再设计，避免实现一个同样 context-blind 的新 gate

**10C.1 的核心约束：只读，不改。** instrumentation 代码只能读取现有状态变量，不能修改任何 gate 逻辑或 transfer 逻辑。

---

## 7. 关联文档

| 文档 | 内容 |
|------|------|
| `docs/phase10A2B2_scheme_e_exhaustion_and_next_control_decision.md` | Scheme E 关闭，Route A 选择 |
| `docs/phase10A2C_divergent_warmup_replay_design.md` | Route A 设计 |
| `docs/phase10A2C_divergent_warmup_replay_notes.md` | Route A 结果 |
| `docs/phase10A2C_route_a_exhaustion_and_next_direction.md` | Route A 关闭，Route C 方向 |
| `docs/phase10C_state_context_sensitive_capture_planning.md` | 本文档 |
