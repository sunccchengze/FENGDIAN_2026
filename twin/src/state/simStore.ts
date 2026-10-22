/* oxlint-disable react/globals -- startSimClock 是模块级外部时钟驱动，非组件内可变全局（docs/08 D2） */
import { create } from 'zustand'
import { FARM, SERVOS } from '../scene/terrainUtil'
import { FREEZE } from '../scene/freeze.ts'
import { optimizeYaw, farmFrame, FARM_RATED_MW, N_UNITS, type FarmFrame } from '../data/farmSim'
import { generateAnomalyPlan, applyAnomalyToFrame, type AnomalyPlan } from '../data/anomaly'
import { createYawBank, stepYawBank, bankActual, YAW_CMD_LIMIT_DEG, type YawBank } from '../core/control/yawDrive'

// ================================================================
// 全局仿真控制状态（zustand）
// ----------------------------------------------------------------
// 这里只放 *控制状态*（时间轴/偏航指令/目标功率/选择/告警确认/画质档）；
// 全部 *运行读数* 由 data/farmSim.farmFrame(t, yaw, target) 纯函数派生，
// HUD 与 3D 场景读同一帧 —— 这是评审 A5"数据全死、零联动"的根因修复。
// ================================================================

export type QualityTier = 'high' | 'medium' | 'low'

export interface SimState {
  // 时间轴（24h 循环；真实 50s = 模拟 24h，与原图 00:50 口径一致）
  tHours: number
  playing: boolean
  togglePlay: () => void
  seek: (h: number) => void

  // 全场偏航【指令】Δψ（滑杆/寻优下发；0° = 对风。量程 ±30°；长度 = N_UNITS，R41-A 派生）
  unitYaw: number[]
  setUnitYaw: (i: number, v: number) => void
  // 全场偏航【实际】Δψ（P2 执行器：0.3°/s 速率限制 + ±5°/±3° 死区滞环 + 1.5s 指令滤波）
  // —— 物理内核 / 三维机头 / 尾流偏折 / HUD 读数全部读 actYaw，unitYaw 只是指令。
  actYaw: number[]
  /** 偏航执行器组（运行时单例；startSimClock 每 tick 推进） */
  yawBank: YawBank

  // 需求功率闭环（研究内容③：输入功率 → 输出各机偏航角/限功率）
  targetMW: number // = FARM_RATED_MW 即不限（R41-A 派生）
  setTargetMW: (v: number) => void

  // 寻优结果回显（HUD 状态行）
  optimizeNote: string | null
  optimizeStamp: number
  runOptimize: () => void
  resetYaw: () => void

  // T9 · 声场（程序化 Web Audio：海浪 / 拍岸碎浪 / 风机切风 + 传动链音调 / HRTF 3D 定位）
  audioOn: boolean
  audioVol: number // 0..1
  /** 用户在开场巡航期间按过声音按钮：手势已发生但 introDone 后需补 ensure() */
  audioGesturePending: boolean
  setAudioOn: (v: boolean) => void
  setAudioVol: (v: number) => void

  // 单机选择（矩阵点击 ↔ 3D 高亮 ↔ 信息卡）
  airflow: boolean
  setAirflow: (v: boolean) => void
  selected: number | null
  setSelected: (i: number | null) => void

  // 已确认告警（key 列表）
  ackedAlarms: number[]
  ackAlarm: (k: number) => void

  // 画质档（自适应 + 手动覆盖）
  quality: QualityTier
  qualityAuto: boolean
  setQuality: (q: QualityTier, manual?: boolean) => void

  // 开场巡航：可跳过（评审 C5：34s 不可跳过是答辩事故）
  introDone: boolean
  skipIntro: () => void

  // 随机异常事件（2~5 天一次，完全随机；演示剧本）
  anomalyCycle: number
  anomalyNextCycle: number
  anomalyPlan: AnomalyPlan | null
  anomalyActive: AnomalyPlan | null
  anomalyFired: boolean
  anomalyModal: { plan: AnomalyPlan; auto: boolean } | null
  ensureAnomalyPlan: (cycle: number) => void
  stepAnomaly: (prevH: number, nextH: number) => void
  repairAnomaly: (auto: boolean) => void
  closeAnomalyModal: () => void

  // WebGL 兜底（D6）
  fatal: string | null
  setFatal: (m: string | null) => void
}

const ZERO_YAW = new Array<number>(N_UNITS).fill(0)
/** 偏航执行器组：全场 N_UNITS 机，指令 0°、实际 0°（P2；R41-A 派生） */
const YAW_BANK = createYawBank(N_UNITS, ZERO_YAW)
const randomAnomalyGap = () => 2 + Math.floor(Math.random() * 4) // 2~5 天
const initialGap = randomAnomalyGap()

