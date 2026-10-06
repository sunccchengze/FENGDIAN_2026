// ================================================================
// L4 物理内核 · FLORIS 4.6.6 GCH 默认配置的 TypeScript 移植
// ----------------------------------------------------------------
// 移植对象（源码行级对照，FLORIS 4.6.6 /usr 安装版 core/）：
//   · sequential_solver        core/solver.py
//   · GaussVelocityDeficit     core/wake_velocity/gauss.py
//   · GaussVelocityDeflection  core/wake_deflection/gauss.py
//   · CrespoHernandez          core/wake_turbulence/crespo_hernandez.py
//   · SOSFS                    core/wake_combination/sosfs.py
//   · CosineLossTurbine        core/turbine/operation_models.py（功率/推力/诱导链）
//   · TurbineGrid(3×3,±D/4)    core/grid.py（radius_ratio=0.5, cubic-mean）
//   · rotate_coordinates_rel_west utilities.py（wind_delta=(wd−270) mod 360）
//
// 配置 = FlorisModel('defaults')（GCH）：
//   velocity=gauss(alpha .58 beta .077 ka .38 kb .004)
//   deflection=gauss(同参) + secondary_steering + yaw_added_recovery
//   transverse velocities（6 涡 + 地面镜像, eps=0.2D, κ=0.41, lmda=D/8）
//   turbulence=crespo_hernandez(.1/.5/.8/−.32)  combination=sosfs
//   风场 shear=0.12（参考高=轮毂 90m）, veer=0, rho=1.225
//
// V&V：scripts/selftest.mts 的 G 节对 docs/research/oracle/
//   floris_gch_oracle_v1.json（FLORIS 4.6.6 实算）逐项对拍。
// 本文件为纯函数、无副作用、无依赖 —— 渲染层与控制层共用同一真值。
// ================================================================

import { TURBINE, powerTableKw, ctTable, effectiveVelocity } from './florisTable.ts'

// ---- GCH 参数（default_inputs.yaml 原文）----
export const GCH = {
  alpha: 0.58,
  beta: 0.077,
  ka: 0.38,
  kb: 0.004,
  ch: { initial: 0.1, constant: 0.5, ai: 0.8, downstream: -0.32 },
  shear: 0.12,
  veer: 0.0,
  rho: 1.225,
  gchGain: 2, // yaw_added_recovery 增益（solver.py 硬编码）
  epsGain: 0.2, // 涡核尺度系数（gauss.py 硬编码）
  numEps: 0.001, // BaseModel.NUM_EPS
} as const

const DEG = Math.PI / 180
const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v)

export interface GCHWind {
  /** 轮毂高参考风速 (m/s) */
  uInf: number
  /** 来风方位（气象口径：风 FROM 的方向，°） */
  fromDeg: number
  /** 环境湍流强度 */
  ti: number
}

export interface TurbineEval {
  /** 转子立方平均风速 (m/s) */
  uAvg: number
  /** 有效风速（含偏航/密度修正，查表口径） */
  uEff: number
  /** 推力系数（有效风速处表值） */
  ct: number
  /** 轴向诱导因子 */
  aI: number
  /** 该机组处湍流强度（含上游尾流诱发，转子平均） */
  ti: number
  /** 并网功率 (kW) */
  powerKw: number
  /** 有效偏航（含二次导向 wake_added_yaw，°）——场采样 sampleHubPlane 用 */
  effYaw: number
}

export interface GCHResult {
  /** 原始布局顺序的逐机结果 */
  turbines: TurbineEval[]
  totalKw: number
}

/**
 * 内部结构：已求解机组状态（用于场点采样 sampleCrossPlane）
 */
interface SolvedTurbineState {
  order: number[]
  unsort: number[]
  xr: number[]
  yr: number[]
  uAvg: number[]
  rawCt: number[]
  ctI: number[]
  aI: number[]
  effYaw: number[]
  effYawViz: number[]
  tiTurbines: Float64Array
  uInfMean: number
  velTop: number
  velBot: number
  eps: number
  eps2: number
}

/**
 * 求解机组转子网格稳态
 */
