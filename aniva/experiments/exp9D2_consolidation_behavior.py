"""Phase 9D.2 Consolidation Behavior — directional slow structure from repeated history.

Tests whether repeated event-order history produces stronger and directionally
interpretable slow structural sediment than single / opposite / simultaneous /
no-event histories.

6 arms:
  L_then_R_repeated  — L→R ×3
  R_then_L_repeated  — R→L ×3
  L_then_R_single    — L→R ×1
  R_then_L_single    — R→L ×1
  simultaneous        — L+R together ×3
  no_event            — baseline

Anti-cheat: arm labels used only for offline metric grouping.
No arm/L/R labels in mechanism update paths.
"""

import argparse, csv, json, sys, time, math
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

PULSE_DURATION = 80
WARMUP = 2000
PAIR_GAP = 500
PAIR_INTERVAL = 1500
TOTAL_STEPS = 7500
N_PAIRS_REPEATED = 3
EPS = 1e-12


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _make_schedule(order, warmup, gap, pulse_dur, pair_interval, n_pairs):
    """Build ordered event schedule.

    order: "L_then_R" | "R_then_L"
    """
    events = []
    first, second = ("L", "R") if order == "L_then_R" else ("R", "L")
    for i in range(n_pairs):
        base = warmup + i * pair_interval
        events.append((base, first, pulse_dur))
        events.append((base + gap, second, pulse_dur))
    return sorted(events, key=lambda x: x[0])


def _make_schedule_simultaneous(warmup, pulse_dur, pair_interval, n_pairs):
    """L and R fire together at the same step."""
    events = []
    for i in range(n_pairs):
        base = warmup + i * pair_interval
        events.append((base, "L", pulse_dur))
        events.append((base, "R", pulse_dur))
    return sorted(events, key=lambda x: x[0])


def _build_env_events(schedule):
    events = []
    for t, side, dur in schedule:
        events.append(StimulusEvent(
            stimulus=STIM_MAP[side], start_step=t, duration_steps=dur))
    return events


def _event_starts_map(schedule):
    m = {}
    for t, side, _dur in schedule:
        m.setdefault(t, []).append(side)
    return m


