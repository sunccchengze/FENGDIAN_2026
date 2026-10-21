/* oxlint-disable react/immutability -- 帧循环内 mutate uniforms/instance attributes 为 R3F 标准模式（docs/08 D2） */
import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { skyState } from './lightState'
import { windAt } from '../data/farmSim'
import { useSim } from '../state/simStore'
import { cameraPos } from './cameraBus'
import {
  GRASS_TILE_CAP, GRASS_TILE_M, bladesPerTile, buildTileBlades, clumpPlane, drawnFrac,
  grassLandStats, planeCurvature, planeY, tileFromIndex, tilesInView, PLANE_ROUGH_THRESH,
  type Blade,
} from './grassTile'
import { landMask, biomeWeights, terrainSurfaceY, mulberry32 } from './terrainUtil'
import { phaseT } from './freeze.ts'

// ============================================================
// P1 · T8 草地系统（R40 正式挂载版：相机跟随分块 + 视距裁决）
// ------------------------------------------------------------
// 挂账历史：grassField 自 R32 起写好但连续 7 轮未挂载 —— 直接全场激活的代价是
// 6 万 blade × 8 顶点 = 48 万顶点常驻 + frustumCulled=false（内陆草在海上特写
// 时也算），构建期还有一次性拒绝采样长尖峰（与 treeField 旧病同源）。
//
// 本版两条裁决（模型见 ./grassTile.ts，纯函数可回归）：
//   ① 【空间分块 + 池化】512m 瓦片，只对相机视距环内的瓦片建数据/上屏；
//      瓦片进出视距即回收槽位（几何与着色器程序不重建，只换实例属性）；
//      池上限 high 24 / medium 14 → draw call 增量有界（≤24），
//      上屏株数实测 ~1.2 万（陆侧机位）/ ~3.8 千（场心海上）；
//   ② 【构建期分帧摊销】每帧落株预算 4000（high）/2500（medium），
//      瓦片建成后 0.7s 淡入（uFade）—— 不再出现首帧后 2.5~5.1s 长尖峰。
//
// 视觉口径（全部沿用 R32 原实现，不回退）：
//   · blade = 两块交叉竖面，顶点正弦风摆（相位差攒动）+ 干湿分区染色；
//   · 光照只做「方向光漫反射近似 + 高度渐变 + 指数雾」，不吃 PBR、不吃阴影；
//   · 暗调莫兰迪（干黄 ↔ 湿绿），夜间压到星光量级 —— 不引入新色相；
//   · 只消费 terrainUtil 纯函数（biomeWeights/terrainSurfaceY），不反向影响
//     地形 mesh 与贴地基准（terrainSurfaceY 唯一真值红线不变）。
// ============================================================

/** 画质档 → 视距 / 槽位数 / 每帧落株预算 / 密度系数（low 档不画草，与树木层同口径） */
const TIERS = {
  // budget = 每帧落株预算（丛级贴地平面后 ≈0.3 次 terrainSurfaceY/株 → 1200 株 ≈ 5ms）
  high: { radius: 1600, slots: 24, budget: 900, density: 1.0 },
  medium: { radius: 1150, slots: 14, budget: 600, density: 0.55 },
  low: { radius: 0, slots: 0, budget: 0, density: 0 },
} as const

const CAP = GRASS_TILE_CAP
const FADE_TAU = 0.7 // 瓦片建成后的淡入时长（s）

// ---- 近场密草贴块（相机跟随）----
// 瓦片系统解决「中远景有草的肌理」，但近场（<40m）要读成草甸需要 ~1.5 株/m²，
// 全域铺不起。经典解法：一块跟随相机的密草盘（双缓冲 + 交叉淡入淡出），
// 原点按 8m 网格量化重播种（重播种分帧摊销，旧块继续显示到新块就绪）。
const PATCH_CLUMPS = 700
const PATCH_BPC = 10
const PATCH_N = PATCH_CLUMPS * PATCH_BPC
const PATCH_R = 44
const PATCH_CELL = 8 // 原重量化网格（m）
const PATCH_RESEED_GAP = 0.3 // 两次重播种的最小间隔（s，防高速飞行抖动）
const PATCH_CHUNK = 90 // 每帧重建的丛数（90 丛 ≈ 270 次地形求值 ≈ 2.5ms）
const PATCH_MAX_ALT = 150 // 相机离地超过此高度不画贴块（高空看是噪点）

