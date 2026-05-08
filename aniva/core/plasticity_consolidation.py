"""Phase 9D: structural consolidation — tag, capture, slow_weight.

Anti-cheat: no arm labels, no L/R knowledge, no memory of past events.
Capture signal comes from internal dynamics only (energy, trace_mass).
"""

import math
import numpy as np

# Hardcoded reference values for 9D.1 (exposed as config fields in later phases)
_CAPTURE_ENERGY_REF = 0.3
_CAPTURE_TRACE_REF = 0.03


def produce_tags(tag_cache: np.ndarray, dW_per_connection: np.ndarray) -> None:
    """Accumulate absolute dW into tag cache (unsigned tags for 9D.1 plumbing).

    Directional information is encoded in which connections get tagged,
    not in the sign of the tag value.
    """
    tag_cache += np.abs(dW_per_connection)


def decay_tags(tag_cache: np.ndarray, tau: float) -> None:
    """Apply per-step exponential decay to tags.

    tau is measured in simulation steps, matching 9C trace semantics.
    """
    decay = math.exp(-1.0 / tau)
    tag_cache *= decay


def compute_capture_signal(mean_energy: float, trace_mass: float) -> float:
    """Compute capture signal from internal dynamics only.

    capture = min(1, energy/energy_ref) * min(1, trace/trace_ref)

    No arm labels, no event indices, no memory of past events.
    Both inputs come from internal state:
      - mean_energy: average across all units' energy levels
      - trace_mass: L1 norm of the 9C event-pair trace vector
    """
    energy_component = min(1.0, mean_energy / _CAPTURE_ENERGY_REF)
    trace_component = min(1.0, trace_mass / _CAPTURE_TRACE_REF) if _CAPTURE_TRACE_REF > 0 else 1.0
    return float(energy_component * trace_component)


def apply_capture(
    tag_cache: np.ndarray,
    slow_weight_cache: np.ndarray,
    slow_weight_rate: float,
    slow_weight_max: float,
) -> float:
    """Transfer tags to slow_weight, then clamp slow_weight to [-max, +max].

    Returns the L1 norm of the slow_weight change (for ledger).
    """
    delta = slow_weight_rate * tag_cache
    slow_weight_cache += delta
    np.clip(slow_weight_cache, -slow_weight_max, slow_weight_max, out=slow_weight_cache)
    return float(np.sum(np.abs(delta)))


def compute_effective_weights(
    fast_weight_cache: np.ndarray,
    slow_weight_cache: np.ndarray,
) -> np.ndarray:
    """Compute effective weights = fast + slow, clamped to [-1, 1].

    Returns a new array; does not modify inputs.
    """
    effective = fast_weight_cache + slow_weight_cache
    np.clip(effective, -1.0, 1.0, out=effective)
    return effective
