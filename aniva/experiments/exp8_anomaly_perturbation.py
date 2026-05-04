"""Phase 8A: External Anomaly Perturbation Experiment.

Tests whether a structurally distinct anomalous event produces
seed-specific outlier trajectories, beyond baseline sensitivity.

Anomaly variants:
  baseline_overlap:
    L pulse: intensity 0.025, duration 150
    R pulse: intensity 0.015, duration 300
    (simultaneous onset -> 150-step overlap, then R alone for 150 more)

  delayed_asymmetric (Phase 8A.2):
    L pulse: intensity 0.025, duration 300
    R pulse: intensity 0.015, duration 225
    (L starts first, R joins at +75 -> 225-step overlap, both end together)

Does NOT: closed-loop world, personality/emotion, stronger L/R replacement.
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


# ── Stimulus definitions ───────────────────────────────────────────

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.03, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.03, radius=0.5)

# Anomalous perturbation: asymmetric, overlapping cross-region pulse
ANOMALY_L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.025, radius=0.5)
ANOMALY_R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.015, radius=0.5)

DEFAULT_ANOMALY_STEP = 30000
DEFAULT_ANOMALY_VARIANT = "baseline_overlap"

ANOMALY_VARIANTS = {
    "baseline_overlap": [
        {"stimulus_key": "L", "start_offset": 0, "duration_steps": 150},
        {"stimulus_key": "R", "start_offset": 0, "duration_steps": 300},
    ],
    "delayed_asymmetric": [
        {"stimulus_key": "L", "start_offset": 0, "duration_steps": 300},
        {"stimulus_key": "R", "start_offset": 75, "duration_steps": 225},
    ],
}

ANOMALY_VARIANT_STIM_MAP = {
    "L": ANOMALY_L_STIM,
    "R": ANOMALY_R_STIM,
}

# Legacy constants (used by baseline_overlap)
ANOMALY_L_DURATION = 150
ANOMALY_R_DURATION = 300


def _get_anomaly_events(anomaly_step: int,
                        variant: str = "baseline_overlap") -> list[dict]:
    spec = ANOMALY_VARIANTS[variant]
    events = []
    for entry in spec:
        stim = ANOMALY_VARIANT_STIM_MAP[entry["stimulus_key"]]
        events.append({
            "stimulus": stim,
            "start_step": anomaly_step + entry["start_offset"],
            "duration_steps": entry["duration_steps"],
        })
    return events


def _get_anomaly_max_duration(variant: str) -> int:
    """Max end-step offset for post-anomaly window calculation."""
    spec = ANOMALY_VARIANTS[variant]
    return max(e["start_offset"] + e["duration_steps"] for e in spec)


# ── Group definitions (same 5-group protocol) ──────────────────────

GROUP_DEFS = {
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

DEFAULT_SEEDS = [42, 77, 123, 999]


# ── Helpers ────────────────────────────────────────────────────────

def _weight_l1(wa: np.ndarray, wb: np.ndarray) -> float:
    return float(np.mean(np.abs(wa - wb)))


def _weight_cosine(wa: np.ndarray, wb: np.ndarray) -> float:
    na = np.linalg.norm(wa)
    nb = np.linalg.norm(wb)
    if na < 1e-12 or nb < 1e-12:
        return 1.0 if na < 1e-12 and nb < 1e-12 else 0.0
    return float(np.dot(wa, wb) / (na * nb))


def _activation_entropy(activations: np.ndarray, bins: int = 20) -> float:
    hist, _ = np.histogram(activations, bins=bins, range=(0.0, 1.0))
    hist = hist.astype(float) / max(hist.sum(), 1)
    hist = hist[hist > 0]
    if len(hist) == 0:
        return 0.0
    return float(-np.sum(hist * np.log(hist)))


# ── Single group run ───────────────────────────────────────────────

def _run_group(
    config: AnivaConfig,
    group_name: str,
    total_steps: int,
    anomaly: bool,
    snapshot_interval: int = 1000,
    anomaly_step: int = 30000,
    anomaly_variant: str = "baseline_overlap",
) -> dict:
    """Run a single experimental group.

    Args:
        anomaly: If True, includes the anomalous perturbation events.
        anomaly_step: Step at which anomaly fires (only used if anomaly=True).
        anomaly_variant: Which anomaly variant to use.
    """
    gdef = GROUP_DEFS[group_name]

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
    obs = Observer(core)

    env = Environment()
    for es in gdef["events"]:
        env.add_event(StimulusEvent(
            stimulus=es["stimulus"],
            start_step=es["start_step"],
            duration_steps=es["duration_steps"],
        ))
    if anomaly:
        for es in _get_anomaly_events(anomaly_step, anomaly_variant):
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

    # Post-anomaly activation: mean activation from anomaly_end to step 60000
    post_anomaly_acts: list[float] = []
    anomaly_max_dur = _get_anomaly_max_duration(anomaly_variant)
    post_window_start = anomaly_step + anomaly_max_dur
    post_window_end = min(60000, total_steps)
    for s in snapshots:
        if post_window_start <= s["step"] <= post_window_end:
            post_anomaly_acts.append(s["mean_activation"])

    return {
        "group": group_name,
        "label": gdef["label"],
        "plasticity_rate": gdef["plasticity_rate"],
        "anomaly": anomaly,
        "weights_initial": weights_initial,
        "weights_final": weights_final,
        "final_mean_activation": float(np.mean(final_acts)),
        "final_mean_energy": float(np.mean(core._energies)),
        "snapshots": snapshots,
        "post_anomaly_mean_activation": float(np.mean(post_anomaly_acts)) if post_anomaly_acts else None,
        "elapsed_sec": time.time() - t_start,
    }


# ── Verdict (same logic as Phase 7) ────────────────────────────────

def _make_verdict(group_results: dict[str, dict]) -> dict:
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
            if c_vs_al < al_vs_ar * 0.5 else "chaotic"
            if c_vs_al > al_vs_ar * 0.8 else "marginal"
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


# ── Run one seed ───────────────────────────────────────────────────

def _run_seed(
    config: AnivaConfig,
    total_steps: int,
    snapshot_interval: int,
    groups: list[str],
    anomaly_step: int,
    anomaly_variant: str = "baseline_overlap",
) -> dict:
    """Run normal and anomaly conditions for one seed."""
    seed = config.seed
    print(f"\n{'='*60}")
    print(f"Seed {seed}")
    print(f"{'='*60}")

    seed_result = {"seed": seed, "conditions": []}

    for condition, anomaly in [("normal", False), ("anomaly", True)]:
        label = "normal_stream" if not anomaly else "anomaly_stream"
        print(f"\n  --- {label} ---")

        group_results: dict[str, dict] = {}
        for gname in groups:
            gdef = GROUP_DEFS[gname]
            print(f"    Running {gname} ({gdef['label']})...", end=" ", flush=True)
            result = _run_group(config, gname, total_steps, anomaly,
                                snapshot_interval, anomaly_step, anomaly_variant)
            group_results[gname] = result
            final = result["snapshots"][-1]
            elapsed = result["elapsed_sec"]
            rate = final["step"] / elapsed if elapsed > 0 else 0
            print(f"act={final['mean_activation']:.4f} "
                  f"eng={final['mean_energy']:.4f} "
                  f"({elapsed:.0f}s, {rate:.0f} steps/s)")

        verdict = _make_verdict(group_results)

        # Post-anomaly activation
        a_l_post = group_results.get("A_L", {}).get("post_anomaly_mean_activation")
        a_r_post = group_results.get("A_R", {}).get("post_anomaly_mean_activation")

        seed_result["conditions"].append({
            "condition": condition,
            "anomaly": anomaly,
            "groups": group_results,
            "verdict": verdict,
            "post_anomaly_a_l_activation": a_l_post,
            "post_anomaly_a_r_activation": a_r_post,
        })

    # Compute derived metrics
    normal = seed_result["conditions"][0]["verdict"]
    anomaly_v = seed_result["conditions"][1]["verdict"]
    seed_result["normal_delta_l1"] = normal.get("delta_weight_l1")
    seed_result["anomaly_delta_l1"] = anomaly_v.get("delta_weight_l1")
    seed_result["anomaly_effect"] = (
        seed_result["anomaly_delta_l1"] - seed_result["normal_delta_l1"]
        if seed_result["anomaly_delta_l1"] is not None
        and seed_result["normal_delta_l1"] is not None
        else None
    )
    seed_result["causal_skeleton_intact"] = (
        normal.get("causal_skeleton_intact")
        and anomaly_v.get("causal_skeleton_intact")
    )

    return seed_result


# ── Cross-seed analysis ────────────────────────────────────────────

def _cross_seed_analysis(seed_results: list[dict]) -> dict:
    """Compute z-scores and identify outlier seeds."""
    effects = []
    for sr in seed_results:
        ae = sr.get("anomaly_effect")
        if ae is not None:
            effects.append(ae)
        else:
            effects.append(0.0)

    mean_effect = float(np.mean(effects))
    std_effect = float(np.std(effects)) if len(effects) > 1 else 1.0

    outliers = []
    for sr, ae in zip(seed_results, effects):
        z = (ae - mean_effect) / std_effect if std_effect > 1e-12 else 0.0
        sr["anomaly_effect_zscore"] = z
        if abs(z) > 1.5:
            outliers.append({
                "seed": sr["seed"],
                "zscore": z,
                "anomaly_effect": ae,
                "direction": "positive_outlier" if z > 0 else "negative_outlier",
            })

    return {
        "mean_anomaly_effect": mean_effect,
        "std_anomaly_effect": std_effect,
        "outliers": outliers,
    }


# ── Output ─────────────────────────────────────────────────────────

def _print_results(result: dict) -> None:
    print("\n" + "=" * 70)
    print(f"Phase 8A: Anomaly Perturbation Results")
    print(f"seeds={result['seeds']}, steps={result['total_steps']}")
    print("=" * 70)

    print(f"\n--- Per-Seed Comparison ---")
    header = (f"{'seed':>6s}  {'normal_Δ_L1':>12s}  {'anomaly_Δ_L1':>12s}  "
              f"{'effect':>10s}  {'zscore':>8s}  {'skeleton':>8s}")
    print(header)
    print("-" * len(header))
    for sr in result["seed_results"]:
        print(
            f"{sr['seed']:>6d}  "
            f"{sr.get('normal_delta_l1', 0):12.6f}  "
            f"{sr.get('anomaly_delta_l1', 0):12.6f}  "
            f"{sr.get('anomaly_effect', 0):10.6f}  "
            f"{sr.get('anomaly_effect_zscore', 0):8.2f}  "
            f"{str(sr.get('causal_skeleton_intact', 'N/A')):>8s}"
        )

    analysis = result["cross_seed_analysis"]
    print(f"\n--- Cross-Seed Analysis ---")
    print(f"  mean anomaly effect: {analysis['mean_anomaly_effect']:.6f}")
    print(f"  std anomaly effect:  {analysis['std_anomaly_effect']:.6f}")
    if analysis["outliers"]:
        print(f"  outliers (|z|>1.5):")
        for o in analysis["outliers"]:
            print(f"    seed={o['seed']} z={o['zscore']:.2f} "
                  f"effect={o['anomaly_effect']:.6f} ({o['direction']})")
    else:
        print(f"  no outlier seeds detected")


def _save_csv(result: dict, path: str) -> None:
    rows = []
    for sr in result["seed_results"]:
        for cond in sr["conditions"]:
            for gname, gdata in cond["groups"].items():
                final = gdata["snapshots"][-1]
                row = {
                    "anomaly_variant": result.get("anomaly_variant", "baseline_overlap"),
                    "seed": sr["seed"],
                    "condition": cond["condition"],
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
                    "post_anomaly_mean_activation": gdata.get("post_anomaly_mean_activation"),
                    "elapsed_sec": gdata["elapsed_sec"],
                }
                rows.append(row)

    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {path}")


def _save_summary_json(result: dict, path: str) -> None:
    def _serialize_seed(sr: dict) -> dict:
        conditions = []
        for cond in sr["conditions"]:
            groups_summary = {}
            for gname, gdata in cond["groups"].items():
                final = gdata["snapshots"][-1]
                groups_summary[gname] = {
                    "label": gdata["label"],
                    "plasticity_rate": gdata["plasticity_rate"],
                    "final_step": final["step"],
                    "mean_activation": final["mean_activation"],
                    "mean_energy": final["mean_energy"],
                    "weight_mean": final["weight_mean"],
                    "weight_abs_mean": final["weight_abs_mean"],
                    "post_anomaly_mean_activation": gdata.get("post_anomaly_mean_activation"),
                    "elapsed_sec": gdata["elapsed_sec"],
                }
            conditions.append({
                "condition": cond["condition"],
                "anomaly": cond["anomaly"],
                "groups": groups_summary,
                "verdict": cond["verdict"],
                "post_anomaly_a_l_activation": cond.get("post_anomaly_a_l_activation"),
                "post_anomaly_a_r_activation": cond.get("post_anomaly_a_r_activation"),
            })
        return {
            "seed": sr["seed"],
            "normal_delta_l1": sr["normal_delta_l1"],
            "anomaly_delta_l1": sr["anomaly_delta_l1"],
            "anomaly_effect": sr["anomaly_effect"],
            "anomaly_effect_zscore": sr["anomaly_effect_zscore"],
            "causal_skeleton_intact": sr["causal_skeleton_intact"],
            "conditions": conditions,
        }

    variant = result.get("anomaly_variant", "baseline_overlap")
    variant_spec = ANOMALY_VARIANTS[variant]
    anomaly_config = {
        "variant": variant,
        "step": result["anomaly_step"],
        "pulses": variant_spec,
    }

    summary = {
        "experiment": "phase8A_anomaly_perturbation",
        "seeds": result["seeds"],
        "unit_count": result["unit_count"],
        "total_steps": result["total_steps"],
        "homeostasis_enabled": result["homeostasis_enabled"],
        "use_numba_plasticity": result["use_numba_plasticity"],
        "anomaly_config": anomaly_config,
        "seed_results": [_serialize_seed(sr) for sr in result["seed_results"]],
        "cross_seed_analysis": result["cross_seed_analysis"],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"Saved summary JSON to {path}")


# ── CLI ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 8A: External Anomaly Perturbation Experiment"
    )
    parser.add_argument("--steps", type=int, default=5000,
                        help="Total steps per group (default: 5000 for smoke test)")
    parser.add_argument("--seeds", type=int, nargs="+", default=None,
                        help=f"Seeds to test (default: {DEFAULT_SEEDS})")
    parser.add_argument("--unit-count", type=int, default=300)
    parser.add_argument("--snapshot-interval", type=int, default=None)
    parser.add_argument("--groups", type=str, nargs="+",
                        default=["A_L", "A_R", "C", "D_L", "D_R"])
    parser.add_argument("--output-csv", type=str, default="results/phase8_anomaly_perturbation.csv")
    parser.add_argument("--summary-json", type=str,
                        default="results/phase8_anomaly_perturbation_summary.json")
    parser.add_argument("--anomaly-step", type=int, default=30000,
                        help="Step at which anomalous perturbation fires (default: 30000)")
    parser.add_argument("--anomaly-variant", type=str, default="baseline_overlap",
                        choices=["baseline_overlap", "delayed_asymmetric"],
                        help="Anomaly variant (default: baseline_overlap)")
    parser.add_argument("--no-homeostasis", action="store_true",
                        help="Disable homeostasis")
    parser.add_argument("--no-numba", action="store_true",
                        help="Disable numba plasticity backend")
    args = parser.parse_args(argv)

    anomaly_step = args.anomaly_step
    anomaly_variant = args.anomaly_variant
    seeds = args.seeds if args.seeds is not None else DEFAULT_SEEDS
    if args.snapshot_interval is None:
        args.snapshot_interval = max(args.steps // 4, 500)

    config = AnivaConfig(unit_count=args.unit_count)
    config.homeostasis_enabled = not args.no_homeostasis
    config.use_numba_plasticity = not args.no_numba
    config.homeostatic_target_abs_weight = 0.30
    config.homeostatic_rate = 1.0

    variant_spec = ANOMALY_VARIANTS[anomaly_variant]

    print(f"Phase 8A: External Anomaly Perturbation")
    print(f"  seeds={seeds}, units={args.unit_count}, steps={args.steps}")
    print(f"  homeostasis={config.homeostasis_enabled}, numba={config.use_numba_plasticity}")
    print(f"  variant={anomaly_variant}:")
    for entry in variant_spec:
        sk = entry["stimulus_key"]
        print(f"    {sk}(intensity={ANOMALY_VARIANT_STIM_MAP[sk].intensity}, "
              f"start=+{entry['start_offset']}, "
              f"duration={entry['duration_steps']})")
    print(f"  anomaly_step={anomaly_step}")

    seed_results: list[dict] = []
    for seed in seeds:
        config.seed = seed
        sr = _run_seed(config, args.steps, args.snapshot_interval,
                       args.groups, anomaly_step, anomaly_variant)
        seed_results.append(sr)

    analysis = _cross_seed_analysis(seed_results)

    result = {
        "experiment": "phase8A_anomaly_perturbation",
        "seeds": seeds,
        "unit_count": args.unit_count,
        "total_steps": args.steps,
        "homeostasis_enabled": config.homeostasis_enabled,
        "use_numba_plasticity": config.use_numba_plasticity,
        "anomaly_step": anomaly_step,
        "anomaly_variant": anomaly_variant,
        "seed_results": seed_results,
        "cross_seed_analysis": analysis,
    }

    _print_results(result)

    if args.output_csv:
        _save_csv(result, args.output_csv)
    if args.summary_json:
        _save_summary_json(result, args.summary_json)

    all_intact = all(
        sr.get("causal_skeleton_intact") for sr in seed_results
    )
    if not all_intact:
        print("\n*** SMOKE TEST FAILED: causal_skeleton_intact != True for some seeds ***")
        return 1

    print("\n*** Smoke test passed: causal_skeleton_intact = True for all seeds ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
