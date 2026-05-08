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

**优点：**
- 直接承接 9C dW 输出，不破坏现有路径
- 生物学类比清晰，易于分阶段验证
- Tag 状态是 O(N_connections)，与现有 _weight_cache 对等

**风险：**
- Capture signal 设计不当会退化为标签泄露
- Tag 衰减时间常数需要仔细校准

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

- 新增 config 字段（全部 default off）：
  - `consolidation_enabled: bool = False`
  - `consolidation_tag_tau: float = 5000.0`（tag 衰减时间常数，steps）
  - `consolidation_capture_threshold: float = 0.5`（capture 触发阈值）
  - `consolidation_slow_weight_rate: float = 0.1`（slow weight 更新速率）
- 新增 `_tag_cache: np.ndarray | None`（O(N_connections)，默认 None）
- 在 `apply_event_pair_update` 中：dW → tag（不直接改 slow weight）
- 新增 `_consolidation_step()`：
  - tag decay（每步）
  - capture 检测（基于全局能量 / trace 残留）
  - capture 触发时：tag → slow_weight
- 新增 `_slow_weight_cache: np.ndarray | None`（O(N_connections)，默认 None）
- 有效权重 = `_weight_cache + _slow_weight_cache`（钳制到 [-1, 1]）
- 测试：tag 产生/衰减、capture gate、默认关闭回归、无 NaN

**验证内容：**
- tag 能产生（来自 9C dW）
- tag 会衰减（τ_tag 正确）
- repeated 9C dW 能积累 tag（多次事件对后 tag 幅值增长）
- capture gate 能把 tag 写入 slow_weight
- 默认关闭时所有旧测试通过

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
| Hebbian plasticity | 继续在 fast weight 上运行 | 不与 tag/slow_weight 直接交互 |
| Homeostasis | 作用在 effective_weight 上 | 需要决定 homo 是否也作用于 slow_weight |
| Energy | 候选 capture signal 来源 | 能量盈余 → consolidation ON |
| Trace (9C) | 候选 tag 增强信号 | trace 残留大 → tag 更强 |
| Observer | 新增 slow_weight / tag 指标 | DI_slow, OS_slow, tag_coverage 等 |

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
