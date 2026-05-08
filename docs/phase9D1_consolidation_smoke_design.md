# Phase 9D.1 Consolidation Smoke Design

> **定位：** plumbing verification only，不是科学验证。
> 9D.1 skeleton 已经把 gear 装进去了；这个 smoke 只是轻敲一下容器，听它响不响。
> 不宣称长期固化成立，不调参，不多 seed。

---

## 1. 目的

验证 Phase 9D.1 skeleton 的 7 个 plumbing 齿轮在 running core 中都正常转动：

1. **tag 产生** — event-pair dW 被 produce_tags 捕获
2. **tag 衰减** — tag 在无事件间隔中按 τ_tag 衰减
3. **tag 累加** — 重复 event-pair update 后 tag 幅值增长
4. **capture 触发** — capture signal 超阈值时 tag → slow_weight
5. **slow_weight clamp** — slow_weight 被 slow_weight_max 约束
6. **refractory 有效** — refractory 期间不重复 capture
7. **effective weights** — effective = fast + slow，参与突触计算

---

## 2. 实验设计

### 2.1 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `unit_count` | 300 | 全尺寸 |
| `seed` | 42 | 单 seed 够用 |
| `dt` | 0.5 | 默认 |
| `consolidation_enabled` | `True` | 开 |
| `event_pair_plasticity_enabled` | `True` | 开 |
| `consolidation_ledger_enabled` | `True` | 开 ledger |
| `event_pair_ledger_enabled` | `True` | 开 9C ledger |
| `event_pair_trace_tau` | 1000.0 | 默认 |
| `consolidation_tag_tau` | 5000.0 | 默认 |
| `consolidation_capture_threshold` | 0.5 | 默认 |
| `consolidation_slow_weight_max` | 0.1 | 默认 |
| `consolidation_slow_weight_rate` | 0.1 | 默认 |
| `consolidation_capture_refractory_steps` | 500 | 默认 |
| `plasticity_rate` | 0.0001 | 默认 Hebbian |

其余参数全部默认。

### 2.2 Arms

**Arm A — repeated same-order (×3 pairs)**

```
warmup: 2000 steps
pair 1: L@2000 → R@2500 (Δt=500)
pair 2: L@3500 → R@4000 (Δt=500)
pair 3: L@5000 → R@5500 (Δt=500)
rest: 2000 steps (to 7500)
```

**Arm B — single pair only**

```
warmup: 2000 steps
pair 1: L@2000 → R@2500 (Δt=500)
rest: 5000 steps (to 7500)
```

**Arm C — no-event baseline**

```
run 7500 steps, no events
```

### 2.3 Environment

- 使用 `Environment.phi_vector` 生成 phi（与 9C.4 一致）
- phi_L: 50 units in left hemisphere, Gaussian activation profile
- phi_R: 50 units in right hemisphere, same profile
- `active_phi_gamma = 2.0`, `active_phi_sigma = 0.3`

---

## 3. 观测指标

### 3.1 Tag 时间线（每 event-pair update 后采样）

| 指标 | 采样时机 | 验证内容 |
|------|----------|----------|
| `tag_mass` | event arrival 后 | tag 绝对值总和，每次 event-pair update 后应增长 |
| `n_tagged` | event arrival 后 | tag > 0 的连接数 |
| `tag_mass_decay_ratio` | 两次 event 之间 | 是否匹配 exp(-Δsteps / τ_tag) |

### 3.2 Capture 事件（ledger）

| 指标 | 来源 | 验证内容 |
|------|------|----------|
| `n_captures` | `len(_consolidation_ledger)` | Arm A 应有 capture 事件 |
| `capture_signal` | ledger entry | 应在 [0, 1]，含 fractional 值 |
| `slow_weight_delta_l1` | ledger entry | 应 > 0（tag 被转移） |
| `tag_mass` (at capture) | ledger entry | capture 前的 tag 质量 |
| `n_tagged_connections` | ledger entry | capture 时 tagged 连接数 |

### 3.3 Slow weight 快照

| 指标 | 采样时机 | 验证内容 |
|------|----------|----------|
| `slow_weight_l1` | 每 500 steps + 每次 capture 后 | 应单调非减，最终值 0 < x ≤ slow_weight_max × N_conn |
| `slow_weight_max_abs` | 最终快照 | ≤ 0.1（clamp 护栏有效） |
| `slow_weight_nonzero_n` | 最终快照 | Arm A > Arm B > Arm C |

### 3.4 Effective weights

| 指标 | 采样时机 | 验证内容 |
|------|----------|----------|
| `effective_l1` | 最终快照 | 应与 fast_l1 有可测量差异（consolidation 后） |
| `effective_clamped_n` | 最终快照 | 被 clamp 到 ±1 的连接数 |

