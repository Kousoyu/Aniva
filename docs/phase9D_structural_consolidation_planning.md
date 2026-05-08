# Phase 9D — Structural Consolidation Planning

> **定位：** planning only. 不实现，不跑实验。
> Phase 9D 不是继续证明 9C-EPT 是否有效。9C 已经在 9C.3/9C.4 完成机制验证与 core integration smoke。
> Phase 9D 的目标是研究：9C 的 event-pair directional dW 如何进一步沉积为更长期、更稳定、更结构化的历史痕迹。

---

## 1. 背景：为什么需要 9D

### 9C 已完成的工作

- **9C.3** — four-seed formal validation positive（42, 77, 123, 999）
  - acc_dW_OS +1.920–1.949, contam ≤ 0.021, gate_w=1.000, gate_c 0.023–0.042
  - 16/16 schedule_ok, 0 NaN, 对照组无稳定假阳性
- **9C.4** — full integration smoke passed
  - 300-unit core path 复现 9C.3 diagnostic 行为
  - acc_dW_OS = +1.948（9C.3: +1.949，偏差 < 0.05%）
  - trace decay unit mismatch 修复于 `7b10e4b`
  - Core path: `Environment.phi_vector → LifeCore.apply_event_pair_phi → plasticity_event_pair.apply_event_pair_update` 在全尺寸下成立
  - Hebbian 共存未淹没 event-pair 信号

### 9C 验证了什么，没验证什么

| 已验证 | 未验证 |
|--------|--------|
| 事件对顺序产生方向性 dW（dW ledger 级别） | 该方向性信号能否长期保留 |
| soft_trace_gate 有效压缩跨对污染 | 重复事件对历史是否累积 |
| 4/4 seeds 一致 | 长期结构沉积是否抵抗稳态擦除 |
| Core path 与 diagnostic 行为一致 | 多 episode 下的 structural memory |

### 核心 gap

9C 产生的是 **event-pair directional dW signal**，发生在事件到达时刻。如果所有 dW 都立即进入普通权重池，面临三个问题：

1. **短促性：** 单次事件对的 dW 量级很小（target=1e-4），可能被连续 Hebbian 更新稀释或逆转
2. **噪声敏感性：** 随机活动波动产生的 dW 与事件对 dW 不可区分，无长期筛选机制
3. **稳态擦除：** homeostasis 和后续活动会把权重推回 target 范围，历史痕迹被洗掉

**9C answered: can world event order create directional plasticity?**

**9D asks: can repeated event-order history become long-term structural sediment?**

---

## 2. 核心问题

1. 9C 产生 event-pair directional dW signal
2. 单次 dW 太小、太短、太容易被后续活动覆盖
3. 需要一层 **structural consolidation**：反复出现、有内部一致性的事件对塑性，逐步变成更稳定的长期结构改变
4. Consolidation signal 必须从系统内部状态来，不能是外部标签或 reward

**一句话：** 9C 让 Aniva 能"听见事件的先后关系"；9D 要研究哪些先后关系会变成骨头里的年轮。

---

## 3. 候选机制路线

### 3.1 STC-like synaptic tagging and capture（推荐主路线）

借鉴生物学 synaptic tagging and capture（STC）框架：

```
9C event-pair dW → 生成 synaptic tag（局部、衰减、O(N_connections)）
tag 随时间衰减（τ_tag）
consolidation/capture signal 触发时：
  tagged synapses 的 dW 被写入 slow structural weight
  未被 tagged 的 synapses 不写入
```

**关键设计约束：**
- Tag 产生于 event-pair update，不需要额外标签
- Tag 衰减是内在的（指数衰减或漏积分）
- Capture signal 不能是 reward 或外部标签
- Capture signal 必须从系统内部状态来（见 3.4）

**fast / slow 权重分离边界（9D.1 review 后明确）：**

