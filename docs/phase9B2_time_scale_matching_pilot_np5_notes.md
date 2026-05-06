# Phase 9B.2 Time-Scale Matching — Pilot Notes (np5)

> 2-seed pilot: does aligning paired-pulse gap with crossing timescale rescue order-specific structural divergence?

## Experiment Setup

- **Branch**: `phase9-temporal-plasticity`
- **Prior commit**: `9a79c84` (dynamic pair scheduling smoke)
- **Seeds**: 42, 999
- **Gaps**: 80, 500, 1000, 1500
- **Num pairs**: 5
- **Modes**: OFF, activity, onset, threshold_crossing
- **Arms**: L_then_R, R_then_L, simultaneous, separated_control
- **Scheduling**: dynamic `pair_interval = gap + pulse_dur + rest_window(500)`

## Engineering Status

- 128 arm-runs completed (2 seeds × 4 gaps × 4 modes × 4 arms)
- Scheduling inherited smoke 16/16 OK — event_count_L = event_count_R = num_pairs for all arms
- CSV/JSON were produced on ECS and verified (128 data rows, correct schema)
- Key pilot metrics extracted from logs (all |diff| values, crossing diagnostics captured above)
- Raw CSV artifacts are pending retrieval from ECS and are NOT included in this commit
- ECS shut down after completion

## Results

### Threshold-crossing |asym_diff| by gap

| Gap | Seed 42 |diff|| Seed 999 |diff|| xing/unit (42) | xing/unit (999) |
|-----|---------|----------|---------|-----------|-----------------|------------------|
| 80  | 3.60e-06 | 5.22e-06 | 2.7  | 3.1  |
| 500 | 2.44e-06 | 2.14e-06 | 3.9  | 4.6  |
| 1000| 3.98e-06 | 8.61e-07 | 5.9  | 6.6  |
| 1500| 2.47e-06 | 4.14e-06 | 7.8  | 8.9  |

OFF baseline range for reference: ~1e-6 to 8e-06 across all gaps.

### Crossing diagnostics

- `xing/unit` increased ~3x from gap=80 to gap=1500 (healthy)
- `frac_steps_with_crossing` stable at 17-21%
- `bal_LR` and `Q4/Q1` well-behaved, no anomalies
- Crossing detection mechanically sound at all gap values

## Conclusion

**No clear pilot trend.** Time-scale matching did not rescue threshold-crossing eligibility in this 2-seed pilot. Increasing paired-pulse gap reliably increased crossing opportunities (xing/unit grew 3x), but did not produce order-specific structural divergence — |asym_diff| remained at OFF baseline across all four gap values.

This is NOT a final verdict against all threshold-crossing variants. It is a strong negative pilot that, combined with the 9B.1 4-seed negative result, indicates that the current form of threshold-crossing eligibility (signed-delta with refractory-gated crossing detection) does not capture L→R vs R→L order information under the tested parameters.

## Interpretation

- **9B.1** showed threshold-crossing worked mechanically but failed at 80-step gap. Root cause identified as time-scale mismatch (mean inter-crossing interval ~1100-1500 steps vs 80-step gap).
- **9B.2 pilot** tested whether extending gap into the crossing timescale regime would help. It did not, under current rule and parameters.
- The crossing mechanism detects events reliably; the failure is in converting temporal-event information into directional structural bias.

## Next Direction (for Phase 9C)

Do not run 4-seed full 9B.2 automatically. Phase 9C should consider a fundamentally different temporal mechanism. Candidates include:

- Explicit event-pair trace (store temporal adjacency, not just crossing count)
- STDP-like pair memory (pre-post interval matters)
- Causal event buffer (maintain a short history of which unit fired when)
- Phase-based timing signal (oscillatory eligibility window)

Keep Aniva at substrate level. Do not add LLM, reward, agent, goal, emotion, personality, or language interface.
