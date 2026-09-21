# -*- coding: utf-8 -*-
"""PPO Evaluation Script"""
from simplified_turbine_env import SimplifiedTurbineEnv
import numpy as np

def run_eval():
    env = SimplifiedTurbineEnv()
    obs = env.reset(target_p=1800.0, u_inf=8.0)
    print(f"✅ PPO 环境初始化成功, Initial Obs: {obs}")
    for step in range(10):
        obs, r, _, info = env.step(2.5)
    print(f"✅ 评估完成: P_actual={info['power_actual']:.1f} kW, Target={env.target_p} kW, Error={info['error']:.2f} kW")

if __name__ == "__main__":
    run_eval()
