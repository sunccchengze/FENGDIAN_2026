"""End-to-end tests for the replaceable quasi-static PPO environment."""

from __future__ import annotations

from pathlib import Path
import unittest

from gymnasium.utils.env_checker import check_env
import numpy as np
import yaml

from optimization_control.environments.mock_quasi_static_plant import (
    MockQuasiStaticPlant,
)
from optimization_control.environments.plant_model import DisturbanceBatch, SteadyPlantOutput
from optimization_control.environments.quasi_static_wind_farm_env import (
    QuasiStaticWindFarmEnv,
    load_quasi_static_env,
)


CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "ppo_single_turbine"
    / "configs"
    / "quasi_static_v0.yaml"
)


class ScaledPlant:
    """Second concrete PlantModel used to prove dependency replacement."""

    def __init__(self, scale: float = 0.97):
        self.base = MockQuasiStaticPlant(turbine_ids=("T01",))
        self.scale = scale

    @property
    def turbine_ids(self):
        return self.base.turbine_ids

    @property
    def rated_power_w(self):
        return self.base.rated_power_w

    def predict_steady(self, disturbance, applied_operating_point):
        output = self.base.predict_steady(disturbance, applied_operating_point)
        power = (output.floris_turbine_power_w * self.scale).astype(np.float32)
        return SteadyPlantOutput(
            turbine_ids=output.turbine_ids,
            floris_turbine_power_w=power,
            floris_farm_power_sum_w=power.sum(
                axis=1, keepdims=True, dtype=np.float32
            ),
            effective_wind_speed_m_s=output.effective_wind_speed_m_s,
            in_domain=output.in_domain,
            ood_score=output.ood_score,
            model_kind="scaled_contract_test_plant",
        )



class FixedSequenceDisturbanceProvider:
    def __init__(self, wind_speeds_m_s):
        self.wind_speeds_m_s = tuple(float(value) for value in wind_speeds_m_s)
        self.seen_steps = []
    def reset(self, *, seed=None):
        del seed
        self.seen_steps = []

    def at(self, step_index):
        self.seen_steps.append(step_index)
        speed = self.wind_speeds_m_s[min(step_index, len(self.wind_speeds_m_s) - 1)]
        return DisturbanceBatch(
            ambient_wind_speed_m_s=np.array([[speed]], dtype=np.float32),
            ambient_wind_direction_rad=np.array([[0.0]], dtype=np.float32),
            turbulence_intensity=np.array([[0.08]], dtype=np.float32),
        )


class OutOfDomainPlant(ScaledPlant):
    """Plant whose counterfactual availability query is invalid."""

    def predict_steady(self, disturbance, applied_operating_point):
        output = super().predict_steady(disturbance, applied_operating_point)
        return SteadyPlantOutput(
            turbine_ids=output.turbine_ids,
            floris_turbine_power_w=output.floris_turbine_power_w,
            floris_farm_power_sum_w=output.floris_farm_power_sum_w,
            effective_wind_speed_m_s=output.effective_wind_speed_m_s,
            in_domain=np.zeros_like(output.in_domain, dtype=bool),
            ood_score=np.ones_like(output.ood_score, dtype=np.float32),
            model_kind="out_of_domain_contract_test_plant",
        )



def _assert_all_value_nodes_have_source(node):
    if isinstance(node, dict):
        if "value" in node:
            assert "source" in node
        for child in node.values():
            _assert_all_value_nodes_have_source(child)
    elif isinstance(node, list):
        for child in node:
            _assert_all_value_nodes_have_source(child)


def test_yaml_records_provenance_for_every_parameter_value():
    document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    _assert_all_value_nodes_have_source(document)
    assert document["environment"]["control_interval_s"]["source"] == "assumed"
    assert document["reference_power"]["headroom_fraction"]["source"] == "assumed"
    assert "Not calibrated" in document["mock_plant"]["warning"]


def test_environment_passes_gymnasium_contract_and_exposes_auditable_info():
    env = load_quasi_static_env(CONFIG_PATH)
    assert isinstance(env, QuasiStaticWindFarmEnv)
    check_env(env, skip_render_check=True)

    observation, reset_info = env.reset(seed=42)
    assert observation.shape == env.observation_space.shape
    assert observation.dtype == np.float32
    assert reset_info["turbine_ids"] == ("T01",)
    assert (
        reset_info["farm_available_power_semantics"]
        == "baseline_control_counterfactual_estimate"
    )
    assert reset_info["hold_action_normalized"].shape == env.action_space.shape
    observation, reward, terminated, truncated, info = env.step(
        np.zeros(env.action_space.shape, dtype=np.float32)
    )
    assert env.observation_space.contains(observation)
    assert np.isfinite(reward)
    assert not terminated
    assert not truncated
    assert set(info["reward_components"]) == {
        "tracking",
        "ramp",
        "action_rate",
        "load",
        "constraint",
        "ood",
        "energy",
    }
    assert set(info["constraint_flags"]) == {
        "normalized_action_clipped",
        "position_saturated",
        "rate_saturated",
        "held_for_multirate_update",
    }
    assert set(info["domain_flags"]) == {
        "in_domain",
        "ood_score",
        "available_power_query_in_domain",
    }