interface PatchPattern {
  /** 丛心局部偏移（盘内均匀分布） */
  cdx: Float32Array
  cdz: Float32Array
  /** 丛内单株：局部偏移 / 高矮抖动 / 相位 / 朝向（620×10×5） */
  b: Float32Array
}

function buildPatchPattern(): PatchPattern {
  const rnd = mulberry32(0x9e37)
  const cdx = new Float32Array(PATCH_CLUMPS)
  const cdz = new Float32Array(PATCH_CLUMPS)
  const b = new Float32Array(PATCH_N * 5)
  let placed = 0
  let guard = 0
  while (placed < PATCH_CLUMPS && guard < PATCH_CLUMPS * 6) {
    guard++
    // 均匀圆盘 r = R·sqrt(u)；边缘按 (r/R)² 概率抽稀 → 密度向外渐隐，
    // 盘边与瓦片草场自然衔接（硬圆边是贴块最容易被看穿的破绽）
    const rr = PATCH_R * Math.sqrt(rnd())
    if (rnd() < 0.7 * (rr / PATCH_R) ** 2) continue
    const th = rnd() * Math.PI * 2
    const c = placed
    cdx[c] = Math.cos(th) * rr
    cdz[c] = Math.sin(th) * rr
    for (let k = 0; k < PATCH_BPC; k++) {
      const gx = (rnd() + rnd() - 1) * 1.5
      const gz = (rnd() + rnd() - 1) * 1.5
      const o = (c * PATCH_BPC + k) * 5
      b[o] = gx
      b[o + 1] = gz
      b[o + 2] = 0.72 + rnd() * 0.55
      b[o + 3] = rnd() * Math.PI * 2
      b[o + 4] = rnd() * Math.PI
    }
    placed++
  }
  return { cdx, cdz, b }
}
/** 已分配瓦片的「保活半径」= 视距 × 1.18（滞环，防边界来回抖动重建） */
const KEEP_HYSTERESIS = 1.18

const VERT = /* glsl */ `
attribute vec3 aOffset;   // 世界落位（根部）
attribute vec3 aParam;    // x: 缩放 s, y: 相位, z: 朝向角
attribute float aKind;    // 0 草原 blade, 1 林下 blade
uniform float uTime;
uniform vec2 uWind;
uniform float uWindAmt;   // 风速调制摆幅（与 windAt 同源：风大浪大草也摆得凶）
varying float vShade;
varying float vKind;
varying float vFogDepth;
varying float vDry;

float hash21(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }

void main() {
  float s = aParam.x;
  float phase = aParam.y;
  float ang = aParam.z;
  float c = cos(ang), si = sin(ang);
  // 局部 blade：position.x ∈ [-0.5,0.5]（宽）, position.y ∈ [0,1]（高，基底已抬到 0）
  vec3 p = position;
  p.x *= (1.0 - uv.y * 0.88);          // 向上收窄成 blade
  p.x += uv.y * uv.y * 0.16;           // 自然弯弧（直板感是"纸片草"的第一来源）
  p = vec3(p.x * c, p.y, -p.x * si + p.z * c);
  // 风摆：顶部摆幅大、根部不动；相位差制造攒动
  float sway = sin(uTime * 1.35 + phase + dot(aOffset.xz, uWind) * 0.02);
  float sway2 = sin(uTime * 2.30 + phase * 1.7);
  float bendAmt = uv.y * uv.y * s * uWindAmt;
  p.x += (sway * 0.35 + sway2 * 0.08) * bendAmt;
  p.z += (sway * 0.22 - sway2 * 0.06) * bendAmt;
  vec3 world = aOffset + p * vec3(s * 0.22, s, s * 0.22); // 窄 blade：宽面片在近景会读成"灌木叶"

  // 干湿分区：世界坐标哈希（斑块）× 单株哈希（颗粒感）各半 —— 纯空间哈希会让
  // 整丛同色，近景读成"一坨一坨的色块"
  float dry = mix(hash21(floor(aOffset.xz * 0.05)), hash21(vec2(aParam.y * 7.31, aParam.z * 3.17)), 0.45);
  vDry = dry;
  vKind = aKind;
  // 高度渐变：根暗、梢亮；叠加摆动微光
  vShade = (0.45 + 0.55 * uv.y) * (0.92 + 0.08 * sway);
  vec4 mv = modelViewMatrix * vec4(world, 1.0);
  vFogDepth = -mv.z;
  gl_Position = projectionMatrix * mv;
}
`

