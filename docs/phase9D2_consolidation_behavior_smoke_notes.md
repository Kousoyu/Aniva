# Phase 9D.2 Consolidation Behavior Smoke Notes

> **Result:** Caveated positive — strong directional consolidation pattern,
> one simultaneous-control topology-bias caveat.
> **Scope:** behavior-level smoke / pilot, not formal validation.

---

## 1. Summary

| Criterion | Result |
|-----------|--------|
| 6 arms completed | PASS |
| 0 NaN / no explosion | PASS |
| repeated > single (L→R) | PASS (6.1×) |
| repeated > single (R→L) | PASS (6.1×) |
| L→R repeated slow_DI ≥ 0 | PASS (+0.206) |
| R→L repeated slow_DI ≤ 0 | PASS (-0.512) |
| slow_OS positive | PASS (+0.718) |
| no_event baseline clean | PASS (slow_l1 = 0) |
| simultaneous near-zero | **FAIL** (+0.164, threshold \|DI\| < 0.1) |
| slow_max clamp ok | PASS |

9/10 success criteria passed. One control-arm criterion failed.

## 2. Core Metrics

| Arm | slow_l1 | slow_LR | slow_RL | slow_DI | captures | tag_mass |
|-----|---------|---------|---------|---------|----------|----------|
| L→R repeated | 2.53e-4 | 1.21e-4 | 7.97e-5 | **+0.206** | 11 | 2.59e-4 |
| R→L repeated | 2.53e-4 | 4.64e-5 | 1.44e-4 | **-0.512** | 11 | 2.59e-4 |
| L→R single | 4.13e-5 | 4.13e-5 | 0 | +1.000 | 6 | 3.68e-5 |
| R→L single | 4.13e-5 | 0 | 4.13e-5 | -1.000 | 6 | 3.68e-5 |
| simultaneous | 9.91e-5 | 2.56e-5 | 1.84e-5 | **+0.164** | 11 | 1.06e-4 |
| no_event | 0 | 0 | 0 | 0 | 0 | 0 |

slow_OS = LTR_DI - RTL_DI = **+0.718**

## 3. Directional Pattern

Ordered arms show clear, opposite slow_DI signs matching event order:

```
L→R repeated:  slow_LR > slow_RL  →  slow_DI = +0.206
R→L repeated:  slow_RL > slow_LR  →  slow_DI = -0.512
```

Single-pair arms show perfect directional specificity:

```
L→R single:  slow_RL = 0  →  slow_DI = +1.000
R→L single:  slow_LR = 0  →  slow_DI = -1.000
```

Repeated arms produce ~6.1× more total slow_weight than single-pair arms.

## 4. Simultaneous Control Caveat

The simultaneous arm's slow_DI = +0.164 exceeds the pre-registered near-zero
threshold of |DI| < 0.1.

**Interpretation:** This is likely a network topology baseline bias, not a
mechanism-level false positive. Evidence:
- +0.164 is smaller than L→R repeated's +0.206 (same direction)
- +0.164 is substantially smaller than |R→L repeated| = 0.512 (opposite direction)
- Simultaneous events carry no order information, so the bias must come from
  asymmetric L→R vs R→L connection topology or weight distributions
- No-event baseline is clean (slow_l1 = 0), confirming capture requires events

**The threshold is NOT being relaxed post-hoc.** This is recorded as a caveat
to be investigated in a follow-up topology-bias diagnostic (9D.2A).

## 5. Runtime

764s (12.7 min), local. Exceeded the initial 8.7 min estimate, likely due to
the additional directional metric computation per snapshot.

## 6. Conclusion

- 9D.2 behavior smoke is NOT a clean pass.
- It IS a caveated positive: the main directional consolidation pattern is
  strong (slow_OS = +0.718) and the ordered arms show opposite slow_DI signs
  matching event order.
- One control-arm criterion (simultaneous_near_zero) failed at the pre-registered
  threshold. This is documented, not threshold-adjusted.
- Next step: 9D.2A topology-bias diagnostic design, before 9D.3 pilot.
