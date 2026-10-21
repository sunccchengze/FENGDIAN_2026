// ================================================================
// 世界真值源（R4 · 原图像素级还原版）
// 地形 / 机位 / 升压站 / 相机 / 锚点 —— 全场景唯一权威
// 构图对齐 docs/research/mockups/user_original_微信图片_174_2.png：
//   远景排 → 中景排 → 近景排（近大远小）；升压站位于画面右下；
//   天际线 ≈ 画面上缘 12%；全场冰青全息基调
// ================================================================

import { LAYOUT } from './layouts.ts'

function makeNoise(seed = 7) {
  const hash = (x: number, y: number) => {
    const s = Math.sin(x * 127.1 + y * 311.7 + seed * 17.43) * 43758.5453
    return s - Math.floor(s)
  }
  const smooth = (t: number) => t * t * (3 - 2 * t)
  const n2 = (x: number, y: number) => {
    const xi = Math.floor(x), yi = Math.floor(y)
    const xf = x - xi, yf = y - yi
    const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1)
    const u = smooth(xf), v = smooth(yf)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
  }
  const fbm = (x: number, y: number, oct = 4) => {
    let v = 0, amp = 0.5, fx = x, fy = y
    for (let i = 0; i < oct; i++) { v += amp * n2(fx, fy); fx *= 2.03; fy *= 2.03; amp *= 0.52 }
    return v
  }
  const ridged = (x: number, y: number, oct = 4) => {
    let v = 0, amp = 0.55, fx = x, fy = y
    for (let i = 0; i < oct; i++) {
      const r = 1 - Math.abs(2 * n2(fx, fy) - 1)
      v += amp * r * r
      fx *= 2.11; fy *= 2.11; amp *= 0.5
    }
    return v
  }
  return { n2, fbm, ridged }
}
const N = makeNoise()
const clamp01 = (t: number) => Math.min(1, Math.max(0, t))
const smoothstep = (e0: number, e1: number, x: number) => {
  const t = clamp01((x - e0) / (e1 - e0))
  return t * t * (3 - 2 * t)
}

// ---- 地形：开放外海 + 两相邻侧陆地（第 32 轮 A-round3：复杂地貌奇观）----
// 第 31 轮的海岸是单层 fbm 直线切割带（wobble ±320m），岬湾尺度单一；
// 本轮升级为「7 层噪声蜿蜒 + 大小高斯弧岬湾 + 双侧钳制 + 不规则离岸群岛/海岬」——
//  · 海域张角 100°（西岸线绕北角向南偏东 10°，不再是横平竖直的 90°）；
//  · 南(+z)、东(+x) 两【相邻侧】仍完全开放为纯海（无岸）；
//  · 北(-z)、西(-x) 为陆地，海岸线多尺度曲折（50m 微齿 ~ 3km 大岬湾）；
//  · 全部 9 机与升压站仍位于海中央（600m 机组净距硬约束，见 cap/bayCap）；
//  · 内陆远山加高锐化（300~550m 奇崛山体，雪冠载体更大）；
//  · 主峰直插云霄（1100m 级）+ 域扭曲山脊谷地 + 丘陵盆地；
//  · 峡湾水道深切北岸（长 1.6km、宽 220~560m，两壁陡峭，海岬变湾中岛）；
//  · 海蚀柱群（离岸峭岩，浪蚀奇观）；
//  · 海床仍只保留极低幅微地貌（±2m），贴地稳定。
// 注：R32-R34 系回退后重做（见 docs/research/R32-R34-改造提示词.md），
//     因原 commit 不在本快照内，函数名与原实现未必逐字一致，但几何约束等价。
/** 海上风电场中心（保持旧取景重心；本版地形不再以之为圆心） */
export const FARM_CENTER = { x: -100, z: -640 } as const

/** 北向(-z)海岸线基准：dNorth = -z + wobbleN(x) - CN0，>0 为陆侧 */
const CN0 = 2100
/** 西向(-x)海岸线基准：dWest = -x + wobbleW(z) - CW0，>0 为陆侧 */
const CW0 = 1750
/** 西岸整体倾角：tan10°，绕北角拐点向南偏东 —— 海域张角由 90° 打开到 100° */
const TILT10 = 0.1763
/** 倾角枢轴 z（北角拐点，与北岸标称衔接） */
const TILT_PIVOT_Z = -2100
/** 海岸抬升基础带宽（round6：520→1400，海滩平原铺开；round7 起实际宽度按位置随机）。
 *  岸线 0 等值线位置不动，机组净距不受影响。 */
