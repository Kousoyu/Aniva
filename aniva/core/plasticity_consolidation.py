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


def compute_capture_diagnostics(
    tag_cache: np.ndarray,
    event_trace: np.ndarray,
    energies: np.ndarray,
    source_indices: np.ndarray,
    target_indices: np.ndarray,
) -> dict:
    """Read-only context metrics at capture time (10C.1 instrumentation).

    Does NOT affect capture_signal, gate logic, or slow_weight transfer.
    """
    tag_mass = float(np.sum(tag_cache))
    abs_trace = np.abs(event_trace)
    trace_mass = float(np.sum(abs_trace))

    # tag-trace alignment: cosine(tag_cache, projected_trace)
    if tag_mass > 0.0 and trace_mass > 0.0:
        projected_trace = abs_trace[source_indices] * abs_trace[target_indices]
        pt_norm = float(np.linalg.norm(projected_trace))
        tag_norm = float(np.linalg.norm(tag_cache))
        if pt_norm > 0.0 and tag_norm > 0.0:
            tag_trace_alignment = float(
                np.dot(tag_cache, projected_trace) / (tag_norm * pt_norm)
            )
        else:
            tag_trace_alignment = 0.0
    else:
        tag_trace_alignment = 0.0

    # tag-weighted local energy
    if tag_mass > 0.0:
        local_energy = 0.5 * (energies[source_indices] + energies[target_indices])
        tag_weighted_energy = float(np.sum(tag_cache * local_energy) / tag_mass)
    else:
        tag_weighted_energy = 0.0

    # tag concentration (HHI)
    if tag_mass > 0.0:
        p_tag = tag_cache / tag_mass
        tag_concentration = float(np.sum(p_tag ** 2))
        tag_effective_support = 1.0 / tag_concentration if tag_concentration > 0.0 else 0.0
    else:
        tag_concentration = 0.0
        tag_effective_support = 0.0

    # trace concentration (HHI)
    if trace_mass > 0.0:
        p_trace = abs_trace / trace_mass
        trace_concentration = float(np.sum(p_trace ** 2))
        trace_effective_support = 1.0 / trace_concentration if trace_concentration > 0.0 else 0.0
    else:
        trace_concentration = 0.0
        trace_effective_support = 0.0

    return {
        "tag_trace_alignment": tag_trace_alignment,
        "tag_weighted_energy": tag_weighted_energy,
        "tag_concentration": tag_concentration,
        "tag_effective_support": tag_effective_support,
        "trace_concentration": trace_concentration,
        "trace_effective_support": trace_effective_support,
    }


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
