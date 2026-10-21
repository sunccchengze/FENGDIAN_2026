/* oxlint-disable react/immutability -- 帧循环内 mutate uniforms 为 R3F 标准模式（docs/08 D2） */
import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { terrainSurfaceY, treeAccept, TREE_SPAN_M, mulberry32 } from './terrainUtil'
import { skyState } from './lightState'
import { windAt } from '../data/farmSim'
import { useSim } from '../state/simStore'
import { phaseT } from './freeze.ts'

// ============================================================
// R36 · 远岸森林（coastal_3d_v2 vegetation.ts 的本仓口径）
// ------------------------------------------------------------
// 诉求：round31 用户钦定「海陆视觉差异要大：近海黄沙、远海森林」——
// 此前林带只是地形着色（cForest 平涂），没有立体天际线。
// 本组件以「实例化低模针叶树」补足：
//  · 落位 = treeAccept（terrainUtil 同一真值：biomeWeights 林带密/缓丘稀、
//    雪线以上不长、坡度 ny<0.62 不长、越过沙岸潮带）；
//  · 单株 ~41 三角（干 + 三层锥），InstancedBufferGeometry 一次画完（+1 draw call）；
//  · 顶点风摆：梢部 t² 幅度、世界相位 + 实例种子（攒动不齐步）；
//  · 着色与 WorldTerrain 陆地同口径：莫兰迪低饱和墨绿、昼夜压暗/月光冷调、
//    指数雾；不进 PBR/阴影链（远景剪影质感，克制不惹眼）；
//  · 画质分档：high 全量 / medium 减半 / low 不画（instanceCount 运行时可调，
//    不重建几何/着色器）。
// ============================================================

/** 各画质档树数（high 全量 4800；medium 2400；low 600 低密度剪影，告别整片空秃）。
 *  模块内部常量（不导出：组件文件只导出组件，保 fast-refresh，lint 0 警告口径）。
 *  实测 high=4800 ≈ +19 万三角 / +1 draw call（单实例化批次）。 */
const TREE_TIERS = { high: 4800, medium: 2400, low: 600 } as const

const VERT = /* glsl */ `
attribute vec4 aInst;   // xyz 世界落位（根部），w 树高（米）
attribute vec2 aRot;    // x 朝向角, y 实例种子 [0,1)
attribute vec3 aNorm;   // 局部法线（构建期算好）
uniform float uTime;
uniform vec2 uWind;
uniform vec3 uSunDir;
varying vec3 vCol;
varying float vLit;
varying float vFogDepth;

float hash21(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }

void main() {
  float scale = aInst.w;
  float t = position.y;            // 0 根 → 1 梢
  float c = cos(aRot.x), s = sin(aRot.x);
  vec3 p = position;
  vec2 rxz = vec2(p.x * c - p.z * s, p.x * s + p.z * c);
  // 风摆：梢部 t² 摆、树干稳；世界相位 + 实例种子 → 攒动不齐步；
  // 慢包络（阵风强弱交替）×快摆动，幅度 ≈0.4m @12m 树
  float gustEnv = 0.55 + 0.45 * sin(uTime * 0.23 + aRot.y * 9.4);
  float sway = sin(uTime * 1.05 + aInst.x * 0.05 + aInst.z * 0.04 + aRot.y * 6.2832);
  vec2 windOff = uWind * sway * gustEnv * 0.030 * t * t * scale;
  vec3 world = vec3(aInst.x + rxz.x * scale + windOff.x,
                    aInst.y + t * scale,
                    aInst.z + rxz.y * scale + windOff.y);
  // 顶点色：干褐灰 → 冠层墨绿（莫兰迪低饱和，与 cForest 同族）；梢部微亮
  vec3 trunkCol = vec3(0.150, 0.120, 0.095);
  vec3 crownA   = vec3(0.042, 0.098, 0.058);
  vec3 crownB   = vec3(0.082, 0.145, 0.082);
  float cm = smoothstep(0.18, 0.40, t);
  vec3 base = mix(trunkCol, mix(crownA, crownB, smoothstep(0.30, 1.00, t)), cm);
  base *= 0.86 + 0.28 * hash21(vec2(aRot.y, floor(t * 5.0))); // 实例/层次明暗差
  vCol = base;
  // 受光：法线随朝向角旋转后对太阳（远景也要有向阳/背阳的立体感）
  vec3 n = normalize(vec3(aNorm.x * c - aNorm.z * s, aNorm.y, aNorm.x * s + aNorm.z * c));
  vLit = 0.62 + 0.38 * clamp(dot(n, uSunDir) * 0.5 + 0.5, 0.0, 1.0);
  vec4 mv = modelViewMatrix * vec4(world, 1.0);
  vFogDepth = -mv.z;
  gl_Position = projectionMatrix * mv;
}
`