export const RAMP_W = 1400
/** 有效过渡带宽（米）：低频噪声分区（0.55~1.55 倍，770~2170m）——
 *  有的岸段短促、有的绵长，坡度和长度都因地而异（round7）。 */
function rampAt(x: number, z: number): number {
  return RAMP_W * (0.5 + 1.1 * N.fbm(x * 0.00035 + 3.3, z * 0.00035 - 8.8, 2))
}
/** 蜿蜒钳制（cap/bayCap）：向陆最多 -380m；向海（bay 侧）北岸 +200 / 西岸 +350 ——
 *  与 CN0/CW0 联立保证：9 机 + 升压站处 landMask ≡ 0，且 600m 环内零沾陆
 *  （实测最近沾陆约 700m＠T09——东南卫星小岛方向，本土岸线更远；
 *  100m 粒度环扫；selftest R32-A1 断言锁定）。 */
const WOB_LAND = -380
const BAYCAP_N = 200
const BAYCAP_W = 350

/** 5 层噪声蜿蜒基底（fbm 主波 + 次级 + 脊线岬角 + 微细节） */
function wobbleBase(x: number, s: number): number {
  const n5 = N.fbm(x * 0.00058 + s, 40.0, 3) - 0.5
  const n4 = N.fbm(x * 0.0016 + s * 2.1, 7.7, 3) - 0.5
  const n3 = N.ridged(x * 0.0009 + s * 0.7, 21.0, 2) - 0.5
  const n2 = N.fbm(x * 0.0042 + s * 3.7, 3.1, 2) - 0.5
  const n1 = N.fbm(x * 0.009 + s * 5.3, 9.4, 2) - 0.5   // 小岬湾（~110m）
  const n0 = N.fbm(x * 0.021 + s * 7.9, 1.2, 1) - 0.5   // 微齿（~50m）
  return n5 * 2 * 260 + n4 * 2 * 90 + n3 * 2 * 70 + n2 * 2 * 25 + n1 * 2 * 38 + n0 * 2 * 16
}

/** 北岸蜿蜒：基底 + 高斯弧（西段岬/东段岬/中部湾），再双侧钳制 */
function wobbleN(x: number): number {
  const g1 = Math.exp(-(((x + 1500) / 700) ** 2)) * 220 // 西段岬（向海）
  const g2 = Math.exp(-(((x - 800) / 900) ** 2)) * 260  // 东段岬（向海）
  const bay = Math.exp(-(((x + 200) / 600) ** 2)) * 180 // 中部大湾（向陆收）
  const g3 = Math.exp(-(((x - 300) / 260) ** 2)) * 120  // 东段小岬（向海）
  const bay2 = Math.exp(-(((x - 1300) / 300) ** 2)) * 130 // 东段小湾（向陆收）
  const raw = wobbleBase(x, 5.7) + g1 + g2 + g3 - bay - bay2
  return Math.max(WOB_LAND, Math.min(BAYCAP_N, raw))
}

/** 西岸蜿蜒：基底 + 高斯弧（北段岬/南段湾），再双侧钳制 */
function wobbleW(z: number): number {
  const g1 = Math.exp(-(((z + 1800) / 800) ** 2)) * 240 // 北段岬（向海）
  const bay = Math.exp(-(((z - 200) / 700) ** 2)) * 200  // 南段大湾（向陆收）
  const g2 = Math.exp(-(((z - 900) / 300) ** 2)) * 130  // 中段小岬（向海）
  const bay2 = Math.exp(-(((z + 800) / 350) ** 2)) * 120 // 北段小湾（向陆收）
  const raw = wobbleBase(z, -3.2) + g1 + g2 - bay - bay2
  return Math.max(WOB_LAND, Math.min(BAYCAP_W, raw))
}

