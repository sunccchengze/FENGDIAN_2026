// ================================================================
// AEOLUS 演示数据契约（Demo Data Contract）—— 全场唯一事实源
// ----------------------------------------------------------------
// 评审 A5/D2 的根因修复：此前 HUD 各组件各自硬编码数字（5 台 vs 9 台、
// 频率 48.20、雷达花瓣写死……互相穿帮）。本模块把 *全部* 运行读数收敛为
// 一个确定性纯函数：
//
//     farmFrame(tHours, unitYaw[9], targetPowerMW) → FarmFrame
//
// 同一 (t, yaw, target) 永远得到同一帧 → HUD / 3D / 告警 / 雷达 / 曲线
// 共享同一帧，天然一致；时间轴真正驱动数据；偏航滑杆真正驱动功率。
//
// 诚实边界（docs/02 §1 红线）：这是"浏览器端确定性演示数据"，物理内核
// 是公开 Jensen 代理模型（见 turbinePhysics.ts），不是 FLORIS/OpenFAST
// 求解结果，不是 SCADA 实测。HUD 所有读数统一挂【演示】角标。
// ================================================================

import { FARM, ROW_COUNT } from '../scene/terrainUtil.ts'
import { smoothNoise, periodicSmoothNoise } from './rng.ts'
import {
  powerCurveKw, rotorRpm, genTempC, gridFrequency, WAKE_REV} from './turbinePhysics.ts'
import { evaluateFarmScene } from '../core/physics/evalFarm.ts'

export const N_UNITS = FARM.length // R41-A：派生自布局真值源（3×3=9 / 1×3=3）
export const FARM_RATED_MW = N_UNITS * 5 // 单机 5 MW × 机组数（R41-A 派生，旧写死 45 作废）

// ---- 场景坐标系约定（全场唯一）----
// +x = 东，+z = 南（three.js Y-up 下取 -z 为北）
// 主导来风：从北吹向南（windFromDeg = 0° 表示"从正北来"）→ 粒子层北→南
// 上风向机组：机舱方位（yawDeg）= 机头朝向，对风 = yawDeg ≈ windFromDeg
export const BASE_WIND_FROM = 0

/** 雷达 8 方位顺序（与 HUD 花瓣索引一致） */
export const ROSE_ORDER = ['NW', 'N', 'NE', 'E', 'SE', 'S', 'SW', 'W'] as const

export type UnitStatus = 'run' | 'curtail' | 'alarm' | 'idle'

export interface UnitFrame {
  id: string
  x: number
  z: number
  row: number
  uFree: number
  uEff: number
  yawDeg: number
  yawErrDeg: number
  rpm: number
  powerKw: number
  tempC: number
  wakeLossPct: number
  status: UnitStatus
}

export interface AlarmEvent {
  key: number
  level: 'warn' | 'crit'
  rule: string
  zh: string
  en: string
  tid: string | null
  part: string
  tStartH: number
  minutesAgo: number
}

export interface FarmFrame {
  tHours: number
  windSpeed: number
  windFromDeg: number
  units: UnitFrame[]
  totalMW: number
  availMW: number
  derateFrac: number
  freqHz: number
  qMVar: number
  runningCount: number
  wakeLossPct: number
  yawPrecPct: number
  targetPct: number
  meanRpm: number
  // 以下为重帧成员：随 30 模拟分钟分桶缓存
  energyTodayMWh: number
  energyYearEstMWh: number
  cfPct: number
  daySeries: number[]
  baseSeries: number[]
  fcSeries: number[]
  alarms: AlarmEvent[]
}

