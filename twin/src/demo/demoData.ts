// ================================================================
// R44 演示数据层（?demo=1 · 9.19 §二 七步流程）
// ----------------------------------------------------------------
// 两路数据，界面上永不混写（§二 界面纪律）：
//   参考模型 = FLORIS 4.6.6 GCH tandem3 oracle（生成件，勿手改）→ 【实测·FLORIS】
//   快速模型 = 本仓 TS GCH 内核（与 FLORIS GCH 同方程的 TS 移植，
//              41 工况偏差 ≲1e-12 kW，浮点噪声级）→ 【代理·GCH 内核】
// PINN 换入点 = inferCase()（推理计时钩子）：李锦飞 PINN 就绪后，
// 仅替换本函数内部，参考值 / 对比 / 耗时口径全部不变。
//
// 两条表述红线（§二 原文，界面文案逐字遵守）：
//   · 轮毂高度截面是展示范围，不能自动解释为二维物理问题；
//   · 第一版不宣称真实风场在线控制或电网跟踪能力。
// ================================================================

import { ORACLE } from '../data/oracle/florisGchOracle.ts'
import { evaluateFarmScene } from '../core/physics/evalFarm.ts'
import { sampleHubPlane } from '../core/physics/gch.ts'
import { LAYOUTS } from '../scene/layouts.ts'

// ---- 工况（9.19 §二：输入范围明确显示；超出已验证范围时提示）----
export const DEMO_WIND = { uInf: 8.0, fromDeg: 0.0, ti: 0.06 } as const
/** FLORIS tandem3 oracle 的已验证范围（唯一工况，R42 生成） */
export const VERIFIED_RANGE = { uInf: 8.0, fromDeg: 0.0, ti: 0.06 } as const
export const TAG_REF = '【实测·FLORIS 4.6.6】'
export const TAG_FAST = '【代理·GCH 内核】'

// ---- 场景几何（1×3 串列 = 3×3 中列，T01 北/上游 → T03 南）----
export const DEMO_UNITS = LAYOUTS['1x3'].units
export const SCENE_X = DEMO_UNITS.map((u) => u.x)
export const SCENE_Z = DEMO_UNITS.map((u) => u.z)
const FLORIS_X = SCENE_X.slice()
const FLORIS_Y = SCENE_Z.map((z) => -z) // 场景 +z=南 → FLORIS y=北
export const DEMO_SCENE = { x: FLORIS_X.slice(), z: SCENE_Z.slice() }

// ---- 图表配色常量（界面纪律：参考=蓝 / 快速模型=琥珀，永不混色）----
export const CC = {
  axis: 'rgba(110,215,255,0.45)',
  grid: 'rgba(110,215,255,0.14)',
  text: '#8fb8cf',
  textHi: '#d7f6ff',
  ref: '#38bdf8',
  fast: '#fbbf24',
  none: '#38bdf8',
  opt: '#fbbf24',
  err: '#f87171',
}

// ---- 固定色标（§二 红线：不得通过自动改变色标夸大变化）----
// 全部为编译期常量；任何图表不得依据数据范围自动缩放。
export const SCALES = {
  /** 流场 u (m/s)，含尾流核心（近场可深至 ~0.3）与净风 8.0 */
  u: [0, 8] as const,
  /** 功率 (kW)，单机 ≤5000 但本工况三机 ≤1500、总 ≤3600 */
  p: [0, 3600] as const,
  /** 有效风速 (m/s) */
  uEff: [4, 9] as const,
  /** 单机功率偏差 (kW)：快速模型=同方程移植，偏差为浮点噪声级 → 对数固定十进位 */
  errKwLog: [1e-14, 1e-9] as const,
  /** 单工况求解耗时 (ms)：内核 ~0.1-1 / FLORIS ~5-10（本机实测）→ 对数固定十进位 */
  msLog: [0.05, 20] as const,
}

// ---- 流场网格（FLORIS 系；北在上 = +y 朝上）----
export const FIELD_N = 33
export const FIELD_XS: number[] = []
export const FIELD_YS: number[] = []
for (let i = 0; i < FIELD_N; i++) FIELD_XS.push(-450 + (700 * i) / (FIELD_N - 1))
for (let j = 0; j < FIELD_N; j++) FIELD_YS.push(-500 + (2000 * j) / (FIELD_N - 1))

// ---- 快速模型推理（PINN 换入点 · 推理计时钩子）----
export interface InferResult {
  totalKw: number
  p: number[]
  uAvg: number[]
  ms: number
}
export function inferCase(yaw: readonly number[]): InferResult {
  const t0 = performance.now()
  const r = evaluateFarmScene(DEMO_SCENE, { ...DEMO_WIND }, yaw.slice())
  const ms = performance.now() - t0
  return {
    totalKw: r.totalKw,
    p: r.turbines.map((t) => t.powerKw),
    uAvg: r.turbines.map((t) => t.uAvg),
    ms,
  }
}