/** 北岸带符号距离（米，>0 陆侧，<0 海侧）：landMask 与 vCoast 的同一真值 */
export function dNorth(x: number, z: number): number {
  return -z + wobbleN(x) - CN0
}
/** 西岸带符号距离（米，>0 陆侧，<0 海侧）：含整体倾角项（海域张角 100°） */
export function dWest(x: number, z: number): number {
  return -x + wobbleW(z) - CW0 + (z - TILT_PIVOT_Z) * TILT10
}

/** 离岸地貌：2 主岛 + 2 卫星小岛 + 1 北岸海岬（全部远离机组/电缆/升压站，见 selftest）。
 *  p1/p2/p3 为轮廓角向谐波相位（3/5/8 瓣，±45% 半径起伏）—— 岛不再是正圆，
 *  而是有岬有湾的不规则岛；卫星小岛构成群岛感。 */
export interface CoastFeature { x: number; z: number; r: number; h: number; p1: number; p2: number; p3: number }
export const ISLANDS: CoastFeature[] = [
  { x: 1700, z: 700, r: 260, h: 26, p1: 1.3, p2: 4.1, p3: 2.2 }, // 东南外海大岛（距 T09/电缆走廊 1353m）
  { x: -500, z: 1400, r: 200, h: 20, p1: 5.0, p2: 0.7, p3: 3.3 }, // 南外海小岛（100°倾角后东移，距 T07 约 1400m）
]
/** 卫星小岛（东南大岛附属，纯海中央，与电缆/机组均 >800m） */
export const SATS: CoastFeature[] = [
  { x: 2100, z: 1100, r: 70, h: 9, p1: 2.0, p2: 1.1, p3: 5.4 },
  { x: 1300, z: 300, r: 55, h: 7, p1: 4.4, p2: 2.8, p3: 0.5 },
]
export const HEADLANDS: CoastFeature[] = [
  { x: -1250, z: -2400, r: 480, h: 42, p1: 0, p2: 0, p3: 0 }, // 北岸向南突出的海岬（距 T01 1218m）
]
/** 主峰（直插云霄）+ 次峰：深陆无人区，只做视觉奇观，不触碰任何约束 */
export interface Peak { x: number; z: number; r: number; h: number }
export const PEAKS: Peak[] = [
  { x: -2700, z: -3900, r: 800, h: 780 }, // 主峰（round11：r600→800、h900→780，
  { x: -1600, z: -4200, r: 600, h: 470 }, // 次峰（同上）—— 宽肩缓脊，合计仍 1000m 级，
]                                         // 不再是“插在地上”的针，只做体量不做高度竞赛
/** 丘陵盆地：台地带平滑洼陷（纯视觉起伏，深陆内部） */
export interface Basin { x: number; z: number; r: number; depth: number }
export const BASINS: Basin[] = [
  { x: -2300, z: -2500, r: 520, depth: 30 },
  { x: 1400, z: -3300, r: 440, depth: 26 },
]
/** 峡湾水道：由口(A)向源头(B)深切北岸。只做减法（carve 陆地），机组侧恒为海，
 *  不可能凭空造陆 —— 600m 净距约束天然不受威胁。 */
