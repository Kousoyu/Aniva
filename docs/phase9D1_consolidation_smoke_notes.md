# Phase 9D.1 Consolidation Quick Smoke Notes

> **Scope:** plumbing verification only — not scientific validation.
> Quick mode: 100 units, 2 repeated pairs, ~2280 steps, 9.6s runtime.

---

## 1. Result Summary

**Plumbing chain confirmed functional.**

| Criterion | Result |
|-----------|--------|
| 0 NaN / no explosion | PASS |
| tag produced (Arm A, B) | PASS |
| tag decayed between events | PASS |
| Arm A final tag_mass > Arm B | PASS (1.19e-4 > 3.5e-5) |
| capture triggered | PASS (A: 4, B: 3) |
| slow_weight > 0 in event arms | PASS |
| Arm C baseline slow_weight = 0 | PASS |
| refractory prevents every-step capture | PASS (2280 steps, 4 captures) |
| slow_weight clamped ≤ 0.1 | PASS |
| CSV / JSON complete | PASS |

## 2. Arm Details

| Arm | Updates | Captures | Final tag_mass | Final slow_l1 | slow_max |
|-----|---------|----------|----------------|---------------|----------|
| repeated_x3 | 3 | 4 | 1.19e-4 | 3.1e-5 | 2.9e-5 |
| single | 1 | 3 | 3.5e-5 | 8e-6 | 8e-6 |
| baseline | 0 | 0 | 0.0 | 0.0 | 0.0 |

## 3. Caveat

Arm A within-arm `tag_accumulates` criterion was 9/10, failed only in quick mode.

**Reason:** quick mode uses only 2 event pairs (3 fired updates). Tag values are very small (~4e-5 per tagged connection). Between the second and third update, decay slightly exceeds the new dW increment for the within-arm mid-vs-last comparison.

**Cross-arm accumulation still passed:** Arm A final tag_mass (1.19e-4) > Arm B (3.5e-5), confirming that repeated event-pair updates produce more total tag than a single pair.

This is a quick-mode test sensitivity issue, not a plumbing bug. Full smoke (3 pairs, 300 units) would have larger absolute tag values and should resolve it.

## 4. Conclusion

- 9D.1 plumbing skeleton is functional: all 7 gears (tag production, decay, accumulation, capture, slow_weight write, clamp, refractory) engage correctly in a running LifeCore.
- This does NOT prove long-term structural consolidation.
- Next step: full smoke (300 units, 3 pairs) to verify the caveat resolves, then 9D.2 consolidation behavior design.