const FRAG = /* glsl */ `
precision highp float;
varying vec3 vCol;
varying float vLit;
varying float vFogDepth;
uniform float uDayF;
uniform vec3 uMoonDir;
uniform vec3 uFogColor;
uniform float uFogDensity;
uniform float uWarmF; // R37 太阳色温（0=白 1=红）：向阳树冠暖调

void main() {
  vec3 col = vCol;
  // 昼夜口径与 WorldTerrain 陆地一致（R36c 同步）：白天受光塑形不变；
  // 夜间改【乘性】月光（旧版加性 wrap +0.30×0.3 抬灰底 → 与地形同病的灰白树影墙）
  float nightT = 1.0 - uDayF;
  float moonUpT = clamp(uMoonDir.y, 0.0, 1.0);
  vec3 nightMultT = vec3(0.040, 0.050, 0.070) * (0.55 + 0.45 * moonUpT)
    + vec3(0.62, 0.78, 1.00) * (0.10 * moonUpT);
  col *= mix(0.80, vLit, uDayF * 0.92);
  // R37 晨昏修正：与地形同口径 —— 晨昏暖光出现时夜乘数让位（深夜不变）
  col *= mix(vec3(1.0), nightMultT, nightT * (1.0 - 0.85 * uWarmF));
  // R37 日照金山：向阳树冠吃晨光暖调（背阴保持冷绿；窗口外逐字旧色）
  col *= mix(vec3(1.0), vec3(1.18, 0.95, 0.75), uWarmF * vLit * 0.35);
  // 指数雾（与场景雾同式；树是陆地，吃全雾）
  float fogF = 1.0 - exp(-uFogDensity * uFogDensity * vFogDepth * vFogDepth);
  col = mix(col, uFogColor, clamp(fogF, 0.0, 1.0));
  gl_FragColor = vec4(col, 1.0);
}
`

