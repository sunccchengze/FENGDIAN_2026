"""Permission order, inheritance, held-out head transfer and exact checkpoint resume."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch
import yaml

from optimization_control.maddpg_wind_farm import progressive_random_control as flow
from optimization_control.maddpg_wind_farm.algorithm import MADDPG
from optimization_control.maddpg_wind_farm.workflow import build_env, make_agent, load_config, DEFAULT_CONFIG


class ProgressiveControlTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.cfg = load_config(DEFAULT_CONFIG)
        self.cfg["environment"].update(horizon=128, control_mask=[0, 1, 0], wind_base_m_s=9.,
            wind_amplitude_m_s=.25, wind_noise_std_m_s=.05,
            action_low=[-.25, 0., .6], action_high=[.25, .22, 1.267],
            reference_schedule=dict(yaw_offset_rad=0., speed_per_wind_rad_m=1.267 / 11.4))
        self.env = build_env(self.cfg)
        self.agent = make_agent(self.cfg, self.env)
        obs, _ = self.env.reset()
        for step in range(256):
            if self.env._done:
                obs, _ = self.env.reset(seed=42 + step)
            nxt, reward, done, _, info = self.env.step(self.agent.act(obs, .03))
            self.agent.replay.add(obs, info["executed_action"], reward, nxt, done)
            obs = nxt
        self.obs = obs
        self.agent.update()

    def test_bootstrap_changes_no_state_or_actions(self):
        before = self.agent.act(self.obs)
        weights = {k: v.clone() for k, v in self.agent.actors.state_dict().items()}
        self.assertEqual(flow.initialize_heads(self.agent, [0, 1, 0]), [])
        np.testing.assert_array_equal(before, self.agent.act(self.obs))
        self.assertTrue(all(torch.equal(v, self.agent.actors.state_dict()[k]) for k, v in weights.items()))

    def test_cannot_skip_speed_remove_pitch_or_add_two_channels(self):
        for mask in ([1, 1, 1], [1, 1, 0], [0, 0, 1], [0, 0, 0]):
            with self.assertRaises(ValueError):
                flow.initialize_heads(self.agent, mask)

    def test_speed_transfer_preserves_pitch_critics_replay_and_optimizer(self):
        before_pitch = self.agent.act(self.obs)[:, 1].copy()
        critics = {k: v.clone() for k, v in self.agent.critics.state_dict().items()}
        replay = self.agent.replay.state_dict()
        optimizers = deepcopy([o.state_dict() for o in self.agent.actor_optimizers])
        reports = flow.initialize_heads(self.agent, [0, 1, 1])
        self.assertEqual(len(reports), 6)
        self.assertLessEqual(max(r["held_out_max_action_error"] for r in reports), .05)
        self.assertTrue(all(r["held_out_rows"] > 0 and r["hidden_and_existing_rows_unchanged"] for r in reports))
        np.testing.assert_array_equal(before_pitch, self.agent.act(self.obs)[:, 1])
        self.assertIsNone(self.agent.config.speed_reference_schedule)
        self.assertTrue(all(torch.equal(v, self.agent.critics.state_dict()[k]) for k, v in critics.items()))
        self.assertEqual(self.agent.replay.rng.bit_generator.state, replay["rng"])
        for k, v in replay["data"].items():
            np.testing.assert_array_equal(v, self.agent.replay.state_dict()["data"][k])
        for old, optimizer in zip(optimizers, self.agent.actor_optimizers):
            current = optimizer.state_dict()
            self.assertEqual(old["param_groups"], current["param_groups"])
            for key, value in old["state"].items():
                self.assertTrue(all(torch.equal(tensor, current["state"][key][name]) for name, tensor in value.items()))

    def test_yaw_handover_matches_background_and_preserves_other_actions(self):
        flow.initialize_heads(self.agent, [0, 1, 1])
        before = self.agent.act(self.obs)
        reports = flow.initialize_heads(self.agent, [1, 1, 1])
        np.testing.assert_array_equal(before, self.agent.act(self.obs))
        self.assertTrue(all(r["new_channel"] == 0 and r["held_out_max_action_error"] == 0 for r in reports))

    def test_transferred_checkpoint_has_exact_next_actions_and_update(self):
        flow.initialize_heads(self.agent, [0, 1, 1])
        stream = io.BytesIO(); self.agent.save(stream, dict(inherited=True)); stream.seek(0)
        other, meta = MADDPG.load(stream)
        self.assertTrue(meta["inherited"])
        self.assertEqual(other.config.action_mask, (0, 1, 1))
        np.testing.assert_array_equal(self.agent.act(self.obs, .03), other.act(self.obs, .03))
        self.assertEqual(self.agent.update(), other.update())

    def test_manual_worker_checks_every_parent_and_locks_after_selection(self):
        # Retain these tiny fixtures under ignored tmp/; no workspace cleanup.
        Path("tmp").mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="progressive_gate_", dir="tmp"))
        p = flow.read_protocol(flow.DEFAULT)
        (root / "config.yaml").write_text(yaml.safe_dump(dict(protocol=p, source_hashes={})), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "all parent streams"):
            flow.parent_for_worker(root, "pitch_speed", 0)
        for run in range(3):
            job = root / f"pitch_run_{run}"; job.mkdir()
            cp = job / "dummy.pth"; cp.write_bytes(b"unit test identity")
            r = dict(stage="pitch", run_id=run, passed=True, steps=16384, initial_rmse_w=420000.,
                     best=dict(step=8192, score_w=350000., validation=[dict(rmse_w=450000.)], checkpoint=str(cp)),
                     final_over_best=1.1, hashes={str(cp): flow.digest(cp)}, lineage=dict(cumulative_parent_steps=16384))
            (job / "result.json").write_text(json.dumps(r), encoding="utf-8")
        self.assertEqual(flow.parent_for_worker(root, "pitch_speed", 0)["run_id"], 0)
        path = root / "pitch_run_2/result.json"
        r = json.loads(path.read_text(encoding="utf-8")); r["best"]["score_w"] = 410000.
        path.write_text(json.dumps(r), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "all parent streams must pass"):
            flow.parent_for_worker(root, "pitch_speed", 0)
        (root / "selection.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "selection frozen"):
            flow.parent_for_worker(root, "pitch", 0)

    def test_fresh_protocol_retains_original_wind_scope_and_gates(self):
        p = flow.read_protocol(flow.DEFAULT)
        old = yaml.safe_load(Path("optimization_control/maddpg_wind_farm/configs/random_wind_training.yaml").read_text(encoding="utf-8"))
        self.assertEqual(p["inflow"], old["inflow"])
        self.assertEqual(p["gate"], old["gate"])
        self.assertFalse(set(p["test_targets_w"]) & set(old["test_targets_w"]))
        self.assertGreater(p["training_episode_offset"], 330064)


if __name__ == "__main__":
    unittest.main()
