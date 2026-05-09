"""Phase 8B: Minimal Closed-Loop World — Smoke Test.

Tests whether LifeCore internal state can bias future environmental event
distribution, creating a feedback loop: state → event bias → new events →
plasticity → new state.

Three arms:
  open_loop:         fixed pre-generated event stream, no state feedback
  closed_loop:       same base stream, L/R probability biased by lr_imbalance
  shuffled_feedback: closed_loop bias sequence applied in scrambled order

Language discipline: no "preference", "choice", "reward", "agent".
Physical description only: "regional activation imbalance biases event probability."
"""

import argparse
import csv
import json
import sys
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

# ── Stimulus definitions ─────────────────────────────────────────────

L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)

# ── State observer ───────────────────────────────────────────────────

def _compute_state_summary(core: LifeCore) -> dict:
    """Extract low-level physical state. No psychological variables."""
    left_ids = [uid for uid, u in core.units.items() if u.position[0] < 0]
    right_ids = [uid for uid, u in core.units.items() if u.position[0] > 0]

    left_acts = np.array([core.units[uid].activation for uid in left_ids])
    right_acts = np.array([core.units[uid].activation for uid in right_ids])

    left_mean = float(np.mean(left_acts)) if len(left_acts) > 0 else 0.0
    right_mean = float(np.mean(right_acts)) if len(right_acts) > 0 else 0.0
    lr_imbalance = left_mean - right_mean

    all_acts = np.array([u.activation for u in core.units.values()])
    energy_mean = float(np.mean(core._energies))

    # Activation entropy (20 bins)
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


# ── Feedback scheduler ───────────────────────────────────────────────

def _compute_bias(lr_imbalance: float, gain: float, max_bias: float) -> float:
    """Map lr_imbalance to event probability bias.

    If lr_imbalance > 0 (L-side more active), bias > 0 → increase R probability.
    This is a balancing physical coupling, not a preference.
    """
    bias = gain * lr_imbalance
    return float(np.clip(bias, -max_bias, max_bias))


# ── Base event stream (pre-generated, shared) ────────────────────────

def _pre_generate_base_stream(
    total_steps: int,
    event_interval: int,
    base_p_L: float,
    event_duration: int,
    rng: np.random.Generator,
) -> list[dict]:
    """Pre-generate a base event stream with fixed probability.

    Each entry: {"step": int, "chosen": "L"|"R", "stimulus": Stimulus, "duration": int}
    This stream is the common baseline for all three arms.
    """
    stream = []
    for step in range(event_interval, total_steps, event_interval):
        if rng.random() < base_p_L:
            stim = L_STIM
            chosen = "L"
        else:
            stim = R_STIM
            chosen = "R"
        stream.append({
            "step": step,
            "chosen": chosen,
            "stimulus": stim,
            "duration": event_duration,
        })
    return stream


# ── Run one arm ──────────────────────────────────────────────────────

