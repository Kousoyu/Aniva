"""Phase 9A: Temporal Eligibility Trace — Smoke Test.

Compares temporal_plasticity_enabled=False (baseline) vs True (eligibility)
using the Phase 8B.4 state-triggered timing experiment structure.

Two arms per mode:
  open_loop_poisson:    Poisson-distributed events, no state feedback
  closed_loop_triggered: Events fire when |lr_imbalance| crosses threshold

Key question:
  Does eligibility trace break the cos=1.0 lock between closed_loop_triggered
  and open_loop_poisson delta vectors?

Language discipline: no "preference", "reward", "choice", "agent".
"""
import argparse, csv, json, sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

EVENT_DURATION = 80
REFRACTORY = 400
SUSTAINED_WINDOW = 100
POISSON_MEAN_INTERVAL = 200
CALIB_STEPS = 2000
THRESHOLD_PERCENTILE = 85
SMOOTHING_ALPHA = 0.1


def _compute_imbalance(core: LifeCore) -> tuple[float, float, float]:
    left_acts = [u.activation for uid, u in core.units.items() if u.position[0] < 0]
    right_acts = [u.activation for uid, u in core.units.items() if u.position[0] > 0]
    left_mean = float(np.mean(left_acts)) if left_acts else 0.0
    right_mean = float(np.mean(right_acts)) if right_acts else 0.0
    return left_mean, right_mean, left_mean - right_mean


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
    n_conns = len(deltas)

    pos_mask = deltas > 0; neg_mask = deltas < 0
    regional = {}
    for reg in unique_regions:
        mask = np.array([r == reg for r in regions])
        reg_deltas = deltas[mask]
        regional[reg] = {
            "count": int(np.sum(mask)),
            "l1": float(np.mean(np.abs(reg_deltas))) if len(reg_deltas) > 0 else 0.0,
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
        "regional": regional,
        "aggregated": {
            "L_incoming_l1": _safe_mean(abs_deltas, l_in),
            "L_outgoing_l1": _safe_mean(abs_deltas, l_out),
            "R_incoming_l1": _safe_mean(abs_deltas, r_in),
            "R_outgoing_l1": _safe_mean(abs_deltas, r_out),
            "within_region_l1": _safe_mean(abs_deltas, within),
            "cross_region_l1": _safe_mean(abs_deltas, cross),
        },
        "delta_vector": deltas.tolist(),
        "n_connections": n_conns,
    }


def _calibrate_threshold(config: AnivaConfig, percentile: float, rng: np.random.Generator) -> float:
    core = LifeCore(config)
    imbalances = []
    for step in range(CALIB_STEPS):
        core.step(env_influences=None)
        if step >= 500:
            _, _, imb = _compute_imbalance(core)
            imbalances.append(abs(imb))
    return float(np.percentile(imbalances, percentile))


def _poisson_event_generator(total_steps, mean_interval, p_L, rng):
    p = 1.0 / mean_interval
    events = []
    for step in range(total_steps):
        if rng.random() < p:
            label = "L" if rng.random() < p_L else "R"
            stim = L_STIM if label == "L" else R_STIM
            events.append({"step": step, "chosen": label, "stimulus": stim, "duration": EVENT_DURATION})
    return events


def _run_poisson_arm(config: AnivaConfig, total_steps: int,
                     event_stream: list[dict], snapshot_interval: int) -> dict:
    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)
    event_log: list[dict] = []
    all_events: list[StimulusEvent] = []

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

    return {
        "arm": "open_loop_poisson",
        "event_log": event_log,
        "total_events": len(event_log),
        "event_count_L": sum(1 for e in event_log if e["chosen"] == "L"),
        "event_count_R": sum(1 for e in event_log if e["chosen"] == "R"),
        "final_weight_l1": float(np.mean(np.abs(
            np.array([c.weight for c in core.connections]) - weights_initial
        ))),
        "readout": _compute_structural_readout(core, weights_initial),
    }


