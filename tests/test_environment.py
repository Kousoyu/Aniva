"""环境模块测试 — PointStimulus + Environment + LifeCore 集成."""

import numpy as np
import pytest
from aniva.config import AnivaConfig
from aniva.environment.environment import Stimulus, Environment
from aniva.life_core import LifeCore


class TestStimulus:
    """PointStimulus 单元测试."""

    def test_default_construction(self):
        s = Stimulus(position=(0.0, 0.0, 0.0))
        assert s.intensity == 1.0
        assert s.radius == 0.3
        assert s.start_step == 0
        assert s.duration_steps == 100

    def test_custom_construction(self):
        s = Stimulus(
            position=(0.5, 0.5, 0.5),
            intensity=0.5,
            radius=0.2,
            start_step=50,
            duration_steps=200,
        )
        assert s.position == (0.5, 0.5, 0.5)
        assert s.intensity == 0.5
        assert s.radius == 0.2
        assert s.start_step == 50
        assert s.duration_steps == 200
        assert s.end_step == 250

    def test_radius_must_be_positive(self):
        with pytest.raises(ValueError):
            Stimulus(position=(0.0, 0.0, 0.0), radius=0.0)
        with pytest.raises(ValueError):
            Stimulus(position=(0.0, 0.0, 0.0), radius=-0.1)

    def test_duration_steps_must_be_positive(self):
        with pytest.raises(ValueError):
            Stimulus(position=(0.0, 0.0, 0.0), duration_steps=0)
        with pytest.raises(ValueError):
            Stimulus(position=(0.0, 0.0, 0.0), duration_steps=-5)

    def test_start_step_must_be_non_negative(self):
        with pytest.raises(ValueError):
            Stimulus(position=(0.0, 0.0, 0.0), start_step=-1)

    def test_is_active_within_window(self):
        s = Stimulus(position=(0.0, 0.0, 0.0), start_step=100, duration_steps=50)
        assert not s.is_active(0)
        assert not s.is_active(99)
        assert s.is_active(100)
        assert s.is_active(120)
        assert s.is_active(149)
        assert not s.is_active(150)

    def test_is_active_default_window(self):
        s = Stimulus(position=(0.0, 0.0, 0.0))
        assert s.is_active(0)
        assert s.is_active(50)
        assert s.is_active(99)
        assert not s.is_active(100)

    def test_influence_at_center_is_full_intensity(self):
        s = Stimulus(position=(0.0, 0.0, 0.0), intensity=0.8, radius=0.5)
        assert s.influence_at((0.0, 0.0, 0.0)) == pytest.approx(0.8)

    def test_influence_at_edge_is_zero(self):
        s = Stimulus(position=(0.0, 0.0, 0.0), intensity=0.8, radius=0.5)
        # Distance == radius → influence should be 0
        assert s.influence_at((0.5, 0.0, 0.0)) == pytest.approx(0.0)

    def test_influence_outside_radius_is_zero(self):
        s = Stimulus(position=(0.0, 0.0, 0.0), radius=0.3)
        assert s.influence_at((1.0, 0.0, 0.0)) == 0.0
        assert s.influence_at((0.0, 0.5, 0.0)) == 0.0

    def test_influence_linear_decay(self):
        s = Stimulus(position=(0.0, 0.0, 0.0), intensity=1.0, radius=1.0)
        # At distance 0.3, influence = 1.0 * (1 - 0.3/1.0) = 0.7
        assert s.influence_at((0.3, 0.0, 0.0)) == pytest.approx(0.7)

    def test_influence_negative_intensity(self):
        s = Stimulus(position=(0.0, 0.0, 0.0), intensity=-0.5, radius=1.0)
        assert s.influence_at((0.0, 0.0, 0.0)) == pytest.approx(-0.5)
        assert s.influence_at((0.5, 0.0, 0.0)) == pytest.approx(-0.25)


