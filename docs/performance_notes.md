# Performance Notes — Aniva LifeCore

## Current State (Phase 6.5)

### Hardware Reference

All benchmarks below measured on:
- Windows 11, Python 3.10
- NumPy 2.2.6
- Numba 0.65.0rc1 / llvmlite 0.47.0 (optional, RC versions)

### LifeCore step() Performance

**Default configuration (300 units, ~4485 connections, homeostasis on, plasticity on):**

| Backend | steps/s | ms/step | Note |
|---|---|---|---|
| Scalar (default) | ~130 | ~7.7 | Pure Python plasticity loop |
| Numba (optional) | ~520 | ~1.9 | ~4x overall speedup |

### Plasticity Kernel Performance

Isolated plasticity call on 4485 connections:

| Path | ms/call | Speedup |
|---|---|---|
| Scalar `apply_plasticity` | 7.01 | 1x |
| Numba `apply_plasticity_numba` | 0.08 | **89x** |

### cProfile Hotspots (scalar path, 500 steps)

```
apply_plasticity:  7.06s (84%)  ← dominant
  _output_strength:  3.06s
  math.exp:          0.33s
  builtins.min/max:  1.78s
_sync_weight_cache:  0.18s (2%)
synaptic input:      0.10s (1%)
per-unit updates:    0.16s (2%)
homeostasis:         0.54s (6%)
```

## Optimization History

### Phase 6.5A: Synaptic input vectorization

Replaced Python for-loop over connections with NumPy vectorized ops:
- Batch sigmoid gate, batch effective output, `np.bincount` accumulation
- Result: synaptic input from ~94% of step time to ~1%
- Overall: 128 → 145 steps/s (+13%)

### Phase 6.5B: Array-backed LifeCore state

Converted `dict[int, Unit]` to canonical NumPy arrays:
- `_activations`, `_energies`, `_thresholds`, `_traces`, `_positions`, `_time_constants`
- `_UnitProxy` backward-compat layer for external code
- `apply_plasticity` now accepts arrays directly (no proxy/dict overhead in hot path)
- Result: no regression, foundation for future vectorization

### Phase 6.5C: Numba plasticity backend (optional)

`@njit`-compiled plasticity kernel:
- Eliminates Python interpreter overhead on per-connection loop
- Bit-identical to scalar path (`np.allclose` at rtol=1e-12)
- Gated behind `AnivaConfig.use_numba_plasticity=False` (default off)
- Gracefully degrades if Numba not installed
- Overall: 130 → 520 steps/s (~4x)

## Numba Backend Design

```
Default: OFF (use_numba_plasticity=False)

When enabled AND Numba available:
  _weight_cache → apply_plasticity_numba (in-place) 
  → sync to Connection.weight 
  → homeostasis (reads Connection.weight) 
  → sync back to _weight_cache

When disabled OR Numba unavailable:
  apply_plasticity (scalar, reads arrays, writes Connection.weight)
  → homeostasis
  → sync to _weight_cache
```

## Current Limitations

- Numba dependency is NOT in requirements.txt (RC versions, installation fragile)
- Plasticity is still the dominant bottleneck at 84% of scalar step time
- Per-unit update loop not yet vectorized (noise/leak/energy/trace)
- No parallel seed runner for multi-seed experiments
- No summary aggregation tool

## Safety Guardrails

Performance changes must not alter experimental semantics:

1. Same seed + same history → same structure (C vs A_L = 0)
2. Same seed + reversed history → different structure (A_L vs A_R > 0)
3. Plasticity off → order irrelevant (D_L vs D_R = 0)
4. Plasticity on → causal pathway for structural change (A_L drift >> D_L drift)

Every performance change is validated against these guardrails via exp5 regression.
