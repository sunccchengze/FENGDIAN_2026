"""Run the already-approved frozen evaluation sequence once training completes."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from .pitch_actor_context_trial import context,read_json,js,size,digest,HERE


def finish(root):
    root,s=context(root);folder=root/'stages';folder.mkdir(exist_ok=True)
    while not (root/'processes/process_09.json').exists():
        for p in (root/'processes').glob('process_*.json'):
            if p.name.endswith('started.json'):continue
            if read_json(p)['returncode']!=0:raise RuntimeError(f'training failed, no auto retry: {p}')
        time.sleep(10)
    assert all(read_json(root/f'processes/process_{i:02d}.json')['returncode']==0 for i in range(10))
    stages=[('trial','select'),('trial','validation'),('trial','known'),('review','pretest'),('trial','test'),('review','review'),('figures',None)]
    for i,(module,mode) in enumerate(stages):
        completed=folder/f'{i:02d}.done.json';started=folder/f'{i:02d}.started.json'
        if completed.exists():assert read_json(completed)['returncode']==0;continue
        if started.exists():raise RuntimeError('unfinished evaluation stage retained; no silent re-execution')
        command=[sys.executable,'-B','-X','utf8','-m',__package__+'.pitch_actor_context_'+module]
        if mode:command.append(mode)
        command+=['--output',str(root)]
        env=os.environ.copy();env.update(TF_NUM_INTRAOP_THREADS='1',TF_NUM_INTEROP_THREADS='1',PYTHONHASHSEED='42')
        begin=time.time()
        with (folder/f'{i:02d}.log').open('xb') as log:
            p=subprocess.Popen(command,cwd=HERE.parents[1],stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=0x08000000 if os.name=='nt' else 0)
            js(root,started,dict(command=command,pid=p.pid,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),driver_sha256=digest(__file__)))
            code=p.wait()
        js(root,completed,dict(command=command,pid=p.pid,returncode=code,elapsed_s=time.time()-begin,storage_bytes=size(root)))
        print(dict(stage=i,module=module,mode=mode,returncode=code,storage_bytes=size(root)),flush=True)
        if code:raise RuntimeError(f'approved stage failed; see {folder/f"{i:02d}.log"}')
    js(root,root/'pipeline_complete.json',dict(status='complete',stages=7,storage_bytes=size(root),no_extra_learning=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);a=p.parse_args();finish(a.output)
