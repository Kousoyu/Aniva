"""Phase 9C: event-pair trace plasticity — batch update on world-event arrival.

Anti-cheat: no arm labels, no L/R knowledge, no memory of past events.
The same formula applies uniformly to all connections.
"""

import numpy as np


def apply_event_pair_update(
    trace: np.ndarray,
    phi: np.ndarray,
    weight_cache: np.ndarray,
    source_indices: np.ndarray,
    target_indices: np.ndarray,
    target_l1: float = 1e-4,
    gate_mode: str = "soft_trace_gate",
    gate_ref: float = 3e-2,
    gate_power: float = 1.0,
    gate_threshold: float = 1e-3,
    ledger_enabled: bool = False,
) -> dict | None:
    """Apply one event-pair plasticity update to all connections.

    For each connection i: raw_dW[i] = trace[src_i] * phi[tgt_i].
    The update is L1-normalized and gated by trace mass.

    Gate modes:
      - "soft_trace_gate": gate = min(1, trace_mass / gate_ref) ** gate_power
      - "bare_l1_norm":   gate = 1.0 (always)
      - "hard_threshold": gate = 1.0 if trace_mass >= gate_threshold else 0.0

    Args:
        trace: O(N) event-pair trace vector (pre-decay, pre-phi-addition).
        phi: O(N) spatial activation vector of the arriving event.
        weight_cache: O(K) mutable weight array (modified in-place).
        source_indices: O(K) int array of source unit indices.
        target_indices: O(K) int array of target unit indices.
        target_l1: target L1 norm of the dW update.
        gate_mode: which gate formula to use.
        gate_ref: reference trace_mass for soft_trace_gate.
        gate_power: exponent for soft_trace_gate.
        gate_threshold: cutoff for hard_threshold mode.
        ledger_enabled: if True, return per-direction dW breakdown.

    Returns:
        Ledger dict if ledger_enabled, else None. Keys: gate, trace_mass,
        phi_mass, raw_l1, dW_l1, n_connections.
    """
    trace_mass = float(np.sum(np.abs(trace)))
    phi_mass = float(np.sum(np.abs(phi)))

    if gate_mode == "soft_trace_gate":
        ratio = trace_mass / gate_ref if gate_ref > 0 else 1.0
        gate = min(1.0, ratio) ** gate_power
    elif gate_mode == "hard_threshold":
        gate = 1.0 if trace_mass >= gate_threshold else 0.0
    else:  # "bare_l1_norm"
        gate = 1.0

    src_trace = trace[source_indices]
    tgt_phi = phi[target_indices]
    raw = src_trace * tgt_phi
    raw_l1 = float(np.sum(np.abs(raw)))

    if raw_l1 < 1e-30 or gate == 0.0:
        return _ledger(gate, trace_mass, phi_mass, 0.0, 0.0, len(weight_cache)) if ledger_enabled else None

    scale = target_l1 * gate / raw_l1
    dW = raw * scale
    weight_cache += dW

    # Clamp weights to [-1, 1]
    np.clip(weight_cache, -1.0, 1.0, out=weight_cache)

    if ledger_enabled:
        dW_l1 = float(np.sum(np.abs(dW)))
        return _ledger(gate, trace_mass, phi_mass, raw_l1, dW_l1, len(weight_cache))
    return None


def _ledger(
    gate: float,
    trace_mass: float,
    phi_mass: float,
    raw_l1: float,
    dW_l1: float,
    n_connections: int,
) -> dict:
    return {
        "gate": gate,
        "trace_mass": trace_mass,
        "phi_mass": phi_mass,
        "raw_l1": raw_l1,
        "dW_l1": dW_l1,
        "n_connections": n_connections,
    }
