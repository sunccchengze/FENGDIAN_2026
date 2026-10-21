/* oxlint-disable react/immutability -- 同 WindVeil：帧循环 mutate uniforms（docs/08 D2） */
import { useMemo, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { FARM, SUBSTATION, terrainSurfaceY } from './terrainUtil'
import { mulberry32 } from '../data/rng'
import { skyState } from './lightState'
import { phaseT } from './freeze.ts'

// W3 星光铺地：谷地 + 电缆走廊两处加密（基准图地面冰晶微光）。
// D2/D11 修复：散布随机量改用 seed 派生 PRNG（StrictMode 双渲染/截图
// 复现不再抖动）；材质对象不再在 useMemo 里写 ref。
const VERT = /* glsl */ `
attribute float aPhase;
attribute float aSize;
varying float vTwinkle;
varying vec3 vColor;
uniform float uTime;
uniform float uDayF;
void main() {
  vColor = color;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  // 夜间闪烁更快更明显，白天收敛
  float night = 1.0 - uDayF;
  float tw = 0.42 + 0.58 * (0.5 + 0.5 * sin(uTime * (1.5 + night * 0.9) + aPhase * 40.0));
  // 夜间点尺寸更大，呼吸感更强
  float sizeBoost = 1.0 + night * (0.55 + 0.25 * sin(uTime * 0.6 + aPhase * 12.0));
  vTwinkle = tw * sizeBoost;
  gl_PointSize = min(aSize * tw * sizeBoost * (600.0 / -mv.z), 7.5 + night * 2.5);
  gl_Position = projectionMatrix * mv;
}
`
const FRAG = /* glsl */ `
precision highp float;
varying float vTwinkle;
varying vec3 vColor;
uniform float uDayF;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.08, d) * vTwinkle;
  float night = 1.0 - uDayF;
  // 第 19 轮：地面星光是三角块"蓝绿边缘"的另一来源，整体压暗（增益 1.35→0.85、alpha 0.75→0.42）
  // 夜间生机：亮度提升，青白更明显
  float gain = 0.85 + night * 0.55;
  float alphaMul = 0.42 + night * 0.38;
  gl_FragColor = vec4(vColor * gain, a * alphaMul);
}
`

export default function SparkleGround({ count = 4600 }: { count?: number }) {
  const built = useMemo(() => {
    const rnd = mulberry32(0xBEEF42)
    const g = new THREE.BufferGeometry()
    const pos = new Float32Array(count * 3)
    const phase = new Float32Array(count)
    const size = new Float32Array(count)
    const col = new Float32Array(count * 3)
    const c1 = new THREE.Color('#4a93b4')
    const c2 = new THREE.Color('#dcf4ff')
    for (let i = 0; i < count; i++) {
      let x: number, z: number
      if (i % 10 < 7) {
        const r = Math.sqrt(rnd()) * 1450
        const a = rnd() * Math.PI * 2
        x = Math.cos(a) * r * 1.15 + 80
        z = Math.sin(a) * r * 0.95 - 60
      } else {
        const u = FARM[(rnd() * FARM.length) | 0]
        const t = rnd()
        x = u.x + (SUBSTATION.x - u.x) * t + (rnd() - 0.5) * 150
        z = u.z + (SUBSTATION.z - u.z) * t + (rnd() - 0.5) * 150
      }
      pos[i * 3] = x
      pos[i * 3 + 1] = terrainSurfaceY(x, z) + 0.9 + rnd() * 3.0
      pos[i * 3 + 2] = z
      phase[i] = rnd()
      size[i] = 1.4 + rnd() * 3.4
      const c = rnd() < 0.82 ? c1 : c2
      col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b
    }
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('aPhase', new THREE.BufferAttribute(phase, 1))
    g.setAttribute('aSize', new THREE.BufferAttribute(size, 1))
    g.setAttribute('color', new THREE.BufferAttribute(col, 3))
    const m = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG,
      uniforms: { uTime: { value: 0 }, uDayF: { value: 1 } },
      transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, vertexColors: true,
    })
    return { geo: g, mat: m }
  }, [count])

  useEffect(() => () => {
    built.geo.dispose()
    built.mat.dispose()
  }, [built])

  useFrame((s) => {
    built.mat.uniforms.uTime.value = phaseT(s.clock.elapsedTime)
    built.mat.uniforms.uDayF.value = skyState.dayF
  })
  return <points geometry={built.geo} material={built.mat} frustumCulled={false} />
}
