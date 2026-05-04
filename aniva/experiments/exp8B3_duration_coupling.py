"""Phase 8B.3: Duration-Coupled Closed Loop.

Hypothesis: L/R label bias cannot steer plasticity trajectory (proven in 8B.2).
Next lever: state → event duration / continuity coupling.

Instead of changing which side gets stimulated, modulate how LONG each
stimulus event lasts, based on regional activation imbalance.

Three arms:
  open_loop:        fixed base stream, duration=80
  closed_loop_dur:  same event times + L/R labels as base stream,
                    but duration modulated by current lr_imbalance
  matched_dur_shuf: closed_loop's duration sequence replayed with
                    shuffled state-time assignment

Duration rule:
  base_duration = 80, min = 40, max = 160
  lr_imbalance > 0 (L more active) → R events longer, L events shorter
  lr_imbalance < 0 (R more active) → L events longer, R events shorter

Language discipline: no "preference", "reward", "choice", "agent".
"""
import argparse, csv, json, sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

# ── Stimulus definitions ─────────────────────────────────────────────

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

# ── Duration params ──────────────────────────────────────────────────

BASE_DURATION = 80
MIN_DURATION = 40
MAX_DURATION = 160

# ── State observer ───────────────────────────────────────────────────

def _compute_state_summary(core: LifeCore) -> dict:
    left_ids = [uid for uid, u in core.units.items() if u.position[0] < 0]
    right_ids = [uid for uid, u in core.units.items() if u.position[0] > 0]
    left_acts = np.array([core.units[uid].activation for uid in left_ids])
    right_acts = np.array([core.units[uid].activation for uid in right_ids])
    left_mean = float(np.mean(left_acts)) if len(left_acts) > 0 else 0.0
    right_mean = float(np.mean(right_acts)) if len(right_acts) > 0 else 0.0
    lr_imbalance = left_mean - right_mean
    all_acts = np.array([u.activation for u in core.units.values()])
    hist, _ = np.histogram(all_acts, bins=20, range=(0.0, 1.0))
    hist = hist.astype(np.float64) / max(hist.sum(), 1)
    hist = hist[hist > 0]
    act_entropy = float(-np.sum(hist * np.log(hist))) if len(hist) > 0 else 0.0
    return {
        "left_mean": left_mean, "right_mean": right_mean,
        "lr_imbalance": lr_imbalance,
        "energy_mean": float(np.mean(core._energies)),
        "act_entropy": act_entropy,
    }


def _compute_duration_bias(lr_imbalance: float, gain: float) -> float:
    """Map lr_imbalance to duration offset.
    lr_imbalance > 0 (L more active): positive bias → R events get longer
    lr_imbalance < 0 (R more active): negative bias → L events get longer
    """
    return float(np.clip(gain * lr_imbalance, -0.5, 0.5))


def _apply_duration_modulation(base_dur: int, label: str, bias: float) -> int:
    """Apply duration modulation.
    bias > 0: R gets longer, L gets shorter.
    bias < 0: L gets longer, R gets shorter.
    """
    if label == "R":
        dur = base_dur * (1.0 + bias)  # bias>0 → longer R
    else:  # "L"
        dur = base_dur * (1.0 - bias)  # bias>0 → shorter L
    return int(np.clip(dur, MIN_DURATION, MAX_DURATION))


# ── Base event stream ───────────────────────────────────────────────

def _pre_generate_base_stream(
    total_steps: int, event_interval: int, base_p_L: float,
    event_duration: int, rng: np.random.Generator,
) -> list[dict]:
    stream = []
    for step in range(event_interval, total_steps, event_interval):
        if rng.random() < base_p_L:
            stim, chosen = L_STIM, "L"
        else:
            stim, chosen = R_STIM, "R"
        stream.append({"step": step, "chosen": chosen, "stimulus": stim, "duration": event_duration})
    return stream


# ── Structural readout (reused from 8B.1B) ──────────────────────────

