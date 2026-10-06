import * as THREE from 'three'
import { FARM } from './terrainUtil.ts'
import { LAYOUT } from './layouts.ts'

// ============================================================================
// 开场巡航路径与速度剖面真值源
// R42（round42 §0.1）：航点机组下标全部改为按布局取（LAYOUT），3×3 与旧表逐位一致；
// 1×3 沿中列纵深：高空俯瞰 → 低空掠列 → 全景（注视列心）→ 掠 T02 尾流 → T03 前低机位。
// ============================================================================

const V3 = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z)

// 3×3：原 13 航点（T01–T09 语义：FARM[2]=T03 右前推、FARM[4]=T05 对角穿、FARM[6]=T07 收尾）
// 惰性求值：仅 3×3 布局下调用（1×3 下 FARM 只有 3 台，顶层求值会读到 undefined）
const nodes3x3 = (): { cam: THREE.Vector3[]; look: THREE.Vector3[] } => ({
  cam: [
    V3(-100, 1450, 250),
    V3(-100, 850, 80),
    V3(-100, 360, -100),
    V3(-100, 320, 150),
    V3(-80, 380, 450),
    V3(-20, 440, 750),
    V3(60, 480, 990),
    V3(120, 470, 900),
    V3(FARM[2].x + 145, 210, FARM[2].z - 160), // 8: 快速前推至 T03
    V3(FARM[2].x + 160, 220, FARM[2].z - 110), // 9: T03 处转头
    V3(FARM[4].x + 100, 130, FARM[4].z + 105), // 10: 沿对角线穿 T05
    V3(FARM[6].x + 145, 86, FARM[6].z + 120),  // 11: 接近 T07
    V3(FARM[6].x + 76, 56, FARM[6].z + 168),   // 12: T07 前低机位终点
  ],
  look: [
    V3(0, 22, -340), V3(0, 22, -340), V3(0, 22, -340), V3(0, 22, -340),
    V3(0, 22, -340), V3(0, 22, -340), V3(0, 22, -340), V3(0, 22, -340),
    V3(FARM[2].x, 96, FARM[2].z), // 8: T03
    V3(FARM[4].x, 96, FARM[4].z), // 9: T05
    V3(FARM[6].x, 98, FARM[6].z), // 10: T07
    V3(FARM[6].x, 96, FARM[6].z), // 11: T07
    V3(FARM[6].x, 92, FARM[6].z), // 12: T07
  ],
})

// 1×3：中列三机 FARM[0]=T01 上游(北) / FARM[1]=T02 / FARM[2]=T03 下游(近)
const nodes1x3 = (): { cam: THREE.Vector3[]; look: THREE.Vector3[] } => {
  const [, M, S] = FARM // 北→南（T01 上游只出现在 look 语义里，路径不单独停靠）
  return {
    cam: [
      V3(-100, 1450, 250),                    // 0: 高空起始：俯瞰全列
      V3(-100, 800, 120),                     // 1: 俯冲
      V3(-100, 340, -150),                    // 2: 低空掠过列中段
      V3(60, 300, 60),                        // 3: 抬头拉开（东南侧）
      V3(140, 360, 480),                      // 4: 进全景过渡段
      V3(60, 420, 780),                       // 5: 全景构图（注视列心）
      V3(0, 400, 860),                        // 6: 全景缓行
      V3(-60, 320, 600),                      // 7: 开始前推
      V3(S.x + 145, 210, S.z - 160),          // 8: 快速前推至 T03
      V3(S.x + 160, 220, S.z - 110),          // 9: T03 处转头
      V3(M.x + 100, 130, M.z + 105),          // 10: 掠 T02 尾流下缘
      V3(S.x + 90, 86, S.z + 120),            // 11: 回到 T03 前
      V3(S.x + 76, 56, S.z + 168),            // 12: T03 前低机位终点
    ],
    look: [
      V3(-100, 40, -640), V3(-100, 40, -640), V3(-100, 40, -640), V3(-100, 40, -640),
      V3(-100, 40, -640), V3(-100, 40, -640), V3(-100, 40, -640), V3(-100, 40, -640),
      V3(S.x, 96, S.z), // 8: T03
      V3(S.x, 96, S.z), // 9: T03
      V3(M.x, 96, M.z), // 10: T02（尾流语义：中游机组）
      V3(S.x, 96, S.z), // 11: T03
      V3(S.x, 92, S.z), // 12: T03
    ],
  }
}

const N = LAYOUT.id === '1x3' ? nodes1x3() : nodes3x3()

export const CAMERA_NODES = N.cam

export const LOOK_NODES = N.look

export const CAMERA_PATH = new THREE.CatmullRomCurve3(CAMERA_NODES, false, 'centripetal', 0.38)
export const LOOK_PATH = new THREE.CatmullRomCurve3(LOOK_NODES, false, 'centripetal', 0.38)
export const INTRO_END = 34

export interface IntroSample {
  frac: number
  t: number
  speed: number
  fov: number
}

export function buildIntroProfile(
  path: THREE.CatmullRomCurve3,
  totalDur: number,
  _vCruise?: number,
  _vMin?: number,
  _vMax?: number,
  _boostPts?: ReadonlyArray<readonly [number, number]>,
) {
  const len = path.getLength()
  const vMean = len / totalDur
  const lookup = (t: number): IntroSample => {
    const k = Math.min(1, Math.max(0, t / totalDur))
    const frac = k * k * (3 - 2 * k)
    const speed = vMean * (6 * k * (1 - k))
    return {
      frac,
      t,
      speed,
      fov: 52 - 5 * frac,
    }
  }

  return {
    lookup,
    vExit: 100,
    exitTangent: path.getTangent(1),
    vMin: 40,
    vMax: 350,
    stats: {
      len,
      vMean,
      totalTime: totalDur,
      rawDur: totalDur,
      scale: 1,
      vMin: 40,
      vMax: 350,
      turns: 0,
      bankMaxDeg: 0,
      maxCurve: 0.05,
    },
  }
}

export const BOOST_TABLE: ReadonlyArray<readonly [number, number]> = [
  [0.00, 1.0],
  [1.00, 1.0],
]
