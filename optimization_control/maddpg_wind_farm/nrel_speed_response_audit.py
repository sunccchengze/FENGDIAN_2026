"""Bounded static speed interventions on frozen, deterministically saved anchors."""
import argparse
import json
import os
from pathlib import Path

from . import nrel_speed_transfer as transfer

old = transfer.old
ROOT = old.EXPS/"20261106_nrel_speed_diagnostic"
PROTOCOL = Path(__file__).with_name("NREL_SPEED_RESPONSE_PROTOCOL_20261106.md")
BASE = "9467cfc169156b58218aa37b707471019b4fb971"
MIB = 1024**2


def store():
    return old.Store(ROOT, 32*MIB)


def context():
    lock = old.read(ROOT/"lock.json")
    for path, sha in lock["hashes"].items():
        old.verify(dict(path=path, sha256=sha))
    return lock


def evaluations(source):
    entries = {(rule, name): ref for rule in ("legacy",) for name, ref in source["old_evaluations"].items()}
    for entry in old.read(transfer.ROOT/"complete.json")["results"]:
        entries["nrel", entry["controller"]] = entry["eval"]
    return entries


def load_traces(ref):
    import numpy as np
    with np.load(old.verify(ref["trace"]), allow_pickle=False) as data:
        result = data["trace"]
    assert result.shape[:2] == (6, 129) and result.shape[2] in (52, 70)
    assert np.isfinite(result).all()
    return result


def inward_speed(values):
    import numpy as np
    from .nrel_speed_adapter import LOW, HIGH
    lo, hi = np.float32(LOW), np.float32(HIGH)
    if float(lo) < LOW:
        lo = np.nextafter(lo, np.float32(np.inf))
    if float(hi) > HIGH:
        hi = np.nextafter(hi, np.float32(-np.inf))
    return np.clip(np.asarray(values, np.float64).astype(np.float32), lo, hi)


def requests(point, ueff):
    import numpy as np
    from .nrel_speed_adapter import base_reference, LOW, HIGH
    points, labels = [point.copy()], [dict(kind="actual", turbine=-1, level=0)]
    for kind, speed in (("legacy_reference", transfer.legacy_base(ueff).astype(np.float32)),
                        ("nrel_reference", inward_speed(base_reference(ueff)))):
        changed = point.copy(); changed[9:12] = speed
        points.append(changed); labels.append(dict(kind=kind, turbine=-1, level=0))
    for turbine in range(3):
        for level, speed in enumerate(inward_speed(np.linspace(LOW, HIGH, 7))):
            changed = point.copy(); changed[9+turbine] = speed
            points.append(changed); labels.append(dict(kind="grid", turbine=turbine, level=level))
    for turbine in range(3):
        for sign in (-1, 1):
            changed = point.copy(); changed[9+turbine] = inward_speed(np.clip(float(point[9+turbine])+.01*sign, LOW, HIGH))
            points.append(changed); labels.append(dict(kind="local", turbine=turbine, level=sign))
    assert len(points) == len(labels) == 30
    unique, mapping, seen = [], [], {}
    for value, label in zip(points, labels, strict=True):
        np.testing.assert_array_equal(value[:9], point[:9])
        turbine = label["turbine"]
        if turbine >= 0:
            other = [i for i in range(3) if i != turbine]
            np.testing.assert_array_equal(value[9:12][other], point[9:12][other])
        key = value.tobytes()
        if key not in seen:
            seen[key] = len(unique); unique.append(value)
        mapping.append(seen[key])
    assert mapping[0] == 0
    return np.stack(unique), np.asarray(mapping, np.int32), labels