class TestEnvironment:
    """Environment 容器测试."""

    def test_empty_environment_returns_empty(self):
        env = Environment()
        units = {0: type("U", (), {"position": (0.0, 0.0, 0.0)})()}
        result = env.compute_influences(units, step=0)
        assert result == {}

    def test_add_and_remove_stimulus(self):
        env = Environment()
        s = Stimulus(position=(0.0, 0.0, 0.0))
        env.add_stimulus(s)
        assert len(env.stimuli) == 1
        env.remove_stimulus(0)
        assert len(env.stimuli) == 0

    def test_remove_invalid_index_does_nothing(self):
        env = Environment()
        env.add_stimulus(Stimulus(position=(0.0, 0.0, 0.0)))
        env.remove_stimulus(5)
        env.remove_stimulus(-1)
        assert len(env.stimuli) == 1

    def test_single_stimulus_influences_nearby_units(self):
        env = Environment()
        env.add_stimulus(Stimulus(
            position=(0.0, 0.0, 0.0), intensity=1.0, radius=0.5, duration_steps=10
        ))
        units = {
            0: type("U", (), {"position": (0.0, 0.0, 0.0)})(),
            1: type("U", (), {"position": (1.0, 0.0, 0.0)})(),
        }
        result = env.compute_influences(units, step=5)
        assert 0 in result
        assert result[0] == pytest.approx(1.0)
        # Unit 1 is outside radius, should not appear
        assert 1 not in result

    def test_stimulus_outside_window_ignored(self):
        env = Environment()
        env.add_stimulus(Stimulus(
            position=(0.0, 0.0, 0.0), start_step=100, duration_steps=10
        ))
        units = {0: type("U", (), {"position": (0.0, 0.0, 0.0)})()}
        result = env.compute_influences(units, step=50)
        assert result == {}

    def test_multiple_stimuli_aggregate(self):
        env = Environment()
        env.add_stimulus(Stimulus(
            position=(0.0, 0.0, 0.0), intensity=0.5, radius=1.0, duration_steps=10,
        ))
        env.add_stimulus(Stimulus(
            position=(0.0, 0.0, 0.0), intensity=0.3, radius=1.0, duration_steps=10,
        ))
        units = {0: type("U", (), {"position": (0.0, 0.0, 0.0)})()}
        result = env.compute_influences(units, step=5)
        assert result[0] == pytest.approx(0.8)

    def test_different_positions_affect_different_units(self):
        env = Environment()
        env.add_stimulus(Stimulus(
            position=(0.0, 0.0, 0.0), intensity=1.0, radius=0.3, duration_steps=10,
        ))
        env.add_stimulus(Stimulus(
            position=(0.8, 0.0, 0.0), intensity=1.0, radius=0.3, duration_steps=10,
        ))
        units = {
            0: type("U", (), {"position": (0.0, 0.0, 0.0)})(),
            1: type("U", (), {"position": (0.8, 0.0, 0.0)})(),
        }
        result = env.compute_influences(units, step=5)
        assert 0 in result
        assert 1 in result
        # Each gets full intensity from its matching stimulus
        assert result[0] == pytest.approx(1.0)
        assert result[1] == pytest.approx(1.0)


