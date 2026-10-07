"""Independent spectral, replay, causality and integration regressions."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import gymnasium as gym
import numpy as np
from scipy.signal import welch

from optimization_control.environments.wind_generator import WindConfig, WindTrace, generate_wind, kaimal_psd, load_config
from optimization_control.environments.stochastic_turbine_env import StochasticTurbineEnv

CONFIG = Path(__file__).resolve().parents[1] / "ppo_single_turbine/configs/stochastic_wind_v1.yaml"


class WindGeneratorTests(unittest.TestCase):
    def test_seed_episode_worker_and_split(self):
        c = WindConfig()
        a = generate_wind(c)
        np.testing.assert_array_equal(a.speed_m_s, generate_wind(c).speed_m_s)
        for kwargs in ({"episode": 1}, {"worker": 1}, {"split": "test"}, {"split": "validation"}):
            self.assertFalse(np.array_equal(a.speed_m_s, generate_wind(c, **kwargs).speed_m_s))

    def test_config_rejects_invalid_values(self):
        for kwargs in ({"dt_s": 0}, {"length_scale_m": np.nan}, {"ti_values": [-0.1]},
                       {"duration_s": 601.5}, {"padding_factor": 1}, {"scenario": "typo"},
                       {"gust_amplitude_m_s": float("inf")}, {"max_attempts": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                WindConfig(**kwargs)

    def test_spectrum_and_variance_match_ensemble_not_forced_record(self):
        c = WindConfig(mean_min_m_s=8, mean_max_m_s=8, ti_values=(0.1,), scenario="stationary")
        ratios, spectra, record_ti, lag1 = [], [], [], []
        for episode in range(64):
            trace = generate_wind(c, split="validation", episode=episode)
            x = trace.turbulence_m_s
            ratios.append(np.mean(x**2) / trace.metadata["expected_band_variance_m2_s2"])
            f, p = welch(x, fs=1, nperseg=256)
            target = kaimal_psd(f, 8, 0.8, 100)
            mask = (f >= 0.03) & (f < 0.35)
            spectra.append(p[mask] / target[mask])
            record_ti.append(np.std(x) / 8)
            lag1.append(np.corrcoef(x[:-1], x[1:])[0, 1])
        self.assertAlmostEqual(float(np.mean(ratios)), 1, delta=0.18)
        self.assertAlmostEqual(float(np.median(np.mean(spectra, axis=0))), 1, delta=0.20)
        self.assertGreater(np.mean(lag1), 0.5)
        self.assertGreater(np.std(record_ti), 0.001)

    def test_events_and_decomposition(self):
        c = WindConfig(ti_values=(0.0,))
        for scenario in ("stationary", "ramp", "gust"):
            trace = generate_wind(replace(c, scenario=scenario))
            np.testing.assert_array_equal(trace.turbulence_m_s, np.zeros(c.steps + 1))
            np.testing.assert_allclose(trace.speed_m_s, trace.background_m_s + trace.event_m_s)
            if scenario == "ramp":
                self.assertAlmostEqual(abs(trace.background_m_s[-1] - trace.background_m_s[0]), c.ramp_amplitude_m_s)
            if scenario == "gust":
                self.assertAlmostEqual(trace.event_m_s[0], 0)
                self.assertAlmostEqual(trace.event_m_s[-1], 0)
                self.assertGreater(trace.event_m_s.max(), 1.4)

    def test_envelope_exhaustion_is_explicit_not_clipped(self):
        c = WindConfig(mean_min_m_s=8, mean_max_m_s=8, ti_values=(0,),
                       scenario="gust", gust_amplitude_m_s=100, max_attempts=2)
        with self.assertRaisesRegex(ValueError, "rejection exhausted"):
            generate_wind(c)

    def test_csv_json_round_trip_and_tamper_detection(self):
        trace = generate_wind(WindConfig())
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "trace.csv"
            trace.save(path)
            loaded = WindTrace.load(path)
            np.testing.assert_array_equal(trace.speed_m_s, loaded.speed_m_s)
            with self.assertRaises(FileExistsError):
                trace.save(path)
            path.write_text(path.read_text() + "\n")
            with self.assertRaisesRegex(ValueError, "checksum"):
                WindTrace.load(path)


class StochasticEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG)

    def test_reset_repeat_and_episode_diversity(self):
        env = StochasticTurbineEnv(self.config)
        a, _ = env.reset(seed=42)
        trace = env.trace.speed_m_s.copy()
        b, _ = env.reset(seed=42)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(trace, env.trace.speed_m_s)
        env.reset()
        self.assertFalse(np.array_equal(trace, env.trace.speed_m_s))
        self.assertAlmostEqual(env.U, env.trace.speed_m_s[0])

    def test_causal_target_and_action_independent_reference(self):
        trace = generate_wind(WindConfig(**self.config["wind"]), split="test")
        a, b = [StochasticTurbineEnv(self.config, trace=trace) for _ in range(2)]
        a.reset()
        b.reset()
        for _ in range(80):
            target = a.P_target
            _, reward, _, _, ia = a.step([0, 0])
            _, _, _, _, ib = b.step([0.1, 0.03])
            self.assertEqual(ia["reference_applied_w"], target)
            self.assertEqual(ia["reference_next_w"], ib["reference_next_w"])
            self.assertAlmostEqual(reward, -(ia["power_w"] - target)**2 / 1e12)
            self.assertLessEqual(a.P_target, ia["available_power_w"] * 0.8 + 1e-6)

    def test_no_future_wind_leak_into_current_observation_or_reference(self):
        a = generate_wind(WindConfig(**self.config["wind"]))
        b = deepcopy(a)
        b.speed_m_s[50:] += 0.2
        b.event_m_s[50:] += 0.2
        ea, eb = [StochasticTurbineEnv(self.config, trace=t) for t in (a, b)]
        np.testing.assert_array_equal(ea.reset()[0], eb.reset()[0])
        for _ in range(49):
            np.testing.assert_array_equal(ea.step([0, 0])[0], eb.step([0, 0])[0])

    def test_rotor_exact_lag_and_observation_state(self):
        env = StochasticTurbineEnv(self.config)
        env.reset()
        initial = env.omega
        env.step([0, -0.1])
        expected = initial - 0.1 * (1 - np.exp(-1 / 5))
        self.assertAlmostEqual(env.omega, expected, places=8)
        self.assertAlmostEqual(env._obs()[5] * env.obs_scale[5], env.omega_set, places=6)

    def test_long_rollout_spaces_lifecycle_and_invalid_actions(self):
        env = StochasticTurbineEnv(self.config)
        rng = np.random.default_rng(42)
        for _ in range(3):
            obs, _ = env.reset()
            self.assertTrue(env.observation_space.contains(obs))
            for step in range(env.ep_len):
                obs, reward, done, truncated, info = env.step(rng.uniform(-0.8, 0.8, 2))
                self.assertTrue(env.observation_space.contains(obs), obs)
                self.assertTrue(np.isfinite(reward))
                self.assertEqual(done, step == env.ep_len - 1)
                self.assertFalse(truncated)
            with self.assertRaises(RuntimeError):
                env.step([0, 0])
        env.reset()
        for action in ([np.nan, 0], [np.inf, 0], [0]):
            with self.assertRaises(ValueError):
                env.step(action)

    def test_availability_respects_speed_limit(self):
        env = StochasticTurbineEnv(self.config)
        power = env.available_power(12)
        brute_omega = np.linspace(env.omega_min, env.omega_max, 401)[:, None]
        brute_beta = np.linspace(0, 25, 301)[None, :]
        cp = env._cp_array(brute_omega * env.R / 12, brute_beta)
        reference = min(5e6, 0.5 * env.rho * env.A * 12**3 * cp.max())
        self.assertAlmostEqual(power, reference, delta=reference * 0.002)

    def test_vector_autoreset_collects_completed_episodes(self):
        from optimization_control.ppo_single_turbine.train import make_env, extract_episode_returns
        config = deepcopy(self.config)
        config["wind"].update(duration_s=64, gust_duration_s=8)
        envs = gym.vector.SyncVectorEnv([make_env(42, i, "test", 0.99, config) for i in range(2)],
                                       autoreset_mode=gym.vector.AutoresetMode.SAME_STEP)
        try:
            obs, _ = envs.reset(seed=[42, 42])
            self.assertEqual(obs.shape, (2, 8))
            completed = []
            for _ in range(128):
                _, _, _, _, info = envs.step(np.zeros((2, 2)))
                completed.extend(extract_episode_returns(info))
            self.assertEqual(len(completed), 4)
            self.assertTrue(np.all(np.isfinite(completed)))
        finally:
            envs.close()


if __name__ == "__main__":
    unittest.main()