function solveTurbineGrid(
  xFloris: number[],
  yFloris: number[],
  wind: GCHWind,
  yawDeg: number[],
) {
  const n = xFloris.length
  const D = TURBINE.D
  const HH = TURBINE.HH
  const { alpha, beta, ka, kb, shear, gchGain, epsGain, numEps } = GCH

  // ---- 坐标旋转（流向 +x'）----
  const delta = ((((wind.fromDeg - 270) % 360) + 360) % 360) * DEG
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (let i = 0; i < n; i++) {
    if (xFloris[i] < minX) minX = xFloris[i]
    if (xFloris[i] > maxX) maxX = xFloris[i]
    if (yFloris[i] < minY) minY = yFloris[i]
    if (yFloris[i] > maxY) maxY = yFloris[i]
  }
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const cosD = Math.cos(delta), sinD = Math.sin(delta)
  const xr = new Array<number>(n), yr = new Array<number>(n)
  for (let i = 0; i < n; i++) {
    const ox = xFloris[i] - cx, oy = yFloris[i] - cy
    xr[i] = ox * cosD - oy * sinD + cx
    yr[i] = ox * sinD + oy * cosD + cy
  }

  // ---- 排序（上游→下游，稳定）----
  const order = Array.from({ length: n }, (_, i) => i)
  order.sort((a, b) => xr[a] - xr[b] || a - b)
  const unsort = new Array<number>(n)
  for (let i = 0; i < n; i++) unsort[order[i]] = i

  // ---- 3×3 转子网格（±D/4，cubic-mean 口径）----
  // FLORIS grid.py: index 2 是 y [-D/4, 0, D/4]，index 3 是 z [-D/4, 0, D/4]
  const NG = 9
  const off = [-D / 4, 0, D / 4]
  const px = new Float64Array(n * NG)
  const py = new Float64Array(n * NG)
  const pz = new Float64Array(n * NG)
  for (let si = 0; si < n; si++) {
    const t = order[si]
    for (let g = 0; g < NG; g++) {
      const k = si * NG + g
      px[k] = xr[t]
      py[k] = yr[t] + off[(g / 3) | 0]
      pz[k] = HH + off[g % 3]
    }
  }

  // ---- 初始流场（剪切廓线，参考高=轮毂）----
  const uInit = new Float64Array(n * NG)
  const dudz = new Float64Array(n * NG)
  const refH = HH
  let uInitSum = 0
  for (let p = 0; p < n * NG; p++) {
    const z = pz[p]
    uInit[p] = wind.uInf * Math.pow(z / refH, shear)
    dudz[p] = wind.uInf * shear * Math.pow(1 / refH, shear) * Math.pow(z, shear - 1)
    uInitSum += uInit[p]
  }
  const uInfMean = uInitSum / (n * NG)

  // ---- 状态场 ----
  const u = uInit.slice()
  const v = new Float64Array(n * NG)
  const w = new Float64Array(n * NG)
  const wake = new Float64Array(n * NG)
  const tiTurbines = new Float64Array(n).fill(wind.ti)
  const defl = new Float64Array(n * NG)
  const deficit = new Float64Array(n * NG)
  const vWake = new Float64Array(n * NG)
  const wWake = new Float64Array(n * NG)

  const eps = epsGain * D
  const eps2 = eps * eps
  const velTop = Math.pow((HH + D / 2) / HH, shear)
  const velBot = Math.pow((HH - D / 2) / HH, shear)

  const uAvgArr = new Array<number>(n)
  const rawCtArr = new Array<number>(n)
  const ctIArr = new Array<number>(n)
  const aIArr = new Array<number>(n)
  const effYawArr = new Array<number>(n)

  for (let si = 0; si < n; si++) {
    const t = order[si]
    const yi = yr[t]
    const xi = xr[t]
    const yawT = yawDeg[t]
    const base = si * NG

    // ---- 机组 i 当前状态 ----
    let u3 = 0
    let vSum = 0
    for (let g = 0; g < NG; g++) {
      const k = base + g
      u3 += u[k] * u[k] * u[k]
      vSum += v[k]
    }
    const uAvgI = Math.cbrt(u3 / NG)
    // FLORIS CosineLossTurbine: Ct = rawCt(uAvg) * cos(yaw) * cos(tilt)/cos(refTilt)
    const rawCtI = uAvgI > 0 ? Math.min(0.9999, Math.max(0.0001, ctTable(uAvgI))) : 0.0001
    const misI = Math.cos(yawT * DEG)
    const ctI = rawCtI * misI
    // FLORIS CosineLossTurbine: aI = 0.5/mis * (1 - sqrt(1 - ct*mis))
    const aI = (0.5 / misI) * (1 - Math.sqrt(Math.max(0, 1 - ctI * misI)))
    const tiI = tiTurbines[si]
    const avgV = vSum / NG

    uAvgArr[si] = uAvgI
    rawCtArr[si] = rawCtI
    ctIArr[si] = ctI
    aIArr[si] = aI

    // ---- 二次导向：wake_added_yaw ----
    let effYaw = yawT
    if (uAvgI > 0 && ctI > 0) {
      const gTop = (Math.PI / 8) * D * velTop * uInfMean * ctI
      const gBot = -(Math.PI / 8) * D * velBot * uInfMean * ctI
      const gRot = 0.25 * 2 * Math.PI * D * (aI - aI * aI) * uAvgI / TURBINE.TSR
      const vz = [HH + D / 2, HH - D / 2, HH]
      const gk = [gTop, gBot, gRot]
      const vMeans = [0, 0, 0]
      for (let g = 0; g < NG; g++) {
        const k = base + g
        const yRel = py[k] - yi + numEps
        for (let q = 0; q < 3; q++) {
          const zRel = pz[k] - vz[q] + numEps
          const r2 = yRel * yRel + zRel * zRel
          const core = 1 - Math.exp(-r2 / eps2)
          vMeans[q] += (gk[q] * zRel) / (2 * Math.PI * r2) * core
        }
      }
      for (let q = 0; q < 3; q++) vMeans[q] /= NG
      let val = (2 * (avgV - vMeans[2])) / (vMeans[0] + vMeans[1])
      if (val < -1) val = -1
      if (val > 1) val = 1
      effYaw = yawT + (0.5 * Math.asin(val)) / DEG
    }
    effYawArr[si] = effYaw

    // ---- 偏折场（gauss，作用于全部网格点）----
    const yawM = -effYaw
    const yawMr = yawM * DEG
    const cosYm = Math.cos(yawMr)
    const s1ct = Math.sqrt(1 - ctI)
    const s1ctCos = Math.sqrt(Math.max(0, 1 - ctI * cosYm))
    const x0 = xi + (D * cosYm * (1 + s1ctCos)) / (Math.SQRT2 * (4 * alpha * tiI + 2 * beta * (1 - s1ct)))
    const kyD = ka * tiI + kb
    const thetaC0 = (0.3 * yawMr / cosYm) * (1 - s1ctCos)
    const delta0 = Math.tan(thetaC0) * (x0 - xi)
    const eA = Math.exp(1 / 12), eB = Math.exp(1 / 3)
    for (let p = 0; p < n * NG; p++) {
      const up = uInit[p]
      const uR = (up * ctI * cosYm) / (2 * (1 - s1ctCos))
      const u0 = up * s1ct
      const sz0 = (D / 2) * Math.sqrt(uR / (up + u0))
      const sy0 = sz0 * cosYm
      const C0 = 1 - u0 / up
      const M0 = C0 * (2 - C0)
      const E0 = C0 * C0 - 3 * eA * C0 + 3 * eB
      const dNear = ((px[p] - xi) / (x0 - xi)) * delta0 * ((px[p] >= xi) && (px[p] <= x0) ? 1 : 0)
      let dFar = 0
      if (px[p] > x0) {
        const sy = kyD * (px[p] - x0) + sy0
        const sz = kyD * (px[p] - x0) + sz0
        const mt = Math.sqrt((sy * sz) / (sy0 * sz0))
        const ms = Math.sqrt(M0)
        const lnNum = (1.6 + ms) * (1.6 * mt - ms)
        const lnDen = (1.6 - ms) * (1.6 * mt + ms)
        const mid = (thetaC0 * E0 / 5.2) * Math.sqrt((sy0 * sz0) / (kyD * kyD * M0)) * Math.log(lnNum / lnDen)
        dFar = delta0 + mid
      }
      defl[p] = dNear + dFar
    }

    // ---- 横向速度（6 涡 + 地面镜像，全部网格点）----
    const yawTr = yawT * DEG
    const sinc = Math.sin(yawTr) * Math.cos(yawTr)
    const gTop2 = sinc * (Math.PI / 8) * D * velTop * uInfMean * ctI
    const gBot2 = -sinc * (Math.PI / 8) * D * velBot * uInfMean * ctI
    const gRot2 = uAvgI > 0 ? 0.25 * 2 * Math.PI * D * (aI - aI * aI) * uAvgI / TURBINE.TSR : 0
    for (let p = 0; p < n * NG; p++) {
      const dx = px[p] - xi
      if (dx < 0) {
        vWake[p] = 0
        wWake[p] = 0
        continue
      }
      const z = pz[p]
      const lm = (0.41 * z) / (1 + (0.41 * z) / (D / 8))
      const nu = lm * lm * Math.abs(dudz[p])
      const decay = eps2 / (4 * nu * (dx / uInfMean) + eps2)
      const yLoc = py[p] - yi + numEps
      const vorts = [
        gTop2, z - (HH + D / 2) + numEps, 1,
        gBot2, z - (HH - D / 2) + numEps, 1,
        gRot2, z - HH + numEps, 1,
        gTop2, z + (HH + D / 2) + numEps, -1,
        gBot2, z + (HH - D / 2) + numEps, -1,
        gRot2, z + HH + numEps, -1,
      ]
      let vv = 0, ww = 0
      for (let q = 0; q < 6; q++) {
        const G = vorts[q * 3], zRel = vorts[q * 3 + 1], sgn = vorts[q * 3 + 2]
        const r2 = yLoc * yLoc + zRel * zRel
        const core = 1 - Math.exp(-r2 / eps2)
        const f = (G * core * decay) / (2 * Math.PI * r2)
        vv += sgn * f * zRel
        ww += -sgn * f * yLoc
      }
      vWake[p] = vv
      wWake[p] = ww > 0 ? ww : 0
    }

    // ---- 偏航附加湍流恢复（yaw_added_recovery, gch_gain=2）----
    let tiNew = tiI
    if (uAvgI > 0) {
      let vw = 0, wv = 0
      for (let g = 0; g < NG; g++) {
        const k = base + g
        vw += v[k] + vWake[k]
        wv += w[k] + wWake[k]
      }
      const vTerm = vw / NG
      const wTerm = wv / NG
      const kTke = (uAvgI * tiI) * (uAvgI * tiI) / (2 / 3)
      const uTerm = Math.sqrt(2 * kTke)
      const kTotal = 0.5 * (uTerm * uTerm + vTerm * vTerm + wTerm * wTerm)
      const iTot = Math.sqrt((2 / 3) * kTotal) / uAvgI
      tiNew = tiI + gchGain * (iTot - tiI)
    }
    tiTurbines[si] = tiNew

    // ---- 速度亏损（gauss，近/远场，全部网格点）----
    const yawV = -yawT
    const yawVr = yawV * DEG
    const cosYv = Math.cos(yawVr)
    const x0v = xi + (D * cosYv * (1 + s1ct)) / (Math.SQRT2 * (4 * alpha * tiNew + 2 * beta * (1 - s1ct)))
    const kyV = ka * tiNew + kb
    for (let p = 0; p < n * NG; p++) {
      const up = uInit[p]
      let dfc = 0
      if (ctI > 0 && up > 0) {
        const uR = (up * ctI) / (2 * (1 - s1ct))
        const u0 = up * s1ct
        const sz0 = (D / 2) * Math.sqrt(uR / (up + u0))
        const sy0 = sz0 * cosYv
        const xP = px[p]
        const dY = py[p] - yi - defl[p]
        const dZ = pz[p] - HH
        if (xP > xi + 0.1 && xP < x0v) {
          const rampUp = (xP - xi) / (x0v - xi)
          const rampDown = (x0v - xP) / (x0v - xi)
          const sy = (rampDown * 0.501 * D * Math.sqrt(ctI / 2) + rampUp * sy0) * (xP >= xi ? 1 : 0) + (xP < xi ? D * 0.5 : 0)
          const sz = (rampDown * 0.501 * D * Math.sqrt(ctI / 2) + rampUp * sz0) * (xP >= xi ? 1 : 0) + (xP < xi ? D * 0.5 : 0)
          const r2 = (dY * dY) / (2 * sy * sy) + (dZ * dZ) / (2 * sz * sz)
          const Cc = 1 - Math.sqrt(clamp01(1 - (ctI * cosYv) / ((8 * sy * sz) / (D * D))))
          dfc = Cc * Math.exp(-r2)
        } else if (xP >= x0v) {
          const sy = kyV * (xP - x0v) + sy0
          const sz = kyV * (xP - x0v) + sz0
          const r2 = (dY * dY) / (2 * sy * sy) + (dZ * dZ) / (2 * sz * sz)
          const Cc = 1 - Math.sqrt(clamp01(1 - (ctI * cosYv) / ((8 * sy * sz) / (D * D))))
          dfc = Cc * Math.exp(-r2)
        }
      }
      deficit[p] = dfc
    }

    // ---- 组合（SOSFS：亏损平方和开方）----
    for (let p = 0; p < n * NG; p++) {
      wake[p] = Math.hypot(wake[p], deficit[p] * uInit[p])
    }

    // ---- 尾流诱发湍流（crespo_hernandez + 面积重叠门）----
    for (let sj = 0; sj < n; sj++) {
      const tj = order[sj]
      const dxj = xr[tj] - xi
      if (dxj <= 0.1 || dxj > 15 * D) continue
      let hit = 0
      let yOk = false
      for (let g = 0; g < NG; g++) {
        const k = sj * NG + g
        if (deficit[k] * uInit[k] > 0.05) hit++
        if (Math.abs(yi - py[k]) < 2 * D) yOk = true
      }
      if (!yOk || hit === 0) continue
      const ov = hit / NG
      const tiWake =
        GCH.ch.constant *
        Math.pow(aI, GCH.ch.ai) *
        Math.pow(wind.ti, GCH.ch.initial) *
        Math.pow(dxj / D, GCH.ch.downstream)
      const add = ov * tiWake
      const cand = Math.sqrt(add * add + wind.ti * wind.ti)
      if (cand > tiTurbines[sj]) tiTurbines[sj] = cand
    }

    // ---- 流场更新 ----
    for (let p = 0; p < n * NG; p++) {
      u[p] = uInit[p] - wake[p]
      v[p] += vWake[p]
      w[p] += wWake[p]
    }
  }

  // 计算用于 full_flow_sequential_solver (viz / crossPlane) 的有效偏航
  const effYawVizArr = new Array<number>(n)
  for (let si = 0; si < n; si++) {
    const t = order[si]
    const yawT = yawDeg[t]
    const uAvgI = uAvgArr[si]
    const ctI = ctIArr[si]
    const base = si * NG
    let vSum = 0
    for (let g = 0; g < NG; g++) vSum += v[base + g]
    const avgV = vSum / NG
    let effYawViz = yawT
    if (uAvgI > 0 && ctI > 0) {
      const vMeans = [0, 0, 0]
      for (let g = 0; g < 3; g++) {
        let sum = 0
        for (let iz = 0; iz < 3; iz++) {
          const k = base + g * 3 + iz
          sum += (v[k] / u[k]) * uInfMean
        }
        vMeans[g] = sum / 3
      }
      let val = (2 * (avgV - vMeans[2])) / (vMeans[0] + vMeans[1])
      if (val < -1) val = -1
      if (val > 1) val = 1
      effYawViz = yawT + (0.5 * Math.asin(val)) / DEG
    }
    effYawVizArr[si] = effYawViz
  }

  const state: SolvedTurbineState = {
    order, unsort, xr, yr,
    uAvg: uAvgArr, rawCt: rawCtArr, ctI: ctIArr, aI: aIArr, effYaw: effYawArr, effYawViz: effYawVizArr,
    tiTurbines, uInfMean, velTop, velBot, eps, eps2,
  }

  return { state, u }
}

