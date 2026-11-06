"""Bounded engineering-only in-memory updates; no environment/test/candidate training."""
from copy import deepcopy
from dataclasses import replace
import argparse
import ast
import io
import json
from pathlib import Path
import subprocess

from .anchor_closeout import sha,read_json,write_json,write_csv,verify_hashes,checked_output

SOURCE_COMMIT='740d04044e6b046dfe6256bfa3c2d4ef88925783'
SOURCE_REPO=Path('.')


def git_blob(path):
    return subprocess.check_output(['git','-c','safe.directory='+str(SOURCE_REPO),'-C',str(SOURCE_REPO),'show',SOURCE_COMMIT+':'+path])


def prepare(root):
    import hashlib
    import yaml
    from .nstep_replay_core import SOURCE_CLASS_SHA256,SOURCE_FILE_SHA256
    worktree=Path(__file__).resolve().parents[2]
    source=worktree/'optimization_control/experiments/20261028_frozen_speed_checked'
    value=source.with_name('20261028_speed_value_diagnostic')
    root=checked_output(root,worktree,Path('.'))
    if root.is_relative_to(source) or root.is_relative_to(value):raise ValueError('history read-only')
    old=yaml.safe_load((source/'config.yaml').read_text(encoding='utf-8'))
    selection=read_json(source/'selection.json')
    pins={str(p):sha(p) for folder in (source,value) for p in folder.rglob('*') if p.is_file()}
    for path,digest in old['source_hashes'].items():
        if Path(path).name not in ('README.md','PROJECT_STATUS.md','TASKFLOW.md'):
            assert sha(path)==digest;pins[path]=digest
    source_files={}
    names=['optimization_control/maddpg_wind_farm/nstep_algorithm.py','optimization_control/tests/test_pitch_nstep.py',
           'optimization_control/maddpg_wind_farm/PITCH_NSTEP_PROTOCOL.md']
    for name in names:source_files[name]=hashlib.sha256(git_blob(name)).hexdigest()
    text=git_blob(names[0]).decode('utf-8');node=next(n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name=='SequenceReplay')
    body=ast.get_source_segment(text,node)
    assert hashlib.sha256(body.encode()).hexdigest()==SOURCE_CLASS_SHA256
    assert source_files[names[0]]==SOURCE_FILE_SHA256
    code_paths=[Path(__file__),Path(__file__).with_name('speed_nstep_algorithm.py'),Path(__file__).with_name('nstep_replay_core.py'),
        worktree/'optimization_control/tests/test_speed_nstep.py',Path(__file__).with_name('SPEED_NSTEP_ENGINEERING_PROTOCOL.md')]
    execution={str(p):sha(p) for p in code_paths}
    # Original update and mapping dependencies stay byte-identical as well.
    for name in ('algorithm.py','frozen_speed_algorithm.py','verify_anchor.py','benchmark.py'):
        p=Path(__file__).with_name(name);execution[str(p)]=sha(p)
    root.mkdir(parents=True,exist_ok=False);(root/'source_740d040').mkdir()
    for name in names:(root/'source_740d040'/Path(name).name).write_bytes(git_blob(name))
    cfg=dict(seed=42,purpose='speed_nstep_engineering_not_candidate',source_commit=SOURCE_COMMIT,
        source_blob_hashes=source_files,sequence_class_sha256=SOURCE_CLASS_SHA256,
        parents=old['parents'],finals=[r for r in selection['results'] if r['arm']=='speed'],
        source_hashes=pins,executed_code_hashes=execution,max_real_discarded_update_calls=39,
        head_namespace=8405,formal_training_steps=0,new_environment_steps=0,new_policy_files=0,
        old_test_states_used=False,worktree=str(worktree),
        coordination={str(Path('.')/n):sha(Path('.')/n) for n in ('PROJECT_STATUS.md','README.md','optimization_control/TASKFLOW.md')})
    # Avoid embedding old environment arrays/results in a new engineering config.
    cfg['finals']=[{k:r[k] for k in ('run_id','final','parent')} for r in cfg['finals']]
    (root/'config.yaml').write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    write_json(root/'summary.txt',dict(seed=42,status='prepared',formal_training_steps=0,engineering_updates_cap=39))
    write_csv(root/'metrics.csv',[dict(status='prepared',formal_training_steps=0)])