```
_weight_cache       = fast weight   — Hebbian + event-pair fast plasticity 写入
_slow_weight_cache  = slow overlay  — 只由 consolidation 写入，read-only for others
_tag_cache          = synaptic tag  — 由 event-pair dW 产生，每步衰减

effective_weight = _weight_cache + _slow_weight_cache  (clamp to [-1, 1])
```

- `compute_synaptic_input_vectorized` 使用 `effective_weight`（当 consolidation enabled）
- Hebbian plasticity 继续读写 `_weight_cache`（fast only），不受 slow_weight 影响
- event-pair fast plasticity（9C）继续写入 `_weight_cache`（fast only）
- Homeostasis 继续作用于 `_weight_cache`（fast only）
- `_slow_weight_cache` 不参与现有 homeostasis → **必须有独立 clamp**（见 §5 slow_weight_max）
- `_sync_connections_from_cache` / `_sync_weight_cache` 只走 `_weight_cache`

**设计原理：** slow_weight 是 read-only overlay。活动被 slow structure 偏置 → Hebbian 从"被 history 塑造的活动"中学习 → 形成 fast↔slow 间的间接耦合，但不产生循环写入依赖。

**优点：**
- 直接承接 9C dW 输出，不破坏现有路径
- 生物学类比清晰，易于分阶段验证
- Tag 状态是 O(N_connections)，与现有 _weight_cache 对等

**风险：**
- Capture signal 设计不当会退化为标签泄露
- Tag 衰减时间常数需要仔细校准：
  - τ_tag 太小 → capture 前 tag 已完全衰减 → 无 consolidation
  - τ_tag 太大 → 前一 episode 的 tag 残留被错误固化到后一 episode → 跨 episode 污染
  - 初始值 τ_tag=5000 ≈ rest_window → inter-episode 衰减约 exp(-5000/5000) ≈ 37%
  - 9D.1 必须测试 tag decay 时间线，验证 tag 在 inter-episode 间隔后降至可忽略水平

### 3.2 Multi-timescale weights（备选 / 可与 STC 结合）

```
fast_weight： 9C 短时 event-pair 塑性 + Hebbian 日常更新
slow_weight： 长期结构沉积，变化速率远低于 fast_weight
transfer： fast → slow 受稳定性、重复性、能量、局部一致性调控
effective_weight = α * fast_weight + β * slow_weight
```

**优点：**
- 天然的时间尺度分离
- slow_weight 变化慢，适合做长期历史痕迹
- 可观测性强（fast vs slow 差异本身就是指标）

**缺点：**
- 引入第二个权重矩阵，内存翻倍
- 需要设计 transfer rule，容易过度设计
- 与现有 homeostasis 的交互复杂

### 3.3 Stability-gated consolidation（补充 / 可叠加）

```
如果同方向 event-pair dW 在多个 episode 中重复出现 → 进入 slow structure
如果方向反复冲突 → 不固化或只保留弱痕迹
stability = f(consistency, repetition_count, time_span)
```

**优点：**
- 直接解决"单次噪声 vs 重复信号"问题
- 不需要额外的 capture signal 设计

**缺点：**
- 需要 episode 边界检测（可能引入标签）
- 方向一致性判断本身需要累积，可能 chicken-and-egg

### 3.4 Capture signal 来源（核心设计问题）

Capture signal 必须来自底层动力学，候选来源：

| 来源 | 机制 | 优点 | 风险 |
|------|------|------|------|
| 全局能量盈余 | 能量高于阈值 → consolidation ON | 简单，已有 energy 系统 | 可能与事件对时机无关 |
| 局部活动一致性 | 前/后突触活动相关 → 局部 capture | 突触特异性强 | 可能与 Hebbian 信号混淆 |
| 网络状态稳定性 | 全局波动低于阈值 → consolidation ON | 反映系统"冷静"状态 | 需要定义稳定性度量 |
| Trace 残留强度 | 9C trace 残留 > 阈值 → 增强 tag | 直接承接 9C 机制 | trace 本身是短时的 |
| Multi-episode 重复 | 同一对连接反复收到同方向 dW | 最接近"历史沉积"概念 | 需要累积计数器 |

