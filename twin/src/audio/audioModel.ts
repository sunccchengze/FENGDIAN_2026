// ================================================================
// T9 · 声场模型（纯函数层，无 Web Audio 依赖）
// ----------------------------------------------------------------
// 为什么单独一层：
//   · audioEngine.ts 只在浏览器里跑（AudioContext），Node 的 selftest 碰不到；
//   · 但「海浪响度跟浪高走、贴岸变碎浪、风机随转速呼啸、远处衰减」这套
//     **映射规律**是本仓的口径问题，必须可回归、可对表 —— 所以放这里。
//
// 同源红线（与渲染层逐项对表，selftest R40 断言）：
//   · 涌浪幅值/波长/方向/时间系数/相位 = WorldTerrain VERT 的两条 Gerstner
//     （λ=2400 陡度 0.06 时间 ×0.35；λ=1500 陡度 0.045 时间 ×0.50 相位 +2.1）；
//   · 场心收敛 + 浅水阻尼包络 = VERT/FRAG 的 amp / swellEnv()（同一式子）；
//   · 拍岸碎浪带 = FRAG 的「离岸 0~300m、向岸推进」碎浪带同一岸距口径
//     （shoreSigned：负 = 海侧离岸米数）；
//   · 风机声源点 = 轮毂（terrainSurfaceY + HUB_H），叶片通过频率 = 3 × rpm/60。
//
// 诚实边界：这是**演示口径的程序化声场**（Web Audio 振荡器 + 滤波噪声），
// 不是实测声压级、不是 IEC 61400-11 噪声认证数据。界面/文档统一挂【示意】。
// ================================================================

import { shoreSigned, FARM_CENTER, terrainSurfaceY } from '../scene/terrainUtil.ts'
import { HUB_H } from '../data/turbinePhysics.ts'

// ---- WorldTerrain VERT 的两条 Gerstner（改动必须同步 selftest R40 对表）----
export const SWELL_A1 = 0.06 / (Math.PI * 2 / 2400) // = 22.92 m
export const SWELL_A2 = 0.045 / (Math.PI * 2 / 1500) // = 10.74 m
const K1 = (Math.PI * 2) / 2400
const K2 = (Math.PI * 2) / 1500
const C1 = Math.sqrt(9.8 / K1)
const C2 = Math.sqrt(9.8 / K2)
/** VERT 里 uTime 的时间系数（涌浪 0.35 / 0.50）—— 视觉周期，不是深水波周期 */
const TCOEF1 = 0.35
const TCOEF2 = 0.50
const PHASE2 = 2.1

const clamp01 = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : t)
const smoothstep = (e0: number, e1: number, x: number) => {
  const t = clamp01((x - e0) / (e1 - e0))
  return t * t * (3 - 2 * t)
}

/** 风向单位向量（场景系 xz）：fromDeg 为气象口径「风 FROM 的方向」，0 = 北来 → 吹向 +z */
export function windDirXZ(fromDeg: number): { x: number; z: number } {
  const th = (fromDeg * Math.PI) / 180
  return { x: Math.sin(th), z: Math.cos(th) }
}

/**
 * 归一化涌浪相位包络 ∈ [-1, 1] —— 逐项镜像 WorldTerrain 的 `swellN()`。
 * 幅值比与几何一致（a1 : a2 = 0.68 : 0.32）。
 */
export function swellPhaseAt(x: number, z: number, t: number, fromDeg: number): number {
  const w = windDirXZ(fromDeg)
  // VERT: d2 = normalize(vec2(-uWind.y, uWind.x)) → 场景系 (x, z) 即 (-w.z, w.x)
  const d2x = -w.z
  const d2z = w.x
  const s1 = Math.sin(K1 * (w.x * x + w.z * z - C1 * (t * TCOEF1)))
  const s2 = Math.sin(K2 * (d2x * x + d2z * z - C2 * (t * TCOEF2 + PHASE2)))
  return (SWELL_A1 * s1 + SWELL_A2 * s2) / (SWELL_A1 + SWELL_A2)
}

/** 涌浪包络（场心收敛 × 浅水阻尼）—— 与 VERT `amp` / FRAG `swellEnv()` 同式 */
export function swellEnvAt(x: number, z: number, shore: number): number {
  const dc = Math.hypot(x - FARM_CENTER.x, z - FARM_CENTER.z)
  return (
    (0.5 + 0.5 * smoothstep(180, 2000, dc)) * (0.16 + 0.84 * smoothstep(0, 260, -shore))
  )
}

/** 听者处的「视觉有效波高」(m)：着色口径波高 × 当地包络（与画面同一套浪） */
export function swellHeightAt(x: number, z: number, t: number, fromDeg: number, shore: number): number {
  return (SWELL_A1 + SWELL_A2) * Math.abs(swellPhaseAt(x, z, t, fromDeg)) * swellEnvAt(x, z, shore)
}