def _classify_connection(source_pos, target_pos):
    src = "L" if source_pos[0] < -0.1 else ("R" if source_pos[0] > 0.1 else "M")
    tgt = "L" if target_pos[0] < -0.1 else ("R" if target_pos[0] > 0.1 else "M")
    return f"{src}→{tgt}"


def _compute_structural_readout(core, weights_initial) -> dict:
    connections = list(core.connections)
    weights_final = np.array([c.weight for c in connections], dtype=np.float64)
    deltas = weights_final - weights_initial

    regions = []
    for conn in connections:
        src_pos = core.units[conn.source_id].position
        tgt_pos = core.units[conn.target_id].position
        regions.append(_classify_connection(src_pos, tgt_pos))
    unique_regions = sorted(set(regions))

    abs_deltas = np.abs(deltas)
    sorted_abs = np.sort(abs_deltas)[::-1]
    n_conns = len(deltas)
    total_mass = float(np.sum(sorted_abs))

    pos_mask = deltas > 0; neg_mask = deltas < 0
    regional = {}
    for reg in unique_regions:
        mask = np.array([r == reg for r in regions])
        reg_deltas = deltas[mask]
        regional[reg] = {
            "count": int(np.sum(mask)),
            "l1": float(np.mean(np.abs(reg_deltas))) if len(reg_deltas) > 0 else 0.0,
            "signed_mean": float(np.mean(reg_deltas)) if len(reg_deltas) > 0 else 0.0,
        }

    l_in = np.array(["→L" in r for r in regions])
    l_out = np.array(["L→" in r for r in regions])
    r_in = np.array(["→R" in r for r in regions])
    r_out = np.array(["R→" in r for r in regions])
    within = np.array([r in ("L→L", "R→R") for r in regions])
    cross = np.array([r in ("L→R", "R→L") for r in regions])

    def _safe_mean(arr, mask):
        return float(np.mean(np.abs(arr[mask]))) if mask.any() else 0.0

    return {
        "global_l1": float(np.mean(abs_deltas)),
        "signed_mean": float(np.mean(deltas)),
        "pos_mass": float(np.sum(deltas[pos_mask])) if pos_mask.any() else 0.0,
        "neg_mass": float(np.sum(np.abs(deltas[neg_mask]))) if neg_mask.any() else 0.0,
        "top1pct_frac": float(np.sum(sorted_abs[:max(1, int(n_conns * 0.01))]) / max(total_mass, 1e-30)),
        "top5pct_frac": float(np.sum(sorted_abs[:max(1, int(n_conns * 0.05))]) / max(total_mass, 1e-30)),
        "top10pct_mass": float(np.sum(sorted_abs[:max(1, int(n_conns * 0.10))])),
        "total_abs_mass": total_mass,
        "regional": regional,
        "aggregated": {
            "L_incoming_l1": _safe_mean(abs_deltas, l_in),
            "L_outgoing_l1": _safe_mean(abs_deltas, l_out),
            "R_incoming_l1": _safe_mean(abs_deltas, r_in),
            "R_outgoing_l1": _safe_mean(abs_deltas, r_out),
            "within_region_l1": _safe_mean(abs_deltas, within),
            "cross_region_l1": _safe_mean(abs_deltas, cross),
        },
        "dist_std": float(np.std(deltas)),
        "dist_p95": float(np.percentile(abs_deltas, 95)),
        "dist_p99": float(np.percentile(abs_deltas, 99)),
        "dist_max": float(np.max(abs_deltas)),
        "delta_vector": deltas.tolist(),
        "n_connections": n_conns,
    }


# ── Run open_loop / closed_loop_duration ─────────────────────────────

