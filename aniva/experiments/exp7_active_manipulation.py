"""Phase 7.6A: time_constant_std Active Manipulation.

Tests whether time_constant heterogeneity is a causal driver of
history-dependent structural divergence (Δ_weight_L1).

Single manipulation: adjust time_constant standard deviation while
preserving mean. Three levels: low_std, baseline, high_std.

Does NOT modify LifeCore / plasticity / dynamics core mechanisms.
Does NOT manipulate L→R connectivity (reserved for Phase 7.6B).
"""

import argparse
import csv
import json
import sys
import time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.observer import Observer
from aniva.environment.environment import Stimulus, StimulusEvent, Environment


# ── Stimulus definitions (same as Phase 7.4) ─────────────────────

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.03, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.03, radius=0.5)


# ── Group definitions ────────────────────────────────────────────

def _build_group_defs(total_steps: int) -> dict:
    """Build group definitions. Stimulus timing: L@300, R@1000, duration=100.

    Same absolute timing as Phase 7.4, independent of total_steps.
    """
    return {
        "A_L": {
            "label": "L then R",
            "events": [
                {"stimulus": L_STIM, "start_step": 300, "duration_steps": 100},
                {"stimulus": R_STIM, "start_step": 1000, "duration_steps": 100},
            ],
            "plasticity_rate": 0.0001,
        },
        "A_R": {
            "label": "R then L",
            "events": [
                {"stimulus": R_STIM, "start_step": 300, "duration_steps": 100},
                {"stimulus": L_STIM, "start_step": 1000, "duration_steps": 100},
            ],
            "plasticity_rate": 0.0001,
        },
        "C": {
            "label": "repeat A_L",
            "events": [
                {"stimulus": L_STIM, "start_step": 300, "duration_steps": 100},
                {"stimulus": R_STIM, "start_step": 1000, "duration_steps": 100},
            ],
            "plasticity_rate": 0.0001,
        },
        "D_L": {
            "label": "plasticity off (L then R)",
            "events": [
                {"stimulus": L_STIM, "start_step": 300, "duration_steps": 100},
                {"stimulus": R_STIM, "start_step": 1000, "duration_steps": 100},
            ],
            "plasticity_rate": 0.0,
        },
        "D_R": {
            "label": "plasticity off (R then L)",
            "events": [
                {"stimulus": R_STIM, "start_step": 300, "duration_steps": 100},
                {"stimulus": L_STIM, "start_step": 1000, "duration_steps": 100},
            ],
            "plasticity_rate": 0.0,
        },
    }


# ── Manipulation ─────────────────────────────────────────────────

# Factor → condition name mapping
TC_STD_CONDITIONS = {
    0.3: "low_std",
    1.0: "baseline",
    2.0: "high_std",
}


def manipulate_time_constant_std(
    core: LifeCore,
    factor: float,
    clamp_range: tuple[float, float] = (0.5, 1.5),
) -> dict:
    """Adjust time_constant dispersion while preserving mean.

    factor < 1.0 → shrink deviations toward mean (lower std)
    factor = 1.0 → no change (baseline)
    factor > 1.0 → expand deviations from mean (higher std)

    Values clamped to clamp_range to avoid dynamics explosion/collapse.
    Modifies core._time_constants in-place.
    """
    tc = core._time_constants
    mean_before = float(np.mean(tc))
    std_before = float(np.std(tc))

    centered = tc - mean_before
    new_tc = mean_before + centered * factor
    lo, hi = clamp_range
    new_tc = np.clip(new_tc, lo, hi)
    tc[:] = new_tc

    return {
        "tc_mean_before": mean_before,
        "tc_std_before": std_before,
        "tc_mean_after": float(np.mean(tc)),
        "tc_std_after": float(np.std(tc)),
        "factor": factor,
        "clamp_range": list(clamp_range),
    }


# ── Helpers ──────────────────────────────────────────────────────

def _weight_l1(wa: np.ndarray, wb: np.ndarray) -> float:
    return float(np.mean(np.abs(wa - wb)))


def _weight_cosine(wa: np.ndarray, wb: np.ndarray) -> float:
    na = np.linalg.norm(wa)
    nb = np.linalg.norm(wb)
    if na < 1e-12 or nb < 1e-12:
        return 1.0 if na < 1e-12 and nb < 1e-12 else 0.0
    return float(np.dot(wa, wb) / (na * nb))


# ── Single group run ─────────────────────────────────────────────

