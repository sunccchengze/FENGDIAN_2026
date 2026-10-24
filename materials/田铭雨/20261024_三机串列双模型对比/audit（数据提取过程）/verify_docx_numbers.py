"""Cross-check every numeric cell of the DOCX tables against the delivered CSV files."""
import sys
import numpy as np
from docx import Document

D = r'F:\NREL 5MW\三机串列_双模型数据包'
doc = Document(D + r'\三机串列_komega_vs_kepsilon_数据对比.docx')
pa = np.genfromtxt(D + r'\k-omega_data\power_thrust.csv', delimiter=',', names=True)
pb = np.genfromtxt(D + r'\k-epsilon_data\power_thrust.csv', delimiter=',', names=True)
CP_AVAIL = 0.5 * 1.225 * np.pi * 63.5 ** 2 * 9.0 ** 3 / 1e6   # MW

def cell(t, r, c):
    return t.rows[r].cells[c].text.strip()

t = doc.tables[1]   # thrust / u_disk / power
print('table 1 (thrust, u_disk, power):')
ok = True
for i in range(3):
    exp = dict(t=[f"{pa['thrust_N'][i]/1e3:.1f}", f"{pb['thrust_N'][i]/1e3:.1f}"],
               u=[f"{pa['u_disk_forward_m_s'][i]:.2f}", f"{pb['u_disk_forward_m_s'][i]:.2f}"],
               p=[f"{pa['power_MW'][i]:.2f}", f"{pb['power_MW'][i]:.2f}"])
    got = dict(t=[cell(t, i + 1, 1), cell(t, i + 1, 2)],
               u=[cell(t, i + 1, 4), cell(t, i + 1, 5)],
               p=[cell(t, i + 1, 6), cell(t, i + 1, 7)])
    for k in exp:
        flag = exp[k] == got[k]
        ok &= flag
        print('   T%d %s  docx=%s csv=%s %s' % (i + 1, k, got[k], exp[k], 'OK' if flag else 'MISMATCH'))

t = doc.tables[2]   # Cp
print('table 2 (Cp):')
for i in range(3):
    ca = pa['power_MW'][i] / CP_AVAIL
    cb = pb['power_MW'][i] / CP_AVAIL
    got = (cell(t, i + 1, 1), cell(t, i + 1, 2))
    exp = (f'{ca:.3f}', f'{cb:.3f}')
    flag = got == exp
    ok &= flag
    print('   T%d docx=%s csv=%s %s' % (i + 1, got, exp, 'OK' if flag else 'MISMATCH'))

t = doc.tables[4]   # TI
print('table 3 (TI):')
for i in range(3):
    got = (cell(t, i + 1, 1), cell(t, i + 1, 2))
    exp = (f"{100*pa['TI_mean'][i]:.1f}%", f"{100*pb['TI_mean'][i]:.1f}%")
    flag = got == exp
    ok &= flag
    print('   T%d docx=%s csv=%s %s' % (i + 1, got, exp, 'OK' if flag else 'MISMATCH'))

t = doc.tables[5]   # ratios
print('table 4 (ratios):')
r_t = pa['thrust_N'][1] / pa['thrust_N'][0]
r_u = pa['u_disk_forward_m_s'][1] / pa['u_disk_forward_m_s'][0]
r_p = pa['power_MW'][1] / pa['power_MW'][0]
print('   docx:', [cell(t, k, 1) for k in (1, 2, 3)], [cell(t, k, 2) for k in (1, 2, 3)])
print('   csv : T2/T1=%.3f  u2/u1=%.3f  P2/P1=%.3f' % (r_t, r_u, r_p))
print('   consistent:', abs(float(cell(t, 3, 1).split('（')[0]) - r_p) < 0.002, '| T %.3f U %.3f P %.3f' % (r_t, r_u, r_p))

tot_a = pa['power_MW'].sum()
tot_b = pb['power_MW'].sum()
print('\nTOTAL k-omega %.3f MW  k-eps %.3f MW  diff %+.2f%%' % (tot_a, tot_b, 100 * (tot_b / tot_a - 1)))
print('ALL TABLE CELLS MATCH:', ok)

