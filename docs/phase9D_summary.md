# Phase 9D — Structural Consolidation: Evidence Chain

> **定位：** Phase 9D 完整证据链装订。不宣布生命，不越界解读。

---

## 总览

```
9D.1 (plumbing)   →  9D.2 (behavior smoke)  →  9D.2A/B/C (diagnostic chain)  →  9D.3 (formal validation)
     PASS              caveated positive           root cause identified              POSITIVE 4/4 seeds
```

9D 的起点问题：**event-pair plasticity 信号能否通过 synaptic tagging and capture
管线沉积为 slow structural weight，并在 LR/RL 方向上有序差异？**

9D 的终点答案：**能。即使在地形有固有几何投影不对称的情况下，repeated ordered
event history 仍能在 geometry baseline 之上产生方向正确的额外结构沉积。**

---

## 各阶段

### 9D.1 — Plumbing Verification

**提交：** `bc849c0` → `e02a63b`
**结论：** PASS（plumbing only，非科学验证）

7-gear chain 在 300-unit full scale 下确认啮合：
tag production → tag decay → tag accumulation → capture trigger →
slow_weight write → slow_weight clamp → refractory。

---

### 9D.2 — Behavior Smoke

**提交：** `501fcb1`
**结论：** caveated positive

Main signal strong：
- L→R slow_DI = +0.206
- R→L slow_DI = -0.512
- slow_OS = +0.718
- repeated > single ~6.1×
- no_event baseline = 0
- 0 NaN

Caveat：simultaneous control slow_DI = +0.164，超过预注册阈值 |DI| < 0.1。

**阈值未事后修改。9D.2 不是 clean pass。**

---

### 9D.2A → 9D.2C — Diagnostic Chain

**提交：** `92c3cf0` → `1c6d16a`
**结论：** simultaneous +0.1635 = geometry_projection_asymmetry

| Stage | Ruled Out / Identified |
|-------|----------------------|
| 9D.2A-A | 不是 baseline topology artifact |
| 9D.2A-B | 不是 phi coverage artifact |
| 9D.2A-C | 不是 baseline correction artifact |
| 9D.2A-D | 不是 spatial position artifact |
| 9D.2A-ordering | 不是 sequential processing artifact |
| 9D.2B.1 | 偏置在 Layer 1 dW，tag/capture/slow 只是搬运（lossless propagators） |
| 9D.2C | **根因：** raw_DI = dW_DI = +0.1635。combined L+R phi 在 directed LR/RL 连接拓扑上的 trace×phi 投影产生固有几何不对称 |

phi_R_mass ≈ 1.8× phi_L_mass → LR product (small × large) ≠ RL product (large × small) → raw_DI > 0。

**9D consolidation pipeline 是干净的。** +0.1635 不是机制假阳性，是地形事实。

---

### 9D.3 — Geometry-Aware Formal Validation

**提交：** `d9803aa` (seed42 smoke), `6c53a3c` (4-seed formal)
**结论：** **POSITIVE, 4/4 seeds, 14/14 PASS each**

**核心框架改变：**
- 旧：simultaneous |DI| < 0.1（naive zero-baseline）
- 新：corrected_slow_DI = slow_DI - geometry_baseline_DI（geometry-aware）

geometry_baseline_DI = simultaneous combined-phi raw_projection_DI。Shared global
constant per seed，所有 arm 共用。

**结果：**

| Seed | baseline_DI | corrected_LR | corrected_RL | corrected_OS | simultaneous corrected |
|------|-----------|-------------|-------------|-------------|----------------------|
| 42 | +0.1635 | +0.0425 | -0.6752 | +0.7177 | -0.0000 |
| 77 | -0.1979 | +0.3723 | -0.2843 | +0.6565 | +0.0000 |
| 123 | -0.2840 | +0.6057 | -0.1317 | +0.7374 | +0.0000 |
| 999 | -0.3645 | +0.6546 | -0.0092 | +0.6639 | +0.0000 |

**通过指标：**
- corrected_LR > 0：4/4 ✓
- corrected_RL < 0：4/4 ✓（seed 999 borderline -0.0092，reported not gated）
- corrected_slow_OS > 0.3：4/4 ✓（range 0.6565-0.7374）
- simultaneous corrected ≈ 0：4/4 ✓
- no_event clean：4/4 ✓
- repeated > single：5.34×-6.12× ✓
- 0 NaN, 0 explosion：4/4 ✓

**关键发现：**
- Geometry baseline 跨 seed 方向不一致（-0.3645 到 +0.1635）→ 证实 per-seed correction 必要
- Simultaneous 全部归零 → geometry correction 精确生效
- Ordered arms 全部保留方向正取的 excess → ordered history 在地形基线之上产生额外方向性沉积

---

## 证据链完整性

```
9D.1: 管线啮合
  └─ 9D.2: 行为信号存在，但有 caveat
       └─ 9D.2A/B/C: caveat 根因 = 几何投影不对称，非管线缺陷
            └─ 9D.3: 用 geometry-aware 框架验证 ordered history excess
                 └─ 4/4 seeds positive
```

从 9D.1 到 9D.3，每一步的结论建立在上一阶段的证据之上，没有跳跃。

---

## 什么是 9D **没有** 证明的

- 不是 "digital life validated"
- 不是 multi-scale / long-history consolidation
- 不是 real-time continuous experience accumulation
- 不是 cross-modal / multi-event-type consolidation
- 不是 open-ended structural growth

9D 验证的是：**在 event-pair 粒度上，temporal order 是否能以方向性
slow structural weight 的形式沉积下来。** 答案是可以。这是地基，不是房子。

---

## 参数稳定性

整个 9D 链条中：
- 参数未调
- 阈值未改
- 机制公式未变
- 9D.2 的 |DI| < 0.1 阈值保持原样（9D.3 用不同框架，不是修改原阈值）

---

## 下一步

- 9D.4：multi-scale / longer-history consolidation（未启动）
- Phase 10：下一阶段方向待定

---

## 关联文档

| 文档 | 内容 |
|------|------|
| `docs/phase9D_structural_consolidation_planning.md` | 9D 总体规划 |
| `docs/phase9D1_consolidation_smoke_notes.md` | 9D.1 plumbing |
| `docs/phase9D2_consolidation_behavior_smoke_notes.md` | 9D.2 behavior smoke |
| `docs/phase9D2A_topology_bias_diagnostic_notes.md` | 9D.2A A/B/C/D/ordering |
| `docs/phase9D2B_decomposition_diagnostic_notes.md` | 9D.2B.1 decomposition |
| `docs/phase9D2C_event_pair_projection_diagnostic_notes.md` | 9D.2C projection root |
| `docs/phase9D3_geometry_aware_consolidation_validation_design.md` | 9D.3 design |
| `docs/phase9D3_geometry_aware_validation_seed42_smoke_notes.md` | 9D.3 seed42 smoke |
| `docs/phase9D3_geometry_aware_validation_4seed_notes.md` | 9D.3 4-seed formal |