/** 涌浪周期（s）：与视觉同源（λ/相速 ÷ 时间系数），不是深水波真实周期 */
export function swellPeriodS(): number {
  return (2 * Math.PI) / (K1 * C1 * TCOEF1)
}

// ---- 增益映射（0..1，交给引擎做 dB/线性混音）----

/** 远场涌浪底噪：随有效波高起伏（±16.8m 理论涌浪 → 0.24 满量程） */
export function oceanSwellGain(hSwell: number): number {
  return 0.12 + 0.88 * smoothstep(0.6, 14, hSwell)
}

/**
 * 拍岸碎浪：海侧岸距 <340m 起、<60m 满（与 FRAG 碎浪带 0~300m 同口径）；
 * 上岸后 80~600m 内渐隐（站在沙滩听得见、走进内陆 1km 听不见）。
 */
export function surfGain(shore: number, hSwell: number): number {
  const band = smoothstep(-340, -60, shore) * (1 - smoothstep(80, 600, shore))
  return band * (0.35 + 0.65 * smoothstep(0.5, 8, hSwell))
}

/**
 * 陆地门（两段）：上岸 0–260m 先压 55%（浪声变远变闷），再向内陆 500–2000m 渐隐到 15%
 * ——旧版只压 55%，内陆 3km 的山头上仍听得到海嗡声（R40b 修）。
 * 海岸崖顶（shore<260）听感基本不变。
 */
export function oceanLandGate(shore: number): number {
  return (1 - 0.55 * smoothstep(0, 260, shore)) * (1 - 0.85 * smoothstep(500, 2000, shore))
}

/** 风噪床（叶片切风之外的大气湍流嘶声）：随风速起伏 */
export function windBedGain(u: number): number {
  return 0.06 + 0.94 * smoothstep(4.5, 12.5, u)
}

/** 叶片通过频率 (Hz)：3 叶片 × 转频。NREL 5MW 6.9~12.1 rpm → 0.345~0.605 Hz */
export function bladePassHz(rpm: number): number {
  return (Math.max(0, rpm) / 60) * 3
}

/** 机舱机械音调基频 (Hz)：发电机侧 = 转频 × 97（NREL 5MW 齿轮箱比 1:97 口径） */
export function driveTrainHz(rpm: number): number {
  return (Math.max(0, rpm) / 60) * 97
}

/** 风机声源点（世界坐标，轮毂）：与 3D 场景同一贴地真值 */
export function turbineSource(x: number, z: number): { x: number; y: number; z: number } {
  return { x, y: terrainSurfaceY(x, z) + HUB_H, z }
}

export interface TurbineAcoustic {
  idx: number
  x: number
  y: number
  z: number
  dist: number
  rpm: number
  uEff: number
  /** 0..1 相对响度（距离衰减 × 风速调制 × 下风向增强） */
  gain: number
  bladePassHz: number
  driveTrainHz: number
}

/** 可闻地平线：≥2.2km 完全静音（1.2–2.2km 渐隐）——R40b 修「离很远还有明显声音」 */
export const TURBINE_AUDIBLE_FAR = 2200

/**
 * 距离衰减闭式（R40b 收紧：指数 1.25→1.6 + 可闻地平线）：
 *   g(d) = (ref/(ref+d))^1.6 × (1 − smoothstep(1200, 2200, d))，ref = 140 m
 * → 1D(126m) 0.36、3D(378m) 0.12、1km 0.035、1.5km ≈0.010、≥2.2km = 0。
 * 口径依据：5MW 机组近塔可闻、1km  quiet 乡村背景下隐约可闻、2km 外被环境噪底淹没
 * （球形扩散 + 空气吸收 + 地面效应），旧 1.25 指数在 2–4km 仍留 3% 增益＝安静环境下
 * 明显可闻的哨音，与物理不符（R40b 用户实测反馈确认）。
 * 引擎 PannerNode 只做 HRTF 方位（rolloff=0），距离衰减**唯一真值在本函数**（可回归）。
 */
export function turbineDistanceGain(dist: number): number {
  const ref = 140
  const d = Math.max(0, dist)
  return Math.pow(ref / (ref + d), 1.6) * (1 - smoothstep(1200, TURBINE_AUDIBLE_FAR, d))
}

/** 风速调制：切风声随来流涨落（uEff 用尾流后的等效风速 → 下游机更安静，物理一致） */
export function turbineWindGain(uEff: number): number {
  return 0.18 + 0.82 * smoothstep(4, 12, uEff)
}

/**
 * 下风向增强：真实机组噪声在下风向比上风向高 ~2 dB（IEC 61400-11 常识口径）。
 * 这里用「听者相对机组是否处在风的去向一侧」给 ±18% 调制，示意级别。
 */
