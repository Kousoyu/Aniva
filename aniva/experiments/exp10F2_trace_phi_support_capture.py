"""Phase 10F Step 2 — Trace/Phi Support Capture Runner.

Read-only instrumentation runner. Captures true trace[src] and phi[tgt] around
existing 9C event-pair plasticity updates.

No mechanism changes. No tag-rule changes. No 9D changes.
"""

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import defaultdict

import numpy as np

from aniva.config import AnivaConfig
from aniva.environment.environment import Environment, Stimulus, StimulusEvent
from aniva.life_core import LifeCore


L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}
EVENT_SET = ["none", "L", "R", "simultaneous"]

TOTAL_STEPS = 7500
WARMUP_END = 2000
DECISION_INTERVAL = 250
PULSE_DURATION = 80
HISTORICAL_CONTEXT_TAU = 10000.0
DIVERGENT_NOISE_OFFSET = 5000
TAG_EPS = 1e-10
TRACE_EPS = 1e-12
PHI_EPS = 1e-12


# ═══════════════════════════════════════════════════════════════════
# Small helpers
# ═══════════════════════════════════════════════════════════════════

def _unit_region(pos):
    x = pos[0]
    if x < -0.1:
        return "L"
    if x > 0.1:
        return "R"
    return "M"


def _subgraph(src_reg, tgt_reg):
    return src_reg + tgt_reg


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def _r(v):
    if isinstance(v, float) and np.isnan(v):
        return "nan"
    if isinstance(v, float):
        return round(v, 6)
    return v


def _pearson(a, b):
    if len(a) < 2:
        return float("nan")
    sa = float(np.std(a))
    sb = float(np.std(b))
    if sa < 1e-12 or sb < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


# ═══════════════════════════════════════════════════════════════════
# Core snapshot helpers
# ═══════════════════════════════════════════════════════════════════

def _snapshot_core_state(core):
    return {
        "activations": core._activations.copy(),
        "energies": core._energies.copy(),
        "thresholds": core._thresholds.copy(),
        "traces": core._traces.copy(),
        "activity_traces": core._activity_traces.copy(),
        "previous_activations": core._previous_activations.copy(),
        "onset_traces": core._onset_traces.copy(),
        "current_onsets": core._current_onsets.copy(),
        "event_trace": core._event_trace.copy(),
        "last_event_step": core._last_event_step,
        "positions": core._positions.copy(),
        "time_constants": core._time_constants.copy(),
        "source_indices": core._source_indices.copy(),
        "target_indices": core._target_indices.copy(),
        "weights": np.array([c.weight for c in core.connections], dtype=np.float64),
        "weight_cache": core._weight_cache.copy(),
        "step_count": core.step_count,
    }


def _restore_core_state(core, snap):
    core._activations[:] = snap["activations"]
    core._energies[:] = snap["energies"]
    core._thresholds[:] = snap["thresholds"]
    core._traces[:] = snap["traces"]
    core._activity_traces[:] = snap["activity_traces"]
    core._previous_activations[:] = snap["previous_activations"]
    core._onset_traces[:] = snap["onset_traces"]
    core._current_onsets[:] = snap["current_onsets"]
    core._event_trace[:] = snap["event_trace"]
    core._last_event_step = snap["last_event_step"]
    core._positions[:] = snap["positions"]
    core._time_constants[:] = snap["time_constants"]
    core._source_indices[:] = snap["source_indices"]
    core._target_indices[:] = snap["target_indices"]
    core._weight_cache[:] = snap["weight_cache"]
    core.step_count = snap["step_count"]
    for i, conn in enumerate(core.connections):
        conn.weight = float(snap["weights"][i])


def _run_warmup_weight_frozen(core, warmup_steps, env):
    w0 = core._weight_cache.copy()
    w0_conn = [c.weight for c in core.connections]
    for s in range(warmup_steps):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)
        core._weight_cache[:] = w0
        for i, conn in enumerate(core.connections):
            conn.weight = w0_conn[i]
    return float(np.sum(np.abs(core._weight_cache - w0)))


