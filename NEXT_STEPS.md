# Aniva — 下一步计划

> 最后更新：2026-05-01 (Phase 3.19)
> 状态：v0.0.0.1 核心动力学搭建完成，默认参数已校准

---

## 已完成的里程碑

| Phase | 内容 | 状态 |
|-------|------|------|
| 3.5 ~ 3.9 | Unit, Connection, Dynamics, Noise, Energy, Leak, Trace, Threshold | ✅ |
| 3.10 ~ 3.11 | 能量平衡修正 + energy gate | ✅ |
| 3.14 | soft threshold (sigmoid) | ✅ |
| 3.16 | 网络边界诊断 (connection_density, exc_inh_ratio) | ✅ |
| 3.17 | synaptic response saturation (符号分离) | ✅ |
| 3.18 | E/I 平衡细扫 + 多 seed 验证 | ✅ |
| 3.19 | 默认参数校准 | ✅ |

详细记录见 `EXPERIMENT_LOG.md`。

---

## 当前默认参数

```python
unit_count = 300
connection_density = 0.05
exc_inh_ratio = 0.50
synaptic_strength = 0.30
threshold_softness = 0.02
```

默认 free-run 出现稳定动态平衡：预热 → 点火 → 能量暂降 → 恢复 → 稳态（mean_act ~0.36, energy ~0.37, hard_active ~48%）。

---

## 尚未实现

| 机制 | 优先级 |
|------|--------|
| Plasticity (连接变化) | 待定 |
| 局部场效应 | 待定 |
| 弥散调节 | 待定 |
| Environment (刺激源) | 待定 |
| Visualizer (可视化) | 待定 |

---

## 历史记录（2026-04-25 设计讨论）

以下是首次设计讨论时留下的计划，已完成的内容已归档到 `EXPERIMENT_LOG.md`。

> 第一步：搭代码骨架 ✅
> 第二步：实现最小可运行核心 ✅
> 第三步：跑第一个实验 ✅
> 第四步：可视化（待定）

需要讨论的问题：
1. 三种影响方式（突触/局部场/弥散）的相对强度怎么调
2. 弥散调节的具体机制
3. 可视化用什么库
4. 是否要支持保存和加载生命核的状态
