"""End-to-end continuation, immutable bank and checkpoint selection verification."""

import argparse
import json
import numpy as np
import torch

from .algorithm import MADDPG
from .workflow import fresh_output, write_csv
from .stable_workflow import load_protocol, DEFAULT, train_run
from .benchmark import freeze_bank, load_cases, evaluate_cases, digest


def verify(output):
    p,cfg=load_protocol(DEFAULT)
    p.update(horizon=32,screen_steps=256,bridge_steps=256,confirm_steps=256,eval_every=64,warmup_steps=32,cases_per_family=1)
    cfg["environment"]["horizon"]=32
    cfg["algorithm"].update(hidden=16,batch_size=16,capacity=512)
    root=fresh_output(output,{"seed":42,"protocol":p,"base_config":cfg})
    bank=root/"bank"; before=freeze_bank(cfg,p,bank)
    candidate=p["candidates"][-1]
    kwargs=dict(steps=256,run_id=1,phase="mixed")
    full=train_run(cfg,p,candidate,[1,1,1],bank,root/"full",**kwargs)
    partial=train_run(cfg,p,candidate,[1,1,1],bank,root/"partial",stop_at=128,**kwargs)
    resumed=train_run(cfg,p,candidate,[1,1,1],bank,root/"resumed",resume=partial["final"],**kwargs)
    left,lm=MADDPG.load(full["final"]); right,rm=MADDPG.load(resumed["final"])
    for name in ("actors","critics","target_actors","target_critics"):
        for a,b in zip(getattr(left,name).parameters(),getattr(right,name).parameters()):
            torch.testing.assert_close(a,b,rtol=0,atol=0)
    for key in left.replay.data: np.testing.assert_array_equal(left.replay.data[key],right.replay.data[key])
    assert lm["history"]==rm["history"]
    assert lm["noise"]["rng"]==rm["noise"]["rng"]
    np.testing.assert_array_equal(lm["noise"]["state"],rm["noise"]["state"])
    assert left.update()==right.update()
    assert digest(bank/"manifest.json")==before
    cases=load_cases(bank,"validation")
    assert evaluate_cases(lm["config"],cases,agent=left)==evaluate_cases(rm["config"],cases,agent=right)
    # Hash tampering must be rejected; leave the isolated test artifact for audit.
    manifest=json.loads((bank/"manifest.json").read_text(encoding="utf-8"))
    victim=bank/manifest["cases"][0]["path"]
    with victim.open("ab") as f: f.write(b"\n")
    try: load_cases(bank,"validation")
    except ValueError: pass
    else: raise AssertionError("tampered bank accepted")
    checks=[{"check":name,"passed":True} for name in ("network_replay_noise_resume_exact","next_update_exact",
             "validation_history_exact","disk_loaded_evaluation_exact","frozen_trace_tampering_rejected")]
    write_csv(root/"metrics.csv",checks)
    (root/"summary.txt").write_text(json.dumps(checks,indent=2)+"\nBank trace intentionally altered AFTER verification to test rejection; not a production bank.\n",encoding="utf-8")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--output",required=True)
    verify(parser.parse_args().output)
