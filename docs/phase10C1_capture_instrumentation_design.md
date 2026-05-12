# Phase 10C.1 — Capture Gate Instrumentation Design

> **定位：** design document only。不实现，不跑实验，不改 life_core.py。
> **目标：** 在不改变任何 capture 决策的前提下，给 9D consolidation ledger 新增 context-aware 只读指标。

---

## 1. 背景

### 1.1 证据链

| Phase | 扰动 | fast Δ | slow Δ | 结论 |
|-------|------|--------|--------|------|
| 10A.2 | closed-loop + 9C | — | 0 | exact ≡ closed，mirror 确认 |
| 10A.2B.1 | Scheme E ε=0.02 | hairline | 0 | fast divergence exists |
| 10A.3 | 9C+9D ON, ε=0.02 | hairline | 0 | clean negative |
| 10A.2B.2 | ε ladder [0.005–0.05] | 0.001–0.010 | 0 | Scheme E 耗尽 |
| 10A.2C | divergent warmup 2000步 | 94–96 | 0 | Route A 耗尽 |
| 10C.0 | planning | — | — | capture gate 是瓶颈 |

### 1.2 当前 9D 信息流（压缩点）

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

### 1.3 10C.1 的定位

10C.1 不改变上述任何逻辑。它只在 `if signal >= threshold` 触发时，额外计算并记录若干 context-aware 指标，写入 `_consolidation_ledger`。

**10C.1 = 给门装传感器，不换锁。**

---

## 2. 新增只读指标

以下所有指标在每次 capture 触发时计算一次，写入 ledger entry。不影响 gate 决策，不影响 slow_weight 写入，不影响 tag_cache 或 event_trace。

### 2.1 `tag_trace_alignment`

**目的：** 测量 tag 分布（哪些连接被 9C 标记过）与当前 trace 模式（这次事件影响了哪些 unit）的对齐程度。

**计算：**

```python
# event_trace: (n_units,) — 9C event-pair trace per unit
# tag_cache:   (n_conn,) — accumulated |dW| per connection
# source_indices: (n_conn,) — source unit index for each connection
# target_indices: (n_conn,) — target unit index for each connection

projected_trace = np.abs(event_trace[source_indices]) * np.abs(event_trace[target_indices])
# projected_trace: (n_conn,) — trace product at each connection's endpoints

tag_norm = np.linalg.norm(tag_cache)
proj_norm = np.linalg.norm(projected_trace)

if tag_norm < 1e-12 or proj_norm < 1e-12:
    tag_trace_alignment = 0.0
else:
    tag_trace_alignment = float(np.dot(tag_cache, projected_trace) / (tag_norm * proj_norm))
```

**范围：** `[-1, 1]`，但因为 `tag_cache ≥ 0` 且 `projected_trace ≥ 0`，实际范围 `[0, 1]`。

**解读：**
- 接近 1：tag 集中在当前 trace 活跃的连接上 → 这次事件发生在"记忆热点"附近
- 接近 0：tag 和 trace 模式正交 → 这次事件与历史 tag 无关

**为什么这个指标有意义：** 如果 closed_loop 和 divergent_warmup_replay 在 capture 时刻的 `tag_trace_alignment` 有稳定差异，说明 state context 确实影响了 tag-trace 的局部关系，只是当前 gate 看不见。

---

### 2.2 `tag_weighted_energy`

**目的：** 测量 tag 所在连接的局部能量。如果 tag 集中在高能量区域，说明这次 capture 发生在"活跃热点"。

**计算：**

```python
# energies: (n_units,) — per-unit energy
# tag_cache: (n_conn,) — per-connection

local_energy = 0.5 * (energies[source_indices] + energies[target_indices])
# local_energy: (n_conn,) — mean energy at each connection's endpoints

tag_mass = np.sum(tag_cache)
if tag_mass < 1e-12:
    tag_weighted_energy = 0.0
else:
    tag_weighted_energy = float(np.dot(tag_cache, local_energy) / tag_mass)
```

**范围：** `[0, max_energy]`，通常 `[0, 1]`。

**对比量：** 当前 gate 用的 `mean_energy = np.mean(energies)`。`tag_weighted_energy` 是 tag 加权版本。

**解读：**
- `tag_weighted_energy >> mean_energy`：tag 集中在高能量区域
- `tag_weighted_energy ≈ mean_energy`：tag 均匀分布，局部加权退化为全局均值

---

### 2.3 `tag_concentration`

**目的：** 测量 tag 分布的集中程度。tag 越集中，说明 9C 的历史标记越局部化。

**计算（使用 effective support ratio）：**