// ---- 41 工况对照表（§七 验收：≥20 个独立测试工况）----
// 快速模型为闭式内核（无训练过程、未对本工况组拟合）→ 41 工况全部可视为
// 未参与训练的独立测试工况（§二 步骤 6 的口径，界面如实标注）。
export interface DemoCase {
  id: string
  label: string
  yaw: readonly number[]
  refTotalKw: number
  refP: readonly number[]
  refUEff: readonly number[]
  refVel: readonly number[]
  refSec: number
  predTotalKw: number
  predP: number[]
  predUAvg: number[]
  predMs: number
  errKw: number
  errPct: number
  maxUnitErrKw: number
  maxUnitErrUEff: number
}

const fmtYaw = (v: number) => (v > 0 ? `+${v}` : `${v}`)

export function buildCases(): DemoCase[] {
  const t3 = ORACLE.tandem3
  const out: DemoCase[] = []
  const add = (
    id: string, label: string, yaw: readonly number[],
    ref: { totalKw: number; p: readonly number[]; uEff: readonly number[]; vel: readonly number[]; sec: number },
  ): void => {
    const pred = inferCase(yaw)
    let maxP = 0, maxU = 0
    for (let i = 0; i < 3; i++) {
      maxP = Math.max(maxP, Math.abs(pred.p[i] - ref.p[i]))
      maxU = Math.max(maxU, Math.abs(pred.uAvg[i] - ref.uEff[i]))
    }
    const errKw = pred.totalKw - ref.totalKw
    out.push({
      id, label, yaw: [...yaw],
      refTotalKw: ref.totalKw, refP: ref.p, refUEff: ref.uEff, refVel: ref.vel, refSec: ref.sec,
      predTotalKw: pred.totalKw, predP: pred.p, predUAvg: pred.uAvg, predMs: pred.ms,
      errKw, errPct: (errKw / ref.totalKw) * 100,
      maxUnitErrKw: maxP, maxUnitErrUEff: maxU,
    })
  }
  const refOf = (o: { totalKw: number; pKw: readonly number[]; uEff: readonly number[]; vel: readonly number[]; sec: number }) =>
    ({ totalKw: o.totalKw, p: o.pKw, uEff: o.uEff, vel: o.vel, sec: o.sec })
  add('none', '基准 · 零偏航', [0, 0, 0], refOf(t3.none))
  for (const c of t3.unified) add(`unified${fmtYaw(c.yaw)}`, `统一偏航 ${fmtYaw(c.yaw)}°（三机同角）`, [c.yaw, c.yaw, c.yaw], refOf(c))
  for (const c of t3.upstreamScan) add(`up${fmtYaw(c.yaw)}`, `上游偏航 ${fmtYaw(c.yaw)}°（仅 T01）`, [c.yaw, 0, 0], refOf(c))
  for (const c of t3.midstreamScan) add(`mid${fmtYaw(c.yaw)}`, `中游偏航 ${fmtYaw(c.yaw)}°（仅 T02）`, [0, c.yaw, 0], refOf(c))
  add('greedy', '逐机贪心 [30,25,0]', t3.greedy.yaw, refOf(t3.greedy))
  return out
}

export const findCase = (cases: DemoCase[], id: string): DemoCase => {
  const c = cases.find((x) => x.id === id)
  if (!c) throw new Error(`demo case not found: ${id}`)
  return c
}

// ---- 快速模型逐机贪心（与 oracle greedy 同定义：上游→下游，CAND 5° 网格）----
export interface OptStage {
  stage: 'upstream' | 'midstream' | 'downstream'
  stageZh: string
  candBest: number
  yaw3: number[]
  totalKw: number
  ms: number
}
export interface OptimizeRun {
  stages: OptStage[]
  yaw: number[]
  totalKw: number
  ms: number
  calls: number
}
const CAND = [-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30]
export function runGreedy(): OptimizeRun {
  const t0 = performance.now()
  const stages: OptStage[] = []
  let calls = 0
  let best1 = CAND[0], best2 = CAND[0], best3 = CAND[0]
  let v1 = -Infinity, v2 = -Infinity, v3 = -Infinity
  for (const a of CAND) {
    const r = inferCase([a, 0, 0]); calls++
    if (r.totalKw > v1) { v1 = r.totalKw; best1 = a }
  }
  const r1 = inferCase([best1, 0, 0]); calls++
  stages.push({ stage: 'upstream', stageZh: '上游 T01', candBest: best1, yaw3: [best1, 0, 0], totalKw: r1.totalKw, ms: 0 })
  for (const b of CAND) {
    const r = inferCase([best1, b, 0]); calls++
    if (r.totalKw > v2) { v2 = r.totalKw; best2 = b }
  }
  const r2 = inferCase([best1, best2, 0]); calls++
  stages.push({ stage: 'midstream', stageZh: '中游 T02', candBest: best2, yaw3: [best1, best2, 0], totalKw: r2.totalKw, ms: 0 })
  for (const c of CAND) {
    const r = inferCase([best1, best2, c]); calls++
    if (r.totalKw > v3) { v3 = r.totalKw; best3 = c }
  }
  const r3 = inferCase([best1, best2, best3]); calls++
  stages.push({ stage: 'downstream', stageZh: '下游 T03', candBest: best3, yaw3: [best1, best2, best3], totalKw: r3.totalKw, ms: 0 })
  const ms = performance.now() - t0
  return { stages, yaw: [best1, best2, best3], totalKw: r3.totalKw, ms, calls }
}

