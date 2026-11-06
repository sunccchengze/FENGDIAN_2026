"""Fixed direct ridge forecast; public inference accepts observed history only."""
from pathlib import Path
import hashlib


def features(history):
    import numpy as np
    history=np.asarray(history,dtype=np.float32)
    if history.ndim!=2 or history.shape[1]!=3 or not len(history) or not np.isfinite(history).all():
        raise ValueError('finite nonempty observed history [N,3] required')
    history=history[-32:].astype(np.float64)
    if len(history)<32:history=np.concatenate((np.repeat(history[:1],32-len(history),axis=0),history))
    z=np.column_stack((history[:,0],np.sin(history[:,1]),np.cos(history[:,1])))
    return np.r_[z[-1],(z[-2::-1]-z[-1]).ravel()]


class RidgeForecast:
    def __init__(self,mean,scale,target_mean,coefficients):
        import numpy as np
        self.mean=np.asarray(mean,np.float64);self.scale=np.asarray(scale,np.float64)
        self.target_mean=np.asarray(target_mean,np.float64);self.coefficients=np.asarray(coefficients,np.float64)
        if (self.mean.shape,self.scale.shape,self.target_mean.shape,self.coefficients.shape)!=((96,),(96,),(36,),(96,36)):
            raise ValueError('fixed forecast coefficient shapes required')
        if not all(np.isfinite(x).all() for x in (self.mean,self.scale,self.target_mean,self.coefficients)) or not (self.scale>0).all():
            raise ValueError('invalid forecast parameters')

    def predict(self,history):
        import numpy as np
        history=np.asarray(history,np.float32);x=features(history)
        change=(((x-self.mean)/self.scale)@self.coefficients+self.target_mean).reshape(12,3)
        current=history[-1].astype(np.float64)
        z=np.array([current[0],np.sin(current[1]),np.cos(current[1])])+change
        norm=np.hypot(z[:,1],z[:,2]);fallback=norm<1e-12
        direction=np.mod(np.arctan2(z[:,1],z[:,2]),2*np.pi);direction[fallback]=current[1]
        speed=np.clip(z[:,0],7.5,10.5)
        prediction=np.column_stack((speed,direction,np.full(12,current[2]))).astype(np.float32)
        return prediction,dict(raw_speed_m_s=z[:,0].tolist(),speed_clipped=(z[:,0]!=speed).tolist(),
            speed_clip_delta_m_s=(speed-z[:,0]).tolist(),direction_fallback=fallback.tolist(),
            observed_samples=len(history),feature_sha256=hashlib.sha256(x.tobytes()).hexdigest())

    def save(self,path):
        import numpy as np
        np.savez_compressed(path,mean=self.mean,scale=self.scale,target_mean=self.target_mean,coefficients=self.coefficients)

    @classmethod
    def load(cls,path):
        import numpy as np
        with np.load(path,allow_pickle=False) as saved:return cls(**{k:saved[k] for k in ('mean','scale','target_mean','coefficients')})


def fit(trajectories):
    import numpy as np
    xs=[];ys=[]
    for values in trajectories:
        values=np.asarray(values,np.float32)
        if values.shape!=(129,3):raise ValueError('entire 128-second trajectory required')
        z=np.column_stack((values[:,0].astype(float),np.sin(values[:,1].astype(float)),np.cos(values[:,1].astype(float))))
        for t in range(117):
            xs.append(features(values[:t+1]));ys.append((z[t+1:t+13]-z[t]).ravel())
    x=np.asarray(xs);y=np.asarray(ys);mean=x.mean(axis=0);scale=x.std(axis=0)
    scale[scale<1e-8]=1.;target_mean=y.mean(axis=0);x=(x-mean)/scale;y=y-target_mean
    gram=x.T@x/len(x)+.1*np.eye(96);rhs=x.T@y/len(x)
    coefficients=np.linalg.solve(gram,rhs);residual=x@coefficients-y
    model=RidgeForecast(mean,scale,target_mean,coefficients)
    return model,dict(fit_trajectories=len(trajectories),fit_windows=len(x),feature_count=96,response_count=36,
        alpha=.1,training_only_normalizer=True,solver_residual_max=float(np.max(np.abs(gram@coefficients-rhs))),
        in_sample_uncorrected_increment_MSE_by_horizon_and_channel=np.mean(residual**2,axis=0).reshape(12,3).tolist())