export const FJORD_A = { x: -400, z: -1750 } // 口（可靠海域，距 T01 约 580m）
export const FJORD_B = { x: -700, z: -3250 } // 源头（深陆）
function fjordCarve(x: number, z: number): number {
  const vx = FJORD_B.x - FJORD_A.x, vz = FJORD_B.z - FJORD_A.z
  const t = Math.max(0, Math.min(1, ((x - FJORD_A.x) * vx + (z - FJORD_A.z) * vz) / (vx * vx + vz * vz)))
  const d = Math.hypot(x - FJORD_A.x - vx * t, z - FJORD_A.z - vz * t)
  return 1 - smoothstep(110, 280, d) // 通道内全切（宽 220m），边缘 280m 羽化成峭壁
}
/** 海蚀柱群：离岸峭岩（小半径高锥，浪蚀奇观；全部纯海中央） */
export const STACKS: CoastFeature[] = [
  { x: -1000, z: -1700, r: 45, h: 20, p1: 1.0, p2: 2.0, p3: 3.0 }, // 西岬外柱（岬前 467m 海中）
  { x: -1150, z: -1500, r: 38, h: 16, p1: 3.0, p2: 5.0, p3: 1.0 }, // 西岬外柱二
  { x: 2400, z: 400, r: 48, h: 18, p1: 2.0, p2: 4.0, p3: 0.0 },    // 东外海孤柱
]
/** 岛极坐标：角向谐波半径 rr(θ)，设色 mask 与锥形抬升共用（同一真值） */
function islandPolar(f: CoastFeature, x: number, z: number): { d: number; rr: number } {
  const dx = x - f.x, dz = z - f.z
  const d = Math.hypot(dx, dz)
  const th = Math.atan2(dz, dx)
  const rr = f.r * (1 + 0.22 * Math.sin(3 * th + f.p1) + 0.14 * Math.sin(5 * th + f.p2) + 0.09 * Math.sin(8 * th + f.p3))
  return { d, rr }
}
/** 全部离岸地貌（二主岛二卫岛一海岬三海蚀柱）：mask 与抬升共用此表 */
const ISLES: CoastFeature[] = [...ISLANDS, ...SATS, ...HEADLANDS, ...STACKS]

/** 方向性陆地基底（北/西，不含岛——岛只做锥形抬升+设色，不触发内陆分带） */
function landBase(x: number, z: number): number {
  const rw = rampAt(x, z)
  const wN = smoothstep(0, rw, dNorth(x, z))
  const wW = smoothstep(0, rw, dWest(x, z))
  return Math.max(wN, wW) * (1 - fjordCarve(x, z))
}

/** 海岸过渡场（与陆地基底同式，不含岛）：vCoast / Step B 海岸距离场的同一真值 */
export function coastT(x: number, z: number): number {
  return landBase(x, z)
}

// ---- R36 · 岸距场（coastal_3d_v2 ocean.ts「真水深/岸距驱动泡沫与阻尼」的本仓口径）----
// coastT 是【陆侧】渐变（海侧恒 0），无法区分「远海」与「贴岸」；本函数给出
// 带符号最近岸距（米）：负 = 海侧离岸距离、正 = 陆侧深入距离。
// 与 landMask 同一几何真值：北/西岸用 dNorth/dWest，岛/海岬/海蚀柱用极坐标轮廓。
// 用途：浅水波幅阻尼、拍岸碎浪带、swash 水线爬升（WorldTerrain VERT/FRAG 消费）。
function islandSigned(f: CoastFeature, x: number, z: number): number {
  const { d, rr } = islandPolar(f, x, z)
  return rr - d // >0 在岛内（陆），<0 在岛外（海）
}
/** 陆地各件的 SDF 并集（任一件内部即陆）：北/西岸 + 岛/海岬/海蚀柱。
 *  海侧返回带符号最近岸距（负 = 离岸米数）。 */
export function shoreSigned(x: number, z: number): number {
  let s = Math.max(dNorth(x, z), dWest(x, z))
  for (const f of ISLES) {
    const si = islandSigned(f, x, z)
    if (si > s) s = si
  }
  return s
}

/**
 * 海岸线带符号距离（米，陆侧正 / 海侧负）—— R36 新增（参考 coastal_3d_v2 的
 * 「真海岸距离」思路，闭式实现，不上 EDT，理由见 docs/11 §四）。
 *
 * 真值推导：landBase = max(wN, wW)·(1−fjordCarve)，wN = smoothstep(0, rw, dNorth)，
 * rw = rampAt(x,z)。max(wN,wW)=0.5（视觉岸线）⟺ max(sN, sW) = 0，其中
 * sN = dNorth − rw/2、sW = dWest − rw/2（各岸 0.5 等值面即 s=0，两条岸线
 * 法向分别近似沿 −z / +x，轴方向距离≈法向距离，误差 ≲5%，与 R34 同类已知偏差）。
 *  · 海侧（至少一个 s<0）：到岸线距离 = min(|sN|, |sW|) → 符号化 = max(sN, sW)
 *  · 陆侧深处（sN>0 且 sW>0，仅西北角内侧）：最近岸线在拐角 → hypot(sN, sW)
 *  · 峡湾水道：carve 把陆地挖成海 → 强制负值（≈半渠宽 110m 封顶）
 *  · 离岸岛/海蚀柱不在此场（其水线泡沫由 vLand 薄带自动环绕，见 WorldTerrain）
 * ⚠ R39 合并口径（2026-09-17）：本函数**未被运行时采用**。主线同一问题的实现是上面的
 * `shoreSigned()`——北/西岸 + 岛/海岬/海蚀柱的 SDF 并集（严格更全，含离岸岛）；
 * 本函数只算两条岸（其作者自己在 docs/11 §四 声明离岸岛不在此场）。
 * 按 docs/research/round38_残项收口与裁决.md §一 的裁决「否决」，仅作对照实现保留，
 * 无调用方、不参与渲染、不进 selftest；若后续确认无用可直接删除（历史在 595daf2）。
 */
