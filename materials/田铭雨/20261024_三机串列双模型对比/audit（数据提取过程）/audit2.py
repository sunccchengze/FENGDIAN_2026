"""Audit v2: recompute thrust / u_disk from raw files, compare with CSV, Fluent reports and the DOCX."""
import sys, os
import numpy as np
sys.path.insert(0, r'F:\NREL 5MW\_tools\pylibs')
import h5py

HUB_Y, R = 81.333, 63.5
AX = np.array([0.0, 0.096225, 0.99536]); AX /= np.linalg.norm(AX)
Z_ROT = [8.006, -369.994, -747.994]
CASES = {
    'k-omega': dict(cas=r'F:\NREL 5MW\fangji-2_files\dp0\FLTG\Fluent\FLTG-2.cas.h5',
                    dat=r'F:\NREL 5MW\fangji-2_files\dp0\FLTG\Fluent\FLTG-2-04606.dat.h5',
                    csv=r'F:\NREL 5MW\三机串列_双模型数据包\k-omega_data',
                    fl=[]),
    'k-eps':   dict(cas=r'F:\NREL 5MW\fangji-2_files\dp0\FLTG-2\Fluent\FLTG-1.cas.h5',
                    dat=r'F:\NREL 5MW\fangji-2_files\dp0\FLTG-2\Fluent\FLTG-1-04800.dat.h5',
                    csv=r'F:\NREL 5MW\三机串列_双模型数据包\k-epsilon_data',
                    fl=[r'F:\NREL 5MW\fangji-2_files\dp0\FLTG-2\Fluent\report-file-0.out',
                        r'F:\NREL 5MW\fangji-2_files\dp0\FLTG-2\Fluent\report-file-2.out',
                        r'F:\NREL 5MW\fangji-2_files\dp0\FLTG-2\Fluent\report-def-3-rfile.out']),
}