def _compute_region_activity(core):
    acts = core._activations
    positions = core._positions
    l_vals, r_vals = [], []
    for uid in range(len(acts)):
        reg = _unit_region(positions[uid])
        if reg == "L":
            l_vals.append(acts[uid])
        elif reg == "R":
            r_vals.append(acts[uid])
    return (
        float(np.mean(l_vals)) if l_vals else 0.0,
        float(np.mean(r_vals)) if r_vals else 0.0,
    )


def _build_phi_cache(core):
    n = core.unit_count
    phi_l = np.array([L_STIM.influence_at(tuple(core._positions[u])) for u in range(n)], dtype=np.float64)
    phi_r = np.array([R_STIM.influence_at(tuple(core._positions[u])) for u in range(n)], dtype=np.float64)
    return {"L": phi_l, "R": phi_r, "simultaneous": phi_l + phi_r}


def _make_cfg(seed, event_pair_on=True, consolidation_on=True):
    return AnivaConfig(
        unit_count=300,
        seed=seed,
        event_pair_plasticity_enabled=event_pair_on,
        event_pair_ledger_enabled=event_pair_on,
        consolidation_enabled=consolidation_on,
        consolidation_ledger_enabled=consolidation_on,
        historical_context_enabled=True,
        historical_context_tau=HISTORICAL_CONTEXT_TAU,
        historical_context_clip=True,
    )


def _tag_event_hash(event_index, event_step, event_type, tag_pre, tag_after):
    h = hashlib.sha256()
    h.update(f"{event_index}|{event_step}|{event_type}|".encode())
    h.update(np.ascontiguousarray(tag_pre, dtype=np.float64).tobytes())
    h.update(b"|")
    h.update(np.ascontiguousarray(tag_after, dtype=np.float64).tobytes())
    return h.hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════
# Connection-level capture
# ═══════════════════════════════════════════════════════════════════

def _capture_connection_rows(core, trace_pre, tag_pre, w_pre, phi, seed, arm, event_index, event_step, event_type):
    src_idx = core._source_indices
    tgt_idx = core._target_indices
    positions = core._positions

    trace_src = trace_pre[src_idx]
    phi_tgt = phi[tgt_idx]
    raw = trace_src * phi_tgt

    w_after = core._weight_cache.copy()
    tag_after = core._tag_cache.copy()
    dW = w_after - w_pre
    tag_delta = tag_after - tag_pre

    src_regions = [_unit_region(positions[u]) for u in src_idx]
    tgt_regions = [_unit_region(positions[u]) for u in tgt_idx]

    rows = []
    for i in range(len(src_idx)):
        rows.append({
            "seed": seed,
            "arm": arm,
            "event_index": event_index,
            "event_step": event_step,
            "event_type": event_type,
            "connection_id": i,
            "src": int(src_idx[i]),
            "tgt": int(tgt_idx[i]),
            "src_region": src_regions[i],
            "tgt_region": tgt_regions[i],
            "subgraph": _subgraph(src_regions[i], tgt_regions[i]),
            "trace_src": round(float(trace_src[i]), 8),
            "phi_tgt": round(float(phi_tgt[i]), 8),
            "raw": round(float(raw[i]), 8),
            "dW": round(float(dW[i]), 8),
            "tag_before": round(float(tag_pre[i]), 8),
            "tag_after": round(float(tag_after[i]), 8),
            "tag_delta": round(float(tag_delta[i]), 8),
            "trace_src_positive": int(abs(trace_src[i]) > TRACE_EPS),
            "phi_tgt_positive": int(abs(phi_tgt[i]) > PHI_EPS),
            "raw_support": int(abs(raw[i]) > TRACE_EPS),
            "dW_support": int(abs(dW[i]) > TRACE_EPS),
            "tag_support": int(abs(tag_delta[i]) > TAG_EPS),
            "h_src": round(float(core._historical_context_trace[src_idx[i]]), 8),
            "h_tgt": round(float(core._historical_context_trace[tgt_idx[i]]), 8),
            "h_conn": round(float(0.5 * (core._historical_context_trace[src_idx[i]] + core._historical_context_trace[tgt_idx[i]])), 8),
            "baseline_weight_abs": round(float(abs(w_pre[i])), 8),
        })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Analysis helpers
# ═══════════════════════════════════════════════════════════════════