def _run_duration_arm(
    config: AnivaConfig, arm: str, total_steps: int,
    base_duration: int, duration_gain: float,
    feedback_interval: int, snapshot_interval: int,
    base_stream: list[dict],
) -> dict:
    """Run one arm with duration coupling.
    arm = "open_loop" or "closed_loop_dur"
    """
    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    all_events: list[StimulusEvent] = []
    event_log: list[dict] = []
    bias_history: list[float] = []

    for step in range(total_steps):
        if step > 0 and step % base_stream[0]["step"] == 0:
            base_event = None
            for be in base_stream:
                if be["step"] == step:
                    base_event = be
                    break
            if base_event is None:
                core.step(env_influences=None)
                continue

            label = base_event["chosen"]
            stim = base_event["stimulus"]

            if arm == "open_loop":
                dur = base_duration
                bias = 0.0
            elif arm == "closed_loop_dur":
                state = _compute_state_summary(core)
                bias = _compute_duration_bias(state["lr_imbalance"], duration_gain)
                dur = _apply_duration_modulation(base_duration, label, bias)
            else:
                raise ValueError(f"Unknown arm: {arm}")

            bias_history.append(bias)
            event = StimulusEvent(stimulus=stim, start_step=step, duration_steps=dur)
            all_events.append(event)
            event_log.append({
                "step": step, "chosen": label, "duration": dur,
                "base_duration": base_duration, "bias": bias,
            })

        influences = {}
        for event in all_events:
            if event.start_step <= step < event.start_step + event.duration_steps:
                for uid, u in core.units.items():
                    d = np.linalg.norm(np.array(u.position) - np.array(event.stimulus.position))
                    if d <= event.stimulus.radius:
                        val = event.stimulus.intensity * (1.0 - d / event.stimulus.radius)
                        if uid not in influences:
                            influences[uid] = 0.0
                        influences[uid] += val

        core.step(env_influences=influences if influences else None)

        if (step + 1) % snapshot_interval == 0 or step == total_steps - 1:
            all_acts = np.array([u.activation for u in core.units.values()])
            left_ids = [uid for uid, u in core.units.items() if u.position[0] < 0]
            right_ids = [uid for uid, u in core.units.items() if u.position[0] > 0]
            left_acts = np.array([core.units[uid].activation for uid in left_ids])
            right_acts = np.array([core.units[uid].activation for uid in right_ids])
            weights = np.array([c.weight for c in core.connections])
            snapshots.append({
                "step": step + 1,
                "mean_activation": float(np.mean(all_acts)),
                "mean_energy": float(np.mean(core._energies)),
                "weight_abs_mean": float(np.mean(np.abs(weights))),
                "left_activation_mean": float(np.mean(left_acts)) if len(left_acts) > 0 else 0.0,
                "right_activation_mean": float(np.mean(right_acts)) if len(right_acts) > 0 else 0.0,
                "lr_imbalance": (
                    float(np.mean(left_acts)) - float(np.mean(right_acts))
                    if left_ids and right_ids else 0.0
                ),
            })

    weights_final = np.array([c.weight for c in core.connections], dtype=np.float64)
    final_weight_l1 = float(np.mean(np.abs(weights_final - weights_initial)))

    n_L = sum(1 for e in event_log if e["chosen"] == "L")
    n_R = sum(1 for e in event_log if e["chosen"] == "R")
    total_events = max(n_L + n_R, 1)
    dur_L = [e["duration"] for e in event_log if e["chosen"] == "L"]
    dur_R = [e["duration"] for e in event_log if e["chosen"] == "R"]

    return {
        "arm": arm, "seed": config.seed,
        "snapshots": snapshots, "event_log": event_log,
        "bias_history": bias_history,
        "final_weight_l1": final_weight_l1,
        "event_count_L": n_L, "event_count_R": n_R,
        "event_L_fraction": n_L / total_events,
        "mean_duration_L": float(np.mean(dur_L)) if dur_L else 0.0,
        "mean_duration_R": float(np.mean(dur_R)) if dur_R else 0.0,
        "total_duration_L": int(np.sum(dur_L)),
        "total_duration_R": int(np.sum(dur_R)),
        "duration_std": float(np.std([e["duration"] for e in event_log])),
        "final_mean_activation": float(np.mean([u.activation for u in core.units.values()])),
        "readout": _compute_structural_readout(core, weights_initial),
    }


