import numpy as np
import pandas as pd
import os
from pathlib import Path

print("=" * 40)
print("POD 本征正交分解")
print("=" * 40)

BASE = Path(__file__).parent

# ===== 第一步：读取所有流场快照 =====
df = pd.read_csv(BASE / "cases.csv")
df = df.sort_values("yaw_1").reset_index(drop=True)

snapshots = []
for _, row in df.iterrows():
    path = BASE / "fields" / f"{row['case_id']}.npz"
    data = np.load(path)
    u    = data["u"]           # shape: (64, 128)
    snapshots.append(u.flatten())  # 展开成一维：64×128 = 8192

# 拼成快照矩阵：每列是一个工况，shape = (8192, 13)
X = np.column_stack(snapshots)
print(f"快照矩阵形状：{X.shape}  ({X.shape[0]}个空间点 × {X.shape[1]}个工况)")

# ===== 第二步：减去均值场 =====
x_mean = X.mean(axis=1, keepdims=True)   # 空间均值场
X_centered = X - x_mean                   # 去均值

# ===== 第三步：SVD分解（POD的核心）=====
# U：空间模态，shape = (8192, 13)
# S：奇异值（能量），shape = (13,)
# Vt：时间系数，shape = (13, 13)
U, S, Vt = np.linalg.svd(X_centered, full_matrices=False)
print(f"\nSVD完成：")
print(f"  空间模态矩阵 U：{U.shape}")
print(f"  奇异值向量  S：{S.shape}")
print(f"  时间系数矩阵 Vt：{Vt.shape}")

# ===== 第四步：计算能量占比 =====
energy      = S ** 2
energy_frac = energy / energy.sum()          # 每个模态能量占比
energy_cum  = np.cumsum(energy_frac)         # 累计能量占比

print(f"\n各模态能量占比：")
for i in range(len(S)):
    print(f"  模态 {i+1:2d}：{energy_frac[i]*100:6.2f}%  "
          f"累计：{energy_cum[i]*100:6.2f}%")

# 找到累计能量超过95%和99%需要的模态数
k_95 = int(np.searchsorted(energy_cum, 0.95)) + 1
k_99 = int(np.searchsorted(energy_cum, 0.99)) + 1
print(f"\n累计能量 95% 需要：{k_95} 个模态")
print(f"累计能量 99% 需要：{k_99} 个模态")

# ===== 第五步：读取原始网格坐标 =====
sample_data = np.load(BASE / "fields" / df["case_id"].iloc[0] + ".npz"
                      if False else
                      BASE / "fields" / (df["case_id"].iloc[0] + ".npz"))
# 修正写法
sample_data = np.load(BASE / "fields" / f"{df['case_id'].iloc[0]}.npz")
x_coord = sample_data["x"]   # shape: (128,)
y_coord = sample_data["y"]   # shape: (64,)

# ===== 第六步：保存POD结果 =====
os.makedirs(BASE / "pod_results", exist_ok=True)

np.savez(
    BASE / "pod_results" / "pod_data.npz",
    # 空间信息
    x=x_coord,
    y=y_coord,
    x_mean=x_mean.reshape(64, 128),   # 均值流场
    # POD模态（前10个）
    modes=U[:, :10].T.reshape(10, 64, 128),  # shape: (10, 64, 128)
    singular_values=S,
    energy_frac=energy_frac,
    energy_cum=energy_cum,
    # 时间系数（POD系数）
    coefficients=np.diag(S) @ Vt,     # shape: (13, 13)
    # 工况信息
    yaw_angles=df["yaw_1"].values,
    n_snapshots=len(df),
)

print(f"\n✅ POD结果已保存至 pod_results/pod_data.npz")
print(f"\n重构误差验证（用前k个模态重构）：")

for k in [1, 2, 3, 5, 10, 13]:
    X_recon = x_mean + U[:, :k] @ np.diag(S[:k]) @ Vt[:k, :]
    error   = np.mean((X - X_recon) ** 2) / np.mean(X ** 2) * 100
    print(f"  前 {k:2d} 个模态：相对误差 = {error:.4f}%")