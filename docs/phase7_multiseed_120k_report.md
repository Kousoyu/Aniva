# Phase 7.4: Multi-Seed 120k Verification — 实验报告

> **日期**: 2026-05-03
> **版本**: v0.0.0.1, Phase 7.4
> **状态**: 跨 seed 统计证据

---

## 1. 实验目的

Phase 6 在 seed=42 上确认了历史分叉效应的存在。Phase 6 的 4 seed 验证（42, 77, 123, 999）表明因果骨架跨 seed 可复现。

Phase 7.4 的目标是扩大样本量，回答一个更硬的问题：

> **历史依赖结构分叉是 seed=42 的个例，还是跨 seed 系统性存在的现象？**

---

## 2. 实验设计

### 2.1 配置

| 参数 | 值 |
|---|---|
| Seeds | 1, 2, 3, 4, 5, 10, 42, 77, 99, 123, 999（11 个） |
| Steps per seed | 120,000 |
| Groups per seed | A_L, A_R, C, D_L, D_R（5 组） |
| Total experiments | 55 |
| Backend | Numba plasticity |
| Homeostasis | on, target=0.30 |

### 2.2 实验组定义（与 Phase 6 一致）

| 组 | 描述 | Plasticity |
|---|---|---|
| A_L | L@300, R@1000 | on |
| A_R | R@300, L@1000 | on |
| C | 重复 A_L（可重复性对照） | on |
| D_L | L@300, R@1000 | off |
| D_R | R@300, L@1000 | off |

### 2.3 刺激定义

```
L_STIM: (-0.5, 0.0, 0.0), intensity=0.03, radius=0.5
R_STIM: ( 0.5, 0.0, 0.0), intensity=0.03, radius=0.5
每次刺激持续 100 步
```

---

## 3. 数据完整性检查

| 检查项 | 结果 |
|---|---|
| per_seed 数量 | 11 ✅ |
| 所有 seed 均在列表中 | 1,2,3,4,5,10,42,77,99,123,999 ✅ |
| 每个 seed 含 5 组 | A_L, A_R, C, D_L, D_R ✅ |
| aggregate 存在 | ✅ |
| JSON 可解析 | ✅ |

---

## 4. 结果

### 4.1 因果骨架：11/11 完整

| 检查项 | 通过率 | 含义 |
|---|---|---|
| C vs A_L = 0 | **11/11** | 相同历史完全可复现 |
| D_L vs D_R = 0 | **11/11** | 无 plasticity 时顺序无关 |
| D drift = 0 | **11/11** | Plasticity-off 阻止结构重写 |
| A_L vs A_R > 0 | **11/11** | 不同历史顺序产生非零结构分叉 |
| causal_skeleton_intact | **11/11** | 因果链闭合 |

### 4.2 Δ_weight_L1 分布

```
Seed    Δ_weight_L1    判定          Δ (visual)
----    -----------    ----------    ----------
  3     0.000032       weak          ▏
  1     0.000035       weak          ▏
 10     0.000042       weak          ▏
123     0.000062       emerging      ▎
  2     0.000063       emerging      ▎
  5     0.000067       emerging      ▎
  4     0.000068       emerging      ▎
 77     0.000070       emerging      ▎
 99     0.000076       emerging      ▎
999     0.000092       emerging      ▌
 42     0.000105       significant   ▌
```

### 4.3 统计汇总

| 指标 | 值 |
|---|---|
| Δ mean | 6.47 × 10⁻⁵ |
| Δ std | 2.12 × 10⁻⁵ |
| Δ min | 3.24 × 10⁻⁵ (seed=3) |
| Δ max | 1.05 × 10⁻⁴ (seed=42) |
| Δ range | 3.2× |

### 4.4 判定分布

| 等级 | 阈值 | 数量 | 占比 | Seeds |
|---|---|---|---|---|
| significant | > 1e-4 | 1 | 9% | 42 |
| emerging | 5e-5 ~ 1e-4 | 7 | 64% | 2, 4, 5, 77, 99, 123, 999 |
| weak | < 5e-5 | 3 | 27% | 1, 3, 10 |

### 4.5 每 Seed 完整数据

| Seed | Δ A_LvsA_R | CvsA_L | DLvsDR | D_drift | AL_drift | Bifurcation | Skeleton |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 3.48e-05 | 0 | 0 | 0 | 0.195 | weak | True |
| 2 | 6.27e-05 | 0 | 0 | 0 | 0.197 | emerging | True |
| 3 | 3.24e-05 | 0 | 0 | 0 | 0.199 | weak | True |
| 4 | 6.76e-05 | 0 | 0 | 0 | 0.201 | emerging | True |
| 5 | 6.72e-05 | 0 | 0 | 0 | 0.197 | emerging | True |
| 10 | 4.24e-05 | 0 | 0 | 0 | 0.207 | weak | True |
| 42 | 1.05e-04 | 0 | 0 | 0 | 0.197 | significant | True |
| 77 | 7.01e-05 | 0 | 0 | 0 | 0.203 | emerging | True |
| 99 | 7.64e-05 | 0 | 0 | 0 | 0.198 | emerging | True |
| 123 | 6.22e-05 | 0 | 0 | 0 | 0.195 | emerging | True |
| 999 | 9.17e-05 | 0 | 0 | 0 | 0.201 | emerging | True |