for tag, C in CASES.items():
    print('=' * 78)
    print(tag)
    with h5py.File(C['cas'], 'r', locking=False) as f:
        coords = f['meshes/1/nodes/coords/663'][:]
        nn = f['meshes/1/faces/nodes/1/nnodes'][:]
        fn = f['meshes/1/faces/nodes/1/nodes'][:].astype(np.int64) - 1
        c0 = f['meshes/1/faces/c0/1'][:].astype(np.int64)
        c1 = np.concatenate([f['meshes/1/faces/c1/1'][:], f['meshes/1/faces/c1/2'][:]]).astype(np.int64)
        fz = f['meshes/1/faces/zoneTopology']
        fnames = [s.decode() for s in fz['name'][:]][0].split(';')
        fmin, fmax = fz['minId'][:], fz['maxId'][:]
        cz = f['meshes/1/cells/zoneTopology']
        cnames = [s.decode() for s in cz['name'][:]][0].split(';')
        cmin, cmax = cz['minId'][:], cz['maxId'][:]
    F = nn.size
    offs = np.concatenate([[0], np.cumsum(nn.astype(np.int64))[:-1]])
    fcent = np.add.reduceat(coords[fn], offs, axis=0) / nn[:, None]
    c1full = np.zeros(F, np.int64); c1full[:c1.size] = c1
    m = c1full > 0
    ncell = int(max(c0.max(), c1full.max())) + 1
    cids = np.concatenate([c0, c1full[m]])
    fcs = np.concatenate([fcent, fcent[m]])
    cnt = np.bincount(cids, minlength=ncell).astype(float)
    cc = np.zeros((ncell, 3))
    for d in range(3):
        cc[:, d] = np.bincount(cids, weights=fcs[:, d], minlength=ncell)
    cc /= np.maximum(cnt[:, None], 1)
    with h5py.File(C['dat'], 'r', locking=False) as f:
        g = f['results/1/phase-1/cells']
        U = g['SV_U/1'][:]; V = g['SV_V/1'][:]; W = g['SV_W/1'][:]
        Pf = f['results/1/phase-1/faces/SV_P/1'][:]
    n = min(U.size, cc.shape[0]); cc, U, V, W = cc[:n], U[:n], V[:n], W[:n]
    Uax = U * AX[0] + V * AX[1] + W * AX[2]

    flow = np.ones(n, bool)
    for nm, lo, hi in zip(cnames, cmin, cmax):
        sl = slice(int(lo) - 1, int(hi))
        if np.abs(Uax[sl]).max() < 1e-9:
            flow[sl] = False
    print('  cells %d, flowing %d (%.1f%%), zero-velocity %.1f%%'
          % (n, flow.sum(), 100 * flow.mean(), 100 * (~flow).mean()))

    # ---- thrust (fixed indexing: nodes[nxt]) ----
    Fz = {}
    for nm, lo, hi in zip(fnames, fmin, fmax):
        if 'shadow' in nm or 'internal' in nm or 'interior' in nm or nm in ('wall', 'inlet', 'outlet'):
            continue
        i0, i1 = int(lo) - 1, int(hi)
        seg = nn[i0:i1].astype(np.int64); st = int(offs[i0]); tot = seg.sum()
        pos = np.arange(tot)
        nodes = fn[st:st + tot]
        fo = np.repeat(np.arange(seg.size), seg)
        first = np.concatenate([[0], np.cumsum(seg)[:-1]])
        last = first + seg - 1
        nxt = pos + 1
        wr = pos == last[fo]
        nxt[wr] = first[fo[wr]]
        avec = 0.5 * np.add.reduceat(np.cross(coords[nodes], coords[nodes[nxt]]), first, axis=0)
        p = Pf[i0:i1]
        Fz[nm] = (-(p[:, None] * avec).sum(axis=0), np.linalg.norm(avec, axis=1).sum())
    groups = {'T1': ['blade1', 'blade1-51'], 'T2': ['blade2', 'blade2-52'], 'T3': ['blade3', 'blade3-53']}
    thrust, area = {}, {}
    for k, zs in groups.items():
        tot = np.zeros(3); ar = 0.0
        for z in zs:
            if z in Fz:
                tot += Fz[z][0]; ar += Fz[z][1]
        thrust[k] = abs(float(np.dot(tot, AX))); area[k] = ar

    # ---- u_disk: polar grid over flow cells only ----
    cf = cc[flow]; uf = -Uax[flow]
    ud = {}
    for k, z0 in zip((1, 2, 3), Z_ROT):
        recs = []
        for r in np.arange(10.0, R, 3.0):
            for th in np.arange(0, 2 * np.pi, np.pi / 18):
                x = r * np.cos(th); y = HUB_Y + r * np.sin(th)
                d2 = (cf[:, 0] - x) ** 2 + (cf[:, 1] - y) ** 2 + (cf[:, 2] - z0) ** 2
                recs.append((r, uf[int(np.argmin(d2))]))
        recs = np.array(recs)
        ud[k] = float(np.sum(recs[:, 1] * recs[:, 0]) / np.sum(recs[:, 0]))

    # ---- Fluent's own report values ----
    fl = []
    for p in C['fl']:
        a = np.genfromtxt(p, skip_header=3)
        fl.append(a[-1, 1])
    csv = np.genfromtxt(os.path.join(C['csv'], 'power_thrust.csv'), delimiter=',', names=True)
    print('  %-4s %10s %10s %10s | %8s %8s | %8s %8s' %
          ('', 'T_audit', 'T_CSV', 'Fluent', 'u_audit', 'u_CSV', 'P_audit', 'P_CSV'))
    for i, k in enumerate(('T1', 'T2', 'T3')):
        fv = fl[i] if i < len(fl) else float('nan')
        Pa = thrust[k] * ud[i + 1] / 1e6
        print('  %-4s %9.1f %9.1f %9.1f | %8.3f %8.3f | %8.3f %8.3f  (area %.0f m2)'
              % (k, thrust[k] / 1e3, csv['thrust_N'][i] / 1e3, fv / 1e3,
                 ud[i + 1], csv['u_disk_forward_m_s'][i], Pa, csv['power_MW'][i], area[k]))
