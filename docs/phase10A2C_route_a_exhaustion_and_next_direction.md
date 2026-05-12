# Phase 10A.2C — Route A Exhaustion and Next Direction

> **定位：** 诊断性决策文档。不是 tuning。不是 Route B。
> **结论：** Route A 正式关闭。下一阶段：Route C — 重新设计 capture gate。

---

## 1. 当前证据链（完整）

| Phase | 扰动类型 | fast Δ | slow Δ | 结论 |
|-------|---------|--------|--------|------|
| 10A.2 | closed-loop + 9C | — | 0 | mirror 发现，clean negative |
| 10A.2B.1 | Scheme E ε=0.02 | 小 | 0 | hairline positive（fast only） |
| 10A.3 | 9C+9D ON, ε=0.02 | 小 | 0 | clean negative |
| 10A.2B.2 | ε ladder [0.005–0.05] | 0.001–0.010 | 0 | Scheme E 耗尽 |
| **10A.2C** | **divergent warmup 2000步** | **94–96** | **0** | **Route A 耗尽** |

从 ε=0.005 到 divergent warmup，fast-weight divergence 增加了约 4 个数量级（0.001 → 95）。slow Δ 始终为 0，amplification_ratio 始终为 0.0。

**这不是信号太弱的问题。这是 capture gate 的结构性问题。**

---

## 2. Route A 正式关闭

**Route A（divergent warmup replay）已诊断性耗尽。**

关闭依据：
- P6 确认 warmup state divergence 真实存在（act_div = 0.056–0.135）
- P7 确认 weight restore 精确（post-restore delta = 0.0）
- P8 确认 matched control 干净（slow_l1 = 0，captures = 0）
- 尽管如此，slow_l1 在 closed / exact / divergent 三 arm 间 bit-identical

Route A 的设计假设是：**不同的 warmup 历史会让 replay 阶段的 9D capture 产生不同结果。** 这个假设被证伪。

**禁止事项（不可回头）：**
- 不再增加 warmup_steps（更长的 warmup 不解决 gate 问题）
- 不再尝试 Option B（plasticity-ON warmup）——它增加 weight confound，不解决 gate 瓶颈
- 不再调整 ε（Scheme E 已关闭）
- 不进入 10A.4

---

## 3. 为什么 Route B 不是下一步

Route B（跨 seed yoked diagnostic）的逻辑是：用不同 seed（不同拓扑）跑同一 event log，观察 slow_l1 是否不同。

问题：不同 seed 意味着不同拓扑（连接权重、位置、时间常数全部不同）。如果 slow_l1 不同，无法区分"state context 起作用"和"不同拓扑对同一事件反应不同"。这是一个 trivially true 的结果，不能推进对 capture gate 的理解。

Route B 可以作为 sanity check，但不是下一个主要实验。

---

## 4. 瓶颈诊断：9D Capture Gate

### 4.1 当前 gate 结构

9D capture 的触发条件：

```
signal = min(1, energy / 0.3) × min(1, trace_mass / 0.03) ≥ 0.5
```

两个因子都是**全局聚合量**：
- `energy`：单个 unit 的能量（标量）
- `trace_mass`：全网络 trace 的 L1 总量（标量）

capture 决策基于这两个全局标量的乘积。

### 4.2 为什么 state context 看不见

state context divergence（act_div = 0.056–0.135）体现在：
- 各 unit 的 activation 分布不同
- 各 unit 的 energy 分布不同
- 各 connection 的 trace 分布不同

但 capture gate 把这些分布**压缩成两个标量**。压缩之后，分布的差异消失了。

具体来说：
- `trace_mass = Σ|trace_i|`：不同 trace 分布可以有相同的 L1 总量
- `energy`：单 unit 能量，不携带网络拓扑上的 context 信息

**结论：当前 capture gate 是 context-blind 的。它能感知"系统整体有多活跃"，但感知不到"活跃发生在哪里、以什么模式发生"。**

### 4.3 fast-weight divergence 为什么没有传播

10A.2C 中，divergent arm 的 fast_l1 与 exact arm 相差 94–96（L1 单位）。这是真实的 weight-level divergence。但 slow_l1 为 0。

