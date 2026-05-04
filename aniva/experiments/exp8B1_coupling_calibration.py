"""Phase 8B.1: Closed-Loop Coupling Calibration.

Three tuning knives:
  1. Event density:    event_interval 200 → 100 → 50
  2. Event duration:   event_duration 80 → 150 → 240
  3. Matched shuffle:  post-hoc L/R label shuffle from closed_loop sequence

Four configs:
  A: interval=200, duration=80   (8B baseline)
  B: interval=100, duration=80
  C: interval=100, duration=150
  D: interval=50,  duration=150

Three arms per config:
  open_loop:        base event stream as-is
  closed_loop:      state-biased overrides (same mechanism as 8B)
  matched_shuffle:  closed_loop's exact event positions + L/R counts,
                    but L/R labels shuffled → decouples state timing from label

Language discipline: no "preference", "choice", "reward", "agent".
"""
import argparse, csv, json, sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

# ── Stimulus definitions ─────────────────────────────────────────────

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

# ── Config definitions ───────────────────────────────────────────────

CONFIGS = {
    "A": {"event_interval": 200, "event_duration": 80},
    "B": {"event_interval": 100, "event_duration": 80},
    "C": {"event_interval": 100, "event_duration": 150},
    "D": {"event_interval": 50,  "event_duration": 150},
}

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
    energy_mean = float(np.mean(core._energies))

    hist, _ = np.histogram(all_acts, bins=20, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    hist_sum = hist.sum()
    if hist_sum > 0:
        hist = hist / hist_sum
    hist = hist[hist > 0]
    act_entropy = float(-np.sum(hist * np.log(hist))) if len(hist) > 0 else 0.0

    return {
        "left_mean": left_mean,
        "right_mean": right_mean,
        "lr_imbalance": lr_imbalance,
        "energy_mean": energy_mean,
        "act_entropy": act_entropy,
    }


def _compute_bias(lr_imbalance: float, gain: float, max_bias: float) -> float:
    bias = gain * lr_imbalance
    return float(np.clip(bias, -max_bias, max_bias))


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


# ── Structural readout ───────────────────────────────────────────────

def _classify_connection(source_pos, target_pos):
    """Classify a connection by region of source and target.
    L: x < -0.1, R: x > 0.1, M (midline): otherwise.
    """
    src = "L" if source_pos[0] < -0.1 else ("R" if source_pos[0] > 0.1 else "M")
    tgt = "L" if target_pos[0] < -0.1 else ("R" if target_pos[0] > 0.1 else "M")
    return f"{src}→{tgt}"


def _compute_structural_readout(core, weights_initial) -> dict:
    """Per-connection weight delta decomposition by region.
    Returns a dict with all regional and distribution metrics.
    """
    connections = list(core.connections)
    weights_final = np.array([c.weight for c in connections], dtype=np.float64)
    deltas = weights_final - weights_initial

    # Build region classification
    regions = []
    for conn in connections:
        src_pos = core.units[conn.source_id].position
        tgt_pos = core.units[conn.target_id].position
        regions.append(_classify_connection(src_pos, tgt_pos))

    unique_regions = sorted(set(regions))

    # ── Global metrics ────────────────────────────────────────────
    abs_deltas = np.abs(deltas)
    global_l1 = float(np.mean(abs_deltas))

    signed_mean = float(np.mean(deltas))
    pos_mask = deltas > 0
    neg_mask = deltas < 0
    pos_mass = float(np.sum(deltas[pos_mask])) if pos_mask.any() else 0.0
    neg_mass = float(np.sum(np.abs(deltas[neg_mask]))) if neg_mask.any() else 0.0

    # Top-k mass concentration
    sorted_abs = np.sort(abs_deltas)[::-1]
    n_conns = len(deltas)
    top1_pct = float(np.sum(sorted_abs[:max(1, int(n_conns * 0.01))]))
    top5_pct = float(np.sum(sorted_abs[:max(1, int(n_conns * 0.05))]))
    top10_pct = float(np.sum(sorted_abs[:max(1, int(n_conns * 0.10))]))
    total_mass = float(np.sum(sorted_abs))

    # ── Regional decomposition ────────────────────────────────────
    regional = {}
    for reg in unique_regions:
        mask = np.array([r == reg for r in regions])
        reg_deltas = deltas[mask]
        regional[reg] = {
            "count": int(np.sum(mask)),
            "l1": float(np.mean(np.abs(reg_deltas))) if len(reg_deltas) > 0 else 0.0,
            "signed_mean": float(np.mean(reg_deltas)) if len(reg_deltas) > 0 else 0.0,
            "pos_mass": float(np.sum(reg_deltas[reg_deltas > 0])) if np.any(reg_deltas > 0) else 0.0,
            "neg_mass": float(np.sum(np.abs(reg_deltas[reg_deltas < 0]))) if np.any(reg_deltas < 0) else 0.0,
        }

    # L/R aggregated by direction
    l_in_mask = np.array(["→L" in r for r in regions])
    l_out_mask = np.array(["L→" in r for r in regions])
    r_in_mask = np.array(["→R" in r for r in regions])
    r_out_mask = np.array(["R→" in r for r in regions])

    aggregated = {
        "L_incoming_l1": float(np.mean(abs_deltas[l_in_mask])) if l_in_mask.any() else 0.0,
        "L_outgoing_l1": float(np.mean(abs_deltas[l_out_mask])) if l_out_mask.any() else 0.0,
        "R_incoming_l1": float(np.mean(abs_deltas[r_in_mask])) if r_in_mask.any() else 0.0,
        "R_outgoing_l1": float(np.mean(abs_deltas[r_out_mask])) if r_out_mask.any() else 0.0,
        "L_incoming_signed": float(np.mean(deltas[l_in_mask])) if l_in_mask.any() else 0.0,
        "L_outgoing_signed": float(np.mean(deltas[l_out_mask])) if l_out_mask.any() else 0.0,
        "R_incoming_signed": float(np.mean(deltas[r_in_mask])) if r_in_mask.any() else 0.0,
        "R_outgoing_signed": float(np.mean(deltas[r_out_mask])) if r_out_mask.any() else 0.0,
    }

    # Within-region vs cross-region
    within_mask = np.array([r in ("L→L", "R→R") for r in regions])
    cross_mask = np.array([r in ("L→R", "R→L") for r in regions])
    aggregated["within_region_l1"] = float(np.mean(abs_deltas[within_mask])) if within_mask.any() else 0.0
    aggregated["within_region_signed"] = float(np.mean(deltas[within_mask])) if within_mask.any() else 0.0
    aggregated["cross_region_l1"] = float(np.mean(abs_deltas[cross_mask])) if cross_mask.any() else 0.0
    aggregated["cross_region_signed"] = float(np.mean(deltas[cross_mask])) if cross_mask.any() else 0.0

    # ── Distribution statistics ───────────────────────────────────
    p50 = float(np.percentile(abs_deltas, 50))
    p95 = float(np.percentile(abs_deltas, 95))
    p99 = float(np.percentile(abs_deltas, 99))

    return {
        "global_l1": global_l1,
        "signed_mean": signed_mean,
        "pos_mass": pos_mass,
        "neg_mass": neg_mass,
        "top1pct_mass": top1_pct,
        "top5pct_mass": top5_pct,
        "top10pct_mass": top10_pct,
        "total_abs_mass": total_mass,
        "top1pct_frac": float(top1_pct / total_mass) if total_mass > 0 else 0.0,
        "top5pct_frac": float(top5_pct / total_mass) if total_mass > 0 else 0.0,
        "regional": regional,
        "aggregated": aggregated,
        "dist_p50": p50,
        "dist_p95": p95,
        "dist_p99": p99,
        "dist_max": float(np.max(abs_deltas)),
        "dist_std": float(np.std(deltas)),
        # Raw deltas for arm-to-arm comparison
        "delta_vector": deltas.tolist(),
        "n_connections": n_conns,
    }


# ── Run one arm (open_loop / closed_loop) ───────────────────────────

def _run_arm(
    config: AnivaConfig, arm: str, total_steps: int,
    event_duration: int, base_p_L: float,
    feedback_gain: float, max_bias: float,
    feedback_interval: int, snapshot_interval: int,
    base_stream: list[dict], override_rng: np.random.Generator,
) -> dict:
    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    bias_history: list[float] = []
    all_events: list[StimulusEvent] = []
    event_log: list[dict] = []

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

            if arm == "open_loop":
                chosen_stim = base_event["stimulus"]
                chosen_label = base_event["chosen"]
                bias = 0.0
            elif arm == "closed_loop":
                state = _compute_state_summary(core)
                bias = _compute_bias(state["lr_imbalance"], feedback_gain, max_bias)
                override_prob = min(abs(bias), 1.0)
                if override_rng.random() < override_prob:
                    p_L = float(np.clip(base_p_L - bias, 0.05, 0.95))
                    if override_rng.random() < p_L:
                        chosen_stim, chosen_label = L_STIM, "L"
                    else:
                        chosen_stim, chosen_label = R_STIM, "R"
                else:
                    chosen_stim = base_event["stimulus"]
                    chosen_label = base_event["chosen"]
            else:
                raise ValueError(f"Unknown arm: {arm}")

            bias_history.append(bias)
            event = StimulusEvent(
                stimulus=chosen_stim, start_step=step, duration_steps=event_duration,
            )
            all_events.append(event)
            event_log.append({
                "step": step, "chosen": chosen_label,
                "base_chosen": base_event["chosen"],
                "overridden": chosen_label != base_event["chosen"],
                "bias": bias,
            })

        # Apply active event influences
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

        # Snapshot
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
    total = n_L + n_R if (n_L + n_R) > 0 else 1

    return {
        "arm": arm, "seed": config.seed,
        "snapshots": snapshots, "event_log": event_log,
        "bias_history": bias_history,
        "final_weight_l1": final_weight_l1,
        "event_count_L": n_L, "event_count_R": n_R,
        "events_overridden": sum(1 for e in event_log if e.get("overridden")),
        "event_L_fraction": n_L / total,
        "final_mean_activation": float(np.mean([u.activation for u in core.units.values()])),
        "readout": _compute_structural_readout(core, weights_initial),
    }


# ── Run matched_shuffle arm (replay with shuffled labels) ───────────

def _run_matched_shuffle_arm(
    config: AnivaConfig, total_steps: int,
    event_duration: int, feedback_interval: int,
    snapshot_interval: int, cl_event_log: list[dict],
    shuffle_rng: np.random.Generator,
) -> dict:
    """Replay closed_loop's event positions with shuffled L/R labels.

    Same event positions (steps), same total L/R counts, same durations.
    Only the assignment of which position gets L vs R is shuffled.
    No feedback loop — this is a pure replay arm.
    """
    # Collect L/R labels from closed_loop's event log
    labels = [e["chosen"] for e in cl_event_log]
    steps_list = [e["step"] for e in cl_event_log]
    durations_list = [event_duration] * len(labels)

    # Shuffle labels
    shuffled_labels = labels.copy()
    shuffle_rng.shuffle(shuffled_labels)

    # Build fixed event schedule
    fixed_schedule = []
    for step, label in zip(steps_list, shuffled_labels):
        stim = L_STIM if label == "L" else R_STIM
        fixed_schedule.append({
            "step": step, "chosen": label, "stimulus": stim, "duration": event_duration,
        })

    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    all_events: list[StimulusEvent] = []
    event_log: list[dict] = []

    schedule_idx = 0
    for step in range(total_steps):
        # Check if there's an event scheduled at this step
        while schedule_idx < len(fixed_schedule) and fixed_schedule[schedule_idx]["step"] <= step:
            se = fixed_schedule[schedule_idx]
            if se["step"] == step:
                event = StimulusEvent(
                    stimulus=se["stimulus"], start_step=step, duration_steps=se["duration"],
                )
                all_events.append(event)
                event_log.append({"step": step, "chosen": se["chosen"], "overridden": False, "bias": 0.0})
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
    total = n_L + n_R if (n_L + n_R) > 0 else 1

    return {
        "arm": "matched_shuffle", "seed": config.seed,
        "snapshots": snapshots, "event_log": event_log,
        "bias_history": [],
        "final_weight_l1": final_weight_l1,
        "event_count_L": n_L, "event_count_R": n_R,
        "events_overridden": 0,
        "event_L_fraction": n_L / total,
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
            })
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _save_summary_json(results: list[dict], path: str, params: dict) -> None:
    summary = {"experiment": "phase8B1_coupling_calibration", "params": params, "arms": []}
    for r in results:
        summary["arms"].append({
            "seed": r["seed"], "arm": r["arm"],
            "config": r.get("config_label", ""),
            "event_count_L": r["event_count_L"],
            "event_count_R": r["event_count_R"],
            "event_L_fraction": r["event_L_fraction"],
            "final_weight_l1": r["final_weight_l1"],
            "mean_lr_imbalance": float(np.mean([
                s["lr_imbalance"] for s in r["snapshots"]
            ])) if r["snapshots"] else None,
            "final_mean_activation": r["final_mean_activation"],
        })
        # Add structural readout (exclude raw delta_vector for file size)
        ro = r.get("readout")
        if ro:
            summary["arms"][-1]["readout"] = {
                "global_l1": ro["global_l1"],
                "signed_mean": ro["signed_mean"],
                "pos_mass": ro["pos_mass"],
                "neg_mass": ro["neg_mass"],
                "top1pct_frac": ro["top1pct_frac"],
                "top5pct_frac": ro["top5pct_frac"],
                "top10pct_mass": ro["top10pct_mass"],
                "total_abs_mass": ro["total_abs_mass"],
                "regional": ro["regional"],
                "aggregated": ro["aggregated"],
                "dist_p95": ro["dist_p95"],
                "dist_p99": ro["dist_p99"],
                "dist_max": ro["dist_max"],
                "dist_std": ro["dist_std"],
                "n_connections": ro["n_connections"],
            }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)