def _run_group(
    config: AnivaConfig,
    group_name: str,
    total_steps: int,
    tc_std_factor: float,
    snapshot_interval: int = 1000,
) -> dict:
    """Run a single experimental group with time_constant manipulation applied."""
    gdef = _build_group_defs(total_steps)[group_name]

    cfg = AnivaConfig(
        seed=config.seed,
        unit_count=config.unit_count,
        plasticity_rate=gdef["plasticity_rate"],
        homeostasis_enabled=config.homeostasis_enabled,
        homeostatic_target_abs_weight=config.homeostatic_target_abs_weight,
        homeostatic_rate=config.homeostatic_rate,
        use_numba_plasticity=config.use_numba_plasticity,
    )

    core = LifeCore(cfg)
    manip_info = manipulate_time_constant_std(core, tc_std_factor)
    obs = Observer(core)

    env = Environment()
    for es in gdef["events"]:
        env.add_event(StimulusEvent(
            stimulus=es["stimulus"],
            start_step=es["start_step"],
            duration_steps=es["duration_steps"],
        ))

    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)
    snapshots: list[dict] = []
    t_start = time.time()

    for step in range(total_steps):
        influences = env.compute_influences(core.units, step)
        core.step(env_influences=influences if influences else None)

        if (step + 1) % snapshot_interval == 0 or step == total_steps - 1:
            metrics = obs.get_metrics()
            activations = np.array([u.activation for u in core.units.values()])
            weights = np.array([c.weight for c in core.connections])
            snapshots.append({
                "step": step + 1,
                "mean_activation": metrics["mean_activation"],
                "mean_energy": metrics["mean_energy"],
                "hard_active_ratio": metrics["hard_active_ratio"],
                "weight_mean": float(np.mean(weights)),
                "weight_std": float(np.std(weights)),
                "weight_abs_mean": float(np.mean(np.abs(weights))),
                "activation_entropy": float(_activation_entropy(activations)),
            })

    weights_final = np.array([c.weight for c in core.connections], dtype=np.float64)
    final_acts = np.array([u.activation for u in core.units.values()])

    return {
        "group": group_name,
        "label": gdef["label"],
        "plasticity_rate": gdef["plasticity_rate"],
        "weights_initial": weights_initial,
        "weights_final": weights_final,
        "final_mean_activation": float(np.mean(final_acts)),
        "final_mean_energy": float(np.mean(core._energies)),
        "snapshots": snapshots,
        "manipulation": manip_info,
        "elapsed_sec": time.time() - t_start,
    }


def _activation_entropy(activations: np.ndarray, bins: int = 20) -> float:
    hist, _ = np.histogram(activations, bins=bins, range=(0.0, 1.0))
    hist = hist.astype(float) / max(hist.sum(), 1)
    hist = hist[hist > 0]
    if len(hist) == 0:
        return 0.0
    return float(-np.sum(hist * np.log(hist)))


# ── Verdict ──────────────────────────────────────────────────────

