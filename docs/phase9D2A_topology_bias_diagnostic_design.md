# Phase 9D.2A — Topology-Bias Diagnostic Design

> **定位：** diagnostic design，不是新 validation。
> 9D.2 主信号很强（slow_OS +0.718），但 simultaneous control 的 slow_DI = +0.164
> 超过了预注册阈值 |DI| < 0.1。9D.2A 的目标是诊断这个偏置的来源，不是改写 9D.2 结论。

---

## 1. 背景

### 9D.2 结果回顾

| Arm | slow_DI | 说明 |
|-----|---------|------|
| L→R repeated | +0.206 | 方向正确 |
| R→L repeated | -0.512 | 方向正确，反向 |
| L→R single | +1.000 | 纯方向（单对） |
| R→L single | -1.000 | 纯方向（单对） |
| **simultaneous** | **+0.164** | **超过 |DI|<0.1 阈值** |
| no_event | 0 | 干净 |

### 问题

simultaneous 事件不编码顺序（L 和 R 同时到达）。理论上 slow_DI 应接近 0。
+0.164 可能来自：

1. **初始 L/R 拓扑不对称** — L→R 和 R→L 连接数量/权重分布不等
2. **Event vector 覆盖差异** — L phi 和 R phi 的空间覆盖/质量不对称
3. **Consolidation global bias** — capture 机制非方向性地偏向某侧
4. **Metric 未做 baseline correction** — DI 被基线偏置抬高
5. **真正的 false positive** — consolidation 产生了无事件顺序却能方向化的假信号

---

## 2. 候选诊断

### A. Pre-consolidation topology baseline

在任何事件发生前，测量 fast weight 的 L→R / R→L L1 分布：

```
baseline_fast_LR_l1 = L1 of fast weights on L→R connections (step 0)
baseline_fast_RL_l1 = L1 of fast weights on R→L connections (step 0)
baseline_fast_DI = (LR - RL) / (LR + RL + eps)
```

同时在 warmup 结束后（step 2000，事件前）再测一次。

**判断：** 如果 `baseline_fast_DI` 与 simultaneous slow_DI 同号且同量级，
则偏置来自初始网络拓扑，非 consolidation 引入。

### B. Event-vector support diagnostic

统计 L 和 R 的 phi 向量覆盖特征：

```
event_support_L = count(phi_L > 0)
event_support_R = count(phi_R > 0)
phi_mass_L = sum(|phi_L|)
phi_mass_R = sum(|phi_R|)
```

同时检查 L/R phi 对 L 半球和 R 半球的覆盖是否对称。

**判断：** 如果 L phi 覆盖的 L-hemisphere 单元多于 R phi 覆盖的 R-hemisphere
单元（或反过来），simultaneous phi = L+R 会自然产生覆盖偏置。

### C. Baseline-corrected slow_DI

```
corrected_slow_DI = slow_DI - baseline_fast_DI
```

这不是替代原始指标，只作为诊断辅助。如果 `corrected_slow_DI` 接近 0，
说明 simultaneous 的 apparent DI 几乎完全来自拓扑基线。

### D. Swapped / mirrored L-R diagnostic

交换 L 和 R stimulus 的空间位置，重新跑 simultaneous arm：

```
L_STIM' = original R_STIM position
R_STIM' = original L_STIM position
```

**判断：**
- 如果 bias 反向（原来是 +0.164，交换后变负），→ spatial/topology bias
- 如果 bias 仍同向（交换后仍是正），→ 可能是 consolidation global bias

⚠️ 这一步需要改变 stimulus definition，属于较重的诊断，可以放在 9D.2A 后期或
标记为 optional。

### E. Shuffled / matched topology mask（optional）

仅在第一轮诊断不足以判明时启用。例如：
- 按 L→R / R→L 连接数做匹配采样，消除数量不对称
- 或随机 shuffle 连接的空间标签，看 bias 是否消失

---

## 3. Primary Diagnostic Metrics

| 指标 | 来源 | 说明 |
|------|------|------|
| `baseline_fast_LR_l1` | step 0 或 warmup-end | 初始 L→R fast weight 质量 |
| `baseline_fast_RL_l1` | step 0 或 warmup-end | 初始 R→L fast weight 质量 |
| `baseline_fast_DI` | 计算 | 初始方向偏置 |
| `event_support_L` | phi vector | L event 覆盖单元数 |
| `event_support_R` | phi vector | R event 覆盖单元数 |
| `phi_mass_L` | phi vector | L phi 总质量 |
| `phi_mass_R` | phi vector | R phi 总质量 |
| `simultaneous_slow_DI` | 9D.2 已有 | 原始 simultaneous DI |
| `corrected_slow_DI` | DI - baseline_DI | 基线校正后的 DI |
| `sign_agreement` | sign(baseline_DI) == sign(simultaneous_DI) | 同号确认 |
| `n_LR_connections` | 连接分类 | L→R 连接总数 |
| `n_RL_connections` | 连接分类 | R→L 连接总数 |

---

## 4. Decision Rules

按优先级执行诊断 A-C，必要时启用 D：

1. **如果 `baseline_fast_DI` 与 `simultaneous_slow_DI` 同号**，
   且 `|corrected_slow_DI| < 0.1` →
   **判为 topology baseline bias**。9D.2 simultaneous caveat 本质是网络先天不对称，
   不是 consolidation 引入的假阳性。

2. **如果 swapped L/R 后 simultaneous slow_DI 反向** →
   **判为 spatial / topology bias**，确认 bias 来自 stimulus placement。

3. **如果 baseline correction 后 |corrected_DI| 仍 ≥ 0.1**，
   且 swapped 后仍未反向 →
   **判为 possible consolidation false positive**，需要更深入研究，
   但不应直接 pivot 9D 路线。

4. **无论诊断结果如何：**
   - 不修改 9D.2 原 success threshold
   - 不把 9D.2 改写成 clean pass
   - 不在 9D.3 中删除 simultaneous arm

---

## 5. 边界

- 不启动 9D.3
- 不调参
- 不修改 9D.2 结果口径
- 不声称 formal validation
- arm label 只能用于离线分析，不进入机制更新
- capture signal / tag / slow_weight 公式不变
- 不引入 reward / goal / agent / emotion / LLM

---

## 6. 文件规划

```
docs/phase9D2A_topology_bias_diagnostic_design.md  ← 本文档
aniva/experiments/exp9D2A_topology_diagnostic.py    (实现时创建)
```

---

## 7. 与后续阶段的关系

- **9D.2A 完成诊断** → 判明 simultaneous caveat 来源
- **诊断为 topology bias** → 9D.3 pilot 可以直接推进，带上 baseline correction 作为辅助指标
- **诊断为 consolidation false positive** → 需要在 9D.3 前重新审视 capture gate / tag 方向性
- **诊断 inconclusive** → 9D.3 保留 simultaneous arm，带上 baseline_DI 作为 covariate
