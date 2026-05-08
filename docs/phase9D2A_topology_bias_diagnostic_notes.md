# Phase 9D.2A Topology-Bias Diagnostic Notes

> **定位：** diagnostic，不是 validation。
> 9D.2 仍保持 caveated positive，不改写成 clean pass。
> simultaneous |DI| < 0.1 阈值不修改。

---

## 1. Summary

| Candidate | What was tested | Result |
|-----------|----------------|--------|
| A | Pre-consolidation topology baseline | baseline_fast_DI = +0.0096 (near zero) — ruled out |
| B | Event-vector support asymmetry | phi_mass L=0.054, R=0.096 (R ~1.8x L) |
| C | Baseline-corrected slow_DI | corrected_DI = +0.1539 (still > 0.1) — ruled out |
| D | Swapped L/R stimulus positions | slow_DI unchanged (+0.1635 → +0.1635) — ruled out |
| Ordering | Same-step sequential vs combined | LR vs RL gap = +0.9856 — ruled out for current impl |

**All five diagnostic paths ruled out.** Simultaneous +0.1635 remains unexplained.
Next step: candidate E (shuffled/matched topology or matched mask diagnostic).

---

## 2. A/B/C: Topology Baseline, Event-Vector Support, Corrected DI

```
seed=42  unit_count=300

A (topology baseline):
  L→R connections: 946
  R→L connections: 938
  fast_LR_l1: 470.6486
  fast_RL_l1: 461.6902
  baseline_fast_DI: +0.0096

B (event-vector support):
  units: 300 (L hemi: 139, R hemi: 138)
  event_support: L=11  R=18
  phi_mass: L=0.0540  R=0.0960
  mass_ratio (L/R): 0.563
  support_ratio (L/R): 0.611

C (simultaneous arm, combined phi):
  slow_LR_l1: 2.555e-05
  slow_RL_l1: 1.837e-05
  simultaneous_slow_DI: +0.1635
  corrected_DI: +0.1539
  sign_agreement: True
  |corrected_DI| < 0.1: False

Verdict: baseline_partial
  Topology baseline (+0.0096) cannot explain +0.1635.
  Corrected DI remains well above 0.1 threshold.
  Escalate to D (swapped L/R).
```

The initial network topology is nearly symmetric (L/R connection counts and fast
weight L1 norms differ by < 2%). Baseline correction barely moves the DI needle.

Event-vector support is notably asymmetric: R phi has ~1.8× the mass and 1.6×
the unit coverage of L phi. This is a real asymmetry in how stimuli reach units,
but candidate D proves it does not drive the simultaneous caveat.

---

## 3. D: Swapped L/R Stimulus Positions

```
Original (L at -0.5, R at +0.5):
  phi_mass L=0.0540  R=0.0960
  simultaneous_slow_DI = +0.1635

Swapped (L at +0.5, R at -0.5):
  phi_mass L=0.0960  R=0.0540    ← mass ratio flipped perfectly (1.776)
  simultaneous_slow_DI = +0.1635  ← completely unchanged

  slow_LR_l1 and slow_RL_l1 values identical to 6 decimal places
  between original and swapped.

Verdict: possible_consolidation_false_positive
  slow_DI does NOT follow stimulus spatial position or phi mass.
  The bias is robust to stimulus placement.
  Escalate to ordering diagnostic (9D.2A.1).
```

The phi mass ratio flipped perfectly (0.563 → 1.776), confirming the swap worked
at the spatial level. But slow_DI is completely invariant — same value, same
per-direction L1 norms. This eliminates spatial/event-vector support asymmetry
as the primary driver of the simultaneous caveat.

---

## 4. 9D.2A.1: Same-Step Event Ordering Diagnostic

Tested three phi-application modes for simultaneous L+R events at the same step:

| Mode | slow_LR_l1 | slow_RL_l1 | slow_DI | tag_mass | updates |
|------|-----------|-----------|---------|---------|-----|
| combined | 2.56e-05 | 1.84e-05 | **+0.1635** | 1.06e-04 | 2 |
| LR order | 1.43e-04 | 7.07e-05 | **+0.3372** | 2.45e-04 | 5 |
| RL order | 3.45e-05 | 1.62e-04 | **-0.6484** | 2.45e-04 | 5 |

```
LR-RL gap: +0.9856
```

**Key findings:**

1. **Sequential same-step processing is a massive artifact risk.**
   LR order (L first → R sees L's trace) produces strong positive DI (+0.3372).
   RL order (R first → L sees R's trace) produces strong negative DI (-0.6484).
   The two orders diverge by nearly 1.0 in slow_DI space. This confirms Max's
   intuition that same-step event ordering is a critical implementation detail.

2. **Current 9D.2 simultaneous implementation uses combined-phi.**
   The step loop sums L phi + R phi and calls `apply_event_pair_phi()` once.
   This is the "combined" mode — the true simultaneous control. The sequential
   ordering artifact does NOT explain the current +0.1635 caveat.

3. **Combined mode still shows +0.1635.**
   Even after eliminating sequential processing, the simultaneous arm produces
   a directional slow_DI above the |DI| < 0.1 threshold. The source lies deeper.

**Verdict:** `ordering_artifact_confirmed` — sequential processing is a real
risk and combined-phi is the correct implementation. But the +0.1635 caveat
persists in combined mode, so same-step ordering is ruled out as the
explanation.

---

## 5. Diagnostic Decision Tree (completed)

```
baseline_fast_DI = +0.0096
    ↓
corrected_DI = +0.1539 (≥ 0.1)
    ↓ [escalate to D]
swapped L/R → slow_DI unchanged (+0.1635)
    ↓ [escalate to ordering diagnostic]
LR vs RL gap = +0.9856 → sequential artifact real
combined mode = +0.1635 → not explained by ordering
    ↓ [escalate to E]
candidate E: shuffled/matched topology mask
```

All five diagnostic paths exhausted. The simultaneous +0.1635 caveat is:

- **NOT** from initial topology asymmetry (A — baseline near zero)
- **NOT** explainable by baseline correction (C — corrected DI still > 0.1)
- **NOT** from stimulus spatial placement or phi coverage (D — swapped DI identical)
- **NOT** from same-step sequential processing (ordering — combined mode already used)

Remaining hypotheses for candidate E:
- Connection-count asymmetry in L→R vs R→L subsets
- Per-connection weight magnitude distributions within each subset
- Tag accumulation / capture distribution bias across connection groups
- Metric aggregation artifact in slow_DI computation
- Consolidation gate interaction with connection-level dynamics

---

## 6. Boundary

- 9D.2 remains caveated positive (not clean pass)
- Simultaneous threshold |DI| < 0.1 is NOT modified
- 9D.3 is NOT started
- No parameter tuning
- No mechanism formula changes
- All arm/side labels used only for offline metric grouping