def _build_groups(rows):
    groups = defaultdict(list)
    for r in rows:
        seed = r["seed"]
        arm = r["arm"]
        etype = r["event_type"]
        sg = r["subgraph"]
        groups[(seed, arm, "ALL", "ALL")].append(r)
        groups[(seed, arm, etype, "ALL")].append(r)
        groups[(seed, arm, "ALL", sg)].append(r)
        groups[(seed, arm, etype, sg)].append(r)
    return groups


def _verdict(all_identities_hold, dW_vs_tag_hold, raw_vs_dW_hold, corr_h_trace, corr_h_phi):
    if not all_identities_hold:
        return "identity_failure"
    if not raw_vs_dW_hold:
        return "support_scaling_or_gate_issue"
    if not dW_vs_tag_hold:
        return "tag_accumulation_mismatch"
    if not np.isnan(corr_h_trace) and abs(corr_h_trace) > 0.5:
        return "h_may_be_slow_trace_proxy"
    if not np.isnan(corr_h_phi) and abs(corr_h_phi) > 0.5:
        return "h_may_track_phi_geometry"
    return "trace_phi_support_identity_confirmed"


def _analyze_group(rows, eps):
    if not rows:
        return None

    trace = np.array([r["trace_src"] for r in rows], dtype=np.float64)
    phi = np.array([r["phi_tgt"] for r in rows], dtype=np.float64)
    raw = np.array([r["raw"] for r in rows], dtype=np.float64)
    dW = np.array([r["dW"] for r in rows], dtype=np.float64)
    tag_delta = np.array([r["tag_delta"] for r in rows], dtype=np.float64)
    h_src = np.array([r["h_src"] for r in rows], dtype=np.float64)
    h_tgt = np.array([r["h_tgt"] for r in rows], dtype=np.float64)
    h_conn = np.array([r["h_conn"] for r in rows], dtype=np.float64)

    trace_pos = np.abs(trace) > TRACE_EPS
    phi_pos = np.abs(phi) > PHI_EPS
    raw_support = np.abs(raw) > TRACE_EPS
    dW_support = np.abs(dW) > TRACE_EPS
    tag_support = np.abs(tag_delta) > TAG_EPS

    n = len(rows)
    trace_rate = float(np.mean(trace_pos))
    phi_rate = float(np.mean(phi_pos))
    raw_rate = float(np.mean(raw_support))
    dW_rate = float(np.mean(dW_support))
    tag_rate = float(np.mean(tag_support))

    raw_vs_trace_phi = int(np.sum(raw_support != (trace_pos & phi_pos)))
    raw_vs_dW = int(np.sum(raw_support != dW_support))
    dW_vs_tag = int(np.sum(dW_support != tag_support))

    trace_l1 = float(np.sum(np.abs(trace)))
    phi_l1 = float(np.sum(np.abs(phi)))
    raw_l1 = float(np.sum(np.abs(raw)))
    dW_l1 = float(np.sum(np.abs(dW)))
    tag_delta_l1 = float(np.sum(np.abs(tag_delta)))
    scale_consistency = _r(dW_l1 / raw_l1 if raw_l1 > 1e-12 else float("nan"))

    corr_h_trace = _pearson(h_src, trace)
    corr_h_phi = _pearson(h_tgt, phi)

    all_hold = raw_vs_trace_phi == 0
    raw_vs_dW_hold = raw_vs_dW == 0
    dW_vs_tag_hold = dW_vs_tag == 0
    verdict = _verdict(all_hold, dW_vs_tag_hold, raw_vs_dW_hold, corr_h_trace, corr_h_phi)

    return {
        "n_connections": n,
        "trace_src_positive_rate": _r(trace_rate),
        "phi_tgt_positive_rate": _r(phi_rate),
        "raw_support_rate": _r(raw_rate),
        "dW_support_rate": _r(dW_rate),
        "tag_support_rate": _r(tag_rate),
        "raw_vs_trace_phi_mismatch_count": raw_vs_trace_phi,
        "raw_vs_dW_mismatch_count": raw_vs_dW,
        "dW_vs_tag_mismatch_count": dW_vs_tag,
        "trace_src_l1": _r(trace_l1),
        "phi_tgt_l1": _r(phi_l1),
        "raw_l1": _r(raw_l1),
        "dW_l1": _r(dW_l1),
        "tag_delta_l1": _r(tag_delta_l1),
        "raw_l1_to_dW_l1_scale": scale_consistency,
        "corr_h_trace_src": _r(corr_h_trace),
        "corr_h_phi_tgt": _r(corr_h_phi),
        "support_geometry_verdict": verdict,
    }