/**
 * FLORIS 4.6.6 GCH 顺序求解（turbine_grid 3×3 口径）。
 * @param xFloris 东向坐标 (m)
 * @param yFloris 北向坐标 (m)
 * @param wind 风况
 * @param yawDeg 各机偏航指令（°，FLORIS 约定：正=机头顺时针）
 */
export function runGCH(
  xFloris: number[],
  yFloris: number[],
  wind: GCHWind,
  yawDeg: number[],
): GCHResult {
  const n = xFloris.length
  const NG = 9
  const { state, u } = solveTurbineGrid(xFloris, yFloris, wind, yawDeg)
  const { unsort, tiTurbines } = state

  // ---- 机组结果（unsort 回原始顺序）----
  const turbines: TurbineEval[] = new Array<TurbineEval>(n)
  let totalKw = 0
  for (let si = 0; si < n; si++) {
    const t = unsort[si]
    const base = si * NG
    let u3 = 0
    for (let g = 0; g < NG; g++) {
      const k = base + g
      u3 += u[k] * u[k] * u[k]
    }
    const uAvg = Math.cbrt(u3 / NG)
    const uEff = uAvg > 0 ? effectiveVelocity(uAvg, yawDeg[t], GCH.rho) : 0
    const rawCt = uAvg > 0 ? Math.min(0.9999, Math.max(0.0001, ctTable(uAvg))) : 0.0001
    const ct = rawCt * Math.cos(yawDeg[t] * DEG)
    const pKw = powerTableKw(uEff)
    totalKw += pKw
    turbines[t] = {
      uAvg, uEff, ct,
      aI: (0.5 / Math.cos(yawDeg[t] * DEG)) * (1 - Math.sqrt(Math.max(0, 1 - ct * Math.cos(yawDeg[t] * DEG)))),
      ti: tiTurbines[si],
      powerKw: pKw,
      effYaw: state.effYaw[si],
    }
  }
  return { turbines, totalKw }
}

