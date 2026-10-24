"""Extract the PINN dataset from a Fluent k-eps/k-omega MRF run (same pipeline both times)."""
import sys, os, json
import numpy as np
sys.path.insert(0, r'F:\NREL 5MW\_tools\pylibs')
import h5py

CAS, DAT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
HUB_Y, R, VINF, OMEGA = 81.333, 63.5, 9.0, 1.070
AX = np.array([0.0, 0.096225, 0.99536]); AX /= np.linalg.norm(AX)
Z_ROT = [8.006, -369.994, -747.994]
os.makedirs(OUT, exist_ok=True)

print('reading mesh ...', flush=True)
with h5py.File(CAS, 'r', locking=False) as f:
    coords = f['meshes/1/nodes/coords/663'][:]
    nn = f['meshes/1/faces/nodes/1/nnodes'][:]
    fnodes = f['meshes/1/faces/nodes/1/nodes'][:].astype(np.int64) - 1
    c0 = f['meshes/1/faces/c0/1'][:].astype(np.int64)
    c1 = np.concatenate([f['meshes/1/faces/c1/1'][:], f['meshes/1/faces/c1/2'][:]]).astype(np.int64)
    fz = f['meshes/1/faces/zoneTopology']
    fnames = [s.decode() for s in fz['name'][:]][0].split(';')
    fmin = fz['minId'][:]; fmax = fz['maxId'][:]
    cz = f['meshes/1/cells/zoneTopology']
    cnames = [s.decode() for s in cz['name'][:]][0].split(';')
    cmin = cz['minId'][:]; cmax = cz['maxId'][:]
F = nn.size
offs = np.concatenate([[0], np.cumsum(nn.astype(np.int64))[:-1]])
fcent = np.add.reduceat(coords[fnodes], offs, axis=0) / nn[:, None]
c1full = np.zeros(F, dtype=np.int64); c1full[:c1.size] = c1
mask = c1full > 0
ncell = int(max(c0.max(), c1full.max())) + 1
cids = np.concatenate([c0, c1full[mask]])
fcs = np.concatenate([fcent, fcent[mask]])
cnt = np.bincount(cids, minlength=ncell).astype(np.float64)
ccent = np.zeros((ncell, 3))
for d in range(3):
    ccent[:, d] = np.bincount(cids, weights=fcs[:, d], minlength=ncell)
ccent /= np.maximum(cnt[:, None], 1)

print('reading fields ...', flush=True)
with h5py.File(DAT, 'r', locking=False) as f:
    g = f['results/1/phase-1/cells']
    U = g['SV_U/1'][:]; V = g['SV_V/1'][:]; W = g['SV_W/1'][:]
    K = g['SV_K/1'][:]
    eps = g['SV_D/1'][:] if 'SV_D' in g else None
    om = g['SV_O/1'][:] if 'SV_O' in g else None
    P_face = f['results/1/phase-1/faces/SV_P/1'][:]
n = min(U.size, ccent.shape[0])
ccent, U, V, W, K = ccent[:n], U[:n], V[:n], W[:n], K[:n]
aux = (eps[:n] if eps is not None else om[:n])
aux_name = 'epsilon' if eps is not None else 'omega'

valid = np.zeros(n, dtype=bool)
for nm, lo, hi in zip(cnames, cmin, cmax):
    print(f'  cell zone {nm}: {lo}-{hi}', flush=True)
    valid[int(lo) - 1:int(hi)] = True
# drop zones with (almost) no flow
u_test = U * AX[0] + V * AX[1] + W * AX[2]
for nm, lo, hi in zip(cnames, cmin, cmax):
    sl = slice(int(lo) - 1, int(hi))
    if np.abs(u_test[sl]).max() < 1e-9:
        valid[sl] = False
        print('  drop zero-velocity zone', nm, flush=True)

ccent, U, V, W, K, aux, u_test = (a[valid] for a in (ccent, U, V, W, K, aux, u_test))
n = int(valid.sum())
Uax = U * AX[0] + V * AX[1] + W * AX[2]
Uf = -Uax                      # forward-positive convention
mag = np.sqrt(U * U + V * V + W * W)
TI = np.where(mag > 1e-6, np.sqrt(np.maximum(2 * K / 3, 0)) / np.maximum(mag, 1e-9), 0.0)
r_xy = np.sqrt(ccent[:, 0] ** 2 + (ccent[:, 1] - HUB_Y) ** 2)
print('flow cells', n, flush=True)

# (1) centreline
zs = np.arange(160.0, -1700.0, -2.0)
order = np.argsort(ccent[:, 2]); zc = ccent[order, 2]; r_all = r_xy[order]
rows = []
for z in zs:
    i0 = np.searchsorted(zc, z - 5.0); i1 = np.searchsorted(zc, z + 5.0)
    m = r_all[i0:i1] < 10.0
    if not m.any():
        continue
    idx = order[i0:i1][m]
    rows.append([z, float(Uf[idx].mean()), float(mag[idx].mean()), float(TI[idx].mean()),
                 float(K[idx].mean()), float(aux[idx].mean()), int(idx.size)])
