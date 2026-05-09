# Phase 6: History-Dependent Structural Bifurcation — 实验报告

> **日期**: 2026-05-02
> **版本**: v0.0.0.1, Phase 6.5
> **状态**: 稳定里程碑

---

## 1. 实验目的

验证 Aniva 的核心命题：

> **历史经历是否能够不可逆地重塑系统结构？**

具体来说：对两个初始状态完全相同的系统，施加相同刺激但**顺序不同**，最终它们的连接结构是否会产生可测量的差异？

这不是在测试"系统能记住什么"，而是在测试一个更底层的前提：

> 结构本身是否因经历而变形。

---

## 2. 实验设计

### 2.1 实验组矩阵

| 组名 | 描述 | Plasticity | 刺激序列 |
|------|------|:---:|------|
| **A_L** | 先左后右 | on | L@300, R@1000 |
| **A_R** | 先右后左 | on | R@300, L@1000 |
| **C** | 重复 A_L（可重复性对照） | on | L@300, R@1000 |
| **D_L** | plasticity-off 对照（先左后右） | **off** | L@300, R@1000 |
| **D_R** | plasticity-off 顺序对照（先右后左） | **off** | R@300, L@1000 |

### 2.2 刺激定义

```
L_STIM:  位置 (-0.5, 0.0, 0.0), 强度 0.03, 半径 0.5
R_STIM:  位置 ( 0.5, 0.0, 0.0), 强度 0.03, 半径 0.5
```

每次刺激持续 100 步。

### 2.3 默认参数

| 参数 | 值 |
|---|---|
| unit_count | 300 |
| connection_density | 0.05 (~4485 connections) |
| plasticity_rate | 0.0001 |
| homeostasis_enabled | True |
| homeostatic_target_abs_weight | 0.30 |
| dt | 0.1 |

---

## 3. 核心指标

### 3.1 Δ_weight_L1（结构分叉量）

两组最终权重向量的平均绝对差异：

```
Δ_weight_L1 = mean(|W_a - W_b|)
```

这是衡量"历史是否写入了结构"的直接指标。

### 3.2 因果骨架三检查

实验中定义了三个控制组来验证因果链：

| 检查项 | 比较 | 期望 | 含义 |
|---|---|---|---|
| **可重复性** | C vs A_L | = 0 | 相同历史 → 相同结构 |
| **Plasticity 因果** | D_L drift vs A_L drift | D_L << A_L | 结构变化需要 plasticity |
| **顺序对称性** | D_L vs D_R | = 0 | 无 plasticity 时顺序无关 |

三个检查全部通过 = `causal_skeleton_intact = True`。

### 3.3 分叉等级

| Δ_weight_L1 | 判定 |
|---|---|
| > 1e-4 | significant |
| 5e-5 ~ 1e-4 | emerging |
| < 5e-5 | weak |

---

## 4. 结果

### 4.1 120k 步 Numba 对照（seed=42）

**配置**: Numba plasticity 后端, homeostasis on, 120,000 步

| 比较 | Δ_weight_L1 | Cosine | 含义 |
|---|---:|---:|---|
| C vs A_L | 0.000000 | 1.000000 | 相同历史完全可复现 ✅ |
| A_L vs A_R | **0.000105** | 0.99999987 | 不同顺序产生结构分叉 ✅ |
| D_L vs D_R | 0.000000 | 1.000000 | 无 plasticity 时顺序无关 ✅ |
| D_L drift | 0.000000 | — | Plasticity-off 阻止结构重写 ✅ |
| A_L drift | 0.197002 | — | Plasticity-on 允许结构变化 ✅ |

**因果骨架**: intact ✅

### 4.2 120k 步 Scalar 对照（seed=999）

**配置**: Scalar plasticity 后端, homeostasis on, 120,000 步

| 比较 | Δ_weight_L1 | Cosine |
|---|---:|---:|
| C vs A_L | 0.000000 | 1.000000 |
| A_L vs A_R | **0.000092** | 0.99999988 |
| D_L vs D_R | 0.000000 | 1.000000 |
| D_L drift | 0.000000 | — |
| A_L drift | 0.200711 | — |

**因果骨架**: intact ✅ → 判定 **emerging**（>5e-5, <1e-4）

### 4.3 Numba vs Scalar 等价性验证

同一 seed=42、同一步数（120k）的 Numba 与 Scalar 路径对比：

| 指标 | Scalar (Phase 6) | Numba (Phase 6.5) | 匹配 |
|---|---|---|---|
| A_L vs A_R Δ_weight_L1 | 0.000105 | 0.000105 | ✅ |
| C vs A_L | 0.000000 | 0.000000 | ✅ |
| D_L vs D_R | 0.000000 | 0.000000 | ✅ |
| D_L drift | 0.000000 | 0.000000 | ✅ |
| A_L drift | 0.197002 | 0.197002 | ✅ |
| causal_skeleton_intact | True | True | ✅ |

**结论**: Numba 后端与 Scalar 路径在 120k 步尺度上逐位一致。加速未改变因果骨架。

### 4.4 2k 步 Numba 多 seed 回归