# ── CLI ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 8B.1: Coupling Calibration")
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 999])
    parser.add_argument("--unit-count", type=int, default=300)
    parser.add_argument("--configs", type=str, nargs="+",
                        default=["A", "B", "C", "D"],
                        help="Config labels: A B C D (or 'all')")
    parser.add_argument("--feedback-gain", type=float, default=2.5)
    parser.add_argument("--max-bias", type=float, default=0.2)
    parser.add_argument("--base-p-L", type=float, default=0.5)
    parser.add_argument("--feedback-interval", type=int, default=200)
    parser.add_argument("--snapshot-interval", type=int, default=None)
    parser.add_argument("--base-rng-seed", type=int, default=20260504)
    parser.add_argument("--output-csv", type=str, default="results/phase8B1_calibration.csv")
    parser.add_argument("--summary-json", type=str, default="results/phase8B1_calibration_summary.json")
    parser.add_argument("--no-homeostasis", action="store_true")
    parser.add_argument("--no-numba", action="store_true")
    args = parser.parse_args(argv)

    if "all" in args.configs:
        args.configs = ["A", "B", "C", "D"]

    if args.snapshot_interval is None:
        args.snapshot_interval = max(args.steps // 10, 200)

    config_base = AnivaConfig(unit_count=args.unit_count)
    config_base.homeostasis_enabled = not args.no_homeostasis
    config_base.use_numba_plasticity = not args.no_numba
    config_base.homeostatic_target_abs_weight = 0.30
    config_base.homeostatic_rate = 1.0

    print(f"Phase 8B.1: Closed-Loop Coupling Calibration")
    print(f"  configs={args.configs}, seeds={args.seeds}, steps={args.steps}")
    print(f"  gain={args.feedback_gain}, max_bias={args.max_bias}")
    print(f"  homeostasis={config_base.homeostasis_enabled}, numba={config_base.use_numba_plasticity}")

    all_results: list[dict] = []
    all_config_params: dict[str, dict] = {}

    for cfg_label in args.configs:
        cfg = CONFIGS[cfg_label]
        event_interval = cfg["event_interval"]
        event_duration = cfg["event_duration"]

        print(f"\n{'#'*70}")
        print(f"Config {cfg_label}: interval={event_interval}, duration={event_duration}")
        print(f"{'#'*70}")

        for seed in args.seeds:
            config_base.seed = seed
            print(f"\n  --- Seed {seed} ---")

            base_rng = np.random.default_rng(args.base_rng_seed)
            base_stream = _pre_generate_base_stream(
                args.steps, event_interval, args.base_p_L, event_duration, base_rng,
            )
            base_L = sum(1 for be in base_stream if be["chosen"] == "L")
            base_R = len(base_stream) - base_L
            print(f"  base_stream: {len(base_stream)} events, L={base_L}, R={base_R}")

            override_rng_ol = np.random.default_rng(args.base_rng_seed + seed * 10 + 0)
            override_rng_cl = np.random.default_rng(args.base_rng_seed + seed * 10 + 1)

            # Arm 1: open_loop
            r_ol = _run_arm(
                config_base, "open_loop", args.steps,
                event_duration, args.base_p_L,
                args.feedback_gain, args.max_bias,
                args.feedback_interval, args.snapshot_interval,
                base_stream, override_rng_ol,
            )
            r_ol["config_label"] = cfg_label
            print(f"  [open_loop]        L={r_ol['event_count_L']:>4d} R={r_ol['event_count_R']:>4d} "
                  f"L_frac={r_ol['event_L_fraction']:.4f} wL1={r_ol['final_weight_l1']:.8f}")
            all_results.append(r_ol)

            # Arm 2: closed_loop
            r_cl = _run_arm(
                config_base, "closed_loop", args.steps,
                event_duration, args.base_p_L,
                args.feedback_gain, args.max_bias,
                args.feedback_interval, args.snapshot_interval,
                base_stream, override_rng_cl,
            )
            r_cl["config_label"] = cfg_label
            delta_L = r_cl["event_L_fraction"] - r_ol["event_L_fraction"]
            delta_w = r_cl["final_weight_l1"] - r_ol["final_weight_l1"]
            print(f"  [closed_loop]      L={r_cl['event_count_L']:>4d} R={r_cl['event_count_R']:>4d} "
                  f"L_frac={r_cl['event_L_fraction']:.4f} wL1={r_cl['final_weight_l1']:.8f}")
            print(f"    ΔL_frac={delta_L:>+.4f}  ΔwL1={delta_w:>+.4e}  "
                  f"overridden={r_cl['events_overridden']}")
            all_results.append(r_cl)

            # Arm 3: matched_shuffle (from closed_loop's event log)
            shuffle_rng = np.random.default_rng(args.base_rng_seed + seed * 10 + 3)
            r_ms = _run_matched_shuffle_arm(
                config_base, args.steps, event_duration,
                args.feedback_interval, args.snapshot_interval,
                r_cl["event_log"], shuffle_rng,
            )
            r_ms["config_label"] = cfg_label
            delta_L_ms = r_ms["event_L_fraction"] - r_ol["event_L_fraction"]
            delta_w_ms = r_ms["final_weight_l1"] - r_ol["final_weight_l1"]
            print(f"  [matched_shuffle]  L={r_ms['event_count_L']:>4d} R={r_ms['event_count_R']:>4d} "
                  f"L_frac={r_ms['event_L_fraction']:.4f} wL1={r_ms['final_weight_l1']:.8f}")
            print(f"    ΔL_frac={delta_L_ms:>+.4f}  ΔwL1={delta_w_ms:>+.4e}")

            # Separation check: closed_loop vs matched_shuffle
            sep = abs(r_cl["event_L_fraction"] - r_ms["event_L_fraction"])
            print(f"    cl-ms separation: {sep:.4f}")

            all_results.append(r_ms)

    # ── Cross-config comparison ────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"Phase 8B.1 — Cross-Config Comparison")
    print(f"{'='*100}")

    # Build per-config, per-seed summary
    print(f"\n{'config':>6s} {'seed':>5s} {'arm':>20s}  "
          f"{'events':>7s} {'L_frac':>7s} {'ΔL_frac':>9s} "
          f"{'wL1':>12s} {'ΔwL1':>10s} {'cl-ms_sep':>12s}")
    print("-" * 105)

    config_summary: dict[str, dict] = {}

    for cfg_label in args.configs:
        cfg_results = [r for r in all_results if r.get("config_label") == cfg_label]
        for seed in args.seeds:
            seed_results = [r for r in cfg_results if r["seed"] == seed]
            arms = {r["arm"]: r for r in seed_results}
            ol = arms.get("open_loop")
            cl = arms.get("closed_loop")
            ms = arms.get("matched_shuffle")

            if ol and cl:
                dL_cl = cl["event_L_fraction"] - ol["event_L_fraction"]
                dw_cl = cl["final_weight_l1"] - ol["final_weight_l1"]
                n_ev = cl["event_count_L"] + cl["event_count_R"]
                cl_ms_sep = abs(cl["event_L_fraction"] - ms["event_L_fraction"]) if ms else 0
                print(f"{cfg_label:>6s} {seed:>5d} {'closed_loop':>20s}  "
                      f"{n_ev:>7d} {cl['event_L_fraction']:>7.4f} {dL_cl:>+9.4f} "
                      f"{cl['final_weight_l1']:>12.8f} {dw_cl:>+10.2e} {'':>12s}")
            if ms and ol:
                dL_ms = ms["event_L_fraction"] - ol["event_L_fraction"]
                dw_ms = ms["final_weight_l1"] - ol["final_weight_l1"]
                print(f"{cfg_label:>6s} {seed:>5d} {'matched_shuffle':>20s}  "
                      f"{'':>7s} {ms['event_L_fraction']:>7.4f} {dL_ms:>+9.4f} "
                      f"{ms['final_weight_l1']:>12.8f} {dw_ms:>+10.2e} {cl_ms_sep:>12.4f}")
            if ol:
                print(f"{cfg_label:>6s} {seed:>5d} {'open_loop':>20s}  "
                      f"{'':>7s} {ol['event_L_fraction']:>7.4f} {'':>9s} "
                      f"{ol['final_weight_l1']:>12.8f} {'':>10s} {'':>12s}")
                print("-" * 105)

            # Track for config ranking
            if cfg_label not in config_summary:
                config_summary[cfg_label] = {"dL_cl": [], "dw_cl": [], "seps": []}
            if ol and cl:
                config_summary[cfg_label]["dL_cl"].append(abs(cl["event_L_fraction"] - ol["event_L_fraction"]))
                config_summary[cfg_label]["dw_cl"].append(abs(cl["final_weight_l1"] - ol["final_weight_l1"]))
                if ms:
                    config_summary[cfg_label]["seps"].append(abs(cl["event_L_fraction"] - ms["event_L_fraction"]))

    # ── Config ranking ─────────────────────────────────────────────
    print(f"\n--- Config Ranking (mean |Δ| across seeds) ---")
    print(f"{'config':>6s} {'mean|ΔL_frac|':>15s} {'mean|ΔwL1|':>14s} {'mean_cl-ms_sep':>17s} {'total_events':>13s}")
    print("-" * 80)
    for cfg_label in args.configs:
        s = config_summary.get(cfg_label, {})
        cfg = CONFIGS[cfg_label]
        n_events_est = args.steps // cfg["event_interval"]
        mean_dL = np.mean(s["dL_cl"]) if s.get("dL_cl") else 0
        mean_dw = np.mean(s["dw_cl"]) if s.get("dw_cl") else 0
        mean_sep = np.mean(s["seps"]) if s.get("seps") else 0
        print(f"{cfg_label:>6s} {mean_dL:>15.4f} {mean_dw:>14.4e} {mean_sep:>17.4f} {n_events_est:>13d}")

    # ── Structural Readout Comparison ────────────────────────────
    print(f"\n--- Structural Readout: Regional Decomposition ---")
    print(f"{'config':>6s} {'seed':>5s} {'arm':>20s}  "
          f"{'L1_global':>10s} {'signed':>10s} "
          f"{'L→L':>10s} {'R→R':>10s} {'L→R':>10s} {'R→L':>10s} "
          f"{'within':>10s} {'cross':>10s}")
    print("-" * 120)

    for r in all_results:
        ro = r.get("readout")
        if not ro:
            continue
        reg = ro["regional"]
        agg = ro["aggregated"]
        def _rl1(k):
            return f"{reg.get(k, {}).get('l1', 0):.6e}" if k in reg else "N/A"
        print(f"{r.get('config_label', ''):>6s} {r['seed']:>5d} {r['arm']:>20s}  "
              f"{ro['global_l1']:>10.6e} {ro['signed_mean']:>+10.3e} "
              f"{_rl1('L→L'):>10s} {_rl1('R→R'):>10s} {_rl1('L→R'):>10s} {_rl1('R→L'):>10s} "
              f"{agg['within_region_l1']:>10.6e} {agg['cross_region_l1']:>10.6e}")

    # Arm-to-arm delta vector comparison
    print(f"\n--- Cross-Arm Delta Vector Comparison ---")
    print(f"{'config':>6s} {'seed':>5s} "
          f"{'cos(cl, ol)':>14s} {'cos(ms, ol)':>14s} {'cos(cl, ms)':>14s} "
          f"{'|cl-ms|_L1':>12s} {'|cl-ms|_L2':>12s}")
    print("-" * 85)

    for cfg_label in args.configs:
        cfg_results = [r for r in all_results if r.get("config_label") == cfg_label]
        for seed in args.seeds:
            seed_results = [r for r in cfg_results if r["seed"] == seed]
            arms = {r["arm"]: r for r in seed_results}
            ol = arms.get("open_loop")
            cl = arms.get("closed_loop")
            ms = arms.get("matched_shuffle")
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
            l1_cl_ms = float(np.mean(np.abs(dv_cl - dv_ms)))
            l2_cl_ms = float(np.sqrt(np.mean((dv_cl - dv_ms) ** 2)))

            print(f"{cfg_label:>6s} {seed:>5d}  "
                  f"{cos_cl_ol:>14.6f} {cos_ms_ol:>14.6f} {cos_cl_ms:>14.6f} "
                  f"{l1_cl_ms:>12.6e} {l2_cl_ms:>12.6e}")

    # ── Save ─────────────────────────────────────────────────────
    if args.output_csv:
        _save_csv(all_results, args.output_csv)
    if args.summary_json:
        _save_summary_json(all_results, args.summary_json, {
            "steps": args.steps, "seeds": args.seeds,
            "configs": args.configs,
            "feedback_gain": args.feedback_gain,
            "max_bias": args.max_bias,
            "base_rng_seed": args.base_rng_seed,
        })

    print(f"\nDone. {len(all_results)} arm-runs across {len(args.configs)} configs x {len(args.seeds)} seeds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