def _run_triggered_arm(config: AnivaConfig, total_steps: int,
                       threshold: float, sustained_window: int, refractory: int,
                       snapshot_interval: int) -> dict:
    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)
    event_log: list[dict] = []
    all_events: list[StimulusEvent] = []

    smoothed_imb = 0.0
    sustained_count = 0
    steps_since_last_event = refractory

    for step in range(total_steps):
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

        _, _, raw_imb = _compute_imbalance(core)
        smoothed_imb = SMOOTHING_ALPHA * raw_imb + (1 - SMOOTHING_ALPHA) * smoothed_imb

        steps_since_last_event += 1
        if abs(smoothed_imb) > threshold:
            sustained_count += 1
        else:
            sustained_count = 0

        if sustained_count >= sustained_window and steps_since_last_event >= refractory:
            stim = R_STIM if smoothed_imb > 0 else L_STIM
            label = "R" if smoothed_imb > 0 else "L"
            ev = StimulusEvent(stimulus=stim, start_step=step, duration_steps=EVENT_DURATION)
            all_events.append(ev)
            event_log.append({"step": step, "chosen": label, "duration": EVENT_DURATION})
            sustained_count = 0
            steps_since_last_event = 0

    return {
        "arm": "closed_loop_triggered",
        "event_log": event_log,
        "total_events": len(event_log),
        "event_count_L": sum(1 for e in event_log if e["chosen"] == "L"),
        "event_count_R": sum(1 for e in event_log if e["chosen"] == "R"),
        "final_weight_l1": float(np.mean(np.abs(
            np.array([c.weight for c in core.connections]) - weights_initial
        ))),
        "readout": _compute_structural_readout(core, weights_initial),
    }