| Seed | A_L vs A_R Δ | 判定 | C vs A_L | D_L vs D_R | 骨架 |
|---:|---:|---|---:|---:|---|
| 42 | 4.54e-05 | weak | 0.000000 | 0.000000 | intact |
| 77 | 4.32e-05 | weak | 0.000000 | 0.000000 | intact |

2k 步时 Δ 较小（分叉需要时间积累），但因果骨架在两个 seed 上均已完整。

---

## 5. Δ_weight_L1 增长轨迹（seed=42, Scalar）

```
 20k:  0.000041  (dynamics only)
 50k:  0.000060  (+46%)
100k:  0.000093  (2.27× baseline)
120k:  0.000105  (跨过 1e-4 significance 阈值)
```

分叉量随步数单调增长，未出现饱和或回退迹象。

---

## 6. 解读

### 6.1 可以确认的

1. **历史顺序效应存在且可复现。** 相同 seed + 相同事件 = 完全相同结构。相同 seed + 颠倒顺序 = 可测量结构差异。

2. **效应经过 plasticity 通道。** 关闭 plasticity 后，结构不再变化，顺序也不再产生差异。

3. **效应不是噪声伪影。** 对照组（C vs A_L, D_L vs D_R）均为 0，系统不会凭空制造"历史分叉"。

4. **机制跨后端一致。** Numba JIT 编译的 plasticity 内核与 Python scalar 路径在 120k 步尺度上获得完全一致的因果判定。

5. **机制跨 seed 可复现。** 所有测试 seed 均通过因果骨架三检查。

### 6.2 不能确认的

- 系统具有意识、生命、智能或自主意图
- 系统能够"回忆"特定事件
- 结构差异具有功能性意义（影响后续行为）
- 效应在更大规模或更长时间尺度上的行为

### 6.3 当前最严谨的表述

> **Aniva 在 v0.0.0.1 阶段展示了可测量、可复现的 history-dependent plasticity trace（历史依赖型可塑性痕迹）。**

---

## 7. 限制

1. **单次刺激模式**: 每个实验组仅含两次刺激事件。未测试多次重复、交错或长序列。
2. **全局稳态**: Homeostasis 目前为全局缩放，非局部（per-connection）调控。
3. **小规模**: 300 units × ~4500 connections。效应在更大规模拓扑上的表现未知。
4. **无闭合环路**: 系统结构变化不反馈到环境。环境是开环的。
5. **seed 样本有限**: 当前仅 4 个 seed 完成 120k 验证，需要更大样本。
6. **结构差异的功能意义未测试**: 不知道 Δ_weight_L1 = 1e-4 是否对系统行为有可观测影响。

---

## 8. 复现命令

### 快速验证（~4 分钟，5000 步）

```bash
python -u -m aniva.experiments.exp5_history_bifurcation \
  --steps 5000 \
  --groups A_L A_R C D_L D_R \
  --seed 42 \
  --homeostasis-enabled
```

### 正式复现（~40 分钟，120k 步，Numba 加速）

```bash
python -u -m aniva.experiments.exp5_history_bifurcation \
  --steps 120000 \
  --groups A_L A_R C D_L D_R \
  --seed 42 \
  --homeostasis-enabled \
  --use-numba-plasticity \
  --snapshot-interval 30000 \
  --summary-json results/phase6_120k_numba_seed42.json \
  --summary-only
```

### 多 seed 批量（需要 Numba）

```bash
python -u -m aniva.experiments.exp5_history_bifurcation \
  --steps 2000 \
  --groups A_L A_R C D_L D_R \
  --seeds 42 77 99 \
  --homeostasis-enabled \
  --use-numba-plasticity \
  --summary-json results/phase6_2k_multiseed.json \
  --summary-only
```

---

## 9. 下一步

| 优先级 | 任务 | 说明 |
|---|---|---|
| 高 | 多 seed 120k 验证 | seed=1,2,3,4,5 确认效应稳定性 |
| 高 | 汇总聚合工具 | `aggregate_summaries.py` 自动统计多 seed 结果 |
| 中 | 更多刺激模式 | 重复刺激、交错刺激、不同间隔 |
| 中 | 功能影响测试 | 结构差异是否影响后续刺激响应 |
| 低 | 局部稳态 | per-connection homeostatic regulation |
| 低 | 并行 seed runner | 加速多 seed 实验 |

---

## 附录 A: 硬件与软件环境

| 项 | 值 |
|---|---|
| OS | Windows 11 |
| Python | 3.10 |
| NumPy | 2.2.6 |
| Numba | 0.65.0rc1 (optional) |

## 附录 B: 相关文件

- 实验代码: `aniva/experiments/exp5_history_bifurcation.py`
- 核心引擎: `aniva/life_core.py`
- Plasticity (scalar): `aniva/core/plasticity.py`
- Plasticity (Numba): `aniva/core/plasticity_numba.py`
- 性能文档: `docs/performance_notes.md`
- 历史发现: `docs/phase5_phase6_findings.md`
- 正式结果: `results/phase6_120k_numba_seed42.json`