export function coastSignedDist(x: number, z: number): number {
  const rw = rampAt(x, z)
  const sN = dNorth(x, z) - rw * 0.5
  const sW = dWest(x, z) - rw * 0.5
  let d = sN > 0 && sW > 0 ? Math.hypot(sN, sW) : Math.max(sN, sW)
  const carve = fjordCarve(x, z)
  if (carve > 0) d = Math.min(d, -110 * carve)
  return d
}

/**
 * 陆地权重 0..1：0=开放海床，1=陆地。北/西两个方向各自产生一片陆地，
 * 用平滑 max 组合 —— 任一方向靠陆即抬升。南/东即保持 0（开放海）。
 * 多尺度蜿蜒 + 高斯弧岬湾破除「直线切割」的切割带感；离岸岛叠加设色 mask。
 */
export function landMask(x: number, z: number): number {
  let m = landBase(x, z)
  for (const f of ISLES) {
    const { d, rr } = islandPolar(f, x, z)
    if (d < rr + 120) m = Math.max(m, 1 - smoothstep(rr * 0.45, rr + 80, d))
  }
  return m
}

/** 雪线（米）：山地带中世界高度超过此值染雪冠（GPU 端，见 WorldTerrain v4）。
 *  round5：205→300；round10：300→380 —— 只属于主峰/次峰/最高山脊，雪下露岩重见天日。 */
export const SNOW_LINE = 380

/** 确定性 RNG（草地落位与 selftest 共用，保证"采样验证"与"真实落位"同分布） */
export function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** 草地拒绝采样命中数（kind 0=草原带 / 1=林下）：与 grassField.buildSet 同条件
 *  （landMask≥0.05 且按 biome 权重接受）。默认 2 万次试投，命中 >1% 即对应
 *  生物群系带真实存在、全量 6 万可按同分布铺满。 */
export function grassSampleHits(kind: 0 | 1, tries = 20000): number {
  const rnd = mulberry32(kind === 0 ? 1337 : 7331)
  let hits = 0
  for (let i = 0; i < tries; i++) {
    const x = (rnd() * 2 - 1) * 4550
    const z = (rnd() * 2 - 1) * 4550
    if (landMask(x, z) < 0.05) continue
    const w = biomeWeights(x, z)
    if (rnd() > (kind === 0 ? w.grass : w.forest)) continue
    hits++
  }
  return hits
}