def _save_results_json(results: list[dict], path: str, params: dict) -> None:
    summary = {"experiment": "phase9A_eligibility_smoke", "params": params, "arms": []}
    for r in results:
        arm_entry = {
            "seed": r["seed"], "arm": r["arm"], "temporal": r["temporal"],
            "event_count_L": r["event_count_L"],
            "event_count_R": r["event_count_R"],
            "total_events": r["total_events"],
            "final_weight_l1": r["final_weight_l1"],
        }
        ro = r.get("readout")
        if ro:
            arm_entry["readout"] = {
                "global_l1": ro["global_l1"],
                "signed_mean": ro["signed_mean"],
                "regional": ro["regional"],
                "aggregated": ro["aggregated"],
            }
        summary["arms"].append(arm_entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 9A: Eligibility Trace Smoke Test")
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 999])
    parser.add_argument("--temporal-beta", type=float, default=0.5,
                        help="temporal_plasticity_rate (eligibility weight)")
    parser.add_argument("--temporal-decay", type=float, default=0.05,
                        help="temporal_trace_decay (EMA rate)")
    parser.add_argument("--output-json", type=str,
                        default="results/phase9A_eligibility_smoke.json")
    parser.add_argument("--no-homeostasis", action="store_true")
    parser.add_argument("--base-rng-seed", type=int, default=20260504)
    args = parser.parse_args(argv)

    print(f"Phase 9A: Eligibility Trace Smoke Test")
    print(f"  steps={args.steps}, seeds={args.seeds}")
    print(f"  temporal_beta={args.temporal_beta}, temporal_decay={args.temporal_decay}")
    print()

    all_results: list[dict] = []

    for temporal_on in [False, True]:
        mode_label = "TEMPORAL ON" if temporal_on else "TEMPORAL OFF (baseline)"
        print(f"{'='*60}")
        print(f"  {mode_label}")
        print(f"{'='*60}")

        for seed in args.seeds:
            config_base = AnivaConfig(unit_count=300)
            config_base.seed = seed
            config_base.homeostasis_enabled = not args.no_homeostasis
            config_base.homeostatic_target_abs_weight = 0.30
            config_base.homeostatic_rate = 1.0
            config_base.temporal_plasticity_enabled = temporal_on
            config_base.temporal_plasticity_rate = args.temporal_beta
            config_base.temporal_trace_decay = args.temporal_decay

            # Calibrate threshold
            calib_rng = np.random.default_rng(args.base_rng_seed)
            threshold = _calibrate_threshold(config_base, THRESHOLD_PERCENTILE, calib_rng)

            # Poisson stream (same for both modes per seed)
            poisson_rng = np.random.default_rng(args.base_rng_seed + seed)
            poisson_stream = _poisson_event_generator(
                args.steps, POISSON_MEAN_INTERVAL, 0.5, poisson_rng,
            )

            # Arm 1: open_loop_poisson
            r_ol = _run_poisson_arm(config_base, args.steps, poisson_stream, 2000)
            r_ol["seed"] = seed
            r_ol["temporal"] = temporal_on
            all_results.append(r_ol)

            # Arm 2: closed_loop_triggered
            config_base.seed = seed  # re-seed for identical init
            r_cl = _run_triggered_arm(
                config_base, args.steps, threshold, SUSTAINED_WINDOW, REFRACTORY, 2000,
            )
            r_cl["seed"] = seed
            r_cl["temporal"] = temporal_on
            all_results.append(r_cl)

            # Delta vector comparison
            dv_ol = np.array(r_ol["readout"]["delta_vector"])
            dv_cl = np.array(r_cl["readout"]["delta_vector"])
            na, nb = np.linalg.norm(dv_ol), np.linalg.norm(dv_cl)
            cos_val = float(np.dot(dv_ol, dv_cl) / (na * nb)) if na > 0 and nb > 0 else 0.0
            l1_dist = float(np.mean(np.abs(dv_ol - dv_cl)))

            print(f"  seed={seed:>4d}  "
                  f"ol_events={r_ol['total_events']:>4d}  "
                  f"cl_events={r_cl['total_events']:>4d}  "
                  f"cos(ol,cl)={cos_val:.8f}  "
                  f"|ol-cl|_L1={l1_dist:.6e}  "
                  f"ΔwL1={r_cl['final_weight_l1'] - r_ol['final_weight_l1']:>+.4e}")

        print()

    # Summary comparison
    print(f"{'='*80}")
    print(f"Cross-Mode Comparison: TEMPORAL OFF vs ON")
    print(f"{'='*80}")
    print(f"{'seed':>5s} {'arm':>25s} {'temp_off cos':>14s} {'temp_on cos':>14s} "
          f"{'off |L1|':>12s} {'on |L1|':>12s}")
    print("-" * 80)

    for seed in args.seeds:
        off_ol = next(r for r in all_results if r["seed"] == seed and r["arm"] == "open_loop_poisson" and not r["temporal"])
        off_cl = next(r for r in all_results if r["seed"] == seed and r["arm"] == "closed_loop_triggered" and not r["temporal"])
        on_ol = next(r for r in all_results if r["seed"] == seed and r["arm"] == "open_loop_poisson" and r["temporal"])
        on_cl = next(r for r in all_results if r["seed"] == seed and r["arm"] == "closed_loop_triggered" and r["temporal"])

        def _cos(r_a, r_b):
            a, b = np.array(r_a["readout"]["delta_vector"]), np.array(r_b["readout"]["delta_vector"])
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

        def _l1(r_a, r_b):
            return float(np.mean(np.abs(np.array(r_a["readout"]["delta_vector"]) - np.array(r_b["readout"]["delta_vector"]))))

        cos_off = _cos(off_ol, off_cl)
        cos_on = _cos(on_ol, on_cl)
        l1_off = _l1(off_ol, off_cl)
        l1_on = _l1(on_ol, on_cl)

        print(f"{seed:>5d} {'ol vs cl':>25s} {cos_off:>14.8f} {cos_on:>14.8f} "
              f"{l1_off:>12.6e} {l1_on:>12.6e}")

        # Also compare on vs off for the SAME arm
        for arm_label in ["open_loop_poisson", "closed_loop_triggered"]:
            r_off = next(r for r in all_results if r["seed"] == seed and r["arm"] == arm_label and not r["temporal"])
            r_on = next(r for r in all_results if r["seed"] == seed and r["arm"] == arm_label and r["temporal"])
            cos_mode = _cos(r_off, r_on)
            l1_mode = _l1(r_off, r_on)
            print(f"{seed:>5d} {'  same arm: '+arm_label:>25s} {'':>14s} {cos_mode:>14.8f} "
                  f"{'':>12s} {l1_mode:>12.6e}")

    # Save
    if args.output_json:
        _save_results_json(all_results, args.output_json, {
            "steps": args.steps, "seeds": args.seeds,
            "temporal_beta": args.temporal_beta,
            "temporal_decay": args.temporal_decay,
            "threshold_percentile": THRESHOLD_PERCENTILE,
            "sustained_window": SUSTAINED_WINDOW,
            "refractory": REFRACTORY,
        })
    print(f"\nDone. {len(all_results)} arm-runs saved to {args.output_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