原因：fast-weight divergence 体现在各 connection 的 weight 分布上，但 capture gate 不读 weight 分布。它只读 energy 和 trace_mass。fast-weight divergence 没有路径进入 capture 决策。

---

## 5. Route C：State-Context-Sensitive Capture Redesign

### 5.1 核心问题

**如何让 capture gate 感知 state context，而不只是全局活跃度？**

这不是调参问题（不是降低 capture_threshold 或缩短 refractory）。这是 gate 的信息输入问题。

### 5.2 方向框架

Route C 的目标是：设计一个 capture gate，使得：
1. 相同事件 + 不同 state context → 不同 capture 决策（或不同 slow_weight 沉积量）
2. 不引入写死的 if-else 或行为表
3. 保持涌现性：gate 规则简单，结果开放

可能的方向（待深入分析，不是最终决策）：

**方向 A：局部 trace 模式替代全局 trace_mass**
- 当前：`trace_mass = Σ|trace_i|`（全局标量）
- 候选：用 trace 向量的某种局部特征（如 top-k 活跃 connection 的 trace 集中度）
- 直觉：如果 trace 集中在特定 connection 子集，说明这次事件在特定 context 下发生

**方向 B：energy 分布替代单 unit energy**
- 当前：capture 由单个 unit 的 energy 触发
- 候选：capture 条件包含 energy 分布的某种 context 特征（如 energy 在 L/R 区域的不对称性）
- 直觉：同一事件在不同 energy 分布下，应该留下不同的 slow trace

**方向 C：trace × activation 的局部乘积**
- 当前：trace 和 activation 分开处理
- 候选：capture gate 读取 `trace_i × activation_i` 的局部模式
- 直觉：只有 trace 高且当前活跃的 connection 才参与 capture，这自然携带 state context

**方向 D：capture 量（而非 capture 决策）对 context 敏感**
- 当前：capture 是 binary（触发或不触发），触发后 slow_weight 按固定 rate 更新
- 候选：保持 binary capture，但 slow_weight 更新量由 state context 调制
- 直觉：同一事件触发 capture，但 context 不同时沉积的 slow_weight 量不同

### 5.3 设计约束

Route C 的任何设计必须满足：
- **不写死 context 定义**：不能硬编码"L 区域"或"R 区域"作为 context
- **不引入新的全局超参数**：不能靠调参来"让它工作"
- **可验证**：必须有对应的 hard protocol（类似 P6/P7/P8）来证明 context sensitivity 真实存在
- **不破坏 Phase 9D 的基本结构**：tag → capture → slow_weight 的三层结构保留

### 5.4 下一步

Route C 的第一步不是实现，而是**分析**：

1. 读 `aniva/life_core.py` 中 9D 的完整实现（tag 生成、capture 触发、slow_weight 更新）
2. 画出信息流：从 activation/trace/energy → tag → capture signal → slow_weight
3. 找到信息压缩发生的具体位置
4. 在那个位置设计 context-sensitive 的替代方案

---

## 6. 决策记录

| 决策 | 内容 |
|------|------|
| Route A 关闭 | divergent warmup replay 诊断性耗尽，不再重开 |
| Route B 跳过 | trivially true，不推进 gate 理解 |
| Route C 开启 | 下一阶段主线：state-context-sensitive capture redesign |
| 禁止 | 调 capture_threshold / refractory / slow_weight_rate 等参数 |
| 禁止 | 进入 10A.4 |
| 禁止 | 增加 warmup_steps |
| 禁止 | 数字生命 / 意识 / 人格声明 |

---

## 7. 关联文档

| 文档 | 内容 |
|------|------|
| `docs/phase10A2B2_scheme_e_exhaustion_and_next_control_decision.md` | Scheme E 关闭，Route A 选择 |
| `docs/phase10A2C_divergent_warmup_replay_design.md` | Route A 设计 |
| `docs/phase10A2C_divergent_warmup_replay_notes.md` | Route A 结果 |
| `docs/phase10A2C_route_a_exhaustion_and_next_direction.md` | 本文档 |