/** 调试/取证用：solveTurbineGrid 的 27 点转子网格原始 u（布局序 × 3×3，g = iy*3+iz，±D/4） */
export function __debugRotorU(xFloris: number[], yFloris: number[], wind: GCHWind, yawDeg: number[]): number[] {
  const { u } = solveTurbineGrid(xFloris, yFloris, wind, yawDeg)
  return Array.from(u)
}

/**
 * 轮毂高度水平面流场采样（z = HH，展示口径，R44 演示 C1 流场图）。
 * 与 solveTurbineGrid 同一套 GCH 公式（gauss 偏折 + gauss 亏损 + SOSFS 组合），
 * 但机组状态（uAvg/ct/aI/effYaw/ti）直接复用 runGCH 的逐机结果：
 *  · 口径差异（已文档化）：ti 取恢复后值（runGCH 返回口径），对 sigma 的影响
 *    在亚百分点级，仅影响展示场，不影响任何功率/误差数字（那些走 runGCH 原路）。
 * 红线（9.19 §二）：轮毂高度截面是展示范围，不解释为二维物理问题。
 * @param xs FLORIS 系东向坐标采样点 (m)
 * @param ys FLORIS 系北向坐标采样点 (m)
 * @returns u (m/s)，长度 = ys.length * xs.length（iy 外层, ix 内层）
 */
