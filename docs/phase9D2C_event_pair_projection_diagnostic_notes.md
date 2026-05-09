# Phase 9D.2C Event-Pair Projection Diagnostic Notes

> **定位：** offline diagnostic，追 simultaneous +0.1635 在 event-pair dW 层的根因。
> 不改机制、不调参、不启动 9D.3。

---

## 1. Summary

**raw_DI = dW_DI = +0.1635** (diff = -2.5e-09, floating-point noise).

The L1 normalization in `apply_event_pair_update` is DI-invariant. The +0.1635
bias exists at the raw eligibility entry point (trace[src] × phi[tgt]) and is
faithfully propagated through tag, capture, and slow_weight.

**Root cause: combined L+R phi field projected through trace×phi onto directed
LR/RL connection topology produces an inherent geometric asymmetry.**

---

## 2. Core Metrics

| Metric | Pair 1 (step 3500) | Pair 2 (step 5000) |
|--------|-------------------|-------------------|
| trace_mass | 3.347e-02 | 4.094e-02 |
| phi_mass | 1.500e-01 | 1.500e-01 |
| raw_LR_l1 | 8.006e-05 | 9.792e-05 |
| raw_RL_l1 | 5.756e-05 | 7.040e-05 |
| **raw_DI** | **+0.1635** | **+0.1635** |
| dW_LR_l1 | 2.580e-05 | 2.580e-05 |
| dW_RL_l1 | 1.855e-05 | 1.855e-05 |
| **dW_DI** | **+0.1635** | **+0.1635** |
| raw_DI − dW_DI | −2.50e-09 | −2.72e-09 |

dW_LR_l1 and dW_RL_l1 are identical across pairs 1 and 2 (to 4 sig figs),
because the L1 normalization produces a fixed dW magnitude regardless of raw
eligibility mass. dW_DI is preserved because the scaling factor cancels in the
DI ratio.

---

## 3. Normalization Diagnostics

All five DI variants remain in [+0.15, +0.17] — none approach zero:

| Normalization | Value | Implication |
|---------------|-------|-------------|
| raw_DI | **+0.1635** | baseline |
| raw_DI_per_conn | **+0.1594** | not a connection-count artifact |
| raw_DI_norm (by init weight mass) | **+0.1541** | not an initial-weight-mass artifact |
| raw_DI_matched (n=938 matched) | **+0.1635** | not a mask-distribution artifact |

Matching method: greedy nearest-neighbor on |initial_weight|, pairing each
L→R connection with the closest-weight R→L connection. 938 matched pairs.

Matched mask DI is identical to full mask DI because matching by initial weight
does not change the source/target hemisphere membership of connections —
the trace/phi projection geometry is invariant under weight-based matching.

---

## 4. Geometric Decomposition

### Trace × Phi Projection

```
L→R connection:  src in L-hemi, tgt in R-hemi
  trace_src_LR_l1 = 0.094  (trace L1 at L-hemi source units)
  phi_tgt_LR_l1   = 0.653  (phi L1 at R-hemi target units)
  product         = 0.0617

R→L connection:  src in R-hemi, tgt in L-hemi
  trace_src_RL_l1 = 0.140  (trace L1 at R-hemi source units)
  phi_tgt_RL_l1   = 0.310  (phi L1 at L-hemi target units)
  product         = 0.0435

LR / RL = 1.42
```

### Hemisphere Mass Distribution

| Component | L-hemi | R-hemi | Ratio (R/L) |
|-----------|--------|--------|-------------|
| phi mass | 0.0540 | 0.0960 | **1.78×** |
| trace mass | 0.0121 | 0.0214 | **1.78×** |
| phi_tgt (per-conn mask) | 0.310 | 0.653 | **2.11×** |
| trace_src (per-conn mask) | 0.094 | 0.140 | **1.48×** |

### Why LR > RL

- phi_R mass ≈ 1.78× phi_L mass (R stimulus at +0.5 hits more units)
- All past traces accumulate combined L+R phi → trace_R_mass ≈ 1.78× trace_L_mass
- L→R uses trace_L(src) × phi_R(tgt) → small × large
- R→L uses trace_R(src) × phi_L(tgt) → large × small
- phi asymmetry (2.11×) outweighs trace asymmetry (0.67×)
- L→R product > R→L product → raw_DI > 0

The asymmetry is multiplicative: even though trace has more mass on the R side
(which should favor R→L), the phi vector at targets has an even larger R/L
ratio, and the target-phi asymmetry dominates the source-trace asymmetry in
the element-wise product.

---

## 5. Full Diagnostic Chain

```
9D.2A A/B/C/D/ordering:
  baseline topology   ✗ ruled out
  phi coverage        ✗ ruled out (D: swapped invariant)
  baseline correction ✗ ruled out
  spatial position    ✗ ruled out
  sequential ordering ✗ ruled out (combined-phi already used)

9D.2B.1 decomposition:
  dW_DI = +0.1635 at Layer 1
  tag/capture/slow are lossless propagators
  root is NOT in consolidation

9D.2C projection:
  raw_DI = dW_DI = +0.1635
  L1 normalization is DI-invariant
  all normalizations fail to zero the bias
  root = trace×phi geometry × directed topology
```

---

## 6. Impact on 9D.2

- **9D.2 remains caveated positive.**
- Simultaneous control failed the |DI| < 0.1 threshold for a real geometric
  reason, not a mechanism-level false positive.
- The threshold is NOT being relaxed post-hoc.
- 9D.2 is NOT being rewritten as clean pass.
- Future 9D.3 should include geometry-aware controls:
  - raw projection baseline as a covariate
  - corrected slow_DI (slow_DI − baseline_projection_DI)
  - simultaneous control criterion that accounts for phi-mass asymmetry

---

## 7. Boundary

- No mechanism changes
- No parameter tuning
- No threshold modification
- 9D.3 NOT started
- All analysis is offline diagnostic