def clone_v4(agent):
    from .frozen_speed_algorithm import FrozenSpeedMADDPG
    buffer=io.BytesIO();agent.save(buffer,{});buffer.seek(0)
    return FrozenSpeedMADDPG.load(buffer)[0]


def assert_equal(a,b):
    import numpy as np
    from .verify_anchor import comparable
    for key in ('actors','target_actors','critics','target_critics','speed_heads','target_speed_heads'):
        np.testing.assert_equal(comparable(getattr(a,key).state_dict()),comparable(getattr(b,key).state_dict()))
    for key in ('head_optimizers','critic_optimizers'):
        np.testing.assert_equal(comparable([o.state_dict() for o in getattr(a,key)]),comparable([o.state_dict() for o in getattr(b,key)]))


def independent_spans(replay,starts,n):
    import numpy as np
    rewards=[];ends=[];lengths=[]
    for start in starts:
        end=int(start);value=replay.data['rewards'][end].copy();m=1
        while m<n and not replay.data['terminated'][end,0]:
            nxt=(end+1)%replay.capacity
            if hasattr(replay,'sequence') and replay.sequence[nxt]!=replay.sequence[end]+1:break
            if not np.array_equal(replay.data['next_obs'][end],replay.data['obs'][nxt]):raise ValueError('independent continuity check')
            value+=(replay.gamma**m)*replay.data['rewards'][nxt];end=nxt;m+=1
        rewards.append(value);ends.append(end);lengths.append(m)
    return np.asarray(rewards),np.asarray(ends),np.asarray(lengths)


def trace_update(agent,radius):
    import numpy as np
    import torch
    from ..utils.reference_schedule import speed_torch
    agent.config=replace(agent.config,speed_scale=2*radius/.667)
    replay=agent.replay;data={};sample=replay.sample;td=agent.td_target
    rng=np.random.default_rng(42);rng.bit_generator.state=deepcopy(replay.rng.bit_generator.state)
    predicted=rng.choice(replay.size,agent.config.batch_size,replace=False)
    def capture(size,device):
        b=sample(size,device);data['batch']={k:v.detach().clone() for k,v in b.items()};return b
    def capture_td(r,d,q,g):
        result=td(r,d,q,g);data.setdefault('targets',[]).append(result.detach().clone());return result
    def pre(_,args):
        b=data['batch'];future=b['next_obs'];x=args[0].detach()
        with torch.no_grad():
            pitch=torch.stack([agent.target_actors[i](future[:,i])[:,1] for i in range(3)],1)
            raw=torch.stack([agent.target_speed_heads[i](future[:,i]).squeeze(-1) for i in range(3)],1)
            speed=(speed_torch(future,agent.config.speed_schedule)+raw*agent.config.speed_scale).clamp(-1,1)
            expected=torch.stack((torch.zeros_like(pitch)+agent.config.fixed_action[0],pitch,speed),2)
        assert torch.equal(x[:,:45],future.flatten(1)) and torch.equal(x[:,45:],expected.flatten(1))
        data.setdefault('target_inputs',[]).append(x.clone())
    def post(_,args,out):data.setdefault('target_q',[]).append(out.detach().clone())
    replay.sample=capture;agent.td_target=capture_td
    hooks=[h for c in agent.target_critics for h in (c.register_forward_pre_hook(pre),c.register_forward_hook(post))]
    try:loss=agent.update()
    finally:
        replay.__dict__.pop('sample',None);agent.__dict__.pop('td_target',None)
        for hook in hooks:hook.remove()
    starts=replay.last_indices if hasattr(replay,'last_indices') else predicted
    np.testing.assert_array_equal(starts,predicted)
    n=getattr(agent,'n',1)
    returns,ends,m=independent_spans(replay,starts,n)
    b=data['batch'];np.testing.assert_array_equal(b['actions'].numpy(),replay.data['actions'][starts])
    np.testing.assert_array_equal(b['actions'].numpy(),replay.data['next_obs'][starts,:,5:8])
    np.testing.assert_array_equal(b['next_obs'].numpy(),replay.data['next_obs'][ends])
    np.testing.assert_array_equal(b['rewards'].numpy(),returns)
    d=torch.tensor(replay.data['terminated'][ends])
    for i,q in enumerate(data['target_q']):
        if n==1:expected=torch.tensor(returns[:,i:i+1])+agent.config.gamma*(1-d)*q
        else:expected=torch.tensor(returns[:,i:i+1])+torch.tensor(agent.config.gamma**m,dtype=torch.float32)[:,None]*(1-d)*q
        assert torch.equal(expected,data['targets'][i])
    data.update(starts=starts.copy(),ends=ends,m=m,loss=loss,radius=radius)
    return data