// ---- 单株针叶树几何（归一化：y∈[0,1]，半径按树高比例）----
// 干（5 棱台）+ 三层交叠锥（7 棱、只侧面）：~41 三角，远看是层叠剪影。
function buildTreeGeometry(): THREE.BufferGeometry {
  const pos: number[] = []
  const nrm: number[] = []
  const pushTri = (
    ax: number, ay: number, az: number, bx: number, by: number, bz: number,
    cx: number, cy: number, cz: number,
    na: THREE.Vector3, nb: THREE.Vector3, nc: THREE.Vector3,
  ) => {
    pos.push(ax, ay, az, bx, by, bz, cx, cy, cz)
    nrm.push(na.x, na.y, na.z, nb.x, nb.y, nb.z, nc.x, nc.y, nc.z)
  }
  // 树干：5 棱台（r0→r1，y0→y1），顶隐在第一层锥里
  {
    const y0 = 0, y1 = 0.34, r0 = 0.030, r1 = 0.016, seg = 5
    for (let i = 0; i < seg; i++) {
      const a0 = (i / seg) * Math.PI * 2, a1 = ((i + 1) / seg) * Math.PI * 2
      const n0 = new THREE.Vector3(Math.cos(a0), 0.25, Math.sin(a0)).normalize()
      const n1 = new THREE.Vector3(Math.cos(a1), 0.25, Math.sin(a1)).normalize()
      pushTri(
        Math.cos(a0) * r0, y0, Math.sin(a0) * r0,
        Math.cos(a1) * r0, y0, Math.sin(a1) * r0,
        Math.cos(a1) * r1, y1, Math.sin(a1) * r1,
        n0, n1, n1,
      )
      pushTri(
        Math.cos(a0) * r0, y0, Math.sin(a0) * r0,
        Math.cos(a1) * r1, y1, Math.sin(a1) * r1,
        Math.cos(a0) * r1, y1, Math.sin(a0) * r1,
        n0, n1, n0,
      )
    }
  }
  // 三层锥（base y → tip y，底半径 r；7 棱侧面）
  const cones: Array<[number, number, number]> = [
    [0.14, 0.52, 0.300],
    [0.34, 0.74, 0.230],
    [0.56, 1.00, 0.155],
  ]
  for (const [y0, y1, r] of cones) {
    const seg = 7
    for (let i = 0; i < seg; i++) {
      const a0 = (i / seg) * Math.PI * 2, a1 = ((i + 1) / seg) * Math.PI * 2
      // 锥面法线：径向 + 上倾（近似，剪影足够）
      const mid = (a0 + a1) / 2
      const tilt = r / Math.max(0.01, y1 - y0)
      const nm = new THREE.Vector3(Math.cos(mid), tilt, Math.sin(mid)).normalize()
      const n0 = new THREE.Vector3(Math.cos(a0), tilt, Math.sin(a0)).normalize()
      const n1 = new THREE.Vector3(Math.cos(a1), tilt, Math.sin(a1)).normalize()
      pushTri(
        Math.cos(a0) * r, y0, Math.sin(a0) * r,
        Math.cos(a1) * r, y0, Math.sin(a1) * r,
        0, y1, 0,
        n0, n1, nm,
      )
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
  g.setAttribute('aNorm', new THREE.Float32BufferAttribute(nrm, 3))
  return g
}

interface TreeSet {
  geo: THREE.InstancedBufferGeometry
  mat: THREE.ShaderMaterial
  count: number
}

/** 几何 + 材质立即可用（空实例）；落位数据延迟填充（见 fillPlacements）——
 *  4800 株拒绝采样 ≈1.6s CPU，放首帧前会顶住 Loading 屏（round25 红线），
 *  改为 splash 之后就绪、开场运镜期间悄然长出（远景，无感）。 */
function createSet(): TreeSet {
  const base = buildTreeGeometry()
  const geo = new THREE.InstancedBufferGeometry()
  geo.attributes.position = base.attributes.position
  geo.attributes.aNorm = base.attributes.aNorm
  geo.instanceCount = 0

  const mat = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: {
      uTime: { value: 0 },
      uWind: { value: new THREE.Vector2(0, 1) },
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
      uDayF: { value: 1 },
      uMoonDir: { value: new THREE.Vector3(0, 1, 0) },
      uFogColor: { value: new THREE.Color('#040911') },
      uFogDensity: { value: 0.00013 },
      uWarmF: { value: 0 },
    },
    side: THREE.DoubleSide,
  })
  mat.customProgramCacheKey = () => 'tree-field-r36'
  return { geo, mat, count: 0 }
}

/** 拒绝采样分帧落位（解决 T3b 首帧 2.5s~5s 长尖峰：分帧每批 600 株渐进落盘）。
 *  写入实例属性并抬 instanceCount；幂等。 */
