# Phase 9D.2 — Consolidation Behavior Design

> **定位：** behavior-level smoke / pilot design，不是 formal validation。
> 9D.1 已证明 tag/capture/slow_weight plumbing 能工作。
> 9D.2 要验证 repeated event-order history 是否能产生可解释的 slow structural pattern。

---

## 1. 背景

### 9D.1 已完成

| 齿轮 | 验证方式 | 状态 |
|------|----------|------|
| tag 产生 | event-pair dW → produce_tags | full smoke passed |
| tag 衰减 | exp(-1/τ_tag) per step | full smoke passed |
| tag 累加 | repeated > single tag_mass | full smoke passed (7×) |
| capture 触发 | signal ≥ threshold → apply_capture | full smoke passed |
| slow_weight 写入 | tag → slow_weight via rate | full smoke passed (6.2×) |
| slow_weight clamp | ≤ slow_weight_max | full smoke passed |
| refractory | ≥ 500 steps between captures | full smoke passed |
| baseline 零污染 | no-event arm slow_l1 = 0 | full smoke passed |

### 9D.2 要回答的问题

```
9C answered:  Can event order create directional fast dW?
9D.1 answered: Can fast dW produce tag, capture, and slow_weight plumbing?
9D.2 asks:    Can repeated event-order history produce stronger and
              directionally interpretable slow structural sediment than
              single / no-event / opposite-order / simultaneous histories?
```

---

## 2. 实验设计

### 2.1 Arms

| Arm | 事件模式 | 对重复数 | 验证内容 |
|-----|---------|---------|----------|
| L→R repeated | L→R 重复 | 3–5 | 同向重复是否沉积方向性 slow structure |
| R→L repeated | R→L 重复 | 3–5 | 反向重复是否产生反向 slow DI |
| L→R single | L→R 单对 | 1 | 单次事件对 baseline，应与 repeated 有量级差 |
| R→L single | R→L 单对 | 1 | 反向单次 baseline |
| simultaneous | L+R 同时 | 3–5 | 同时事件不应产生方向性 slow pattern |
| no-event | 无事件 | 0 | baseline 零污染确认 |

可选暂不加：
- alternating (L→R then R→L alternating) — 方向冲突是否降低 consolidation

### 2.2 参数

全部沿用 9D.1 full smoke + 9C.4 默认值：

| 参数 | 值 |
|------|-----|
| `unit_count` | 300 |
| `seed` | 42 |
| `dt` | 0.5 |
| `event_pair_plasticity_enabled` | True |
| `event_pair_trace_tau` | 1000.0 |
| `event_pair_target_update_l1` | 1e-4 |
| `event_pair_gate_mode` | soft_trace_gate |
| `event_pair_trace_gate_ref` | 3e-2 |
| `event_pair_gate_power` | 1.0 |
| `event_pair_ledger_enabled` | True |
| `consolidation_enabled` | True |
| `consolidation_tag_tau` | 5000.0 |
| `consolidation_capture_threshold` | 0.5 |
| `consolidation_slow_weight_max` | 0.1 |
| `consolidation_slow_weight_rate` | 0.1 |
| `consolidation_capture_refractory_steps` | 500 |
| `consolidation_ledger_enabled` | True |
| `plasticity_rate` | 0.0001 |
| `homeostasis_enabled` | False（9D.1 默认） |

### 2.3 Schedule

沿用 9D.1 full smoke 结构：

```
warmup: 2000 steps
pair_gap: 500 steps (L→R or R→L within-pair interval)
pair_interval: 1500 steps (between pair starts)
rest_after: 2000 steps

Arm structure (repeated, n=3):
  L@2000→R@2500, L@3500→R@4000, L@5000→R@5500, rest to 7500

Arm structure (single):
  L@2000→R@2500, rest to 7500

Arm structure (simultaneous ×3):
  LR@2000, LR@3500, LR@5000, rest to 7500
```

---

## 3. 观测指标

### 3.1 Primary metrics

| 指标 | 定义 | 说明 |
|------|------|------|
| `slow_LR_l1` | L1 norm of slow_weight on L→R connections | 方向性 slow 沉积量 |
| `slow_RL_l1` | L1 norm of slow_weight on R→L connections | 反向沉积量 |
| `slow_DI` | (slow_LR − slow_RL) / (slow_LR + slow_RL + ε) | 单 arm 方向指数 |
| `slow_OS` | slow_DI_L→R_repeated − slow_DI_R→L_repeated | 跨 arm 顺序分离度 |
| `slow_l1_total` | L1 norm of all slow_weight | 总沉积量 |
| `tag_mass_final` | 最终 tag 绝对值总和 | tag 累积总量 |
| `capture_count` | 总 capture 事件数 | capture 频率 |
| `slow_delta_l1_total` | 所有 capture 的 slow_weight 变化 L1 总和 | capture 转移量 |

