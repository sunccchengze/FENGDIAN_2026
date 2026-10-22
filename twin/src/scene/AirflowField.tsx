/* oxlint-disable react/immutability -- R3F 帧循环 mutate 缓冲为既定性能模式（docs/08 D2） */
import { useEffect, useMemo } from 'react'
import { debugEnabled } from '../data/debug'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { FARM, terrainSurfaceY } from './terrainUtil'
import { windAt } from '../data/farmSim'
import { ROTOR_D, WAKE_K, thrustCt, wakeDeflection } from '../data/turbinePhysics'
import { useSim } from '../state/simStore'
import { mulberry32 } from '../data/rng.ts'
import { phaseT, FREEZE } from './freeze.ts'

// ============================================================================
// AirflowField —— 风洞烟线式全场气流可视化（第 12 轮 R2 重制 + 性能精简优化）
// 用户反馈：圆环走廊"不像尾流"。改为两种经典 CFD/风洞语言：
//  ① 风纹拖尾线（streak lines）：每条=粒子上一帧→当前帧的线段，
//     长度∝当地速度、亮度∝有效风速——自由来流=长而亮，
//     穿过尾流=骤然变短变暗，尾流本体第一次"直接可见"；
//     偏航滑杆拨动 → 尾流轴横偏 → 整片烟线跟着弯折（与功率同内核）。
//  ② 烟羽管（wake plume）：每台机下游的半透明展宽管体（Jensen 半径扩张
//     + 偏航横偏 + 行进中的波形扰动），取代悬浮圆环；边缘薄、正视浓，
//     像 CFD 里的等值面，而非线框球。
// 物理同源：基流=windAt；亏损=2a·(D/(D+2kx))²·高斯横截面（与 farmSim/HUD 同式）。
// 视觉克制：纯青白加性、无 Bloom；HUD「三维气流场」整层开关。
// 第 22 轮（视觉精修 pass）：烟羽 alpha 峰值 0.13→0.055 + 轴向 exp 衰减 + 深冰青色相，
// 只动视觉层，Jensen 半径/横偏/粒子平流全部原样（数据红线不变）。
// ============================================================================

const N_SEG = 24 // 拖尾线头尾 2 顶点；烟羽管环周段数（16→24：管截面更接近正圆）
const N_RING = 11
const CX = 1500
const FCX = FARM.reduce((a, f) => a + f.x, 0) / FARM.length
const FCZ = FARM.reduce((a, f) => a + f.z, 0) / FARM.length

const STREAK_VERT = /* glsl */ `
attribute float aB;
varying float vB;
void main() {
  vB = aB;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`
const STREAK_FRAG = /* glsl */ `
precision mediump float;
varying float vB;
void main() {
  vec3 col = mix(vec3(0.10, 0.42, 0.66), vec3(0.82, 0.97, 1.0), vB);
  gl_FragColor = vec4(col, vB);
}
`
const PLUME_VERT = /* glsl */ `
attribute float aA;
varying float vA;
void main() {
  vA = aA;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`
// 第 22 轮视觉精修：烟羽管"克制化"——峰值 0.13→0.055、轴向距离衰减 exp(-ax/1000)、
// 色相转深冰青（加性贡献降亮度），消除中排/近排线稿被灰色烟锥洗灰的问题。
// 物理口径不变：半径仍是 Jensen 扩张，横偏仍调 wakeDeflection()，仅改视觉 alpha 分布。
const PLUME_FRAG = /* glsl */ `
precision mediump float;
varying float vA;
void main() {
  gl_FragColor = vec4(vec3(0.16, 0.52, 0.82), vA);
}
`