// ---- 时变风况（确定性）----
export function windAt(tHours: number): { u: number; fromDeg: number } {
  // 昼夜风廓线 + 平滑扰动（seed 固定，跨帧一致；夜间风大是低空风切变常见现象）
  // BUG-FIX（第 18 轮）：原用 smoothNoise(t*k)，其整数格点不随 24h 循环，
  // 且 fromDeg 里的 sin(t*0.13)/sin(t*0.37) 周期也不是 24 的约数 ——
  // 实测 23:59→00:00 风向瞬跳 23.2°（日内相邻步的 2715 倍），
  // 这就是"风机与尾流在 24:00/0:00 交界断裂突变"的根因。
  // 现全部改为以 24h 为周期的构造：噪声格点取模、正弦频率取 2π·n/24。
  const diurnal = 7.9 + 2.1 * Math.cos(((tHours - 3) / 24) * Math.PI * 2)
  const slow = 1.8 * (periodicSmoothNoise(tHours * 0.5, 12, 5) - 0.5)
  const fast = 0.64 * (periodicSmoothNoise(tHours * 3, 72, 9) - 0.5)
  const u = Math.min(13.2, Math.max(5.4, diurnal + slow + fast))
  // 来流方位：均值风北 + 慢尺度摆摆（veer，N±9°）。幅度小是为了与尾流/对风
  // 标定（docs/07）兼容；足以让 16 扇区风频玫瑰出现真实的主/次方向分布。
  const W = (2 * Math.PI) / 24 // 基频：一天整一圈
  const fromDeg =
    BASE_WIND_FROM - 2 +
    26 * (periodicSmoothNoise(tHours * 0.5, 12, 3) - 0.5) +
    9 * Math.sin(tHours * W + 0.9) +
    4 * Math.sin(tHours * 3 * W + 2.1)
  return { u, fromDeg }
}

/** 单机自由流风（含空间微差异）；baseU 提供时替代时变剖面（校准/快照模式） */
export function freeWindAt(tHours: number, x: number, z: number, baseU?: number): number {
  const u = baseU ?? windAt(tHours).u
  // 时间项同样必须 24h 周期（否则单机自由流在午夜也会跳）；空间项与时间项分离叠加。
  const sp = smoothNoise(x * 0.004 + z * 0.003, 17) - 0.5
  // 速率取 0.875 使 0.875×24 = 21 为整数格点，取模才真正闭合（0.9×24=21.6 不闭合）
  const tm = periodicSmoothNoise(tHours * 0.875, 21, 23) - 0.5
  return Math.max(0, u + 0.44 * (0.6 * sp + 0.4 * tm))
}

export interface WindOverride { u: number; fromDeg: number }
interface CoreOpts {
  tHours: number
  unitYaw: number[]
  targetMW: number
  /** 校准/QA 快照：锁定全场基准风（老网页 FLORIS 工况 = {u:8, fromDeg:0}） */
  wind?: WindOverride | null
}

interface FarmCore {
  units: UnitFrame[]
  totalMW: number
  availMW: number
  derateFrac: number
  wakeLossPct: number
  yawPrecPct: number
  meanRpm: number
}

const FARM_SCENE = {
  x: FARM.map((f) => f.x),
  z: FARM.map((f) => f.z),
}

function evalCore(o: CoreOpts): FarmCore {
  const { tHours, unitYaw, targetMW, wind = null } = o
  const w0 = windAt(tHours)
  const fromDeg = wind ? wind.fromDeg : w0.fromDeg
  const uInf = wind ? wind.u : w0.u
  const yawMisalignment = FARM.map((_, i) => unitYaw[i] ?? 0)

  const gch = evaluateFarmScene(
    FARM_SCENE,
    { uInf, fromDeg, ti: 0.06 },
    yawMisalignment,
  )

  const units: UnitFrame[] = FARM.map((f, i) => {
    const uFree = freeWindAt(tHours, f.x, f.z, wind ? wind.u : undefined)
    const tGch = gch.turbines[i]
    const uEff = tGch.uEff
    const powerKw = tGch.powerKw
    const rpm = rotorRpm(uEff)
    const before = powerCurveKw(uFree)
    const wakeLossPct = before > 0 ? Math.max(0, 100 * (1 - powerKw / before)) : 0
    const offset = unitYaw[i] ?? 0
    const absYaw = ((fromDeg + offset) % 360 + 360) % 360
    return {
      id: f.id,
      x: f.x,
      z: f.z,
      row: f.row,
      uFree,
      uEff,
      yawDeg: absYaw,
      yawErrDeg: offset,
      rpm,
      powerKw,
      tempC: 0,
      wakeLossPct,
      status: rpm <= 0 ? 'idle' : 'run',
    }
  })

  const withWakeMW = gch.totalKw / 1000
  let noWakeMW = 0
  for (const di of units) noWakeMW += powerCurveKw(di.uFree)

  const availMW = withWakeMW
  const t = targetMW > 0 && targetMW < FARM_RATED_MW ? targetMW : FARM_RATED_MW
  const derateFrac = Math.min(1, t / Math.max(availMW, 0.001))
  if (derateFrac < 0.999) {
    for (const di of units) di.powerKw *= derateFrac
  }
  for (const di of units) {
    if (di.status !== 'idle') di.rpm = rotorRpm(di.uEff, di.powerKw)
  }
  const totalMW = availMW * derateFrac
  const wakeLossPct = noWakeMW > 0 ? Math.max(0, 100 * (1 - (withWakeMW * 1000) / noWakeMW)) : 0
  let errSum = 0
  for (const di of units) errSum += Math.min(30, Math.abs(di.yawErrDeg))
  const yawPrecPct = 100 * (1 - errSum / units.length / 30)
  let rpmSum = 0
  let rpmN = 0
  for (const di of units) {
    if (di.rpm > 0) {
      rpmSum += di.rpm
      rpmN++
    }
  }
  return { units, totalMW, availMW, derateFrac, wakeLossPct, yawPrecPct, meanRpm: rpmN ? rpmSum / rpmN : 0 }
}