```python
tag_mass = np.sum(tag_cache)
if tag_mass < 1e-12:
    tag_concentration = 0.0
else:
    tag_probs = tag_cache / tag_mass
    # Herfindahl-Hirschman Index (HHI): sum of squared shares
    tag_concentration = float(np.sum(tag_probs ** 2))
    # HHI = 1/n_conn when uniform, = 1.0 when all mass on one connection
```

**范围：** `[1/n_conn, 1.0]`。

**归一化版本（可选）：**

```python
n_conn = len(tag_cache)
tag_concentration_normalized = (tag_concentration - 1.0/n_conn) / (1.0 - 1.0/n_conn)
# 0 = uniform, 1 = all mass on one connection
```

**解读：**
- 高集中度：tag 集中在少数连接上，这些连接是"记忆热点"
- 低集中度：tag 均匀分布，没有明显的局部结构

---

### 2.4 `trace_concentration`

**目的：** 测量 event_trace 的集中程度。trace 越集中，说明这次事件影响的 unit 越局部化。

**计算：**

```python
trace_abs = np.abs(event_trace)
trace_mass_local = np.sum(trace_abs)
if trace_mass_local < 1e-12:
    trace_concentration = 0.0
else:
    trace_probs = trace_abs / trace_mass_local
    trace_concentration = float(np.sum(trace_probs ** 2))
```

**范围：** `[1/n_units, 1.0]`，同 HHI。

**解读：**
- 高集中度：这次事件的 trace 集中在少数 unit 上
- 低集中度：trace 弥散，事件影响了大部分 unit

---

### 2.5 Region-Level Summaries（optional diagnostics）

**目的：** 如果 unit 有 L/R/M 区域标记（来自 `_positions`），记录各区域的 tag mass 和 trace mass。

**计算（仅当 region 信息可用时）：**

```python
# positions: (n_units, 2) — (x, y) coordinates
# L region: x < -0.3, R region: x > 0.3, M: otherwise

x_positions = positions[:, 0]
l_mask = x_positions < -0.3   # (n_units,) bool
r_mask = x_positions > 0.3    # (n_units,) bool
m_mask = ~l_mask & ~r_mask

# Trace mass by region
trace_abs = np.abs(event_trace)
trace_L = float(np.sum(trace_abs[l_mask]))
trace_R = float(np.sum(trace_abs[r_mask]))
trace_M = float(np.sum(trace_abs[m_mask]))

# Tag mass by region (connection belongs to region if BOTH src and tgt in region)
conn_in_L = l_mask[source_indices] & l_mask[target_indices]
conn_in_R = r_mask[source_indices] & r_mask[target_indices]
tag_L = float(np.sum(tag_cache[conn_in_L]))
tag_R = float(np.sum(tag_cache[conn_in_R]))
```

**注意：** 这些 region summaries 是纯 diagnostics，不进入任何 gate 逻辑。它们依赖 `_positions` 的空间结构，而 `_positions` 是 seed-dependent 的。

---

## 3. Ledger Entry 结构（新增字段）

当前 ledger entry（`_consolidation_ledger` 中每个 dict）包含：

```python
{
    "step": int,
    "signal": float,
    "mean_energy": float,
    "trace_mass": float,
    "tag_mass": float,
    "n_tagged": int,
    "delta_l1": float,
}
```

10C.1 新增字段：

```python
{
    # ... 现有字段 ...

    # 10C.1 instrumentation (read-only, no effect on gate)
    "tag_trace_alignment": float,      # cosine similarity of tag_cache and projected_trace
    "tag_weighted_energy": float,      # tag-weighted mean local energy
    "tag_concentration": float,        # HHI of tag distribution
    "trace_concentration": float,      # HHI of event_trace distribution

    # optional region diagnostics (only if positions available)
    "trace_L": float,
    "trace_R": float,
    "trace_M": float,
    "tag_L": float,
    "tag_R": float,
}
```

---

## 4. Anti-Cheat 约束

以下约束必须在实现时显式验证：

| 约束 | 验证方式 |
|------|---------|
| instrumentation 不读 arm_label | 代码中无 arm_label 参数 |
| instrumentation 不读 future | 只读当前步状态变量 |
| instrumentation 不改变 capture 决策 | `signal` 计算和 `threshold` 比较在 instrumentation 之后，不依赖新字段 |
| instrumentation 不改变 slow_weight | `apply_capture` 调用不变 |
| instrumentation 不改变 tag_cache | 新字段计算不修改 `tag_cache` |
| instrumentation 不改变 event_trace | 新字段计算不修改 `event_trace` |
| 除以零保护 | tag_mass=0、trace_mass=0、norm=0 时返回 0.0 |
| 数值稳定 | 所有新字段有明确范围，无 NaN 路径 |

---

## 5. 测试要求

### 5.1 回归测试

