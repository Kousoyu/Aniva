"""Phase 8B.4: State-Triggered Timing Coupling.

Hypothesis: Event-property coupling (label, duration) cannot steer the
plasticity trajectory (proven in 8B.2, 8B.3) because events follow a
fixed temporal grid. The plasticity system follows the rhythm, not the
decoration.

8B.4 tests removing the fixed clock entirely: event onset timing is
triggered by internal state crossing a threshold, not by a schedule.
The question is whether state-timed events create a different plasticity
trajectory from matched controls that preserve event counts but destroy
the state-timing alignment.

Four arms:
  open_loop_poisson:   Poisson-distributed events, no state feedback
  closed_loop_triggered: Events fire when |smoothed_lr_imbalance|
                         crosses a sustained threshold
  matched_time_shuffle: Same events as triggered, times randomly shuffled
  circular_shift:       Same events as triggered, all times shifted by
                        +total_steps/2 (preserves intervals, shifts phase)

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

# ── Trigger params ───────────────────────────────────────────────────

DEFAULT_EVENT_DURATION = 80
DEFAULT_REFRACTORY = 400
DEFAULT_SUSTAINED_WINDOW = 100
POISSON_MEAN_INTERVAL = 200  # ~100 events in 20k steps
CALIB_STEPS = 2000
THRESHOLD_PERCENTILE = 85
SMOOTHING_ALPHA = 0.1

# ── State observer ───────────────────────────────────────────────────

def _compute_imbalance(core: LifeCore) -> tuple[float, float, float]:
    """Return (left_mean, right_mean, lr_imbalance)."""
    left_acts = [u.activation for uid, u in core.units.items() if u.position[0] < 0]
    right_acts = [u.activation for uid, u in core.units.items() if u.position[0] > 0]
    left_mean = float(np.mean(left_acts)) if left_acts else 0.0
    right_mean = float(np.mean(right_acts)) if right_acts else 0.0
    return left_mean, right_mean, left_mean - right_mean


# ── Structural readout (shared with 8B.1B / 8B.3) ───────────────────

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


# ── Threshold calibration ───────────────────────────────────────────

def _calibrate_threshold(config: AnivaConfig, percentile: float, rng: np.random.Generator) -> float:
    """Run a short open-loop simulation to estimate |lr_imbalance| distribution."""
    core = LifeCore(config)
    imbalances = []
    for step in range(CALIB_STEPS):
        core.step(env_influences=None)
        if step >= 500:  # let transients settle
            _, _, imb = _compute_imbalance(core)
            imbalances.append(abs(imb))
    return float(np.percentile(imbalances, percentile))


# ── Arm 1: open_loop_poisson ────────────────────────────────────────

def _poisson_event_generator(
    total_steps: int, mean_interval: float, p_L: float, rng: np.random.Generator,
) -> list[dict]:
    """Pre-generate Poisson-distributed events."""
    p = 1.0 / mean_interval
    events = []
    for step in range(total_steps):
        if rng.random() < p:
            label = "L" if rng.random() < p_L else "R"
            stim = L_STIM if label == "L" else R_STIM
            events.append({"step": step, "chosen": label, "stimulus": stim, "duration": DEFAULT_EVENT_DURATION})
    return events


def _run_poisson_arm(
    config: AnivaConfig, total_steps: int,
    event_stream: list[dict], snapshot_interval: int,
) -> dict:
    """Run with pre-generated Poisson events. No state feedback."""
    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    all_events: list[StimulusEvent] = []
    event_log: list[dict] = []
    imbalance_history: list[float] = []

    event_idx = 0
    for step in range(total_steps):
        while event_idx < len(event_stream) and event_stream[event_idx]["step"] <= step:
            se = event_stream[event_idx]
            if se["step"] == step:
                ev = StimulusEvent(stimulus=se["stimulus"], start_step=step, duration_steps=se["duration"])
                all_events.append(ev)
                event_log.append({"step": step, "chosen": se["chosen"], "duration": se["duration"]})
            event_idx += 1

        influences = {}
        for ev in all_events:
            if ev.start_step <= step < ev.start_step + ev.duration_steps:
                for uid, u in core.units.items():
                    d = np.linalg.norm(np.array(u.position) - np.array(ev.stimulus.position))
                    if d <= ev.stimulus.radius:
                        val = ev.stimulus.intensity * (1.0 - d / ev.stimulus.radius)
                        if uid not in influences:
                            influences[uid] = 0.0
                        influences[uid] += val

        core.step(env_influences=influences if influences else None)

        _, _, imb = _compute_imbalance(core)
        imbalance_history.append(imb)

        if (step + 1) % snapshot_interval == 0 or step == total_steps - 1:
            all_acts = np.array([u.activation for u in core.units.values()])
            snapshots.append({
                "step": step + 1,
                "mean_activation": float(np.mean(all_acts)),
                "mean_energy": float(np.mean(core._energies)),
                "lr_imbalance": imb,
            })

    return _package_result(
        core, weights_initial, snapshots, event_log, imbalance_history,
        config.seed, "open_loop_poisson",
    )


# ── Arm 2: closed_loop_triggered ────────────────────────────────────

def _run_triggered_arm(
    config: AnivaConfig, total_steps: int,
    threshold: float, sustained_window: int, refractory: int,
    snapshot_interval: int,
) -> dict:
    """Run with state-triggered events.

    When |smoothed_lr_imbalance| exceeds threshold for sustained_window
    consecutive steps AND refractory period has elapsed, an event fires:
    - L more active (imbalance > 0) → stimulate R
    - R more active (imbalance < 0) → stimulate L
    """
    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    all_events: list[StimulusEvent] = []
    event_log: list[dict] = []
    imbalance_history: list[float] = []

    smoothed_imb = 0.0
    sustained_count = 0
    steps_since_last_event = refractory  # allow first event immediately

    for step in range(total_steps):
        # Update active event influences
        influences = {}
        for ev in all_events:
            if ev.start_step <= step < ev.start_step + ev.duration_steps:
                for uid, u in core.units.items():
                    d = np.linalg.norm(np.array(u.position) - np.array(ev.stimulus.position))
                    if d <= ev.stimulus.radius:
                        val = ev.stimulus.intensity * (1.0 - d / ev.stimulus.radius)
                        if uid not in influences:
                            influences[uid] = 0.0
                        influences[uid] += val

        core.step(env_influences=influences if influences else None)

        # State observation
        _, _, raw_imb = _compute_imbalance(core)
        imbalance_history.append(raw_imb)
        smoothed_imb = SMOOTHING_ALPHA * raw_imb + (1 - SMOOTHING_ALPHA) * smoothed_imb

        # Trigger logic
        steps_since_last_event += 1
        if abs(smoothed_imb) > threshold:
            sustained_count += 1
        else:
            sustained_count = 0

        if sustained_count >= sustained_window and steps_since_last_event >= refractory:
            if smoothed_imb > 0:
                # L more active → stimulate R
                stim = R_STIM
                label = "R"
            else:
                # R more active → stimulate L
                stim = L_STIM
                label = "L"

            ev = StimulusEvent(stimulus=stim, start_step=step, duration_steps=DEFAULT_EVENT_DURATION)
            all_events.append(ev)
            event_log.append({
                "step": step, "chosen": label, "duration": DEFAULT_EVENT_DURATION,
                "smoothed_imb": smoothed_imb,
            })
            sustained_count = 0
            steps_since_last_event = 0

        if (step + 1) % snapshot_interval == 0 or step == total_steps - 1:
            all_acts = np.array([u.activation for u in core.units.values()])
            snapshots.append({
                "step": step + 1,
                "mean_activation": float(np.mean(all_acts)),
                "mean_energy": float(np.mean(core._energies)),
                "lr_imbalance": raw_imb,
                "smoothed_imb": smoothed_imb,
            })

    return _package_result(
        core, weights_initial, snapshots, event_log, imbalance_history,
        config.seed, "closed_loop_triggered",
    )


# ── Arm 3: matched_time_shuffle ─────────────────────────────────────

def _run_time_shuffle_arm(
    config: AnivaConfig, total_steps: int,
    triggered_event_log: list[dict], shuffle_rng: np.random.Generator,
    snapshot_interval: int,
) -> dict:
    """Replay triggered arm's events with shuffled time assignments.

    Preserves: event count, L/R labels, durations.
    Destroys: state-timing alignment, inter-event interval structure.
    """
    # Extract event data
    event_data = [(e["step"], e["chosen"], e.get("duration", DEFAULT_EVENT_DURATION))
                  for e in triggered_event_log]
    # Shuffle the times across all events
    times = [e[0] for e in event_data]
    shuffle_rng.shuffle(times)
    shuffled_events = sorted(
        [(t, e[1], e[2]) for t, e in zip(times, event_data)],
        key=lambda x: x[0],
    )

    return _run_fixed_schedule_arm(
        config, total_steps, shuffled_events, snapshot_interval,
        "matched_time_shuffle",
    )


# ── Arm 4: circular_shift ───────────────────────────────────────────

def _run_circular_shift_arm(
    config: AnivaConfig, total_steps: int,
    triggered_event_log: list[dict], shift_amount: int,
    snapshot_interval: int,
) -> dict:
    """Replay triggered arm's events with all times shifted by +shift_amount.

    Preserves: event count, L/R labels, durations, inter-event intervals.
    Destroys: phase alignment between event timing and network state evolution.
    """
    shifted_events = []
    for e in triggered_event_log:
        new_step = (e["step"] + shift_amount) % total_steps
        shifted_events.append((new_step, e["chosen"], e.get("duration", DEFAULT_EVENT_DURATION)))
    shifted_events.sort(key=lambda x: x[0])

    return _run_fixed_schedule_arm(
        config, total_steps, shifted_events, snapshot_interval,
        "circular_shift",
    )


def _run_fixed_schedule_arm(
    config: AnivaConfig, total_steps: int,
    schedule: list[tuple[int, str, int]], snapshot_interval: int,
    arm_label: str,
) -> dict:
    """Run with a fixed event schedule (used by time_shuffle and circular_shift)."""
    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    all_events: list[StimulusEvent] = []
    event_log: list[dict] = []
    imbalance_history: list[float] = []

    schedule_idx = 0
    for step in range(total_steps):
        while schedule_idx < len(schedule) and schedule[schedule_idx][0] <= step:
            t, label, dur = schedule[schedule_idx]
            if t == step:
                stim = L_STIM if label == "L" else R_STIM
                ev = StimulusEvent(stimulus=stim, start_step=step, duration_steps=dur)
                all_events.append(ev)
                event_log.append({"step": step, "chosen": label, "duration": dur})
            schedule_idx += 1

        influences = {}
        for ev in all_events:
            if ev.start_step <= step < ev.start_step + ev.duration_steps:
                for uid, u in core.units.items():
                    d = np.linalg.norm(np.array(u.position) - np.array(ev.stimulus.position))
                    if d <= ev.stimulus.radius:
                        val = ev.stimulus.intensity * (1.0 - d / ev.stimulus.radius)
                        if uid not in influences:
                            influences[uid] = 0.0
                        influences[uid] += val

        core.step(env_influences=influences if influences else None)
        _, _, imb = _compute_imbalance(core)
        imbalance_history.append(imb)

        if (step + 1) % snapshot_interval == 0 or step == total_steps - 1:
            all_acts = np.array([u.activation for u in core.units.values()])
            snapshots.append({
                "step": step + 1,
                "mean_activation": float(np.mean(all_acts)),
                "mean_energy": float(np.mean(core._energies)),
                "lr_imbalance": imb,
            })

    return _package_result(
        core, weights_initial, snapshots, event_log, imbalance_history,
        config.seed, arm_label,
    )


# ── Result packaging ────────────────────────────────────────────────

def _package_result(
    core, weights_initial, snapshots, event_log, imbalance_history,
    seed, arm_label,
) -> dict:
    n_L = sum(1 for e in event_log if e["chosen"] == "L")
    n_R = sum(1 for e in event_log if e["chosen"] == "R")
    total_events = max(n_L + n_R, 1)

    inter_event_intervals = []
    for i in range(1, len(event_log)):
        inter_event_intervals.append(event_log[i]["step"] - event_log[i-1]["step"])

    return {
        "arm": arm_label, "seed": seed,
        "snapshots": snapshots, "event_log": event_log,
        "imbalance_history": imbalance_history,
        "final_weight_l1": float(np.mean(np.abs(
            np.array([c.weight for c in core.connections]) - weights_initial
        ))),
        "event_count_L": n_L, "event_count_R": n_R,
        "event_L_fraction": n_L / total_events,
        "total_events": n_L + n_R,
        "mean_inter_event_interval": float(np.mean(inter_event_intervals)) if inter_event_intervals else 0.0,
        "std_inter_event_interval": float(np.std(inter_event_intervals)) if inter_event_intervals else 0.0,
        "mean_lr_imbalance": float(np.mean(imbalance_history)),
        "std_lr_imbalance": float(np.std(imbalance_history)),
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
                "lr_imbalance": snap["lr_imbalance"],
                "event_count_L": r["event_count_L"],
                "event_count_R": r["event_count_R"],
                "total_events": r["total_events"],
                "final_weight_l1": r["final_weight_l1"],
                "mean_inter_event_interval": r["mean_inter_event_interval"],
            })
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _save_summary_json(results: list[dict], path: str, params: dict) -> None:
    summary = {"experiment": "phase8B4_state_triggered_timing", "params": params, "arms": []}
    for r in results:
        arm_entry = {
            "seed": r["seed"], "arm": r["arm"],
            "event_count_L": r["event_count_L"],
            "event_count_R": r["event_count_R"],
            "event_L_fraction": r["event_L_fraction"],
            "total_events": r["total_events"],
            "final_weight_l1": r["final_weight_l1"],
            "mean_inter_event_interval": r["mean_inter_event_interval"],
            "std_inter_event_interval": r["std_inter_event_interval"],
            "mean_lr_imbalance": r["mean_lr_imbalance"],
            "std_lr_imbalance": r["std_lr_imbalance"],
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
    parser = argparse.ArgumentParser(description="Phase 8B.4: State-Triggered Timing Coupling")
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 999])
    parser.add_argument("--unit-count", type=int, default=300)
    parser.add_argument("--threshold-percentile", type=float, default=85.0)
    parser.add_argument("--sustained-window", type=int, default=100)
    parser.add_argument("--refractory", type=int, default=400)
    parser.add_argument("--event-duration", type=int, default=80)
    parser.add_argument("--poisson-mean-interval", type=int, default=200)
    parser.add_argument("--snapshot-interval", type=int, default=None)
    parser.add_argument("--output-csv", type=str, default="results/phase8B4_state_triggered_20k.csv")
    parser.add_argument("--summary-json", type=str, default="results/phase8B4_state_triggered_20k_summary.json")
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

    print(f"Phase 8B.4: State-Triggered Timing Coupling")
    print(f"  seeds={args.seeds}, steps={args.steps}")
    print(f"  threshold_percentile={args.threshold_percentile}")
    print(f"  sustained_window={args.sustained_window}, refractory={args.refractory}")
    print(f"  event_duration={args.event_duration}")
    print(f"  poisson_mean_interval={args.poisson_mean_interval}")

    all_results: list[dict] = []

    for seed in args.seeds:
        config_base.seed = seed
        print(f"\n{'='*60}")
        print(f"Seed {seed}")
        print(f"{'='*60}")

        # Step 0: calibrate threshold
        calib_rng = np.random.default_rng(20260504)
        threshold = _calibrate_threshold(config_base, args.threshold_percentile, calib_rng)
        print(f"  calibrated threshold (P{args.threshold_percentile}): {threshold:.6f}")

        # Arm 1: open_loop_poisson
        poisson_rng = np.random.default_rng(20260504 + seed)
        poisson_stream = _poisson_event_generator(
            args.steps, args.poisson_mean_interval, 0.5, poisson_rng,
        )
        r_ol = _run_poisson_arm(config_base, args.steps, poisson_stream, args.snapshot_interval)
        print(f"  [open_loop_poisson]      events={r_ol['total_events']:>4d} "
              f"L={r_ol['event_count_L']} R={r_ol['event_count_R']} "
              f"mean_IEI={r_ol['mean_inter_event_interval']:.0f} "
              f"wL1={r_ol['final_weight_l1']:.8f}")
        all_results.append(r_ol)

        # Arm 2: closed_loop_triggered (must run first — generates event log for arms 3 & 4)
        r_cl = _run_triggered_arm(
            config_base, args.steps,
            threshold, args.sustained_window, args.refractory,
            args.snapshot_interval,
        )
        delta_w = r_cl["final_weight_l1"] - r_ol["final_weight_l1"]
        n_overlap = sum(
            1 for e in r_cl["event_log"]
            for pe in poisson_stream
            if abs(e["step"] - pe["step"]) <= 10
        )
        print(f"  [closed_loop_triggered]  events={r_cl['total_events']:>4d} "
              f"L={r_cl['event_count_L']} R={r_cl['event_count_R']} "
              f"mean_IEI={r_cl['mean_inter_event_interval']:.0f} "
              f"wL1={r_cl['final_weight_l1']:.8f}")
        print(f"    ΔwL1(vs poisson)={delta_w:>+.4e}  "
              f"overlap_with_poisson≈{n_overlap}")
        all_results.append(r_cl)

        # Arm 3: matched_time_shuffle
        shuffle_rng = np.random.default_rng(20260504 + seed * 10 + 3)
        r_ms = _run_time_shuffle_arm(
            config_base, args.steps,
            r_cl["event_log"], shuffle_rng,
            args.snapshot_interval,
        )
        delta_w_ms = r_ms["final_weight_l1"] - r_ol["final_weight_l1"]
        print(f"  [matched_time_shuffle]    events={r_ms['total_events']:>4d} "
              f"L={r_ms['event_count_L']} R={r_ms['event_count_R']} "
              f"mean_IEI={r_ms['mean_inter_event_interval']:.0f} "
              f"wL1={r_ms['final_weight_l1']:.8f}")
        print(f"    ΔwL1(vs poisson)={delta_w_ms:>+.4e}")
        all_results.append(r_ms)

        # Arm 4: circular_shift
        shift_amount = args.steps // 2
        r_cs = _run_circular_shift_arm(
            config_base, args.steps,
            r_cl["event_log"], shift_amount,
            args.snapshot_interval,
        )
        delta_w_cs = r_cs["final_weight_l1"] - r_ol["final_weight_l1"]
        print(f"  [circular_shift]          events={r_cs['total_events']:>4d} "
              f"L={r_cs['event_count_L']} R={r_cs['event_count_R']} "
              f"mean_IEI={r_cs['mean_inter_event_interval']:.0f} "
              f"wL1={r_cs['final_weight_l1']:.8f}")
        print(f"    ΔwL1(vs poisson)={delta_w_cs:>+.4e}")
        all_results.append(r_cs)

    # ── Cross-Arm Delta Vector Comparison ─────────────────────────
    print(f"\n{'='*90}")
    print(f"Phase 8B.4 — Cross-Arm Delta Vector + Timing Summary")
    print(f"{'='*90}")

    print(f"\n{'seed':>5s} {'arm':>25s}  {'events':>7s} {'L':>4s} {'R':>4s} "
          f"{'mean_IEI':>9s} {'wL1':>12s}")
    print("-" * 80)
    for r in all_results:
        print(f"{r['seed']:>5d} {r['arm']:>25s}  {r['total_events']:>7d} "
              f"{r['event_count_L']:>4d} {r['event_count_R']:>4d} "
              f"{r['mean_inter_event_interval']:>9.0f} "
              f"{r['final_weight_l1']:>12.8f}")

    print(f"\n--- Cross-Arm Delta Vector Comparison ---")
    print(f"{'seed':>5s} {'arm_pair':>30s} "
          f"{'cos':>12s} {'|L1|':>12s} {'|L2|':>12s}")
    print("-" * 75)

    for seed in args.seeds:
        seed_results = [r for r in all_results if r["seed"] == seed]
        arms = {r["arm"]: r for r in seed_results}
        cl = arms.get("closed_loop_triggered")
        ol = arms.get("open_loop_poisson")
        ms = arms.get("matched_time_shuffle")
        cs = arms.get("circular_shift")

        def _cos(a, b):
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

        def _pair(name_a, name_b, arm_a, arm_b):
            if arm_a is None or arm_b is None:
                return
            dv_a = np.array(arm_a["readout"]["delta_vector"])
            dv_b = np.array(arm_b["readout"]["delta_vector"])
            c = _cos(dv_a, dv_b)
            l1 = float(np.mean(np.abs(dv_a - dv_b)))
            l2 = float(np.sqrt(np.mean((dv_a - dv_b) ** 2)))
            print(f"{seed:>5d} {f'{name_a} vs {name_b}':>30s}  "
                  f"{c:>12.6f} {l1:>12.6e} {l2:>12.6e}")

        _pair("closed_loop_triggered", "open_loop_poisson", cl, ol)
        _pair("closed_loop_triggered", "matched_time_shuffle", cl, ms)
        _pair("closed_loop_triggered", "circular_shift", cl, cs)
        _pair("matched_time_shuffle", "open_loop_poisson", ms, ol)
        _pair("circular_shift", "open_loop_poisson", cs, ol)
        _pair("matched_time_shuffle", "circular_shift", ms, cs)

    # ── Regional Readout ──────────────────────────────────────────
    print(f"\n--- Regional Structural Readout ---")
    print(f"{'seed':>5s} {'arm':>25s}  {'global_l1':>12s} {'signed':>10s} "
          f"{'L→L':>10s} {'R→R':>10s} {'L→R':>10s} {'R→L':>10s} "
          f"{'within':>10s} {'cross':>10s}")
    print("-" * 120)
    for r in all_results:
        ro = r.get("readout")
        if not ro:
            continue
        reg = ro["regional"]
        agg = ro["aggregated"]
        def _r(k):
            return f"{reg.get(k, {}).get('l1', 0):.6f}" if k in reg else "N/A"
        print(f"{r['seed']:>5d} {r['arm']:>25s}  "
              f"{ro['global_l1']:>12.6e} {ro['signed_mean']:>+10.3e} "
              f"{_r('L→L'):>10s} {_r('R→R'):>10s} {_r('L→R'):>10s} {_r('R→L'):>10s} "
              f"{agg['within_region_l1']:.6f} {agg['cross_region_l1']:.6f}")

    # ── Save ─────────────────────────────────────────────────────
    if args.output_csv:
        _save_csv(all_results, args.output_csv)
    if args.summary_json:
        _save_summary_json(all_results, args.summary_json, {
            "steps": args.steps, "seeds": args.seeds,
            "threshold_percentile": args.threshold_percentile,
            "sustained_window": args.sustained_window,
            "refractory": args.refractory,
            "event_duration": args.event_duration,
            "poisson_mean_interval": args.poisson_mean_interval,
        })

    print(f"\nDone. {len(all_results)} arm-runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