def _aggregate(rows, eps):
    trace = np.array([r["trace_src"] for r in rows], dtype=np.float64)
    phi = np.array([r["phi_tgt"] for r in rows], dtype=np.float64)
    raw = np.array([r["raw"] for r in rows], dtype=np.float64)
    dW = np.array([r["dW"] for r in rows], dtype=np.float64)
    tag_delta = np.array([r["tag_delta"] for r in rows], dtype=np.float64)
    trace_pos = np.abs(trace) > TRACE_EPS
    phi_pos = np.abs(phi) > PHI_EPS
    raw_support = np.abs(raw) > TRACE_EPS
    dW_support = np.abs(dW) > TRACE_EPS
    tag_support = np.abs(tag_delta) > TAG_EPS
    return {
        "n": len(rows),
        "raw_vs_trace_phi_mismatch_count": int(np.sum(raw_support != (trace_pos & phi_pos))),
        "raw_vs_dW_mismatch_count": int(np.sum(raw_support != dW_support)),
        "dW_vs_tag_mismatch_count": int(np.sum(dW_support != tag_support)),
        "trace_src_positive_rate": float(np.mean(trace_pos)),
        "phi_tgt_positive_rate": float(np.mean(phi_pos)),
        "raw_support_rate": float(np.mean(raw_support)),
        "dW_support_rate": float(np.mean(dW_support)),
        "tag_support_rate": float(np.mean(tag_support)),
        "trace_src_l1": float(np.sum(np.abs(trace))),
        "phi_tgt_l1": float(np.sum(np.abs(phi))),
        "raw_l1": float(np.sum(np.abs(raw))),
        "dW_l1": float(np.sum(np.abs(dW))),
        "tag_delta_l1": float(np.sum(np.abs(tag_delta))),
    }


