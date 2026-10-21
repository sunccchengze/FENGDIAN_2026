import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { SUBSTATION, terrainSurfaceY } from './terrainUtil'
import { skyState } from './lightState'
import { phaseT } from './freeze.ts'

// ============================================================================
// 升压站（v3：比例与要素修正 —— docs/07 A8）
// ----------------------------------------------------------------------------
//  · 主体不再用"76m 高实心巨盒"：220kV 站构架真实高度约 20-30m；
//    现取 30m（H=30），并补齐可视化可辨的电气要素：
//    门型构架×2 + V 型绝缘子串（示意）、主变×3（带套管束）、
//    控楼、围墙光桩、母线桥——全部保持玻璃/晶格全息语言，不引入写实皮肤。
//  · 几何为【示意】：表达"功率在此升压外送"的空间关系，不宣称符合任何
//    具体站的施工总平面。
// ============================================================================

const C_EDGE = new THREE.Color(0.5, 1.35, 1.72)
const C_CORE = new THREE.Color(0.95, 1.85, 2.2)

export default function Substation() {
  const lightRef = useRef<THREE.PointLight>(null!)
  const lightRef2 = useRef<THREE.PointLight>(null!)
  useFrame((state) => {
    const night = 1 - skyState.dayF
    const t = phaseT(state.clock.elapsedTime)
    const flick = 0.85 + 0.15 * Math.sin(t * 0.9)
    if (lightRef.current) {
      lightRef.current.intensity = night * (12 + 4 * flick)
    }
    if (lightRef2.current) {
      lightRef2.current.intensity = night * (7 + 2.5 * Math.sin(t * 0.6 + 1.2))
    }
  })
  const mats = useMemo(() => {
    const mkAdd = (o: THREE.MeshBasicMaterialParameters) =>
      new THREE.MeshBasicMaterial({ blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, fog: false, ...o })
    return {
      dark: new THREE.MeshBasicMaterial({ color: '#040c15', transparent: true, opacity: 0.9 }),
      lattice: mkAdd({ color: C_EDGE, wireframe: true, opacity: 0.5 }),
      glass: mkAdd({ color: C_EDGE, opacity: 0.08, side: THREE.DoubleSide }),
      core: mkAdd({ color: C_CORE, opacity: 0.9 }),
      pad: mkAdd({ color: C_EDGE, opacity: 0.4, side: THREE.DoubleSide }),
      padSoft: mkAdd({ color: C_EDGE, opacity: 0.1, side: THREE.DoubleSide }),
      rail: mkAdd({ color: C_CORE, opacity: 0.55 }),
      // 描边层：depthTest:false + renderOrder 置顶（见上注释：与 dark 体块同面深度会被平局覆盖）；纯白 alpha 细线，非 addi混合
      edge: new THREE.LineBasicMaterial({ color: '#eaf9ff', transparent: true, opacity: 0.92, depthTest: false, depthWrite: false, fog: false, toneMapped: false }),
      edgeHi: new THREE.LineBasicMaterial({ color: '#f4fdff', transparent: true, opacity: 1.0, depthTest: false, depthWrite: false, fog: false, toneMapped: false }),
      bush: mkAdd({ color: C_EDGE, opacity: 0.7 }),
    }
  }, [])
  const y = terrainSurfaceY(SUBSTATION.x, SUBSTATION.z)
  const W = 112, H = 30, D = 52
  // 晶格描边（任务#6）：主体体块EdgesGeometry硬边，强化"全息线稿"语言
  const edges = useMemo(() => ({
    platform: new THREE.EdgesGeometry(new THREE.BoxGeometry(W + 40, 2.4, D + 40), 24),
    ctrl: new THREE.EdgesGeometry(new THREE.BoxGeometry(36, 12, 16), 24),
    roof: new THREE.EdgesGeometry(new THREE.BoxGeometry(37.2, 0.5, 17.2), 24),
    trans: new THREE.EdgesGeometry(new THREE.CylinderGeometry(5.8, 5.8, 13, 10, 1), 30),
    gate: new THREE.EdgesGeometry(new THREE.BoxGeometry(33.6, 1.1, 1.1), 24),
    leg: new THREE.EdgesGeometry(new THREE.BoxGeometry(1.2, H, 1.2), 24),
    bus: new THREE.EdgesGeometry(new THREE.BoxGeometry(76, 0.7, 0.7), 24),
    // 周界围墙"光绳"：沿光桩顶面的矩形 LineLoop（与桩位同坐标）
    fence: (() => {
      const hx = W / 2 + 12, hz = D / 2 + 8
      const pts = [[-hx, -hz], [hx, -hz], [hx, hz], [-hx, hz]].map(([fx, fz]) => new THREE.Vector3(fx, 8.7, fz))
      return new THREE.BufferGeometry().setFromPoints(pts)
    })(),
  }), [])

  return (
    <group position={[SUBSTATION.x, y, SUBSTATION.z]}>
      {/* 平台与同心光环（比旧版收敛） */}
      <mesh position={[0, 1.2, 0]} material={mats.dark}><boxGeometry args={[W + 40, 2.4, D + 40]} /></mesh>
      <lineSegments geometry={edges.platform} material={mats.edge} position={[0, 1.2, 0]} renderOrder={7} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 2.6, 0]} material={mats.padSoft}>
        <circleGeometry args={[92, 56]} />
      </mesh>
      {[66, 82].map((r, i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, 0]} position={[0, 2.7, 0]} material={mats.pad}>
          <ringGeometry args={[r, r + 1.4, 64]} />
        </mesh>
      ))}

      {/* 主控楼（2026-08-29 可读性修正）：真实 220kV 主控通信楼约 36×16m；
          底座坐在平台面上（顶 y=2.4）而非埋进台体；补接原"玻璃面"材质——
          之前只写了注释没挂 mesh，这就是"长方体外形看不到"的直接原因；
          描边换高亮线（alpha 1.0），中远景也能读出体块。 */}
      <group position={[-W / 2 + 17, 2.4, -D / 2 + 10]}>
        <mesh position={[0, 6, 0]} material={mats.dark}><boxGeometry args={[36, 12, 16]} /></mesh>
        <mesh position={[0, 6, 0]} material={mats.glass}><boxGeometry args={[36.4, 12.4, 16.4]} /></mesh>
        <mesh position={[0, 6, 0]} material={mats.lattice}><boxGeometry args={[36.2, 12.2, 16.2, 4, 2, 2]} /></mesh>
        <lineSegments geometry={edges.ctrl} material={mats.edgeHi} position={[0, 6, 0]} renderOrder={8} />
        {/* 女儿墙压顶：顶部细环让"楼顶"读得出来 */}
        <lineSegments geometry={edges.roof} material={mats.edgeHi} position={[0, 12.15, 0]} renderOrder={8} />
      </group>

      {/* 主变 ×3 + 套管束（不再是"圆柱顶球"） */}
      {[-34, -4, 26].map((dx, i) => (
        <group key={i} position={[dx, 2.6, D / 2 - 14]}>
          <mesh position={[0, 6.5, 0]} material={mats.dark}><cylinderGeometry args={[5.8, 5.8, 13, 10]} /></mesh>
          <lineSegments geometry={edges.trans} material={mats.edge} position={[0, 6.5, 0]} renderOrder={7} />
          <mesh position={[0, 6.5, 0]} material={mats.lattice}><cylinderGeometry args={[5.9, 5.9, 13.1, 10, 2]} /></mesh>
          {/* 三相高压套管 */}
          {[-2.6, 0, 2.6].map((bx, k) => (
            <mesh key={k} position={[bx, 15.6, -1.2]} material={mats.bush}>
              <cylinderGeometry args={[0.28, 0.5, 5.4, 6]} />
            </mesh>
          ))}
        </group>
      ))}

      {/* 门型构架 ×2（220kV 出线架，横梁标高 = 站构架高 H） */}
      {[-14, 26].map((gx, i) => (
        <group key={i} position={[gx, 2.6, -6]}>
          {[-16, 16].map((px, k) => (
            <group key={k} position={[px, H / 2, 0]}>
              <mesh material={mats.rail}><boxGeometry args={[1.2, H, 1.2]} /></mesh>
              <lineSegments geometry={edges.leg} material={mats.edge} renderOrder={7} />
            </group>
          ))}
          <mesh position={[0, H, 0]} material={mats.rail}><boxGeometry args={[33.6, 1.1, 1.1]} /></mesh>
          <lineSegments geometry={edges.gate} material={mats.edge} position={[0, H, 0]} renderOrder={7} />
          {/* V 型绝缘子串（示意，6 串） */}
          {[-10, 0, 10].map((bx, k) => (
            <group key={k}>
              <mesh position={[bx, H - 3.4, 0]} rotation={[0, 0, 0.6]} material={mats.bush}><cylinderGeometry args={[0.22, 0.22, 6.8, 5]} /></mesh>
              <mesh position={[bx, H - 3.4, 0]} rotation={[0, 0, -0.6]} material={mats.bush}><cylinderGeometry args={[0.22, 0.22, 6.8, 5]} /></mesh>
            </group>
          ))}
        </group>
      ))}

      {/* 母线桥（主变 → 构架横梁） */}
      <mesh position={[6, H + 0.9, -1]} material={mats.core}><boxGeometry args={[76, 0.7, 0.7]} /></mesh>
      <lineSegments geometry={edges.bus} material={mats.edge} position={[6, H + 0.9, -1]} renderOrder={7} />
      <lineLoop geometry={edges.fence} material={mats.edge} renderOrder={7} />

      {/* 周界光桩（围墙语义） */}
      {[-W / 2 - 12, -W / 4, 0, W / 4, W / 2 + 12].flatMap((dx) => [-D / 2 - 8, D / 2 + 8].map((dz) => (
        <mesh key={`${dx}-${dz}`} position={[dx, 5, dz]} material={mats.rail}>
          <boxGeometry args={[1, 7.4, 1]} />
        </mesh>
      )))}
      {/* 夜间生机：升压站点光，照亮站区，夜晚可见 */}
      <pointLight ref={lightRef} position={[0, 18, 0]} intensity={0} distance={220} decay={2} color="#8fd4ff" />
      <pointLight ref={lightRef2} position={[-W / 2 + 17, 10, -D / 2 + 10]} intensity={0} distance={120} decay={2} color="#b8e8ff" />
    </group>
  )
}