// ---- R36 · 远岸森林落位（coastal_3d_v2 vegetation.ts「拒绝采样 + 坡度/雪线门」的本仓口径）----
// treeAccept 是 treeField.buildSet 与 selftest 的同一真值：
//  · landMask ≥ 0.30：越过沙岸/潮带（树林不长在海滩上）；
//  · 接受概率 = w.forest + 0.35·w.hill：林带密、缓丘带稀；
//  · 高度 < SNOW_LINE-40：雪线以上是裸岩雪冠，不长树；
//  · 坡度门 ny ≥ 0.62：峭壁不长树（有限差分估地形法线）；
// 返回树高缩放（米，≈7.5~16.5m 冠幅含在内），0 = 拒绝。
export const TREE_SPAN_M = 4550 // 与草地同一采样域
export function treeAccept(x: number, z: number, r: number): number {
  const L = landMask(x, z)
  if (L < 0.30) return 0
  const h = terrainHeight(x, z)
  if (h > SNOW_LINE - 40) return 0
  const e = 7
  const ny = (2 * e) / Math.hypot(
    terrainHeight(x - e, z) - terrainHeight(x + e, z),
    2 * e,
    terrainHeight(x, z - e) - terrainHeight(x, z + e),
  )
  if (ny < 0.62) return 0
  const w = biomeWeights(x, z)
  // 海岛/海岬低海拔区（h < 60m）允许植被茂盛生长，避免岛心因 L>0.82 归入高山裸岩而漏植被
  const islandBoost = h < 60 ? 0.35 * w.mountain : 0
  if (r > w.forest + 0.35 * w.hill + islandBoost) return 0
  return 7.5 + r * 9
}
/** 树木拒绝采样命中数（selftest 用，与 treeField.buildSet 同一 treeAccept） */
export function treeSampleHits(tries = 20000): number {
  const rnd = mulberry32(4242)
  let hits = 0
  for (let i = 0; i < tries; i++) {
    const x = (rnd() * 2 - 1) * TREE_SPAN_M
    const z = (rnd() * 2 - 1) * TREE_SPAN_M
    if (treeAccept(x, z, rnd()) > 0) hits++
  }
  return hits
}

/** 六类生物群系权重（CPU 端，与 WorldTerrain v4 GPU 分带同式）：沙岸/潮带/草原/林地/缓丘/远山。
 *  供贴地物（草地散布等）与 selftest 消费；海面（land≈0）返回全零。 */
export interface BiomeWeights {
  sand: number; tidal: number; grass: number; forest: number; hill: number; mountain: number
}
export function biomeWeights(x: number, z: number): BiomeWeights {
  const L = landMask(x, z)
  if (L <= 0.001) return { sand: 0, tidal: 0, grass: 0, forest: 0, hill: 0, mountain: 0 }
  const sand = 1 - smoothstep(0.06, 0.16, L)
  const tidal = smoothstep(0.05, 0.12, L) * (1 - smoothstep(0.16, 0.28, L))
  const grass = smoothstep(0.14, 0.30, L) * (1 - smoothstep(0.45, 0.62, L))
  const forest = smoothstep(0.38, 0.55, L) * (1 - smoothstep(0.68, 0.82, L))
  const hill = smoothstep(0.60, 0.75, L) * (1 - smoothstep(0.85, 0.95, L))
  const mountain = smoothstep(0.82, 0.93, L)
  // 主导群系对比增强（pow 1.25 再归一，与 GPU 同式）：过渡带不再"混在一起看不真切"
  const ce = 1.25
  const eSand = sand ** ce, eTidal = tidal ** ce, eGrass = grass ** ce
  const eForest = forest ** ce, eHill = hill ** ce, eMtn = mountain ** ce
  const s = eSand + eTidal + eGrass + eForest + eHill + eMtn
  // 中间过渡带各分量和可能 <1（分带交叠设计），归一保证"权重"语义
  if (s < 1e-6) return { sand: 0, tidal: 0, grass: 0, forest: 0, hill: 0, mountain: 0 }
  return { sand: eSand / s, tidal: eTidal / s, grass: eGrass / s, forest: eForest / s, hill: eHill / s, mountain: eMtn / s }
}

/** 高度网格烘焙（Step C1 地形投影用）：size² 采样 terrainSurfaceY，
 *  data[j*size+i] ↔ x=(i/(size-1)-0.5)*extent, z=(j/(size-1)-0.5)*extent，
 *  与 GPU 端 uv = xz/extent+0.5 同式（v=0 ↔ z=-extent/2，DataTexture flipY=false）。
 *  纯真值采样，不改变任何地形 —— 陆地冻结令下允许新增的只读消费。 */
export function bakeHeightGrid(size: number, extent: number): { size: number; extent: number; data: Float32Array } {
  const data = new Float32Array(size * size)
  for (let j = 0; j < size; j++) {
    const z = (j / (size - 1) - 0.5) * extent
    for (let i = 0; i < size; i++) {
      data[j * size + i] = terrainSurfaceY((i / (size - 1) - 0.5) * extent, z)
    }
  }
  return { size, extent, data }
}