// ---- 流场（轮毂高度水平截面 · 展示口径）----
let fieldMsAccum = 0
export function hubField(yaw: readonly number[]): Float64Array {
  const t0 = performance.now()
  const u = sampleHubPlane(FLORIS_X, FLORIS_Y, { ...DEMO_WIND }, yaw.slice(), FIELD_XS, FIELD_YS)
  fieldMsAccum += performance.now() - t0
  return u
}
export function takeFieldMs(): number {
  const v = fieldMsAccum
  fieldMsAccum = 0
  return v
}

// ---- 汇总（步骤 7 导出用）----
export interface DemoSummary {
  caseId: string
  timestamp: string
  dataSource: Record<string, string>
  config: { wind: { uInf: number; fromDeg: number; ti: number }; layout: string; baselineYaw: number[]; optimizedYaw: number[] }
  results: {
    baseline: { refKw: number; predKw: number; refP: number[]; predP: number[] }
    optimized: { refKw: number; predKw: number; refP: number[]; predP: number[]; gainPctRef: number; gainPctPred: number }
    caseCount: number
    maxUnitErrKw: number
    nmaeTotalKwPct: number
    cases: Array<{ id: string; label: string; yaw: number[]; refKw: number; predKw: number; errKw: number; refSec: number; predMs: number }>
  }
  timings: { inferMs: number; optimizeMs: number | null; reviewMs: number | null; fieldMs: number }
  notes: string[]
}
export function buildSummary(
  cases: DemoCase[], optimized: DemoCase,
  timings: { inferMs: number; optimizeMs: number | null; reviewMs: number | null },
): DemoSummary {
  let maxUnit = 0, sumAbs = 0, sumRef = 0
  for (const c of cases) {
    maxUnit = Math.max(maxUnit, c.maxUnitErrKw)
    sumAbs += Math.abs(c.errKw)
    sumRef += c.refTotalKw
  }
  const none = findCase(cases, 'none')
  return {
    caseId: 'tandem3-demo-2026-10-05',
    timestamp: new Date().toISOString(),
    dataSource: {
      参考模型: 'FLORIS 4.6.6 GCH（tandem3 oracle；docs/research/oracle/floris_gch_oracle_v1.json；生成脚本 generate_floris_gch_oracle.py）',
      快速模型: '本仓 TS GCH 内核（与 FLORIS GCH 同方程移植，41 工况偏差 ≲1e-12 kW；李锦飞 PINN 就绪后经 inferCase() 换入）',
      场景: '1×3 串列（T01–T03，间距 632 m；NREL 5MW 参考机组 D=125.88 m，HH=90 m；场景系 +x=东 +z=南）',
    },
    config: {
      wind: { ...DEMO_WIND },
      layout: '1x3',
      baselineYaw: [0, 0, 0],
      optimizedYaw: [...optimized.yaw],
    },
    results: {
      baseline: { refKw: none.refTotalKw, predKw: none.predTotalKw, refP: [...none.refP], predP: none.predP },
      optimized: {
        refKw: optimized.refTotalKw, predKw: optimized.predTotalKw,
        refP: [...optimized.refP], predP: optimized.predP,
        gainPctRef: (optimized.refTotalKw / none.refTotalKw - 1) * 100,
        gainPctPred: (optimized.predTotalKw / none.predTotalKw - 1) * 100,
      },
      caseCount: cases.length,
      maxUnitErrKw: maxUnit,
      nmaeTotalKwPct: (sumAbs / sumRef) * 100,
      cases: cases.map((c) => ({
        id: c.id, label: c.label, yaw: [...c.yaw],
        refKw: c.refTotalKw, predKw: c.predTotalKw, errKw: c.errKw,
        refSec: c.refSec, predMs: c.predMs,
      })),
    },
    timings: { ...timings, fieldMs: takeFieldMs() },
    notes: [
      '轮毂高度截面是展示范围，不能自动解释为二维物理问题（9.19 §二 红线）。',
      '第一版不宣称真实风场在线控制或电网跟踪能力（9.19 §二 红线）。',
      '快速模型=FLORIS GCH 同方程 TS 移植（代理 PINN），误差为浮点噪声级；PINN 换入后误差字段自动反映真实模型误差。',
      'refSec 为 FLORIS fm.run() 本机墙钟（含模型构建前的一次性成本另计）；predMs 为浏览器端内核实测。',
    ],
  }
}

export { ORACLE }