# ── Run matched_duration_shuffle ──────────────────────────────────────

def _run_duration_shuffle_arm(
    config: AnivaConfig, total_steps: int,
    feedback_interval: int, snapshot_interval: int,
    cl_event_log: list[dict], shuffle_rng: np.random.Generator,
) -> dict:
    """Replay closed_loop's events with shuffled duration assignments.
    Same event times, same L/R labels, but durations are randomly
    reassigned across the event sequence.
    """
    # Extract durations and shuffle
    durations = [e["duration"] for e in cl_event_log]
    shuffled_durations = durations.copy()
    shuffle_rng.shuffle(shuffled_durations)

    # Build fixed schedule
    fixed_schedule = []
    for base_ev, dur in zip(cl_event_log, shuffled_durations):
        stim = L_STIM if base_ev["chosen"] == "L" else R_STIM
        fixed_schedule.append({
            "step": base_ev["step"], "chosen": base_ev["chosen"],
            "stimulus": stim, "duration": dur,
        })

    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    all_events: list[StimulusEvent] = []
    event_log: list[dict] = []

    schedule_idx = 0
    for step in range(total_steps):
        while schedule_idx < len(fixed_schedule) and fixed_schedule[schedule_idx]["step"] <= step:
            se = fixed_schedule[schedule_idx]
            if se["step"] == step:
                event = StimulusEvent(stimulus=se["stimulus"], start_step=step, duration_steps=se["duration"])
                all_events.append(event)
                event_log.append({"step": step, "chosen": se["chosen"], "duration": se["duration"], "bias": 0.0})
            schedule_idx += 1

        influences = {}
        for event in all_events:
            if event.start_step <= step < event.start_step + event.duration_steps:
                for uid, u in core.units.items():
                    d = np.linalg.norm(np.array(u.position) - np.array(event.stimulus.position))
                    if d <= event.stimulus.radius:
                        val = event.stimulus.intensity * (1.0 - d / event.stimulus.radius)
                        if uid not in influences:
                            influences[uid] = 0.0
                        influences[uid] += val

        core.step(env_influences=influences if influences else None)

        if (step + 1) % snapshot_interval == 0 or step == total_steps - 1:
            all_acts = np.array([u.activation for u in core.units.values()])
            left_ids = [uid for uid, u in core.units.items() if u.position[0] < 0]
            right_ids = [uid for uid, u in core.units.items() if u.position[0] > 0]
            left_acts = np.array([core.units[uid].activation for uid in left_ids])
            right_acts = np.array([core.units[uid].activation for uid in right_ids])
            weights = np.array([c.weight for c in core.connections])
            snapshots.append({
                "step": step + 1,
                "mean_activation": float(np.mean(all_acts)),
                "mean_energy": float(np.mean(core._energies)),
                "weight_abs_mean": float(np.mean(np.abs(weights))),
                "left_activation_mean": float(np.mean(left_acts)) if len(left_acts) > 0 else 0.0,
                "right_activation_mean": float(np.mean(right_acts)) if len(right_acts) > 0 else 0.0,
                "lr_imbalance": (
                    float(np.mean(left_acts)) - float(np.mean(right_acts))
                    if left_ids and right_ids else 0.0
                ),
            })

    weights_final = np.array([c.weight for c in core.connections], dtype=np.float64)
    final_weight_l1 = float(np.mean(np.abs(weights_final - weights_initial)))

    n_L = sum(1 for e in event_log if e["chosen"] == "L")
    n_R = sum(1 for e in event_log if e["chosen"] == "R")
    total_events = max(n_L + n_R, 1)
    dur_L = [e["duration"] for e in event_log if e["chosen"] == "L"]
    dur_R = [e["duration"] for e in event_log if e["chosen"] == "R"]

    return {
        "arm": "matched_dur_shuf", "seed": config.seed,
        "snapshots": snapshots, "event_log": event_log,
        "bias_history": [],
        "final_weight_l1": final_weight_l1,
        "event_count_L": n_L, "event_count_R": n_R,
        "event_L_fraction": n_L / total_events,
        "mean_duration_L": float(np.mean(dur_L)) if dur_L else 0.0,
        "mean_duration_R": float(np.mean(dur_R)) if dur_R else 0.0,
        "total_duration_L": int(np.sum(dur_L)),
        "total_duration_R": int(np.sum(dur_R)),
        "duration_std": float(np.std([e["duration"] for e in event_log])),
        "final_mean_activation": float(np.mean([u.activation for u in core.units.values()])),
        "readout": _compute_structural_readout(core, weights_initial),
    }