export function sampleHubPlane(
  xFloris: number[],
  yFloris: number[],
  wind: GCHWind,
  yawDeg: number[],
  xs: number[],
  ys: number[],
): Float64Array {
  const n = xFloris.length
  const D = TURBINE.D
  const { alpha, beta, ka, kb } = GCH

  // ---- 坐标旋转（流向 +x'，与 solveTurbineGrid 同口径）----
  const delta = ((((wind.fromDeg - 270) % 360) + 360) % 360) * DEG
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (let i = 0; i < n; i++) {
    if (xFloris[i] < minX) minX = xFloris[i]
    if (xFloris[i] > maxX) maxX = xFloris[i]
    if (yFloris[i] < minY) minY = yFloris[i]
    if (yFloris[i] > maxY) maxY = yFloris[i]
  }
  const cx = (minX + maxX) / 2
  const cy = (minY + maxY) / 2
  const cosD = Math.cos(delta), sinD = Math.sin(delta)
  const xr = new Array<number>(n), yr = new Array<number>(n)
  for (let i = 0; i < n; i++) {
    const ox = xFloris[i] - cx, oy = yFloris[i] - cy
    xr[i] = ox * cosD - oy * sinD + cx
    yr[i] = ox * sinD + oy * cosD + cy
  }

  // ---- 排序（上游→下游，稳定，与 solveTurbineGrid 一致）----
  const order = Array.from({ length: n }, (_, i) => i)
  order.sort((a, b) => xr[a] - xr[b] || a - b)

  // ---- 逐机状态复用 runGCH（同输入同结果）----
  const res = runGCH(xFloris, yFloris, wind, yawDeg)

  // ---- 水平面网格点（旋转后坐标）----
  const NX = xs.length, NY = ys.length
  const P = NX * NY
  const px = new Float64Array(P)
  const py = new Float64Array(P)
  for (let iy = 0; iy < NY; iy++) {
    for (let ix = 0; ix < NX; ix++) {
      const p = iy * NX + ix
      const ox = xs[ix] - cx, oy = ys[iy] - cy
      px[p] = ox * cosD - oy * sinD + cx
      py[p] = ox * sinD + oy * cosD + cy
    }
  }

  // z = HH（= 参考高）→ 初始流场处处 = uInf（剪切项幂为 0）
  const uInit = wind.uInf
  const wake = new Float64Array(P)
  const defl = new Float64Array(P)
  const eA = Math.exp(1 / 12), eB = Math.exp(1 / 3)

  for (let si = 0; si < n; si++) {
    const t = order[si]
    const xi = xr[t]
    const yi = yr[t]
    const yawT = yawDeg[t]
    const tb = res.turbines[t]
    const ctI = tb.ct
    const tiI = tb.ti
    const s1ct = Math.sqrt(1 - ctI)

    // ---- 偏折场参数（gauss；z=HH → dZ=0，与 solveTurbineGrid 同式，up=uInit 处处相等）----
    const yawMr = -tb.effYaw * DEG
    const cosYm = Math.cos(yawMr)
    const s1ctCos = Math.sqrt(Math.max(0, 1 - ctI * cosYm))
    const x0 = xi + (D * cosYm * (1 + s1ctCos)) / (Math.SQRT2 * (4 * alpha * tiI + 2 * beta * (1 - s1ct)))
    const kyD = ka * tiI + kb
    const thetaC0 = (0.3 * yawMr / cosYm) * (1 - s1ctCos)
    const delta0 = Math.tan(thetaC0) * (x0 - xi)
    const uRm = (uInit * ctI * cosYm) / (2 * (1 - s1ctCos))
    const sz0m = (D / 2) * Math.sqrt(uRm / (uInit + uInit * s1ct))
    const sy0m = sz0m * cosYm
    const C0 = 1 - s1ct
    const M0 = C0 * (2 - C0)
    const E0 = C0 * C0 - 3 * eA * C0 + 3 * eB
    const midCoef = (thetaC0 * E0 / 5.2) * Math.sqrt((sy0m * sz0m) / (kyD * kyD * M0))

    // ---- 亏损场参数（gauss；z=HH → dZ=0，与 solveTurbineGrid 同式）----
    const yawVr = -yawT * DEG
    const cosYv = Math.cos(yawVr)
    const x0v = xi + (D * cosYv * (1 + s1ct)) / (Math.SQRT2 * (4 * alpha * tiI + 2 * beta * (1 - s1ct)))
    const kyV = ka * tiI + kb
    const uRv = (uInit * ctI) / (2 * (1 - s1ct))
    const sz0v = (D / 2) * Math.sqrt(uRv / (uInit + uInit * s1ct))
    const sy0v = sz0v * cosYv

    for (let p = 0; p < P; p++) {
      const xP = px[p]
      // 偏折：近场 [xi, x0] 线性 + 远场解析（dNear + dFar，与内核同一结构）
      const dNear = ((xP - xi) / (x0 - xi)) * delta0 * ((xP >= xi && xP <= x0) ? 1 : 0)
      let dFar = 0
      if (xP > x0) {
        const sy = kyD * (xP - x0) + sy0m
        const sz = kyD * (xP - x0) + sz0m
        const mt = Math.sqrt((sy * sz) / (sy0m * sz0m))
        const ms = Math.sqrt(M0)
        const lnNum = (1.6 + ms) * (1.6 * mt - ms)
        const lnDen = (1.6 - ms) * (1.6 * mt + ms)
        dFar = delta0 + midCoef * Math.log(lnNum / lnDen)
      }
      defl[p] = dNear + dFar

      // 亏损（gauss 近/远场）
      let dfc = 0
      if (ctI > 0 && xP > xi + 0.1) {
        const dY = py[p] - yi - defl[p]
        if (xP < x0v) {
          const rampUp = (xP - xi) / (x0v - xi)
          const rampDown = (x0v - xP) / (x0v - xi)
          const sy = rampDown * 0.501 * D * Math.sqrt(ctI / 2) + rampUp * sy0v
          const sz = rampDown * 0.501 * D * Math.sqrt(ctI / 2) + rampUp * sz0v
          const r2 = (dY * dY) / (2 * sy * sy)
          const Cc = 1 - Math.sqrt(clamp01(1 - (ctI * cosYv) / ((8 * sy * sz) / (D * D))))
          dfc = Cc * Math.exp(-r2)
        } else {
          const sy = kyV * (xP - x0v) + sy0v
          const sz = kyV * (xP - x0v) + sz0v
          const r2 = (dY * dY) / (2 * sy * sy)
          const Cc = 1 - Math.sqrt(clamp01(1 - (ctI * cosYv) / ((8 * sy * sz) / (D * D))))
          dfc = Cc * Math.exp(-r2)
        }
      }
      wake[p] = Math.hypot(wake[p], dfc * uInit)
    }
  }

  const out = new Float64Array(P)
  for (let p = 0; p < P; p++) out[p] = uInit - wake[p]
  return out
}