class TestLifeCoreWithEnvironment:
    """LifeCore 集成环境输入测试."""

    def test_empty_and_none_env_influences_produce_same_result(self):
        """空 dict 和 None 的行为完全一致（环境层 no-op，其余动力学正常执行）。"""
        cfg = AnivaConfig(unit_count=50, seed=42)
        core_a = LifeCore(cfg)
        core_b = LifeCore(cfg)
        core_a.step(env_influences={})
        core_b.step(env_influences=None)
        acts_a = [u.activation for u in core_a.units.values()]
        acts_b = [u.activation for u in core_b.units.values()]
        assert acts_a == pytest.approx(acts_b)

    def test_env_influence_increases_activation(self):
        cfg = AnivaConfig(unit_count=50, seed=42)
        core = LifeCore(cfg)
        # Stimulate unit 0 with positive influence
        core.step(env_influences={0: 0.5})
        # Unit 0 should have increased activation
        u0 = core.units[0]
        assert u0.activation > 0.0

    def test_env_influence_before_synaptic_transmission(self):
        """环境输入在突触传递之前应用。

        刺激 unit 0 → 同一 step 内，unit 0 的 activation 变化
        通过 connections 传播到其 targets。
        """
        cfg = AnivaConfig(unit_count=50, seed=42, synaptic_strength=0.30)
        core = LifeCore(cfg)
        # Record activations before stimulus
        before_all = {uid: u.activation for uid, u in core.units.items()}
        # Apply strong stimulus to unit 0
        core.step(env_influences={0: 1.0})
        # unit 0 should be affected directly
        assert core.units[0].activation > before_all[0]
        # Some of unit 0's targets should also have changed
        # (through synaptic transmission in the same step)
        targets_of_0 = [
            c.target_id for c in core.connections if c.source_id == 0
        ]
        if targets_of_0:
            target_activations = [core.units[t].activation for t in targets_of_0]
            target_before = [before_all[t] for t in targets_of_0]
            # At least some difference expected from synaptic propagation
            assert target_activations != target_before

    def test_negative_stimulus_reduces_activation(self):
        cfg = AnivaConfig(unit_count=50, seed=42)
        core = LifeCore(cfg)
        # First give some activation
        core.step(env_influences={0: 0.5})
        mid = core.units[0].activation
        # Then inhibitory stimulus
        core.step(env_influences={0: -0.3})
        after_inhib = core.units[0].activation
        # After inhibition, activation should be lower (or at least not higher)
        assert after_inhib <= mid + 1e-9  # allow float tolerance

    def test_stimulus_effect_is_spatial(self):
        """刺激只影响空间上靠近的单元。"""
        cfg = AnivaConfig(unit_count=100, seed=42)
        core = LifeCore(cfg)
        env = Environment()
        # Place stimulus at positive x corner
        env.add_stimulus(Stimulus(
            position=(0.8, 0.0, 0.0),
            intensity=1.0,
            radius=0.3,
            duration_steps=10,
        ))
        before = {uid: u.activation for uid, u in core.units.items()}
        influences = env.compute_influences(core.units, step=0)
        core.step(env_influences=influences)
        # Units near (0.8, 0, 0) should be affected more
        affected = [
            uid for uid in influences
            if abs(core.units[uid].activation - before[uid]) > 1e-9
        ]
        unaffected = [
            uid for uid in core.units
            if uid not in influences
        ]
        # Affected units should be close to stimulus position
        for uid in affected:
            pos = core.units[uid].position
            dist = ((pos[0] - 0.8)**2 + pos[1]**2 + pos[2]**2) ** 0.5
            assert dist < 0.3 + 0.01  # within radius + epsilon
        # Unaffected units should be farther
        for uid in unaffected:
            pos = core.units[uid].position
            dist = ((pos[0] - 0.8)**2 + pos[1]**2 + pos[2]**2) ** 0.5
            assert dist >= 0.3 - 1e-9

    def test_determinism_same_stimulus_same_result(self):
        """相同 seed + 相同刺激 = 相同结果。"""
        def run_with_stimulus():
            cfg = AnivaConfig(unit_count=50, seed=99)
            core = LifeCore(cfg)
            env = Environment()
            env.add_stimulus(Stimulus(
                position=(0.0, 0.0, 0.0),
                intensity=0.5,
                radius=0.5,
                duration_steps=20,
            ))
            for step in range(50):
                influences = env.compute_influences(core.units, step)
                core.step(env_influences=influences)
            return [u.activation for u in core.units.values()]

        result_a = run_with_stimulus()
        result_b = run_with_stimulus()
        assert result_a == pytest.approx(result_b)

    def test_no_stimulus_matches_baseline_free_run(self):
        """无刺激时行为与原始 free-run 一致。"""
        cfg = AnivaConfig(unit_count=50, seed=42)
        core_a = LifeCore(cfg)
        core_b = LifeCore(cfg)
        env = Environment()  # empty
        for step in range(100):
            influences = env.compute_influences(core_a.units, step)
            core_a.step(env_influences=influences)
            core_b.step(env_influences=None)
        acts_a = [u.activation for u in core_a.units.values()]
        acts_b = [u.activation for u in core_b.units.values()]
        assert acts_a == pytest.approx(acts_b)

    def test_stimulus_removal_leaves_trace(self):
        """刺激移除后状态不会完全回到刺激前。

        实验 2 的核心验证：外界经历会留下痕迹。
        """
        cfg = AnivaConfig(unit_count=100, seed=42)
        core = LifeCore(cfg)
        env = Environment()
        env.add_stimulus(Stimulus(
            position=(0.0, 0.0, 0.0),
            intensity=0.5,
            radius=0.5,
            start_step=50,
            duration_steps=100,
        ))
        # Run 300 steps
        for step in range(300):
            influences = env.compute_influences(core.units, step)
            core.step(env_influences=influences)
        # After stimulus ends (step 150), the system continues
        # State at step 200 should differ from a no-stimulus run at step 200
        # due to trace accumulation and network propagation
        cfg2 = AnivaConfig(unit_count=100, seed=42)
        core_no_stim = LifeCore(cfg2)
        for _ in range(300):
            core_no_stim.step()
        # The traces should differ
        traces_with = [u.trace for u in core.units.values()]
        traces_without = [u.trace for u in core_no_stim.units.values()]
        # Not all traces should be identical
        assert not all(
            abs(a - b) < 1e-12
            for a, b in zip(traces_with, traces_without)
        )