# ── Save ────────────────────────────────────────────────────────────

def _save_csv(results: list[dict], path: str) -> None:
    rows = []
    for r in results:
        for snap in r["snapshots"]:
            rows.append({
                "seed": r["seed"], "arm": r["arm"], "step": snap["step"],
                "mean_activation": snap["mean_activation"],
                "mean_energy": snap["mean_energy"],
                "weight_abs_mean": snap["weight_abs_mean"],
                "left_activation_mean": snap["left_activation_mean"],
                "right_activation_mean": snap["right_activation_mean"],
                "lr_imbalance": snap["lr_imbalance"],
                "event_count_L": r["event_count_L"],
                "event_count_R": r["event_count_R"],
                "event_L_fraction": r["event_L_fraction"],
                "final_weight_l1": r["final_weight_l1"],
                "mean_duration_L": r["mean_duration_L"],
                "mean_duration_R": r["mean_duration_R"],
            })
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _save_summary_json(results: list[dict], path: str, params: dict) -> None:
    summary = {"experiment": "phase8B3_duration_coupling", "params": params, "arms": []}
    for r in results:
        arm_entry = {
            "seed": r["seed"], "arm": r["arm"],
            "event_count_L": r["event_count_L"],
            "event_count_R": r["event_count_R"],
            "event_L_fraction": r["event_L_fraction"],
            "final_weight_l1": r["final_weight_l1"],
            "mean_duration_L": r["mean_duration_L"],
            "mean_duration_R": r["mean_duration_R"],
            "total_duration_L": r["total_duration_L"],
            "total_duration_R": r["total_duration_R"],
            "duration_std": r["duration_std"],
            "mean_lr_imbalance": float(np.mean([
                s["lr_imbalance"] for s in r["snapshots"]
            ])) if r["snapshots"] else None,
            "final_mean_activation": r["final_mean_activation"],
        }
        ro = r.get("readout")
        if ro:
            arm_entry["readout"] = {
                "global_l1": ro["global_l1"],
                "signed_mean": ro["signed_mean"],
                "top1pct_frac": ro["top1pct_frac"],
                "top5pct_frac": ro["top5pct_frac"],
                "regional": ro["regional"],
                "aggregated": ro["aggregated"],
                "dist_p95": ro["dist_p95"],
                "dist_max": ro["dist_max"],
                "dist_std": ro["dist_std"],
            }
        summary["arms"].append(arm_entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)