def prepare():
    import numpy as np
    import yaml
    from .nrel_speed_adapter import LOW, HIGH
    assert old.git("rev-parse", "HEAD").decode().strip() == BASE
    source = transfer.context()
    entries = evaluations(source)
    cases = transfer.cases(source)
    meta, packets, expected, mapping, offsets = [], [], [], [], [0]
    semantic = None
    for rule in ("legacy", "nrel"):
        for controller in ("Y2_selected", "pi"):
            ref = entries[rule, controller]
            traces = load_traces(ref)
            for case_index, ((case, wind), trace) in enumerate(zip(cases, traces, strict=True)):
                np.testing.assert_array_equal(trace[:, 4:7], wind)
                for t in (32, 96):
                    row = trace[t]
                    assert row[0] == t and row[1] == case["target_w"]
                    applied = row[19:28].reshape(3, 3)
                    gamma = (row[16:19]-row[5]+np.pi)%(2*np.pi)-np.pi
                    np.testing.assert_allclose(gamma, applied[:, 0], atol=1e-7, rtol=0)
                    point = np.r_[row[4:7], applied[:, 0], applied[:, 1], applied[:, 2]].astype(np.float32)
                    query, index, labels = requests(point, row[10:13])
                    assert len(query) <= 30
                    if semantic is None: semantic = labels
                    else: assert semantic == labels
                    packets.append(query); mapping.append(index); offsets.append(offsets[-1]+len(query))
                    expected.append(np.r_[row[13:16], row[10:13]].astype(np.float32))
                    meta.append(dict(id=len(meta), rule=rule, controller=controller, case_index=case_index,
                        case_id=case["id"], family=case["family"], t=t, target_w=case["target_w"],
                        saved_farm_w=float(row[2]), source_trace=ref["trace"], source_row_sha=old.hashlib.sha256(row.tobytes()).hexdigest(),
                        request_count=30, unique_rows=len(query), duplicates=30-len(query)))
    assert len(meta) == 48 and offsets[-1] <= 1440
    cfg = dict(seed=42, base_commit=BASE, start_commit="93370066992012c61bb9244912ee0481200abf1f",
        anchors=48, times=[32,96], rules=["legacy","nrel"], controllers=["Y2_selected","pi"],
        cases=6, planned_PINN_rows=offsets[-1], row_hard_cap=2048, disk_cap_MiB=32,
        inherited_completed_rows=4030, combined_planned_rows=4030+offsets[-1], combined_hard_cap=6078,
        speed_low=LOW, speed_high=HIGH, grid_points=7, local_radius_rad_s=.01,
        replay_power_atol_w=2., replay_ueff_atol_m_s=2e-5, replay_farm_atol_w=6., direction_zero_band_w=2.,
        environment_steps=0, training_steps=0, optimizer_updates=0, new_winds=0,
        reference_ueff="same_response_anchor_output_once_no_fixed_point_iteration",
        intervention="speed_only_fixed_ambient_gamma_pitch_positions",
        static_query_not_actuator_feasibility=True, plot_anchor=0,
        mse_units="kW_squared", variance_ddof=0, threshold_error_sign=0.)
    ROOT.mkdir(exist_ok=False)
    s = store()
    cfgref = s.write("config.yaml", yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True).encode())
    bank = s.arrays("requests.npz", inputs=np.concatenate(packets), offsets=np.array(offsets),
                    mapping=np.stack(mapping), expected=np.stack(expected))
    anchors = s.json("anchors.json", meta)
    requests_ref = s.json("semantic_requests.json", semantic)
    hashes = dict(source["hashes"])
    for ref in entries.values():
        for value in ref.values(): hashes[value["path"]] = old.sha(old.verify(value))
    paths = [Path(__file__), PROTOCOL, Path(__file__).with_name("nrel_speed_response_report.py"),
        Path(__file__).with_name("wind_pinn_demo.py"), transfer.ROOT/"complete.json",
        transfer.ROOT/"output_manifest.csv", transfer.ROOT/"final_qa.json", transfer.ROOT/"metrics.csv"]
    for path in paths: hashes[str(path)] = old.sha(path)
    for ref in (cfgref, bank, anchors, requests_ref): hashes[ref["path"]] = ref["sha256"]
    s.json("lock.json", dict(hashes=hashes, source=source, config=cfg, bank=bank,
        anchors=anchors, semantic=requests_ref, evaluations=[dict(rule=k[0], controller=k[1], ref=v) for k,v in entries.items()]))
    print("Prepared",len(meta),"fixed anchors; planned PINN rows",offsets[-1],"; no queries.",flush=True)


class Meter:
    def __init__(self, predictor, budget):
        self.predictor, self.budget, self.inputs = predictor, budget, []

    def __call__(self, x):
        self.budget.take(len(x), "PINN"); self.budget.save()
        self.inputs.append(x.copy())
        return self.predictor(x)


