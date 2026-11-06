"""Formal runner for the frozen forecast-assisted speed comparison."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time

REPO = Path(__file__).resolve().parents[2]
ORIGIN = Path(".")
PITCH = Path(".")
EXPS = REPO / "optimization_control/experiments"
ROOT = EXPS / "20261104_forecast_speed_formal"
ENGINEERING = EXPS / "20261104_forecast_speed_engineering"
SOURCE = EXPS / "20261029_history_independent_test"
PROTOCOL = Path(__file__).with_name("FORECAST_SPEED_FORMAL_PROTOCOL.md")
BASE = "8b941d2a9761131e48058ce7b1b4cfdddd4d66b3"
ARMS = ("A", "B", "C")
POINTS = (0, 2048, 4096, 6144, 8192)
RUNS = (0, 1, 2)
MIB = 1024**2
PURPOSE = "formal_forecast_speed_v1"
TRACE = ("step", "target_w", "farm_w", "error_w", "U", "direction", "TI", "reward",
         "action_mse", "saturation", "u_effective_0", "u_effective_1", "u_effective_2",
         "power_0", "power_1", "power_2", "heading_0", "heading_1", "heading_2",
         *[f"{key}_{i}_{j}" for key in ("applied", "command", "parent") for i in range(3) for j in range(3)],
         "z_0", "z_1", "z_2")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def job_name(arm, run):
    return f"{arm}{run}"


def job_cap(arm):
    return (116 if arm == "A" else 16)*MIB


class Store:
    """One writer owns its fixed storage partition and creates files exclusively."""
    def __init__(self, folder, cap, *, shared=False):
        self.folder, self.cap, self.shared = Path(folder), cap, shared

    def used(self):
        return sum(path.stat().st_size for path in self.folder.rglob("*") if path.is_file()
                   and not (self.shared and path.relative_to(self.folder).parts[0] == "jobs"))

    def write(self, name, data, limit=None):
        path = (self.folder/name).resolve()
        if not path.is_relative_to(self.folder.resolve()):
            raise ValueError("artifact escaped its partition")
        if (limit is not None and len(data) > limit) or self.used()+len(data) > self.cap:
            raise RuntimeError(f"storage partition exhausted before {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return dict(path=str(path), sha256=sha(path), bytes=len(data))

    def json(self, name, value):
        return self.write(name, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode())

    def arrays(self, name, **values):
        import numpy as np
        with io.BytesIO() as buf:
            np.savez_compressed(buf, **values)
            return self.write(name, buf.getbuffer())

    def torch(self, name, value, limit):
        import torch
        with io.BytesIO() as buf:
            torch.save(value, buf)
            return self.write(name, buf.getbuffer(), limit)


class QueryScope:
    def __init__(self, store, tag, rows, **meta):
        self.store, self.tag, self.rows, self.actual = store, tag, rows, 0
        self.reservation = store.json(f"{tag}/reserved.json", dict(rows=rows, pid=os.getpid(), **meta))

    def take(self, rows, _kind):
        if self.actual+rows > self.rows:
            raise RuntimeError("query scope exhausted")
        self.actual += rows

    def finish(self, **data):
        if self.actual != self.rows:
            raise ValueError("scope count differs from fixed plan")
        return self.store.json(f"{self.tag}/complete.json",
            dict(rows=self.actual, reservation=self.reservation, pid=os.getpid(), **data))


def verify(ref):
    if sha(ref["path"]) != ref["sha256"]:
        raise ValueError("artifact identity mismatch: " + ref["path"])
    return Path(ref["path"])


def git(*args):
    return subprocess.check_output(["git", "-c", f"safe.directory={REPO.as_posix()}", *args], cwd=REPO)


def namespace_scan():
    ids = {67000000+1000*run+e for run in RUNS for e in range(64)}
    ids.update(range(68000000, 68000006))
    ids.update(range(69000000, 69000018))
    scanned, matches = 0, []
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("episode", "source_episode") and type(item) is int and item in ids:
                    yield item
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)
    for tree in (REPO, ORIGIN, PITCH):
        files = subprocess.check_output(["rg", "--files", "--hidden", "--no-ignore", "-g", "*.json",
                                        str(tree/"optimization_control")], encoding="utf-8")
        for line in files.splitlines():
            path = Path(line)
            if "20261029_history_independent_test" in path.parts or path.is_relative_to(ROOT):
                continue
            scanned += 1
            raw = path.read_bytes()
            if re.search(rb"(?:6700[012]\d{3}|6800000[0-5]|690000[01]\d)", raw):
                matches.extend(dict(episode=n, path=str(path)) for n in walk(json.loads(raw.decode("utf-8-sig"))))
    return dict(scanned_json=scanned, collisions=matches, reserved_count=len(ids),
                excluded_sealed_test="20261029_history_independent_test")


def context():
    lock = read(ROOT/"lock.json")
    for path, digest in lock["hashes"].items():
        verify(dict(path=path, sha256=digest))
    for ref in lock["banks"].values():
        verify(ref)
    return lock


def formal_class():
    from .forecast_speed_macro import MacroSpeed
    class FormalMacro(MacroSpeed):
        PURPOSE = "formal_forecast_speed_v1"
    return FormalMacro


def prepare():
    import numpy as np
    import torch
    import yaml
    from .speed_nstep_training import design
    from .algorithm import MADDPG
    from ..environments.farm_inflow import generate_inflow
    if git("rev-parse", "HEAD").decode().strip() != BASE:
        raise ValueError("preparation requires the reviewed engineering base")
    old = yaml.safe_load((SOURCE/"config.yaml").read_text(encoding="utf-8"))
    eng = read(ENGINEERING/"complete.json")
    assert eng["passed"] and eng["totals"] == dict(model=1728, update=6)
    e_lock = read(ENGINEERING/"attempt_000/lock.json")
    macro_file = Path(__file__).with_name("forecast_speed_macro.py")
    original = git("show", f"{BASE}:{macro_file.relative_to(REPO).as_posix()}")
    assert hashlib.sha256(original).hexdigest() == e_lock["hashes"][str(macro_file)]
    for path, digest in e_lock["hashes"].items():
        if Path(path).name not in ("forecast_speed_macro.py", "PROJECT_STATUS.md", "TASKFLOW.md", "README.md"):
            verify(dict(path=path, sha256=digest))
    namespace = namespace_scan()
    ROOT.mkdir(exist_ok=False)
    store = Store(ROOT, 68*MIB, shared=True)
    store.json("namespace_check.json", namespace)
    if namespace["collisions"]:
        raise ValueError("occupied episode identities")
    cfg = deepcopy(old["base_config"])
    ep_design = dict(design_entropy=[42, 20261030, 8601], training_targets_w=[2.6e6, 3.2e6, 3.8e6],
                     training_initial_pitch_rad=[.025, .055])
    banks = {}
    identities = set()
    def wind(family, split, number):
        inflow = deepcopy(cfg["environment"]["inflow"])
        inflow["speed"]["scenario"] = family
        return generate_inflow(inflow, dt_s=1, horizon=128, seed=42, split=split, episode=number).values
    def case(name, family, target, pitch, number, split, values):
        digest = hashlib.sha256(values.tobytes()).hexdigest()
        if digest in identities:
            raise ValueError("duplicate new wind")
        identities.add(digest)
        return dict(id=name, family=family, target_w=target, pitch_rad=pitch, episode=number, split=split, wind_sha=digest)
    for run in RUNS:
        cases, values = [], []
        for i in range(64):
            family, target, pitch = design(ep_design, run, i)
            number = 67000000+1000*run+i
            w = wind(family, "train", number)
            cases.append(case(f"train_{run}_{i:02d}", family, target, pitch, number, "train", w))
            values.append(w)
        banks[f"train{run}"] = store.arrays(f"bank/train{run}.npz", wind=np.stack(values),
                                           meta=np.array(json.dumps(cases)))
    cases, values = [], []
    for family in ("stationary", "ramp", "gust"):
        for target in (2.85e6, 3.45e6):
            number = 68000000+len(cases)
            w = wind(family, "validation", number)
            cases.append(case(f"val_{family}_{int(target)}", family, target, .04, number, "validation", w))
            values.append(w)
    banks["validation"] = store.arrays("bank/validation.npz", wind=np.stack(values), meta=np.array(json.dumps(cases)))
    w = np.tile(np.array([7.6, 0., .08], np.float32), (129, 1))
    stress = case("known_low_wind_4400000", "low_wind_stress", 4.4e6, .04, None, "stress", w)
    banks["stress"] = store.arrays("bank/stress.npz", wind=w[None], meta=np.array(json.dumps([stress])))
    sources = e_lock["parents"]
    forecast = e_lock["forecast"]
    initial = []
    for run, ref in enumerate(sources):
        parent, _ = MADDPG.load(verify(ref))
        c = parent.config
        assert (c.actor_lr,c.critic_lr,c.gamma,c.tau,c.batch_size,c.capacity,tuple(c.action_mask)) == (
            1e-4,.001,.99,.01,64,32768,(0,1,0))
        with io.BytesIO() as probe:
            parent.save(probe, dict(purpose=PURPOSE, run=run, step=0))
            measured = len(probe.getbuffer())
        assert measured < 28*MIB
        initial.append(dict(updates=parent.updates, replay=parent.replay.size, position=parent.replay.position,
                            preflight_serialized_bytes=measured))
        b, d = [formal_class()(ref, forecast, run, arm) for arm in ("B", "C")]
        for group in ("heads", "critics", "target_heads", "target_critics"):
            for x, y in zip(getattr(b, group).parameters(), getattr(d, group).parameters()):
                torch.testing.assert_close(x, y, rtol=0, atol=0)
        assert b.replay.size == d.replay.size == 0 and all(not x.state for x in (
            *b.head_adam,*d.head_adam,*b.critic_adam,*d.critic_adam))
        assert b.noise.bit_generator.state == d.noise.bit_generator.state
        assert b.replay.rng.bit_generator.state == d.replay.rng.bit_generator.state
    # Check purpose rejection using the engineering receipt, before any formal sampling.
    e_checkpoint = read(ENGINEERING/"attempt_000/B_boundary.json")
    try:
        formal_class().load(e_checkpoint["path"], e_checkpoint["identity"], e_checkpoint["sha256"])
    except ValueError as exc:
        assert "private macro checkpoint identity" in str(exc)
    else:
        raise AssertionError("engineering state accepted by formal loader")
    assert 9*(4*2064+5*774)+3870+9288+2967 == 125259
    assert 125259+4096 == 129355 < 130000
    assert 3*job_cap("A")+6*job_cap("B")+68*MIB == 512*MIB
    cfg_ref = store.write("config.yaml", yaml.safe_dump(dict(seed=42, base_commit=BASE, purpose=PURPOSE,
        arms=list(ARMS), runs=list(RUNS), points=list(POINTS), total_physical_steps=73728,
        formal_query_rows=125259, engineering_reserve=4096, engineering_rows_used=1728,
        entry_extra_rows=0, entry_extra_updates=0, query_hard_cap=130000, disk_hard_cap_MiB=512,
        resume_run0_at=2048, training_namespace=67000000, validation_namespace=68000000,
        future_test_reserved=69000000, test_release=False, design=ep_design, parents=sources,
        forecast=forecast, base_config=cfg), allow_unicode=True, sort_keys=False).encode())
    paths = [PROTOCOL, Path(__file__), macro_file, Path(cfg_ref["path"]), ENGINEERING/"complete.json",
             ENGINEERING/"output_manifest.csv", SOURCE/"config.yaml"]
    paths.extend(REPO/"optimization_control"/f for f in (
        "maddpg_wind_farm/algorithm.py", "maddpg_wind_farm/controllers.py", "maddpg_wind_farm/workflow.py",
        "maddpg_wind_farm/history_wind_forecast.py", "maddpg_wind_farm/forecast_decision_contract.py",
        "maddpg_wind_farm/causal_speed_search.py", "maddpg_wind_farm/benchmark.py",
        "environments/maddpg_farm_env.py", "environments/farm_inflow.py", "environments/wind_pinn_backend.py",
        "utils/action_mapper.py", "utils/actuator_model.py", "utils/reference_schedule.py"))
    for tree in (REPO, ORIGIN):
        paths.extend(tree/n for n in ("PROJECT_STATUS.md", "optimization_control/TASKFLOW.md", "README.md"))
    hashes = {str(path):sha(path) for path in paths}
    hashes.update({x["path"]:x["sha256"] for x in [*sources,forecast]})
    hashes.update({p:h for p,h in e_lock["hashes"].items() if p.endswith(".keras") or "modify_pinn_wind_io.py" in p})
    store.json("lock.json", dict(hashes=hashes, base_config=cfg, banks=banks, parents=sources, forecast=forecast,
        A_initial=initial, engineering_sha=sha(ENGINEERING/"complete.json"),
        engineering_source_blob_verified=True, B_C_initial_paired=True, engineering_state_rejected=True,
        fixed_rows=125259, engineering_rows=1728, entry_rows=0, entry_updates=0, no_test_release=True))
    print("Locked 192 train, 6 validation, 1 stress. No model queries.", flush=True)


def bank(lock, name):
    import numpy as np
    with np.load(verify(lock["banks"][name]), allow_pickle=False) as data:
        cases = json.loads(data["meta"].item())
        wind = data["wind"]
    for case, values in zip(cases, wind, strict=True):
        assert hashlib.sha256(values.tobytes()).hexdigest() == case["wind_sha"]
    return list(zip(cases, wind))


class World:
    def __init__(self, lock):
        from .workflow import build_env
        self.config = lock["base_config"]
        self.plant = build_env(self.config).plant
        self.predictor = self.plant.predictor

    def env(self, scope, speed):
        from .causal_speed_search import Meter
        from ..environments.maddpg_farm_env import MADDPGFarmEnv
        cfg = deepcopy(self.config["environment"])
        cfg["control_mask"] = [0,1,int(speed)]
        self.plant.predictor = Meter(self.predictor, scope)
        self.plant.predictor.kind = "formal_PINN"
        return MADDPGFarmEnv(self.plant, cfg)


def reset(env, case, wind):
    env.initial[1] = case["pitch_rad"]
    return env.reset(seed=42, options=dict(wind_trajectory=wind, target_w=case["target_w"]))


def trace_row(info, parent, z, reward):
    return [info["step"], info["target_w"], info["farm_power_w"], info["error_w"], *info["wind"],
            float(reward), info["action_change"], info["saturation_fraction"], *info["effective_wind_m_s"],
            *info["power_w"], *info["heading_rad"], *info["applied"].ravel(), *info["executed_action"].ravel(),
            *parent.ravel(), *z]


def metric(trace, case):
    import numpy as np
    columns = {name:i for i,name in enumerate(TRACE)}
    assert trace.shape == (129,len(TRACE)) and np.array_equal(trace[:,0], np.arange(129))
    error = trace[1:,3]
    actual = trace[:,19:28].reshape(129,3,3).copy()
    actual[:,:,0] = trace[:,16:19]
    action = trace[:,28:37].reshape(129,3,3)
    tv = np.abs(np.diff(actual,axis=0))
    assert np.all(tv.max(axis=(0,1)) <= np.array([.005,.00872664626,.1])+1e-7)
    assert np.all(np.abs(action) <= 1)
    gamma = (actual[:,:,0]-trace[:,5,None]+np.pi)%(2*np.pi)-np.pi
    np.testing.assert_allclose(gamma, trace[:,19:28].reshape(129,3,3)[:,:,0], atol=1e-7,rtol=0)
    return dict(case_id=case["id"], family=case["family"], split=case["split"], target_w=case["target_w"],
        pitch_rad=case["pitch_rad"], rmse_w=float(np.sqrt(np.mean(error**2))),
        bias_w=float(error.mean()), tail_rmse_w=float(np.sqrt(np.mean(error[-32:]**2))),
        max_abs_error_w=float(np.abs(error).max()), heading_tv=float(tv[:,:,0].sum()),
        pitch_tv=float(tv[:,:,1].sum()), speed_tv=float(tv[:,:,2].sum()),
        speed_command_tv=float(np.abs(np.diff(action[:,:,2],axis=0)).sum()*.667/2),
        command_mse=float(trace[1:,columns["action_mse"]].mean()),
        saturation=float(trace[1:,columns["saturation"]].mean()),
        pitch_command_boundary=float(np.mean(np.abs(action[1:,:,1])>.98)),
        speed_command_boundary=float(np.mean(np.abs(action[1:,:,2])>.98)),
        max_speed_rate=float(tv[:,:,2].max()), max_pitch_rate=float(tv[:,:,1].max()),
        max_heading_rate=float(tv[:,:,0].max()))


def evaluate(world, scope, cases, policy, *, mode=None, zero=False):
    import numpy as np
    from .forecast_speed_macro import Episode, MacroSpeed
    from .controllers import PitchController
    from unittest.mock import patch
    speed = isinstance(policy,MacroSpeed)
    env = world.env(scope,speed)
    metrics, traces = [], []
    for case,wind in cases:
        obs,info = reset(env,case,wind)
        z = np.zeros(3,np.float32)
        rows = [trace_row(info,info["executed_action"],z,0)]
        baseline = PitchController(env,world.config["baselines"],mode) if mode else None
        episode = Episode(policy,env,obs,info) if speed else None
        for t in range(128):
            if episode:
                if zero:
                    with patch.object(policy,"z",return_value=z):
                        parent,_,held,reward,done,info = episode.step()
                else:
                    parent,_,held,reward,done,info = episode.step()
            else:
                parent = baseline.act(obs) if baseline else policy.act(obs)
                obs,reward,done,trunc,info = env.step(parent)
                assert not trunc
                held = z
            assert done == (t==127)
            rows.append(trace_row(info,parent,held,reward[0]))
        trace = np.asarray(rows,np.float64)
        traces.append(trace)
        metrics.append(metric(trace,case))
    return metrics,np.stack(traces)


def save_eval(store, tag, metrics, traces):
    import numpy as np
    return dict(metrics=store.json(f"{tag}/metrics.json",metrics),
                trace=store.arrays(f"{tag}/traces.npz", trace=traces, fields=np.array(TRACE)))


def fresh(lock, arm, run):
    import numpy as np
    from .algorithm import MADDPG
    if arm == "A":
        agent,_ = MADDPG.load(verify(lock["parents"][run]))
        noise = np.random.default_rng(np.random.SeedSequence([42,20261030,8605,run]))
        return agent,noise
    return formal_class()(lock["parents"][run],lock["forecast"],run,arm),None


def snapshot(store, tag, lock, agent, arm, run, step):
    if arm == "A" and step == 0:
        return lock["parents"][run] | dict(original_parent=True)
    weights = agent.actors if arm == "A" else agent.heads
    return store.torch(f"{tag}/inference.pt",dict(purpose=PURPOSE,arm=arm,run=run,step=step,
        lock_sha=sha(ROOT/"lock.json"),weights=weights.state_dict()),MIB//4)


def inference(lock, ref, arm, run, step):
    import torch
    agent,_ = fresh(lock,arm,run)
    if not ref.get("original_parent",False):
        state = torch.load(verify(ref),map_location="cpu",weights_only=True)
        assert (state["purpose"],state["arm"],state["run"],state["step"],state["lock_sha"]) == (
            PURPOSE,arm,run,step,sha(ROOT/"lock.json"))
        (agent.actors if arm=="A" else agent.heads).load_state_dict(state["weights"],strict=True)
    else:
        assert arm=="A" and step==0 and ref["sha256"]==lock["parents"][run]["sha256"]
    return agent


def expected_updates(arm, step):
    first,stride = (512,2) if arm=="A" else (512,16)
    return 0 if step<first else (step-first)//stride+1


def save_state(store, tag, lock, agent, noise, arm, run, step, bank_next):
    meta = dict(purpose=PURPOSE,arm=arm,run=run,step=step,episode=step//128,next_case=bank_next,
                lock_sha=sha(ROOT/"lock.json"))
    if arm=="A":
        with io.BytesIO() as buf:
            agent.save(buf,meta|dict(noise=noise.bit_generator.state))
            state = store.write(f"{tag}/state.pth",buf.getbuffer(),28*MIB)
    else:
        state = store.torch(f"{tag}/state.pth",agent.state(),3*MIB)
    return store.json(f"{tag}/state_ref.json",dict(state=state,meta=meta))


def resume(lock, arm, run, receipt, step, bank_next):
    import numpy as np
    from .algorithm import MADDPG
    ref = read(verify(receipt["checkpoint"]))
    meta = ref["meta"]
    assert (meta["purpose"],meta["arm"],meta["run"],meta["step"],meta["episode"],meta["next_case"],meta["lock_sha"]) == (
        PURPOSE,arm,run,step,step//128,bank_next,sha(ROOT/"lock.json"))
    path = verify(ref["state"])
    if arm=="A":
        agent,original_meta = MADDPG.load(path)
        noise = np.random.default_rng()
        noise.bit_generator.state = original_meta.pop("noise")
        assert original_meta == meta
        initial = lock["A_initial"][run]
        assert agent.updates == initial["updates"]+expected_updates(arm,step)
        assert agent.replay.size == min(32768,initial["replay"]+step)
        assert agent.replay.position == (initial["position"]+step)%32768
    else:
        identity = dict(parent=lock["parents"][run],forecast=lock["forecast"],run=run,arm=arm)
        agent = formal_class().load(path,identity,ref["state"]["sha256"])
        noise = None
        assert (agent.steps,agent.episodes,agent.draws,agent.replay.insertions,agent.updates)==(
            step,step//128,step//8,step//8,expected_updates(arm,step))
    return agent,noise


def train_segment(world, scope, lock, agent, noise, arm, run, step, training):
    import numpy as np
    from .forecast_speed_macro import Episode
    env = world.env(scope,arm!="A")
    logs = []
    for ordinal in range((step-2048)//128,step//128):
        case,wind = training[ordinal]
        obs,info = reset(env,case,wind)
        episode = Episode(agent,env,obs,info,collect=True,explore=True) if arm!="A" else None
        updates,errors,rewards,motion = [],[],[],[]
        for t in range(128):
            k = ordinal*128+t
            if arm=="A":
                action = agent.act(obs)
                action[:,1] = np.clip(action[:,1]+noise.normal(0,.03*(1-.8*k/8192),3),-1,1)
                nxt,reward,done,trunc,info = env.step(action)
                assert not trunc and np.max(np.abs(info["executed_action"][:,[0,2]]-action[:,[0,2]])) <= 2e-6
                agent.replay.add(obs,info["executed_action"],reward,nxt,done)
                obs = nxt
                if k+1>=512 and (k+1)%2==0:
                    updates.append(agent.update())
            else:
                _,_,_,reward,done,info = episode.step()
                if episode.pending is None and k+1>=512 and (k+1)%16==0:
                    update = agent.update(lambda:None)
                    updates.append(dict(actor_loss=float(np.mean(update["losses"][1::2])),
                        critic_loss=float(np.mean(update["losses"][::2])),
                        actor_grad_norm=float(np.mean(update["gradient_norms"][1::2])),
                        critic_grad_norm=float(np.mean(update["gradient_norms"][::2]))))
            assert done==(t==127)
            errors.append(info["error_w"]);rewards.append(float(reward[0]));motion.append(info["action_change"])
        stats = {key:float(np.mean([row[key] for row in updates])) for key in updates[0]} if updates else {}
        logs.append(dict(**case,ordinal=ordinal,step=(ordinal+1)*128,updates=len(updates),
            rmse_w=float(np.sqrt(np.mean(np.square(errors)))),bias_w=float(np.mean(errors)),
            reward_mean=float(np.mean(rewards)),command_mse=float(np.mean(motion)),loss_summary=stats))
    assert sum(x["updates"] for x in logs) == expected_updates(arm,step)-expected_updates(arm,step-2048)
    if arm!="A":
        assert (agent.steps,agent.draws,agent.episodes,agent.updates)==(step,step//8,step//128,expected_updates(arm,step))
    return logs


def worker(arm, run, stop):
    import numpy as np
    import torch
    from .forecast_decision_contract import model_digest
    lock = context()
    store = Store(ROOT/"jobs"/job_name(arm,run),job_cap(arm))
    training = bank(lock,f"train{run}")
    validation = bank(lock,"validation")
    start = 0
    last = None
    for point in POINTS:
        path = store.folder/f"s{point:04d}/complete.json"
        if path.exists():
            start,last = point,read(path)
        elif (path.parent/"reserved.json").exists():
            raise ValueError("unfinished reserved scope retained; inspect before any replay")
        else:
            break
    if last and (start!=2048 or run!=0 or stop!=8192):
        raise ValueError("only the planned run0 restart is allowed")
    if last:
        assert last["pid"] != os.getpid() and last["rows"] == 2838
        agent,noise = resume(lock,arm,run,last,start,training[start//128][0]["id"])
        store.json("restart.json",dict(previous_pid=last["pid"],pid=os.getpid(),from_step=start,
            next_step=start+1,next_episode=training[start//128][0],restored_checkpoint=last["checkpoint"]))
    else:
        agent,noise = fresh(lock,arm,run)
    protected = model_digest(agent.parent) if arm!="A" else None
    world = World(lock)
    for step in POINTS:
        if (last is not None and step<=start) or step>stop:
            continue
        begin = time.perf_counter()
        tag = f"s{step:04d}"
        scope = QueryScope(store,tag,2838 if step else 774,arm=arm,run=run,step=step)
        logs = train_segment(world,scope,lock,agent,noise,arm,run,step,training) if step else []
        train_ref = store.json(f"{tag}/episodes.json",logs)
        checkpoint = (save_state(store,tag,lock,agent,noise,arm,run,step,
            training[step//128][0]["id"] if step<8192 else None) if step else None)
        snap = snapshot(store,tag,lock,agent,arm,run,step)
        rng = torch.get_rng_state().clone()
        metrics,traces = evaluate(world,scope,validation,agent)
        assert torch.equal(rng,torch.get_rng_state())
        if protected is not None:
            assert model_digest(agent.parent)==protected
        ev = save_eval(store,tag,metrics,traces)
        mean = float(np.mean([x["rmse_w"] for x in metrics]))
        scope.finish(step=step,checkpoint=checkpoint,snapshot=snap,eval=ev,episodes=train_ref,mean_w=mean,
                     worst_w=max(x["rmse_w"] for x in metrics),elapsed_s=time.perf_counter()-begin,
                     new_updates=expected_updates(arm,step))
        print(f"{arm}{run} step={step} mean={mean/1000:.3f} kW, {time.perf_counter()-begin:.1f}s",flush=True)


def select():
    lock = context()
    jobs = []
    for arm in ARMS:
        for run in RUNS:
            folder=ROOT/"jobs"/job_name(arm,run)
            points=[read(folder/f"s{x:04d}/complete.json") for x in POINTS]
            assert [x["rows"] for x in points]==[774]+[2838]*4
            for row in points:
                for ref in (row["reservation"],row["snapshot"],row["episodes"],*row["eval"].values()):
                    verify(ref)
                if row["checkpoint"]:
                    verify(read(verify(row["checkpoint"]))["state"])
            chosen=min(points,key=lambda x:(x["mean_w"],x["step"]))
            if run==0:
                restart=read(folder/"restart.json")
                assert restart["next_step"]==2049 and restart["pid"]!=restart["previous_pid"]
                assert points[1]["pid"]==restart["previous_pid"] and points[2]["pid"]==restart["pid"]
            jobs.append(dict(arm=arm,run=run,initial=points[0],selected=chosen,final=points[-1],points=points))
    Store(ROOT,68*MIB,shared=True).json("selection.json",dict(lock_sha=sha(ROOT/"lock.json"),jobs=jobs,
        steps=73728,rows=109134,no_independent_test_release=True,criterion="strictly_lowest_validation_mean_then_earliest"))


def diagnostics():
    lock=context()
    selection=read(ROOT/"selection.json")
    assert selection["lock_sha"]==sha(ROOT/"lock.json")
    world=World(lock)
    store=Store(ROOT,68*MIB,shared=True)
    val,stress=bank(lock,"validation"),bank(lock,"stress")
    groups=[]
    def one(group,policy,cases,**kwargs):
        scope=QueryScope(store,group,len(cases)*129,selection_sha=sha(ROOT/"selection.json"))
        metrics,trace=evaluate(world,scope,cases,policy,**kwargs)
        ref=scope.finish(eval=save_eval(store,group,metrics,trace))
        groups.append(dict(group=group,receipt=ref))
    for run in RUNS:
        parent,_=fresh(lock,"A",run)
        one(f"diagnostics/parent{run}/validation",parent,val)
        one(f"diagnostics/parent{run}/stress",parent,stress)
    for mode in ("p","pi"):
        one(f"diagnostics/{mode}/validation",None,val,mode=mode)
        one(f"diagnostics/{mode}/stress",None,stress,mode=mode)
    for job in selection["jobs"]:
        arm,run=job["arm"],job["run"]
        for role in ("selected","final"):
            row=job[role]
            policy=inference(lock,row["snapshot"],arm,run,row["step"])
            label=f"diagnostics/{arm}{run}/{role}"
            if arm!="A":
                one(label+"/zero",policy,val,zero=True)
            one(label+"/stress",policy,stress)
    rows=sum(read(verify(x["receipt"]))["rows"] for x in groups)
    assert rows==16125 and 109134+rows==125259
    store.json("diagnostics_complete.json",dict(groups=groups,rows=rows,formal_rows=125259,
        formal_steps=73728,engineering_rows=1728,cumulative_model_rows=126987,no_new_test=True,
        selection_sha=sha(ROOT/"selection.json")))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("prepare","worker","select","diagnostics"))
    parser.add_argument("--arm",choices=ARMS)
    parser.add_argument("--run",type=int,choices=RUNS)
    parser.add_argument("--stop",type=int,choices=(2048,8192),default=8192)
    args=parser.parse_args()
    if args.mode=="worker" and (args.arm is None or args.run is None or (args.stop==2048 and args.run!=0)):
        parser.error("worker requires arm/run, and only run0 may stop at 2048")
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(ORIGIN/".venv/pinn_tf216")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS","1")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS","1")
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(42)
    if args.mode=="worker":
        worker(args.arm,args.run,args.stop)
    else:
        {"prepare":prepare,"select":select,"diagnostics":diagnostics}[args.mode]()


if __name__=="__main__":
    main()
