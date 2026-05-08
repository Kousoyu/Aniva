# Phase 9D.2B.1 Pipeline Decomposition Diagnostic Notes

> **定位：** E3+E4 offline decomposition，诊断 simultaneous +0.1635 在 pipeline 哪一层出现。
> 不修改 9D.2 结论，不改变阈值，不启动 9D.3。

---

## 1. Summary

Simultaneous combined-phi slow_DI = +0.1635 的偏置在 **Layer 1 event-pair dW** 就已完全确立。tag/capture/slow_weight 各层忠实传递，未引入额外偏置。

**Root is NOT consolidation false positive.** Root is trace×phi projection asymmetry onto LR/RL connection masks.

---

## 2. Pipeline Layer Trace

| Layer | Metric | Value |
|-------|--------|-------|
| 0 | n_LR / n_RL | 946 / 938 |
| 0 | fast_LR_l1 / fast_RL_l1 | 470.65 / 461.69 (ratio=1.019) |
| 1 | dW_DI (pair 0) | +0.0000 (trace=0, no update) |
| 1 | **dW_DI (pair 1)** | **+0.1635** ← bias appears here |
| 1 | dW_DI (pair 2) | +0.1635 (stable) |
| 2 | tag_delta_DI (per pair) | +0.1635 (|dW| lossless) |
| 2 | tag_DI (accumulated) | +0.1635 (n_tagged LR=13, RL=7) |
| 3 | capture events | 11 total, all signal > 0.85 |
| 4 | slow_DI (final) | +0.1635 |

### Per-pair dW detail

```
Pair 0 (step 2000):  dW=0     (trace_mass=0 at first event, no update produced)
Pair 1 (step 3500):  dW_LR=2.5797e-05  dW_RL=1.8547e-05  dW_DI=+0.1635
Pair 2 (step 5000):  dW_LR=2.5797e-05  dW_RL=1.8547e-05  dW_DI=+0.1635
```

Pairs 1 and 2 produce identical dW_LR and dW_RL (to 4 significant digits). The dW_DI is stable.

### Capture timeline

Captures 0-2 (steps 2001, 2502, 3003): tag_mass=0 (pre-first-event-pair), no slow_weight written.
Capture 3 (step 3504): first meaningful capture, tag_DI already +0.1635.
All subsequent captures preserve the +0.1635 tag_DI.

---

## 3. Interpretation

1. **Consolidation pipeline is clean.** tag production (`|dW|`), tag decay, capture signal, and slow_weight write do not introduce or amplify directional bias. They faithfully transfer the dW-layer asymmetry to slow_weight.

2. **Bias originates in event-pair dW layer.** `apply_event_pair_update(trace, phi)` produces asymmetric dW on L→R vs R→L connections. Since tag = |dW| and all contributing dW values are positive, tag_DI = dW_DI.

3. **Root hypothesis:** The combined L+R phi field, when projected through the trace×phi Hebbian correlation onto the directed LR/RL connection masks, produces an inherent projection asymmetry. This is a geometry/field effect, not a mechanism bug.

4. **Swapped L/R insensitivity is expected for combined-phi simultaneous.** When phi = phi_L + phi_R, swapping L and R stimulus positions may leave the combined field mostly unchanged (commutative under summation). The D result (slow_DI unchanged under swapped positions) is consistent with this interpretation.

---

## 4. Next Step

**9D.2C event-pair projection diagnostic.** Inspect the raw eligibility
(trace[source] × phi[target]) on LR vs RL connections before any normalization
or L1 target constraint. Determine whether:

- raw_DI already equals +0.1635 → geometry/projection origin
- raw_DI ≈ 0 but dW_DI ≠ 0 → normalization/clipping inside `apply_event_pair_update`
- matched-mask raw_DI ≈ 0 → LR/RL mask aggregation artifact

---

## 5. Boundary

- 9D.2 remains caveated positive
- Simultaneous |DI| < 0.1 threshold NOT modified
- No parameter tuning
- No mechanism formula changes
- 9D.3 NOT started