export function downwindFactor(
  lx: number,
  lz: number,
  tx: number,
  tz: number,
  fromDeg: number,
): number {
  const w = windDirXZ(fromDeg)
  const dx = lx - tx
  const dz = lz - tz
  const d = Math.hypot(dx, dz)
  if (d < 1) return 1
  const cosAng = (dx * w.x + dz * w.z) / d
  return 1 + 0.18 * cosAng
}

/** 单台机组的声学读数（纯函数，供引擎与 selftest 共用） */
export function turbineAcoustic(
  idx: number,
  tx: number,
  tz: number,
  rpm: number,
  uEff: number,
  lx: number,
  ly: number,
  lz: number,
  fromDeg: number,
): TurbineAcoustic {
  const src = turbineSource(tx, tz)
  const dist = Math.hypot(lx - src.x, ly - src.y, lz - src.z)
  const gain =
    turbineDistanceGain(dist) * turbineWindGain(uEff) * downwindFactor(lx, lz, tx, tz, fromDeg) *
    (rpm > 0.1 ? 1 : 0.06) // 停机机组只剩机舱风噪的残响
  return {
    idx, x: src.x, y: src.y, z: src.z, dist, rpm, uEff,
    gain, bladePassHz: bladePassHz(rpm), driveTrainHz: driveTrainHz(rpm),
  }
}

/**
 * 声部裁决：3×3 九机全上 PannerNode 会让节点数与 CPU 都翻三倍，
 * 实际可闻的永远只有最近几台 —— 按 gain 取前 N（其余归零，引擎淡出）。
 * R42：上限 3 ≥ 1×3 场区机组数，三机全上（HRTF 方位更准）；3×3 裁到最近 3 台。
 */
export function selectTurbines(
  units: Array<{ x: number; z: number; rpm: number; uEff: number }>,
  lx: number,
  ly: number,
  lz: number,
  fromDeg: number,
  maxVoices = 3,
  // R40b：曲线收紧（指数 1.6）后 1km 处增益 ≈0.015×风速调制，旧地板 0.012 会把
  // 「1km 隐约可闻」也裁掉 → 地板降到 0.004；≥2.2km 由地平线**精确归零**兜底
  gainFloor = 0.004,
): TurbineAcoustic[] {
  const all = units.map((u, i) =>
    turbineAcoustic(i, u.x, u.z, u.rpm, u.uEff, lx, ly, lz, fromDeg),
  )
  all.sort((a, b) => b.gain - a.gain || a.dist - b.dist)
  return all.slice(0, maxVoices).filter((a) => a.gain >= gainFloor)
}

/** 声场一帧的全部输入（引擎 update() 的唯一入参，便于 selftest 构造） */
export interface AcousticScene {
  /** 听者（相机）世界坐标 */
  lx: number
  ly: number
  lz: number
  /** 相机前向（单位向量，场景系）：HRTF 定位用 */
  fx: number
  fy: number
  fz: number
  /** 世界上向量 */
  ux: number
  uy: number
  uz: number
  /** 仿真时间轴（小时） */
  tHours: number
  /** 渲染时钟（秒，与 uTime 同源） */
  t: number
  /** 全场风速 (m/s) */
  windSpeed: number
  /** 来风方位（气象口径） */
  windFromDeg: number
  /** 机组（9 台，场景坐标 + 转速 + 等效风速） */
  units: Array<{ x: number; z: number; rpm: number; uEff: number }>
  maxVoices?: number
}

export interface AcousticFrame {
  /** 听者处岸距（负 = 海侧离岸米数） */
  shore: number
  /** 听者处有效波高 (m) */
  hSwell: number
  /** 远场涌浪底噪增益 0..1 */
  swellGain: number
  /** 拍岸碎浪增益 0..1 */
  surfGain: number
  /** 陆地门（听者在陆上时压低海面底噪） */
  landGate: number
  /** 风噪床增益 0..1 */
  windGain: number
  /** 涌浪周期（s）：驱动 LFO，浪涌节奏与画面同源 */
  swellPeriod: number
  /** 参与发声的机组（按响度取前 N） */
  voices: TurbineAcoustic[]
}

/** 声场求值：一帧的全部增益与声部裁决（纯函数） */
export function acousticFrame(s: AcousticScene): AcousticFrame {
  const shore = shoreSigned(s.lx, s.lz)
  // 听者在陆地上时 shoreSigned > 0，波高按岸线外推（浪不会爬上陆地）
  const hSwell = shore < 0 ? swellHeightAt(s.lx, s.lz, s.t, s.windFromDeg, shore) : 0
  return {
    shore,
    hSwell,
    swellGain: oceanSwellGain(hSwell) * oceanLandGate(shore),
    surfGain: surfGain(shore, hSwell),
    landGate: oceanLandGate(shore),
    windGain: windBedGain(s.windSpeed),
    swellPeriod: swellPeriodS(),
    voices: selectTurbines(s.units, s.lx, s.ly, s.lz, s.windFromDeg, s.maxVoices ?? 3),
  }
}