**推荐 9D.1 先用全局能量盈余 + trace 残留强度的简单组合**，验证 plumbing 后再在 9D.2/9D.3 中细化。

---

## 4. 反作弊边界

以下红线不可逾越：

- **不允许** reward / goal / agent / emotion / personality / LLM / language interface 参与 consolidation
- **不允许** `if arm == "L_then_R"` 这类标签分支出现在 consolidation 路径中
- **不允许** 把"记忆"写成 `memory["last_event"]` 或类似字典查询
- **长期记忆必须体现为结构变量变化**（权重、tag 状态、slow_weight），不是字段记录
- **Consolidation signal 必须来自底层动力学**（能量、活动、trace、稳定性），不是实验标签
- **不允许** 用 episode index、pair_index、event 计数做 consolidation 判断
- **默认关闭**：所有 9D 新字段 default off，旧行为不变

---

## 5. 分阶段路线

### 9D.0 — planning only（本次）

- 本文档
- 方向判断、机制路线、失败标准
- 不写代码、不跑实验

### 9D.1 — minimal tag-state skeleton, default off

**目标：** plumbing check，不是科学结论。

**新增 config 字段（全部 default off / neutral）：**

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `consolidation_enabled: bool` | `False` | 总开关，False 时不创建任何 9D 数据结构 |
| `consolidation_tag_tau: float` | `5000.0` | tag 衰减时间常数（steps），应 < inter-episode 间隔 |
| `consolidation_capture_threshold: float` | `0.5` | capture signal 阈值（0–1），超过触发 consolidation |
| `consolidation_slow_weight_max: float` | `0.1` | per-connection slow_weight 绝对值上限，防止 runaway |
| `consolidation_slow_weight_rate: float` | `0.1` | capture 时 tag → slow_weight 的转换比率 |
| `consolidation_capture_refractory_steps: int` | `500` | capture 触发后 refractory 步数，防止同一事件对内重复固化 |

**slow_weight_max 设计理由（review 识别风险）：**
- Homeostasis 继续只作用于 fast_weight（`_weight_cache`）
- slow_weight（`_slow_weight_cache`）游离于 homeostasis 之外
- 若无独立 clamp → slow_weight 可无限累积 → runaway
- `slow_weight_max = 0.10` 意味着慢结构最多偏置 10% 的总权重范围
- fast_weight 仍有 ~[-0.9, 0.9] 的动态范围给 Hebbian
- 可在 9D.2 根据数据调整

**capture refractory 设计理由（review 识别风险）：**
- 如果没有 refractory，capture signal 持续高位时每步都触发 consolidation
- 导致同一事件对内 slow_weight 反复累积，失去"沉积"的稀疏性
- refractory = 500 steps（≈ 一次事件对的持续时间 scale）
- 触发 capture 后进入 refractory，refractory 期间不检查 capture signal

**新增数据结构：**
- `_tag_cache: np.ndarray | None`（O(N_connections)，默认 None）
- `_slow_weight_cache: np.ndarray | None`（O(N_connections)，默认 None）
- `_capture_refractory_remaining: int`（步计数，默认 0）

**9C → 9D 衔接：**
- 在 `apply_event_pair_update` 中：dW → tag（不直接改 slow_weight）
  - tag += |dW|（取绝对值，tag 是无符号的"此处发生过塑性"标记）
  - 或者 tag += dW（有符号，tag 保留方向信息）—— 9D.1 先用无符号版本
- 每步 `_consolidation_step()`：
  1. tag decay：`tag *= exp(-1.0 / τ_tag)`
  2. refractory countdown：`refractory -= 1`（如 > 0 则跳过 capture）
  3. capture 检测：`capture_signal > threshold` 且 refractory ≤ 0
  4. capture 触发：`slow_weight += slow_weight_rate * tag`，clamp slow_weight to `[-slow_max, +slow_max]`，reset refractory