function fillPlacementsChunked(
  set: TreeSet,
  targetCount: number,
): () => void {
  let cancelled = false
  const budget = targetCount
  if (set.count >= budget) {
    set.geo.instanceCount = budget
    return () => {}
  }

  if (!set.geo.attributes.aInst) {
    const inst = new Float32Array(TREE_TIERS.high * 4)
    const rot = new Float32Array(TREE_TIERS.high * 2)
    set.geo.setAttribute('aInst', new THREE.InstancedBufferAttribute(inst, 4))
    set.geo.setAttribute('aRot', new THREE.InstancedBufferAttribute(rot, 2))
  }

  const instAttr = set.geo.attributes.aInst as THREE.InstancedBufferAttribute
  const rotAttr = set.geo.attributes.aRot as THREE.InstancedBufferAttribute
  const inst = instAttr.array as Float32Array
  const rot = rotAttr.array as Float32Array

  const rnd = mulberry32(4242)
  let placed = set.count
  let guard = 0
  const guardMax = TREE_TIERS.high * 30
  const CHUNK_SIZE = 600

  // 恢复之前采样的随机状态（若增量采样）
  for (let i = 0; i < placed; i++) {
    // 快速步进 rnd 保持与全量采样确定性一致
    rnd(); rnd(); rnd(); rnd(); rnd()
  }

  function step() {
    if (cancelled) return
    const chunkTarget = Math.min(placed + CHUNK_SIZE, budget)
    while (placed < chunkTarget && guard < guardMax) {
      guard++
      const x = (rnd() * 2 - 1) * TREE_SPAN_M
      const z = (rnd() * 2 - 1) * TREE_SPAN_M
      const r1 = rnd()
      const s = treeAccept(x, z, r1)
      if (s <= 0) continue
      inst[placed * 4] = x
      inst[placed * 4 + 1] = terrainSurfaceY(x, z) - 0.22 // 根部微埋防悬空
      inst[placed * 4 + 2] = z
      inst[placed * 4 + 3] = s
      rot[placed * 2] = rnd() * Math.PI * 2
      rot[placed * 2 + 1] = rnd()
      placed++
    }
    set.count = placed
    set.geo.instanceCount = placed
    instAttr.needsUpdate = true
    rotAttr.needsUpdate = true

    if (placed < budget && guard < guardMax) {
      if (typeof window !== 'undefined' && 'requestAnimationFrame' in window) {
        window.requestAnimationFrame(step)
      } else {
        setTimeout(step, 0)
      }
    }
  }

  step()
  return () => { cancelled = true }
}

export default function TreeField() {
  const quality = useSim((s) => s.quality)
  const set = useMemo(() => createSet(), [])
  const meshRef = useRef<THREE.Mesh>(null)

  // 首帧之后分帧渐进落位（消除 CPU 尖峰，平滑扩展至当前档位预算）
  useEffect(() => {
    const target = TREE_TIERS[quality]
    if (set.count >= target) {
      set.geo.instanceCount = target
      return
    }
    const cancel = fillPlacementsChunked(set, target)
    return cancel
  }, [set, quality])

  // 画质档 → 实例数（运行时只调 instanceCount，不重建几何/程序）
  const target = TREE_TIERS[quality]
  set.geo.instanceCount = Math.min(set.count, target)

  useFrame((state) => {
    const u = set.mat.uniforms as Record<string, { value: unknown }>
    ;(u.uTime as { value: number }).value = phaseT(state.clock.elapsedTime)
    ;(u.uDayF as { value: number }).value = skyState.dayF
    ;(u.uSunDir as { value: THREE.Vector3 }).value.copy(skyState.sunDir)
    ;(u.uMoonDir as { value: THREE.Vector3 }).value.copy(skyState.moonDir)
    ;(u.uWarmF as { value: number }).value = skyState.warmF
    const { fromDeg } = windAt(useSim.getState().tHours)
    const th = (fromDeg * Math.PI) / 180
    ;(u.uWind as { value: THREE.Vector2 }).value.set(Math.sin(th), Math.cos(th))
    const fog = state.scene.fog
    if (fog && (fog as THREE.FogExp2).isFogExp2) {
      ;(u.uFogColor as { value: THREE.Color }).value.copy((fog as THREE.FogExp2).color)
      ;(u.uFogDensity as { value: number }).value = (fog as THREE.FogExp2).density
    }
  })

  if (target <= 0) return null
  return <mesh ref={meshRef} geometry={set.geo} material={set.mat} frustumCulled={false} />
}