/**
 * 地面【实际渲染面】高度（第 30 轮起连续面）。
 * 直接等于连续地形 terrainHeight（连续海床，无台地量化台阶）。
 * 贴地基准与渲染面同源 —— 风机/升压站/电缆/星光全部贴它定位，零回归。
 */
export function terrainSurfaceY(x: number, z: number): number {
  return terrainHeight(x, z)
}

export function terrainHeight(x: number, z: number): number {
  const land = landBase(x, z)
  // 海床基准（低，贴近真实海平台）+ 极低幅微地貌（不是完全平面）
  const bed = (N.fbm(x * 0.0009, z * 0.0009, 3) - 0.5) * 4.0
  let h = 2.0 + bed
  if (land > 0) {
    // 分带（round7 全程缓坡 + round9 还回远山）：沙带 → 台地拉长 → 高地【线性登山】
    // （全程等坡、无后墙；上限 400m 级 + 高矮分区；近岸 1km 仍是滩原丘陵）
    const sand = smoothstep(0.0, 0.28, land)      // 近海黄沙带
    const forest = smoothstep(0.20, 0.80, land)   // 森林台地（拉长，盖住中段）
    const mountain = clamp01((land - 0.55) / 0.45) // 内陆高地（线性登山）
    const roll = (N.fbm(x * 0.0021 + 8.8, z * 0.0021 - 3.3, 2) - 0.5) * 2 // 台地丘陵起伏 ±12m
    const crag = N.ridged(x * 0.00032 + 3.1, z * 0.00032 - 1.4, 4)        // 主峰（锐化）
    const crag2 = N.ridged(x * 0.0011 - 7.7, z * 0.0011 + 4.2, 2)         // 次峰（破碎感）
    const warp = (N.fbm(x * 0.0004 - 11.0, z * 0.0004 + 5.0, 3) - 0.5) * 1600 // 域扭曲（山脊走弯）
    const ridge = N.ridged(x * 0.0009 + warp * 0.0009 + 3.1, z * 0.0009 - 1.4, 3) // 曲折山脊谷地
    const mAmp = 0.85 + 0.6 * N.fbm(x * 0.0002 - 5.5, z * 0.0002 + 2.2, 2) // 山系高矮分区
    h += sand * 10
    h += forest * (34 + 20 * N.ridged(x * 0.0005 + 1.7, z * 0.0005 - 9.3, 3) + 12 * roll)
    h += mountain * (90 + 170 * crag + 70 * crag2 + 70 * ridge) * mAmp
    for (const b of BASINS) { // 丘陵盆地（平滑洼陷）
      const db = Math.hypot(x - b.x, z - b.z)
      if (db < b.r) h -= b.depth * (1 - smoothstep(0, b.r, db))
    }
  }
  for (const pk of PEAKS) { // 主峰/次峰（round11：宽肩缓脊 + 基座裙边，坐进山脊）
    const dp = Math.hypot(x - pk.x, z - pk.z)
    if (dp < pk.r * 2.6) {
      const prof = 1 - smoothstep(0, pk.r, dp)
      const gully = (N.ridged(x * 0.006 + pk.x * 0.01, z * 0.006 - pk.z * 0.01, 3) - 0.5) * 2
      h += pk.h * prof ** 1.05 + pk.h * 0.14 * gully * prof
      // 裙边：峰脚向外 1.2r 处垫高 0.32h、2.6r 处归零 —— 峰从山脊里“长出来”，不断层
      h += pk.h * 0.32 * smoothstep(pk.r * 0.3, pk.r * 1.2, dp) * (1 - smoothstep(pk.r * 1.2, pk.r * 2.6, dp))
    }
  }
  // 离岸岛/海岬（第 32 轮）：不规则轮廓锥形抬升（中心全高 → rr+180m 处归零），
  // 与主体陆地自然衔接；岛只走本抬升，不触发上面的内陆分带（避免岛变高山）。
  for (const f of ISLES) {
    const { d, rr } = islandPolar(f, x, z)
    if (d < rr + 180) h += f.h * (1 - smoothstep(0, rr + 180, d))
  }
  // 升压站局地再压平（站体仍在海中央）
  const dS = Math.hypot(x - SUBSTATION.x, z - SUBSTATION.z)
  h *= 1 - 0.9 * smoothstep(300, 130, dS)
  return h
}