def test_fixed_seed_reproduces_observations_rewards_and_flags():
    first = load_quasi_static_env(CONFIG_PATH)
    second = load_quasi_static_env(CONFIG_PATH)
    obs_first, info_first = first.reset(seed=1234)
    obs_second, info_second = second.reset(seed=1234)
    np.testing.assert_array_equal(obs_first, obs_second)
    assert info_first["farm_available_power_w"] == info_second["farm_available_power_w"]

    action_rng = np.random.default_rng(99)
    for _ in range(50):
        action = action_rng.uniform(-1.0, 1.0, first.action_space.shape).astype(
            np.float32
        )
        transition_first = first.step(action)
        transition_second = second.step(action)
        np.testing.assert_array_equal(transition_first[0], transition_second[0])
        assert transition_first[1:4] == transition_second[1:4]
        assert transition_first[4]["reward_components"] == transition_second[4][
            "reward_components"
        ]
        assert transition_first[4]["constraint_flags"] == transition_second[4][
            "constraint_flags"
        ]


def test_random_multi_episode_rollout_has_no_nan_or_inf():
    env = load_quasi_static_env(CONFIG_PATH)
    observation, _ = env.reset(seed=42)
    action_rng = np.random.default_rng(42)
    for episode_step in range(1_000):
        assert np.all(np.isfinite(observation))
        action = action_rng.uniform(-1.0, 1.0, env.action_space.shape).astype(
            np.float32
        )
        observation, reward, terminated, truncated, info = env.step(action)
        assert np.all(np.isfinite(observation))
        assert np.isfinite(reward)
        assert np.isfinite(info["farm_power_w"])
        assert np.isfinite(info["farm_available_power_w"])
        assert np.isfinite(info["farm_power_reference_w"])
        if terminated or truncated:
            observation, _ = env.reset(seed=42 + episode_step)


def test_available_power_uses_baseline_counterfactual_not_applied_control():
    curtailed = load_quasi_static_env(CONFIG_PATH)
    permissive = load_quasi_static_env(CONFIG_PATH)
    curtailed.reset(seed=7)
    permissive.reset(seed=7)

    _, _, _, _, curtailed_info = curtailed.step(
        np.array([1.0, 1.0, -1.0], dtype=np.float32)
    )
    _, _, _, _, permissive_info = permissive.step(
        np.array([0.0, -1.0, 1.0], dtype=np.float32)
    )

    assert np.isclose(
        curtailed_info["farm_available_power_w"],
        permissive_info["farm_available_power_w"],
    )
    assert not np.isclose(
        curtailed_info["farm_power_w"], permissive_info["farm_power_w"]
    )


def test_injected_fixed_disturbance_sequence_replaces_synthetic_profile():
    provider = FixedSequenceDisturbanceProvider([7.0, 9.0])
    env = load_quasi_static_env(CONFIG_PATH, disturbance_provider=provider)
    _, reset_info = env.reset(seed=321)
    initial_available_power = reset_info["farm_available_power_w"]

    _, _, _, _, step_info = env.step(env.hold_action_normalized.copy())

    assert provider.seen_steps == [0, 1]
    assert np.isclose(step_info["reward_components"]["action_rate"], 0.0)
    assert step_info["farm_available_power_w"] != initial_available_power


def test_replacement_plant_requires_no_environment_code_change():
    default_env = load_quasi_static_env(CONFIG_PATH)
    replacement_env = load_quasi_static_env(CONFIG_PATH, plant=ScaledPlant())
    assert type(default_env) is type(replacement_env) is QuasiStaticWindFarmEnv
    assert default_env.action_space == replacement_env.action_space
    assert default_env.observation_space.shape == replacement_env.observation_space.shape

    default_obs, default_info = default_env.reset(seed=5)
    replacement_obs, replacement_info = replacement_env.reset(seed=5)
    assert default_obs.shape == replacement_obs.shape
    assert default_info["model_kind"] != replacement_info["model_kind"]
    assert default_info["farm_power_w"] != replacement_info["farm_power_w"]


def test_out_of_domain_available_power_cannot_create_reference():
    with unittest.TestCase().assertRaisesRegex(RuntimeError, "out of domain"):
        load_quasi_static_env(CONFIG_PATH, plant=OutOfDomainPlant())


def test_step_requires_reset_after_episode_horizon():
    env = load_quasi_static_env(CONFIG_PATH)
    env.reset(seed=42)
    for _ in range(env.config.episode_horizon_steps):
        _, _, _, truncated, _ = env.step(env.hold_action_normalized.copy())
    assert truncated
    with unittest.TestCase().assertRaisesRegex(RuntimeError, "reset"):
        env.step(env.hold_action_normalized.copy())


def test_loader_rejects_unimplemented_interface_modes():
    document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    document["interface"]["model_kind"]["value"] = "dynamic_transition"
    with tempfile.TemporaryDirectory() as directory:
        invalid_path = Path(directory) / "invalid.yaml"
        invalid_path.write_text(yaml.safe_dump(document), encoding="utf-8")
        with unittest.TestCase().assertRaisesRegex(ValueError, "quasi_static"):
            load_quasi_static_env(invalid_path)

def load_tests(loader, tests, pattern):
    del loader, tests, pattern
    suite = unittest.TestSuite()
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            suite.addTest(unittest.FunctionTestCase(function))
    return suite
import tempfile
