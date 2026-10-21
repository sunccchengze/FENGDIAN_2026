// ============================================================================
// 九个塔位快速镜头（数字键 1-9）—— 单一真值源
// ----------------------------------------------------------------------------
//  · CameraRig（运行时跳转）与 App（OrbitControls 约束）与 selftest（回归断言）
//    三方共用本模块，约束与机位不再散落三处各自漂移；
//  · 坐标系约定：+x=东，+z=南，场心 FARM_CENTER=(-100,-640)；
//  · “前” = 塔位看向场心的方向（normalize(C - P)）；“右/左” = 前向量 × 上向量；
//  · 高度为绝对海拔（海床约 +2m，轮毂约 +92m）；HUB_Y=90 为沿用已久的取景基准，
//    与真实轮毂差 ~2m（<0.5° 视角差），刻意保持以冻结 1/2/3/5/6 已验收构图。
// ----------------------------------------------------------------------------
//  取景设计（fov 47°，16:9；拟合余量见 checkHotkeyFit，selftest 锁定）：
//  · 1/2/3 高处俯拍：轮毂上空 +260m，距塔 ~390-470m（沿用，不动）；
//  · 4/5/6 平视：4 = T04 右前方近距离（距塔 ~172m， rotor 全框 + 裕度）；
//  · 7/8/9 低处仰拍：机位海拔 14m（浪上 ~12m），距塔 ~200-220m，注视塔身 75m
//    处（仰角 ~16-17°，极角 ~106-107°），转子 + 全塔收进框内。
//  · 4789 重设计根因（2026-09-06）：旧 4/7/8/9 距塔仅 104/117/129/124m ——
//    (a) 框高不足以容下 126m 转子（4 号）或转子+仰角透视（7/8/9），叶片被裁；
//    (b) 7/8/9 极角 129-135° 远超 OrbitControls maxPolarAngle（旧 104.65°），
//        跳转落地瞬间被约束钳位弹回，视角“定不住”；4/7 落地距离 < minDistance
//        120m，同样被顶出。详见 docs/research/hotkey_framing_fix_4789.md。
// ============================================================================
import * as THREE from 'three'
import { FARM, FARM_CENTER } from './terrainUtil.ts'
import { unitOf } from './layouts.ts'

// —— OrbitControls 约束（App.tsx 直接引用，禁止在组件里另写魔法数）——
/** 最小 Lambert 距离：近摄特写下限；全部热键落地距离必须 ≥ 此值 + 5m 裕度 */
export const ORBIT_MIN_DISTANCE = 120
export const ORBIT_MAX_DISTANCE = 4600
/** 最大极角：90°=水平；114° 容纳低机位仰拍（极角 ~107°）+ 7° 裕度。
 *  开场环绕极角约 100° 不受影响；地下穿透风险与旧值（104.65°）同阶——
 *  远距离 + 低目标本来就能入地，此值只管“仰拍定得住”，不管防穿地。 */
export const ORBIT_MAX_POLAR_DEG = 114
/** 热键取景的设计视场（与 CameraRig 落地 fov 一致） */
export const HOTKEY_FOV_DEG = 47

/** 取景轮毂基准（绝对海拔，见文件头说明） */
export const HUB_Y = 90

function towerForward(i: number): [number, number, number] {
  const u = FARM[i]
  const dx = FARM_CENTER.x - u.x
  const dz = FARM_CENTER.z - u.z
  // 场心机组（T05）C-P 接近零向量：归一化会退化成抖动噪声方向。
  // 当前抖动恰好给出正北，此处显式兜底正北，行为不变但不再依赖抖动巧合。
  if (Math.hypot(dx, dz) < 1) return [0, 0, -1]
  const f = new THREE.Vector3(dx, 0, dz).normalize()
  return [f.x, f.y, f.z]
}

// 调用约定：先调用 towerForward(i) 拿前向量，再以同一前向量求右向量。
function towerRight(fx: number, fz: number): [number, number, number] {
  const r = new THREE.Vector3(fx, 0, fz).cross(new THREE.Vector3(0, 1, 0)).normalize()
  return [r.x, r.y, r.z]
}

function hotPos(
  i: number,
  along: number, // 前向量方向上的偏移（正=朝场心方向）
  aside: number, // 右向量方向上的偏移（正=右）
  height: number, // 相机海拔（绝对）
): THREE.Vector3 {
  const u = FARM[i]
  const [fx, , fz] = towerForward(i)
  const [rx, , rz] = towerRight(fx, fz)
  return new THREE.Vector3(
    u.x + fx * along + rx * aside,
    height,
    u.z + fz * along + rz * aside,
  )
}

function hotTarget(i: number, height: number): THREE.Vector3 {
  return new THREE.Vector3(FARM[i].x, height, FARM[i].z)
}

export interface CamHotkey { pos: THREE.Vector3; target: THREE.Vector3 }

