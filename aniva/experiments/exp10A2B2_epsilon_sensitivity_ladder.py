"""Phase 10A.2B.2 — Epsilon Sensitivity Ladder (diagnostic, not tuning).

Systematically probes the sensitivity threshold at which 9D slow
consolidation captures initial-activation state-context divergence.
Ladder ε ∈ {0.005, 0.01, 0.02, 0.05}.

Both 9C event-pair plasticity and 9D consolidation are ON.
No ε value is promoted to default. 10A.3 negative stands unchanged.

Frozen from docs/phase10A2B2_epsilon_sensitivity_ladder_design.md.
"""

import argparse, csv, hashlib, json, sys, time
import numpy as np

from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.environment.environment import Stimulus, StimulusEvent, Environment

# ── Frozen from 10A.0 / 10A.1B / 10A.2B.1 ──
L_STIM = Stimulus(position=(-0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
R_STIM = Stimulus(position=(0.5, 0.0, 0.0), intensity=0.02, radius=0.5)
STIM_MAP = {"L": L_STIM, "R": R_STIM}

TOTAL_STEPS = 7500
WARMUP = 2000
DECISION_INTERVAL = 250
PULSE_DURATION = 80

# Scheduler θ (FROZEN)
W = 5.0
B_NONE = +1.0
B_L = -1.5
B_R = -1.5
B_SIM = -3.0
TAU = 1.0

# Perturbation (FROZEN except ε)
PERTURB_SEED_OFFSET = 3000

# ε ladder (FROZEN)
EPSILONS = [0.005, 0.01, 0.02, 0.05]

EVENT_SET = ["none", "L", "R", "simultaneous"]


def _unit_region(pos):
    x = pos[0]
    if x < -0.1: return "L"
    elif x > 0.1: return "R"
    return "M"


def _hash_obs(act_l, act_r):
    return hashlib.sha256(f"{act_l:.6f},{act_r:.6f}".encode()).hexdigest()[:16]


def _hash_payload(phi):
    return hashlib.sha256(phi.tobytes()).hexdigest()[:16]


def _hash_trace(trace):
    parts = [f"{t}:{e}:{h}" for t, e, h in trace]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _compute_region_activity(core):
    acts = core._activations
    positions = core._positions
    l_vals, r_vals = [], []
    for uid in range(len(acts)):
        reg = _unit_region(positions[uid])
        if reg == "L": l_vals.append(acts[uid])
        elif reg == "R": r_vals.append(acts[uid])
    act_l = float(np.mean(l_vals)) if l_vals else 0.0
    act_r = float(np.mean(r_vals)) if r_vals else 0.0
    return act_l, act_r


def _fast_weight_l1(core):
    return float(np.sum(np.abs(core._weight_cache)))


def _slow_weight_l1(core):
    return float(np.sum(np.abs(core._slow_weight_cache)))


def _saturation_frac(core):
    eff = core._weight_cache + core._slow_weight_cache
    np.clip(eff, -1.0, 1.0, out=eff)
    return float(np.mean(np.abs(eff) >= 0.999))


def _tag_mass(core):
    return float(np.sum(np.abs(core._tag_cache)))


def _n_tagged(core):
    return int(np.sum(core._tag_cache > 0))


class Scheduler:
    """Parameterized stochastic scheduler. Fixed θ, no learning, no memory."""

    def __init__(self, rng: np.random.Generator):
        self._rng = rng

    def propose(self, activity_L: float, activity_R: float):
        logit_none = B_NONE
        logit_L = W * activity_R + B_L
        logit_R = W * activity_L + B_R
        logit_sim = B_SIM

        logits = np.array([logit_none, logit_L, logit_R, logit_sim], dtype=np.float64)
        logits -= np.max(logits)
        exp_logits = np.exp(logits / TAU)
        probs = exp_logits / np.sum(exp_logits)

        u = float(self._rng.random())
        cum = 0.0
        chosen_idx = 0
        for i, p in enumerate(probs):
            cum += p
            if u < cum:
                chosen_idx = i
                break

        return {
            "logits": {
                "none": float(logit_none), "L": float(logit_L),
                "R": float(logit_R), "simultaneous": float(logit_sim),
            },
            "probs": {
                "none": float(probs[0]), "L": float(probs[1]),
                "R": float(probs[2]), "simultaneous": float(probs[3]),
            },
            "u_draw": u,
            "chosen": EVENT_SET[chosen_idx],
        }


def _build_phi_cache(core):
    n_units = core.unit_count
    phi_l = np.array([L_STIM.influence_at(tuple(core._positions[uid]))
                      for uid in range(n_units)], dtype=np.float64)
    phi_r = np.array([R_STIM.influence_at(tuple(core._positions[uid]))
                      for uid in range(n_units)], dtype=np.float64)
    phi_sim = phi_l + phi_r
    return {"L": phi_l, "R": phi_r, "simultaneous": phi_sim}


def _git_sha():
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def _save_event_log(rows, path):
    if not rows:
        return
    all_fields = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                all_fields.append(k)
                seen.add(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _make_cfg(seed):
    return AnivaConfig(
        unit_count=300,
        seed=seed,
        event_pair_plasticity_enabled=True,
        event_pair_ledger_enabled=True,
        consolidation_enabled=True,
        consolidation_ledger_enabled=True,
    )


# ═══════════════════════════════════════════════════════════════════
# Arm runners (adapted from 10A.3, epsilon now parameterized)
# ═══════════════════════════════════════════════════════════════════

def run_closed_loop(cfg, seed_env, seed_sched, decision_points, pulse_dur,
                    epsilon, code_sha, config_sha):
    core = LifeCore(cfg)
    sched_rng = np.random.default_rng(seed_sched)
    scheduler = Scheduler(sched_rng)
    env = Environment()
    phi_cache = _build_phi_cache(core)

    nan_hit = False
    event_log = []

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        if s in decision_points:
            act_l, act_r = _compute_region_activity(core)
            result = scheduler.propose(act_l, act_r)
            chosen = result["chosen"]

            row = {
                "run_id": f"phase10A2B2_eps{epsilon}_closed_seed{seed_env}",
                "arm": "closed_loop",
                "seed_env": seed_env,
                "epsilon": epsilon,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "activity_L": round(act_l, 8),
                "activity_R": round(act_r, 8),
                "obs_hash": _hash_obs(act_l, act_r),
                "chosen_event": chosen,
                "payload_hash": "",
            }

            if chosen != "none":
                phi = phi_cache[chosen]
                row["payload_hash"] = _hash_payload(phi)

                stim = STIM_MAP.get(chosen)
                if stim is None:
                    env.add_event(StimulusEvent(
                        stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                    env.add_event(StimulusEvent(
                        stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
                else:
                    env.add_event(StimulusEvent(
                        stimulus=stim, start_step=s, duration_steps=pulse_dur))

                core.apply_event_pair_phi(phi)

            event_log.append(row)

    slow = core._slow_weight_cache
    captures = core._consolidation_ledger

    return event_log, {
        "arm": "closed_loop",
        "seed_env": seed_env,
        "epsilon": epsilon,
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "slow_weight_max_abs": round(float(np.max(np.abs(slow))), 8) if len(slow) > 0 else 0.0,
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8) if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }


def run_exact_replay(cfg, seed_env, event_trace, epsilon, pulse_dur,
                     code_sha, config_sha):
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)
    env = Environment()

    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache[chosen]
            actual_hash = _hash_payload(phi)
            if actual_hash != exp_hash:
                hash_mismatches += 1

            stim = STIM_MAP.get(chosen)
            if stim is None:
                env.add_event(StimulusEvent(
                    stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                env.add_event(StimulusEvent(
                    stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
            else:
                env.add_event(StimulusEvent(
                    stimulus=stim, start_step=s, duration_steps=pulse_dur))

            core.apply_event_pair_phi(phi)

            row = {
                "run_id": f"phase10A2B2_eps{epsilon}_exact_seed{seed_env}",
                "arm": "exact_replay",
                "seed_env": seed_env,
                "epsilon": epsilon,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
            }
            event_log.append(row)
            replay_idx += 1

    slow = core._slow_weight_cache
    captures = core._consolidation_ledger

    return event_log, {
        "arm": "exact_replay",
        "seed_env": seed_env,
        "epsilon": epsilon,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "slow_weight_max_abs": round(float(np.max(np.abs(slow))), 8) if len(slow) > 0 else 0.0,
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8) if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }


def run_perturbed_replay(cfg, seed_env, event_trace, epsilon, pulse_dur,
                          code_sha, config_sha):
    core = LifeCore(cfg)
    phi_cache = _build_phi_cache(core)

    # ── Perturbation at t=0 ──
    perturb_rng = np.random.default_rng(seed_env + PERTURB_SEED_OFFSET)
    eps_vec = perturb_rng.uniform(-epsilon, epsilon, size=core.unit_count)
    acts_before = core._activations.copy()
    core._activations += eps_vec
    np.clip(core._activations, 0.0, 1.0, out=core._activations)
    actual_eps = core._activations - acts_before

    perturb_l1 = float(np.sum(np.abs(actual_eps)))
    perturb_l2 = float(np.sqrt(np.sum(actual_eps ** 2)))
    perturb_max = float(np.max(np.abs(actual_eps)))

    env = Environment()
    nan_hit = False
    event_log = []
    replay_idx = 0
    n_expected = len(event_trace)
    hash_mismatches = 0

    for s in range(TOTAL_STEPS):
        influences = env.compute_influences(core.units, s)
        core.step(env_influences=influences if influences else None)

        if not nan_hit and np.any(np.isnan(core._activations)):
            nan_hit = True

        while replay_idx < n_expected and event_trace[replay_idx][0] == s:
            t_dec, chosen, exp_hash = event_trace[replay_idx]
            phi = phi_cache[chosen]
            actual_hash = _hash_payload(phi)
            if actual_hash != exp_hash:
                hash_mismatches += 1

            stim = STIM_MAP.get(chosen)
            if stim is None:
                env.add_event(StimulusEvent(
                    stimulus=L_STIM, start_step=s, duration_steps=pulse_dur))
                env.add_event(StimulusEvent(
                    stimulus=R_STIM, start_step=s, duration_steps=pulse_dur))
            else:
                env.add_event(StimulusEvent(
                    stimulus=stim, start_step=s, duration_steps=pulse_dur))

            core.apply_event_pair_phi(phi)

            row = {
                "run_id": f"phase10A2B2_eps{epsilon}_perturbed_seed{seed_env}",
                "arm": "perturbed_replay",
                "seed_env": seed_env,
                "epsilon": epsilon,
                "code_sha": code_sha, "config_sha": config_sha,
                "t_decision": s,
                "chosen_event": chosen,
                "payload_hash": actual_hash,
                "expected_payload_hash": exp_hash,
                "hash_match": actual_hash == exp_hash,
            }
            event_log.append(row)
            replay_idx += 1

    slow = core._slow_weight_cache
    captures = core._consolidation_ledger

    return event_log, {
        "arm": "perturbed_replay",
        "seed_env": seed_env,
        "epsilon": epsilon,
        "n_expected": n_expected,
        "n_replayed": replay_idx,
        "hash_mismatches": hash_mismatches,
        "perturb_l1": round(perturb_l1, 10),
        "perturb_l2": round(perturb_l2, 10),
        "perturb_max_abs": round(perturb_max, 10),
        "fast_weight_l1": round(_fast_weight_l1(core), 8),
        "slow_weight_l1": round(_slow_weight_l1(core), 8),
        "slow_weight_max_abs": round(float(np.max(np.abs(slow))), 8) if len(slow) > 0 else 0.0,
        "capture_count": len(captures),
        "tag_mass_final": round(_tag_mass(core), 8),
        "n_tagged_connections": _n_tagged(core),
        "saturation_frac": round(_saturation_frac(core), 8),
        "max_abs_weight": round(float(np.max(np.abs(core._weight_cache))), 8) if len(core._weight_cache) > 0 else 0.0,
        "nan_hit": nan_hit,
    }


# ═══════════════════════════════════════════════════════════════════
# Ladder diagnostics
# ═══════════════════════════════════════════════════════════════════

def _compute_ladder_diagnostics(all_summaries, seeds, epsilons):
    """Compute cross-ε diagnostics. Returns dict of diagnostics per seed."""
    diag = {}
    for seed in seeds:
        seed_sums = [s for s in all_summaries if s["seed_env"] == seed]
        by_eps_arm = {}
        for s in seed_sums:
            key = (s["epsilon"], s["arm"])
            by_eps_arm[key] = s

        # Collect ε → slow Δ for monotonicity check
        eps_slow_delta = []
        eps_fast_delta = []
        eps_amp_ratio = []
        eps_capture_delta = []

        for eps in epsilons:
            cl = by_eps_arm.get((eps, "closed_loop"), {})
            ex = by_eps_arm.get((eps, "exact_replay"), {})
            pe = by_eps_arm.get((eps, "perturbed_replay"), {})

            cl_sl = cl.get("slow_weight_l1", float("nan"))
            ex_sl = ex.get("slow_weight_l1", float("nan"))
            pe_sl = pe.get("slow_weight_l1", float("nan"))

            cl_fl = cl.get("fast_weight_l1", float("nan"))
            pe_fl = pe.get("fast_weight_l1", float("nan"))

            slow_d = abs(ex_sl - pe_sl)
            fast_d = abs(cl_fl - pe_fl)
            amp = slow_d / fast_d if fast_d > 1e-30 else 0.0

            eps_slow_delta.append(slow_d)
            eps_fast_delta.append(fast_d)
            eps_amp_ratio.append(amp)
            eps_capture_delta.append(
                cl.get("capture_count", 0) - pe.get("capture_count", 0))

        # Monotonicity: slow_delta non-decreasing with epsilon
        monotonic = all(
            eps_slow_delta[i] <= eps_slow_delta[i + 1] + 1e-15
            for i in range(len(eps_slow_delta) - 1)
        )

        # Threshold: lowest epsilon with |slow Δ| > 0
        threshold = None
        for i, eps in enumerate(epsilons):
            if eps_slow_delta[i] > 1e-15:
                threshold = eps
                break

        # Any slow signal at all?
        any_slow_signal = any(d > 1e-15 for d in eps_slow_delta)

        # Any fast signal at all?
        any_fast_signal = any(d > 1e-15 for d in eps_fast_delta)

        # Saturation check
        any_saturation = False
        for eps in epsilons:
            for arm_name in ["closed_loop", "exact_replay", "perturbed_replay"]:
                s = by_eps_arm.get((eps, arm_name), {})
                if s.get("saturation_frac", 0.0) > 0.5:
                    any_saturation = True

        diag[seed] = {
            "epsilons": epsilons,
            "slow_deltas": [round(d, 12) for d in eps_slow_delta],
            "fast_deltas": [round(d, 12) for d in eps_fast_delta],
            "amp_ratios": [round(r, 8) for r in eps_amp_ratio],
            "capture_deltas": eps_capture_delta,
            "monotonic": monotonic,
            "threshold_epsilon": threshold,
            "any_slow_signal": any_slow_signal,
            "any_fast_signal": any_fast_signal,
            "any_saturation": any_saturation,
        }

    return diag


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Phase 10A.2B.2 — Epsilon Sensitivity Ladder (diagnostic)")
    p.add_argument("--seeds", type=int, nargs="+", default=[42, 77])
    p.add_argument("--epsilons", type=float, nargs="+", default=EPSILONS)
    p.add_argument("--unit-count", type=int, default=300)
    p.add_argument("--total-steps", type=int, default=TOTAL_STEPS)
    p.add_argument("--decision-interval", type=int, default=DECISION_INTERVAL)
    p.add_argument("--estimate-only", action="store_true")
    p.add_argument("--dry-run-schedule", action="store_true")
    p.add_argument("--output-csv", type=str,
                   default="results/phase10A2B2_epsilon_ladder.csv")
    p.add_argument("--events-csv", type=str,
                   default="results/phase10A2B2_epsilon_ladder_events.csv")
    p.add_argument("--summary-json", type=str,
                   default="results/phase10A2B2_epsilon_ladder_summary.json")
    args = p.parse_args(argv)

    warmup = WARMUP
    pulse_dur = PULSE_DURATION
    decision_points = list(range(warmup, args.total_steps, args.decision_interval))
    n_decisions = len(decision_points)
    epsilons = args.epsilons
    seeds = args.seeds

    print("Phase 10A.2B.2 — Epsilon Sensitivity Ladder (diagnostic, not tuning)")
    print(f"  seeds={seeds}  epsilons={epsilons}")
    print(f"  unit_count={args.unit_count}  steps={args.total_steps}"
          f"  interval={args.decision_interval}")
    print(f"  decision_points={n_decisions}")
    print(f"  scheduler θ: w={W} b_none={B_NONE} b_L={B_L} b_R={B_R}"
          f"  b_sim={B_SIM} tau={TAU}")
    print(f"  9C ON  9D ON")
    print(f"  arms per ε: closed_loop, exact_replay, perturbed_replay")
    print()

    if args.dry_run_schedule:
        print(f"  ε ladder: {epsilons}")
        print(f"  ε variants: {len(epsilons)}")
        print(f"  Arms per ε: 3 (closed, exact, perturbed)")
        print(f"  Total arms: {len(epsilons) * 3} × {len(seeds)} seeds"
              f" = {len(epsilons) * 3 * len(seeds)}")
        print(f"  Decision points (first 5): {decision_points[:5]}...")
        print(f"  Decision points (last 5): ...{decision_points[-5:]}")
        print(f"  Estimated per ε per seed: ~300s")
        print(f"  Total estimated:"
              f" ~{len(epsilons) * 300 * len(seeds) / 60:.0f} min")
        print(f"  ← MUST run on ECS (> 15 min threshold)")
        print()
        return 0

    code_sha = _git_sha()
    all_event_rows = []
    all_summaries = []

    if args.estimate_only:
        # Sample one closed_loop per seed to estimate per-ε cost
        for seed in seeds:
            print(f"── Seed {seed} (estimate) ──")
            cfg = _make_cfg(seed)
            config_sha = hashlib.sha256(
                json.dumps({k: v for k, v in cfg.__dict__.items()
                            if not k.startswith("_")}, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]

            # Run closed_loop once for timing
            print(f"  Sampling closed_loop ...", end=" ", flush=True)
            t0 = time.time()
            el, s_info = run_closed_loop(
                cfg, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=pulse_dur,
                epsilon=epsilons[0], code_sha=code_sha, config_sha=config_sha)
            wall_closed = time.time() - t0
            n_events = sum(1 for d in el if d["chosen_event"] != "none")
            print(f"{wall_closed:.0f}s  events={n_events}")

            # Exact replay + perturbed estimate from closed timing
            wall_exact = wall_closed * 1.0
            wall_pert = wall_closed * 1.0
            per_eps = wall_closed + wall_exact + wall_pert

            print(f"    Per-ε estimate: ~{per_eps:.0f}s"
                  f"  ({len(epsilons)} ε × ~{per_eps:.0f}s"
                  f" = ~{len(epsilons) * per_eps:.0f}s per seed)")
        total_est = len(epsilons) * per_eps * len(seeds)
        print(f"\n  Total estimate: ~{total_est:.0f}s"
              f" = ~{total_est / 60:.0f} min")
        print(f"  {'← ECS required (>15 min)' if total_est > 900 else '← OK for local'}")
        return 0

    # ── Full run: iterate ε × seeds ──
    for eps in epsilons:
        print(f"══════ ε = {eps} ══════")

        for seed in seeds:
            print(f"── Seed {seed}, ε={eps} ──")

            cfg = _make_cfg(seed)
            assert cfg.event_pair_plasticity_enabled
            assert cfg.consolidation_enabled

            config_sha = hashlib.sha256(
                json.dumps({k: v for k, v in cfg.__dict__.items()
                            if not k.startswith("_")}, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]

            # ── Arm 1: closed_loop ──
            print(f"  [1/3] closed_loop ...", end=" ", flush=True)
            t0 = time.time()
            el_closed, s_closed = run_closed_loop(
                cfg, seed_env=seed, seed_sched=seed + 1000,
                decision_points=decision_points, pulse_dur=pulse_dur,
                epsilon=eps, code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0

            n_events = sum(1 for d in el_closed if d["chosen_event"] != "none")
            L_count = sum(1 for d in el_closed if d["chosen_event"] == "L")
            R_count = sum(1 for d in el_closed if d["chosen_event"] == "R")
            sim_count = sum(1 for d in el_closed if d["chosen_event"] == "simultaneous")

            print(f"{wall:.0f}s  events={n_events}"
                  f"  L={L_count} R={R_count} sim={sim_count}"
                  f"  captures={s_closed['capture_count']}"
                  f"  slow_l1={s_closed['slow_weight_l1']:.6f}")

            event_trace = []
            for d in el_closed:
                if d["chosen_event"] != "none":
                    event_trace.append((d["t_decision"], d["chosen_event"],
                                        d["payload_hash"]))
            trace_hash = _hash_trace(event_trace)

            s_closed.update({
                "event_count": n_events,
                "L_count": L_count, "R_count": R_count,
                "simultaneous_count": sim_count,
                "trace_hash": trace_hash,
                "wall_time_s": round(wall, 1),
            })
            all_event_rows.extend(el_closed)
            all_summaries.append(s_closed)

            # ── Arm 2: exact_replay ──
            print(f"  [2/3] exact_replay (mirror check) ...", end=" ", flush=True)
            t0 = time.time()
            cfg_replay = _make_cfg(seed)
            el_exact, s_exact = run_exact_replay(
                cfg_replay, seed_env=seed, event_trace=event_trace,
                epsilon=eps, pulse_dur=pulse_dur,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0

            replay_exact = (s_exact["hash_mismatches"] == 0
                            and s_exact["n_replayed"] == s_exact["n_expected"])
            s_exact.update({
                "trace_hash": trace_hash,
                "wall_time_s": round(wall, 1),
                "replay_exact": replay_exact,
            })
            all_event_rows.extend(el_exact)
            all_summaries.append(s_exact)

            status = "EXACT" if replay_exact else "MISMATCH"
            print(f"{wall:.0f}s  replayed={s_exact['n_replayed']}"
                  f"  captures={s_exact['capture_count']}"
                  f"  slow_l1={s_exact['slow_weight_l1']:.6f}"
                  f"  [{status}]")

            # ── Arm 3: perturbed_replay ──
            print(f"  [3/3] perturbed_replay (ε={eps}) ...", end=" ", flush=True)
            t0 = time.time()
            cfg_pert = _make_cfg(seed)
            el_pert, s_pert = run_perturbed_replay(
                cfg_pert, seed_env=seed, event_trace=event_trace,
                epsilon=eps, pulse_dur=pulse_dur,
                code_sha=code_sha, config_sha=config_sha)
            wall = time.time() - t0

            replay_exact_p = (s_pert["hash_mismatches"] == 0
                              and s_pert["n_replayed"] == s_pert["n_expected"])
            s_pert.update({
                "trace_hash": trace_hash,
                "wall_time_s": round(wall, 1),
                "replay_exact": replay_exact_p,
            })
            all_event_rows.extend(el_pert)
            all_summaries.append(s_pert)

            status_p = "EXACT" if replay_exact_p else "MISMATCH"
            print(f"{wall:.0f}s  replayed={s_pert['n_replayed']}"
                  f"  captures={s_pert['capture_count']}"
                  f"  slow_l1={s_pert['slow_weight_l1']:.6f}"
                  f"  perturb_l1={s_pert['perturb_l1']:.4f}"
                  f"  [{status_p}]")

    # ── Per-ε, per-seed summary table ──
    print()
    print("══ Per-ε / Per-Seed Summary ══")
    header = (f"  {'ε':>6} {'Seed':>5} {'Arm':<18}"
              f" {'Slow_L1':>12} {'Fast_L1':>12}"
              f" {'Captures':>9} {'TagMass':>10} {'Satur%':>7}"
              f" {'Perturb_L1':>12} {'NaN':>5}")
    print(header)
    print(f"  {'-'*6} {'-'*5} {'-'*18} {'-'*12} {'-'*12}"
          f" {'-'*9} {'-'*10} {'-'*7} {'-'*12} {'-'*5}")
    for s in all_summaries:
        perturb_str = f"{s.get('perturb_l1', 0):.4f}" if "perturb_l1" in s else "N/A"
        print(f"  {s['epsilon']:>6.3f} {s['seed_env']:>5} {s['arm']:<18}"
              f" {s['slow_weight_l1']:>12.8f}"
              f" {s['fast_weight_l1']:>12.6f}"
              f" {s['capture_count']:>9}"
              f" {s['tag_mass_final']:>10.6f}"
              f" {s['saturation_frac']:>6.4f}"
              f" {perturb_str:>12}"
              f" {'Y' if s['nan_hit'] else 'N':>5}")
    print()

    # ── Per-ε, per-seed cross-arm deltas ──
    print("══ Cross-Arm Deltas (per ε, per seed) ══")
    for seed in seeds:
        for eps in epsilons:
            seed_eps_sums = [s for s in all_summaries
                             if s["seed_env"] == seed and s["epsilon"] == eps]
            by_arm = {s["arm"]: s for s in seed_eps_sums}
            cl = by_arm.get("closed_loop", {})
            ex = by_arm.get("exact_replay", {})
            pe = by_arm.get("perturbed_replay", {})

            cl_sl = cl.get("slow_weight_l1", float("nan"))
            ex_sl = ex.get("slow_weight_l1", float("nan"))
            pe_sl = pe.get("slow_weight_l1", float("nan"))
            cl_fl = cl.get("fast_weight_l1", float("nan"))
            pe_fl = pe.get("fast_weight_l1", float("nan"))

            d_ce = cl_sl - ex_sl
            d_cp = cl_sl - pe_sl
            d_ep_slow = ex_sl - pe_sl
            d_cp_fast = cl_fl - pe_fl

            amp = abs(d_ep_slow) / abs(d_cp_fast) if abs(d_cp_fast) > 1e-30 else 0.0

            mirror_ok = abs(d_ce) < max(1e-6, 0.01 * cl_sl) if cl_sl > 0 else True

            print(f"  Seed {seed}  ε={eps}:")
            print(f"    slow_l1:  closed={cl_sl:.8f}  exact={ex_sl:.8f}"
                  f"  perturbed={pe_sl:.8f}")
            print(f"    fast_l1:  closed={cl_fl:.6f}  perturbed={pe_fl:.6f}")
            print(f"    Δ(closed-exact)_slow     = {d_ce:.8f}"
                  f"  {'← MIRROR OK' if mirror_ok else '← PROTOCOL BUG'}")
            print(f"    Δ(closed-perturbed)_slow = {d_cp:.8f}")
            print(f"    Δ(exact-perturbed)_slow  = {d_ep_slow:.8f}")
            print(f"    Δ(closed-perturbed)_fast = {d_cp_fast:.8f}")
            print(f"    amplification_ratio      = {amp:.6f}")
            print(f"    captures:"
                  f" closed={cl.get('capture_count','?')}"
                  f" exact={ex.get('capture_count','?')}"
                  f" perturbed={pe.get('capture_count','?')}")
    print()

    # ── Ladder-wide diagnostics ──
    ladder_diag = _compute_ladder_diagnostics(all_summaries, seeds, epsilons)

    print("══ Ladder-Wide Diagnostics ══")
    for seed in seeds:
        d = ladder_diag[seed]
        print(f"  Seed {seed}:")
        print(f"    ε values:          {d['epsilons']}")
        print(f"    slow Δ:            {d['slow_deltas']}")
        print(f"    fast Δ:            {d['fast_deltas']}")
        print(f"    amp ratio:         {d['amp_ratios']}")
        print(f"    capture Δ:         {d['capture_deltas']}")
        print(f"    monotonic?         {d['monotonic']}")
        print(f"    threshold ε:       {d['threshold_epsilon']}")
        print(f"    any slow signal?   {d['any_slow_signal']}")
        print(f"    any fast signal?   {d['any_fast_signal']}")
        print(f"    saturation?        {d['any_saturation']}")
    print()

    # ── Hard protocol (per ε, per seed) ──
    print("══ Hard Protocol (per ε, per seed) ══")
    all_hard_pass = True
    hard_results = []
    for seed in seeds:
        for eps in epsilons:
            seed_eps_sums = [s for s in all_summaries
                             if s["seed_env"] == seed and s["epsilon"] == eps]
            by_arm = {s["arm"]: s for s in seed_eps_sums}

            p1 = not any(s["nan_hit"] for s in seed_eps_sums)
            p2 = all(s["max_abs_weight"] < 10.0 for s in seed_eps_sums)
            p3 = all(s.get("hash_mismatches", 0) == 0 for s in seed_eps_sums
                     if s["arm"] != "closed_loop")
            cl_ev = by_arm.get("closed_loop", {}).get("event_count", -1)
            ex_ev = by_arm.get("exact_replay", {}).get("n_replayed", -1)
            pe_ev = by_arm.get("perturbed_replay", {}).get("n_replayed", -1)
            p4 = (cl_ev == ex_ev == pe_ev) and cl_ev >= 0

            cl_sl = by_arm.get("closed_loop", {}).get("slow_weight_l1", 0.0)
            ex_sl = by_arm.get("exact_replay", {}).get("slow_weight_l1", 0.0)
            p5 = abs(cl_sl - ex_sl) < max(1e-6, 0.01 * cl_sl) if cl_sl > 0 else True

            tier_ok = p1 and p2 and p3 and p4 and p5
            if not tier_ok:
                all_hard_pass = False

            hard_results.append({
                "seed": seed, "epsilon": eps,
                "P1_nan": p1, "P2_explosion": p2,
                "P3_replay_hash": p3, "P4_event_count": p4,
                "P5_mirror_sanity": p5,
                "hard_pass": tier_ok,
            })

            print(f"  Seed {seed}  ε={eps}:"
                  f"  P1={'OK' if p1 else 'FAIL'}"
                  f"  P2={'OK' if p2 else 'FAIL'}"
                  f"  P3={'OK' if p3 else 'FAIL'}"
                  f"  P4={'OK' if p4 else 'FAIL'}"
                  f"  P5={'OK' if p5 else 'FAIL'}"
                  f"  → {'PASS' if tier_ok else 'FAIL'}")
    print()

    n_pass = sum(1 for r in hard_results if r["hard_pass"])
    n_total = len(hard_results)
    print(f"  Hard pass: {n_pass}/{n_total}")
    print()

    # ── Overall diagnostic verdict ──
    print("══ Diagnostic Verdict ══")
    for seed in seeds:
        d = ladder_diag[seed]
        if not d["any_slow_signal"]:
            if d["any_fast_signal"]:
                print(f"  Seed {seed}: FAST DIVERGENCE BUT NO SLOW SIGNAL —"
                      f" 9D capture insensitive to this perturbation class"
                      f" at ε ≤ {epsilons[-1]}.")
            else:
                print(f"  Seed {seed}: NO FAST OR SLOW SIGNAL —"
                      f" perturbation too small to affect even fast layer.")
        elif d["threshold_epsilon"] is not None:
            print(f"  Seed {seed}: THRESHOLD FOUND at ε = {d['threshold_epsilon']}"
                  f" — classify as threshold effect, do NOT promote ε.")
        if d["monotonic"]:
            print(f"  Seed {seed}: Slow Δ is monotonic in ε — sensitivity curve established.")
        if d["any_saturation"]:
            print(f"  Seed {seed}: WARNING — saturation detected at some ε tier."
                  f" Invalid for interpretation at that tier.")
    print()

    # ── Save outputs ──
    if args.events_csv:
        _save_event_log(all_event_rows, args.events_csv)
        print(f"  Events CSV: {args.events_csv} ({len(all_event_rows)} rows)")

    if args.output_csv:
        if all_summaries:
            all_sf, seen_sf = [], set()
            for s in all_summaries:
                for k in s:
                    if k not in seen_sf and not isinstance(s[k], (np.ndarray, list, dict)):
                        all_sf.append(k)
                        seen_sf.add(k)
            with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=all_sf, extrasaction="ignore")
                w.writeheader()
                w.writerows(all_summaries)
            print(f"  Summary CSV: {args.output_csv}")

    if args.summary_json:
        json_sums = []
        for s in all_summaries:
            js = {}
            for k, v in s.items():
                if isinstance(v, (np.ndarray, list)):
                    js[k] = float(v) if isinstance(v, (np.floating, float, int)) else str(v)
                else:
                    js[k] = v
            json_sums.append(js)

        # Serialize ladder diagnostics
        json_ladder = {}
        for seed, d in ladder_diag.items():
            json_ladder[str(seed)] = d

        with open(args.summary_json, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "phase10A2B2_epsilon_sensitivity_ladder",
                "frozen_params": {
                    "w": W, "b_none": B_NONE, "b_L": B_L, "b_R": B_R,
                    "b_sim": B_SIM, "tau": TAU,
                    "total_steps": args.total_steps,
                    "warmup": warmup,
                    "decision_interval": args.decision_interval,
                    "pulse_duration": pulse_dur,
                    "epsilons": epsilons,
                    "perturb_seed_offset": PERTURB_SEED_OFFSET,
                    "perturbation_target": "activations only",
                    "perturbation_distribution": "uniform [-ε, +ε], zero-mean, clip [0,1]",
                    "9C_enabled": True,
                    "9D_enabled": True,
                },
                "summaries": json_sums,
                "hard_protocol": hard_results,
                "ladder_diagnostics": json_ladder,
                "n_hard_pass": n_pass,
                "n_tiers": n_total,
            }, f, indent=2, ensure_ascii=False)
        print(f"  JSON: {args.summary_json}")

    return 0 if all_hard_pass else 1


if __name__ == "__main__":
    sys.exit(main())