def score(model,values):
    import numpy as np
    values=np.asarray(values,np.float32);records=[]
    for t in range(0,128,8):
        predicted,details=model.predict(values[:t+1])
        for k in range(min(12,128-t)):
            actual=values[t+k+1].astype(float);forecast=predicted[k].astype(float);current=values[t].astype(float)
            angle=lambda d:float((d+np.pi)%(2*np.pi)-np.pi)
            records.append(dict(origin=t,horizon=k+1,actual_speed=actual[0],predicted_speed=forecast[0],persistence_speed=current[0],
                speed_error=forecast[0]-actual[0],persistence_speed_error=current[0]-actual[0],
                direction_error=angle(forecast[1]-actual[1]),persistence_direction_error=angle(current[1]-actual[1]),
                ti_error=forecast[2]-actual[2],speed_clipped=int(details['speed_clipped'][k]),
                speed_clip_delta=details['speed_clip_delta_m_s'][k],direction_fallback=int(details['direction_fallback'][k])))
    result=[]
    for label,h,complete in [('1_8',8,False),('1_12',12,True)]+[(f'h{i}',i,False) for i in range(1,13)]:
        part=[r for r in records if (r['horizon']<=h if label.startswith('1_') else r['horizon']==h) and (not complete or r['origin']<=112)]
        row=dict(interval=label,samples=len(part))
        for name in ('speed','direction'):
            row[f'{name}_MSE']=float(np.mean([r[f'{name}_error']**2 for r in part]))
            row[f'persistence_{name}_MSE']=float(np.mean([r[f'persistence_{name}_error']**2 for r in part]))
            row[f'{name}_bias']=float(np.mean([r[f'{name}_error'] for r in part]))
        row.update(speed_MSE_ratio=row['speed_MSE']/row['persistence_speed_MSE'],speed_clip_fraction=float(np.mean([r['speed_clipped'] for r in part])),
            mean_speed_clip_delta=float(np.mean([r['speed_clip_delta'] for r in part])),direction_fallbacks=sum(r['direction_fallback'] for r in part),
            ti_MSE=float(np.mean([r['ti_error']**2 for r in part])))
        result.append(row)
    return result,records


def aggregate(rows,bootstrap_samples=2000):
    import numpy as np
    result=[]
    for split in ('decision_train','decision_validation'):
        for interval in ('1_8','1_12'):
            for family in ('all','stationary','ramp','gust'):
                part=[r for r in rows if r['split']==split and r['interval']==interval and (family=='all' or r['family']==family)]
                a=np.array([r['speed_MSE'] for r in part]);b=np.array([r['persistence_speed_MSE'] for r in part])
                rng=np.random.default_rng(42);groups=[np.array([i for i,r in enumerate(part) if r['family']==f]) for f in ('stationary','ramp','gust')]
                groups=[g for g in groups if len(g)]
                samples=np.concatenate([rng.choice(g,size=(bootstrap_samples,len(g)),replace=True) for g in groups],axis=1)
                ratios=a[samples].mean(axis=1)/b[samples].mean(axis=1);differences=(a-b)[samples].mean(axis=1)
                row=dict(split=split,interval=interval,family=family,trajectories=len(part),speed_MSE=float(a.mean()),
                    persistence_speed_MSE=float(b.mean()),speed_MSE_ratio=float(a.mean()/b.mean()),
                    ratio_CI95_low=float(np.quantile(ratios,.025)),ratio_CI95_high=float(np.quantile(ratios,.975)),
                    difference_CI95_low=float(np.quantile(differences,.025)),difference_CI95_high=float(np.quantile(differences,.975)))
                for key in ('speed_bias','direction_MSE','persistence_direction_MSE','direction_bias','speed_clip_fraction','mean_speed_clip_delta','ti_MSE'):
                    row[key]=float(np.mean([r[key] for r in part]))
                result.append(row)
    primary=[r for r in result if r['split']=='decision_validation' and r['interval']=='1_8']
    overall=next(r for r in primary if r['family']=='all');families=[r for r in primary if r['family']!='all']
    screen=dict(passed=overall['speed_MSE_ratio']<1 and sum(r['speed_MSE_ratio']<1 for r in families)>=2 and max(r['speed_MSE_ratio'] for r in families)<=1.05,
        primary_split='decision_validation',primary_interval='1_8',improved_families=sum(r['speed_MSE_ratio']<1 for r in families),
        maximum_family_ratio=max(r['speed_MSE_ratio'] for r in families),overall_ratio=overall['speed_MSE_ratio'],
        exploratory_only=True,final_control_gate_unchanged=True)
    return result,screen