/**
 * FLORIS 4.6.6 full_flow_sequential_solver 横截面采样（FlowFieldPlanarGrid 口径）。
 * @param xFloris 机组东向坐标 (m)
 * @param yFloris 机组北向坐标 (m)
 * @param wind 风况
 * @param yawDeg 机组偏航
 * @param downstreamDist 下游距离 (m，旋转流场系 x')
 * @param ys 横截面 y 采样点序列 (m)
 * @param zs 横截面 z 采样点序列 (m)
 * @returns u 展平数组（len = zs.length * ys.length，iz 外层, iy 内层）
 */
export function sampleCrossPlane(
  xFloris: number[],
  yFloris: number[],
  wind: GCHWind,
  yawDeg: number[],
  downstreamDist: number,
  ys: number[],
  zs: number[],
): number[] {
  const n = xFloris.length
  const ny = ys.length
  const nz = zs.length
  const nPoints = ny * nz
  const D = TURBINE.D
  const HH = TURBINE.HH
  const { alpha, beta, ka, kb, shear, numEps } = GCH

  // 1. 先求解机组转子网格稳态
  const { state } = solveTurbineGrid(xFloris, yFloris, wind, yawDeg)
  const { order, xr, yr, ctI, aI, effYawViz, tiTurbines, uInfMean, velTop, velBot, eps2 } = state

  // 2. 建立横截面网格（CutPlane: iz 外层, iy 内层）
  const px = new Float64Array(nPoints).fill(downstreamDist)
  const py = new Float64Array(nPoints)
  const pz = new Float64Array(nPoints)
  let idx = 0
  for (let iz = 0; iz < nz; iz++) {
    for (let iy = 0; iy < ny; iy++) {
      py[idx] = ys[iy]
      pz[idx] = zs[iz]
      idx++
    }
  }

  // 3. 初始流场与各状态场
  const uInit = new Float64Array(nPoints)
  const dudz = new Float64Array(nPoints)
  const refH = HH
  for (let p = 0; p < nPoints; p++) {
    const z = pz[p]
    uInit[p] = wind.uInf * Math.pow(z / refH, shear)
    dudz[p] = wind.uInf * shear * Math.pow(1 / refH, shear) * Math.pow(z, shear - 1)
  }

  const wake = new Float64Array(nPoints)
  const defl = new Float64Array(nPoints)
  const deficit = new Float64Array(nPoints)
  const vWake = new Float64Array(nPoints)
  const wWake = new Float64Array(nPoints)

  // 4. 按上游到下游顺序将各机组尾流叠加到横截面网格
  for (let si = 0; si < n; si++) {
    const t = order[si]
    const yi = yr[t]
    const xi = xr[t]
    const yawT = yawDeg[t]
    const ct = ctI[si]
    const induction = aI[si]
    const tiI = tiTurbines[si]
    const effY = effYawViz[si]

    // Deflection field
    const yawM = -effY
    const yawMr = yawM * DEG
    const cosYm = Math.cos(yawMr)
    const s1ct = Math.sqrt(1 - ct)
    const s1ctCos = Math.sqrt(Math.max(0, 1 - ct * cosYm))
    const x0 = xi + (D * cosYm * (1 + s1ctCos)) / (Math.SQRT2 * (4 * alpha * tiI + 2 * beta * (1 - s1ct)))
    const kyD = ka * tiI + kb
    const thetaC0 = (0.3 * yawMr / cosYm) * (1 - s1ctCos)
    const delta0 = Math.tan(thetaC0) * (x0 - xi)
    const eA = Math.exp(1 / 12), eB = Math.exp(1 / 3)
    for (let p = 0; p < nPoints; p++) {
      const up = uInit[p]
      const uR = (up * ct * cosYm) / (2 * (1 - s1ctCos))
      const u0 = up * s1ct
      const sz0 = (D / 2) * Math.sqrt(uR / (up + u0))
      const sy0 = sz0 * cosYm
      const C0 = 1 - u0 / up
      const M0 = C0 * (2 - C0)
      const E0 = C0 * C0 - 3 * eA * C0 + 3 * eB
      const dNear = ((px[p] - xi) / (x0 - xi)) * delta0 * ((px[p] >= xi) && (px[p] <= x0) ? 1 : 0)
      let dFar = 0
      if (px[p] > x0) {
        const sy = kyD * (px[p] - x0) + sy0
        const sz = kyD * (px[p] - x0) + sz0
        const mt = Math.sqrt((sy * sz) / (sy0 * sz0))
        const ms = Math.sqrt(M0)
        const lnNum = (1.6 + ms) * (1.6 * mt - ms)
        const lnDen = (1.6 - ms) * (1.6 * mt + ms)
        const mid = (thetaC0 * E0 / 5.2) * Math.sqrt((sy0 * sz0) / (kyD * kyD * M0)) * Math.log(lnNum / lnDen)
        dFar = delta0 + mid
      }
      defl[p] = dNear + dFar
    }

    // Transverse velocity
    const yawTr = yawT * DEG
    const sinc = Math.sin(yawTr) * Math.cos(yawTr)
    const gTop2 = sinc * (Math.PI / 8) * D * velTop * uInfMean * ct
    const gBot2 = -sinc * (Math.PI / 8) * D * velBot * uInfMean * ct
    const gRot2 = state.uAvg[si] > 0 ? 0.25 * 2 * Math.PI * D * (induction - induction * induction) * state.uAvg[si] / TURBINE.TSR : 0
    for (let p = 0; p < nPoints; p++) {
      const dx = px[p] - xi
      if (dx < 0) {
        vWake[p] = 0
        wWake[p] = 0
        continue
      }
      const z = pz[p]
      const lm = (0.41 * z) / (1 + (0.41 * z) / (D / 8))
      const nu = lm * lm * Math.abs(dudz[p])
      const decay = eps2 / (4 * nu * (dx / uInfMean) + eps2)
      const yLoc = py[p] - yi + numEps
      const vorts = [
        gTop2, z - (HH + D / 2) + numEps, 1,
        gBot2, z - (HH - D / 2) + numEps, 1,
        gRot2, z - HH + numEps, 1,
        gTop2, z + (HH + D / 2) + numEps, -1,
        gBot2, z + (HH - D / 2) + numEps, -1,
        gRot2, z + HH + numEps, -1,
      ]
      let vv = 0, ww = 0
      for (let q = 0; q < 6; q++) {
        const G = vorts[q * 3], zRel = vorts[q * 3 + 1], sgn = vorts[q * 3 + 2]
        const r2 = yLoc * yLoc + zRel * zRel
        const core = 1 - Math.exp(-r2 / eps2)
        const f = (G * core * decay) / (2 * Math.PI * r2)
        vv += sgn * f * zRel
        ww += -sgn * f * yLoc
      }
      vWake[p] = vv
      wWake[p] = ww > 0 ? ww : 0
    }

    // Velocity deficit
    const yawV = -yawT
    const yawVr = yawV * DEG
    const cosYv = Math.cos(yawVr)
    const x0v = xi + (D * cosYv * (1 + s1ct)) / (Math.SQRT2 * (4 * alpha * tiI + 2 * beta * (1 - s1ct)))
    const kyV = ka * tiI + kb
    for (let p = 0; p < nPoints; p++) {
      const up = uInit[p]
      let dfc = 0
      if (ct > 0 && up > 0) {
        const uR = (up * ct) / (2 * (1 - s1ct))
        const u0 = up * s1ct
        const sz0 = (D / 2) * Math.sqrt(uR / (up + u0))
        const sy0 = sz0 * cosYv
        const xP = px[p]
        const dY = py[p] - yi - defl[p]
        const dZ = pz[p] - HH
        if (xP > xi + 0.1 && xP < x0v) {
          const rampUp = (xP - xi) / (x0v - xi)
          const rampDown = (x0v - xP) / (x0v - xi)
          const sy = (rampDown * 0.501 * D * Math.sqrt(ct / 2) + rampUp * sy0) * (xP >= xi ? 1 : 0) + (xP < xi ? D * 0.5 : 0)
          const sz = (rampDown * 0.501 * D * Math.sqrt(ct / 2) + rampUp * sz0) * (xP >= xi ? 1 : 0) + (xP < xi ? D * 0.5 : 0)
          const r2 = (dY * dY) / (2 * sy * sy) + (dZ * dZ) / (2 * sz * sz)
          const Cc = 1 - Math.sqrt(clamp01(1 - (ct * cosYv) / ((8 * sy * sz) / (D * D))))
          dfc = Cc * Math.exp(-r2)
        } else if (xP >= x0v) {
          const sy = kyV * (xP - x0v) + sy0
          const sz = kyV * (xP - x0v) + sz0
          const r2 = (dY * dY) / (2 * sy * sy) + (dZ * dZ) / (2 * sz * sz)
          const Cc = 1 - Math.sqrt(clamp01(1 - (ct * cosYv) / ((8 * sy * sz) / (D * D))))
          dfc = Cc * Math.exp(-r2)
        }
      }
      deficit[p] = dfc
    }

    // Wake combination (SOSFS)
    for (let p = 0; p < nPoints; p++) {
      wake[p] = Math.hypot(wake[p], deficit[p] * uInit[p])
    }
  }

  const uResult = new Array<number>(nPoints)
  for (let p = 0; p < nPoints; p++) {
    uResult[p] = uInit[p] - wake[p]
  }
  return uResult
}