- 所有现有 116 个测试必须继续通过
- `consolidation_enabled=True` + `instrumentation_enabled=False`（或不存在该 flag）时，行为与当前 bit-identical
- `consolidation_enabled=True` + `instrumentation_enabled=True` 时，`slow_weight_cache` 数值与 `instrumentation_enabled=False` 时 bit-identical

### 5.2 新增测试

- ledger entry 包含所有新字段
- `tag_trace_alignment` 在 `[0, 1]` 范围内
- `tag_weighted_energy` 在 `[0, max_energy]` 范围内
- `tag_concentration` 在 `[1/n_conn, 1.0]` 范围内
- `trace_concentration` 在 `[1/n_units, 1.0]` 范围内
- tag_mass=0 时所有新字段为 0.0，无 NaN
- trace_mass=0 时所有新字段为 0.0，无 NaN

---

## 6. 实现位置

### 6.1 `plasticity_consolidation.py`

新增函数 `compute_capture_diagnostics`：

```python
def compute_capture_diagnostics(
    tag_cache: np.ndarray,          # (n_conn,)
    event_trace: np.ndarray,        # (n_units,)
    energies: np.ndarray,           # (n_units,)
    source_indices: np.ndarray,     # (n_conn,) int
    target_indices: np.ndarray,     # (n_conn,) int
    positions: np.ndarray = None,   # (n_units, 2) optional
) -> dict:
    """Compute read-only context-aware diagnostics at capture time.
    Does not modify any input array. Does not affect gate or transfer."""
    ...
```

### 6.2 `life_core.py`

在 `_consolidation_step` 的 `if signal >= threshold:` 分支里，`apply_capture` 之后，调用 `compute_capture_diagnostics` 并将结果 merge 进 ledger entry。

```python
if signal >= cfg.consolidation_capture_threshold:
    delta_l1 = apply_capture(...)
    self._capture_refractory_remaining = ...
    if cfg.consolidation_ledger_enabled:
        diag = compute_capture_diagnostics(
            self._tag_cache,
            self._event_trace,
            self._energies,
            self._source_indices,
            self._target_indices,
            self._positions if cfg.consolidation_diagnostics_enabled else None,
        )
        self._consolidation_ledger.append({
            # existing fields
            "step": self.step_count,
            "signal": signal,
            ...
            # new fields
            **diag,
        })
```

### 6.3 `config.py`

新增一个 flag：

```python
consolidation_diagnostics_enabled: bool = False
```

`consolidation_diagnostics_enabled=True` 时，`compute_capture_diagnostics` 计算并记录所有新字段（包括 region summaries）。`False` 时，ledger entry 不包含新字段（保持当前行为）。

`consolidation_ledger_enabled` 保持不变，控制是否记录 ledger。

---

## 7. 10C.2 分析目标

10C.1 实现完成后，用以下实验结构收集数据：

- 复用 10A.2C 的 4-arm 结构（closed_loop, exact_replay, divergent_warmup_replay, matched_warmup_control）
- `consolidation_diagnostics_enabled=True`
- 2 seeds（42, 77）

分析问题：

1. **`tag_trace_alignment`** 在 closed vs divergent 两个 arm 的 capture 事件之间是否有稳定差异？
2. **`tag_weighted_energy`** 是否比 `mean_energy` 更能区分两个 arm？
3. **`tag_concentration`** 在两个 arm 之间是否不同？（如果 divergent warmup 让 tag 更集中，说明 state context 影响了 9C 的标记模式）
4. **`trace_concentration`** 是否在两个 arm 之间不同？

如果所有四个指标在两个 arm 之间都没有差异，说明 state context 的影响在 capture 时刻已经完全消失，需要在更早的阶段（如 9C 的 trace 更新）寻找 context 信号。

---

## 8. 路线总结

| Phase | 内容 | 状态 |
|-------|------|------|
| 10C.0 | Planning | ✅ 完成 |
| **10C.1** | **Instrumentation design** | **← 当前（本文档）** |
| 10C.1 impl | 实现 `compute_capture_diagnostics`，新增 config flag | 待做 |
| 10C.1 smoke | plumbing smoke，验证回归测试通过 | 待做 |
| 10C.2 | Offline analysis：用 10A.2C 结构收集 diagnostics 数据 | 待做 |
| 10C.3 | 基于 10C.2 结果，选择候选 gate 设计 | 待做 |
| 10C.4 | 实现候选 gate，default-off | 待做 |
| 10C.5 | 2-seed pilot | 待做 |
| 10C.6 | 4-seed validation | 待做 |

---

## 9. 关联文档

| 文档 | 内容 |
|------|------|
| `docs/phase10A2C_route_a_exhaustion_and_next_direction.md` | Route A 关闭 |
| `docs/phase10C_state_context_sensitive_capture_planning.md` | Route C 总体规划 |
| `docs/phase10C1_capture_instrumentation_design.md` | 本文档 |
