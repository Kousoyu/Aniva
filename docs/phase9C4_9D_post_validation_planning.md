# Phase 9C.4 / 9D — Post-Validation Planning

> **定位：** 路线规划，不实现，不跑实验。
> Phase 9C.3 已完成 formal validation positive（commit `023ef4a`）。
> 9C-EPT + soft_trace_gate + washout 在 4 seeds 上通过预注册成功标准。

---

## 1. 当前状态

### 已验证的

- 9C-EPT 核心机制在 dW ledger 层面完成 4-seed formal validation
- event-pair trace × pulse-vector 更新 + soft_trace_gate + washout 在锁定的参数下稳产低污染方向性 dW

### 尚未验证的

- 机制在不同 gap / tau / num_pairs 下的鲁棒性
- 与现有 Hebbian / energy / homeostasis 的共存行为
- final_DI 仍被稳态遮盖（这是机制分层问题，不是 bug）

### 架构上的距离

- 当前 9C-EPT 实现全部在诊断实验脚本（`exp9C1C_trace_gated_update.py`）中
- 不在 `LifeCore`、不在 `apply_plasticity`、不在 `AnivaConfig`
- trace、phi、gate、update 都是实验脚本自己管理的 numpy 数组，没有进入核心管线

---

## 2. Phase 9C.4 — Core Integration Design

**目标：** 把 soft_trace_gate 从诊断脚本迁入核心架构，成为一等 plasticity 路径。

### 2.1 架构问题清单

| # | 问题 | 当前状态 | 集成方向 |
|---|------|----------|----------|
| 1 | trace 属于谁？ | 实验脚本手动管理 | LifeCore 应维护一个 O(N) event-pair trace 数组 |
| 2 | phi 怎么来？ | 实验脚本硬造 L/R stimulus phi | Environment 层应生成 world-event 的 spatial vector |
| 3 | update 何时触发？ | 实验脚本在 schedule 的脉冲步触发 | LifeCore 应在环境事件到达时触发 event-pair update |
| 4 | soft_trace_gate 与 Hebbian 如何共存？ | 现在代码里完全没有共存逻辑 | 两种机制应是叠加关系，不是互斥 |
| 5 | dW ledger 是永久的还是 debug-only？ | 实验内置了 ledger 打印 | 应该是 debug instrumentation，不开时不计算 |
| 6 | 参数如何管理？ | 硬编在实验脚本 CLI 里 | 应进入 AnivaConfig |
| 7 | final weight 与 dW ledger 的指标分层 | 当前 DI 只看 final weight，不反映 dW 方向 | 保留 dW ledger 作为主要机制级 readout |

### 2.2 Trace 的归属

**建议：LifeCore 维护一个 O(N) event-pair trace 数组。**

理由：
- trace 是全局状态（所有单元共享一个时间衰减的"最近事件印记"），不是 per-connection
- 它和 `_activity_traces` / `_onset_traces` 性质相同——都是单元级的时间信号
- 但语义不同：9C trace 是"脉冲-响应向量"，不是 EMA 活动均值

命名建议：`_event_trace`（区分于已有的 `_activity_traces`、`_onset_traces`）。

### 2.3 Event Vector (phi) 的生成

**当前问题：** 9C 实验中 phi 是从硬编码的 L/R stimulus 的 spatial Gaussian 生成的。在真实系统中，不应有硬编码的 L/R。

**建议：** Environment 层定义 world-event，每个 event 天然带有 spatial activation pattern。

```
world_event → Environment.generate_spatial_vector(event, units) → phi (O(N) np.ndarray)
```

这一步不应该是 9C.4 的 blocker——可以先用最小的 Environment event 接口（已有的 `StimulusEvent` → `_influences_at_step`），把 phi 生成逻辑从实验脚本移到 Environment。

### 2.4 Update 触发时机

**当前：** 实验脚本在预定的 schedule step 触发更新。

**集成后：** LifeCore.step 中检测环境事件，在事件到达的 step 触发 event-pair update。

```
LifeCore.step:
  ...
  env_events = environment.get_events_at(step)
  for event in env_events:
      phi = environment.phi_vector(event, units)
      trace.apply_decay(dt_since_last_event)
      if trace_mass > EPS and phi_mass > EPS:
          apply_event_pair_update(trace, phi, ...)
      trace += phi
  ...
```

### 2.5 与 Hebbian Plasticity 共存

**建议：两条路径叠加，不互斥。**

```
每一 step：
  1. Hebbian (per-step, per-connection, continuous)
  2. Event-pair (on-event, batch, gated)     ← 仅在事件到达时触发
```