arr = np.array(rows)
us = np.convolve(np.pad(arr[:, 1], (4, 4), mode='edge'), np.ones(9) / 9.0, mode='valid')
arr = np.column_stack([arr[:, 0], arr[:, 1], us, arr[:, 2], arr[:, 3], arr[:, 4], arr[:, 5], arr[:, 6]])
np.savetxt(os.path.join(OUT, 'wake_centerline.csv'), arr, delimiter=',',
           header=f'z_m,U_forward_mean_m_s,U_forward_smooth_m_s,U_mag_mean_m_s,TI_mean,k_mean_m2_s2,{aux_name}_mean,n_cells',
           comments='')
print('centerline', arr.shape[0], flush=True)

# (2) rotor planes
summary = []
for k, z0 in enumerate(Z_ROT, start=1):
    recs = []
    for r in np.arange(10.0, R, 3.0):
        for th in np.arange(0, 2 * np.pi, np.pi / 18):
            x = r * np.cos(th); y = HUB_Y + r * np.sin(th)
            d2 = (ccent[:, 0] - x) ** 2 + (ccent[:, 1] - y) ** 2 + (ccent[:, 2] - z0) ** 2
            i = int(np.argmin(d2))
            recs.append([x, y, z0, r, th, Uf[i], mag[i], TI[i]])
    recs = np.array(recs)
    np.savetxt(os.path.join(OUT, f'rotor{k}_plane.csv'), recs, delimiter=',',
               header='x_m,y_m,z_m,r_m,theta_rad,U_forward_m_s,U_mag_m_s,TI', comments='')
    w = recs[:, 3]
    ud = float(np.sum(recs[:, 5] * w) / np.sum(w))
    summary.append([k, z0, ud, float(np.mean(recs[:, 7]))])
    print(f'  rotor{k}: u_disk = {ud:.3f} m/s', flush=True)

# (3) wake profiles
prof = []
for k, z0 in enumerate(Z_ROT, start=1):
    for d in (1, 2, 3, 4, 6, 8):
        zs2 = z0 - 2 * R * d
        for dy in np.arange(-2 * R, 2 * R + 1, 2.0):
            y = HUB_Y + dy
            d2 = (ccent[:, 0]) ** 2 + (ccent[:, 1] - y) ** 2 + (ccent[:, 2] - zs2) ** 2
            i = int(np.argmin(d2))
            prof.append([k, d, zs2, dy, Uf[i], mag[i], TI[i]])
np.savetxt(os.path.join(OUT, 'wake_profiles.csv'), np.array(prof), delimiter=',',
           header='turbine,dist_D,z_m,dy_m,U_forward_m_s,U_mag_m_s,TI', comments='')

# (4) thrust by pressure integration
print('integrating thrust ...', flush=True)
AXv = AX
res = {}
for nm, lo, hi in zip(fnames, fmin, fmax):
    if 'shadow' in nm or 'internal' in nm or 'interior' in nm or nm in ('wall', 'inlet', 'outlet'):
        continue
    i0, i1 = int(lo) - 1, int(hi)
    seg = nn[i0:i1].astype(np.int64)
    st = offs[i0:i1]
    tot = seg.sum()
    idx = np.repeat(st - np.concatenate([[0], np.cumsum(seg)[:-1]]), seg) + np.arange(tot)
    nodes = fnodes[idx]
    pos = np.arange(tot)
    face_of = np.repeat(np.arange(seg.size), seg)
    first = np.concatenate([[0], np.cumsum(seg)[:-1]])
    last = first + seg - 1
    nxt = pos + 1
    wrap = pos == last[face_of]
    nxt[wrap] = first[face_of[wrap]]
    avec = 0.5 * np.add.reduceat(np.cross(coords[nodes], coords[nodes[nxt]]), first, axis=0)
    p = P_face[i0:i1]
    Fw = -(p[:, None] * avec).sum(axis=0)
    res[nm] = Fw

groups = {'T1': ['blade1', 'blade1-51'], 'T2': ['blade2', 'blade2-52'], 'T3': ['blade3', 'blade3-53']}
power = []
for tag, zs_ in groups.items():
    tot = np.zeros(3)
    for z in zs_:
        if z in res:
            tot += res[z]
    k = int(tag[1])
    T = float(np.dot(tot, AXv))     # negative downstream; magnitude below
    ud = summary[k - 1][2]
    P = abs(T) * ud
    power.append([k, Z_ROT[k - 1], ud, abs(T), P, P / 1e6, summary[k - 1][3]])
    print(f'  {tag}: T = {abs(T)/1e3:.1f} kN, P = {P/1e6:.2f} MW', flush=True)
np.savetxt(os.path.join(OUT, 'power_thrust.csv'), np.array(power), delimiter=',',
           header='turbine,z_rotor_m,u_disk_forward_m_s,thrust_N,power_W,power_MW,TI_mean', comments='')

with open(os.path.join(OUT, 'case_meta.json'), 'w', encoding='utf-8') as f:
    json.dump(dict(case=os.path.basename(CAS), data=os.path.basename(DAT),
                   turbulence=aux_name, inlet_velocity_m_s=VINF, R_m=R, omega_rad_s=OMEGA,
                   turbine_z_m=Z_ROT, axis=list(AX), hub_y=HUB_Y,
                   cells=int(ncell), flow_cells=int(n),
                   convention='U_forward = -U_axial'), f, ensure_ascii=False, indent=1)
print('done ->', OUT, flush=True)
