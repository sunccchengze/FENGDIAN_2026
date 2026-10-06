// ================================================================
// 布局真值源（R41-A · 2026-10-05）
// 全场机组几何 / 排数 / 舵机编排 / 语义锚点下标的**唯一权威**。
// 依据 docs/13 §四（2026-09-19 组会决议）：
//   · 3×3 **不删**（留档 tag `twin-3x3-archive-20260919`），布局可切换（`?layout=1x3`）；
//   · 1×3 = 3×3 **中列的严格子集**（北→南串列，间距 632 m = 5.02D，NREL 5MW D=126m）；
//   · 1×3 下机组重新编号 T01–T03（北→南），语义锚点：power→中机、wake→上游机北侧
//     来流空域、turbine/dot→最近景机、cable→最近景机↔升压站中点。
// 本文件**不得 import terrainUtil**（避免环）：只出纯几何，贴地高度由 terrainUtil 套。
// ================================================================

export type LayoutId = '3x3' | '1x3'

export interface LayoutUnit { id: string; x: number; z: number; row: number; col: number }

export interface LayoutDef {
  id: LayoutId
  /** HUD/文档口径标签，如「阵列 3×3」「串列 1×3」 */
  label: string
  /** 排数：偏航贪心按排推进的上界（1×3 每排 1 台，退化为逐机贪心，逻辑不变） */
  rows: number
  units: LayoutUnit[]
  /** 舵机滑杆对应的机组序号（1-based，沿用旧 SERVOS 口径） */
  servos: number[]
  /** 语义锚点 → units 下标（0-based）；几何套法见 terrainUtil.ANCHOR */
  anchors: { power: number; wake: number; turbine: number; cable: number; dot: number }
  /** 集电回路拓扑：rows = 每排西→东串接后汇站；column = 单回路沿列南下串接 */
  cableTopology: 'rows' | 'column'
}

export const ROW_GAP_M = 632 // 行距 = FLORIS 例程阵列间距（5.02D）
export const COL_GAP_M = 632 // 列距

/** 北→南三排 z（3×3 的 rowsZ；1×3 沿用同三档，只取中列） */
const ROWS_Z = [-1272, -640, -8] as const
const COLS_X = [-732, -100, 532] as const
const MID_COL = 1

function build3x3(): LayoutUnit[] {
  const out: LayoutUnit[] = []
  let k = 0
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      out.push({ id: `T0${k + 1}`, x: COLS_X[c], z: ROWS_Z[r], row: r, col: c })
      k++
    }
  }
  return out
}

export const LAYOUTS: Record<LayoutId, LayoutDef> = {
  '3x3': {
    id: '3x3',
    label: '阵列 3×3',
    rows: 3,
    units: build3x3(),
    // 近大远小中最显眼 5 台：近排左/中、中排左/右、远排中（1-based）
    servos: [6, 7, 3, 5, 1],
    anchors: { power: 4, wake: 7, turbine: 6, cable: 8, dot: 6 },
    cableTopology: 'rows',
  },
  '1x3': {
    id: '1x3',
    label: '串列 1×3',
    rows: 3,
    // 3×3 中列的严格子集；重新编号 T01（北/上游）→ T03（南/最近景）
    units: ROWS_Z.map((z, i) => ({ id: `T0${i + 1}`, x: COLS_X[MID_COL], z, row: i, col: 0 })),
    servos: [1, 2, 3],
    anchors: { power: 1, wake: 0, turbine: 2, cable: 2, dot: 2 },
    cableTopology: 'column',
  },
}

/** 当前生效布局：URL `?layout=1x3` 切换；node 环境可用 TWIN_LAYOUT=1x3（selftest 分布局取证）；
 *  两者皆无时恒为 3×3（留档口径） */
const q =
  typeof location !== 'undefined' && typeof location.search === 'string'
    ? new URLSearchParams(location.search).get('layout')
    : null
const g = globalThis as { process?: { env?: Record<string, string | undefined> } }
const envL = g.process?.env?.TWIN_LAYOUT
export const ACTIVE_LAYOUT: LayoutId = q === '1x3' || (q == null && envL === '1x3') ? '1x3' : '3x3'
export const LAYOUT: LayoutDef = LAYOUTS[ACTIVE_LAYOUT]

/** 热键槽位 i（0-based，恒 9 槽 = 3 机组 × 3 取景语法）→ 布局内机组下标。
 *  3×3：i 本身（T01–T09 各一个机位）；1×3：i % 3（三机各享 高俯/平视/低仰 三个机位，
 *  上→下 = 上游→下游）。消费者：hotkeys.ts 的 CAM_HOTKEYS/diagnoseHotkey。 */
export function unitOf(i: number): number {
  return LAYOUT.id === '3x3' ? i : ((i % LAYOUT.units.length) + LAYOUT.units.length) % LAYOUT.units.length
}
