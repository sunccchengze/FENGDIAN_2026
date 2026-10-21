"""Verify uninterrupted/resumed training and repeated disk-loaded evaluation."""

import argparse
from copy import deepcopy
import json
import numpy as np
import torch

from .algorithm import MADDPG
from .workflow import DEFAULT_CONFIG, load_config, fresh_output, train, evaluate, write_csv


def verify(output, config_path=DEFAULT_CONFIG):
    cfg = load_config(config_path)
    stochastic = bool(cfg["environment"].get("inflow"))
    cfg["environment"]["horizon"] = 128 if stochastic else 32
    if stochastic:
        cfg["environment"]["inflow"]["speed"]["gust_duration_s"] = 20.0
    cfg["algorithm"].update(hidden=16, batch_size=16, capacity=512)
    cfg["training"].update(total_steps=512 if stochastic else 256, warmup_steps=32)
    output = fresh_output(output, cfg)
    full = train(cfg, output / "continuous")
    half = deepcopy(cfg)
    half["training"]["total_steps"] //= 2
    partial = train(half, output / "partial")
    resumed = train(cfg, output / "resumed", partial)
    left, lm = MADDPG.load(full)
    right, rm = MADDPG.load(resumed)
    for name in ("actors", "critics", "target_actors", "target_critics"):
        for a,b in zip(getattr(left,name).parameters(),getattr(right,name).parameters()):
            torch.testing.assert_close(a,b,rtol=0,atol=0)
    for key in left.replay.data:
        np.testing.assert_array_equal(left.replay.data[key], right.replay.data[key])
    assert lm == rm
    assert left.updates == right.updates
    assert left.rng.bit_generator.state == right.rng.bit_generator.state
    assert left.replay.rng.bit_generator.state == right.replay.rng.bit_generator.state
    # Same next update also verifies optimizer moments and sampled transitions.
    assert left.update() == right.update()
    evaluate(full, output / "replay_a")
    evaluate(full, output / "replay_b")
    for filename in ("metrics.csv", "trajectories.csv"):
        assert (output / "replay_a" / filename).read_bytes() == (output / "replay_b" / filename).read_bytes()
    write_csv(output / "metrics.csv", [
        {"check":"continuous_vs_resumed_all_networks_replay_rng_next_update", "passed":True},
        {"check":"disk_loaded_evaluation_csv_byte_identical", "passed":True}])
    result={"steps":lm["steps"],"updates_before_extra_check":left.updates-1,"resume_exact":True,"replay_exact":True}
    (output / "summary.txt").write_text(
        "Command: python -m optimization_control.maddpg_wind_farm.verify_workflow --output <new-directory>\n"
        + json.dumps(result,indent=2) + "\nAll results use coupled integration mock; not physical evidence.\n",encoding="utf-8")
    print(json.dumps(result),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args=parser.parse_args()
    verify(args.output, args.config)