class TestExp2Stimulus:
    """实验 2 集成测试 — exp2_stimulus.run() 端到端验证."""

    def test_run_completes_without_error(self):
        from aniva.experiments.exp2_stimulus import run
        cfg = AnivaConfig(unit_count=50, seed=42)
        result = run(
            config=cfg, total_steps=100,
            stim_start=30, stim_duration=20,
            stim_radius=0.5, stim_intensity=0.03,
            report_interval=999,  # suppress output
        )
        assert result["config_seed"] == 42
        assert result["total_steps"] == 100
        assert len(result["trajectory_history"]) == 100

    def test_pre_stimulus_trajectories_near_identical(self):
        """同 seed 下，刺激开始前 baseline 和 stimulus 轨迹应接近一致。"""
        from aniva.experiments.exp2_stimulus import run
        cfg = AnivaConfig(unit_count=50, seed=42)
        result = run(
            config=cfg, total_steps=100,
            stim_start=50, stim_duration=20,
            stim_radius=0.5, stim_intensity=0.03,
            report_interval=999,
        )
        # Pre-stimulus phase: trajectory_distance should be near 0
        pre_dists = [
            h["trajectory_distance"]
            for h in result["trajectory_history"]
            if h["phase"] == "pre_stimulus"
        ]
        assert len(pre_dists) > 0
        max_pre_dist = max(pre_dists)
        assert max_pre_dist < 1e-6, (
            f"pre_stimulus trajectories should be identical, "
            f"got max distance={max_pre_dist}"
        )

    def test_during_stimulus_trajectory_diverges(self):
        """刺激期间 trajectory_distance 应大于 0（轨迹分叉）。"""
        from aniva.experiments.exp2_stimulus import run
        cfg = AnivaConfig(unit_count=50, seed=42)
        result = run(
            config=cfg, total_steps=100,
            stim_start=30, stim_duration=30,
            stim_radius=0.5, stim_intensity=0.03,
            report_interval=999,
        )
        during_dists = [
            h["trajectory_distance"]
            for h in result["trajectory_history"]
            if h["phase"] == "during_stimulus"
        ]
        assert len(during_dists) > 0
        assert max(during_dists) > 0, (
            "trajectory_distance should increase during stimulus"
        )

    def test_post_stimulus_distance_recorded(self):
        """刺激结束后 trajectory_distance 仍可记录（不归零）。"""
        from aniva.experiments.exp2_stimulus import run
        cfg = AnivaConfig(unit_count=50, seed=42)
        result = run(
            config=cfg, total_steps=150,
            stim_start=30, stim_duration=30,
            stim_radius=0.5, stim_intensity=0.03,
            report_interval=999,
        )
        post_dists = [
            h["trajectory_distance"]
            for h in result["trajectory_history"]
            if h["phase"] == "post_stimulus"
        ]
        assert len(post_dists) > 0

    def test_stimulated_unit_ratio_in_range(self):
        from aniva.experiments.exp2_stimulus import run
        cfg = AnivaConfig(unit_count=100, seed=42)
        result = run(
            config=cfg, total_steps=50,
            stim_start=20, stim_duration=10,
            stim_radius=0.5, stim_intensity=0.03,
            report_interval=999,
        )
        ratio = result["stimulated_unit_ratio"]
        assert 0.0 <= ratio <= 1.0
        # With radius=0.5 in a [-1,1] space, some units should be in range
        assert ratio > 0.0, "at least some units should be in stimulus radius"

    def test_phase_summaries_have_all_phases(self):
        from aniva.experiments.exp2_stimulus import run
        cfg = AnivaConfig(unit_count=50, seed=42)
        result = run(
            config=cfg, total_steps=60,
            stim_start=20, stim_duration=20,
            stim_radius=0.5, stim_intensity=0.03,
            report_interval=999,
        )
        for phase in ["pre_stimulus", "during_stimulus", "post_stimulus"]:
            assert phase in result["phase_summaries"]
            summary = result["phase_summaries"][phase]
            assert summary["step_count"] > 0
            assert "baseline" in summary
            assert "stimulus" in summary

    def test_determinism_same_params_same_result(self):
        """相同参数运行两次应得到完全一致的结果。"""
        from aniva.experiments.exp2_stimulus import run

        def run_once():
            cfg = AnivaConfig(unit_count=30, seed=77)
            return run(
                config=cfg, total_steps=50,
                stim_start=20, stim_duration=15,
                stim_radius=0.5, stim_intensity=0.03,
                report_interval=999,
            )

        r1 = run_once()
        r2 = run_once()

        # trajectory history should be identical
        d1 = [h["trajectory_distance"] for h in r1["trajectory_history"]]
        d2 = [h["trajectory_distance"] for h in r2["trajectory_history"]]
        assert d1 == pytest.approx(d2)

        # final metrics should match
        for key in ["mean_activation", "mean_energy", "hard_active_ratio"]:
            assert r1["final_stimulus_metrics"][key] == pytest.approx(
                r2["final_stimulus_metrics"][key]
            )

    def test_cli_runs_without_error(self):
        import sys
        from io import StringIO
        from aniva.experiments.exp2_stimulus import main

        old_stdout = sys.stdout
        try:
            sys.stdout = StringIO()
            exit_code = main([
                "--steps", "50",
                "--seed", "42",
                "--unit-count", "30",
                "--stim-start", "20",
                "--stim-duration", "10",
                "--stim-radius", "0.5",
                "--stim-intensity", "0.03",
            ])
            assert exit_code == 0
        finally:
            sys.stdout = old_stdout

    def test_trajectory_distance_grows_over_time(self):
        """刺激期间 trajectory_distance 应随时间增长（累积效应）。"""
        from aniva.experiments.exp2_stimulus import run
        cfg = AnivaConfig(unit_count=50, seed=42)
        result = run(
            config=cfg, total_steps=100,
            stim_start=20, stim_duration=50,
            stim_radius=0.5, stim_intensity=0.03,
            report_interval=999,
        )
        during_dists = [
            h["trajectory_distance"]
            for h in result["trajectory_history"]
            if h["phase"] == "during_stimulus"
        ]
        # Check that the last few distances in the phase are larger than the first few
        first_quarter = np.mean(during_dists[: max(1, len(during_dists) // 4)])
        last_quarter = np.mean(during_dists[-max(1, len(during_dists) // 4):])
        assert last_quarter >= first_quarter, (
            f"trajectory distance should grow during stimulus: "
            f"first_quarter={first_quarter:.8f}, last_quarter={last_quarter:.8f}"
        )


class TestExp2StimulusSweep:
    """实验 2 参数扫描测试."""

    def test_sweep_completes_without_error(self):
        from aniva.experiments.exp2_stimulus_sweep import sweep
        rows = sweep(
            total_steps=80,
            intensities=(0.01, 0.03),
            radii=(0.5,),
            stim_starts=(30,),
            stim_durations=(20,),
            seeds=(42, 77),
        )
        # 2 intensities × 2 seeds = 4 rows
        assert len(rows) == 4

    def test_sweep_row_count_matches_combinations(self):
        from aniva.experiments.exp2_stimulus_sweep import sweep
        rows = sweep(
            total_steps=60,
            intensities=(0.01, 0.05),
            radii=(0.5, 0.7),
            stim_starts=(20,),
            stim_durations=(15,),
            seeds=(1, 42),
        )
        # 2 × 2 × 1 × 1 × 2 = 8
        assert len(rows) == 8

    def test_row_has_all_required_fields(self):
        from aniva.experiments.exp2_stimulus_sweep import sweep
        rows = sweep(
            total_steps=60,
            intensities=(0.03,),
            radii=(0.5,),
            stim_starts=(20,),
            stim_durations=(15,),
            seeds=(42,),
        )
        assert len(rows) == 1
        r = rows[0]
        required = [
            "seed", "stim_intensity", "stim_radius", "stim_start",
            "stim_duration", "stimulated_unit_ratio",
            "during_max_trajectory_distance", "during_mean_trajectory_distance",
            "post_final_trajectory_distance", "post_mean_trajectory_distance",
            "baseline_final_mean_activation", "stimulus_final_mean_activation",
            "baseline_final_mean_energy", "stimulus_final_mean_energy",
            "baseline_final_hard_active_ratio", "stimulus_final_hard_active_ratio",
            "baseline_final_strong_output_ratio",
            "stimulus_final_strong_output_ratio",
            "response_class",
        ]
        for key in required:
            assert key in r, f"missing field: {key}"

    def test_response_class_is_valid(self):
        from aniva.experiments.exp2_stimulus_sweep import sweep
        rows = sweep(
            total_steps=60,
            intensities=(0.01, 0.03, 0.05),
            radii=(0.5,),
            stim_starts=(20,),
            stim_durations=(15,),
            seeds=(42,),
        )
        for r in rows:
            assert r["response_class"] in ("none", "touch", "takeover"), (
                f"invalid response_class: {r['response_class']}"
            )

    def test_sweep_determinism(self):
        from aniva.experiments.exp2_stimulus_sweep import sweep

        def run_once():
            return sweep(
                total_steps=50,
                intensities=(0.01, 0.03),
                radii=(0.5,),
                stim_starts=(20,),
                stim_durations=(10,),
                seeds=(42,),
            )

        r1 = run_once()
        r2 = run_once()
        for row_a, row_b in zip(r1, r2):
            for key in row_a:
                assert row_a[key] == pytest.approx(row_b[key]), (
                    f"non-deterministic field: {key}"
                )

    def test_cli_runs_without_error(self):
        import sys
        from io import StringIO
        from aniva.experiments.exp2_stimulus_sweep import main

        old_stdout = sys.stdout
        try:
            sys.stdout = StringIO()
            exit_code = main([
                "--intensity", "0.01", "0.03",
                "--radius", "0.5",
                "--stim-start", "20",
                "--stim-duration", "15",
                "--seeds", "42", "77",
                "--unit-count", "30",
                "--steps", "50",
            ])
            assert exit_code == 0
        finally:
            sys.stdout = old_stdout

    def test_csv_output_creates_file(self, tmp_path):
        from aniva.experiments.exp2_stimulus_sweep import main
        import sys
        from io import StringIO

        csv_path = tmp_path / "sweep.csv"
        old_stdout = sys.stdout
        try:
            sys.stdout = StringIO()
            exit_code = main([
                "--intensity", "0.01", "0.03",
                "--radius", "0.5",
                "--stim-start", "20",
                "--stim-duration", "15",
                "--seeds", "42",
                "--unit-count", "30",
                "--steps", "50",
                "--output-csv", str(csv_path),
            ])
            assert exit_code == 0
        finally:
            sys.stdout = old_stdout
        assert csv_path.exists()

    def test_touch_detected_for_default_params(self):
        """默认参数下 intensity=0.03 应该被分类为 touch。"""
        from aniva.experiments.exp2_stimulus_sweep import sweep
        rows = sweep(
            total_steps=200,
            intensities=(0.03,),
            radii=(0.5,),
            stim_starts=(50,),
            stim_durations=(50,),
            seeds=(42,),
        )
        assert len(rows) == 1
        assert rows[0]["response_class"] == "touch", (
            f"expected touch, got {rows[0]['response_class']}"
        )

    def test_weak_intensity_classified_as_none(self):
        """极低 intensity 应该被分类为 none。"""
        from aniva.experiments.exp2_stimulus_sweep import sweep
        rows = sweep(
            total_steps=100,
            intensities=(1e-6,),
            radii=(0.1,),
            stim_starts=(30,),
            stim_durations=(30,),
            seeds=(42,),
        )
        assert len(rows) == 1
        assert rows[0]["response_class"] == "none", (
            f"expected none, got {rows[0]['response_class']}"
        )