def _cross_seed_summary(rows, fieldnames, eps):
    all_stats = _aggregate(rows, eps)
    by_seed = {}
    by_event_type = {}
    by_seed_event = defaultdict(list)
    for r in rows:
        by_seed_event[(r["seed"], r["event_type"])].append(r)

    for seed in sorted(set(r["seed"] for r in rows)):
        seed_rows = [r for r in rows if r["seed"] == seed]
        by_seed[str(seed)] = {k: _r(v) if isinstance(v, float) else v for k, v in _aggregate(seed_rows, eps).items()}

    for et in sorted(set(r["event_type"] for r in rows)):
        et_rows = [r for r in rows if r["event_type"] == et]
        by_event_type[et] = {k: _r(v) if isinstance(v, float) else v for k, v in _aggregate(et_rows, eps).items()}

    l_vs_r = {}
    for seed in sorted(set(r["seed"] for r in rows)):
        l_rows = by_seed_event.get((seed, "L"), [])
        r_rows = by_seed_event.get((seed, "R"), [])
        if l_rows and r_rows:
            l_stats = _aggregate(l_rows, eps)
            r_stats = _aggregate(r_rows, eps)
            l_vs_r[str(seed)] = {
                "L_phi_tgt_positive_rate": _r(l_stats["phi_tgt_positive_rate"]),
                "R_phi_tgt_positive_rate": _r(r_stats["phi_tgt_positive_rate"]),
                "R_minus_L_phi_tgt_positive_rate": _r(r_stats["phi_tgt_positive_rate"] - l_stats["phi_tgt_positive_rate"]),
                "L_trace_src_positive_rate": _r(l_stats["trace_src_positive_rate"]),
                "R_trace_src_positive_rate": _r(r_stats["trace_src_positive_rate"]),
                "R_minus_L_trace_src_positive_rate": _r(r_stats["trace_src_positive_rate"] - l_stats["trace_src_positive_rate"]),
                "L_raw_support_rate": _r(l_stats["raw_support_rate"]),
                "R_raw_support_rate": _r(r_stats["raw_support_rate"]),
            }

    fam_a_rows = [r for r in rows if r["seed"] in (42, 77)]
    fam_b_rows = [r for r in rows if r["seed"] in (123, 999)]
    fam_a = _aggregate(fam_a_rows, eps)
    fam_b = _aggregate(fam_b_rows, eps)

    exact_phi_tgt_available = True
    trace_src_available = True
    step2_required = False

    final_verdict = "trace_phi_support_identity_confirmed" if (
        all_stats["raw_vs_trace_phi_mismatch_count"] == 0 and
        all_stats["raw_vs_dW_mismatch_count"] == 0 and
        all_stats["dW_vs_tag_mismatch_count"] == 0
    ) else "identity_failure"

    return {
        "all_raw_vs_trace_phi_mismatch_count": all_stats["raw_vs_trace_phi_mismatch_count"],
        "all_raw_vs_dW_mismatch_count": all_stats["raw_vs_dW_mismatch_count"],
        "all_dW_vs_tag_mismatch_count": all_stats["dW_vs_tag_mismatch_count"],
        "by_seed_trace_src_positive_rate": {k: v["trace_src_positive_rate"] for k, v in by_seed.items()},
        "by_seed_phi_tgt_positive_rate": {k: v["phi_tgt_positive_rate"] for k, v in by_seed.items()},
        "by_event_type_phi_tgt_positive_rate": {k: v["phi_tgt_positive_rate"] for k, v in by_event_type.items()},
        "R_event_phi_tgt_rate_vs_L": l_vs_r,
        "seed123_999_trace_distribution_vs_42_77": {
            "seed42_77_trace_src_positive_rate": _r(fam_a["trace_src_positive_rate"]),
            "seed123_999_trace_src_positive_rate": _r(fam_b["trace_src_positive_rate"]),
            "seed123_999_minus_42_77_trace_src_positive_rate": _r(fam_b["trace_src_positive_rate"] - fam_a["trace_src_positive_rate"]),
            "seed42_77_trace_src_l1": _r(fam_a["trace_src_l1"]),
            "seed123_999_trace_src_l1": _r(fam_b["trace_src_l1"]),
        },
        "seed123_999_phi_distribution_vs_42_77": {
            "seed42_77_phi_tgt_positive_rate": _r(fam_a["phi_tgt_positive_rate"]),
            "seed123_999_phi_tgt_positive_rate": _r(fam_b["phi_tgt_positive_rate"]),
            "seed123_999_minus_42_77_phi_tgt_positive_rate": _r(fam_b["phi_tgt_positive_rate"] - fam_a["phi_tgt_positive_rate"]),
            "seed42_77_phi_tgt_l1": _r(fam_a["phi_tgt_l1"]),
            "seed123_999_phi_tgt_l1": _r(fam_b["phi_tgt_l1"]),
        },
        "exact_phi_tgt_available": exact_phi_tgt_available,
        "trace_src_available": trace_src_available,
        "step2_required": step2_required,
        "final_verdict": final_verdict,
    }


# ═══════════════════════════════════════════════════════════════════
# Arm runners
# ═══════════════════════════════════════════════════════════════════

def _run_arm_closed_loop(seed_env, decision_points):
    cfg = _make_cfg(seed_env)
    core = LifeCore(cfg)
    sched_rng = np.random.default_rng(seed_env + 1000)
    env = Environment()
    phi_cache = _build_phi_cache(core)
    event_rows = []
    event_log = []
    tag_hashes = []
    event_index = 0

    _run_warmup_weight_frozen(core, WARMUP_END, env)

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            logits = np.array([
                1.0,
                5.0 * act_r - 1.5,
                5.0 * act_l - 1.5,
                -3.0,
            ], dtype=np.float64)
            logits -= np.max(logits)
            exp_l = np.exp(logits / 1.0)
            probs = exp_l / np.sum(exp_l)
            u = float(sched_rng.random())
            cum = 0.0
            chosen = "none"
            for i, p in enumerate(probs):
                cum += p
                if u < cum:
                    chosen = EVENT_SET[i]
                    break

            if chosen != "none":
                phi = phi_cache[chosen]
                trace_pre = core._event_trace.copy()
                acts_pre = core._activations.copy()
                tag_pre = core._tag_cache.copy()
                w_pre = core._weight_cache.copy()

                stim = STIM_MAP.get(chosen)
                if stim is None:
                    env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s, duration_steps=PULSE_DURATION))
                    env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s, duration_steps=PULSE_DURATION))
                else:
                    env.add_event(StimulusEvent(stimulus=stim, start_step=s, duration_steps=PULSE_DURATION))

                core.apply_event_pair_phi(phi)

                tag_after = core._tag_cache.copy()
                th = _tag_event_hash(event_index, s, chosen, tag_pre, tag_after)
                tag_hashes.append((event_index, s, chosen, th))
                rows = _capture_connection_rows(core, trace_pre, tag_pre, w_pre, phi, seed_env, "closed_loop", event_index, s, chosen)
                event_rows.extend(rows)
                event_log.append({"t": s, "chosen": chosen, "phi_hash": hashlib.sha256(phi.tobytes()).hexdigest()[:16]})
                event_index += 1

    return event_rows, event_log, tag_hashes