# ── CLI ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 8B.3: Duration-Coupled Closed Loop")
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 999])
    parser.add_argument("--unit-count", type=int, default=300)
    parser.add_argument("--event-interval", type=int, default=200)
    parser.add_argument("--base-duration", type=int, default=80)
    parser.add_argument("--base-p-L", type=float, default=0.5)
    parser.add_argument("--duration-gain", type=float, default=300.0,
                        help="Multiplier: bias = gain * lr_imbalance, mapped to duration ±50%")
    parser.add_argument("--feedback-interval", type=int, default=200)
    parser.add_argument("--snapshot-interval", type=int, default=None)
    parser.add_argument("--base-rng-seed", type=int, default=20260504)
    parser.add_argument("--output-csv", type=str, default="results/phase8B3_duration_20k.csv")
    parser.add_argument("--summary-json", type=str, default="results/phase8B3_duration_20k_summary.json")
    parser.add_argument("--no-homeostasis", action="store_true")
    parser.add_argument("--no-numba", action="store_true")
    args = parser.parse_args(argv)

    if args.snapshot_interval is None:
        args.snapshot_interval = max(args.steps // 10, 200)

    config_base = AnivaConfig(unit_count=args.unit_count)
    config_base.homeostasis_enabled = not args.no_homeostasis
    config_base.use_numba_plasticity = not args.no_numba
    config_base.homeostatic_target_abs_weight = 0.30
    config_base.homeostatic_rate = 1.0

    print(f"Phase 8B.3: Duration-Coupled Closed Loop")
    print(f"  seeds={args.seeds}, steps={args.steps}")
    print(f"  event_interval={args.event_interval}, base_duration={args.base_duration}")
    print(f"  duration_gain={args.duration_gain}, range=[{MIN_DURATION}, {MAX_DURATION}]")

    all_results: list[dict] = []

    for seed in args.seeds:
        config_base.seed = seed
        print(f"\n{'='*60}")
        print(f"Seed {seed}")
        print(f"{'='*60}")

        base_rng = np.random.default_rng(args.base_rng_seed)
        base_stream = _pre_generate_base_stream(
            args.steps, args.event_interval, args.base_p_L,
            args.base_duration, base_rng,
        )
        base_L = sum(1 for be in base_stream if be["chosen"] == "L")
        base_R = len(base_stream) - base_L
        print(f"  base_stream: {len(base_stream)} events, L={base_L}, R={base_R}")

        # Arm 1: open_loop
        r_ol = _run_duration_arm(
            config_base, "open_loop", args.steps,
            args.base_duration, args.duration_gain,
            args.feedback_interval, args.snapshot_interval,
            base_stream,
        )
        print(f"  [open_loop]         L={r_ol['event_count_L']:>4d} R={r_ol['event_count_R']:>4d} "
              f"dur(L)={r_ol['mean_duration_L']:.0f} dur(R)={r_ol['mean_duration_R']:.0f} "
              f"wL1={r_ol['final_weight_l1']:.8f}")
        all_results.append(r_ol)

        # Arm 2: closed_loop_duration
        r_cl = _run_duration_arm(
            config_base, "closed_loop_dur", args.steps,
            args.base_duration, args.duration_gain,
            args.feedback_interval, args.snapshot_interval,
            base_stream,
        )
        delta_w = r_cl["final_weight_l1"] - r_ol["final_weight_l1"]
        print(f"  [closed_loop_dur]   L={r_cl['event_count_L']:>4d} R={r_cl['event_count_R']:>4d} "
              f"dur(L)={r_cl['mean_duration_L']:.0f} dur(R)={r_cl['mean_duration_R']:.0f} "
              f"wL1={r_cl['final_weight_l1']:.8f}")
        print(f"    ΔwL1={delta_w:>+.4e}  dur_std={r_cl['duration_std']:.1f}")
        all_results.append(r_cl)

        # Arm 3: matched_duration_shuffle
        shuffle_rng = np.random.default_rng(args.base_rng_seed + seed * 10 + 3)
        r_ms = _run_duration_shuffle_arm(
            config_base, args.steps,
            args.feedback_interval, args.snapshot_interval,
            r_cl["event_log"], shuffle_rng,
        )
        delta_w_ms = r_ms["final_weight_l1"] - r_ol["final_weight_l1"]
        print(f"  [matched_dur_shuf]  L={r_ms['event_count_L']:>4d} R={r_ms['event_count_R']:>4d} "
              f"dur(L)={r_ms['mean_duration_L']:.0f} dur(R)={r_ms['mean_duration_R']:.0f} "
              f"wL1={r_ms['final_weight_l1']:.8f}")
        print(f"    ΔwL1={delta_w_ms:>+.4e}  dur_std={r_ms['duration_std']:.1f}")
        all_results.append(r_ms)

    # ── Cross-Arm Delta Vector Comparison ─────────────────────────
    print(f"\n{'='*90}")
    print(f"Phase 8B.3 — Cross-Arm Delta Vector + Duration Summary")
    print(f"{'='*90}")

    print(f"\n{'seed':>5s} {'arm':>20s}  "
          f"{'dur(L)':>7s} {'dur(R)':>7s} {'dur_std':>8s} "
          f"{'wL1':>12s} {'ΔwL1':>10s}")
    print("-" * 85)
    for r in all_results:
        print(f"{r['seed']:>5d} {r['arm']:>20s}  "
              f"{r['mean_duration_L']:>7.1f} {r['mean_duration_R']:>7.1f} "
              f"{r['duration_std']:>8.1f} "
              f"{r['final_weight_l1']:>12.8f} {r['final_weight_l1'] - r_ol['final_weight_l1']:>+10.2e}"
              if r['seed'] == r['seed'] else "")

    print(f"\n--- Cross-Arm Delta Vector Comparison ---")
    print(f"{'seed':>5s} "
          f"{'cos(cl, ol)':>14s} {'cos(ms, ol)':>14s} {'cos(cl, ms)':>14s} "
          f"{'|cl-ms|_L1':>12s} {'|cl-ms|_L2':>12s}")
    print("-" * 75)

    for seed in args.seeds:
        seed_results = [r for r in all_results if r["seed"] == seed]
        arms = {r["arm"]: r for r in seed_results}
        ol = arms.get("open_loop")
        cl = arms.get("closed_loop_dur")
        ms = arms.get("matched_dur_shuf")
        if not all([ol, cl, ms]):
            continue
        dv_ol = np.array(ol["readout"]["delta_vector"])
        dv_cl = np.array(cl["readout"]["delta_vector"])
        dv_ms = np.array(ms["readout"]["delta_vector"])

        def _cos(a, b):
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

        cos_cl_ol = _cos(dv_cl, dv_ol)
        cos_ms_ol = _cos(dv_ms, dv_ol)
        cos_cl_ms = _cos(dv_cl, dv_ms)
        l1 = float(np.mean(np.abs(dv_cl - dv_ms)))
        l2 = float(np.sqrt(np.mean((dv_cl - dv_ms) ** 2)))

        print(f"{seed:>5d}  "
              f"{cos_cl_ol:>14.6f} {cos_ms_ol:>14.6f} {cos_cl_ms:>14.6f} "
              f"{l1:>12.6e} {l2:>12.6e}")

    # ── Regional Readout ──────────────────────────────────────────
    print(f"\n--- Regional Structural Readout ---")
    print(f"{'seed':>5s} {'arm':>20s}  {'global_l1':>12s} {'signed':>10s} "
          f"{'L→L':>10s} {'R→R':>10s} {'L→R':>10s} {'R→L':>10s}")
    print("-" * 100)
    for r in all_results:
        ro = r.get("readout")
        if not ro:
            continue
        reg = ro["regional"]
        def _r(k):
            return f"{reg.get(k, {}).get('l1', 0):.6e}" if k in reg else "N/A"
        print(f"{r['seed']:>5d} {r['arm']:>20s}  "
              f"{ro['global_l1']:>12.6e} {ro['signed_mean']:>+10.3e} "
              f"{_r('L→L'):>10s} {_r('R→R'):>10s} {_r('L→R'):>10s} {_r('R→L'):>10s}")

    # ── Save ─────────────────────────────────────────────────────
    if args.output_csv:
        _save_csv(all_results, args.output_csv)
    if args.summary_json:
        _save_summary_json(all_results, args.summary_json, {
            "steps": args.steps, "seeds": args.seeds,
            "event_interval": args.event_interval,
            "base_duration": args.base_duration,
            "duration_gain": args.duration_gain,
            "base_rng_seed": args.base_rng_seed,
        })

    print(f"\nDone. {len(all_results)} arm-runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