// ---- 两级记忆化：轻帧（0.25 模拟分钟）+ 重帧（30 模拟分钟分桶）----
const coreCache = new Map<string, FarmCore>()
const heavyCache = new Map<string, HeavyFrame>()
const CACHE_MAX = 64

interface HeavyFrame {
  energyTodayMWh: number
  energyYearEstMWh: number
  cfPct: number
  daySeries: number[]
  baseSeries: number[]
  fcSeries: number[]
  alarms: AlarmEvent[]
}

const yawSig = (y: number[]) => y.map((v) => Math.round(v * 2) / 2).join(',')
function evictOldest<K>(m: Map<K, unknown>, max: number) {
  while (m.size > max) {
    const k = m.keys().next().value
    if (k === undefined) break
    m.delete(k)
  }
}

function coreAt(tq: number, unitYaw: number[], targetMW: number, wind?: WindOverride | null): FarmCore {
  const ws = wind ? `|w${wind.u.toFixed(2)}@${wind.fromDeg.toFixed(1)}` : ''
  const key = `${tq}|${yawSig(unitYaw)}|${Math.round(targetMW * 10) / 10}${ws}|r${WAKE_REV}`
  const hit = coreCache.get(key)
  if (hit) return hit
  const c = evalCore({ tHours: tq, unitYaw, targetMW, wind })
  coreCache.set(key, c)
  evictOldest(coreCache, CACHE_MAX)
  return c
}

// ---- 告警引擎：对过去 6h 网格做确定性阈值扫描（可回放、无随机）----
const SCAN_N = 40 // 40 格 × 9 模拟分钟 = 6h
const SCAN_MIN = 9

const ZERO_YAW = new Array<number>(9).fill(0)

const baseSeriesCache = new Map<string, number[]>()
function getBaseSeries(wind?: WindOverride | null): number[] {
  const ws = wind ? `|w${wind.u.toFixed(2)}@${wind.fromDeg.toFixed(1)}` : '|w_auto'
  const hit = baseSeriesCache.get(ws)
  if (hit) return hit
  const arr: number[] = []
  for (let s = 0; s < 48; s++) {
    const t = (s / 48) * 24
    arr.push(coreAt(t, ZERO_YAW, FARM_RATED_MW, wind).totalMW)
  }
  baseSeriesCache.set(ws, arr)
  return arr
}