// R42（round42 §0.1）：机位表从「写死 T01–T09」改为「3 取景语法 × 3 槽位」，
// 机组下标由 layouts.unitOf(i) 派生：
//   · 3×3：i 本身（T01–T09 各一个机位，与旧表逐位一致，selftest 有回归锁）；
//   · 1×3：i % 3（三机各享 高俯/平视/低仰 三个机位，上→下 = 上游→下游）。
// 语法 = 机位相对塔的方向与海拔；槽位 = 右/中/左 三个方位变体。
const GRAMMAR: Array<{ th: number; slots: Array<{ along: number; aside: number; h: number }> }> = [
  // 语法一 · 高处俯拍（1/2/3）：轮毂上空 +260~270m，距塔 ~390-470m（沿用）
  { th: HUB_Y, slots: [{ along: 360, aside: 160, h: HUB_Y + 260 }, { along: 380, aside: 0, h: HUB_Y + 270 }, { along: 360, aside: -160, h: HUB_Y + 260 }] },
  // 语法二 · 平视（4/5/6）：4 = 右前方近距离（~172m 转子全框）、5 = 正前方中距离、6 = 左前方远距离
  { th: HUB_Y, slots: [{ along: 150, aside: 84, h: HUB_Y + 12 }, { along: 170, aside: 0, h: HUB_Y + 22 }, { along: 320, aside: -120, h: HUB_Y + 20 }] },
  // 语法三 · 低处仰拍（7/8/9）：机位海拔 14m，距塔 ~200-220m，注视塔身 75m（全塔 + 转子同框）
  { th: 75, slots: [{ along: 168, aside: 108, h: 14 }, { along: 210, aside: 0, h: 14 }, { along: 170, aside: -102, h: 14 }] },
]
export const CAM_HOTKEYS: readonly CamHotkey[] = GRAMMAR.flatMap((g, gi) =>
  g.slots.map((s, si) => {
    const i = gi * 3 + si
    const u = unitOf(i)
    return { pos: hotPos(u, s.along, s.aside, s.h), target: hotTarget(u, g.th) }
  }),
)

// ---------------------------------------------------------------------------
// 纯函数诊断：机位几何 + 取景拟合（selftest 与分析脚本共用，无 React 依赖）
// ---------------------------------------------------------------------------
const D2R = Math.PI / 180

export interface HotkeyDiag {
  index: number // 0..8
  dist3: number // 机位→注视点三维距离
  horiz: number // 水平距离
  tiltDeg: number // 视轴仰角（正=抬头看）
  polarDeg: number // 极角（=90-tilt，与 OrbitControls 同口径）
  camY: number
  /** 关键点 NDC（fov 47 / aspect 16:9）：hub/上下左右叶尖/塔基/塔身 25m */
  ndc: Record<'hub' | 'tipTop' | 'tipBottom' | 'tipLeft' | 'tipRight' | 'base' | 'tower25', { x: number; y: number }>
  rotorMaxAbs: number // 转子 5 点 |ndc| 最大值（拟合判据）
}

/**
 * 把世界点投影到取景 NDC。转子包络取偏航 0°（正对北来风）：
 * 叶尖包络圆半径 63m（=rotorD/2，见 turbine/geometry TURBINE_SPEC），
 * 位于 x=机位x 平面；塔基/塔身取机位柱轴线。
 */
export function diagnoseHotkey(
  i: number,
 scene: {
    baseY: number // 机位地面海拔（terrainSurfaceY）
    hubAboveBase?: number // 默认 90
    rotorR?: number // 默认 63
    aspect?: number // 默认 16/9
  },
): HotkeyDiag {
  const hubAboveBase = scene.hubAboveBase ?? 90
  const rotorR = scene.rotorR ?? 63
  const aspect = scene.aspect ?? 16 / 9
  const u = FARM[unitOf(i)] // R42：1×3 下热键 i 对应机组 i%3（3×3 时 = i，行为不变）
  const gy = scene.baseY
  const { pos, target } = CAM_HOTKEYS[i]
  const fwd = target.clone().sub(pos)
  const dist3 = fwd.length()
  fwd.normalize()
  const horiz = Math.hypot(target.x - pos.x, target.z - pos.z)
  const tiltDeg = Math.atan2(target.y - pos.y, horiz) / D2R
  // 极角口径与 OrbitControls 一致：offset = pos - target 与 +Y 的夹角；
  // 相机在注视点下方（抬头看，tilt>0）→ 极角 >90°。
  const polarDeg = 90 + tiltDeg
  // 相机基：right = fwd × 世界上；upCam = right × fwd
  const worldUp = new THREE.Vector3(0, 1, 0)
  const right = new THREE.Vector3().crossVectors(fwd, worldUp).normalize()
  const upCam = new THREE.Vector3().crossVectors(right, fwd).normalize()
  const tanV = Math.tan((HOTKEY_FOV_DEG / 2) * D2R)
  const tanH = tanV * aspect
  const proj = (p: THREE.Vector3) => {
    const d = p.clone().sub(pos)
    const z = d.dot(fwd)
    return { x: d.dot(right) / z / tanH, y: d.dot(upCam) / z / tanV }
  }
  const hub = new THREE.Vector3(u.x, gy + hubAboveBase, u.z)
  const ndc = {
    hub: proj(hub),
    tipTop: proj(new THREE.Vector3(u.x, gy + hubAboveBase + rotorR, u.z)),
    tipBottom: proj(new THREE.Vector3(u.x, gy + hubAboveBase - rotorR, u.z)),
    tipLeft: proj(new THREE.Vector3(u.x - rotorR, gy + hubAboveBase, u.z)),
    tipRight: proj(new THREE.Vector3(u.x + rotorR, gy + hubAboveBase, u.z)),
    base: proj(new THREE.Vector3(u.x, gy + 1, u.z)),
    tower25: proj(new THREE.Vector3(u.x, gy + 25, u.z)),
  }
  const rotorMaxAbs = Math.max(
    Math.abs(ndc.hub.x), Math.abs(ndc.hub.y),
    Math.abs(ndc.tipTop.x), Math.abs(ndc.tipTop.y),
    Math.abs(ndc.tipBottom.x), Math.abs(ndc.tipBottom.y),
    Math.abs(ndc.tipLeft.x), Math.abs(ndc.tipLeft.y),
    Math.abs(ndc.tipRight.x), Math.abs(ndc.tipRight.y),
  )
  return { index: i, dist3, horiz, tiltDeg, polarDeg, camY: pos.y, ndc, rotorMaxAbs }
}
