/* oxlint-disable react/immutability -- R3F 帧循环内 mutate LineMaterial.resolution/脉冲实例矩阵为既定模式（docs/08 D2 说明） */
import { useMemo, useRef, useEffect } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { APPROACH, FARM, SUBSTATION, terrainSurfaceY } from './terrainUtil'
import { LAYOUT } from './layouts.ts'
import { buildHugPath, type HugPath } from '../data/paths.ts'
import { mulberry32 } from '../data/rng.ts'
import { phaseT } from './freeze.ts'

// ============================================================================
// 集电网络（v3：串接拓扑 + O(1) 脉冲）
// ---------------------------------------------------------------------------
//  · A8 拓扑修正：旧版"9 机各自 1 根放射电缆"不符合电气一次接线；
//    现改为 3 条集电回路：每条沿一"排"串接 3 台机组后汇入升压站
//    （3-4 机一串为 35kV 风电场集电线路的典型接法），外送段收为 2 回。
//  · D3 性能：脉冲不再逐帧 getPointAt —— 路径构建期离散为等弧长折线表
//    （data/paths.HugPath），每帧只做索引 + 线性插值。
//  · 亮度视角无关：Line2 屏幕空间等宽 + fog/toneMapped 关，任意机位粗细恒定
//    （用户钦定口径）。depthTest 于 2026-08-29 恢复为 true：旧"全关"把贴地的
//    集电线在远机上方位成悬浮光带（叠加曲线过冲 = 用户看到的飘环）；
//    粗细恒定本就由屏幕空间线宽保证，与遮挡无关。
//  · 电压等级 35 kV：以标注口径写进 HUD（不虚构电缆型号）。
// ============================================================================

const C_CORE = new THREE.Color(0.72, 0.92, 1.0)
const C_HALO = new THREE.Color(0.25, 0.62, 0.95)
const C_PULSE = new THREE.Color(0.85, 1.5, 2.0)
const C_GLITTER = new THREE.Color(0.45, 0.85, 1.15)
const LIFT = 2.6 // 示意悬高（真实为直埋），见文件头

const GL_VERT = /* glsl */ `
attribute float aPhase;
varying float vA;
uniform float uTime;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float tw = 0.55 + 0.45 * sin(uTime * 1.6 + aPhase * 22.0);
  vA = tw;
  gl_PointSize = 2.2 * (380.0 / max(-mv.z, 180.0));
  gl_Position = projectionMatrix * mv;
}
`
const GL_FRAG = /* glsl */ `
precision highp float;
varying float vA;
uniform vec3 uColor;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d) * vA;
  gl_FragColor = vec4(uColor, a);
}
`

function hug(x: number, z: number, extra = 0): number {
  return terrainSurfaceY(x, z) + LIFT + extra
}