export const useSim = create<SimState>((set, get) => ({
  // 默认进入时刻改为 t=6（日出后高清高功率段）：与《日间氛围_参考基线》
  // 06:12 帧一致，HUD 首屏即展示 ~14MW 高功率 + 低角度晨光最长光影梯度；
  // 避免默认 t=10 落在日内风速低谷（~5.6MW）让人误以为“功率被降低”。
  tHours: 6,
  playing: true,
  togglePlay: () => set((s) => ({ playing: !s.playing })),
  seek: (h) => set({ tHours: ((h % 24) + 24) % 24 }),

  unitYaw: [...ZERO_YAW],
  actYaw: [...ZERO_YAW],
  yawBank: YAW_BANK,
  setUnitYaw: (i, v) =>
    set((s) => {
      const unitYaw = [...s.unitYaw]
      unitYaw[i] = Math.max(-YAW_CMD_LIMIT_DEG, Math.min(YAW_CMD_LIMIT_DEG, v)) // 与执行器/HUD 同一量程 ±30°
      return { unitYaw }
    }),

  targetMW: FARM_RATED_MW,
  setTargetMW: (v) => set({ targetMW: Math.max(4, Math.min(FARM_RATED_MW, v)) }), // R41-A：量程由布局额定派生（3×3=45 MW，1×3=15 MW）

  optimizeNote: null,
  optimizeStamp: 0,
  runOptimize: () => {
    const s = get()
    const r = optimizeYaw(s.tHours, s.unitYaw)
    // 口径诚实化：optimizeYaw 的 baseMW/totalMW 都是「满发、不限功率」口径，
    // 且 baseMW 是「当前偏航」而非「零偏航基准」——因此增益表示的是
    // 由用户当前偏航 → 代理最优偏航的满发收益，不是「较指令前目标功率收益」，
    // 限功率时实际可用收益会被目标功率约束削平。
    const delta = r.totalMW - r.baseMW
    const capped = s.targetMW < FARM_RATED_MW
    const capNote = capped
      ? `（当前限至 ${s.targetMW.toFixed(1)} MW，实际收益受功率指令约束）`
      : '（不限功率/满发口径）'
    set({
      unitYaw: r.unitYaw,
      optimizeStamp: Date.now(),
      optimizeNote:
        delta > 0.005
          ? `寻优完成：指令已下发（偏航电机 0.3°/s、±5° 死区，逐机到位约 ${yawSlewSeconds(r.unitYaw, get().actYaw).toFixed(0)} s）；满发口径全场 ${(r.totalMW * 1000).toFixed(0)} kW，由当前偏航 → 最优配置 +${(delta * 1000).toFixed(0)} kW / +${r.gainPct.toFixed(1)}%${capNote}【FLORIS 4.6.6 GCH 内核】`
          : `当前偏航已处于 GCH 模型最优附近，满发口径增益 ${(Math.max(0, delta) * 1000).toFixed(0)} kW${capNote}【FLORIS 4.6.6 GCH 内核】`,
    })
  },
  resetYaw: () =>
    set({
      unitYaw: [...ZERO_YAW],
      optimizeNote: `偏航指令已复位：全场对风 0°（基准工况）；执行器回零约 ${yawSlewSeconds(ZERO_YAW, get().actYaw).toFixed(0)} s`,
      optimizeStamp: Date.now(),
    }),

  audioOn: false,
  audioVol: 0.7,
  audioGesturePending: false,
  setAudioOn: (v) => set({ audioOn: v }),
  setAudioVol: (v) => set({ audioVol: Math.max(0, Math.min(1, v)) }),

  airflow: true,
  setAirflow: (v: boolean) => set({ airflow: v }),

  selected: null,
  setSelected: (i) => set({ selected: i }),

  ackedAlarms: [],
  ackAlarm: (k) =>
    set((s) => (s.ackedAlarms.includes(k) ? {} : { ackedAlarms: [...s.ackedAlarms, k] })),

  quality: 'medium',
  qualityAuto: true,
  setQuality: (q, manual) => set(manual ? { quality: q, qualityAuto: false } : { quality: q }),

  introDone: false,
  skipIntro: () => set({ introDone: true }),

  // —— 随机异常剧本（2~5 天一次）——
  anomalyCycle: 0,
  anomalyNextCycle: initialGap,
  anomalyPlan: null,
  anomalyActive: null,
  anomalyFired: false,
  anomalyModal: null,
  ensureAnomalyPlan: (cycle) =>
    set((s) => {
      // 未到下次异常日：不生成剧本
      if (cycle < s.anomalyNextCycle) {
        if (s.anomalyPlan !== null || s.anomalyCycle !== cycle) {
          return { anomalyCycle: cycle, anomalyPlan: null }
        }
        return {}
      }
      if (s.anomalyPlan && s.anomalyPlan.cycle === cycle) return { anomalyCycle: cycle }
      return { anomalyCycle: cycle, anomalyPlan: generateAnomalyPlan(cycle, s.tHours) }
    }),
  stepAnomaly: (prevH, nextH) =>
    set((s) => {
      const wrapped = nextH < prevH && prevH - nextH > 12
      if (wrapped) {
        const cycle = s.anomalyCycle + 1
        // 仍未到下次异常日：清空剧本
        if (cycle < s.anomalyNextCycle) {
          return {
            anomalyCycle: cycle,
            anomalyPlan: null,
            anomalyActive: null,
            anomalyFired: false,
            anomalyModal: s.anomalyModal,
          }
        }
        // 到达或超过预定异常日：若无剧本则生成
        const needPlan = !s.anomalyPlan || s.anomalyPlan.cycle !== cycle
        return {
          anomalyCycle: cycle,
          anomalyPlan: needPlan ? generateAnomalyPlan(cycle, nextH) : s.anomalyPlan,
          anomalyActive: null,
          anomalyFired: false,
          anomalyModal: s.anomalyModal,
        }
      }
      const p = s.anomalyPlan
      if (!p || s.anomalyActive || s.anomalyFired) return {}
      if (s.anomalyCycle < s.anomalyNextCycle) return {}
      const crossed = nextH > prevH && p.triggerH > prevH && p.triggerH <= nextH
      if (!crossed) return {}
      return { anomalyActive: p, anomalyFired: true }
    }),
  repairAnomaly: (auto) =>
    set((s) => {
      const p = s.anomalyActive
      if (!p) return {}
      const gap = randomAnomalyGap()
      return {
        anomalyActive: null,
        anomalyModal: { plan: p, auto },
        anomalyNextCycle: s.anomalyCycle + gap,
        anomalyPlan: null,
        anomalyFired: false,
      }
    }),
  closeAnomalyModal: () => set({ anomalyModal: null }),

  fatal: null,
  setFatal: (m) => set({ fatal: m }),
}))