### 3.5 稳定性

| 指标 | 验证内容 |
|------|----------|
| `NaN count` | tag / slow / effective 全程 0 NaN |
| `runaway count` | slow_weight 无超出 clamp 范围 |
| `weight explosion` | fast_weight 全程在 [-1, 1] |

---

## 4. 预期定性行为（plumbing 级）

这些不是科学假设，而是对 plumbing 正确性的工程预期：

1. **Arm A > Arm B > Arm C** 在以下指标上：
   - `n_tagged_connections`（Arm A 累积更多）
   - `tag_mass` 峰值
   - `n_captures`
   - `slow_weight_l1` 最终值

2. **Tag 衰减在 event 间隔中可视**：
   - 两次 pair 之间 tag_mass 按指数下降
   - 下降速率匹配 τ_tag = 5000

3. **Capture 只在信号高时触发**：
   - 不是每步都 capture（refractory 有效）
   - capture 间隔 ≥ 500 steps

4. **Slow weight 在 clamp 范围内**：
   - 最大绝对值 ≤ 0.1
   - 增长后不再倒退（slow_weight 只增不减）

5. **0 NaN / 0 runaway**：
   - 所有数组在全程无 NaN
   - 所有权重在 [-1, 1]

---

## 5. 成功标准（plumbing 级）

- [ ] 所有 arm 0 NaN
- [ ] tag_mass > 0 出现在每次 event-pair update 后
- [ ] tag_mass 在无事件间隔中衰减
- [ ] Arm A 的 tag 累积 > Arm B（3 对 vs 1 对）
- [ ] capture ledger 非空（Arm A 至少 1 次 capture）
- [ ] slow_weight_l1 > 0（tag 被转移到了 slow_weight）
- [ ] slow_weight 最大绝对值 ≤ 0.1（clamp 护栏有效）
- [ ] capture 间隔 ≥ 500 steps（refractory 有效）
- [ ] Arm C（无事件）slow_weight 全部为 0
- [ ] effective_l1 ≠ fast_l1（consolidation 改变了突触计算输入）

---

## 6. 失败标准

以下任一情况视为 plumbing 有 bug，需要 debug：

- [ ] 任何 arm 出现 NaN
- [ ] tag_mass 在所有 arm 始终为 0
- [ ] tag 不衰减（decay 路径未接通）
- [ ] capture 永不远触发（signal 公式或 threshold 有问题）
- [ ] capture 每步都触发（refractory 不工作）
- [ ] slow_weight 突破 ±0.1（clamp 不工作）
- [ ] Arm C slow_weight 非零（无事件却产生了固化）
- [ ] effective = fast（consolidation 开关未影响突触计算）
- [ ] 运行时报错或 OOM

失败时不自动调参。先诊断哪个齿轮没啮合。

---

## 7. 反作弊边界

- 不引入 arm label 做 capture 判断
- capture signal 公式不变（能量 × trace，无新输入）
- 不持久化任何"记忆"字段
- 不引入 episode counter / event counter
- 不比较 arm 间差异来触发不同行为

---

## 8. 不做的事

- 不跑多 seed（单 seed=42 够 plumbing check）
- 不调参
- 不宣称 long-term structural memory 成立
- 不分析 DI / OS / directional asymmetry（那是 9D.2 的事）
- 不启动 ECS（~7500 steps 本地可跑）
- 不写 formal validation report

---

## 9. 实现计划

文件：`aniva/experiments/exp9D1_consolidation_smoke.py`

结构（参考 `exp9C4_full_integration_smoke.py`）：

```python
def run_arm(label, schedule, seed, n_steps):
    """Run one arm, return metrics dict."""
    ...

def make_schedule_L_then_R(n_pairs, warmup, dt_pair, rest):
    """Generate event schedule."""
    ...

def main():
    # Arm A: 3 pairs
    # Arm B: 1 pair
    # Arm C: no events
    # Collect and print metrics
    # Save CSV
    ...
```

输出：
- 终端打印所有 10 项 success criteria 的 pass/fail
- `results/phase9D1_smoke_metrics.csv` 保存 tag / capture / slow 时间线

---

## 10. 判断

- 这个 smoke 的粒度是 **7 个齿轮逐个敲**，不是 9D 科学结论
- 如果全部通过 → 9D.1 skeleton 确认完好，可以进入 9D.2 smoke design
- 如果部分失败 → 根因诊断，修 plumbing，不 pivot 路线
- 预计运行时间 < 5 分钟（7500 steps × 300 units，本地）