- 突触计算：`effective = _weight_cache + _slow_weight_cache`，clamp to `[-1, 1]`

**Capture signal 初始公式：**
```
capture_signal = min(1.0, mean_energy / energy_ref) * min(1.0, trace_mass / trace_ref)
```
其中 `energy_ref` 和 `trace_ref` 为可配参数（9D.1 用硬编码初始值，后续阶段暴露为 config）。

**Capture debug ledger（仅当 ledger_enabled）：**
每次 capture 触发时记录：
- `capture_signal_value` — 触发时的 signal 值
- `mean_energy` — 全局平均能量
- `trace_mass_at_capture` — 触发时的 trace_mass
- `tag_mass` — tag 绝对值总和
- `slow_weight_delta_l1` — 本次 slow_weight 变化的 L1 范数
- `refractory_remaining` — 触发前的 refractory 剩余步数
- `n_tagged_connections` — tag > 0 的连接数

**有效权重计算（仅在 consolidation enabled 时）：**
```python
if cfg.consolidation_enabled:
    effective = self._weight_cache + self._slow_weight_cache
    np.clip(effective, -1.0, 1.0, out=effective)
    synaptic_weights = effective
else:
    synaptic_weights = self._weight_cache  # 无 overhead
```

**验证内容：**
- tag 能产生（来自 9C dW）
- tag 会衰减（τ_tag 正确，decay 时间线可测）
- repeated 9C dW 能积累 tag（多次 event-pair update 后 tag 幅值增长）
- capture gate 能把 tag 写入 slow_weight
- slow_weight 被 `slow_weight_max` clamp，不会无限增长
- refractory 防止同一事件对内重复 capture
- 默认关闭时所有旧测试通过（244/244+）

**9D.1 测试要求（新增）：**

| 测试 | 验证内容 |
|------|----------|
| `test_consolidation_disabled_no_effect` | consolidation_enabled=False 时 synaptic input 与旧行为完全一致 |
| `test_slow_weight_zero_effective_equals_fast` | slow_weight 初始为 0 时 effective == fast |
| `test_tag_produced_from_event_pair_dw` | apply_event_pair_update 后 tag 非零 |
| `test_tag_decays_with_correct_tau` | tag 按 exp(-1.0/τ_tag) 衰减 |
| `test_tag_accumulates_across_updates` | 两次连续 update 后 tag > 单次 |
| `test_capture_writes_tag_to_slow_weight` | capture signal 超阈值时 slow_weight 改变 |
| `test_slow_weight_clamped_by_max` | slow_weight 不超过 slow_weight_max |
| `test_refractory_prevents_repeated_capture` | refractory 期间不触发 capture |
| `test_capture_uses_no_arm_labels` | capture signal 公式不含 arm/L/R/event_index |
| `test_no_nan_in_consolidation` | tag / slow_weight / effective 全程无 NaN |

### 9D.2 — single-seed consolidation smoke

- seed=42, 300 units
- 固定参数，测试场景：
  - repeated same-order（L_then_R × N episodes）
  - alternating order（L_then_R → R_then_L → L_then_R ...）
  - single-episode baseline（只一对）
- 预期：
  - repeated same-order → slow structure 最强
  - alternating → slow structure 弱或抵消
  - single-episode → slow structure 最弱

### 9D.3 — two-seed pilot

- seeds 42, 999
- 验证 cross-seed stability
- 基本参数扫描（tag_tau, capture_threshold）

### 9D.4 — four-seed validation

- seeds 42, 77, 123, 999
- 正式验证 consolidation 机制
- 不预注册具体成功指标（等 9D.1–9D.3 的数据再定）

---

## 6. 成功标准（9D 整体，待 9D.1 后细化）

### Plumbing 级（9D.1）