### 3.2 Secondary metrics

| 指标 | 说明 |
|------|------|
| `fast_DI` / `fast_OS` | 快速权重方向性（对比 slow） |
| `effective_DI` / `effective_OS` | 总权重方向性 |
| `capture_signal_mean/max` | capture signal 分布 |
| `refractory_intervals` | capture 间隔分布 |
| `saturation_frac` | 权重饱和比例 |
| `NaN_count` | 全程 NaN 计数 |

### 3.3 Connection classification (offline only)

使用与 9C.4 相同的空间区域分类：
- L→R: src.x < −0.1, tgt.x > 0.1
- R→L: src.x > 0.1, tgt.x < −0.1

---

## 4. 预期定性行为

1. **Repeated > Single**：repeated arms 的 slow_l1_total 显著大于对应 single arms
2. **Directional separation**：L→R repeated 的 slow_DI > 0，R→L repeated 的 slow_DI < 0
3. **slow_OS > 0**：跨 arm 顺序分离度为正
4. **Baseline clean**：no-event arm slow_l1 = 0
5. **Simultaneous non-directional**：simultaneous arm slow_DI ≈ 0
6. **Single arms weakly directional**：比 repeated 弱但方向一致
7. **No runaway**：slow_max_abs ≪ 0.1
8. **No NaN**

---

## 5. 成功标准（behavior smoke 级）

- [ ] All arms complete without NaN / explosion
- [ ] slow_l1_repeated > slow_l1_single（显著差异，>2×）
- [ ] L→R repeated slow_DI > 0
- [ ] R→L repeated slow_DI < 0
- [ ] slow_OS > 0（方向性顺序分离）
- [ ] no-event slow_l1 ≈ 0
- [ ] simultaneous slow_DI ≈ 0（|slow_DI| 远小于 ordered arms）
- [ ] slow_max_abs ≪ 0.1（clamp 有效）
- [ ] capture_count repeated > capture_count single > 0
- [ ] tag_mass repeated > tag_mass single

---

## 6. 失败标准

以下任一视为需要诊断：

- [ ] 所有 arm slow_l1 相同 → global shift，非事件特异性
- [ ] no-event arm slow_l1 > 0 → 非事件触发 leak
- [ ] simultaneous arm slow_DI 与 ordered arm 同量级 → 方向性非来自顺序
- [ ] L→R repeated 与 R→L repeated 的 slow_DI 同号 → 方向性不来自事件顺序
- [ ] capture 每步触发 → refractory 失效
- [ ] slow_weight 触达 slow_weight_max → runaway
- [ ] slow_l1_repeated ≤ slow_l1_single → 重复未增强

---

## 7. 反作弊边界

- 不引入 arm label 做机制判断（仅离线分类）
- capture signal 公式不变
- 不引入 episode counter / event counter
- 不持久化任何"记忆"字段
- 不比较 arm 间差异来触发不同行为
- 不引入 reward / goal / agent / emotion / LLM
- slow_DI / slow_OS 是离线观测指标，不参与 capture 判断

---

## 8. 不做的事

- 不跑多 seed（单 seed=42 够 behavior smoke）
- 不调参
- 不宣称 long-term memory 成立
- 不启动 ECS（6 arms × ~87s/arm ≈ 8.7 min，本地可跑）
- 不写 formal validation report
- 不自动 9D.3

---

## 9. Runtime 估算

9D.1 full smoke：3 arms × 7500 steps, 260s → ~87s/arm。
9D.2：6 arms × 7500 steps → ~522s ≈ 8.7 min。

在 10 分钟红线内，本地可跑。

---

## 10. 文件规划

```
docs/phase9D2_consolidation_behavior_design.md   ← 本文档
aniva/experiments/exp9D2_consolidation_behavior.py (9D.2 实现时创建)
```

---

## 11. 与后续阶段的关系

- **9D.2 passed** → 进入 9D.3 two-seed pilot（seeds 42, 999）
- **9D.2 failed** → 诊断是 plumbing leak 还是 behavior hypothesis 不成立，不自动 pivot
- **9D.3 passed** → 进入 9D.4 four-seed validation
- **9D.4 passed** → 9D 整体可收档，进入 Phase 10 或其他方向

9D.2 仍然是 behavior smoke，不是 formal validation。它在 9D.1 plumbing 和 9D.3/9D.4 多 seed validation 之间起桥梁作用。