def _make_verdict(group_results: dict[str, dict]) -> dict:
    """Compute verdict for one condition (same logic as Phase 7.4)."""
    v = {}

    if "C" in group_results and "A_L" in group_results and "A_R" in group_results:
        c_vs_al = _weight_l1(
            group_results["C"]["weights_final"],
            group_results["A_L"]["weights_final"],
        )
        al_vs_ar = _weight_l1(
            group_results["A_L"]["weights_final"],
            group_results["A_R"]["weights_final"],
        )
        v["repeatability"] = (
            "deterministic_history_sensitive"
            if c_vs_al < al_vs_ar * 0.5
            else "chaotic"
            if c_vs_al > al_vs_ar * 0.8
            else "marginal"
        )
        v["repeat_weight_l1"] = c_vs_al
        v["diverge_weight_l1"] = al_vs_ar

    if "D_L" in group_results and "A_L" in group_results:
        dl_vs_al_init = _weight_l1(
            group_results["D_L"]["weights_final"],
            group_results["A_L"]["weights_initial"],
        )
        al_vs_al_init = _weight_l1(
            group_results["A_L"]["weights_final"],
            group_results["A_L"]["weights_initial"],
        )
        v["plasticity_causal"] = (
            "plasticity_drives_divergence"
            if dl_vs_al_init < al_vs_al_init * 0.5
            else "no_clear_plasticity_effect"
        )
        v["D_L_weight_drift"] = dl_vs_al_init
        v["A_L_weight_drift"] = al_vs_al_init

    if "D_L" in group_results and "D_R" in group_results:
        dl_vs_dr = _weight_l1(
            group_results["D_L"]["weights_final"],
            group_results["D_R"]["weights_final"],
        )
        v["plasticity_off_symmetry"] = (
            "order_irrelevant_without_plasticity"
            if dl_vs_dr < 1e-4
            else "order_matters_even_without_plasticity"
        )
        v["D_L_vs_D_R_weight_l1"] = dl_vs_dr

    # Structural bifurcation: A_L vs A_R delta
    if "A_L" in group_results and "A_R" in group_results:
        al_init = group_results["A_L"]["weights_initial"]
        ar_init = group_results["A_R"]["weights_initial"]
        al_final = group_results["A_L"]["weights_final"]
        ar_final = group_results["A_R"]["weights_final"]

        init_l1 = _weight_l1(al_init, ar_init)
        final_l1 = _weight_l1(al_final, ar_final)
        delta = final_l1 - init_l1

        v["initial_weight_l1"] = init_l1
        v["final_weight_l1"] = final_l1
        v["delta_weight_l1"] = delta
        v["final_weight_cosine"] = _weight_cosine(al_final, ar_final)

        if delta > 1e-4:
            v["structural_bifurcation"] = "significant"
        elif delta > 5e-5:
            v["structural_bifurcation"] = "emerging"
        else:
            v["structural_bifurcation"] = "weak"

    # Causal skeleton
    skeleton_ok = True
    skeleton_checks = []
    if "repeatability" in v:
        ok = v["repeatability"] == "deterministic_history_sensitive"
        skeleton_checks.append(ok)
        if not ok:
            skeleton_ok = False
    if "plasticity_off_symmetry" in v:
        ok = v["plasticity_off_symmetry"] == "order_irrelevant_without_plasticity"
        skeleton_checks.append(ok)
        if not ok:
            skeleton_ok = False
    if "plasticity_causal" in v:
        ok = v["plasticity_causal"] == "plasticity_drives_divergence"
        skeleton_checks.append(ok)
        if not ok:
            skeleton_ok = False
    v["causal_skeleton_intact"] = skeleton_ok if skeleton_checks else None

    return v


# ── Run one condition ────────────────────────────────────────────

def _run_condition(
    config: AnivaConfig,
    total_steps: int,
    tc_std_factor: float,
    snapshot_interval: int,
    groups: list[str],
) -> dict:
    """Run all groups for one time_constant_std condition."""
    condition_name = TC_STD_CONDITIONS[tc_std_factor]
    print(f"\n{'='*60}")
    print(f"Condition: {condition_name} (factor={tc_std_factor})")
    print(f"{'='*60}")

    group_results: dict[str, dict] = {}
    for gname in groups:
        label = _build_group_defs(total_steps)[gname]["label"]
        print(f"  Running {gname} ({label})...", end=" ", flush=True)
        result = _run_group(config, gname, total_steps, tc_std_factor, snapshot_interval)
        group_results[gname] = result
        final = result["snapshots"][-1]
        elapsed = result["elapsed_sec"]
        rate = final["step"] / elapsed if elapsed > 0 else 0
        print(f"act={final['mean_activation']:.4f} "
              f"eng={final['mean_energy']:.4f} "
              f"w_mean={final['weight_mean']:.4f} "
              f"({elapsed:.0f}s, {rate:.0f} steps/s)")

    verdict = _make_verdict(group_results)
    manip_info = group_results[list(groups)[0]]["manipulation"]

    return {
        "condition": condition_name,
        "factor": tc_std_factor,
        "manipulation": manip_info,
        "groups": group_results,
        "verdict": verdict,
    }


# ── Full experiment ──────────────────────────────────────────────