def predict(plant, x):
    import numpy as np
    from ..environments.plant_model import DisturbanceBatch, AppliedOperatingPoint
    d = DisturbanceBatch(*(x[:, i:i+1] for i in range(3)))
    op = AppliedOperatingPoint(plant.turbine_ids, x[:,3:6],x[:,6:9],x[:,9:12])
    out = plant.predict_steady(d, op)
    assert np.all(out.in_domain)
    return np.concatenate((out.floris_turbine_power_w, out.effective_wind_speed_m_s),axis=1)


def query():
    import numpy as np
    from .causal_speed_search import Budget
    from .wind_pinn_demo import synthetic_labels
    from ..environments.maddpg_farm_env import MADDPGFarmEnv
    lock,s = context(),store()
    def forbidden(*args, **kwargs):
        raise RuntimeError("diagnostic forbids environment reset and step")
    MADDPGFarmEnv.reset = MADDPGFarmEnv.step = forbidden
    world = old.World(dict(base_config=lock["source"]["base_config"]))
    raw = world.predictor
    positions = raw.positions.copy()
    assert raw.model_sha256 == lock["source"]["base_config"]["plant"]["backend"]["model_sha256"]
    assert np.isclose(raw.spacing_m,lock["source"]["base_config"]["plant"]["layout"]["spacing_m"])
    s.arrays("positions.npz",positions=positions)
    budget = Budget(ROOT/"model_budget.json", 2048)
    meter = Meter(raw,budget); world.plant.predictor = meter
    meta = old.read(old.verify(lock["anchors"]))
    with np.load(old.verify(lock["bank"]),allow_pickle=False) as data:
        points,offsets,mapping,expected = [data[k] for k in ("inputs","offsets","mapping","expected")]
    outcomes = []
    for anchor in meta:
        i = anchor["id"]; x = points[offsets[i]:offsets[i+1]]
        budget.start(f"anchor{i:02d}",len(x))
        try:
            before_inputs = len(meter.inputs)
            y0 = predict(world.plant,x[:1])
            dp = float(np.max(np.abs(y0[0,:3].astype(float)-expected[i,:3])))
            du = float(np.max(np.abs(y0[0,3:].astype(float)-expected[i,3:])))
            df = abs(float(y0[0,:3].sum())-anchor["saved_farm_w"])
            replay = dict(power_max_abs_w=dp,ueff_max_abs_m_s=du,farm_abs_w=df)
            if dp>2 or du>2e-5 or df>6:
                s.json(f"anchor{i:02d}_replay_failure.json",dict(anchor=anchor,replay=replay,inputs=x[0].tolist(),observed=y0[0].tolist(),expected=expected[i].tolist()))
                raise ValueError("actual anchor replay mismatch; no counterfactual interpretation")
            rest = predict(world.plant,x[1:]) if len(x)>1 else np.empty((0,6),np.float32)
            outputs = np.concatenate((y0,rest))
            encoded = np.concatenate(meter.inputs[before_inputs:])
            np.testing.assert_array_equal(encoded,x)
            labels = synthetic_labels(encoded,positions)
            ref=s.arrays(f"anchors/a{i:02d}.npz",inputs=encoded,outputs=outputs,labels=labels,mapping=mapping[i])
            account=budget.finish(); assert account["actual"]==len(x)
            outcomes.append(dict(anchor=i,artifact=ref,replay=replay,budget=account,label_calls=1,label_rows=len(x)))
        except BaseException:
            budget.save()
            raise
        if (i+1)%12==0: print("Completed static anchors",i+1,"/ 48",flush=True)
    context()
    used=sum(x["budget"]["actual"] for x in outcomes)
    assert used==lock["config"]["planned_PINN_rows"]<=1440
    s.json("complete.json",dict(outcomes=outcomes,PINN_rows=used,model_api_calls=sum(x["budget"]["api_calls"] for x in outcomes),
        label_calls=48,label_input_rows=used,labels_not_physical_truth=True,replay_passed=48,
        environment_steps=0,training_steps=0,optimizer_updates=0,new_winds=0,combined_rows=4030+used,
        row_hard_cap=2048,combined_hard_cap=6078,failed_scopes=0,retries=0))
    print("Static audit complete; PINN rows",used,"; inherited + diagnostic",4030+used,flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=("prepare","query"));args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(old.ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS","1");os.environ.setdefault("TF_NUM_INTEROP_THREADS","1")
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(42)
    dict(prepare=prepare,query=query)[args.phase]()