const FRAG = /* glsl */ `
precision highp float;
varying float vShade;
varying float vKind;
varying float vFogDepth;
varying float vDry;
uniform float uDayF;
uniform vec3 uFogColor;
uniform float uFogDensity;
uniform float uFade;      // 瓦片淡入（分帧建成后 0→1，消除「一整片草突然蹦出来」）

void main() {
  // 干(黄) ↔ 湿(绿)；林下整体压暗偏黄
  // 莫兰迪低饱和（与地形 cGrass/cForest 同族）：干=灰橄榄、湿=灰绿，压住对比不抢地形
  vec3 dryCol = mix(vec3(0.225, 0.205, 0.105), vec3(0.165, 0.150, 0.075), vKind);
  vec3 wetCol = mix(vec3(0.085, 0.185, 0.085), vec3(0.065, 0.130, 0.070), vKind);
  vec3 col = mix(wetCol, dryCol, smoothstep(0.42, 0.88, vDry)); // 偏湿绿：干黄只作点缀
  col *= vShade * 0.92;
  // 昼夜：只保留方向光漫反射近似的明暗比例
  col *= mix(vec3(0.16, 0.18, 0.24), vec3(1.0), uDayF);
  // 指数雾（与场景雾同式）
  float fogF = 1.0 - exp(-uFogDensity * uFogDensity * vFogDepth * vFogDepth);
  col = mix(col, uFogColor, clamp(fogF, 0.0, 1.0));
  gl_FragColor = vec4(col, uFade);
}
`

// ---- blade 基底几何（两块交叉竖面，1×1，基底 y=0）：全部槽位共享一份 ----
function buildBladeBase(): THREE.BufferGeometry {
  const p1 = new THREE.PlaneGeometry(1, 1)
  p1.translate(0, 0.5, 0)
  const p2 = new THREE.PlaneGeometry(1, 1)
  p2.rotateY(Math.PI / 2)
  p2.translate(0, 0.5, 0)
  const posArr: number[] = []
  const uvArr: number[] = []
  const idxArr: number[] = []
  let vi = 0
  for (const p of [p1, p2]) {
    const pp = p.attributes.position as THREE.BufferAttribute
    const uu = p.attributes.uv as THREE.BufferAttribute
    const ii = p.index as THREE.BufferAttribute
    for (let i = 0; i < pp.count; i++) {
      posArr.push(pp.getX(i), pp.getY(i), pp.getZ(i))
      uvArr.push(uu.getX(i), uu.getY(i))
    }
    for (let i = 0; i < ii.count; i++) idxArr.push(ii.getX(i) + vi)
    vi += pp.count
  }
  p1.dispose()
  p2.dispose()
  const base = new THREE.BufferGeometry()
  base.setAttribute('position', new THREE.Float32BufferAttribute(posArr, 3))
  base.setAttribute('uv', new THREE.Float32BufferAttribute(uvArr, 2))
  base.setIndex(idxArr)
  return base
}

interface Slot {
  geo: THREE.InstancedBufferGeometry
  mat: THREE.ShaderMaterial
  off: THREE.InstancedBufferAttribute
  par: THREE.InstancedBufferAttribute
  kind: THREE.InstancedBufferAttribute
  offArr: Float32Array
  parArr: Float32Array
  kindArr: Float32Array
  /** 当前占用的瓦片（-1 = 空闲） */
  ti: number
  /** 已落株数 */
  progress: number
  /** 瓦片目标株数 */
  target: number
  /** 淡入 0..1 */
  fade: number
  /** 该瓦片的全量株表（分配时一次构建，之后按预算增量拷进属性） */
  blades: Blade[]
  mesh: THREE.Mesh
}