def run(root):
    import numpy as np
    import torch
    import yaml
    from .algorithm import MADDPG
    from .frozen_speed_algorithm import FrozenSpeedMADDPG
    from .speed_nstep_algorithm import FrozenSpeedNStepMADDPG,validate_ring
    from .benchmark import seed_for
    from .verify_anchor import comparable
    cfg=yaml.safe_load((root/'config.yaml').read_text(encoding='utf-8'))
    verify_hashes(cfg['source_hashes']);verify_hashes(cfg['executed_code_hashes'])
    if (root/'complete.json').exists():raise ValueError('Engineering audit completed; use saved results')
    metrics=[];ledgers=[];proofs=[];calls=0
    for run_id,p in enumerate(cfg['parents']):
        parent,pm=MADDPG.load(p['checkpoint'])
        # Count is derived from independently saved lineage, not from retained size.
        count=pm['lineage']['cumulative_parent_steps']+pm['steps']
        if count!=p['cumulative_parent_steps']:raise ValueError('parent lineage count mismatch')
        parent.config=replace(parent.config,actor_lr=1e-4)
        base=FrozenSpeedMADDPG.from_parent(parent,seed_for(42,cfg['head_namespace'],run_id))
        origin=sha(p['checkpoint']);evidence=dict(expected_insertions=count,source_sha256=origin,
            derivation='metadata.lineage.cumulative_parent_steps + metadata.steps')
        def wrap(n):return FrozenSpeedNStepMADDPG.adapt(clone_v4(base),n,insertion_count=count,horizon=128,epoch=origin,evidence=evidence)
        original=clone_v4(base);n1=wrap(1);n8=wrap(8)
        assert_equal(base,n1);assert_equal(base,n8)
        proofs.append(dict(run_id=run_id,source='original_pitch_parent',**n8.replay.proof))
        first_actors=deepcopy(base.actors.state_dict());first_targets=deepcopy(base.target_actors.state_dict())
        for step,radius in enumerate((.02,.06,.10),1):
            a,b,c=(trace_update(agent,radius) for agent in (original,n1,n8));calls+=3
            assert a['loss']==b['loss'];assert_equal(original,n1)
            np.testing.assert_array_equal(a['starts'],b['starts']);np.testing.assert_array_equal(b['starts'],c['starts'])
            np.testing.assert_equal(comparable(first_actors),comparable(n8.actors.state_dict()))
            np.testing.assert_equal(comparable(original.target_actors.state_dict()),comparable(n8.target_actors.state_dict()))
            for label,trace in (('legacy_n1',a),('adapted_n1',b),('adapted_n8',c)):
                ledgers.append(dict(run_id=run_id,source='parent',label=label,update=step,radius=radius,
                    starts=trace['starts'].tolist(),ends=trace['ends'].tolist(),actual_m=trace['m'].tolist(),
                    losses_for_reproduction_only=trace['loss'],targets=[t.numpy().tolist() for t in trace['targets']]))
        expected=deepcopy(first_targets)
        for _ in range(3):
            for key,v in expected.items():v.lerp_(first_actors[key],base.config.tau)
        np.testing.assert_equal(comparable(expected),comparable(n8.target_actors.state_dict()))
        buffer=io.BytesIO();n8.save(buffer,dict(artifact_kind='engineering_audit_not_candidate'));buffer.seek(0)
        restored,meta=FrozenSpeedNStepMADDPG.load(buffer,expected_n=8)
        a,b=trace_update(n8,.06),trace_update(restored,.06);calls+=2
        assert a['loss']==b['loss'];assert_equal(n8,restored)
        np.testing.assert_equal(n8.replay.state_dict(),restored.replay.state_dict())
        metrics.append(dict(run_id=run_id,source='pitch_parent',insertion_count=count,replay_size=base.replay.size,
            n1_exact_updates=3,paired_n1_n8_anchors=True,n8_restore_exact=True,
            future_total_actions_and_actual_m_targets=True,current_radius_checked='0.02/0.06/0.10',discarded_updates=11))
        final=next(r for r in cfg['finals'] if r['run_id']==run_id)
        agent,fm=FrozenSpeedNStepMADDPG.from_v4(final['final'],8)
        order=(agent.replay.position+np.arange(agent.replay.size))%agent.replay.capacity
        start=next(int(i) for i in order if np.all(agent.replay.data['obs'][i,:,14]==1))
        ids=(start+np.arange(8))%agent.replay.capacity
        copied={key:values[ids].copy() for key,values in agent.replay.data.items()}
        first=agent.replay.position
        for j in range(8):agent.replay.add(copied['obs'][j],copied['actions'][j],copied['rewards'][j],copied['next_obs'][j],copied['terminated'][j,0])
        anchors=[first,(agent.replay.position-1)%agent.replay.capacity,(first-1)%agent.replay.capacity]
        returns,ends,lengths=agent.replay.spans(anchors)
        np.testing.assert_array_equal(lengths,[8,1,1]);np.testing.assert_array_equal(agent.replay.data['terminated'][ends,0],[0,0,1])
        direct=independent_spans(agent.replay,anchors,8)
        for x,y in zip((returns,ends,lengths),direct):np.testing.assert_array_equal(x,y)
        buffer=io.BytesIO();agent.save(buffer,dict(artifact_kind='engineering_audit_not_candidate',copied_train_slots=ids.tolist()));buffer.seek(0)
        other,_=FrozenSpeedNStepMADDPG.load(buffer,expected_n=8)
        a,b=trace_update(agent,.02),trace_update(other,.02);calls+=2
        assert a['loss']==b['loss'];assert_equal(agent,other);np.testing.assert_equal(agent.replay.state_dict(),other.replay.state_dict())
        proofs.append(dict(run_id=run_id,source='old_speed_final',**agent.replay.proof))
        metrics.append(dict(run_id=run_id,source='old_speed_final_plus_8_train_copies',insertion_count=agent.replay.insertions,
            replay_size=agent.replay.size,n1_exact_updates=0,paired_n1_n8_anchors=True,n8_restore_exact=True,
            future_total_actions_and_actual_m_targets=True,current_radius_checked='0.02',discarded_updates=2))
        ledgers.append(dict(run_id=run_id,source='train_replay_copy_append_only_engineering',copied_slots=ids.tolist(),
            probe_slots=anchors,actual_m=lengths.tolist(),terminal=[0,0,1],replay_position=agent.replay.position,
            monotonic_insertions=agent.replay.insertions,losses_for_exact_recovery_only=a['loss']))
        print('Engineering stream',run_id,'passed; discarded update calls',calls,flush=True)
    assert calls==cfg['max_real_discarded_update_calls']==39
    verify_hashes(cfg['source_hashes']);verify_hashes(cfg['executed_code_hashes'])
    write_csv(root/'metrics.csv',metrics);write_json(root/'updates.json',ledgers);write_json(root/'migration_proofs.json',proofs)
    write_json(root/'summary.txt',dict(seed=42,status='engineering_verified',formal_training_steps=0,new_environment_steps=0,
        real_replay_discarded_update_calls=calls,new_policy_files=0,test_states_used=False,n1_precision='exact',
        real_parent_streams=3,old_final_replays=3,performance_support=False,formal_start_allowed=False,
        draft='../../maddpg_wind_farm/SPEED_NSTEP_DRAFT.md'))
    write_json(root/'complete.json',{name:sha(root/name) for name in ('config.yaml','metrics.csv','updates.json','migration_proofs.json','summary.txt')})


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','run'));parser.add_argument('--output',required=True)
    args=parser.parse_args()
    from .fixed_pinn_demo import activate_runtime
    activate_runtime(Path('./.venv/pinn_tf216'))
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    (prepare if args.command=='prepare' else run)(Path(args.output).resolve())


if __name__=='__main__':main()
