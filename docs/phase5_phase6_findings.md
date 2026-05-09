# Phase 5–6 Findings: History-Dependent Structural Bifurcation

## 1. Core Question

**Can different histories reshape the same initial dynamical system into
measurably different structures?**

This is the foundational question for Aniva's central premise:
that history is not a log written alongside a static system, but a force
that irreversibly deforms the system itself.

## 2. Key Result

Under homeostatic maintenance, identical initial systems exposed to
different stimulus orders develop measurable structural divergence:

- Same seed + same history → bit-identical structure
- Same seed + reversed history → structural bifurcation
- Plasticity off → no structural rewriting

## 3. Phase 5: Causal Chain (seed=42, 120k steps)

| Comparison | Δ_weight_L1 | Meaning |
|---|---:|---|
| A_L vs C | 0.000000 | Same history is deterministic |
| A_L vs A_R | 0.000105 | Different order → significant bifurcation |
| A_L vs B | 0.000094 | Stimulus history vs no-stimulus baseline |
| D drift | 0.000000 | Plasticity off prevents structural rewriting |
| A_L drift | 0.197002 | Plasticity on enables structural change |

**Conclusion:**

> History order is a causal source of structural divergence.

The chain is closed: same seed + same events → identical result.
Same seed + reversed events → different result. Plasticity off → no
structural rewriting. The effect goes through plasticity, not through
residual dynamics.

## 4. Homeostasis Finding

Without homeostatic maintenance, Hebbian decay dominates Hebbian
learning at roughly 30:1, causing exponential weight collapse:

| Experiment | Steps | Homeostasis | Result |
|---|---|---|---|
| Baseline | 20,000 | off | Alive, dynamics divergence only |
| P1 (rate=0.0005) | 20,000 | off | Dead by 20k (decay overwhelms) |
| T1 (rate=0.0001) | 50,000 | off | Collapsed ~step 48,000 |
| H0 | 50,000 | on | Alive, Δ_L1 = 0.000060 |
| H1 | 100,000 | on | Alive, Δ_L1 = 0.000093 |
| H2 | 120,000 | on | Alive, Δ_L1 = 0.000105 |

The collapse threshold is approximately `weight_abs_mean < 0.15`, at
which point hard_active ratio drops to zero and the system goes silent.

Global homeostatic maintenance locks `weight_abs_mean` at the target
(0.30), preserving weight signs and preventing collapse.

**Δ_L1 growth trajectory (seed=42):**

```
20k:  0.000041  (dynamics only)
50k:  0.000060  (+46%)
100k: 0.000093  (2.27× baseline)
120k: 0.000105  (crosses 1e-4 significance threshold)
```

## 5. Phase 6: Multi-Seed Validation

| Seed | Δ_weight_L1 | Verdict | C vs A_L | D_L vs D_R | Causal Skeleton |
|---:|---:|---|---:|---:|---|
| 42 | 0.000105 | significant | 0.000000 | 0.000000 | intact |
| 999 | 0.000092 | emerging | 0.000000 | 0.000000 | intact |
| 77 | 0.000070 | emerging | 0.000000 | 0.000000 | intact |
| 123 | 0.000062 | emerging | 0.000000 | 0.000000 | intact |

**Verdict tiers:** significant (>1e-4) / emerging (5e-5 ~ 1e-4) / weak (<5e-5)

Across four seeds, the causal skeleton reproduced in every run. No seed
fell into the weak bifurcation range. All seeds showed Δ_weight_L1 > 5e-5.

All four seeds satisfy the causal skeleton:

- `C vs A_L = 0` — same history is deterministic
- `D_L vs D_R = 0` — plasticity-off order is irrelevant
- `D_L drift = 0, A_L drift >> 0` — plasticity is the causal pathway
- `causal_skeleton_intact = True`

**Conclusion:**

> The causal mechanism is reproducible across seeds. Bifurcation
> magnitude varies by seed/topology. No seed showed weak or absent
> structural divergence.

In short:

> **Mechanism is reproducible. Speed is individual.**

This is not a failure of any individual seed. It is the first sign of a
property Aniva needs to have: different initial topologies produce
different developmental trajectories.

## 6. Interpretation

Aniva has not demonstrated consciousness, agency, or full digital life.

It has demonstrated a lower-level condition required for
digital-life-like continuity:

> **History can reshape structure.**

This supports the project's core principle:

> Memory is not a field. Memory is structural deformation caused by history.

The system does not "store" a history log. The system *becomes different*
because of what it experienced.

## 7. Current Status

**Confirmed:**

- Event-centric history representation (Stimulus / StimulusEvent separation)
- Plasticity-driven structural rewriting (Hebbian + decay + energy gate)
- Homeostatic survival beyond collapse point (global weight scaling)
- Deterministic repeatability (same seed + same events = same structure)
- Plasticity-off order symmetry (D_L = D_R, order irrelevant without plasticity)
- Plasticity causality (structural change requires plasticity)
- Seed-dependent bifurcation speed (mechanism stable, magnitude varies)

**Not yet confirmed:**

- Long-term autobiographical memory across multiple episodes
- Agency / intrinsic drive
- Closed-loop world coupling
- Local (per-connection) homeostasis
- Multi-episode developmental history
- Performance at scale (300 units × 120k steps = ~18 min/group)

## 8. Next Steps

1. Run additional seeds (999) to widen the diversity sample.
2. Characterize local homeostasis after global homeostasis is understood.
3. Add repeated episode protocols (L-R-L, R-L-R alternations).
4. Add richer event streams with varying intervals.
5. Add performance optimization before scaling experiments further.
6. Maintain research log as new mechanisms are added.