interface TileRec {
  ti: number
  slot: number
  progress: number
  target: number
}

export default function GrassField() {
  const quality = useSim((s) => s.quality)

  const rig = useMemo(() => {
    const base = buildBladeBase()
    // 共享 uniform 对象：所有槽位材质引用同一批 { value } —— 每帧只写一次
    const shared = {
      uTime: { value: 0 },
      uWind: { value: new THREE.Vector2(0, 1) },
      uWindAmt: { value: 1 },
      uDayF: { value: 1 },
      uFogColor: { value: new THREE.Color('#040911') },
      uFogDensity: { value: 0.00013 },
      uFade: { value: 0 },
    }
    const slots: Slot[] = []
    for (let i = 0; i < TIERS.high.slots; i++) {
      const geo = new THREE.InstancedBufferGeometry()
      geo.attributes.position = base.attributes.position
      geo.attributes.uv = base.attributes.uv
      geo.setIndex(base.getIndex())
      geo.instanceCount = 0
      const offArr = new Float32Array(CAP * 3)
      const parArr = new Float32Array(CAP * 3)
      const kindArr = new Float32Array(CAP)
      const off = new THREE.InstancedBufferAttribute(offArr, 3)
      const par = new THREE.InstancedBufferAttribute(parArr, 3)
      const kind = new THREE.InstancedBufferAttribute(kindArr, 1)
      off.setUsage(THREE.DynamicDrawUsage)
      par.setUsage(THREE.DynamicDrawUsage)
      kind.setUsage(THREE.DynamicDrawUsage)
      geo.setAttribute('aOffset', off)
      geo.setAttribute('aParam', par)
      geo.setAttribute('aKind', kind)
      const mat = new THREE.ShaderMaterial({
        vertexShader: VERT,
        fragmentShader: FRAG,
        uniforms: { ...shared, uFade: { value: 0 } }, // uFade 逐槽位，其余共享引用
        side: THREE.DoubleSide,
        transparent: true,
      })
      mat.customProgramCacheKey = () => 'grass-blade-v2-tiled'
      const mesh = new THREE.Mesh(geo, mat)
      // 包围球按瓦片对角 + 株高给足（不逐帧重算，池化槽位复用）
      geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), GRASS_TILE_M * 0.75 + 4)
      mesh.frustumCulled = false
      mesh.renderOrder = 1
      slots.push({
        geo, mat, off, par, kind, offArr, parArr, kindArr,
        ti: -1, progress: 0, target: 0, fade: 0, blades: [], mesh,
      })
    }
    // 近场贴块：两套缓冲（双缓冲交叉淡化），共享 base 几何与 shared uniforms
    const pattern = buildPatchPattern()
    const patches = [0, 1].map(() => {
      const geo = new THREE.InstancedBufferGeometry()
      geo.attributes.position = base.attributes.position
      geo.attributes.uv = base.attributes.uv
      geo.setIndex(base.getIndex())
      geo.instanceCount = 0
      const offArr = new Float32Array(PATCH_N * 3)
      const parArr = new Float32Array(PATCH_N * 3)
      const kindArr = new Float32Array(PATCH_N)
      const off = new THREE.InstancedBufferAttribute(offArr, 3)
      const par = new THREE.InstancedBufferAttribute(parArr, 3)
      const kind = new THREE.InstancedBufferAttribute(kindArr, 1)
      off.setUsage(THREE.DynamicDrawUsage)
      par.setUsage(THREE.DynamicDrawUsage)
      kind.setUsage(THREE.DynamicDrawUsage)
      geo.setAttribute('aOffset', off)
      geo.setAttribute('aParam', par)
      geo.setAttribute('aKind', kind)
      geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 6, 0), PATCH_R + 6)
      const mat = new THREE.ShaderMaterial({
        vertexShader: VERT,
        fragmentShader: FRAG,
        uniforms: { ...shared, uFade: { value: 0 } },
        side: THREE.DoubleSide,
        transparent: true,
      })
      mat.customProgramCacheKey = () => 'grass-blade-v2-tiled'
      const mesh = new THREE.Mesh(geo, mat)
      mesh.renderOrder = 2
      return {
        geo, mat, mesh, off, par, kind, offArr, parArr, kindArr,
        originX: NaN, originZ: NaN, progress: 0, placed: 0, fade: 0, active: false,
      }
    })
    return {
      base, shared, slots, tiles: new Map<number, TileRec>(), view: [] as number[],
      pattern, patches, patchActive: 0, patchBuild: -1, patchLastReseed: 0,
    }
  }, [])

  // 构建期权重表（324 瓦片 × 16 子格 ≈ 38ms）在 splash 之后的空闲帧里预热，
  // 不进首帧、也不进开场巡航的关键帧。
  useEffect(() => {
    let cancelled = false
    const warm = () => {
      if (cancelled) return
      grassLandStats()
    }
    if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      ;(window as unknown as { requestIdleCallback: (cb: () => void, o?: { timeout: number }) => number })
        .requestIdleCallback(warm, { timeout: 1500 })
    } else {
      setTimeout(warm, 400)
    }
    return () => { cancelled = true }
  }, [])

  // low 档：整层不画（与 treeField 的 low 档同口径；此时也不占任何构建预算）
  const tier = TIERS[quality]
  const groupRef = useRef<THREE.Group>(null)

  useFrame((state, delta) => {
    const dt = Math.min(0.1, Math.max(0.001, delta))
    // —— 共享 uniform：时间 / 风 / 昼夜 / 雾 ——
    const sh = rig.shared
    sh.uTime.value = phaseT(state.clock.elapsedTime)
    sh.uDayF.value = skyState.dayF
    const w = windAt(useSim.getState().tHours)
    const th = (w.fromDeg * Math.PI) / 180
    sh.uWind.value.set(Math.sin(th), Math.cos(th))
    sh.uWindAmt.value = 0.55 + 0.075 * w.u // 5.4 m/s → 0.96；13.2 m/s → 1.54
    const fog = state.scene.fog
    if (fog && (fog as THREE.FogExp2).isFogExp2) {
      sh.uFogColor.value.copy((fog as THREE.FogExp2).color)
      sh.uFogDensity.value = (fog as THREE.FogExp2).density
    }

    const slots = rig.slots
    const nSlots = tier.slots
    if (nSlots <= 0) {
      for (const s of slots) {
        s.geo.instanceCount = 0
        s.mesh.visible = false
        if (s.ti !== -1) { s.ti = -1; s.progress = 0; s.target = 0 }
      }
      rig.tiles.clear()
      for (const pb of rig.patches) {
        pb.fade = 0
        pb.mesh.visible = false
        pb.active = false
      }
      rig.patchBuild = -1
      return
    }

    // —— ① 视距裁决：相机环内瓦片（含滞环保活，防边界抖动）——
    const cam = cameraPos()
    tilesInView(cam.x, cam.z, tier.radius, rig.view)
    const view = rig.view
    const keepR = tier.radius * KEEP_HYSTERESIS

    // 回收：出保活半径的瓦片释放槽位
    for (const [ti, rec] of rig.tiles) {
      const t = tileFromIndex(ti)
      const dx = Math.max(Math.abs(cam.x - t.cx) - GRASS_TILE_M / 2, 0)
      const dz = Math.max(Math.abs(cam.z - t.cz) - GRASS_TILE_M / 2, 0)
      if (Math.hypot(dx, dz) > keepR) {
        const sl = slots[rec.slot]
        if (sl) { sl.ti = -1; sl.progress = 0; sl.target = 0; sl.fade = 0; sl.geo.instanceCount = 0; sl.mesh.visible = false }
        rig.tiles.delete(ti)
      }
    }

    // 分配：按距离升序占槽（已占的保住，空闲槽给新瓦片）
    for (let i = 0; i < view.length; i++) {
      if (rig.tiles.size >= nSlots) break
      const ti = view[i]
      if (rig.tiles.has(ti)) continue
      let free = -1
      for (let k = 0; k < nSlots; k++) if (slots[k].ti === -1) { free = k; break }
      if (free < 0) break
      const target = Math.min(CAP, Math.round(bladesPerTile(ti) * tier.density))
      if (target <= 0) continue
      const sl = slots[free]
      // 全量株表一次构建（同瓦片重复求值 = O(n²) 浪费）：之后每帧只按预算拷进属性
      sl.blades = buildTileBlades(ti, target)
      sl.ti = ti
      sl.progress = 0
      sl.target = Math.min(target, sl.blades.length)
      sl.fade = 0
      sl.geo.instanceCount = 0
      sl.mesh.visible = false
      rig.tiles.set(ti, { ti, slot: free, progress: 0, target: sl.target })
    }

    // —— ② 分帧落株（每帧预算 → 不再有构建期长尖峰）——
    let budget = tier.budget
    for (let k = 0; k < nSlots && budget > 0; k++) {
      const sl = slots[k]
      if (sl.ti < 0 || sl.progress >= sl.target) continue
      const n = Math.min(sl.target, sl.progress + budget)
      for (let b = sl.progress; b < n; b++) {
        const bl = sl.blades[b]
        sl.offArr[b * 3] = bl.x
        sl.offArr[b * 3 + 1] = bl.y
        sl.offArr[b * 3 + 2] = bl.z
        sl.parArr[b * 3] = bl.s
        sl.parArr[b * 3 + 1] = bl.phase
        sl.parArr[b * 3 + 2] = bl.ang
        sl.kindArr[b] = bl.kind
      }
      budget -= n - sl.progress
      sl.progress = n
      sl.off.needsUpdate = true
      sl.par.needsUpdate = true
      sl.kind.needsUpdate = true
      const rec = rig.tiles.get(sl.ti)
      if (rec) rec.progress = n
      if (sl.progress >= sl.target) {
        sl.geo.instanceCount = sl.progress
        sl.mesh.visible = true
        sl.blades = [] // 拷完即释放引用（数组留在 GC 里没意义）
      }
    }

    // —— ③ 淡入 + 视距密度截断（instanceCount 截断，不重建数据）——
    for (let k = 0; k < nSlots; k++) {
      const sl = slots[k]
      if (sl.ti < 0 || sl.progress < sl.target) continue
      sl.fade = Math.min(1, sl.fade + dt / FADE_TAU)
      ;(sl.mat.uniforms.uFade as { value: number }).value = sl.fade
      const t = tileFromIndex(sl.ti)
      const ddx = Math.max(Math.abs(cam.x - t.cx) - GRASS_TILE_M / 2, 0)
      const ddz = Math.max(Math.abs(cam.z - t.cz) - GRASS_TILE_M / 2, 0)
      const drawn = Math.round(sl.progress * drawnFrac(Math.hypot(ddx, ddz)) * tier.density)
      sl.geo.instanceCount = Math.max(0, Math.min(sl.progress, drawn))
      sl.mesh.visible = sl.fade > 0.02 && sl.geo.instanceCount > 0
    }

    // —— ④ 近场密草贴块（相机跟随，双缓冲）——
    const pat = rig.pattern
    const patches = rig.patches
    const now = phaseT(state.clock.elapsedTime)
    const groundY = terrainSurfaceY(cam.x, cam.z)
    const onLand = landMask(cam.x, cam.z) >= 0.1
    const altOk = cam.y - groundY < PATCH_MAX_ALT
    const wantPatch = onLand && altOk
    const ox = Math.round(cam.x / PATCH_CELL) * PATCH_CELL
    const oz = Math.round(cam.z / PATCH_CELL) * PATCH_CELL

    // 触发重播种：原点换格 / 之前没建过，且距上次起建 > PATCH_RESEED_GAP
    const active = patches[rig.patchActive]
    const building = rig.patchBuild >= 0 ? patches[rig.patchBuild] : null
    const needReseed =
      wantPatch &&
      (!building || building.originX !== ox || building.originZ !== oz) &&
      (active.originX !== ox || active.originZ !== oz || active.fade <= 0) &&
      now - rig.patchLastReseed > PATCH_RESEED_GAP
    if (needReseed) {
      const idx = rig.patchActive === 0 ? 1 : 0
      const pb = patches[idx]
      pb.originX = ox
      pb.originZ = oz
      pb.progress = 0
      pb.placed = 0
      pb.geo.instanceCount = 0
      rig.patchBuild = idx
      rig.patchLastReseed = now
    }

    // 分帧重建（每帧 PATCH_CHUNK 丛）
    if (rig.patchBuild >= 0) {
      const pb = patches[rig.patchBuild]
      const c0 = pb.progress
      const c1 = Math.min(PATCH_CLUMPS, c0 + PATCH_CHUNK)
      for (let c = c0; c < c1; c++) {
        const wx = pb.originX + pat.cdx[c]
        const wz = pb.originZ + pat.cdz[c]
        const L = landMask(wx, wz)
        if (L < 0.08) continue // 滩涂/岩面/水洼：留裸地（草甸本就有斑块）
        const w = biomeWeights(wx, wz)
        const forestish = w.forest > w.grass * 0.9
        // 丛级贴地平面（5 次真值求值/丛，与瓦片同口径）；折痕丛逐株真值
        const plane = clumpPlane(wx, wz)
        const rough = planeCurvature(plane) > PLANE_ROUGH_THRESH
        const clumpScale = 0.85 + ((c * 2654435761) % 1000) / 1000 * 0.4
        for (let k = 0; k < PATCH_BPC; k++) {
          const o = (c * PATCH_BPC + k) * 5
          const gx = pat.b[o]
          const gz = pat.b[o + 1]
          const i3 = pb.placed * 3
          // 局部坐标（mesh 原点在贴块原点）：丛心偏移 + 丛内散布
          pb.offArr[i3] = pat.cdx[c] + gx
          pb.offArr[i3 + 1] = (rough ? terrainSurfaceY(pb.originX + pat.cdx[c] + gx, pb.originZ + pat.cdz[c] + gz) : planeY(plane, gx, gz)) - 0.15
          pb.offArr[i3 + 2] = pat.cdz[c] + gz
          const sj = pat.b[o + 2] * clumpScale
          pb.parArr[i3] = (forestish ? 0.62 : 0.95) * sj
          pb.parArr[i3 + 1] = pat.b[o + 3]
          pb.parArr[i3 + 2] = pat.b[o + 4]
          pb.kindArr[pb.placed] = forestish ? 1 : 0
          pb.placed++
        }
      }
      pb.progress = c1
      pb.off.needsUpdate = true
      pb.par.needsUpdate = true
      pb.kind.needsUpdate = true
      if (c1 >= PATCH_CLUMPS) {
        pb.geo.instanceCount = pb.placed
        pb.active = true
        rig.patchActive = rig.patchBuild
        rig.patchBuild = -1
      }
    }

    // 贴块位姿 + 交叉淡化
    for (let i = 0; i < 2; i++) {
      const pb = patches[i]
      const isActive = i === rig.patchActive && pb.active
      const target = isActive && wantPatch ? 1 : 0
      pb.fade += (target - pb.fade) * Math.min(1, dt / 0.22)
      if (pb.fade < 0.02 && target === 0) {
        pb.mesh.visible = false
        continue
      }
      ;(pb.mat.uniforms.uFade as { value: number }).value = pb.fade
      pb.mesh.position.set(pb.originX, 0, pb.originZ)
      pb.mesh.visible = pb.geo.instanceCount > 0
    }
  })

  return (
    <group ref={groupRef}>
      {rig.slots.map((s, i) => (
        <primitive key={`t${i}`} object={s.mesh} />
      ))}
      {rig.patches.map((p, i) => (
        <primitive key={`p${i}`} object={p.mesh} />
      ))}
    </group>
  )
}