function buildHeavy(tq: number, unitYaw: number[], targetMW: number, wind?: WindOverride | null): HeavyFrame {
  // 全天 48 点（半小时网格）功率剖面 —— 当前偏航/目标设定下的"这一天"
  const daySeries: number[] = []
  const baseSeries = getBaseSeries(wind)
  for (let s = 0; s < 48; s++) {
    const t = (s / 48) * 24
    daySeries.push(coreAt(t, unitYaw, targetMW, wind).totalMW)
  }
  let daySum = 0
  for (const v of daySeries) daySum += v
  const energyTodayMWh = daySum * 0.5
  const avgMW = daySum / 48
  const energyYearEstMWh = avgMW * 8760
  const cfPct = (avgMW / FARM_RATED_MW) * 100

  // 预测 = Persistence + 2h 平移（演示口径，明说不是模型预报）
  const fcSeries = daySeries.map((_, s) => daySeries[(s + 4) % 48])

  // 告警扫描（确定性，同输入同事件；时间戳取自网格 → 可复现）
  const best = new Map<string, AlarmEvent>()
  const push = (e: AlarmEvent) => {
    const k2 = `${e.rule}|${e.tid ?? '-'}`
    const prev = best.get(k2)
    if (!prev || e.minutesAgo < prev.minutesAgo) best.set(k2, e)
  }
  const now = coreAt(tq, unitYaw, targetMW, wind)
  for (let g = 0; g <= SCAN_N; g++) {
    const t = (tq - (g * SCAN_MIN) / 60 + 24) % 24
    const c = coreAt(t, unitYaw, targetMW, wind)
    for (let i = 0; i < c.units.length; i++) {
      const di = c.units[i]
      const temp = genTempC(di.powerKw / 5000, t, i)
      const mk = (level: 'warn' | 'crit', rule: string, zh: string, en: string, part: string) =>
        push({
          // BUG-FIX：原式 hashKey(rule)*31 溢出 32 位后与其余项叠加，实测 9360 组
          // (rule,机组,时刻,偏差) 只落到 432 个 key —— 确认一条告警会连带隐藏其它条。
          // 改为按 (rule,机组) 唯一定 key，与 best Map 的去重口径一致。
          key: hashKey(`${rule}|${di.id}`),
          level, rule, zh, en, tid: di.id, part, tStartH: t, minutesAgo: g * SCAN_MIN,
        })
      if (temp > 96) mk('crit', 'TEMP', '发电机绕组超温', 'Generator Winding Overtemp', '发电机')
      else if (temp > 93) mk('warn', 'TEMP', '发电机温度偏高', 'Generator Temp High', '发电机')
      if (Math.abs(di.yawErrDeg) > 24) mk('warn', 'YAWERR', '偏航对风偏差超限', 'Yaw Misalignment', '偏航系统')
    }
    // BUG-FIX（下两条）：key 原先含 Math.round(t*60)，每个扫描周期都生成新 key，
    // 用户"确认"过的告警下一 tick 又以新身份出现 —— 确认按钮等于无效。
    if (Math.abs(gridFrequency(c.totalMW, targetMW, t) - 50) > 0.12)
      push({ key: hashKey('FREQ'), level: 'crit', rule: 'FREQ', zh: '并网点频率越限', en: 'Grid Frequency Deviation', tid: null, part: '并网点', tStartH: t, minutesAgo: g * SCAN_MIN })
    if (c.derateFrac < 0.85)
      push({ key: hashKey('DERATE'), level: 'warn', rule: 'DERATE', zh: `全场限功率运行（指令 ${Math.round(targetMW)} MW）`, en: 'Farm Output Curtailed', tid: null, part: '功率控制', tStartH: t, minutesAgo: g * SCAN_MIN })
  }
  // 当前活跃事件优先展示
  let activeCritNow = false
  for (let i = 0; i < now.units.length; i++) {
    const di = now.units[i]
    void di
    if (genTempC(di.powerKw / 5000, tq, i) > 96) activeCritNow = true
  }
  const list = [...best.values()].map((e) => (activeCritNow && e.level === 'crit' ? { ...e, level: 'crit' as const } : e))
  list.sort((a, b) => a.minutesAgo - b.minutesAgo || a.key - b.key)
  const alarms = list.slice(0, 6)

  return { energyTodayMWh, energyYearEstMWh, cfPct, daySeries, baseSeries, fcSeries, alarms }
}