def run_experiment_a(
    config: AnivaConfig | None = None,
    total_steps: int = 2000,
    snapshot_interval: int | None = None,
    groups: list[str] | None = None,
    factors: list[float] | None = None,
) -> dict:
    """Run Phase 7.6A: time_constant_std active manipulation.

    Args:
        config: Base config. Defaults to AnivaConfig(seed=42) with homeostasis+numba on.
        total_steps: Steps per group.
        snapshot_interval: Snapshot interval. Auto-scaled if None.
        groups: Groups to run. Default: A_L, A_R, C, D_L, D_R.
        factors: tc_std factors. Default: [0.3, 1.0, 2.0].

    Returns:
        dict with per-condition results and cross-condition comparison.
    """
    if config is None:
        config = AnivaConfig(seed=42)
        config.homeostasis_enabled = True
        config.use_numba_plasticity = True

    if groups is None:
        groups = ["A_L", "A_R", "C", "D_L", "D_R"]

    if factors is None:
        factors = [0.3, 1.0, 2.0]

    if snapshot_interval is None:
        snapshot_interval = max(total_steps // 4, 500)

    print(f"Phase 7.6A: time_constant_std Active Manipulation")
    print(f"  seed={config.seed}, units={config.unit_count}, steps={total_steps}")
    print(f"  homeostasis={config.homeostasis_enabled}, numba={config.use_numba_plasticity}")
    print(f"  conditions: {[TC_STD_CONDITIONS[f] for f in factors]}")
    print(f"  groups: {groups}")

    condition_results: list[dict] = []
    for factor in factors:
        cr = _run_condition(config, total_steps, factor, snapshot_interval, groups)
        condition_results.append(cr)

    # Cross-condition comparison
    comparison = _compare_conditions(condition_results)

    return {
        "experiment": "phase7_6A_time_constant_std",
        "seed": config.seed,
        "unit_count": config.unit_count,
        "total_steps": total_steps,
        "homeostasis_enabled": config.homeostasis_enabled,
        "use_numba_plasticity": config.use_numba_plasticity,
        "conditions": condition_results,
        "comparison": comparison,
    }


def _compare_conditions(condition_results: list[dict]) -> dict:
    """Extract Δ_weight_L1 trend across conditions."""
    deltas = []
    for cr in condition_results:
        v = cr["verdict"]
        deltas.append({
            "condition": cr["condition"],
            "factor": cr["factor"],
            "delta_weight_l1": v.get("delta_weight_l1"),
            "initial_weight_l1": v.get("initial_weight_l1"),
            "final_weight_l1": v.get("final_weight_l1"),
            "structural_bifurcation": v.get("structural_bifurcation"),
            "causal_skeleton_intact": v.get("causal_skeleton_intact"),
            "repeatability": v.get("repeatability"),
            "plasticity_off_symmetry": v.get("plasticity_off_symmetry"),
            "tc_std_after": cr["manipulation"]["tc_std_after"],
            "tc_mean_after": cr["manipulation"]["tc_mean_after"],
        })

    # Check monotonicity
    delta_vals = [d["delta_weight_l1"] for d in deltas if d["delta_weight_l1"] is not None]
    if len(delta_vals) >= 2:
        increasing = all(x <= y for x, y in zip(delta_vals, delta_vals[1:]))
        decreasing = all(x >= y for x, y in zip(delta_vals, delta_vals[1:]))
        if increasing and not decreasing:
            trend = "monotonic_increasing"
        elif decreasing and not increasing:
            trend = "monotonic_decreasing"
        else:
            trend = "non_monotonic"
    else:
        trend = "insufficient_data"

    return {
        "trend": trend,
        "deltas": deltas,
    }


# ── Output ───────────────────────────────────────────────────────

def _print_results(result: dict) -> None:
    """Print experiment results summary."""
    print()
    print("=" * 70)
    print("Phase 7.6A Results: time_constant_std Manipulation")
    print(f"seed={result['seed']}, steps={result['total_steps']}")
    print("=" * 70)

    print("\n--- Per-Condition Verdict ---")
    header = (f"{'condition':>12s}  {'tc_std':>8s}  {'Δ_L1':>10s}  "
              f"{'bifurcation':>16s}  {'skeleton':>8s}  {'repeat':>22s}")
    print(header)
    print("-" * len(header))
    for cr in result["conditions"]:
        v = cr["verdict"]
        print(
            f"{cr['condition']:>12s}  "
            f"{cr['manipulation']['tc_std_after']:8.4f}  "
            f"{v.get('delta_weight_l1', 0):10.6f}  "
            f"{str(v.get('structural_bifurcation', 'N/A')):>16s}  "
            f"{str(v.get('causal_skeleton_intact', 'N/A')):>8s}  "
            f"{str(v.get('repeatability', 'N/A')):>22s}"
        )

    print("\n--- Cross-Condition Comparison ---")
    comp = result["comparison"]
    print(f"  Δ_L1 trend: {comp['trend']}")
    for d in comp["deltas"]:
        print(f"  {d['condition']:>12s}: Δ_L1={d['delta_weight_l1']:.6f}  "
              f"tc_std={d['tc_std_after']:.4f}  skeleton={d['causal_skeleton_intact']}")


def _save_csv(result: dict, path: str) -> None:
    """Save per-condition per-group metrics to CSV."""
    rows = []
    for cr in result["conditions"]:
        for gname, gdata in cr["groups"].items():
            final = gdata["snapshots"][-1]
            rows.append({
                "condition": cr["condition"],
                "factor": cr["factor"],
                "tc_std_after": cr["manipulation"]["tc_std_after"],
                "tc_mean_after": cr["manipulation"]["tc_mean_after"],
                "group": gname,
                "label": gdata["label"],
                "plasticity_rate": gdata["plasticity_rate"],
                "final_step": final["step"],
                "mean_activation": final["mean_activation"],
                "mean_energy": final["mean_energy"],
                "hard_active_ratio": final["hard_active_ratio"],
                "weight_mean": final["weight_mean"],
                "weight_std": final["weight_std"],
                "weight_abs_mean": final["weight_abs_mean"],
                "activation_entropy": final["activation_entropy"],
                "elapsed_sec": gdata["elapsed_sec"],
            })

    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {path}")


def _save_summary_json(result: dict, path: str) -> None:
    """Save structured summary JSON."""

    def _serialize_condition(cr: dict) -> dict:
        groups_summary = {}
        for gname, gdata in cr["groups"].items():
            final = gdata["snapshots"][-1]
            groups_summary[gname] = {
                "label": gdata["label"],
                "plasticity_rate": gdata["plasticity_rate"],
                "final_step": final["step"],
                "mean_activation": final["mean_activation"],
                "mean_energy": final["mean_energy"],
                "weight_mean": final["weight_mean"],
                "weight_abs_mean": final["weight_abs_mean"],
                "elapsed_sec": gdata["elapsed_sec"],
            }
        return {
            "condition": cr["condition"],
            "factor": cr["factor"],
            "manipulation": cr["manipulation"],
            "groups": groups_summary,
            "verdict": cr["verdict"],
        }

    summary = {
        "experiment": result["experiment"],
        "seed": result["seed"],
        "unit_count": result["unit_count"],
        "total_steps": result["total_steps"],
        "homeostasis_enabled": result["homeostasis_enabled"],
        "use_numba_plasticity": result["use_numba_plasticity"],
        "conditions": [_serialize_condition(cr) for cr in result["conditions"]],
        "comparison": result["comparison"],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"Saved summary JSON to {path}")


# ── CLI ──────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 7.6A: time_constant_std Active Manipulation"
    )
    parser.add_argument("--steps", type=int, default=2000,
                        help="Total steps per group (default: 2000 for smoke test)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--unit-count", type=int, default=300)
    parser.add_argument("--snapshot-interval", type=int, default=None,
                        help="Snapshot interval (auto-scaled if not set)")
    parser.add_argument("--groups", type=str, nargs="+",
                        default=["A_L", "A_R", "C", "D_L", "D_R"])
    parser.add_argument("--factors", type=float, nargs="+",
                        default=[0.3, 1.0, 2.0])
    parser.add_argument("--output-csv", type=str,
                        default="results/phase7_6_time_constant_manipulation.csv")
    parser.add_argument("--summary-json", type=str,
                        default="results/phase7_6_time_constant_manipulation_summary.json")
    parser.add_argument("--no-homeostasis", action="store_true",
                        help="Disable homeostasis")
    parser.add_argument("--no-numba", action="store_true",
                        help="Disable numba plasticity backend")
    args = parser.parse_args(argv)

    config = AnivaConfig(seed=args.seed, unit_count=args.unit_count)
    config.homeostasis_enabled = not args.no_homeostasis
    config.use_numba_plasticity = not args.no_numba
    # Ensure homeostatic target is set for the homeostasis_on case
    config.homeostatic_target_abs_weight = 0.30
    config.homeostatic_rate = 1.0

    result = run_experiment_a(
        config=config,
        total_steps=args.steps,
        snapshot_interval=args.snapshot_interval,
        groups=args.groups,
        factors=args.factors,
    )

    _print_results(result)

    if args.output_csv:
        _save_csv(result, args.output_csv)
    if args.summary_json:
        _save_summary_json(result, args.summary_json)

    # Smoke test gate
    all_intact = all(
        cr["verdict"].get("causal_skeleton_intact") for cr in result["conditions"]
    )
    if not all_intact:
        print("\n*** SMOKE TEST FAILED: causal_skeleton_intact != True for some conditions ***")
        return 1

    print("\n*** Smoke test passed: causal_skeleton_intact = True for all conditions ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