export default function CableNetwork() {
  const pulses = useRef<THREE.InstancedMesh>(null!)
  const { size } = useThree()

  const built = useMemo(() => {
    const group = new THREE.Group()

    const matCore = new LineMaterial({
      color: C_CORE.getHex(),
      linewidth: 0.85,
      transparent: true,
      opacity: 0.75,
      depthWrite: false,
      depthTest: true,
      fog: false,
      blending: THREE.NormalBlending,
    })
    ;(matCore as THREE.ShaderMaterial).toneMapped = false
    const matHalo = new LineMaterial({
      color: C_HALO.getHex(),
      linewidth: 2.4,
      transparent: true,
      opacity: 0.16,
      depthWrite: false,
      depthTest: true,
      fog: false,
      blending: THREE.AdditiveBlending,
    })
    ;(matHalo as THREE.ShaderMaterial).toneMapped = false

    const pulseMat = new THREE.MeshBasicMaterial({
      color: C_PULSE,
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
      depthTest: true,
      fog: false,
      toneMapped: false,
      blending: THREE.AdditiveBlending,
    })
    const pulseGeo = new THREE.SphereGeometry(0.55, 8, 8)

    const paths: HugPath[] = []
    const pulseSpeeds: number[] = []
    const glitterPos: number[] = []
    const glitterPhase: number[] = []
    const rnd = mulberry32(20260828)

    const addLine = (plan: [number, number][], opts: { pulseSpeed?: number; glitter?: number } = {}) => {
      const { path, curvePts } = buildHugPath(plan, (x, z) => hug(x, z))
      paths.push(path)
      pulseSpeeds.push(opts.pulseSpeed ?? 0.09)
      const g = new LineGeometry()
      g.setPositions(curvePts)
      const haloLine = new Line2(g, matHalo)
      haloLine.renderOrder = 1
      haloLine.frustumCulled = false
      group.add(haloLine)
      const coreLine = new Line2(new LineGeometry().setPositions(curvePts), matCore)
      coreLine.renderOrder = 2
      coreLine.frustumCulled = false
      group.add(coreLine)
      // 沿线晶粒（闪烁）——构建期布点，运行期仅 shader 呼吸
      const n = opts.glitter ?? Math.floor(path.total / 9)
      for (let k = 0; k < n; k++) {
        const s = rnd() * path.total
        const p = [0, 0, 0]
        path.sample(s, p)
        const t = [0, 0, 0]
        path.sample(Math.min(path.total, s + 4), t)
        const dx = t[0] - p[0]
        const dz = t[2] - p[2]
        const len = Math.max(1e-6, Math.hypot(dx, dz))
        const off = (rnd() - 0.5) * 2.4
        const gx = p[0] + (-dz / len) * off
        const gz = p[2] + (dx / len) * off
        glitterPos.push(gx, hug(gx, gz, rnd() * 0.6), gz)
        glitterPhase.push(rnd())
      }
    }

    // ---- 集电回路：拓扑由布局给定（R42；docs/13 §4.1）----
    // 3×3 = 3 条回路，每条沿一"排"串接 3 台（西→东蛇形）后汇入升压站；
    // 1×3 = 1 条回路沿列南下串接 3 台后入站（符合电气一次接线，线条更少）。
    const feeder = (plan: [number, number][], entrance: [number, number], top: [number, number]) => {
      plan.push(entrance, top)
      addLine(plan, { pulseSpeed: 0.1 })
    }
    if (LAYOUT.cableTopology === 'column') {
      const col = [...FARM].sort((a, b) => a.z - b.z) // 北(上游)→南(下游)
      const plan: [number, number][] = []
      col.forEach((u, i) => {
        plan.push([u.x, u.z])
        if (i < col.length - 1) {
          // 相邻两机之间沿列方向的浅摆点（蛇形敷设，非直线魔法）
          const nx = col[i + 1]
          plan.push([(u.x + nx.x) / 2 + 18, (u.z + nx.z) / 2])
        }
      })
      feeder(plan, [SUBSTATION.x - 60, SUBSTATION.z - 96], [SUBSTATION.x - 40, SUBSTATION.z - 46])
    } else {
      for (let row = 0; row < 3; row++) {
        const inRow = FARM.filter((f) => f.row === row).sort((a, b) => a.x - b.x)
        const plan: [number, number][] = []
        inRow.forEach((u, i) => {
          plan.push([u.x, u.z])
          if (i < inRow.length - 1) {
            // 相邻两机之间加一个沿排方向的浅摆点（表达实际蛇形敷设，非直线魔法）
            const nx = inRow[i + 1]
            plan.push([(u.x + nx.x) / 2, (u.z + nx.z) / 2 + 18])
          }
        })
        // 串接尾 → 升压站对应侧的进线段
        feeder(plan, [SUBSTATION.x - 60 + row * 30, SUBSTATION.z - 96 - row * 8], [SUBSTATION.x - 40 + row * 40, SUBSTATION.z - 46])
      }
    }

    // ---- 外送：升压站 → 220kV 出线构架 → 场外的 2 回出线 ----
    for (const k of [-1, 1]) {
      addLine(
        [
          [SUBSTATION.x + 58, SUBSTATION.z + k * 14],
          [SUBSTATION.x + 260, SUBSTATION.z + k * 90],
          [(SUBSTATION.x + APPROACH.x) / 2 + k * 30, (SUBSTATION.z + APPROACH.z) / 2 + k * 70],
          [APPROACH.x, APPROACH.z + k * 40],
        ],
        { pulseSpeed: 0.16, glitter: 40 },
      )
    }

    const gg = new THREE.BufferGeometry()
    gg.setAttribute('position', new THREE.Float32BufferAttribute(glitterPos, 3))
    gg.setAttribute('aPhase', new THREE.Float32BufferAttribute(glitterPhase, 1))
    const gm = new THREE.ShaderMaterial({
      vertexShader: GL_VERT,
      fragmentShader: GL_FRAG,
      uniforms: { uTime: { value: 0 }, uColor: { value: C_GLITTER } },
      transparent: true,
      depthWrite: false,
      depthTest: true,
      blending: THREE.AdditiveBlending,
      fog: false,
      toneMapped: false,
    })
    const glitter = new THREE.Points(gg, gm)
    glitter.renderOrder = 3
    glitter.frustumCulled = false
    group.add(glitter)

    const perCurve = 3
    return {
      group, paths, perCurve, pulseGeo, pulseMat,
      glitterMat: gm, lineMats: [matCore, matHalo], pulseSpeeds,
      total: paths.length * perCurve,
    }
  }, [])

  const dummy = useMemo(() => new THREE.Object3D(), [])
  const buf = useMemo(() => new Float32Array(3), [])
  useFrame((s) => {
    const t = phaseT(s.clock.elapsedTime)
    built.glitterMat.uniforms.uTime.value = t
    const dpr = s.viewport.dpr
    for (const m of built.lineMats) m.resolution.set(size.width * dpr, size.height * dpr)
    const im = pulses.current
    if (!im) return
    let k = 0
    for (let i = 0; i < built.paths.length; i++) {
      const p = built.paths[i]
      const speed = built.pulseSpeeds[i]
      for (let j = 0; j < built.perCurve; j++) {
        const tt = (t * speed + j / built.perCurve + i * 0.137) % 1
        p.sample(tt * p.total, buf)
        const fade = Math.sin(tt * Math.PI)
        dummy.position.set(buf[0], buf[1] + 0.4, buf[2])
        dummy.scale.setScalar(0.55 + 0.5 * fade)
        dummy.updateMatrix()
        im.setMatrixAt(k++, dummy.matrix)
      }
    }
    im.instanceMatrix.needsUpdate = true
  })

  useEffect(() => {
    const dpr = window.devicePixelRatio || 1
    for (const m of built.lineMats) m.resolution.set(size.width * dpr, size.height * dpr)
  }, [built, size])

  useEffect(() => () => {
    built.group.traverse((o) => {
      const any = o as unknown as { geometry?: THREE.BufferGeometry; material?: THREE.Material | THREE.Material[] }
      any.geometry?.dispose?.()
      const mm = any.material
      if (Array.isArray(mm)) mm.forEach((x) => x.dispose())
      else mm?.dispose?.()
    })
  }, [built])

  return (
    <group>
      <primitive object={built.group} />
      <instancedMesh
        ref={pulses}
        args={[built.pulseGeo, built.pulseMat, built.total]}
        frustumCulled={false}
        renderOrder={4}
      />
    </group>
  )
}