- [ ] tag 产生且量级合理（非零、非饱和）
- [ ] tag 衰减曲率匹配 τ_tag
- [ ] capture gate 有可测的动态范围（不全 0、不全 1）
- [ ] slow_weight 变化与 fast_weight 可区分
- [ ] 默认关闭时所有旧测试通过（244/244+）

### 行为级（9D.2–9D.4）

- [ ] Repeated same-order event-pair produces stronger slow structure than one-off
- [ ] Opposite-order history produces opposite slow directional tendency
- [ ] Simultaneous / separated controls do not produce same stable consolidation
- [ ] 0 NaN / 0 explosion / 0 runaway saturation
- [ ] Slow structure changes are smaller and more stable than fast dW
- [ ] Cross-seed consistency

---

## 7. 失败标准

以下任一情况视为 9D 路线需要重新评估：

- [ ] All arms consolidate equally（global shift，无方向特异性）
- [ ] Consolidation only follows initial topology bias（先天连接 > 历史事件）
- [ ] Slow weights saturate（全部到 ±1.0，无动态范围）
- [ ] Effect disappears across seeds（单 seed fluke）
- [ ] Capture signal secretly encodes labels（标签泄露）
- [ ] Homeostasis 完全抵消 consolidation（无法共存）
- [ ] 事后调参才通过（预注册参数应 work）

失败时不自动 pivot。先诊断是 plumbing bug、参数错配、还是 consolidation 路线本身的问题。

---

## 8. 与现有系统的交互

| 系统 | 交互方式 | 注意事项 |
|------|----------|----------|
| 9C event-pair plasticity | dW → tag 产生 | tag 在 apply_event_pair_update 中创建 |
| Hebbian plasticity | 继续在 fast weight（`_weight_cache`）上运行 | 不受 slow_weight 直接影响；活动被 slow 偏置后间接影响 Hebbian |
| Homeostasis | 只作用于 fast_weight（`_weight_cache`） | slow_weight 不参与现有 homeostasis，由 `slow_weight_max` 独立 clamp |
| Energy | 候选 capture signal 来源 | 能量盈余 → consolidation ON |
| Trace (9C) | 候选 capture signal 来源 | trace 残留大 → consolidation window 更可能打开 |
| Synaptic computation | 使用 `effective = fast + slow`（consolidation enabled 时） | 当 disabled 时直接用 fast，零 overhead |
| Observer | 新增 slow_weight / tag / capture 指标 | DI_slow, OS_slow, tag_coverage, capture_count |

---

## 9. 核心表述

```
Phase 9C answered:
  Can world event order create directional plasticity?
  → Yes. 9C-EPT + soft_trace_gate produces strong, seed-consistent directional dW.

Phase 9D asks:
  Can repeated event-order history become long-term structural sediment?
  → Can the dW ledger become bone?
```

**9C 让 Aniva 能"听见事件的先后关系"。**

**9D 要研究的是：哪些先后关系会变成骨头里的年轮。**

---

## 10. 文件规划

```
docs/phase9D_structural_consolidation_planning.md    ← 本文档
aniva/config.py                                       ← 9D config fields (9D.1)
aniva/core/plasticity_consolidation.py                ← consolidation 模块 (9D.1)
tests/test_plasticity_consolidation.py                ← 测试 (9D.1)
aniva/experiments/exp9D1_consolidation_smoke.py       ← smoke script (9D.2)
docs/phase9D1_consolidation_skeleton_notes.md         ← skeleton notes (9D.1)
docs/phase9D2_consolidation_smoke_notes.md            ← smoke notes (9D.2)
```

---

## 11. 纪律

- 先写 design → commit → 再实现
- 不调参
- 不改 9C 机制公式
- 不在 consolidation 路径加 arm/L/R label
- 不自动 9E
- 9D.1 只是 plumbing skeleton，不宣称科学结论
- 失败如实记录，不事后解释为成功
- Consolidation signal 必须来自底层动力学，不能是实验标签