两者作用于同一组 weights，正常情况下 Hebbian 贡献连续微小变化，事件对贡献离散方向性变化。这模拟了"日常慢慢塑形 + 关键事件留下方向性印记"。

需要注意的可能是：washout（长 rest）的语义在 core 中变成了"事件的到达间隔"，而这取决于环境的事件频率。这不是参数，是环境设计。

### 2.6 dW Ledger 的角色

**建议：debug instrumentation，默认关闭。**

```python
cfg.event_pair_ledger_enabled = False  # 诊断时才开
```

当启用时，在 event-pair update 后记录 per-direction dW、gate 值、contamination 等，写入内部 buffer，实验层通过 Observer API 读取。

### 2.7 参数提案

向 `AnivaConfig` 新增：

```python
# Phase 9C: event-pair trace plasticity
event_pair_plasticity_enabled: bool = False
event_pair_trace_decay: float = 1000.0       # τ_trace, O(N) trace decay
event_pair_update_l1: float = 1e-4            # target_event_update_l1
event_pair_gate_mode: str = "soft_trace_gate" # "soft_trace_gate" | "bare_l1_norm" | "hard_threshold"
event_pair_gate_ref: float = 3e-2             # trace_gate_ref
event_pair_gate_power: float = 1.0            # gate_power
event_pair_gate_threshold: float = 1e-3       # hard_threshold 的阈值
event_pair_ledger_enabled: bool = False       # dW ledger diagnostics
event_pair_ledger_buffer_size: int = 1000     # 最多保留的 ledger 条目数
```

### 2.8 最小集成步骤（9C.4 实现时按序执行）

1. 在 `AnivaConfig` 添加 event-pair 参数
2. 在 `LifeCore` 添加 `_event_trace` 数组（O(N)）
3. 在 `LifeCore.step` 中添加 trace decay + event 检测逻辑
4. 在 `plasticity.py`（或新建 `plasticity_event_pair.py`）实现 `apply_event_pair_update`
5. 添加环境事件生成 phi 的最小路径（复用 `_influences_at_step`）
6. 写最小 smoke 验证 plumbing（1 seed, OFF vs event_pair, 检查 trace decay / update / no NaN）
7. 运行 2-seed pilot（42, 999）确认核心集成不退化
8. 不在此阶段做 4-seed validation（那是 9C.4 实现完成后的 .5）

---

## 3. Phase 9D — Structural Consolidation（方向规划）

### 3.1 为什么需要 9D

9C 解决的是：**短时事件关系绑定。** 一次事件对到达 → 立即沉积方向性 dW。

但生命系统的记忆不只是瞬时沉积——有些模式是反复出现的，需要从短暂塑性痕迹深化为稳定结构。9D 要研究：**如何把 event-pair plasticity 的产出巩固为长期结构。**

### 3.2 候选方向：Synaptic Tagging and Capture (STC) 启发

Nature Reviews Neuroscience, 2010 (Redondo & Morris); Annual Review of Neuroscience, 2008 (Reymann & Frey).

核心思想：
- 突触活动产生"标签"（tag）——临时标记，持续数小时
- 标签本身不足以产生持久 LTP/LTD
- 需要弥散调节信号（如多巴胺、去甲肾上腺素）来"捕获"标签
- 只有被捕获的标签才会固化

Aniva 映射：
- tag = 9C event-pair dW 的局部沉积（已经存在）
- capture signal = 全局调节信号（不存在，需要设计）
- 被捕获的 tag → weight change 从"暂时"升级为"稳定"

### 3.3 设计挑战

- 如何定义"全局重要事件"？不能靠外部 reward（红线）
- capture signal 应该内生——比如网络整体活动超过某个阈值、或特定节律模式触发
- 需要避免"所有事件都被捕获"或"没有事件被捕获"

### 3.4 明确不在此阶段做的事

- 不实现 STC-like 机制
- 不引入外部 reward signal
- 不连接 LLM / emotion / personality 作为 capture trigger

---

## 4. 边界声明

| 验证了什么 | 没验证什么 |
|-----------|-----------|
| 9C-EPT + soft_trace_gate 在 dW ledger 层面稳产方向性 | broader digital-life existence |
| 4 seeds 跨 seed 一致 | 更多 seed / 更大参数空间 |
| 对照组干净（无假阳性） | 所有可能的对照组 |
| temporal event-pair plasticity mechanism | consciousness / personhood / full digital life |

---

## 5. 优先级建议

```
9C.4 integration design (本 note) → done
9C.4 minimal implementation → minimal smoke → 2-seed pilot
9C.4 integration validation → 如果需要，再跑 4-seed
9D detailed design note → when 9C.4 is stable
```

**先装齿轮，再盖房子。**