def _run_arm(
    config: AnivaConfig,
    arm: str,  # "open_loop", "closed_loop", "shuffled_feedback"
    total_steps: int,
    event_duration: int,
    base_p_L: float,
    feedback_gain: float,
    max_bias: float,
    feedback_interval: int,
    snapshot_interval: int,
    base_stream: list[dict],
    override_rng: np.random.Generator,
    shuffled_bias_seq: list[float] | None = None,
) -> dict:
    """Run one experimental arm.

    open_loop:         use base_stream as-is (no bias, no override)
    closed_loop:       start from base_stream; at each event step,
                       compute bias from current state, and with
                       probability = |bias|, override the base event
                       with a re-sampled event (biased toward the
                       direction opposite to the imbalance)
    shuffled_feedback: same as closed_loop but bias values come from
                       a pre-computed, shuffled sequence
    """

    core = LifeCore(config)
    weights_initial = np.array([c.weight for c in core.connections], dtype=np.float64)

    snapshots: list[dict] = []
    bias_history: list[float] = []
    state_history: list[dict] = []
    all_events: list[StimulusEvent] = []
    event_log_entries: list[dict] = []
    bias_idx = 0

    for step in range(total_steps):
        # Event decision: every event_interval steps
        if step > 0 and step % (base_stream[0]["step"] if base_stream else 200) == 0:
            # Find the base event for this step
            base_event = None
            event_idx = -1
            for i, be in enumerate(base_stream):
                if be["step"] == step:
                    base_event = be
                    event_idx = i
                    break

            if base_event is None:
                # No base event at this step — skip
                core.step(env_influences=None)
                continue

            if arm == "open_loop":
                # Use base stream exactly as-is
                chosen_stim = base_event["stimulus"]
                chosen_label = base_event["chosen"]
                bias = 0.0
                bias_history.append(bias)

            elif arm == "closed_loop":
                # Compute bias from current state
                state = _compute_state_summary(core)
                bias = _compute_bias(state["lr_imbalance"], feedback_gain, max_bias)
                bias_history.append(bias)

                # Override probability = |bias| (clipped to [0, 1])
                override_prob = min(abs(bias), 1.0)
                if override_rng.random() < override_prob:
                    # Re-sample with biased probability
                    # bias > 0 (L more active) → push toward R (decrease p_L)
                    p_L = float(np.clip(base_p_L - bias, 0.05, 0.95))
                    if override_rng.random() < p_L:
                        chosen_stim = L_STIM
                        chosen_label = "L"
                    else:
                        chosen_stim = R_STIM
                        chosen_label = "R"
                else:
                    chosen_stim = base_event["stimulus"]
                    chosen_label = base_event["chosen"]

            elif arm == "shuffled_feedback":
                if shuffled_bias_seq and bias_idx < len(shuffled_bias_seq):
                    bias = shuffled_bias_seq[bias_idx]
                else:
                    bias = 0.0
                bias_idx += 1
                bias_history.append(bias)

                override_prob = min(abs(bias), 1.0)
                if override_rng.random() < override_prob:
                    p_L = float(np.clip(base_p_L - bias, 0.05, 0.95))
                    if override_rng.random() < p_L:
                        chosen_stim = L_STIM
                        chosen_label = "L"
                    else:
                        chosen_stim = R_STIM
                        chosen_label = "R"
                else:
                    chosen_stim = base_event["stimulus"]
                    chosen_label = base_event["chosen"]

            event = StimulusEvent(
                stimulus=chosen_stim,
                start_step=step,
                duration_steps=event_duration,
            )
            all_events.append(event)
            event_log_entries.append({
                "step": step,
                "chosen": chosen_label,
                "base_chosen": base_event["chosen"],
                "overridden": chosen_label != base_event["chosen"],
                "bias": bias,
            })

        # Compute influences from active events
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

        # Periodic state observation
        if step > 0 and step % feedback_interval == 0:
            state = _compute_state_summary(core)
            state["step"] = step
            state_history.append(state)

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
                    if len(left_acts) > 0 and len(right_acts) > 0
                    else 0.0
                ),
            })

    weights_final = np.array([c.weight for c in core.connections], dtype=np.float64)
    final_weight_l1 = float(np.mean(np.abs(weights_final - weights_initial)))

    n_L = sum(1 for e in event_log_entries if e["chosen"] == "L")
    n_R = sum(1 for e in event_log_entries if e["chosen"] == "R")
    n_overridden = sum(1 for e in event_log_entries if e.get("overridden"))
    total_events = n_L + n_R
    L_fraction = n_L / total_events if total_events > 0 else 0.5

    return {
        "arm": arm,
        "seed": config.seed,
        "snapshots": snapshots,
        "state_history": state_history,
        "bias_history": bias_history,
        "event_log": event_log_entries,
        "final_weight_l1": final_weight_l1,
        "event_count_L": n_L,
        "event_count_R": n_R,
        "events_overridden": n_overridden,
        "event_L_fraction": L_fraction,
        "final_mean_activation": (
            float(np.mean([u.activation for u in core.units.values()]))
        ),
    }


# ── Save / Print ─────────────────────────────────────────────────────