// ---- 场区：布局真值源在 ./layouts（R41-A · 2026-10-05 起）----
// 2026-08-28（任务#1 数据对齐）：阵列几何直接采用老网页/FLORIS 例题场
// ——3×3、纵横间距 632 m = 5.02D（NREL 5MW D=126m）。这同时消解了
// docs/07 B7 的"间距小于工程惯例"叙事风险：5D 恰是尾流控制惯例下限，
// 且与本仓引用的 FLORIS 9 机基准功率 8095.15 kW 同一几何，代理引擎
// 的尾流 k 即按该工况标定（turbinePhysics.JENSEN_K）。
// R41-A：几何 / 排数 / 舵机 / 语义锚点下标全部派生自 layouts.ts
// （3×3 与留档 tag `twin-3x3-archive-20260919` 逐位一致，selftest 有回归锁）；
// P0-1（2026-09-16）移除的 ±20m 位置抖动**保持移除**（layouts 里就没有抖动）。
export const ROTOR_D_M = 126 // NREL 5MW 风轮直径（示意几何）
export interface FarmUnit { id: string; x: number; z: number; row: number; col: number; speed: number }
export const FARM: FarmUnit[] = LAYOUT.units.map((u, k) => ({
  ...u,
  // 演示层确定性转速抖动（不影响功率物理口径）；k = 布局内序号
  speed: 1.02 + ((k * 29) % 5) * 0.1,
}))

// 舵机滑杆对应的机组（1-based；3×3 = 近大远小中最显眼 5 台，1×3 = 全部 3 台）
export const SERVOS: number[] = LAYOUT.servos

export const ROW_COUNT = LAYOUT.rows

// 升压站：画面右中下（原图位置 x≈60%、y≈58%）
export const SUBSTATION = { x: 300, z: 300 }
export const APPROACH = { x: 1900, z: 1400 }

// ---- 相机构图（对版原图：强透视、天际线≈画面上缘 12%）----
export const CAM = {
  pos: [60, 430, 990] as [number, number, number],
  target: [0, 22, -340] as [number, number, number],
  fov: 47,
}

// ---- 世界标注锚点（引线标签用）----
// A6 修复：锚点必须挂在"被指物体"的真实几何位置附近（塔基/机舱/站体顶/
// 线路中点），而不是随意的高空悬点；Callouts 还会按屏幕投影做避让。
const HUB = 90 // 轮毂高（米）
// R41-A：锚点改语义选择器（docs/13 §4.1）：power→中排中机、wake→上游机北侧来流空域、
// turbine/dot→最近景机、cable→最近景机↔升压站中点。3×3 下与旧写死下标逐位等价。
const AU = LAYOUT.units
const AA = LAYOUT.anchors
const at = (i: number, dx: number, dy: number, dz: number) => ({
  x: AU[i].x + dx,
  y: terrainSurfaceY(AU[i].x, AU[i].z + dz) + dy,
  z: AU[i].z + dz,
})
export const ANCHOR = {
  // 全场功率总览 → 指向语义中心机组机舱（功率汇聚处）
  power: at(AA.power, 0, HUB + 8, 0),
  // 风能资源场 → 上游机组北侧的来流空域（北缘外 220m、轮毂高度）
  wake: at(AA.wake, 0, HUB - 6, -220),
  // 风机 → 最近景机组塔筒中段
  turbine: at(AA.turbine, 14, 52, 0),
  // 集电线路 → 最近景机组串接电缆中段（机组与升压站之间）
  cable: {
    x: (AU[AA.cable].x + SUBSTATION.x) / 2,
    y: terrainSurfaceY((AU[AA.cable].x + SUBSTATION.x) / 2, (AU[AA.cable].z + SUBSTATION.z) / 2) + 14,
    z: (AU[AA.cable].z + SUBSTATION.z) / 2,
  },
  // 升压站 → 站体顶缘
  substation: { x: SUBSTATION.x - 40, y: terrainSurfaceY(SUBSTATION.x, SUBSTATION.z) + 46, z: SUBSTATION.z - 20 },
  // 圈选：最近景大机组塔基
  dot: at(AA.dot, 0, 4, 0),
}