export default function AirflowField() {
  const quality = useSim((s) => s.quality)
  const n = quality === 'high' ? 1600 : quality === 'medium' ? 900 : 450

  const { streaks, plumes } = useMemo(() => {
    // —— 风纹拖尾线：每粒 2 顶点（尾→头），alpha 头亮尾隐 ——
    const g = new THREE.BufferGeometry()
    const pos = new Float32Array(n * 2 * 3)
    const bb = new Float32Array(n * 2)
    const px = new Float32Array(n)
    const py = new Float32Array(n)
    const pz = new Float32Array(n)
    const seed = mulberry32(0x0830) // D2：渲染期随机必须可复现
    for (let i = 0; i < n; i++) {
      px[i] = FCX + (seed() * 2 - 1) * CX
      py[i] = 4 + seed() ** 1.6 * 250
      pz[i] = FCZ + (seed() * 2 - 1) * CX
      pos[i * 6] = px[i] - 30
      pos[i * 6 + 1] = py[i]
      pos[i * 6 + 2] = pz[i]
      pos[i * 6 + 3] = px[i]
      pos[i * 6 + 4] = py[i]
      pos[i * 6 + 5] = pz[i]
      bb[i * 2] = 0.05
      bb[i * 2 + 1] = 1
    }
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('aB', new THREE.BufferAttribute(bb, 1))
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(FCX, 140, FCZ), 3200)
    const streakObj = new THREE.LineSegments(
      g,
      new THREE.ShaderMaterial({
        vertexShader: STREAK_VERT, fragmentShader: STREAK_FRAG,
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      }),
    )
    streakObj.frustumCulled = false

    // —— 烟羽管：每机 N_RING×N_SEG 顶点三角带，顶点 alpha 沿程衰减 ——
    const vg = FARM.length * N_RING * N_SEG
    const pg = new THREE.BufferGeometry()
    const ppos = new Float32Array(vg * 3)
    const paA = new Float32Array(vg)
    const idx = new Uint16Array(FARM.length * (N_RING - 1) * N_SEG * 6)
    let t = 0
    for (let j = 0; j < FARM.length; j++) {
      const base = j * N_RING * N_SEG
      for (let r = 0; r < N_RING - 1; r++) {
        for (let kk = 0; kk < N_SEG; kk++) {
          const kn = (kk + 1) % N_SEG // BUG-FIX：环周需闭合取模，原来 kk+1 在最后一段
          const a0 = base + r * N_SEG + kk
          const a1 = base + r * N_SEG + kn
          const b0 = a0 + N_SEG
          const b1 = a1 + N_SEG
          idx[t++] = a0; idx[t++] = b0; idx[t++] = a1
          idx[t++] = a1; idx[t++] = b0; idx[t++] = b1
        }
      }
      for (let r = 0; r < N_RING; r++) {
        // 从近转子 15m 平滑展开，近端 fadeIn 根除硬边切口，远端指数消散
        const ax = 15 + r * (r * 15 + 46)
        const fadeIn = Math.min(1, ax / 120)
        const fade = (1 - r / (N_RING - 1)) * fadeIn
        const a = 0.040 * fade * fade * Math.exp(-ax / 900)
        for (let kk = 0; kk < N_SEG; kk++) paA[base + r * N_SEG + kk] = a
      }
    }
    pg.setAttribute('position', new THREE.BufferAttribute(ppos, 3))
    pg.setAttribute('aA', new THREE.BufferAttribute(paA, 1))
    pg.setIndex(new THREE.BufferAttribute(idx, 1))
    pg.boundingSphere = new THREE.Sphere(new THREE.Vector3(FCX, 140, FCZ), 3200)
    const plumeObj = new THREE.Mesh(
      pg,
      new THREE.ShaderMaterial({
        vertexShader: PLUME_VERT, fragmentShader: PLUME_FRAG,
        transparent: true, depthWrite: false, side: THREE.DoubleSide,
        blending: THREE.AdditiveBlending,
      }),
    )
    plumeObj.frustumCulled = false
    streakObj.userData.px = px
    streakObj.userData.py = py
    streakObj.userData.pz = pz
    return { streaks: streakObj, plumes: plumeObj }
  }, [n])

  useEffect(
    () => () => {
      streaks.geometry.dispose()
      ;(streaks.material as THREE.Material).dispose()
      plumes.geometry.dispose()
      ;(plumes.material as THREE.Material).dispose()
    },
    [streaks, plumes],
  )

  useFrame((_state, dtRaw) => {
    const s = useSim.getState()
    const on = s.airflow
    streaks.visible = on
    plumes.visible = on
    if (!on) return
    const dt = FREEZE ? 0 : Math.min(0.05, dtRaw) // R42 freeze：粒子平流停摆（否则 Math.random 重生破坏确定性）
    const w = windAt(s.tHours)
    const baseU = w.u
    const th = (((w.fromDeg % 360) + 360) % 360) * (Math.PI / 180)
    const fx = Math.sin(th), fz = Math.cos(th)
    const cxv = fz, czv = -fx
    const ct = Math.min(0.9, thrustCt(baseU))
    const a = (1 - Math.sqrt(Math.max(0, 1 - ct))) / 2
    const twoA = 2 * a
    const rd035 = ROTOR_D * 0.35
    const NX = FARM.length
    const x9: number[] = new Array(NX), z9: number[] = new Array(NX), yawErr9: number[] = new Array(NX)
    for (let j = 0; j < NX; j++) {
      x9[j] = FARM[j].x
      z9[j] = FARM[j].z
      // P2：尾流偏折读【实际偏航】（执行器输出），与 farmSim/HUD/机头朝向同源 ——
      // 指令与实际之间的分钟级滞后，画面上看得见（烟羽跟着机头慢慢摆过去）。
      yawErr9[j] = s.actYaw[j] ?? 0
    }

    const g = streaks.geometry
    const pos = g.getAttribute('position') as THREE.BufferAttribute
    const ab = g.getAttribute('aB') as THREE.BufferAttribute
    const pa = pos.array as Float32Array
    const ba = ab.array as Float32Array
    const P = streaks.userData as { px: Float32Array; py: Float32Array; pz: Float32Array }
    const SPEED = 30 // 平流倍率：烟线过场 ~10s（视觉流速≈现场直播的 26 倍）
    const TRAIL = 0.11 // 拖尾时长（秒，仿真倍率后）→ 线长∝当地速度；0.3→0.11：用户反馈画面显乱，收短
    const now = phaseT(performance.now() / 1000)
    for (let i = 0; i < n; i++) {
      let px = P.px[i], py = P.py[i], pz = P.pz[i]
      let def2 = 0, lat = 0
      for (let j = 0; j < NX; j++) {
        const dx = px - x9[j], dz = pz - z9[j]
        const ax = dx * fx + dz * fz
        if (ax <= rd035) continue
        const cr = dx * cxv + dz * czv
        const sigma = ROTOR_D * 0.5 + WAKE_K * ax
        const q = (cr - wakeDeflection(yawErr9[j], ax)) / sigma
        const bell = Math.exp(-0.5 * q * q)
        const core = (ROTOR_D / (ROTOR_D + 2 * WAKE_K * ax)) ** 2
        const di = Math.min(0.85, twoA * core * bell)
        def2 += di * di
        lat += di * (q / (1 + Math.abs(q)))
      }
      const eff = Math.sqrt(Math.max(0.03, 1 - def2))
      const shear = 0.72 + 0.5 * Math.min(1, Math.log(Math.max(8, py) / 8) / Math.log(30))
      const sp = baseU * eff * shear * SPEED
      const vxs = (fx + cxv * lat * 1.35) * sp
      const vzs = (fz + czv * lat * 1.35) * sp
      const vys = lat * sp * 0.16 + (eff < 0.9 ? 6 : 0)
      const hx = px + vxs * dt, hy = py + vys * dt, hz = pz + vzs * dt
      const along = (hx - FCX) * fx + (hz - FCZ) * fz
      const across = (hx - FCX) * cxv + (hz - FCZ) * czv
      if (along > CX + 260 || Math.abs(across) > CX * 1.15 || hy > 330) {
        const back = -CX - Math.random() * 300
        const side = (Math.random() * 2 - 1) * CX * 0.94
        const nx = FCX + fx * back + cxv * side
        const nz = FCZ + fz * back + czv * side
        const ny = 4 + Math.random() ** 1.7 * 255
        P.px[i] = nx; P.py[i] = ny; P.pz[i] = nz
        pa[i * 6] = nx - vxs * TRAIL
        pa[i * 6 + 1] = ny
        pa[i * 6 + 2] = nz - vzs * TRAIL
        pa[i * 6 + 3] = nx; pa[i * 6 + 4] = ny; pa[i * 6 + 5] = nz
        ba[i * 2] = 0.015
        ba[i * 2 + 1] = 0.05 // 重生帧淡入，避免闪线
        continue
      }
      px = hx
      const gd = hy < 30 ? terrainSurfaceY(hx, hz) : 0
      py = hy < gd + 2.5 ? gd + 2.5 : hy
      pz = hz
      P.px[i] = px; P.py[i] = py; P.pz[i] = pz
      pa[i * 6] = px - vxs * TRAIL
      pa[i * 6 + 1] = py - vys * TRAIL
      pa[i * 6 + 2] = pz - vzs * TRAIL
      pa[i * 6 + 3] = px
      pa[i * 6 + 4] = py
      pa[i * 6 + 5] = pz
      const b = 0.05 + 0.36 * eff
      ba[i * 2] = b * 0.1
      ba[i * 2 + 1] = b
    }
    pos.needsUpdate = true
    ab.needsUpdate = true

    // —— 烟羽管体：环半径 Jensen 扩张 + 偏航横偏 + 行进波扰动 ——
    const cp = plumes.geometry.getAttribute('position') as THREE.BufferAttribute
    const ca = cp.array as Float32Array
    let c = 0
    for (let j = 0; j < NX; j++) {
      const ye = yawErr9[j]
      const by = terrainSurfaceY(x9[j], z9[j]) + 90
      for (let r = 0; r < N_RING; r++) {
        const ax = 15 + r * (r * 15 + 46)
        const rad0 = ROTOR_D * 0.50 + WAKE_K * ax
        const off = wakeDeflection(ye, ax)
        for (let kk = 0; kk < N_SEG; kk++) {
          const ang = (kk / N_SEG) * Math.PI * 2
          const wob = 1 + 0.025 * Math.sin(ang * 3 + now * 1.2 + j * 2.1)
          const o = Math.cos(ang) * rad0 * wob + off
          const h = Math.sin(ang) * rad0 * wob
          ca[c++] = x9[j] + fx * ax + cxv * o
          ca[c++] = by + h
          ca[c++] = z9[j] + fz * ax + czv * o
        }
      }
    }
    cp.needsUpdate = true
  })

  // 调试开关：?wakeoff 关闭 AirflowField 尾流视觉（用于排除法定位暗斑来源）
  if (debugEnabled() && new URLSearchParams(location.search).has('wakeoff')) return null
  return (
    <group>
      <primitive object={streaks} />
      <primitive object={plumes} />
    </group>
  )
}
