# Phase 9D.1 Consolidation Full Smoke Notes

> **Scope:** plumbing verification only — not scientific validation.
> Full mode: 300 units, 3 repeated pairs, 7500 steps, 260s runtime.

---

## 1. Result Summary

**All 7 plumbing gears confirmed functional at full scale.**

| Criterion | Arm A | Arm B | Arm C |
|-----------|-------|-------|-------|
| no_nan | PASS | PASS | PASS |
| tag_produced | PASS | PASS | PASS |
| tag_decays | PASS | PASS | PASS |
| tag_accumulates | PASS | PASS | PASS |
| capture_triggered | PASS | PASS | PASS |
| slow_weight_positive | PASS | PASS | PASS |
| slow_weight_clamped | PASS | PASS | PASS |
| refractory_effective | PASS | PASS | PASS |
| baseline_slow_zero | PASS | PASS | PASS |
| effective_diverged | PASS | PASS | PASS |

## 2. Core Metrics

| Metric | Arm A (×3) | Arm B (×1) | Arm C | Ratio A/B |
|--------|-----------|-----------|-------|-----------|
| tag_mass (final) | 2.59e-4 | 3.7e-5 | 0 | 7.0× |
| n_tagged | 42 | 13 | 0 | 3.2× |
| n_captures | 11 | 6 | 0 | 1.8× |
| slow_l1 (final) | 2.53e-4 | 4.1e-5 | 0 | 6.2× |
| slow_max_abs | 4.8e-5 | 1.7e-5 | 0 | — |

All slow_weight values ≪ 0.1 clamp limit.

## 3. Quick Smoke Caveat Resolution

The quick-mode Arm A `tag_accumulates` failure (2-pair schedule, tiny tag values)
disappeared in full smoke with 3 pairs and 300 units.

## 4. Conclusion

- 9D.1 consolidation plumbing is functional at full scale.
- 7-gear chain (tag production → decay → accumulation → capture → slow_weight write → clamp → refractory) all engage correctly.
- Repeated same-order event pairs produce stronger tag and slow_weight signals than single pairs.
- No-event baseline produces zero contamination.
- This does NOT prove long-term structural consolidation as a scientific result.
- Next step: 9D.2 consolidation behavior design.