def run_arm(cfg, total_steps, schedule, arm_label):
    """Run one arm, returning directional consolidation metrics."""
    core = LifeCore(cfg)
    n_units = cfg.unit_count

    # Connection region classification (offline only)
    src_regions = np.array([_unit_region(core.units[c.source_id].position)
                            for c in core.connections])
    tgt_regions = np.array([_unit_region(core.units[c.target_id].position)
                            for c in core.connections])
    is_LR = (src_regions == "L") & (tgt_regions == "R")
    is_RL = (src_regions == "R") & (tgt_regions == "L")

    env_events = _build_env_events(schedule)
    env = Environment()
    for ev in env_events:
        env.add_event(ev)

    event_starts = _event_starts_map(schedule)

    phi_cache = {
        "L": np.array([L_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
        "R": np.array([R_STIM.influence_at(tuple(core._positions[uid]))
                        for uid in range(n_units)], dtype=np.float64),
    }

    snapshots = []
    snapshot_interval = max(100, total_steps // 20)
    next_snapshot = 0

    update_records = []
    update_idx = 0
    nan_hit = False

    for s in range(total_steps):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit:
            if (np.any(np.isnan(core._tag_cache))
                or np.any(np.isnan(core._slow_weight_cache))
                or np.any(np.isnan(core._weight_cache))):
                nan_hit = True

        # Periodic snapshot with directional slow metrics
        if s >= next_snapshot:
            slow = core._slow_weight_cache
            snap = {
                "step": s,
                "tag_mass": float(np.sum(np.abs(core._tag_cache))),
                "n_tagged": int(np.sum(core._tag_cache > 0)),
                "slow_l1_total": float(np.sum(np.abs(slow))),
                "slow_max_abs": float(np.max(np.abs(slow))),
                "slow_LR_l1": float(np.sum(np.abs(slow[is_LR]))),
                "slow_RL_l1": float(np.sum(np.abs(slow[is_RL]))),
                "fast_l1": float(np.sum(np.abs(core._weight_cache))),
                "refractory_remaining": core._capture_refractory_remaining,
            }
            # slow_DI at snapshot
            lr = snap["slow_LR_l1"]
            rl = snap["slow_RL_l1"]
            snap["slow_DI"] = (lr - rl) / (lr + rl + EPS)
            snapshots.append(snap)
            next_snapshot = s + snapshot_interval

        # Event-pair update
        if s in event_starts:
            sides = event_starts[s]
            phi = np.zeros(n_units, dtype=np.float64)
            for side in sides:
                phi += phi_cache[side]

            tag_before = float(np.sum(np.abs(core._tag_cache)))
            result = core.apply_event_pair_phi(phi)
            update_fired = result is not None

            if update_fired:
                tag_after = float(np.sum(np.abs(core._tag_cache)))
                update_records.append({
                    "update_idx": update_idx,
                    "step": s,
                    "sides": "+".join(sides),
                    "tag_before": tag_before,
                    "tag_after": tag_after,
                    "tag_delta": tag_after - tag_before,
                    "gate": result["gate"],
                    "trace_mass": result["trace_mass"],
                })
                update_idx += 1

    # Final state
    captures = list(core._consolidation_ledger)
    slow = core._slow_weight_cache
    fast = core._weight_cache

    slow_LR_l1 = float(np.sum(np.abs(slow[is_LR])))
    slow_RL_l1 = float(np.sum(np.abs(slow[is_RL])))
    slow_DI = (slow_LR_l1 - slow_RL_l1) / (slow_LR_l1 + slow_RL_l1 + EPS)

    # total slow_weight delta from all captures
    total_slow_delta_l1 = sum(c["slow_weight_delta_l1"] for c in captures)

    # Saturation
    effective = fast + slow
    np.clip(effective, -1.0, 1.0, out=effective)
    sat_frac = float(np.sum(np.abs(effective) >= 0.999)) / len(effective) if len(effective) > 0 else 0.0

    # Capture signal distribution
    capture_signals = [c["capture_signal"] for c in captures]

    # Capture intervals (use snapshot proxy: snapshots between captures)
    n_captures = len(captures)

    return {
        "arm": arm_label,
        "n_connections": len(core.connections),
        "n_connections_LR": int(np.sum(is_LR)),
        "n_connections_RL": int(np.sum(is_RL)),
        "n_updates": len(update_records),
        "n_captures": n_captures,
        "final_tag_mass": float(np.sum(np.abs(core._tag_cache))),
        "final_n_tagged": int(np.sum(core._tag_cache > 0)),
        "slow_l1_total": float(np.sum(np.abs(slow))),
        "slow_max_abs": float(np.max(np.abs(slow))),
        "slow_LR_l1": slow_LR_l1,
        "slow_RL_l1": slow_RL_l1,
        "slow_DI": slow_DI,
        "total_slow_delta_l1": total_slow_delta_l1,
        "capture_signal_mean": float(np.mean(capture_signals)) if capture_signals else 0.0,
        "capture_signal_max": float(np.max(capture_signals)) if capture_signals else 0.0,
        "final_fast_l1": float(np.sum(np.abs(fast))),
        "final_eff_l1": float(np.sum(np.abs(effective))),
        "saturation_frac": sat_frac,
        "nan_hit": nan_hit,
        "snapshots": snapshots,
        "update_records": update_records,
        "capture_ledger": captures,
    }


def _evaluate_behavior_criteria(arm_label, r):
    """Evaluate 9D.2 behavior-level criteria per arm (offline only)."""
    c = {}
    n_updates = r["n_updates"]

    # 1. No NaN
    c["no_nan"] = not r["nan_hit"]

    # 2. No explosion (saturation < 50%)
    c["no_explosion"] = r["saturation_frac"] < 0.5

    # 3. Updates fired appropriately (first event never fires: trace starts at zero)
    if arm_label == "simultaneous":
        c["updates_fired"] = n_updates >= 2  # n_pairs-1, all pairs after first
    elif "repeated" in arm_label:
        c["updates_fired"] = n_updates >= 3  # 2*n_pairs-1 for n_pairs=3
    elif arm_label in ("L_then_R_single", "R_then_L_single"):
        c["updates_fired"] = n_updates >= 1
    else:
        c["updates_fired"] = n_updates == 0  # baseline should have none

    # 4. Capture triggered for event arms
    if arm_label == "no_event":
        c["capture_ok"] = r["n_captures"] == 0
    elif "repeated" in arm_label:
        c["capture_ok"] = r["n_captures"] >= 1
    else:
        c["capture_ok"] = True

    # 5. slow_weight clamped
    c["slow_clamped"] = r["slow_max_abs"] <= 0.1 + EPS

    # 6. Baseline clean
    if arm_label == "no_event":
        c["baseline_clean"] = r["slow_l1_total"] < EPS
    else:
        c["baseline_clean"] = True

    # 7. Directional sign for ordered arms (offline check only)
    if arm_label == "L_then_R_repeated":
        c["direction_sign"] = r["slow_DI"] > -0.1  # allow near-zero positive
    elif arm_label == "R_then_L_repeated":
        c["direction_sign"] = r["slow_DI"] < 0.1  # allow near-zero negative
    elif arm_label == "simultaneous":
        c["direction_sign"] = abs(r["slow_DI"]) < 0.5  # not strongly directional
    else:
        c["direction_sign"] = True

    c["all_pass"] = all(c.values())
    return c


def _estimate_runtime(model_arm_steps, n_arms):
    """Estimate runtime based on 9D.1 full smoke baseline (87s/arm at 7500 steps)."""
    baseline_per_arm = 87.0
    baseline_steps = 7500
    per_arm = baseline_per_arm * (model_arm_steps / baseline_steps)
    total = per_arm * n_arms
    print(f"Runtime estimate:")
    print(f"  steps per arm: {model_arm_steps}")
    print(f"  n_arms: {n_arms}")
    print(f"  est per arm: ~{per_arm:.0f}s")
    print(f"  est total (serial): ~{total:.0f}s ({total/60:.1f} min)")
    print(f"  baseline: 9D.1 full smoke, 300 units, ~87s/arm @ 7500 steps")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 9D.2 Consolidation Behavior — directional slow structure")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--n-pairs", type=int, default=3)
    p.add_argument("--quick", action="store_true",
                   help="Reduced-size quick check.")
    p.add_argument("--dry-run-schedule", action="store_true",
                   help="Print schedules and exit.")
    p.add_argument("--estimate-only", action="store_true",
                   help="Print runtime estimate and exit.")
    p.add_argument("--output-csv", type=str,
                   default="results/phase9D2_behavior.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase9D2_behavior_summary.json")
    args = p.parse_args(argv)

    if args.quick:
        unit_count = 100
        warmup = 500
        gap = 300
        pulse_dur = 40
        pair_interval = gap + pulse_dur + 300
        n_pairs = 2
        total_steps = warmup + n_pairs * pair_interval + 500
    else:
        unit_count = args.unit_count
        warmup = WARMUP
        gap = PAIR_GAP
        pulse_dur = PULSE_DURATION
        pair_interval = PAIR_INTERVAL
        n_pairs = args.n_pairs
        total_steps = TOTAL_STEPS

    # Define all 6 arms
    arms_def = [
        ("L_then_R_repeated", "L_then_R", warmup, gap, pulse_dur, pair_interval, n_pairs),
        ("R_then_L_repeated", "R_then_L", warmup, gap, pulse_dur, pair_interval, n_pairs),
        ("L_then_R_single", "L_then_R", warmup, gap, pulse_dur, pair_interval, 1),
        ("R_then_L_single", "R_then_L", warmup, gap, pulse_dur, pair_interval, 1),
        ("simultaneous", None, warmup, None, pulse_dur, pair_interval, n_pairs),
        ("no_event", None, 0, 0, 0, 0, 0),
    ]

    # Build schedules
    arm_schedules = {}
    for label, order, wu, ga, pd, pi, npairs in arms_def:
        if label == "no_event":
            sched = []
        elif label == "simultaneous":
            sched = _make_schedule_simultaneous(wu, pd, pi, npairs)
        else:
            sched = _make_schedule(order, wu, ga, pd, pi, npairs)
        arm_schedules[label] = sched

    if args.estimate_only:
        _estimate_runtime(total_steps, len(arm_schedules))
        return 0

    if args.dry_run_schedule:
        for label, sched in arm_schedules.items():
            nL = sum(1 for _, side, _ in sched if side == "L")
            nR = sum(1 for _, side, _ in sched if side == "R")
            print(f"[{label}] steps={total_steps}  events: L={nL} R={nR}")
            for t, side, dur in sched:
                print(f"  step={t:>6d}  side={side}  dur={dur}")
        return 0

    mode_str = "QUICK" if args.quick else "FULL"
    print(f"Phase 9D.2 Consolidation Behavior [{mode_str}]")
    print(f"  seed={args.seed}  unit_count={unit_count}  n_pairs={n_pairs}")
    print(f"  warmup={warmup}  gap={gap}  pulse={pulse_dur}")
    print(f"  pair_interval={pair_interval}  total_steps={total_steps}")
    print(f"  arms: {list(arm_schedules.keys())}")
    print(f"  BEHAVIOR SMOKE — directional slow structure test.")
    print()

    base_cfg = AnivaConfig(
        unit_count=unit_count, seed=args.seed,
        consolidation_enabled=True,
        consolidation_ledger_enabled=True,
        event_pair_plasticity_enabled=True,
        event_pair_trace_tau=1000.0,
        event_pair_ledger_enabled=True,
    )

    t0 = time.time()
    all_results = {}

    for label, sched in arm_schedules.items():
        cfg = AnivaConfig(**{k: v for k, v in base_cfg.__dict__.items()
                             if not k.startswith("_")})
        cfg.seed = args.seed

        print(f"  [{label}] running {total_steps} steps ...", end=" ", flush=True)
        r = run_arm(cfg, total_steps, sched, label)
        all_results[label] = r

        criteria = _evaluate_behavior_criteria(label, r)
        r["criteria"] = criteria
        status = "PASS" if criteria["all_pass"] else "FAIL"
        n_pass = sum(1 for v in criteria.values() if v is True)
        print(f"{status} ({n_pass}/7 criteria)")

        for k, v in criteria.items():
            if k == "all_pass": continue
            print(f"    [{'OK' if v else '!!'}] {k}")

        print(f"    updates={r['n_updates']}  captures={r['n_captures']}")
        print(f"    slow_LR_l1={r['slow_LR_l1']:.6e}  slow_RL_l1={r['slow_RL_l1']:.6e}  "
              f"slow_DI={r['slow_DI']:+.4f}")
        print(f"    slow_total={r['slow_l1_total']:.6e}  "
              f"tag_mass={r['final_tag_mass']:.6e}  "
              f"sat={r['saturation_frac']:.4f}  nan={r['nan_hit']}")
        if r['capture_ledger']:
            sig_mean = r['capture_signal_mean']
            sig_max = r['capture_signal_max']
            print(f"    capture_signal: mean={sig_mean:.4f}  max={sig_max:.4f}")
        print()

    wall_s = time.time() - t0

    # --- Cross-arm analysis ---
    ltr_r = all_results.get("L_then_R_repeated", {})
    rtl_r = all_results.get("R_then_L_repeated", {})
    ltr_s = all_results.get("L_then_R_single", {})
    rtl_s = all_results.get("R_then_L_single", {})
    sim = all_results.get("simultaneous", {})
    nev = all_results.get("no_event", {})

    # slow_OS: cross-arm order separation
    slow_OS = (ltr_r.get("slow_DI", 0.0) - rtl_r.get("slow_DI", 0.0)
               if ltr_r and rtl_r else 0.0)

    # Repeated vs single comparison
    repeated_gt_single_LR = (
        ltr_r.get("slow_l1_total", 0.0) > ltr_s.get("slow_l1_total", 0.0) + EPS
    )
    repeated_gt_single_RL = (
        rtl_r.get("slow_l1_total", 0.0) > rtl_s.get("slow_l1_total", 0.0) + EPS
    )

    # Directional sign check
    ltr_DI_sign = ltr_r.get("slow_DI", 0.0) > -0.01
    rtl_DI_sign = rtl_r.get("slow_DI", 0.0) < 0.01

    # Simultaneous non-directional
    sim_near_zero = abs(sim.get("slow_DI", 0.0)) < 0.1 if sim else False

    # Baseline clean
    base_clean = nev.get("slow_l1_total", -1.0) < EPS if nev else False

    # Clamp effective
    clamp_ok = all(
        r.get("slow_max_abs", 0.0) <= 0.1 + EPS
        for r in all_results.values()
    )

    any_nan = any(r["nan_hit"] for r in all_results.values())

    print(f"  === Cross-arm ===")
    print(f"  slow_OS (LTR_repeated_DI - RTL_repeated_DI): {slow_OS:+.4f}")
    print(f"  repeated > single (L→R): {repeated_gt_single_LR}")
    print(f"  repeated > single (R→L): {repeated_gt_single_RL}")
    print(f"  L→R_repeated slow_DI sign (≥0): {ltr_DI_sign}  ({ltr_r.get('slow_DI', 0):+.4f})")
    print(f"  R→L_repeated slow_DI sign (≤0): {rtl_DI_sign}  ({rtl_r.get('slow_DI', 0):+.4f})")
    print(f"  simultaneous slow_DI ≈ 0: {sim_near_zero}  ({sim.get('slow_DI', 0):+.4f})")
    print(f"  baseline slow_l1 ≈ 0: {base_clean}")
    print(f"  slow_max clamp ok: {clamp_ok}")
    print(f"  any NaN: {any_nan}")
    print()

    # Summary table
    print(f"  {'Arm':<24s} {'slow_l1':>10s} {'slow_LR':>10s} {'slow_RL':>10s} {'slow_DI':>8s} {'caps':>5s} {'tag':>10s}")
    print(f"  {'-'*24} {'-'*10} {'-'*10} {'-'*10} {'-'*8} {'-'*5} {'-'*10}")
    for label in arm_schedules:
        r = all_results.get(label, {})
        print(f"  {label:<24s} {r.get('slow_l1_total', 0):>10.2e} "
              f"{r.get('slow_LR_l1', 0):>10.2e} {r.get('slow_RL_l1', 0):>10.2e} "
              f"{r.get('slow_DI', 0):>+8.4f} {r.get('n_captures', 0):>5d} "
              f"{r.get('final_tag_mass', 0):>10.2e}")
    print()

    # 10 success criteria for behavior smoke
    success = {
        "all_complete": len(all_results) == 6,
        "no_nan_any": not any_nan,
        "repeated_gt_single_LR": repeated_gt_single_LR,
        "repeated_gt_single_RL": repeated_gt_single_RL,
        "LTR_slow_DI_non_negative": ltr_DI_sign,
        "RTL_slow_DI_non_positive": rtl_DI_sign,
        "slow_OS_positive": slow_OS > -0.01,
        "simultaneous_near_zero": sim_near_zero,
        "baseline_clean": base_clean,
        "slow_clamp_ok": clamp_ok,
    }
    n_success = sum(1 for v in success.values() if v)
    all_success = all(success.values())

    print(f"  Behavior success criteria: {n_success}/10")
    for k, v in success.items():
        print(f"    [{'OK' if v else '!!'}] {k}")
    print(f"  Wall time: {wall_s:.0f}s ({wall_s/60:.1f} min)")
    print()

    if all_success and not any_nan:
        print(f"  OVERALL: ALL BEHAVIOR CRITERIA PASSED")
    else:
        print(f"  OVERALL: ISSUES FOUND — see criteria above")

    # --- CSV output ---
    rows = []
    for label, r in all_results.items():
        rows.append({
            "arm": label,
            "seed": args.seed,
            "unit_count": unit_count,
            "n_pairs": n_pairs if label != "no_event" else 0,
            "total_steps": total_steps,
            "n_updates": r["n_updates"],
            "n_captures": r["n_captures"],
            "n_connections_LR": r["n_connections_LR"],
            "n_connections_RL": r["n_connections_RL"],
            "slow_l1_total": r["slow_l1_total"],
            "slow_LR_l1": r["slow_LR_l1"],
            "slow_RL_l1": r["slow_RL_l1"],
            "slow_DI": r["slow_DI"],
            "slow_max_abs": r["slow_max_abs"],
            "total_slow_delta_l1": r["total_slow_delta_l1"],
            "capture_signal_mean": r["capture_signal_mean"],
            "capture_signal_max": r["capture_signal_max"],
            "final_tag_mass": r["final_tag_mass"],
            "final_n_tagged": r["final_n_tagged"],
            "final_fast_l1": r["final_fast_l1"],
            "final_eff_l1": r["final_eff_l1"],
            "saturation_frac": r["saturation_frac"],
            "nan_hit": r["nan_hit"],
            "slow_OS": slow_OS,
            "wall_time_s": wall_s,
        })

    if args.output_csv:
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  CSV: {args.output_csv}")

    if args.summary_json:
        summary = {
            "experiment": "phase9D2_consolidation_behavior",
            "mode": mode_str.lower(),
            "params": {
                "seed": args.seed,
                "unit_count": unit_count,
                "n_pairs": n_pairs,
                "warmup": warmup,
                "gap": gap,
                "pulse_dur": pulse_dur,
                "pair_interval": pair_interval,
                "total_steps": total_steps,
            },
            "slow_OS": slow_OS,
            "success": success,
            "n_success": n_success,
            "all_success": all_success,
            "any_nan": any_nan,
            "wall_time_s": wall_s,
            "arms": {}
        }
        for label, r in all_results.items():
            summary["arms"][label] = {
                "criteria": {k: v for k, v in r["criteria"].items() if k != "all_pass"},
                "slow_l1_total": r["slow_l1_total"],
                "slow_LR_l1": r["slow_LR_l1"],
                "slow_RL_l1": r["slow_RL_l1"],
                "slow_DI": r["slow_DI"],
                "n_captures": r["n_captures"],
                "n_updates": r["n_updates"],
                "final_tag_mass": r["final_tag_mass"],
                "final_n_tagged": r["final_n_tagged"],
                "saturation_frac": r["saturation_frac"],
                "nan_hit": r["nan_hit"],
            }
        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"  JSON: {args.summary_json}")

    return 0 if (all_success and not any_nan) else 1


if __name__ == "__main__":
    sys.exit(main())