### 4.6 A_L drift 分布

所有 seed 的 A_L drift 集中在 0.195–0.207，表明 plasticity 驱动的结构变化量级非常稳定。这是 homeostasis 维持在 target=0.30 的自然结果——初始权重绝对值均值约 0.50，最终收敛到 0.30，差异约 0.20。

---

## 5. 核心发现

### 5.1 可以确认的

1. **历史分叉跨 seed 系统性存在。** 11/11 seed 均表现出非零的 A_L vs A_R 结构分叉（Δ > 0）。这不是 seed=42 的个例。

2. **因果骨架在所有 seed 上完整。** 重复历史可复现（C=A_L）、plasticity-off 顺序对称（D_L=D_R）、plasticity-off 阻止重写（D drift=0）——三项检查 11/11 全通过。

3. **分叉幅度存在 seed/topology 依赖性。** Δ 跨 seed 变化 3.2 倍（3.2e-05 到 1.0e-04），分布为 1 significant + 7 emerging + 3 weak。不同初始拓扑被历史雕刻的速度不同。

4. **A_L drift 量级跨 seed 高度一致。** 范围 0.195–0.207，说明 plasticity 驱动的总体结构变化受 homeostasis 稳定控制，不随 seed 大幅波动。

### 5.2 不能确认的

- 系统具有意识、生命、智能或自主意图
- 结构差异具有功能性意义（影响后续行为响应）
- 分叉幅度与特定拓扑特征之间的因果关系
- 效应在更大规模、更长步数、或不同参数下的行为
- 分叉是否随时间继续增长、饱和或回退

### 5.3 最严谨的表述

> **Aniva 在 v0.0.0.1 当前参数下，history-dependent structural divergence 跨 11 个 seed 稳定复现。机制可复现，分叉幅度受 seed/topology 影响。**

对应英文：

> Mechanism is reproducible. Speed is individual.

---

## 6. 限制

1. **seed 样本仍有限。** 11 个 seed 提供了比 4 个更强的统计基础，但仍不足以对分布形态做可靠推断。
2. **单次刺激模式。** 每个实验组仅含两次刺激事件（L+R）。
3. **全局稳态。** Homeostasis 为全局缩放，非 per-connection。
4. **300 units 固定规模。** 不排除更大或更小拓扑下表现不同。
5. **结构差异的功能意义未测试。** 不知道 Δ = 3e-5 和 Δ = 1e-4 在行为层面是否有可观测差异。

---

## 7. 下一步

| 优先级 | 任务 | 说明 |
|---|---|---|
| 高 | 功能影响测试 | 结构差异是否导致同一测试刺激下响应不同 |
| 高 | Δ 增长曲线 | 每 seed 的 Δ 如何随步数演化（饱和/线性/加速） |
| 中 | 更丰富的刺激协议 | 多次重复刺激、交错刺激、不同间隔 |
| 中 | 连接级分析 | 哪些连接对历史顺序敏感，哪些不敏感 |
| 低 | 更大 seed 样本 | 30-50 seed 做分布形态分析 |
| 低 | 局部稳态 | Per-connection homeostatic regulation |

---

## 8. 复现命令

### 快速 smoke test（5k 步，3 seeds，~3 分钟）

```bash
python -u -m aniva.experiments.exp5_history_bifurcation \
  --steps 5000 \
  --groups A_L A_R C D_L D_R \
  --seeds 1 2 3 \
  --homeostasis-enabled \
  --use-numba-plasticity \
  --snapshot-interval 1000 \
  --summary-json results/phase7_multiseed_5k_smoke_summary.json \
  --summary-only
```

### 正式复现（120k 步，11 seeds，~7 小时）

```bash
python -u -m aniva.experiments.exp5_history_bifurcation \
  --steps 120000 \
  --groups A_L A_R C D_L D_R \
  --seeds 1 2 3 4 5 10 42 77 99 123 999 \
  --homeostasis-enabled \
  --use-numba-plasticity \
  --snapshot-interval 30000 \
  --summary-json results/phase7_multiseed_120k_summary.json \
  --summary-only
```

---

## 附录 A: 硬件与软件环境

| 项 | 值 |
|---|---|
| OS | Windows 11 |
| Python | 3.10 |
| NumPy | 2.2.6 |
| Numba | 0.65.0rc1 |
| Backend | Numba plasticity |

## 附录 B: 相关文件

- 实验代码: `aniva/experiments/exp5_history_bifurcation.py`
- 核心引擎: `aniva/life_core.py`
- 数据: `results/phase7_multiseed_120k_summary.json`
- 数据 (CSV): `results/phase7_multiseed_120k_summary.csv`
- Phase 6 报告: `docs/phase6_history_bifurcation_report.md`
- 性能文档: `docs/performance_notes.md`
- 历史发现: `docs/phase5_phase6_findings.md`