/** 指令组 → 最慢一台的到位时间 (s)：HUD 提示用（P2 执行器口径） */
function yawSlewSeconds(cmd: number[], actual: number[]): number {
  let worst = 0
  for (let i = 0; i < cmd.length; i++) {
    const err = Math.abs((cmd[i] ?? 0) - (actual[i] ?? 0))
    if (err <= 5) continue // 死区内：电机按设计不动
    worst = Math.max(worst, err / 0.3 + 1.2 * 1.6)
  }
  return worst
}

/** 偏航执行器 i ↔ 机组下标（唯一映射，评审 D7 的"双映射地雷"已拆除） */
export const SERVO_UNIT: number[] = [...SERVOS]

/** 仿真时钟驱动（真实 50s = 模拟 24h）。main.tsx 启动一次。 */
let clockStarted = false
export function startSimClock() {
  if (clockStarted) return
  clockStarted = true
  if (FREEZE) return // R42 freeze：取证模式不进仿真时钟（tHours 定格 ?t=，偏航执行器不动）
  let last = performance.now()
  setInterval(() => {
    const now = performance.now()
    const dt = (now - last) / 1000
    last = now
    const s = useSim.getState()
    // P2 · 偏航执行器推进（真实时间口径：0.3°/s 是墙钟速率，不随 24h/50s 的
    // 仿真倍率缩放 —— 否则开场 43s 里机舱会转完 30° 又停，看着像故障）。
    // 暂停（playing=false）与 WebGL 失效时一并冻结，与仿真时钟同一门控。
    if (s.playing && !s.fatal) {
      stepYawBank(s.yawBank, s.unitYaw, dt)
      const act = bankActual(s.yawBank)
      let changed = false
      for (let i = 0; i < act.length; i++) if (act[i] !== s.actYaw[i]) { changed = true; break }
      if (changed) useSim.setState({ actYaw: act })
    }
    // 开场运镜期间（introDone=false）不推进仿真时间：
    // 否则开场 34~43s（≈大半天）里 HUD 会从默认高功率飞快滑到日内低谷，
    // 用户开场一结束就看到“功率下降”。开场结束后恢复播放（真实 50s=24h）。
    if (!s.introDone) return
    if (s.playing && !s.fatal) {
      const nextT = (s.tHours + dt * (24 / 50)) % 24
      useSim.setState({ tHours: nextT })
    }
  }, 100)
}

// ---- 帧访问封装 ----
// HUD：按 store tick（100ms）取帧；键控缓存保证同一 tick 内多组件一帧。
let hudKey = ''
let hudFrame: FarmFrame | null = null
export function useFarmFrame(): FarmFrame {
  const tHours = useSim((s) => s.tHours)
  // P2：物理读【实际偏航】（actYaw，执行器输出，已量化 0.5°），不读指令 ——
  // 指令与实际之间从此有真实的分钟级滞后，功率随偏航到位逐步爬升。
  const actYaw = useSim((s) => s.actYaw)
  const targetMW = useSim((s) => s.targetMW)
  const anomaly = useSim((s) => s.anomalyActive)
  const key = `${tHours}|${actYaw.join(',')}|${targetMW}|${anomaly?.id ?? ''}`
  if (key !== hudKey || !hudFrame) {
    hudKey = key
    hudFrame = applyAnomalyToFrame(farmFrame(tHours, actYaw, targetMW), anomaly)
  }
  return hudFrame
}

/** 3D 用：每帧即时读数（useFrame 内直读，绕开 React setState） */
export function farmFrameNow(): FarmFrame {
  const s = useSim.getState()
  return applyAnomalyToFrame(farmFrame(s.tHours, s.actYaw, s.targetMW), s.anomalyActive)
}

/** 机组 id ↔ 下标 */
export const unitIndexById = new Map(FARM.map((f, i) => [f.id, i] as const))