def _save_csv(results: list[dict], path: str) -> None:
    rows = []
    for r in results:
        for snap in r["snapshots"]:
            rows.append({
                "seed": r["seed"],
                "arm": r["arm"],
                "step": snap["step"],
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
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows to {path}")


def _save_summary_json(results: list[dict], path: str, params: dict) -> None:
    summary = {
        "experiment": "phase8B_closed_loop_world_smoke",
        "params": params,
        "arms": [],
    }
    for r in results:
        summary["arms"].append({
            "seed": r["seed"],
            "arm": r["arm"],
            "event_count_L": r["event_count_L"],
            "event_count_R": r["event_count_R"],
            "event_L_fraction": r["event_L_fraction"],
            "final_weight_l1": r["final_weight_l1"],
            "mean_lr_imbalance": float(np.mean([
                s["lr_imbalance"] for s in r["snapshots"]
            ])) if r["snapshots"] else None,
            "final_mean_activation": r["final_mean_activation"],
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"Saved summary to {path}")


# ── CLI ──────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 8B: Minimal Closed-Loop World Smoke Test"
    )
    parser.add_argument("--steps", type=int, default=5000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 999])
    parser.add_argument("--unit-count", type=int, default=300)
    parser.add_argument("--event-interval", type=int, default=200,
                        help="Steps between event decision points")
    parser.add_argument("--event-duration", type=int, default=80)
    parser.add_argument("--base-p-L", type=float, default=0.5,
                        help="Base probability of L stimulus (no bias)")
    parser.add_argument("--feedback-gain", type=float, default=0.05,
                        help="Multiplier: bias = gain * lr_imbalance")
    parser.add_argument("--max-bias", type=float, default=0.1,
                        help="Max absolute probability shift")
    parser.add_argument("--feedback-interval", type=int, default=200,
                        help="Steps between state observations")
    parser.add_argument("--snapshot-interval", type=int, default=None)
    parser.add_argument("--base-rng-seed", type=int, default=20260504,
                        help="Fixed seed for event RNG (shared across arms)")
    parser.add_argument("--output-csv", type=str,
                        default="results/phase8B_smoke.csv")
    parser.add_argument("--summary-json", type=str,
                        default="results/phase8B_smoke_summary.json")
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

    print(f"Phase 8B: Minimal Closed-Loop World — Smoke Test")
    print(f"  seeds={args.seeds}, steps={args.steps}, units={args.unit_count}")
    print(f"  event_interval={args.event_interval}, duration={args.event_duration}")
    print(f"  base_p_L={args.base_p_L}, gain={args.feedback_gain}, max_bias={args.max_bias}")
    print(f"  feedback_interval={args.feedback_interval}")
    print(f"  homeostasis={config_base.homeostasis_enabled}, numba={config_base.use_numba_plasticity}")

    all_results: list[dict] = []

    for seed in args.seeds:
        config_base.seed = seed
        print(f"\n{'='*60}")
        print(f"Seed {seed}")
        print(f"{'='*60}")

        # Pre-generate base event stream (same for all arms of this seed)
        base_rng = np.random.default_rng(args.base_rng_seed)
        base_stream = _pre_generate_base_stream(
            args.steps, args.event_interval,
            args.base_p_L, args.event_duration, base_rng,
        )
        base_L = sum(1 for be in base_stream if be["chosen"] == "L")
        base_R = len(base_stream) - base_L
        print(f"  base_stream: {len(base_stream)} events, L={base_L}, R={base_R}")

        # Each arm gets its own override RNG (derived from base + seed + arm index)
        override_rng_ol = np.random.default_rng(args.base_rng_seed + seed * 10 + 0)
        override_rng_cl = np.random.default_rng(args.base_rng_seed + seed * 10 + 1)
        override_rng_sf = np.random.default_rng(args.base_rng_seed + seed * 10 + 2)

        # ── Arm 1: open_loop ──────────────────────────────────────
        print("  [open_loop] — base stream as-is...")
        r_ol = _run_arm(
            config_base, "open_loop",
            total_steps=args.steps,
            event_duration=args.event_duration,
            base_p_L=args.base_p_L,
            feedback_gain=args.feedback_gain,
            max_bias=args.max_bias,
            feedback_interval=args.feedback_interval,
            snapshot_interval=args.snapshot_interval,
            base_stream=base_stream,
            override_rng=override_rng_ol,
        )
        print(f"    L={r_ol['event_count_L']}, R={r_ol['event_count_R']}, "
              f"L_frac={r_ol['event_L_fraction']:.3f}, "
              f"overridden={r_ol['events_overridden']}, "
              f"final_wL1={r_ol['final_weight_l1']:.6f}")
        all_results.append(r_ol)

        # ── Arm 2: closed_loop ────────────────────────────────────
        print("  [closed_loop] — state-biased overrides...")
        r_cl = _run_arm(
            config_base, "closed_loop",
            total_steps=args.steps,
            event_duration=args.event_duration,
            base_p_L=args.base_p_L,
            feedback_gain=args.feedback_gain,
            max_bias=args.max_bias,
            feedback_interval=args.feedback_interval,
            snapshot_interval=args.snapshot_interval,
            base_stream=base_stream,
            override_rng=override_rng_cl,
        )
        print(f"    L={r_cl['event_count_L']}, R={r_cl['event_count_R']}, "
              f"L_frac={r_cl['event_L_fraction']:.3f}, "
              f"overridden={r_cl['events_overridden']}, "
              f"final_wL1={r_cl['final_weight_l1']:.6f}")
        all_results.append(r_cl)

        # ── Arm 3: shuffled_feedback ──────────────────────────────
        cl_biases = r_cl["bias_history"].copy()
        shuffled_biases = cl_biases.copy()
        shuffle_rng = np.random.default_rng(args.base_rng_seed + seed)
        shuffle_rng.shuffle(shuffled_biases)

        print(f"  [shuffled_feedback] — scrambled biases ({len(shuffled_biases)} values)...")
        r_sf = _run_arm(
            config_base, "shuffled_feedback",
            total_steps=args.steps,
            event_duration=args.event_duration,
            base_p_L=args.base_p_L,
            feedback_gain=args.feedback_gain,
            max_bias=args.max_bias,
            feedback_interval=args.feedback_interval,
            snapshot_interval=args.snapshot_interval,
            base_stream=base_stream,
            override_rng=override_rng_sf,
            shuffled_bias_seq=shuffled_biases,
        )
        print(f"    L={r_sf['event_count_L']}, R={r_sf['event_count_R']}, "
              f"L_frac={r_sf['event_L_fraction']:.3f}, "
              f"overridden={r_sf['events_overridden']}, "
              f"final_wL1={r_sf['final_weight_l1']:.6f}")
        all_results.append(r_sf)

    # ── Print comparison ─────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"Phase 8B Smoke — Comparison")
    print(f"{'='*70}")
    print(f"{'seed':>5s} {'arm':>20s}  {'L':>4s} {'R':>4s} {'ovr':>4s} {'L_frac':>7s} {'final_wL1':>10s}")
    print("-" * 75)
    for r in all_results:
        print(f"{r['seed']:>5d} {r['arm']:>20s}  "
              f"{r['event_count_L']:>4d} {r['event_count_R']:>4d} "
              f"{r['events_overridden']:>4d} "
              f"{r['event_L_fraction']:>7.3f} {r['final_weight_l1']:>10.6f}")

    # ── Smoke checks ─────────────────────────────────────────────
    print(f"\n--- Smoke Checks ---")
    passes = 0
    checks = 0

    for seed in args.seeds:
        seed_results = [r for r in all_results if r["seed"] == seed]
        arms = {r["arm"]: r for r in seed_results}
        ol = arms.get("open_loop")
        cl = arms.get("closed_loop")
        sf = arms.get("shuffled_feedback")

        checks += 1
        if ol and cl:
            delta = abs(cl["event_L_fraction"] - ol["event_L_fraction"])
            if delta > 1e-6:
                print(f"  [PASS] seed={seed}: closed_loop L_frac ({cl['event_L_fraction']:.3f}) "
                      f"!= open_loop ({ol['event_L_fraction']:.3f}), delta={delta:.3f}")
                passes += 1
            else:
                print(f"  [WARN] seed={seed}: closed_loop L_frac == open_loop (delta=0)")

        checks += 1
        if cl and len(cl["bias_history"]) > 0:
            bias_range = max(cl["bias_history"]) - min(cl["bias_history"])
            if bias_range > 1e-6:
                print(f"  [PASS] seed={seed}: bias varies (range={bias_range:.6f}), "
                      f"state is affecting event probability")
                passes += 1
            else:
                print(f"  [WARN] seed={seed}: bias is constant (range=0), "
                      f"state may not be affecting events")
        elif cl:
            print(f"  [INFO] seed={seed}: no bias history (too few events)")

        checks += 1
        if sf:
            print(f"  [PASS] seed={seed}: shuffled_feedback completed "
                  f"(L_frac={sf['event_L_fraction']:.3f})")
            passes += 1

    print(f"\n  Smoke: {passes}/{checks} checks passed")

    # ── Save ─────────────────────────────────────────────────────
    if args.output_csv:
        _save_csv(all_results, args.output_csv)
    if args.summary_json:
        _save_summary_json(all_results, args.summary_json, {
            "steps": args.steps,
            "seeds": args.seeds,
            "event_interval": args.event_interval,
            "event_duration": args.event_duration,
            "base_p_L": args.base_p_L,
            "feedback_gain": args.feedback_gain,
            "max_bias": args.max_bias,
            "feedback_interval": args.feedback_interval,
            "base_rng_seed": args.base_rng_seed,
        })

    return 0


if __name__ == "__main__":
    sys.exit(main())