function hashKey(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 131 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

/** 主入口：HUD 与 3D 共用同一帧（同键同帧，天然一致） */
export function farmFrame(tHours: number, unitYaw: number[], targetMW: number, wind?: WindOverride | null): FarmFrame {
  const tq = Math.round(tHours * 240) / 240 // 0.25 模拟分钟量化
  const core = coreAt(tq, unitYaw, targetMW, wind)
  for (let i = 0; i < core.units.length; i++) {
    const di = core.units[i]
    di.tempC = genTempC(di.powerKw / 5000, tq, i)
    if (di.tempC > 96) di.status = 'alarm'
    else if (core.derateFrac < 0.999 && di.status === 'run') di.status = 'curtail'
  }
  const bucket = Math.floor(tHours * 2) / 2 // 30 模拟分钟
  const hkey = `${bucket}|${yawSig(unitYaw)}|${Math.round(targetMW * 10) / 10}${wind ? `|w${wind.u.toFixed(2)}@${wind.fromDeg.toFixed(1)}` : ''}|r${WAKE_REV}`
  let heavy = heavyCache.get(hkey)
  if (!heavy) {
    heavy = buildHeavy(bucket, unitYaw, targetMW, wind)
    heavyCache.set(hkey, heavy)
    evictOldest(heavyCache, 32)
  }
  const running = core.units.filter((di) => di.status !== 'idle').length
  return {
    tHours: tq,
    windSpeed: wind ? wind.u : windAt(tq).u,
    windFromDeg: wind ? wind.fromDeg : windAt(tq).fromDeg,
    meanRpm: core.meanRpm,
    units: core.units,
    totalMW: core.totalMW,
    availMW: core.availMW,
    derateFrac: core.derateFrac,
    freqHz: gridFrequency(core.totalMW, targetMW, tq),
    qMVar: 0.141 * core.totalMW, // pf≈0.99 → Q=P·tan(acos 0.99)
    runningCount: running,
    wakeLossPct: core.wakeLossPct,
    yawPrecPct: core.yawPrecPct,
    targetPct: targetMW > 0 ? Math.min(133, (core.totalMW / Math.min(targetMW, FARM_RATED_MW)) * 100) : 100,
    ...heavy,
  }
}

// ---- 偏航寻优（闭环叙事核心：目标功率/风况 → 各机偏航角指令）----
// 贪心逐排 + 单机细化（与阵列贪心 [30,20,0] 同族思想；数值是代理模型自己的）
export interface OptimizeResult {
  unitYaw: number[]
  totalMW: number
  baseMW: number
  gainPct: number
  rowOffsets: number[]
}

export function optimizeYaw(tHours: number, seedYaw: number[], wind?: WindOverride | null): OptimizeResult {
  const tq = Math.round(tHours * 240) / 240
  const yaw = [...seedYaw]
  const rowOf = (i: number) => FARM[i].row
  const measure = (y: number[]) => evalCore({ tHours: tq, unitYaw: y, targetMW: FARM_RATED_MW, wind }).totalMW
  const base = measure(yaw)
  const CAND = [-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30]
  for (let r = 0; r < ROW_COUNT; r++) { // R41-A：排数派生（1×3 下每排 1 台，退化为逐机贪心）
    let best = -Infinity
    let bestOff = 0
    for (const off of CAND) {
      for (let i = 0; i < N_UNITS; i++) if (rowOf(i) === r) yaw[i] = off
      const v = measure(yaw)
      if (v > best + 1e-9) { best = v; bestOff = off }
    }
    for (let i = 0; i < N_UNITS; i++) if (rowOf(i) === r) yaw[i] = bestOff
  }
  for (let pass = 0; pass < 2; pass++) {
    for (let i = 0; i < N_UNITS; i++) {
      const cur = yaw[i]
      let best = measure(yaw)
      let bestV = cur
      for (const d of [-6, -4.5, -3, -1.5, 1.5, 3, 4.5, 6]) {
        // BUG-FIX：原上限 ±35 超出滑杆量程 ±30，寻优后滑杆会"顶死在 30"
        // 而 store 实存 34.5，HUD 显示与真实指令不符。收敛到同一量程。
        yaw[i] = Math.max(-30, Math.min(30, cur + d))
        const v = measure(yaw)
        if (v > best + 1e-9) { best = v; bestV = yaw[i] }
      }
      yaw[i] = bestV
    }
  }
  const fin = measure(yaw)
  return {
    unitYaw: yaw.map((v) => Math.round(v * 2) / 2),
    totalMW: fin,
    baseMW: base,
    gainPct: base > 0.01 ? ((fin - base) / base) * 100 : 0,
    rowOffsets: [0, 1, 2].map((r) => yaw[FARM.findIndex((f) => f.row === r)]),
  }
}

/** 机组铭牌（单机信息卡用） */
/**
 * 昼夜天体位置（任务#6：天空/灯光/阴影共用口径，0=北、+x=东、+z=南）：
 * 日出 5:24 / 日落 18:36（演示场址简化），正午高度 54°。
 * dayF：0=夜 → 1=全昼（含晨昏 4°-16° 渐变）；sunDir/moonDir 为指向天体的单位向量。
 */
export function dayNight(tHours: number): {
  dayF: number
  moonF: number
  sunElDeg: number
  sunDir: [number, number, number]
  moonDir: [number, number, number]
} {
  // 整周角 θ：0=日出(5:24)、π=日落(18:36)、2π=次日日出——以 24h 为周期，
  // 24:00→0:00 无缝衔接（旧版方位按 13.2h 半周线性旋转，午夜 wrap 时跳 32.7°，
  // 月亮/影子瞬移的根因；且夜间仰角符号错误导致"半夜挂太阳"）。
  const tt = ((tHours % 24) + 24) % 24
  const th = ((tt - 5.4) / 24) * Math.PI * 2
  const elDeg = 54 * Math.sin(th) // 夜间为负=真在水平面下
  const el = (elDeg * Math.PI) / 180
  const az = ((90 + 180 * (th / Math.PI)) * Math.PI) / 180 // 东→西连续旋转
  const sx = Math.sin(az) * Math.cos(el)
  const sz = -Math.cos(az) * Math.cos(el)
  const sy = Math.sin(el)
  const dayF = Math.min(1, Math.max(0, (elDeg + 4) / 16)) // 连续，触底 0
  // 月亮=日对点：方位 az+180、仰角 −38·sinθ（夜正昼负），日落/日出天然衔接
  // C3 修正：旧式 38·sinθ 在午夜为 −37°（月在地平线下）而正午 +38°（月高悬），
  // 正负写反 —— 夜里 moonF=1 却只能从地平线爬出微光，正是“没有月亮”的根因
  const elM = (-38 * Math.sin(th) * Math.PI) / 180
  const azM = az + Math.PI
  const moonF = Math.min(1, Math.max(0, (-elDeg + 3) / 18))
  // R36b · 月落修复：去掉 y=Math.max(0.06, sin(elM)) 的“构造性托底”。
  // 旧钳制下月亮几何落山后被钉在 3.44° 仰角水平滑行（t=5.4→6.0 方位滑 9°，
  // 仰角恒 0.06）再被昼光门控中途淡出——月不落山、贴地平线漂；月出同理
  // 是“凭空出现在 3.44°”。放开后：满月夜 17:24 东升 / 05:24 西落（与日出同刻，
  /// 与日完美反相），落山时沉进西侧地平线雾带（SkyAurora 下半球融雾）。
  // 灯光侧无需跟随：LightRig 主光方向另有 Math.max(0.045,…) 独立托底；
  // WorldTerrain/TreeField 的月光漫反射对 y<0 连续变暗，月路高光天然归零。
  return {
    dayF,
    moonF,
    sunElDeg: elDeg,
    sunDir: [sx, sy, sz],
    moonDir: [Math.sin(azM) * Math.cos(elM), Math.sin(elM), -Math.cos(azM) * Math.cos(elM)],
  }
}

/**
 * R37 · 太阳色温（连续、仰角驱动）：初升红彤彤 → 慢慢金色 → 渐渐白色。
 * 大气散射规律：仰角越低，直射光穿过的大气路径越长，蓝光被瑞利散射掉越多，
 * 剩下的越红。因此色温必须由【太阳仰角】连续驱动，不能用时间窗编排
 * （v1 的 6-7 点窗口在沿上必然「白→暖→白」突跳，正是用户指出的不真实）。
 *   el ≤ 2°   warm=1（红日贴海）
 *   el 2°→30° 红退金、金退白：6 时 el≈8.4°→0.87（金）、7 时 el≈19.6°→0.29
 *   （淡金）、9 时 el≈44°→0（白）
 *   日落对称（17:24 起同样的红→金过程，无开关）。
 * 出地平线门 smoothstep(-1, 1.5, el)：夜间（日在地下）为 0，月光/夜陆不染暖。
 */
export function sunWarmth(tHours: number): number {
  const elDeg = dayNight(tHours).sunElDeg
  const ss = (a: number, b: number, x: number) => {
    const k = Math.min(1, Math.max(0, (x - a) / (b - a)))
    return k * k * (3 - 2 * k)
  }
  const ramp = 1 - ss(2, 30, elDeg)
  const gate = ss(-1, 1.5, elDeg)
  return ramp * gate
}

export const UNIT_NAMEPLATE = {
  model: 'AEOLUS-5MW（NREL 5MW 参考机组几何）',
  ratedKw: 5000,
  rotorD: 126,
  hubH: 90,
  cutIn: 3.0,
  rated: 11.4,
  cutOut: 25.0,
}