def _run_arm_exact_replay(seed_env, event_log):
    cfg = _make_cfg(seed_env)
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)
    env = Environment()
    event_rows = []
    tag_hashes = []
    hash_mismatches = 0
    replay_idx = 0

    _run_warmup_weight_frozen(core, WARMUP_END, env)

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        while replay_idx < len(event_log) and event_log[replay_idx]["t"] == s:
            entry = event_log[replay_idx]
            chosen = entry["chosen"]
            phi = phi_cache[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != entry["phi_hash"]:
                hash_mismatches += 1

            trace_pre = core._event_trace.copy()
            tag_pre = core._tag_cache.copy()
            w_pre = core._weight_cache.copy()

            stim = STIM_MAP.get(chosen)
            if stim is None:
                env.add_event(StimulusEvent(stimulus=L_STIM, start_step=s, duration_steps=PULSE_DURATION))
                env.add_event(StimulusEvent(stimulus=R_STIM, start_step=s, duration_steps=PULSE_DURATION))
            else:
                env.add_event(StimulusEvent(stimulus=stim, start_step=s, duration_steps=PULSE_DURATION))

            core.apply_event_pair_phi(phi)

            tag_after = core._tag_cache.copy()
            th = _tag_event_hash(replay_idx, s, chosen, tag_pre, tag_after)
            tag_hashes.append((replay_idx, s, chosen, th))
            rows = _capture_connection_rows(core, trace_pre, tag_pre, w_pre, phi, seed_env, "exact_replay", replay_idx, s, chosen)
            event_rows.extend(rows)
            replay_idx += 1

    return event_rows, hash_mismatches, tag_hashes


def _run_arm_divergent(seed_env, event_log):
    hc_kw = dict(
        historical_context_enabled=True,
        historical_context_tau=HISTORICAL_CONTEXT_TAU,
        historical_context_clip=True,
    )
    cfg_ref = AnivaConfig(unit_count=300, seed=seed_env, event_pair_plasticity_enabled=False, consolidation_enabled=False, **hc_kw)
    core_ref = LifeCore(cfg_ref)
    ref_snap = _snapshot_core_state(core_ref)

    cfg_div = AnivaConfig(unit_count=300, seed=seed_env + DIVERGENT_NOISE_OFFSET, event_pair_plasticity_enabled=False, consolidation_enabled=False, **hc_kw)
    core_div = LifeCore(cfg_div)
    _restore_core_state(core_div, ref_snap)

    env_div = Environment()
    _run_warmup_weight_frozen(core_div, WARMUP_END, env_div)
    div_state = {
        "activations": core_div._activations.copy(),
        "energies": core_div._energies.copy(),
        "traces": core_div._traces.copy(),
        "event_trace": core_div._event_trace.copy(),
        "weight_cache": core_div._weight_cache.copy(),
        "h_trace": core_div._historical_context_trace.copy(),
    }

    cfg_replay = _make_cfg(seed_env, event_pair_on=True, consolidation_on=True)
    core_replay = LifeCore(cfg_replay)
    core_replay._activations[:] = div_state["activations"]
    core_replay._energies[:] = div_state["energies"]
    core_replay._traces[:] = div_state["traces"]
    core_replay._event_trace[:] = div_state["event_trace"]
    core_replay._weight_cache[:] = div_state["weight_cache"]
    core_replay._historical_context_trace[:] = div_state["h_trace"]
    for i, conn in enumerate(core_replay.connections):
        conn.weight = float(div_state["weight_cache"][i])

    phi_cache = _build_phi_cache(core_replay)
    env_replay = Environment()
    event_rows = []
    hash_mismatches = 0
    replay_idx = 0

    for s in range(WARMUP_END, TOTAL_STEPS):
        influences = env_replay.compute_influences(core_replay.units, s)
        core_replay.step(env_influences=influences if influences else None)

        while replay_idx < len(event_log) and event_log[replay_idx]["t"] == s:
            entry = event_log[replay_idx]
            chosen = entry["chosen"]
            phi = phi_cache[chosen]
            actual_hash = hashlib.sha256(phi.tobytes()).hexdigest()[:16]
            if actual_hash != entry["phi_hash"]:
                hash_mismatches += 1

            trace_pre = core_replay._event_trace.copy()
            tag_pre = core_replay._tag_cache.copy()
            w_pre = core_replay._weight_cache.copy()

            stim = STIM_MAP.get(chosen)
            if stim is None:
                env_replay.add_event(StimulusEvent(stimulus=L_STIM, start_step=s, duration_steps=PULSE_DURATION))
                env_replay.add_event(StimulusEvent(stimulus=R_STIM, start_step=s, duration_steps=PULSE_DURATION))
            else:
                env_replay.add_event(StimulusEvent(stimulus=stim, start_step=s, duration_steps=PULSE_DURATION))

            core_replay.apply_event_pair_phi(phi)

            rows = _capture_connection_rows(core_replay, trace_pre, tag_pre, w_pre, phi, seed_env, "divergent_warmup_replay", replay_idx, s, chosen)
            event_rows.extend(rows)
            replay_idx += 1

    return event_rows, hash_mismatches


# ═══════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════

def _save_csv(rows, path):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Phase 10F Step 2 trace/phi support capture runner")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 77, 123, 999])
    parser.add_argument("--events-csv", default="results/phase10F2_trace_phi_support_events.csv")
    parser.add_argument("--summary-csv", default="results/phase10F2_trace_phi_support_summary.csv")
    parser.add_argument("--summary-json", default="results/phase10F2_trace_phi_support_summary.json")
    parser.add_argument("--dry-run-schedule", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--n-shuffles", type=int, default=100)
    parser.add_argument("--eps", type=float, default=1e-12)
    args = parser.parse_args()

    if args.dry_run_schedule:
        print(f"[dry-run] seeds={args.seeds}")
        print(f"[dry-run] events csv: {args.events_csv}")
        print(f"[dry-run] summary csv: {args.summary_csv}")
        print(f"[dry-run] summary json: {args.summary_json}")
        print(f"[dry-run] n_shuffles={args.n_shuffles}")
        print("[dry-run] config OK, exiting.")
        return 0

    if args.estimate_only:
        seed_count = len(args.seeds)
        est_rows = int(seed_count * 3 * ((TOTAL_STEPS - WARMUP_END) / DECISION_INTERVAL) * 300 * 0.7)
        # very rough wall-clock guess; only used for local-vs-ECS decision
        est_minutes = 12.0 if seed_count >= 4 else 6.0
        print(f"[estimate] seeds={args.seeds}")
        print(f"[estimate] ~{est_rows:,} event rows")
        print(f"[estimate] ~{est_minutes:.1f} min")
        return 0

    print("Phase 10F Step 2 — Trace/Phi Support Capture Runner")
    print(f"  seeds={args.seeds}")
    print(f"  total_steps={TOTAL_STEPS} warmup_end={WARMUP_END} decision_interval={DECISION_INTERVAL}")
    print(f"  events csv: {args.events_csv}")

    decision_points = set(range(WARMUP_END, TOTAL_STEPS, DECISION_INTERVAL))
    all_rows = []
    seed_meta = []

    for seed in args.seeds:
        print(f"\n=== seed={seed} ===")
        t0 = time.time()

        print("  [1/3] closed_loop ...")
        cl_rows, event_log, cl_tag_hashes = _run_arm_closed_loop(seed, decision_points)
        all_rows.extend(cl_rows)
        n_events = len(event_log)
        print(f"    events={n_events} rows={len(cl_rows)} tag_hashes={len(cl_tag_hashes)}")

        print("  [2/3] exact_replay ...")
        er_rows, er_mm, er_tag_hashes = _run_arm_exact_replay(seed, event_log)
        all_rows.extend(er_rows)
        tag_mismatch = 0
        for a, b in zip(cl_tag_hashes, er_tag_hashes):
            if a != b:
                tag_mismatch += 1
        tag_mismatch += abs(len(cl_tag_hashes) - len(er_tag_hashes))
        print(f"    rows={len(er_rows)} hash_mismatches={er_mm} tag_hash_mismatches={tag_mismatch}")

        print("  [3/3] divergent_warmup_replay ...")
        dv_rows, dv_mm = _run_arm_divergent(seed, event_log)
        all_rows.extend(dv_rows)
        print(f"    rows={len(dv_rows)} hash_mismatches={dv_mm}")

        elapsed = time.time() - t0
        print(f"  seed={seed} done in {elapsed:.1f}s")
        seed_meta.append({
            "seed": seed,
            "n_events": n_events,
            "n_cl_rows": len(cl_rows),
            "n_er_rows": len(er_rows),
            "n_dv_rows": len(dv_rows),
            "er_hash_mismatches": er_mm,
            "dv_hash_mismatches": dv_mm,
            "exact_tag_hash_mismatch_count": tag_mismatch,
            "n_cl_tag_hashes": len(cl_tag_hashes),
            "n_er_tag_hashes": len(er_tag_hashes),
            "elapsed_s": round(elapsed, 2),
        })

    print("\nBuilding summaries ...")
    groups = _build_groups(all_rows)
    summaries = []
    for key, rows in sorted(groups.items()):
        s, arm, etype, sg = key
        result = _analyze_group(rows, args.eps)
        if result is None:
            continue
        entry = {"seed": s, "arm": arm, "event_type": etype, "subgraph": sg}
        entry.update(result)
        summaries.append(entry)

    print("\n=== Core identities (closed_loop, ALL, ALL) ===")
    for s in summaries:
        if s["arm"] == "closed_loop" and s["event_type"] == "ALL" and s["subgraph"] == "ALL":
            print(f"  seed={s['seed']} raw_vs_trace_phi_mismatch={s['raw_vs_trace_phi_mismatch_count']}"
                  f" raw_vs_dW_mismatch={s['raw_vs_dW_mismatch_count']}"
                  f" dW_vs_tag_mismatch={s['dW_vs_tag_mismatch_count']}"
                  f" corr_h_trace={s['corr_h_trace_src']} corr_h_phi={s['corr_h_phi_tgt']}"
                  f" verdict={s['support_geometry_verdict']}")

    print("\n=== L vs R support geometry (closed_loop) ===")
    for s in summaries:
        if s["arm"] == "closed_loop" and s["subgraph"] == "ALL" and s["event_type"] in ("L", "R"):
            print(f"  seed={s['seed']} etype={s['event_type']}"
                  f" trace_rate={s['trace_src_positive_rate']}"
                  f" phi_rate={s['phi_tgt_positive_rate']}"
                  f" raw_rate={s['raw_support_rate']}"
                  f" dW_rate={s['dW_support_rate']}"
                  f" tag_rate={s['tag_support_rate']}")

    # Save outputs
    _save_csv(all_rows, args.events_csv)
    _save_csv(summaries, args.summary_csv)

    cross = _cross_seed_summary(all_rows, [r.keys() for r in all_rows[:1]], args.eps)
    # fieldnames are easier to recover directly from the first row if present
    fieldnames = list(all_rows[0].keys()) if all_rows else []
    cross = _cross_seed_summary(all_rows, fieldnames, args.eps)

    output = {
        "experiment": "phase10F2_trace_phi_support_capture",
        "git_sha": _git_sha(),
        "timestamp": int(time.time()),
        "seeds": args.seeds,
        "total_steps": TOTAL_STEPS,
        "warmup_end": WARMUP_END,
        "decision_interval": DECISION_INTERVAL,
        "n_shuffles": args.n_shuffles,
        "eps": args.eps,
        "seed_meta": seed_meta,
        "cross_seed": cross,
        "summaries": summaries,
    }
    with open(args.summary_json, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved: {args.events_csv}")
    print(f"Saved: {args.summary_csv}")
    print(f"Saved: {args.summary_json}")
    print(f"\nFinal verdict: {cross['final_verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
