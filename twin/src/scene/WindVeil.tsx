/* oxlint-disable react/immutability -- R3F 帧循环内 mutate geometry position 缓冲为既定性能模式（docs/08 D2 说明） */
import { useMemo, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { FARM, terrainSurfaceY } from './terrainUtil'
import { buildPathFromCurve, type HugPath } from '../data/paths.ts'
import { mulberry32 } from '../data/rng.ts'
import { windAt } from '../data/farmSim.ts'
import { wakeDeficit } from '../data/turbinePhysics.ts'
import { sampleWorldU, floris3DBound, type FlorisCase } from '../data/florisData.ts'
import { useSim } from '../state/simStore'

/** 北来风时按上游行（row0）偏航选择最接近的 FLORIS 3D 场工况 */
function fcOf(yawDeg: number): FlorisCase {
  const a = Math.abs(yawDeg)
  if (a < 7.5) return '+00'
  if (a < 22.5) return yawDeg > 0 ? '+15' : '-15'
  return yawDeg > 0 ? '+30' : '-30'
}

/** 粒子点处的当地风速：FLORIS 真场优先（仅北来风，覆盖区 T07→T04 走廊），
 *  区外退回与 farmSim 同一套解析尾流（wakeDeficit RSS 合成） */
function localWindU(
  x: number, h: number, z: number, baseU: number, fromDeg: number,
  yaw9: number[], fc: FlorisCase | null,
): number {
  if (fc) {
    const v = sampleWorldU(fc, x, h, z)
    if (v !== null && Number.isFinite(v)) return Math.max(0.6, v)
  }
  let def2 = 0
  for (let i = 0; i < FARM.length; i++) {
    const d = wakeDeficit(baseU, x - FARM[i].x, z - FARM[i].z, fromDeg, yaw9[i] ?? 0)
    def2 += d * d
  }
  return baseU * Math.sqrt(Math.max(0.02, 1 - def2))
}

// ===========================================================================
// 风况粒子（v3：性能 + 可复现 + 语义恒定）
// ---------------------------------------------------------------------------
// 全场风只有一种语义：主导风向 = 北 → 南（+z），与 A4 修正后的转子迎风
// 朝向（机头朝北）、farmSim 坐标约定三方一致：
//   ① 远脊来流 —— 北岭后高空南下，只做纵深氛围；
//   ② 列向来流 —— 近场 11 条流线沿 z 向穿过远/中/近三排（尾流叙事），
//      途经机组轻微绕流。
// D3：流线构建期离散为等弧长折线表（data/paths），每帧只做索引+插值；
// D2：粒子随机量全部由 seed 派生（mulberry32），StrictMode/截图 A/B 可复现；
// D10：?noveil 调试开关仅在 DEV 或 ?debug=1 下生效。
// ===========================================================================

const VERT = /* glsl */ `
attribute float aSize;
attribute float aBright;
varying float vB;
void main() {
  vB = aBright;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = min(aSize * (560.0 / -mv.z), 6.5);
  gl_Position = projectionMatrix * mv;
}
`
const FRAG = /* glsl */ `
precision highp float;
varying float vB;
uniform vec3 uColor;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.1, d) * vB;
  gl_FragColor = vec4(uColor * 1.6, a);
}
`

import { debugEnabled, hasFlag } from '../data/debug.ts'
import { phaseT, FREEZE } from './freeze.ts'

interface StreamDef {
  pts: THREE.Vector3[]
  count: number
  speed: number
  size: number
  bright: number
  wig: number
  /** true=列向来流：每帧按当地风速（FLORIS 真场/解析尾流）调制前进速度与亮度 */
  mod?: boolean
}

export default function WindVeil() {
  const built = useMemo(() => {
    const rnd = mulberry32(0x5EED42)
    const defs: StreamDef[] = []

    // ①（已删除 2026-08-29）远脊来流：高空氛围流在 depthTest:false 下投影成
    //    发光套索环悬浮于天地之间（用户实拍反馈），语义冗余且违和——移除，
    //    全场只保留有物理叙事（尾流减速/聚堆）的列向来流。

    // ② 列向来流（11 条，北→南）
    // 列向流线覆盖 FLORIS 阵列列位（colsX −732..532 ±20 抖动 + 两侧余量）
    const laneXs = [-820, -660, -490, -330, -190, -60, 90, 250, 410, 570, 730]
    laneXs.forEach((lx, li) => {
      const pts: THREE.Vector3[] = []
      const n = 8
      for (let i = 0; i < n; i++) {
        const t = i / (n - 1)
        const z = -1500 + t * 2100
        let x = lx + t * 300 + Math.sin(t * 4.4 + li) * 46
        for (const u of FARM) {
          const dz = z - u.z
          const dx = x - u.x
          const dd = Math.hypot(dx, dz)
          if (dd < 130) x += (dx / Math.max(dd, 1)) * (130 - dd) * 0.5
        }
        pts.push(new THREE.Vector3(x, terrainSurfaceY(x, z) + 9 + Math.sin(t * Math.PI) * 26 + (li % 3) * 7, z))
      }
      defs.push({ pts, count: 64, speed: 0.05, size: 2.7, bright: 0.8, wig: 7.5, mod: true })
    })

    const streams: { path: HugPath; count: number; speed: number; wig: number; speedFrac: number; mod: boolean; o0: number }[] = []
    const total = defs.reduce((s, d) => s + d.count, 0)
    const pos = new Float32Array(total * 3)
    const aSize = new Float32Array(total)
    const aBright = new Float32Array(total)
    const seeds = new Float32Array(total * 2)
    let o = 0
    for (const d of defs) {
      const path = buildPathFromCurve(new THREE.CatmullRomCurve3(d.pts, false, 'catmullrom', 0.3), 192)
      streams.push({ path, count: d.count, speed: 0, wig: d.wig, speedFrac: d.speed, mod: !!d.mod, o0: o })
      for (let j = 0; j < d.count; j++, o++) {
        seeds[o * 2] = rnd()
        seeds[o * 2 + 1] = rnd() * Math.PI * 2
        aSize[o] = d.size * (0.45 + rnd() * 1.55)
        aBright[o] = d.bright * (0.35 + rnd() * 0.65)
      }
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('aSize', new THREE.BufferAttribute(aSize, 1))
    g.setAttribute('aBright', new THREE.BufferAttribute(aBright, 1))
    const m = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG,
      uniforms: { uColor: { value: new THREE.Color('#7fd2f2') } },
      transparent: true, depthWrite: false,
      // 2026-08-29 根因：旧 depthTest:false 让远端粒子流不被山体遮挡，投影成
      // 悬浮光带（用户实拍"飘环"的另一半来源）。粒子贴地飞行，遮挡就该发生。
      depthTest: true,
      fog: false, toneMapped: false,
      blending: THREE.AdditiveBlending,
    })
    const p = new THREE.Points(g, m)
    p.frustumCulled = false
    p.renderOrder = 2
    const frac = new Float32Array(total)
    for (let i = 0; i < total; i++) frac[i] = seeds[i * 2]
    const brightBase = Float32Array.from(aBright)
    return { points: p, streams, seeds, mat: m, frac, brightBase }
  }, [])

  useEffect(() => () => {
    built.points.geometry.dispose()
    built.mat.dispose()
  }, [built])

  const buf = useMemo(() => new Float32Array(3), [])
  useFrame((s, deltaRaw) => {
    const delta = FREEZE ? 0 : deltaRaw // R42 freeze：粒子沿线推进停摆
    const t = phaseT(s.clock.elapsedTime)
    const posAttr = built.points.geometry.attributes.position as THREE.BufferAttribute
    const arr = posAttr.array as Float32Array
    const brightAttr = built.points.geometry.attributes.aBright as THREE.BufferAttribute
    const bArr = brightAttr.array as Float32Array
    // 风场口径（每帧一次）：仿真时刻的来流 + 偏航指令 → 真场工况或解析尾流
    const st0 = useSim.getState()
    const { u: baseU, fromDeg } = windAt(st0.tHours)
    const yaw9 = st0.unitYaw
    const fc = floris3DBound() && Math.cos((fromDeg * Math.PI) / 180) > 0.96 ? fcOf(yaw9[0]) : null
    let o = 0
    for (const stm of built.streams) {
      const { path, count, speedFrac, wig, mod } = stm
      const total = path.total
      for (let j = 0; j < count; j++, o++) {
        let sPos: number
        if (mod) {
          // 沿弧长积分前进：速度随当地风速缩放（尾流中减速、聚堆、变暗）
          const cur = built.frac[o]
          path.sample(cur * total, buf)
          const uL = localWindU(buf[0], buf[1], buf[2], baseU, fromDeg, yaw9, fc)
          const r = Math.min(1.6, Math.max(0.05, uL / Math.max(1e-3, baseU)))
          built.frac[o] = (cur + delta * speedFrac * Math.pow(r, 1.6)) % 1
          sPos = built.frac[o] * total
          path.sample(sPos, buf)
          bArr[o] = built.brightBase[o] * (0.22 + 1.05 * Math.min(1, Math.max(0, (r - 0.42) / 0.52)))
        } else {
          sPos = (built.seeds[o * 2] * total + t * speedFrac * total) % total
        }
        const ph = built.seeds[o * 2 + 1]
        arr[o * 3] = buf[0] + Math.sin(t * 1.3 + ph) * wig
        arr[o * 3 + 1] = buf[1] + Math.sin(t * 1.7 + ph * 2.0) * (wig * 0.7)
        arr[o * 3 + 2] = buf[2] + Math.cos(t * 1.1 + ph) * wig
      }
    }
    posAttr.needsUpdate = true
    brightAttr.needsUpdate = true
  })

  if (debugEnabled() && hasFlag('noveil')) return null
  return <primitive object={built.points} />
}
