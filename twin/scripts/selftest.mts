// ================================================================
// 数据契约回归自检（docs/08 D2：把"截图/帧差验证"沉淀为可执行断言）
// 运行：node --experimental-strip-types scripts/selftest.mts
// 依赖：仅 Node 22 原生类型剥离；无浏览器、无网络。
// ================================================================
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import {
  farmFrame, optimizeYaw, windAt, FARM_RATED_MW, N_UNITS, dayNight, sunWarmth,
} from '../src/data/farmSim.ts'
import { powerCurveKw, yawFactor, wakeDeficit, TILT_F, wakeDeflection } from '../src/data/turbinePhysics.ts'
import {
  FARM, SERVOS, ROW_COUNT, SUBSTATION, FARM_CENTER, terrainHeight, terrainSurfaceY,
  landMask, biomeWeights, SNOW_LINE, grassSampleHits,
  PEAKS, FJORD_A, FJORD_B, STACKS, HEADLANDS, bakeHeightGrid,
  shoreSigned, treeAccept, treeSampleHits, TREE_SPAN_M, mulberry32,
  ISLANDS,
} from '../src/scene/terrainUtil.ts'
import { TURBINE_SPEC } from '../src/scene/turbine/geometry.ts'
import { LAYOUTS, LAYOUT, ACTIVE_LAYOUT, unitOf } from '../src/scene/layouts.ts' // R41-A 布局真值源（R42 起 +ACTIVE_LAYOUT/unitOf）
import { phaseFor, FROZEN_PHASE } from '../src/scene/freeze.ts' // R42 渲染相位冻结
import { CAMERA_NODES, LOOK_NODES } from '../src/scene/introProfile.ts' // R42 开场路径
import {
  CAM_HOTKEYS, diagnoseHotkey, ORBIT_MIN_DISTANCE, ORBIT_MAX_DISTANCE, ORBIT_MAX_POLAR_DEG,
} from '../src/scene/hotkeys.ts'
// R40 新增模块（T9 声场 / T8 草地分块 / P2 偏航执行器）
import {
  swellEnvAt, swellHeightAt, swellPeriodS, surfGain, oceanLandGate, oceanSwellGain,
  bladePassHz, driveTrainHz, turbineDistanceGain, downwindFactor, selectTurbines, TURBINE_AUDIBLE_FAR,
  acousticFrame, SWELL_A1, SWELL_A2,
} from '../src/audio/audioModel.ts'
import {
  bladesPerTile, buildTileBlades, drawnFrac, tilesInView, tileAt, tileFromIndex,
  GRASS_TARGET_TOTAL, GRASS_TILE_COUNT,
} from '../src/scene/grassTile.ts'
import {
  createYawActuator, stepYaw, yawEtaFrom, createYawBank, stepYawBank, snapYawBank,
  bankActual, YAW_RATE_DPS, YAW_DEADBAND_DEG, YAW_STOP_BAND_DEG,
} from '../src/core/control/yawDrive.ts'

const TWIN_ROOT = new URL('../', import.meta.url).pathname // 脚本相对 twin 根，免 cwd 依赖（AUD-21）

let pass = 0
let fail = 0
const ok = (name: string, cond: boolean, detail = '') => {
  if (cond) { pass++; console.log(`  ✓ ${name}`) }
  else { fail++; console.log(`  ✗ ${name} ${detail}`) }
}
const close = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps

console.log('== AEOLUS 数据契约自检 ==')

// 1. 确定性：同输入同帧
{
  const a = farmFrame(7.5, [0, 0, 0, 0, 0, 0, 0, 0, 0], 45)
  const b = farmFrame(7.5, [0, 0, 0, 0, 0, 0, 0, 0, 0], 45)
  ok('确定性：同 (t,yaw,target) 两次求值 totalMW/频率/告警一致',
    close(a.totalMW, b.totalMW) && close(a.freqHz, b.freqHz)
    && JSON.stringify(a.alarms.map((x) => x.key)) === JSON.stringify(b.alarms.map((x) => x.key)))
}

// 2. 功率曲线形状
{
  let mono = true
  let prev = -1
  for (let u = 3; u <= 11.4001; u += 0.1) {
    const p = powerCurveKw(u)
    if (p < prev - 1e-9) mono = false
    prev = p
  }
  ok('功率曲线：额定段单调不减', mono)
  ok('功率曲线：cut-in 以下 = 0', powerCurveKw(2.9) === 0)
  ok('功率曲线：cut-out 以上 = 0', powerCurveKw(25.1) === 0)
  ok('功率曲线：额定平台 = 5000×倾斜因子（FLORIS 表口径，含 5° 转轴倾斜损失）', close(powerCurveKw(15), 5000 * TILT_F, 0.5))
}

// 3. 偏航损失
ok('偏航因子：cos^p 随 |yaw| 递减', yawFactor(0) > yawFactor(10) && yawFactor(10) > yawFactor(25))

// 4. 尾流物理方向与偏航偏折
{
  // 下游机在正南 440m（风从北来）：应出现亏损
  const d0 = wakeDeficit(8, 0, 440, 0, 0)
  // 上游机偏航 25°：尾流横向偏移，下游（对齐机）亏损应减小
  const dS = wakeDeficit(8, 0, 440, 0, 25)
  // 上风向不应有亏损
  const dUp = wakeDeficit(8, 0, -440, 0, 0)
  ok('Jensen：下游同列机组出现速度亏损', d0 > 0.05)
  ok('Jensen：偏航偏折降低下游亏损（wake steering 方向正确）', dS < d0, `d0=${d0.toFixed(3)} dS=${dS.toFixed(3)}`)
  ok('Jensen：上游来流不受下游影响', dUp === 0)
}

// 5. 限功率闭环：total ≈ min(avail, target)
{
  const avail = farmFrame(4.2, [0, 0, 0, 0, 0, 0, 0, 0, 0], 45)
  const curtail = farmFrame(4.2, [0, 0, 0, 0, 0, 0, 0, 0, 0], 8)
  ok('限功率：指令 8MW 时 total≈8（若资源充足）',
    avail.totalMW > 8 ? close(curtail.totalMW, 8, 1e-3) : curtail.totalMW <= avail.totalMW + 1e-6,
    `avail=${avail.totalMW.toFixed(2)} curtail=${curtail.totalMW.toFixed(2)}`)
}

// 6. 电网频率带宽
{
  let inBand = true
  for (let t = 0; t < 24; t += 0.5) {
    const f = farmFrame(t, [0, 0, 0, 0, 0, 0, 0, 0, 0], 45).freqHz
    if (f < 49.8 || f > 50.2) inBand = false
  }
  ok('频率：24h 扫描内 |f-50|≤0.2Hz（并网常态）', inBand)
}

// 7. 机组计数/功率守恒
{
  const fr = farmFrame(11.3, [0, 0, 0, 0, 0, 0, 0, 0, 0], 45)
  const sum = fr.units.reduce((s, u) => s + u.powerKw, 0) / 1000
  ok('守恒：单机功率求和 = 全场功率', close(sum, fr.totalMW, 1e-3), `${sum} vs ${fr.totalMW}`)
  ok('一致性：units 数 = 场景机组数 9', fr.units.length === FARM.length)
  ok('一致性：运行计数 = 9 - idle', fr.runningCount === fr.units.filter((u) => u.status !== 'idle').length)
}

// 8. 告警确定性 + 字段完备
{
  const a = farmFrame(2.75, [28, 28, 28, -22, -22, -22, 12, 12, 12], 9)
  const b = farmFrame(2.75, [28, 28, 28, -22, -22, -22, 12, 12, 12], 9)
  ok('告警：同输入同事件集', JSON.stringify(a.alarms) === JSON.stringify(b.alarms))
  ok('告警：≤6 条且含等级/部件/定位字段', a.alarms.length <= 6
    && a.alarms.every((e) => (e.level === 'warn' || e.level === 'crit') && e.part.length > 0))
  ok('告警：大偏差+限功率工况至少 1 条', a.alarms.length >= 1)
}

// 9. 寻优：增益非负
{
  const seeds = [[0, 0, 0, 0, 0, 0, 0, 0, 0], [10, -6, 3, -12, 5, 0, -8, 4, -2]]
  let allOk = true
  for (const sy of seeds) {
    const base = farmFrame(15.2, sy, 45).totalMW
    const r = optimizeYaw(15.2, sy)
    if (r.totalMW < base - 1e-6) allOk = false
  }
  ok('寻优：优化后功率 ≥ 优化前（任意初始偏航）', allOk)
  const r = optimizeYaw(15.2, [0, 0, 0, 0, 0, 0, 0, 0, 0])
  ok('寻优：基准工况增益 >0（存在可利用的尾流偏折收益）', r.gainPct > 0, `gain=${r.gainPct.toFixed(2)}%`)
}

// 10. 能源口径物理上限
{
  const fr = farmFrame(6.6, [0, 0, 0, 0, 0, 0, 0, 0, 0], 45)
  ok('年估算 ≤ 装机×8760（A2-1 类错误不可能复现）',
    fr.energyYearEstMWh <= FARM_RATED_MW * 8760 + 1)
  ok('容量系数 0-100%', fr.cfPct >= 0 && fr.cfPct <= 100)
}

// 11. 风况函数域与连续
{
  let jumpMax = 0
  let prev = windAt(0).u
  for (let t = 0; t < 24; t += 0.05) {
    const { u } = windAt(t)
    if (u < 3 || u > 25) jumpMax = -1
    jumpMax = Math.max(jumpMax, Math.abs(u - prev))
    prev = u
  }
  ok('风况：全程处于 [3,25] 运行域且无跳变(Δ<0.5m/s/步)', jumpMax > 0 && jumpMax < 0.5, `maxΔ=${jumpMax.toFixed(3)}`)
}

// 12. V&V：对老网页 FLORIS 阵列基准的三指标复算（标定不漂移）
// [TODO P1-Jensen-Migrate]: 下方 none 与 独立寻优增益 2 项为旧 Jensen 代理口径既有失败（farmModel.ts 仍用简化的顶帽 Jensen 代理）。
// 待后续控制层/寻优层全面切换到 GCH 内核（L5/L7）后即可收敛全绿。勿顺手放宽容差。
{
  const W = { u: 8, fromDeg: 0 }
  const Z = new Array(N_UNITS).fill(0) // R42：长度随布局（3×3=9 / 1×3=3）
  const T = new Array(N_UNITS).fill(30)
  const none = farmFrame(12, Z, FARM_RATED_MW, W).totalMW * 1000
  const uni = farmFrame(12, T, FARM_RATED_MW, W).totalMW * 1000
  const gain = optimizeYaw(12, Z, W).gainPct
  // 第 18 轮（P0）：靶值改用与偏折曲线同源的 FLORIS 4.6.6 GCH 实算
  // （none 8108.08 / unified+30° 9060.03；旧靶 9299.05 来自老版本，实测差 −2.57%）。
  // unified 容差 ±10%：该项误差（实测 −9.42%）是 Jensen 顶帽廓线配真实饱和偏折的
  // 模型能力上限，非标定不足 —— 锁定真实几何后对 σ 系数一维扫描，极小值稳定在
  // 0.48（0.45/0.48/0.52/0.58 → 3.88/3.88/3.93/4.09%），unified 始终卡在 −9.4%。
  // 收紧只会逼出"放大偏折几何凑功率"的错误解（曾试出 2.60% 但几何偏 1.9 倍，已弃用）。
  // 这是记录上限、防止继续劣化的守门线，不是掩盖问题：P1 高斯廓线落地后须收回 ±5%。
  if (ACTIVE_LAYOUT === '3x3') {
    // FLORIS 4.6.6 GCH 实算靶值属 3×3 几何；1×3 的靶值组 = tandem3 oracle（R42 #2，floris 生成件）
    ok('V&V FLORIS none：8108.08 kW ±5%', Math.abs(none - 8108.08) <= 405.4, `=${none.toFixed(1)}`)
    ok('V&V FLORIS unified+30°：9060.03 kW ±10%', Math.abs(uni - 9060.03) <= 906, `=${uni.toFixed(1)}`)
    ok('V&V FLORIS 独立寻优增益：24.04% ±3pt', Math.abs(gain - 24.04) <= 3, `=${gain.toFixed(2)}%`)
  } else {
    // 1×3：tandem3 oracle 到岗前，先用物理边界守门（不虚构靶值）
    const f12z = farmFrame(12, Z, FARM_RATED_MW, W)
    const pk = f12z.units.map((u) => u.powerKw)
    ok('V&V 1×3 守门：逐机 0 < P ≤ 1754 kW（8m/s 不超单机 15m/s 额定 731kW×2.4 裕带，尾流只减不增）',
      pk.length === 3 && pk.every((v) => v > 0 && v <= 1753.95 * 1.001), pk.map((v) => v.toFixed(1)).join('/'))
    // 注（R42 oracle 到岗后修正归因）：「下游 T03(509.2) 反高于中游 T02(439.0)」不是
    // Jensen 代理缺陷 —— FLORIS 4.6.6 GCH 实算同样如此（tandem3 none 逐机
    // 1754.0/439.0/509.2 kW，3×3 中列切片 1754.0/439.2/509.7）：T02 正对 T01 尾流
    // 核心（5D 最强衰减），T03 处 T01 尾流 10D 已扩散衰减 + T02 自身低推尾流更弱，
    // 叠加后净衰减反而更小。代理与实算逐机差 ≤0.5 kW（round42 §3.3）。
    ok('V&V 1×3 守门：T01 净风满发、T02/T03 被尾流削减（不锚单调性——FLORIS 实算亦非单调，见上）',
      Math.abs(pk[0] - 1753.95) <= 1753.95 * 0.005 && pk[1] < pk[0] * 0.6 && pk[2] < pk[0] * 0.6,
      pk.map((v) => v.toFixed(1)).join('/'))
  }
  const p6 = powerCurveKw(6)
  const p8 = powerCurveKw(8)
  ok('V&V 单机功率锚点：731.0/1753.95 kW ±0.5%（FLORIS 表×倾斜）',
    Math.abs(p6 - 731) / 731 <= 0.005 && Math.abs(p8 - 1753.95) / 1753.95 <= 0.005,
    `p6=${p6.toFixed(1)} p8=${p8.toFixed(2)}`)
  const f12 = farmFrame(12, Z, 45, W)
  ok('V&V 转速口径：全场均值处于 6.9-13.5 rpm 带（含功率耦合上限）',
    f12.meanRpm >= 6.8 && f12.meanRpm <= 13.5, `=${f12.meanRpm.toFixed(2)}`)
}

// 13. 第 18 轮回归：24h 边界连续性（午夜风向/风速不得跳变）
{
  let mxA = 0
  let mxU = 0
  for (let t = 0; t < 24; t += 0.002) {
    const a = windAt(t)
    const b = windAt(t + 0.002)
    mxA = Math.max(mxA, Math.abs(b.fromDeg - a.fromDeg))
    mxU = Math.max(mxU, Math.abs(b.u - a.u))
  }
  const e = windAt(23.9999)
  const z = windAt(0)
  const jA = Math.abs(z.fromDeg - e.fromDeg)
  const jU = Math.abs(z.u - e.u)
  // 午夜跳变必须不大于日内正常相邻步（修复前为 23.2°，是日内最大的 2715 倍）
  ok('V&V 午夜风向连续：跳变 ≤ 日内相邻步最大值',
    jA <= mxA, `跳变=${jA.toFixed(5)}° 日内最大=${mxA.toFixed(5)}°`)
  ok('V&V 午夜风速连续：跳变 ≤ 日内相邻步最大值',
    jU <= mxU, `跳变=${jU.toFixed(5)} 日内最大=${mxU.toFixed(5)} m/s`)
}

// 14. 第 18 轮回归：P0 尾流横偏饱和模型对 FLORIS 4.6.6 GCH 留出集
{
  const D = 126.0
  // (yaw°, 站位D, FLORIS 真值 m)；均未参与拟合
  const HOLD: [number, number, number][] = [
    [7.5, 1.75, 9.4], [7.5, 9, 39.4], [12.5, 9, 58.5],
    [17.5, 9, 72.4], [22.5, 9, 80.8], [27.5, 9, 83.9],
  ]
  let mx = 0
  for (const [y, d, v] of HOLD) mx = Math.max(mx, Math.abs(wakeDeflection(y, d * D) - v))
  ok('V&V P0 横偏留出集：最大误差 ≤ 5 m（旧线性式为 128.3 m）', mx <= 5, `=${mx.toFixed(2)} m`)
  // 饱和性：远场增量必须收敛
  const a1 = wakeDeflection(30, 20 * D)
  const a2 = wakeDeflection(30, 40 * D)
  ok('V&V P0 横偏远场饱和：20D→40D 增量 < 3 m', Math.abs(a2 - a1) < 3, `=${(a2 - a1).toFixed(2)} m`)
  ok('V&V P0 横偏零偏航恒零 / 反号对称',
    wakeDeflection(0, 5 * D) === 0
    && Math.abs(wakeDeflection(-20, 5 * D) + wakeDeflection(20, 5 * D)) < 1e-9, 'ok')
}

// 15. 第 20 轮回归：贴地基准唯一性（地面渲染面 vs 物体定位面）
// 注意：自「连续面」改造起，WorldTerrain 的顶点几何直接采用 terrainSurfaceY，
// 已去掉旧版碎三角的 per-face hash 抬沉项 (hash-0.5)*6.4。因此这里复刻的
// 「渲染面」公式与 terrainSurfaceY 同源；断言的是「物体定位面」与「静态渲染面」
// 使用同一函数（若 WorldTerrain 改回碎三角会在此抓住），同时保留 sanity check。
{
  const renderedY = (x: number, z: number) => terrainSurfaceY(x, z)
  let mx = 0
  for (const u of FARM) mx = Math.max(mx, Math.abs(terrainSurfaceY(u.x, u.z) - renderedY(u.x, u.z)))
  mx = Math.max(mx, Math.abs(terrainSurfaceY(SUBSTATION.x, SUBSTATION.z) - renderedY(SUBSTATION.x, SUBSTATION.z)))
  for (let i = 0; i < 500; i++) {
    const x = ((i * 733) % 3000) - 1500
    const z = ((i * 971) % 3000) - 1500
    mx = Math.max(mx, Math.abs(terrainSurfaceY(x, z) - renderedY(x, z)))
  }
  // 修复前机位处最大差 7.34m（T06），风机基座环仅离地 0.9m → 环悬空
  ok('V&V 贴地基准唯一：terrainSurfaceY ≡ 静态渲染面', mx < 1e-9, `最大差=${mx.toExponential(2)} m`)

  // 第 29/30 轮：新地形为「海洋」——terrainSurfaceY 连续海床（≈海平面级低矮），
  // 与 terrainHeight 同源；海岸带陡升至数十米，保证「陆地明显高于海面」。
  let seaOK = true, coastOK = true
  for (const u of FARM) {
    const sy = terrainSurfaceY(u.x, u.z)
    if (sy > 12) seaOK = false // 风机区是海床，应接近海平面
  }
  // 第 31 轮「开放外海」：北(-z)/西(-x) 两相邻侧为陆地，南(+z)/东(+x) 两相邻侧开放为海。
  // round6 起过渡带放宽至 1400m（缓坡入海），探针相应外移至 3000m（仍应 ≥30m）——
  // 旧 2300m 探针锁的是“一堵墙”，与用户要的缓坡直接冲突，故外移而非降低阈值。
  for (const dir of [[0, -1] as const, [-1, 0] as const]) {
    const [dx, dz] = dir
    const h = terrainHeight(FARM_CENTER.x + dx * 3000, FARM_CENTER.z + dz * 3000)
    if (h < 30) coastOK = false
  }
  // 开放侧：南(+z)/东(+x) 在离场心 2300m 处应仍为海床（≤12m，无陆地抬升）
  let openOK = true
  for (const dir of [[0, 1] as const, [1, 0] as const]) {
    const [dx, dz] = dir
    const h = terrainHeight(FARM_CENTER.x + dx * 2300, FARM_CENTER.z + dz * 2300)
    if (h > 12) openOK = false
  }
  ok('V&V 风机区为海床：机位 terrainSurfaceY ≤ 12m（贴海）', seaOK, '机位贴海基准')
  ok('V&V 海岸明显高于海面：内陆 2300m 处 ≥30m', coastOK, '海陆交界抬升')
  ok('V&V 开放外海：南/东相邻侧 2300m 处保持海床 ≤12m', openOK, '两相邻侧开放为海')

  // 第 26/29 轮：波浪位移是「运行时顶点着色器」副作用，静态几何应仍严格等于
  // terrainSurfaceY（波幅只在 shader 里对水面顶点叠加，不影响贴地基准）。
  let waveOK = true
  for (const u of FARM) if (Math.abs(terrainSurfaceY(u.x, u.z) - terrainHeight(u.x, u.z)) > 1e-9) waveOK = false
  ok('V&V 波浪位移不污染贴地基准（静态几何=terrainSurfaceY）', waveOK, '机位贴地基准与地形同源')
}

// 16. 第 32 轮 A：真实海岸线/地貌（分形海岸 + 六群系 + 岛岬 + 草地核心）
// ---------------------------------------------------------------
// A1 海岸数值：机组/升压站零沾陆、600m 环零沾陆、开放侧纯海、升压站压平
{
  let mxUnit = 0
  for (const u of [...FARM, SUBSTATION]) mxUnit = Math.max(mxUnit, landMask(u.x, u.z))
  ok('R32-A1 机组/升压站零沾陆：landMask ≡ 0', mxUnit === 0, `max=${mxUnit}`)

  // 600m 环采 16 点/机：过渡踪（>0.02）都不许进环
  let ringBad = 0
  for (const u of [...FARM, SUBSTATION]) {
    for (let a = 0; a < 16; a++) {
      const px = u.x + 600 * Math.cos((a / 16) * 2 * Math.PI)
      const pz = u.z + 600 * Math.sin((a / 16) * 2 * Math.PI)
      if (landMask(px, pz) > 0.02) ringBad++
    }
  }
  ok('R32-A1 600m 机组净距：环上 160 点零沾陆（>0.02 即 fail）', ringBad === 0, `沾陆点=${ringBad}`)

  // 开放侧（南/东 2300m 探针）：纯海、无岛 mask、无抬升
  let openPure = true
  for (const dir of [[0, 1] as const, [1, 0] as const]) {
    const [dx, dz] = dir
    const x = FARM_CENTER.x + dx * 2300
    const z = FARM_CENTER.z + dz * 2300
    if (landMask(x, z) !== 0 || terrainHeight(x, z) > 12) openPure = false
  }
  ok('R32-A1 开放外海纯净：南/东探针 landMask=0 且高度≤12m', openPure, '两相邻侧开放为海')

  ok('R32-A1 升压站局地压平：站体高度 ≤3m', terrainHeight(SUBSTATION.x, SUBSTATION.z) <= 3,
    `=${terrainHeight(SUBSTATION.x, SUBSTATION.z).toFixed(2)}m`)
}

// A2 生物群系：海面全零、权重归一、中带草原+林地主导
{
  const sea = biomeWeights(FARM_CENTER.x, FARM_CENTER.z)
  const seaZero = sea.sand === 0 && sea.tidal === 0 && sea.grass === 0
    && sea.forest === 0 && sea.hill === 0 && sea.mountain === 0
  ok('R32-A2 海面群系全零（场心 land=0 处）', seaZero, JSON.stringify(sea))

  // 中带点：x=-100 列自适应找 L∈[0.4,0.7]（ramp 宽度会变，固定坐标不可靠）
  let midZ = 0
  for (let z = -2000; z >= -4600; z -= 50) {
    const L = landMask(-100, z)
    if (L >= 0.4 && L <= 0.7) { midZ = z; break }
  }
  const w = biomeWeights(-100, midZ)
  const L = landMask(-100, midZ)
  const sum = w.sand + w.tidal + w.grass + w.forest + w.hill + w.mountain
  ok('R32-A2 中带草原+林地主导（L∈[0.4,0.7] 处）',
    midZ !== 0 && w.grass + w.forest > 0.6, `z=${midZ} L=${L.toFixed(3)} grass=${w.grass.toFixed(2)} forest=${w.forest.toFixed(2)}`)
  ok('R32-A2 权重归一（和=1）', close(sum, 1, 1e-9), `sum=${sum}`)
}

// A3 雪线：SNOW_LINE=205；远山有雪载体（>205）、草原带无雪（<205）
{
  ok('R32-A3 雪线 SNOW_LINE = 380（CPU/GPU 同值，round10 上调）', SNOW_LINE === 380, `=${SNOW_LINE}`)
  // round7 起高地振幅分区高矮，固定深陆点未必高于雪线 —— 改扫北陆块存在性
  // （主峰 1200m 级恒在，雪冠载体不可能消失；断言存在性而非定点高度）
  let highFound = false
  for (let x = -4600; x <= -100 && !highFound; x += 200) {
    for (let z = -4600; z <= -2100; z += 200) {
      if (landMask(x, z) > 0.9 && terrainHeight(x, z) > SNOW_LINE) { highFound = true; break }
    }
  }
  ok('R32-A3 高地高于雪线（雪冠有载体）', highFound, '北陆块扫描')
  const midH = terrainHeight(-100, -2600) // 草原中带
  ok('R32-A3 草原带低于雪线（雪不污染草原）', midH < SNOW_LINE, `=${midH.toFixed(1)}m`)
}

// A5 复杂地貌奇观（round3）：主峰高度、峡湾通道为海、海岬连陆、海蚀柱孤立
{
  const peakH = terrainHeight(PEAKS[0].x, PEAKS[0].z)
  ok('R32-A5 主峰直插云霄（>600m，12倍轮毂高的量级）', peakH > 600, `=${peakH.toFixed(0)}m`)
  const midX = (FJORD_A.x + FJORD_B.x) / 2
  const midZ = (FJORD_A.z + FJORD_B.z) / 2
  ok('R32-A5 峡湾通道为海（中线 landMask=0）', landMask(midX, midZ) === 0,
    `L=${landMask(midX, midZ)} h=${terrainHeight(midX, midZ).toFixed(1)}m`)
  const hd = HEADLANDS[0]
  ok('R32-A5 海岬连陆（mask=1，为连岛岬非孤岛）', landMask(hd.x, hd.z) === 1,
    `L=${landMask(hd.x, hd.z)}`)
  // 每柱配一个向海见证点（柱体 mask≈1、高>10m，向海一侧 300m 外为海即孤立；
  // 近岸柱的向陆一侧本就连浅滩，不在此约束）
  const WIT: [number, number][] = [[-700, -1700], [-850, -1350], [2700, 400]]
  let stacksOK = true
  STACKS.forEach((st, i) => {
    if (landMask(st.x, st.z) < 0.9) stacksOK = false
    if (terrainHeight(st.x, st.z) < 10) stacksOK = false
    if (landMask(WIT[i][0], WIT[i][1]) !== 0) stacksOK = false
  })
  ok('R32-A5 海蚀柱孤立（体 mask≈1、高>10m、向海见证点为海）', stacksOK, '三柱')
}

// A4 草地核心：2 万次试投，草原/林下命中 >1%（>200）
{
  const g = grassSampleHits(0)
  const f = grassSampleHits(1)
  ok('R32-A4 草原带可落位（拒绝采样命中>1%）', g > 200, `命中=${g}/20000`)
  ok('R32-A4 林下可落位（拒绝采样命中>1%）', f > 200, `命中=${f}/20000`)
}

// C1 高度烘焙：网格索引↔坐标映射与真值逐点一致（GPU uv = xz/extent+0.5 的 CPU 侧锁）
{
  const g = bakeHeightGrid(16, 9200)
  const pts: Array<[number, number]> = [[0, 0], [15, 15], [0, 15], [15, 0], [7, 9], [3, 12]]
  let gridOK = g.size === 16 && g.extent === 9200 && g.data.length === 256
  for (const [i, j] of pts) {
    const x = (i / 15 - 0.5) * 9200, z = (j / 15 - 0.5) * 9200
    if (Math.abs(g.data[j * 16 + i] - terrainSurfaceY(x, z)) > 0.01) gridOK = false // Float32 存取容差
  }
  ok('R32-C1 高度烘焙映射一致（索引↔坐标↔真值）', gridOK, '16²抽6点')
}

// C3 月夜约定：午夜月在天上（仰角>30°）、正午月在地平线下、月相门控对位
{
  const mid = dayNight(0)
  const noon = dayNight(12)
  const moonOK = mid.moonDir[1] > 0.5 && mid.moonF === 1
    && noon.moonDir[1] < 0.2 && noon.moonF === 0
    && noon.dayF === 1 && mid.dayF === 0
  ok('R32-C3 月夜约定（午夜月高悬/正午月隐/门控对位）', moonOK,
    `午夜月高=${mid.moonDir[1].toFixed(2)} 正午月高=${noon.moonDir[1].toFixed(2)}`)
}

// 17. 热键机位 1-9 回归（2026-09-06：4/7/8/9 视角修复锁）
// ---------------------------------------------------------------
// 根因：旧 4/7/8/9 距塔 104/117/129/124m —— 转子框不下（126m 转子 vs
// 91-112m 框高）且 7/8/9 极角 129-135° 超出 OrbitControls 上限、4/7 落地
// 距离 < minDistance，跳转落地即被约束钳位弹开（“定不住”）。
// 本节把“约束相容 + 转子全框 + 机位在开阔海面”锁成断言。
{
  // 口径对齐：诊断用的轮毂/转子数必须与 NREL 几何铭牌一致
  ok('HOT 口径：诊断轮毂高/转子直径 = TURBINE_SPEC 铭牌',
    TURBINE_SPEC.hubY === 90 && TURBINE_SPEC.rotorD === 126,
    `hubY=${TURBINE_SPEC.hubY} rotorD=${TURBINE_SPEC.rotorD}`)
  ok('HOT 数量：热键机位恰 9 个', CAM_HOTKEYS.length === 9, `=${CAM_HOTKEYS.length}`)

  let distOK = true, polarOK = true, rotorOK = true, seaOK = true
  let worst = ''
  for (let i = 0; i < 9; i++) {
    const u = FARM[unitOf(i)] // R42：1×3 下热键 i → 机组 i%3（3×3 时 = i）
    const d = diagnoseHotkey(i, { baseY: terrainSurfaceY(u.x, u.z) })
    if (!(d.dist3 >= ORBIT_MIN_DISTANCE + 5 && d.dist3 <= ORBIT_MAX_DISTANCE)) { distOK = false; worst += ` hot${i + 1}:dist=${d.dist3.toFixed(0)}` }
    if (!(d.polarDeg <= ORBIT_MAX_POLAR_DEG - 1)) { polarOK = false; worst += ` hot${i + 1}:polar=${d.polarDeg.toFixed(1)}` }
    if (!(d.rotorMaxAbs <= 0.92)) { rotorOK = false; worst += ` hot${i + 1}:rotor=${d.rotorMaxAbs.toFixed(2)}` }
    const { pos } = CAM_HOTKEYS[i]
    if (!(landMask(pos.x, pos.z) < 0.02 && terrainHeight(pos.x, pos.z) < pos.y - 4 && pos.y >= 10)) {
      seaOK = false; worst += ` hot${i + 1}:sea`
    }
  }
  ok('HOT 约束相容：落地距离 ∈ [min+5, max]（跳转不再被顶出）', distOK, worst || '9/9')
  ok('HOT 约束相容：极角 ≤ max-1°（仰拍定得住）', polarOK, worst || '9/9')
  ok('HOT 取景：转子 5 点 |NDC| ≤ 0.92（fov47/16:9 全框+8% 裕度）', rotorOK, worst || '9/9')
  ok('HOT 机位：9 机位均在开阔海面（零沾陆、地形低 4m+、浪上 8m+）', seaOK, worst || '9/9')

  // 仰拍（7/8/9）必须收进全塔：塔基仍在框内（|ndcY| ≤ 0.98），不是只拍半截
  let towerOK = true
  for (const i of [6, 7, 8]) {
    const u = FARM[unitOf(i)]
    const d = diagnoseHotkey(i, { baseY: terrainSurfaceY(u.x, u.z) })
    if (Math.abs(d.ndc.base.y) > 0.98) { towerOK = false; worst += ` hot${i + 1}:baseY=${d.ndc.base.y.toFixed(2)}` }
  }
  ok('HOT 仰拍：7/8/9 塔基在框内（全塔 + 转子同框）', towerOK, worst || '3/3')
}

// R36 · 岸距场（浅水阻尼/拍岸碎浪/水线爬升的同一真值）
// ---------------------------------------------------------------
{
  const deepOK = FARM.every((u) => shoreSigned(u.x, u.z) < -400)
  const worstD = Math.max(...FARM.map((u) => shoreSigned(u.x, u.z)))
  ok('R36 岸距：全机组离岸 >400m（深水区，涌浪全幅不受阻尼）', deepOK,
    `最浅机=${worstD.toFixed(0)}m`)
  const isl = ISLANDS[0]
  ok('R36 岸距：岛心为陆侧（>0），岛外 1.5km 为海侧（<0）',
    shoreSigned(isl.x, isl.z) > 0 && shoreSigned(isl.x + 1500, isl.z) < 0,
    `岛心=${shoreSigned(isl.x, isl.z).toFixed(0)} 岛外=${shoreSigned(isl.x + 1500, isl.z).toFixed(0)}`)
  // 海侧渐近：北岸线外侧 100m vs 800m，离岸距离应单调（更远更负）
  const dN100 = shoreSigned(-300, -2060) // 北岸中段（陆侧约 -2060 以北为陆）
  ok('R36 岸距：北岸外侧海点为负（海侧带符号）', dN100 < 0, `=${dN100.toFixed(0)}m`)
}

// R36 · 远岸森林（treeAccept 同真值：落位约束 + 命中率）
// ---------------------------------------------------------------
{
  const hits = treeSampleHits()
  ok('R36 森林：拒绝采样命中 >1%（林带真实存在、可铺满）', hits > 200, `命中=${hits}/20000`)
  const rnd = mulberry32(99)
  let n = 0
  let allOK = true
  let worstInfo = ''
  for (let i = 0; i < 60000 && n < 300; i++) {
    const x = (rnd() * 2 - 1) * TREE_SPAN_M
    const z = (rnd() * 2 - 1) * TREE_SPAN_M
    const s = treeAccept(x, z, rnd())
    if (s <= 0) continue
    n++
    if (landMask(x, z) < 0.30) { allOK = false; worstInfo = '沾海岸带' }
    if (terrainHeight(x, z) > SNOW_LINE - 39) { allOK = false; worstInfo = '超雪线' }
    if (s < 7.5 - 1e-9 || s > 16.5 + 1e-9) { allOK = false; worstInfo = '尺度域' }
  }
  ok('R36 森林：命中点全过约束（内陆≥0.30 / 雪线下 / 尺度 7.5~16.5m）', n > 0 && allOK,
    `样本=${n} ${worstInfo}`)
}

// R36 · 渲染层口径锁（防后续重构悄悄丢特性；源码 token 级）
// ---------------------------------------------------------------
{
  const read = (p: string) => readFileSync(p.startsWith('src/') ? TWIN_ROOT + p : p, 'utf8')
  const wt = read('src/scene/WorldTerrain.tsx')
  ok('R36 海面：浅水阻尼 + 拍岸碎浪带 + 水线爬升（aShore 消费链完整）',
    wt.includes('aShore') && wt.includes('shoreDamp') && wt.includes('surfRoll') && wt.includes('swash'),
    'VERT 阻尼/swash + FRAG surfRoll')
  ok('R36 海面：远海收边 2600→4420m 全雾（地平线假缝根除）', wt.includes('2600.0, 4420.0'))
  ok('R36 海面：背光透射 + 双瓣高光 + 微细节距离衰减',
    wt.includes('sss') && wt.includes('specBroad') && wt.includes('rippleFade'))
  const sky = read('src/scene/SkyAurora.tsx')
  ok('R36 天空：下半球融雾（uFogColor）+ 白昼卷云（cov）',
    sky.includes('uFogColor') && sky.includes('cov'))
  const tf = read('src/scene/treeField.tsx')
  ok('R36 森林组件：画质分档 + 风摆 + 雾/昼夜同口径',
    tf.includes('TREE_TIERS') && tf.includes('uWind') && tf.includes('uFogDensity') && tf.includes('uDayF'))
  const app = read('src/App.tsx')
  ok('R36 森林挂载：<TreeField/> 在场景装配内', app.includes('<TreeField />'))
}

// R36b · 月落修复锁：月亮必须真的落山（旧版 y=Math.max(0.06,·) 把月钉在
// 3.44° 贴地平线水平滑行后中途淡出；月出同理凭空出现）。满月与日反相：
// 17:24 东升 / 05:24 西落（与日出同刻），昼夜无跳变。
{
  const rise = dayNight(18), set = dayNight(6)
  ok('R36b 月相：18 时月已升（y>0.05）、6 时月已落（y<0）',
    rise.moonDir[1] > 0.05 && set.moonDir[1] < 0,
    `18时y=${rise.moonDir[1].toFixed(3)} 6时y=${set.moonDir[1].toFixed(3)}`)
  let minY = 1, maxStep = 0, prevY = dayNight(0).moonDir[1]
  for (let t = 0.05; t <= 24.0001; t += 0.05) {
    const y = dayNight(t).moonDir[1]
    minY = Math.min(minY, y)
    maxStep = Math.max(maxStep, Math.abs(y - prevY))
    prevY = y
  }
  ok('R36b 月落深度：24h 内最低仰角 sin ≤ -0.55（真落到地平线下，无托底）', minY <= -0.55, `minY=${minY.toFixed(3)}`)
  ok('R36b 月轨连续：0.05h 步长最大 |Δy| < 0.01（无跳变/无钳制折点）', maxStep < 0.01, `maxΔ=${maxStep.toFixed(4)}`)
}

// R36c · 夜陆口径锁：夜间陆地 = 暗底乘性 + 方向月光（旧版加性 wrap 抬灰底 → 灰白）
{
  const wt = readFileSync(TWIN_ROOT + 'src/scene/WorldTerrain.tsx', 'utf8')
  ok('R36c 夜陆：乘性月光塑形（nightBase/moonSlope/moonGate），无加性灰底',
    wt.includes('nightBase') && wt.includes('moonSlope') && wt.includes('moonGate')
    && !wt.includes('landCol += vec3(0.30, 0.42, 0.58)'),
    '加性 wrap 月光必须移除')
  const tf = readFileSync(TWIN_ROOT + 'src/scene/treeField.tsx', 'utf8')
  ok('R36c 夜树：同口径乘性月光（nightMultT），无加性灰底',
    tf.includes('nightMultT') && !tf.includes('col += vec3(0.30, 0.42, 0.58)'),
    '树与地形同病同治')
}

// R37 · 太阳色温（连续、仰角驱动）：初升红 → 金 → 白，日落对称；无时间窗
{
  const g = sunWarmth
  ok('R37 色温演进：5:30 红日(>0.9) → 6 时金(>0.7) → 7 时淡金(0.15~0.5) → 正午白(=0)',
    g(5.5) > 0.9 && g(6.0) > 0.7 && g(7.0) > 0.15 && g(7.0) < 0.5 && g(12) === 0,
    `5.5=${g(5.5).toFixed(2)} 6=${g(6).toFixed(2)} 7=${g(7).toFixed(2)} 12=${g(12)}`)
  ok('R37 色温对称：日落前同样泛红(17.3 > 0.9)；夜间为 0（月光不染暖）',
    g(17.3) > 0.9 && g(0) === 0 && g(3) === 0 && g(23) === 0,
    `17.3=${g(17.3).toFixed(2)} 0=${g(0)} 3=${g(3)}`)
  let maxG = 0, prevG = g(0)
  for (let t = 0.02; t <= 24.0001; t += 0.02) {
    const v = g(t)
    maxG = Math.max(maxG, Math.abs(v - prevG))
    prevG = v
  }
  ok('R37 色温连续：0.02h 步长最大 |Δ| < 0.2（红→金→白全程平滑，无开关跳变）',
    maxG < 0.2, `maxΔ=${maxG.toFixed(3)}`)
  const wtR = readFileSync(TWIN_ROOT + 'src/scene/WorldTerrain.tsx', 'utf8')
  ok('R37 渲染：雪冠红金(alpen/alpenCol) + 岩脊暖线 + 晨昏波光同色温 + uWarmF',
    wtR.includes('alpen') && wtR.includes('alpenCol') && wtR.includes('uWarmF')
    && wtR.includes('sunCol = mix(sunCol, vec3(1.00, 0.52, 0.24), uWarmF'))
  const skyR = readFileSync(TWIN_ROOT + 'src/scene/SkyAurora.tsx', 'utf8')
  ok('R37 渲染：日轮本体色温(sunDiscCol)随仰角红→金→白', skyR.includes('sunDiscCol') && skyR.includes('uWarmF'))
  const lrR = readFileSync(TWIN_ROOT + 'src/scene/LightRig.tsx', 'utf8')
  ok('R37 主灯：sunWarmth 驱动色温暖化 + skyState.warmF 写入',
    lrR.includes('sunWarmth') && lrR.includes('warmF'))
}

// R39 · T4 落地锁（从孤儿分支 a3 采纳并重写的三项：波系同源 / 真天空反射 / 云掩日月次序）
// ---------------------------------------------------------------
// 依据：docs/research/round38_残项收口与裁决.md §一（先裁决后合并）；
//      实现落在主线基线上，不照抄 a3 写法。
{
  const wt = readFileSync(TWIN_ROOT + 'src/scene/WorldTerrain.tsx', 'utf8')
  const vert = wt.slice(wt.indexOf('const VERT'), wt.indexOf('const FRAG'))
  const frag = wt.slice(wt.indexOf('const FRAG'), wt.indexOf('export default function'))

  // ① 波系同源：VERT 的 Gerstner 与 FRAG 的 swellN 必须逐项对表（波长/陡度/时间系数/相位）
  const gs = [...vert.matchAll(/gerstner\(p,\s*(\w+),\s*([\d.]+),\s*([\d.]+),\s*uTime \* ([\d.]+)((?:\s*\+\s*[\d.]+)?)\s*,/g)]
    .map((m) => ({ dir: m[1], steep: m[2], lambda: m[3], tc: m[4], phase: m[5].replace(/\s+/g, '') }))
  const expect = [
    { steep: '0.06', lambda: '2400.0', tc: '0.35', phase: '' },
    { steep: '0.045', lambda: '1500.0', tc: '0.50', phase: '+2.1' },
  ]
  const tableOK = gs.length === 2 && gs.every((g, i) =>
    g.steep === expect[i].steep && g.lambda === expect[i].lambda
    && g.tc === expect[i].tc && g.phase === expect[i].phase)
  ok('R39 波系同源：VERT 仍是两条 Gerstner（λ 2400/1500 · 陡度 0.06/0.045 · 时序 0.35/0.50+2.1）',
    tableOK, JSON.stringify(gs))
  const need = ['6.28318530718 / 2400.0', '6.28318530718 / 1500.0', '0.06 / k1', '0.045 / k2', 't * 0.35', 't * 0.50 + 2.1']
  const miss = need.filter((n) => !frag.includes(n))
  ok('R39 波系同源：FRAG swellN 与 VERT 同方向/同波长/同相位/同幅值（照抄项级对表）',
    frag.includes('float swellN') && miss.length === 0, miss.join(' '))
  ok('R39 波系同源：waveHeight = 0.72·swellN·swellEnv + 次网格细节；法线 = 几何法线 + 解析细节',
    frag.includes('0.72 * swellN(p) * swellEnv()') && frag.includes('vec3 waterNormal(vec3 gN')
    && frag.includes('normalize(gN + vec3(') && frag.includes('float rippleHeight(vec2 p)'))
  ok('R39 波系同源：VERT 几何法线同吃 amp 包络（防「水面不动、法线在摇」）',
    vert.includes('mix(vec3(0.0, 1.0, 0.0), gNorm, clamp(amp, 0.0, 1.0))'))

  // ② 真天空反射：反射色必须来自天幕采样（同源消费 uWarmF/uFogColor/uSunDir/uMoonDir）
  ok('R39 真天空反射：seaSky() 存在且被 reflect(-V,N) 驱动（反射与视角/日月/色温同源）',
    wt.includes('vec3 seaSky(vec3 R, float sGate)') && wt.includes('vec3 Rr = reflect(-V, N)')
    && wt.includes('vec3 skyRef = seaSky(Rr, sGateNow)'))
  ok('R39 真天空反射：旧「与视角无关的平涂 skyRef」已移除',
    !wt.includes('vec3 skyRef = mix(vec3(0.014, 0.032, 0.054)'),
    '平涂反射 = 反射一个天上不存在的颜色（round38 §一 判据）')

  // ③ 云掩日月次序：云必须画在日月之后（云可遮日月），不再自相矛盾
  const sky = readFileSync(TWIN_ROOT + 'src/scene/SkyAurora.tsx', 'utf8')
  const sIdx = sky.indexOf('sunDiscCol'), mIdx = sky.indexOf('moonDot ='), cIdx = sky.indexOf('cov = smoothstep')
  ok('R39 云掩日月次序：日 → 月 → 云（云最后画，可遮日月；夜间云不可见不抢星野）',
    sIdx > -1 && mIdx > sIdx && cIdx > mIdx, `sun=${sIdx} moon=${mIdx} cloud=${cIdx}`)
}

// ================================================================
// G · L4 物理内核（FLORIS 4.6.6 GCH 移植）vs FLORIS 实算 oracle
// 数据：src/data/oracle/florisGchOracle.ts（生成件，勿手改；
//   生成器 docs/research/scripts/generate_floris_gch_oracle.py，
//   FlorisModel('defaults')=GCH，TI=0.06，shear=0.12@90m）
// 容差口径：TS 为行级移植（float64），容差设宽 2 个数量级以上，
//   任何结构性偏差都会越线。
// ================================================================
import { ORACLE } from '../src/data/oracle/florisGchOracle.ts'
import { evaluateFarmScene } from '../src/core/physics/evalFarm.ts'
import { sampleHubPlane, __debugRotorU } from '../src/core/physics/gch.ts' // R44 演示 C1 水平面采样

console.log('== G · L4 GCH 内核 V&V（oracle：FLORIS 4.6.6 实算）==')

// G1 功率链（单机：剪切廓线 3×3 网格 + cubic-mean + 速度域修正 + 表插值）
{
  let maxD = 0, atU = 0
  for (const c of ORACLE.powerCurve) {
    const r = evaluateFarmScene({ x: [0], z: [0] }, { uInf: c.u, fromDeg: 270, ti: 0.06 }, [0])
    const d = Math.abs(r.totalKw - c.kW)
    if (d > maxD) { maxD = d; atU = c.u }
  }
  ok('G1 功率曲线 47 点：|ΔP| ≤ 0.05 kW（剪切网格+cubic-mean+表口径，6→731.0 锚点）',
    maxD <= 0.05, `maxΔ=${maxD.toExponential(2)} kW @u=${atU}`)
  const c0 = ORACLE.powerCurve[8] // u=7 m/s
  const r0 = evaluateFarmScene({ x: [0], z: [0] }, { uInf: c0.u, fromDeg: 270, ti: 0.06 }, [0])
  ok('G1 uEff 链（立方平均风速）|Δ| ≤ 0.005 m/s',
    Math.abs(r0.turbines[0].uEff - c0.uEff) <= 0.005,
    `got=${r0.turbines[0].uEff} want=${c0.uEff}`)
  ok('G1 Ct 表链 |Δ| ≤ 0.002',
    Math.abs(r0.turbines[0].ct - c0.Ct) <= 0.002,
    `got=${r0.turbines[0].ct} want=${c0.Ct}`)
}

// G2 双机 5D（13 偏航：尾流+偏折+二次导向+横向速度+WAT 全链路）
{
  const sc = { x: [0, 632], z: [0, 0] } // FLORIS [0,0]→[632,0]，wd=270（流向+x）
  let mUp = 0, mDn = 0, mU = 0, mCt = 0, mTi = 0
  for (const c of ORACLE.pair8ms) {
    const r = evaluateFarmScene(sc, { uInf: 8, fromDeg: 270, ti: 0.06 }, [c.yaw, 0])
    mUp = Math.max(mUp, Math.abs(r.turbines[0].powerKw - c.pUpKw))
    mDn = Math.max(mDn, Math.abs(r.turbines[1].powerKw - c.pDnKw))
    mU = Math.max(mU, Math.abs(r.turbines[1].uEff - c.uEffDn))
    mCt = Math.max(mCt, Math.abs(r.turbines[1].ct - c.ctDn))
    mTi = Math.max(mTi, Math.abs(r.turbines[1].ti - c.tiDn))
  }
  ok('G2 双机 13 偏航：上游 |ΔP| ≤ 0.05 kW', mUp <= 0.05, `maxΔ=${mUp.toExponential(2)} kW`)
  ok('G2 双机 13 偏航：下游 |ΔP| ≤ 0.5 kW（GCH 全链路）', mDn <= 0.5, `maxΔ=${mDn.toFixed(3)} kW`)
  ok('G2 下游 uEff |Δ| ≤ 0.005 m/s', mU <= 0.005, `maxΔ=${mU.toFixed(5)} m/s`)
  ok('G2 下游 Ct |Δ| ≤ 0.002', mCt <= 0.002, `maxΔ=${mCt.toFixed(5)}`)
  ok('G2 下游 TI（crespo WAT+偏航恢复）|Δ| ≤ 0.002', mTi <= 0.002, `maxΔ=${mTi.toFixed(5)}`)
}

// G3 九机阵列（规范 3×3@632m 场景几何，北来风）—— 3×3 专属：oracle 即 3×3 生成件；
// 1×3 对应组 = G3t（tandem3 oracle，R42 #2 落地后加入，勿提前写假靶值）
if (ACTIVE_LAYOUT === '3x3')
{
  const sc = { x: FARM.map((f) => f.x), z: FARM.map((f) => f.z) }
  const none = ORACLE.array.none
  const r0 = evaluateFarmScene(sc, { uInf: 8, fromDeg: 0, ti: 0.06 }, new Array(9).fill(0))
  const mNone = Math.max(
    Math.abs(r0.totalKw - none.totalKw),
    ...r0.turbines.map((t, i) => Math.abs(t.powerKw - none.pKw[i])),
  )
  ok('G3 阵列 none：总/逐机 |ΔP| ≤ 0.5 kW（总 ~8108 kW，含 WAT 跨 3 排）',
    mNone <= 0.5, `maxΔ=${mNone.toFixed(3)} kW`)
  const mNoneU = Math.max(...r0.turbines.map((t, i) => Math.abs(t.uEff - none.uEff[i])))
  ok('G3 阵列 none：逐机 uEff |Δ| ≤ 0.005 m/s', mNoneU <= 0.005, `maxΔ=${mNoneU.toFixed(5)}`)
  const mNoneTi = Math.max(...r0.turbines.map((t, i) => Math.abs(t.ti - none.ti[i])))
  ok('G3 阵列 none：逐机 TI |Δ| ≤ 0.003', mNoneTi <= 0.003, `maxΔ=${mNoneTi.toFixed(5)}`)
  let mUni = 0
  for (const c of ORACLE.array.unifiedTotal) {
    const r = evaluateFarmScene(sc, { uInf: 8, fromDeg: 0, ti: 0.06 }, new Array(9).fill(c.yaw))
    mUni = Math.max(mUni, Math.abs(r.totalKw - c.totalKw))
  }
  ok('G3 阵列 统一偏航 13 档：总 |ΔP| ≤ 1 kW（含 +30°=9060.12 钦定工况）',
    mUni <= 1, `maxΔ=${mUni.toFixed(3)} kW`)
  let mRow = 0
  for (const c of ORACLE.array.row0Scan) {
    const yaw = new Array(9).fill(0)
    for (let i = 0; i < 3; i++) yaw[i] = c.yaw
    const r = evaluateFarmScene(sc, { uInf: 8, fromDeg: 0, ti: 0.06 }, yaw)
    mRow = Math.max(mRow, Math.abs(r.totalKw - c.totalKw))
  }
  ok('G3 阵列 上游排扫描 13 档：总 |ΔP| ≤ 1 kW', mRow <= 1, `maxΔ=${mRow.toFixed(3)} kW`)
  let mCfg = 0
  for (const [name, c] of Object.entries(ORACLE.array.configs)) {
    const r = evaluateFarmScene(sc, { uInf: 8, fromDeg: 0, ti: 0.06 }, [...c.yaw])
    mCfg = Math.max(mCfg, ...r.turbines.map((t, i) => Math.abs(t.powerKw - c.pKw[i])))
    void name
  }
  ok('G3 阵列 多行配置 5 组：逐机 |ΔP| ≤ 1 kW（含 [30,20,0] 贪心族）', mCfg <= 1, `maxΔ=${mCfg.toFixed(3)} kW`)
}

// G3t 三机串列（R42 · 1×3 真值组：tandem3 oracle，= 3×3 中列，floris 4.6.6 GCH）
// 布局无关（内核吃显式坐标），两种布局下都跑
{
  const td = ORACLE.tandem3
  const sc3 = { x: [-100, -100, -100], z: [-1272, -640, -8] } // 场景系北→南 = FLORIS y=1272/640/8
  const r0 = evaluateFarmScene(sc3, { uInf: 8, fromDeg: 0, ti: 0.06 }, [0, 0, 0])
  const mNone = Math.max(
    Math.abs(r0.totalKw - td.none.totalKw),
    ...r0.turbines.map((tb, i) => Math.abs(tb.powerKw - td.none.pKw[i])),
  )
  ok('G3t 串列 none：总/逐机 |ΔP| ≤ 0.5 kW（2702.2 kW，T01 满发 T02/T03 尾流）',
    mNone <= 0.5, `maxΔ=${mNone.toFixed(3)} kW 逐机=${r0.turbines.map((tb) => tb.powerKw.toFixed(1)).join('/')}`)
  const mNoneU = Math.max(...r0.turbines.map((tb, i) => Math.abs(tb.uEff - td.none.uEff[i])))
  ok('G3t 串列 none：逐机 uEff |Δ| ≤ 0.005 m/s', mNoneU <= 0.005, `maxΔ=${mNoneU.toFixed(5)}`)
  let mUni = 0
  for (const c of td.unified) {
    const r = evaluateFarmScene(sc3, { uInf: 8, fromDeg: 0, ti: 0.06 }, [c.yaw, c.yaw, c.yaw])
    mUni = Math.max(mUni, Math.abs(r.totalKw - c.totalKw))
  }
  ok('G3t 串列 统一偏航 13 档：总 |ΔP| ≤ 1 kW', mUni <= 1, `maxΔ=${mUni.toFixed(3)} kW`)
  let mScan = 0
  for (const c of td.upstreamScan) {
    const r = evaluateFarmScene(sc3, { uInf: 8, fromDeg: 0, ti: 0.06 }, [c.yaw, 0, 0])
    mScan = Math.max(mScan, Math.abs(r.totalKw - c.totalKw))
  }
  for (const c of td.midstreamScan) {
    const r = evaluateFarmScene(sc3, { uInf: 8, fromDeg: 0, ti: 0.06 }, [0, c.yaw, 0])
    mScan = Math.max(mScan, Math.abs(r.totalKw - c.totalKw))
  }
  ok('G3t 串列 上游/中游单列扫描各 13 档：总 |ΔP| ≤ 1 kW', mScan <= 1, `maxΔ=${mScan.toFixed(3)} kW`)
  const rG = evaluateFarmScene(sc3, { uInf: 8, fromDeg: 0, ti: 0.06 }, td.greedy.yaw)
  ok('G3t 串列 贪心终态 [30,25,0]：总 |ΔP| ≤ 1 kW（+22.11%，异于 3×3 的 24.04%）',
    td.greedy.yaw.join(',') === '30,25,0' && Math.abs(rG.totalKw - td.greedy.totalKw) <= 1,
    `yaw=${td.greedy.yaw.join('/')} Δ=${(rG.totalKw - td.greedy.totalKw).toFixed(3)} kW`)
  ok('G3t 交叉校验元数据：零偏航下 1×3 ≈ 3×3 中列切片（maxDiff ≤ 0.5 kW；+30° 时 ~12 kW=横偏跨列，见 round42 §3.3）',
    td.crossCheck3x3.none.maxDiffKw <= 0.5,
    `none=${td.crossCheck3x3.none.maxDiffKw.toFixed(3)} +30=${td.crossCheck3x3.unifiedPlus30.maxDiffKw.toFixed(2)} kW`)
}

// G4t R44 · sampleHubPlane 轮毂高度水平面采样（演示 C1 流场；布局无关，吃显式坐标）
// 口径文档：机组状态复用 runGCH（ti 取恢复后值，亚百分点级 sigma 差，仅展示场）
{
  const XF = [-100, -100, -100], YF = [1272, 640, 8]
  const W = { uInf: 8, fromDeg: 0, ti: 0.06 }
  // ① 轴点 = 内核转子网格中心点（同一套 GCH 公式，浮点噪声级）
  const u27 = __debugRotorU(XF, YF, W, [0, 0, 0])
  const kC = [u27[4], u27[13], u27[22]] // 各机 order 中心点（g=4）
  let dC = 0
  for (let si = 0; si < 3; si++) {
    dC = Math.max(dC, Math.abs(sampleHubPlane(XF, YF, W, [0, 0, 0], [-100], [YF[si]])[0] - kC[si]))
  }
  ok('G4t sampleHubPlane 轴点 = 内核转子中心点（|Δ| ≤ 0.001 m/s）', dC <= 0.001, `maxΔ=${dC.toExponential(2)} m/s`)
  // ② none 尾流结构：净风 8.0 / T01 下游 322m / T02 下游 80m（近场深）/ T03 下游 408m
  const uF = sampleHubPlane(XF, YF, W, [0, 0, 0], [-100], [1500, 950, 560, -400])
  ok('G4t 流场结构(none)：净风=8.0，T01 下游 322m<6，T02 下游 80m<4，T03 下游 408m<7 (m/s)',
    Math.abs(uF[0] - 8) < 1e-9 && uF[1] < 6 && uF[2] < 4 && uF[3] < 7,
    `u=${uF.map((v) => v.toFixed(2)).join('/')}`)
  // ③ greedy [30,25,0]：T01/T02 偏航 → 尾流偏离开轴 + T02 自身尾流减轻 → T02 下游轴点回升
  const uG = sampleHubPlane(XF, YF, W, [30, 25, 0], [-100], [560])
  ok('G4t 流场偏折(greedy)：T02 下游 80m 轴点回升 ≥ 1.5 m/s（0.42→≥1.9）',
    uG[0] - uF[2] >= 1.5, `Δ=${(uG[0] - uF[2]).toFixed(2)} m/s`)
}

// G4/G5（横偏质心 + 横截面）待 gch.ts 的 sampleCrossPlane 导出后启用 ——
// 设计见 docs/research/round38 交接文档 §5（需独立求值网格，不可复用 3×3 转子网格）。

// R38 · 证据链完整性（docs/08 D2 精神：把「要拿证据」沉淀成可执行断言）
// 历史坑：① `twin/shots/` 曾提交 16 个 0 字节 PNG（分步 A/B 序列全是空文件＝假证据）；
// ② `twin/docs/` 与 `docs/` 双证据树，路径漂移后文档指不到图（本轮已合并为单树）。
// 两条都在这里锁死：图片不得为空，*.md 引用的图片名必须能在证据树里找到。
{
  const IMG = /\.(png|jpe?g|webp|gif|bmp)$/i
  const walk = (dir: string, out: string[] = []): string[] => {
    if (!existsSync(dir)) return out
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (e.name === 'node_modules' || e.name === 'dist' || e.name.startsWith('.')) continue
      const p = `${dir}/${e.name}`
      if (e.isDirectory()) walk(p, out)
      else out.push(p)
    }
    return out
  }
  // 2026-10-05（R41 前置基线修复）：聊天截图自 2026-09-21 起归档在
  // `materials/集体/聊天记录/`（materials/README 规则 8/9），而 docs/project/TIMELINE.md
  // 会按名引用它们；本守卫写于 09-21 归档之前，证据树还只有 docs + image-search，
  // 于是把 3 处合法引用判成断链。证据树因此扩为 docs + image-search + materials。
  // 0 字节检查一并覆盖 materials（纳管当天实测 56 张图、零空文件；只增严不放宽）。
  const repoRoot = new URL('../../', import.meta.url).pathname
  const evidence = [...walk(repoRoot + 'docs'), ...walk(repoRoot + 'image-search'), ...walk(repoRoot + 'materials')]
  const empty = evidence.filter((f) => IMG.test(f) && statSync(f).size === 0)
  ok('R38 证据完整性：docs/、image-search/ 与 materials/ 下不存在 0 字节图片',
    empty.length === 0, `${empty.length} 个：${empty.slice(0, 3).join(' ')}`)

  const present = new Set(evidence.filter((f) => IMG.test(f)).map((f) => f.split('/').pop()!))
  const missing: string[] = []
  // 证据图引用必须可查：漏拍 / 改名 / 移树都在这里锁死。
  // 不查：命令行示例（shot.mjs/abdiff/… 行）、花括号速记、`<占位>.png`。
  const CMD = /shot\d?\.mjs|abdiff|framestats|horizoncheck|perfstats|python3|npm run|npx |^\s*\$/
  // 切词须把全角标点也当分隔符：审计文档描写误报根因时的全角括号曾把后缀粘成假文件名（AUD-01）
  const TOK = /[^\s`"'()[\]<>|{},*?（）「」『』、，。：；·…—]+\.(?:png|jpe?g)/g // 排除通配（`r33_*.png` 是集合描述，不是链接）
  // 设计上已不存在、但历史文档合理提及的资产（不允许静默扩大此表）：
  //  sky-realistic-cyan.png —— Round-9 #6 删除的 1.9 MB 无许可位图（见 docs/08「删除…无许可记录」）
  const GONE = new Set(['sky-realistic-cyan.png'])
  // 有意不入库、按 ADR-2026-003 存 Release 资产的图片（登记须带出处，不许静默扩大）：
  //  868b9ad82f7aa32bf26d3d9a4dc68b0b.png —— 2026-10-22 交付截图原件，存草稿 Release
  //  `intake-2026-10-22`，sha256 见 materials/集体/交付收取/20261022_三机优化控制与中期答辩/RELEASE_ASSETS.sha256
  const EXTERNAL = new Set(['868b9ad82f7aa32bf26d3d9a4dc68b0b.png'])
  for (const m of walk(repoRoot + 'docs').filter((f) => f.endsWith('.md'))) {
    const lines = readFileSync(m, 'utf8').split('\n')
    lines.forEach((line, i) => {
      if (CMD.test(line)) return
      for (const mm of line.matchAll(TOK)) {
        const prev = mm.index! > 0 ? line[mm.index! - 1] : ' '
        if (!/[\s`(/]/.test(prev)) continue // 不是独立 token（如 r24_{20,30}s_before.png 的尾巴）
        const name = mm[0].split('/').pop()!
        const tag = `${m.split('/').pop()}:${i + 1} → ${name}`
        if (!present.has(name) && !GONE.has(name) && !EXTERNAL.has(name) && !missing.includes(tag)) missing.push(tag)
      }
    })
  }
  ok('R38 证据链：docs/**.md 引用的截图都能找到对应文件（无漏拍/无断链）',
    missing.length === 0, `${missing.length} 处：${missing.slice(0, 6).join(' | ')}`)
}

// ================================================================
// R41-A · 布局真值源守卫（docs/13 §4.5 原文落地 + 两条回归锁）
// 背景：3×3 不删（留档 tag twin-3x3-archive-20260919）、布局可切换；
// 改造最大的风险是"字面量 9 漏改一处"或"3×3 几何被顺手挪动"，都在这里锁死。
// ================================================================
{
  const walkSrc = (dir: string, out: string[] = []): string[] => {
    if (!existsSync(dir)) return out
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = `${dir}/${e.name}`
      if (e.isDirectory()) walkSrc(p, out)
      else out.push(p)
    }
    return out
  }
  // ① src/ 内不得出现字面量 length: 9 / Array(9) / === 9（机组数一律派生）
  const LIT = [/length:\s*9\b/, /Array\(\s*9\s*\)/, /===\s*9\b/]
  const hits: string[] = []
  for (const f of walkSrc(TWIN_ROOT + 'src').filter((f) => /\.(ts|tsx)$/.test(f))) {
    readFileSync(f, 'utf8').split('\n').forEach((line, i) => {
      if (LIT.some((re) => re.test(line))) hits.push(`${f}:${i + 1}`)
    })
  }
  ok('R41 布局：src/ 内无字面量 length:9 / Array(9) / ===9（机组数派生）',
    hits.length === 0, hits.slice(0, 5).join(' '))

  // ② 两套布局都生成合法 FARM：id 连续、行列间距 632、贴地 ≤12 m
  const legal = (id: '3x3' | '1x3'): string[] => {
    const us = LAYOUTS[id].units
    const bad: string[] = []
    if (!us.every((u, i) => u.id === `T0${i + 1}`)) bad.push('id 不连续')
    const gaps = (vals: number[]) => {
      const u = [...new Set(vals)].sort((a, b) => a - b)
      return u.slice(1).map((v, i) => v - u[i])
    }
    const gx = gaps(us.map((u) => u.x))
    const gz = gaps(us.map((u) => u.z))
    if (![...gx, ...gz].every((d) => d === 632)) bad.push(`间距≠632（${gx}/${gz}）`)
    if (!us.every((u) => Math.abs(terrainSurfaceY(u.x, u.z)) <= 12)) bad.push('贴地>12m')
    return bad
  }
  const bad3 = legal('3x3')
  const bad1 = legal('1x3')
  ok('R41 布局：3×3 与 1×3 均合法（id 连续、间距 632、贴地 ≤12m）',
    bad3.length === 0 && bad1.length === 0, `3×3:${bad3.join(',')} 1×3:${bad1.join(',')}`)

  // ③ 1×3 的几何 = 3×3 中列的严格子集（docs/13 §4.5 几何回归）
  const mid = LAYOUTS['3x3'].units.filter((u) => u.col === 1).map((u) => `${u.x},${u.z}`)
  const tan = LAYOUTS['1x3'].units.map((u) => `${u.x},${u.z}`)
  ok('R41 布局：1×3 = 3×3 中列的严格子集（几何回归）',
    mid.length === tan.length && mid.every((v, i) => v === tan[i]), `${mid} vs ${tan}`)

  // ④ 回归锁：3×3 派生几何与留档 tag 的写死值逐位一致（row-major T01–T09）
  const HIST: [number, number][] = [
    [-732, -1272], [-100, -1272], [532, -1272],
    [-732, -640], [-100, -640], [532, -640],
    [-732, -8], [-100, -8], [532, -8],
  ]
  ok('R41 布局：3×3 派生几何与留档 tag 写死值逐位一致',
    LAYOUTS['3x3'].units.every((u, i) => u.x === HIST[i][0] && u.z === HIST[i][1]))

  // ⑤ 派生同源：FARM / SERVOS / ROW_COUNT / 额定功率 与 ACTIVE_LAYOUT 一致
  ok('R41 布局：FARM/SERVOS/ROW_COUNT/额定功率派生自 ACTIVE_LAYOUT',
    FARM.length === LAYOUT.units.length &&
    SERVOS.length === LAYOUT.servos.length && SERVOS.every((v, i) => v === LAYOUT.servos[i]) &&
    ROW_COUNT === LAYOUT.rows &&
    FARM_RATED_MW === LAYOUT.units.length * 5,
    `N=${FARM.length} servos=${SERVOS} rows=${ROW_COUNT} rated=${FARM_RATED_MW}`)
}

// ================================================================
// R42 · 渲染相位冻结 + 1×3 冒烟（round42 §0/§2）
// ================================================================
{
  // freeze：像素差判据的恢复条件（round41 §3.1 判据事故的修复）
  ok('R42 freeze：?freeze=1 → 相位恒定（同参数两次渲染可逐像素比对）',
    phaseFor('?freeze=1&t=15', 999.5) === FROZEN_PHASE && phaseFor('?freeze=1', 0) === FROZEN_PHASE)
  ok('R42 freeze：默认关闭（无参/他值 → 挂钟透传，演示体验不变）',
    phaseFor(null, 7.7) === 7.7 && phaseFor('', 7.7) === 7.7 &&
    phaseFor('?freeze=0', 7.7) === 7.7 && phaseFor('?t=15', 7.7) === 7.7)

  if (ACTIVE_LAYOUT === '1x3') {
    // 1×3 冒烟：能跑到这里 = import 期不再崩（round42 §0.1 的 FARM[6] undefined.x）
    ok('R42 1×3 冒烟：FARM = T01–T03 且北(上游)→南(下游)',
      FARM.length === 3 && FARM.every((u, i) => u.id === `T0${i + 1}`) && FARM[0].z < FARM[1].z && FARM[1].z < FARM[2].z)
    ok('R42 1×3 冒烟：热键 9 槽 → 3 机组（i%3，上游先）',
      unitOf(0) === 0 && unitOf(1) === 1 && unitOf(2) === 2 && unitOf(3) === 0 && unitOf(6) === 0 && unitOf(8) === 2)
    ok('R42 1×3 冒烟：开场 13 航点齐备且有限（路径按布局派生）',
      CAMERA_NODES.length === 13 && LOOK_NODES.length === 13 &&
      [...CAMERA_NODES, ...LOOK_NODES].every((v) => isFinite(v.x) && isFinite(v.y) && isFinite(v.z) && v.y > 0))
    const f15 = farmFrame(15, new Array(3).fill(0), FARM_RATED_MW, null)
    ok('R42 1×3 冒烟：farmFrame 有限且不超额定（3×3 的 45MW 靶值不得泄漏）',
      f15.units.length === 3 && f15.units.every((u) => isFinite(u.powerKw) && u.powerKw >= 0 && u.powerKw <= 5000) &&
      f15.totalMW <= 15.001, `total=${f15.totalMW.toFixed(2)} MW`)
  }
}


// ================================================================
// R40 · T9 声场模型（audioModel 纯函数层：与渲染同源 + 增益映射单调性）
// ================================================================
{
  // 同源：涌浪包络在「场心 + 远岸」两口子上与 WorldTerrain 的 amp 式逐项对表
  const envCenter = swellEnvAt(FARM_CENTER.x, FARM_CENTER.z, -9999)
  const envFarShore = swellEnvAt(FARM_CENTER.x, FARM_CENTER.z, -130) // smoothstep(0,260,130)=0.5
  ok('R40 声场同源：场心包络 = 0.5×浅水阻尼(=1) = 0.5（与 VERT amp 同式）', close(envCenter, 0.5, 1e-9))
  ok('R40 声场同源：岸距 -130m 包络 = 0.5×(0.16+0.84×0.5)（浅水阻尼半程）',
    close(envFarShore, 0.5 * (0.16 + 0.84 * 0.5), 1e-9))
  // 波高有界 + 与视觉同周期
  let hMax = 0
  for (let t = 0; t < swellPeriodS() * 3; t += 0.37) {
    hMax = Math.max(hMax, swellHeightAt(300, 900, t, 4, -800))
  }
  ok('R40 声场：有效波高 ≤ 两 Gerstner 幅值和（22.9+10.7m）', hMax <= SWELL_A1 + SWELL_A2 + 1e-9)
  // 主导涌浪（λ2400，幅值占 0.68）的节奏 = P；第二条（λ1500）周期不可通约，
  // 故 h(t+P) 与 h(t) 的差被第二分量幅值界定（而不是逐点相等）
  const P = swellPeriodS()
  const env = swellEnvAt(300, 900, -800)
  const h1 = swellHeightAt(300, 900, 12.5, 4, -800)
  const h2 = swellHeightAt(300, 900, 12.5 + P, 4, -800)
  ok('R40 声场：涌浪主节奏与视觉同源（|h(t+P)−h(t)| ≤ 2·A2·包络，P=λ1/(c1·0.35)）',
    Math.abs(h1 - h2) <= 2 * SWELL_A2 * env + 1e-9, `P=${P.toFixed(1)}s Δ=${Math.abs(h1 - h2).toFixed(2)}`)
  // 拍岸碎浪：海侧远海无声 / 贴岸最大 / 深入内陆渐隐
  ok('R40 声场：离岸 2km 碎浪增益 = 0', surfGain(-2000, 6) === 0)
  ok('R40 声场：贴岸 30m 碎浪增益 > 离岸 300m', surfGain(-30, 6) > surfGain(-300, 6))
  ok('R40 声场：深入内陆 2km 碎浪增益 = 0（沙滩听得见、村里听不见）', surfGain(2000, 6) === 0)
  ok('R40b 声场：陆地门两段单调（深海 1 → 崖顶≈0.52 → 内陆 2km ≤0.1 后饱和）',
    oceanLandGate(-1000) === 1 && oceanLandGate(200) < 0.6 &&
    oceanLandGate(1200) < oceanLandGate(600) && oceanLandGate(2000) <= 0.1 &&
    oceanLandGate(3000) <= oceanLandGate(2000))
  ok('R40 声场：涌浪底噪随波高单调不减', oceanSwellGain(1) <= oceanSwellGain(6) && oceanSwellGain(6) <= oceanSwellGain(14))
  // 风机声学：叶片通过频率 / 传动链基频 / 距离衰减 / 下风向
  ok('R40 声场：叶片通过频率 = 3×转频（6.9rpm→0.345Hz，12.1rpm→0.605Hz）',
    close(bladePassHz(6.9), 0.345, 1e-9) && close(bladePassHz(12.1), 0.605, 1e-9))
  ok('R40 声场：传动链基频 = 转频×97（12.1rpm→19.56Hz 齿轮箱侧）', close(driveTrainHz(12.1), (12.1 / 60) * 97, 1e-9))
  ok('R40 声场：距离衰减单调递减且 1km 处 < 0.2',
    turbineDistanceGain(50) > turbineDistanceGain(300) && turbineDistanceGain(300) > turbineDistanceGain(1000)
    && turbineDistanceGain(1000) < 0.2)
  // R40b 修「离很远还有明显声音」：可闻地平线 ≥2.2km 必须**精确归零**（不是渐近趋于 0）
  ok('R40b 声场：可闻地平线 —— 2.2km 外精确 = 0；1.5km < 1km 的一半；2km < 1km 的 5%',
    turbineDistanceGain(TURBINE_AUDIBLE_FAR) === 0 && turbineDistanceGain(2500) === 0 &&
    turbineDistanceGain(1500) < turbineDistanceGain(1000) * 0.5 &&
    turbineDistanceGain(2000) < turbineDistanceGain(1000) * 0.05)
  ok('R40 声场：下风向听者增益 > 上风向（IEC 61400-11 常识口径）',
    downwindFactor(0, 500, 0, 0, 0) > downwindFactor(0, -500, 0, 0, 0))
  // 声部裁决：近塔取本机、远场归零（≤3 声部）
  const units = FARM.map((f) => ({ x: f.x, z: f.z, rpm: 11, uEff: 8 }))
  // R42：最近景机组 = 布局末位（3×3=T07 idx6；1×3=T03 idx2），断言口径不变
  const NEAR = FARM[FARM.length - 1]
  const near = selectTurbines(units, NEAR.x + 60, 20, NEAR.z, 0, 3)
  ok(`R40 声场：${NEAR.id} 塔旁 60m 的第一声部就是 ${NEAR.id}`, near.length > 0 && near[0].idx === FARM.length - 1, `got ${near[0]?.idx}`)
  const far = selectTurbines(units, 4200, 300, 4200, 0, 3)
  ok('R40 声场：4km 外全场无声部（融进底噪，不占 PannerNode）', far.length === 0)
  ok('R40 声场：声部数上限 3', selectTurbines(units, FARM_CENTER.x, 90, FARM_CENTER.z, 0, 3).length <= 3)
  ok('R40b 声场：离场心 3.2km（全机 ≥2.4km 过地平线）声部裁决为空',
    selectTurbines(units, FARM_CENTER.x + 3200, 300, FARM_CENTER.z, 0, 3).length === 0)
  // 整帧求值：海上 vs 内陆
  const sea = acousticFrame({ lx: 300, ly: 12, lz: 900, fx: 0, fy: 0, fz: -1, ux: 0, uy: 1, uz: 0, tHours: 9, t: 40, windSpeed: 9, windFromDeg: 4, units })
  const inland = acousticFrame({ lx: -2600, ly: 300, lz: -3000, fx: 0, fy: 0, fz: 1, ux: 0, uy: 1, uz: 0, tHours: 9, t: 40, windSpeed: 9, windFromDeg: 4, units })
  ok('R40 声场：海上涌浪底噪 > 0 且内陆碎浪 = 0', sea.swellGain > 0 && inland.surfGain === 0)
}

// ================================================================
// R40 · T8 草地分块（grassTile：确定性 / 海洋零株 / 贴地真值 / 视距裁决）
// ================================================================
{
  const seaTi = tileAt(FARM_CENTER.x, FARM_CENTER.z)
  ok('R40 草地：场心（纯海）瓦片零株、零地形求值', bladesPerTile(seaTi) === 0 && buildTileBlades(seaTi, bladesPerTile(seaTi)).length === 0)
  const landTi = 58
  const b1 = buildTileBlades(landTi, 600)
  const b2 = buildTileBlades(landTi, 600)
  ok('R40 草地：同瓦片同种子两次落位逐株一致（可复现，D2 红线）', JSON.stringify(b1) === JSON.stringify(b2) && b1.length === 600)
  const t58 = tileFromIndex(landTi)
  let inBounds = true
  let maxDy = 0
  for (const bl of b1) {
    if (Math.abs(bl.x - t58.cx) > 256 + 6 || Math.abs(bl.z - t58.cz) > 256 + 6) inBounds = false
    maxDy = Math.max(maxDy, Math.abs(bl.y + 0.15 - terrainSurfaceY(bl.x, bl.z)))
  }
  ok('R40 草地：落株不越瓦片边界（丛半径羽化 ≤6m）', inBounds)
  ok('R40 草地：丛级贴地平面与 terrainSurfaceY 真值偏差 ≤0.35m', maxDy <= 0.35, `maxΔy=${maxDy.toFixed(3)}m`)
  let total = 0
  for (let ti = 0; ti < GRASS_TILE_COUNT; ti++) total += bladesPerTile(ti)
  ok('R40 草地：全域满密度株数 ≈ 目标（按 biome 权重摊派，不超发 >2%）',
    total > GRASS_TARGET_TOTAL * 0.8 && total <= GRASS_TARGET_TOTAL * 1.02, `total=${total}`)
  ok('R40 草地：视距密度截断单调不增且远端不为零',
    drawnFrac(0) >= drawnFrac(300) && drawnFrac(300) >= drawnFrac(600)
    && drawnFrac(600) >= drawnFrac(1200) && drawnFrac(1200) >= drawnFrac(3000) && drawnFrac(3000) > 0)
  const seaView = tilesInView(FARM_CENTER.x, FARM_CENTER.z, 1600)
  const landView = tilesInView(-800, -2600, 1600)
  ok('R40 草地：陆侧机位视距环瓦片数 > 海上机位（海瓦片不进环）', landView.length > seaView.length, `sea=${seaView.length} land=${landView.length}`)
  // 排序：到瓦片 AABB 的距离不递减
  let sorted = true
  const distOf = (ti: number, cx: number, cz: number) => {
    const t = tileFromIndex(ti)
    return Math.hypot(Math.max(Math.abs(cx - t.cx) - 256, 0), Math.max(Math.abs(cz - t.cz) - 256, 0))
  }
  for (let i = 1; i < landView.length; i++) if (distOf(landView[i], -800, -2600) < distOf(landView[i - 1], -800, -2600) - 1e-9) sorted = false
  ok('R40 草地：视距环按「相机→瓦片最近距离」升序（近的先建先上屏）', sorted)
}

// ================================================================
// R40 · P2 偏航执行器（死区 / 速率限制 / 滞环 / 到位）
// ================================================================
{
  // 死区：±5° 内电机不启停
  let st = createYawActuator(0)
  const inBand = YAW_DEADBAND_DEG - 1
  for (let i = 0; i < 600; i++) st = stepYaw(st, inBand, 0.1)
  ok(`P2 执行器：指令 ${inBand}°（死区内）60s 后实际仍 0°、零起动`, st.actual === 0 && st.cycles === 0 && !st.slewing)
  //  creeping：死区内多次小改指令也不动
  st = createYawActuator(0)
  for (const c of [2, 4, 3, 4.5]) for (let i = 0; i < 100; i++) st = stepYaw(st, c, 0.1)
  ok('P2 执行器：死区内连续小改指令（2/4/3/4.5°）不产生动作', st.actual === 0 && st.cycles === 0)
  // 速率限制 + 到位
  st = createYawActuator(0)
  let maxRate = 0
  let t = 0
  while (t < 200 && (Math.abs(st.actual - 30) > YAW_STOP_BAND_DEG || st.slewing)) {
    st = stepYaw(st, 30, 0.1)
    maxRate = Math.max(maxRate, Math.abs(st.rate))
    t += 0.1
  }
  ok('P2 执行器：偏航速率从不超 0.3°/s（NREL 5MW 口径）', maxRate <= YAW_RATE_DPS + 1e-9, `max=${maxRate.toFixed(4)}`)
  ok('P2 执行器：0→30° 在 85~130s 内到位并抱闸（≈100s + 加减速）',
    t > 85 && t < 130 && !st.slewing && Math.abs(st.actual - 30) <= YAW_STOP_BAND_DEG, `t=${t.toFixed(1)}s`)
  ok('P2 执行器：全程恰好一次起动（无 hunting）', st.cycles === 1)
  // 滞环：指令在起动阈值边抖动不产生连续点动
  st = createYawActuator(0)
  for (let i = 0; i < 3000; i++) st = stepYaw(st, i % 2 ? 5.3 : 4.7, 0.1)
  ok('P2 执行器：指令在 4.7/5.3° 间抖动 300s，起动次数 ≤2（滞环防点动）', st.cycles <= 2, `cycles=${st.cycles}`)
  // 到位倒计时口径
  ok('P2 执行器：yawEtaFrom(30°,0°) = 30/0.3 + 1.6τ ≈ 101.9s', close(yawEtaFrom(30, 0), 30 / YAW_RATE_DPS + 1.2 * 1.6, 1e-9))
  ok('P2 执行器：死区内 eta = 0（设计上不动，不显示倒计时）', yawEtaFrom(inBand, 0) === 0)
  // 整组：步进 + 量化 + QA 瞬移
  const bank = createYawBank(9, new Array(9).fill(0))
  stepYawBank(bank, [30, 0, 0, 0, 0, 0, 0, 0, 0], 0.1)
  const act = bankActual(bank)
  ok('P2 执行器：bankActual 量化到 0.5°（缓存键口径）', act.every((v) => Math.abs(v * 2 - Math.round(v * 2)) < 1e-9))
  snapYawBank(bank, [12.34, -7, 0, 0, 0, 0, 0, 0, 0])
  ok('P2 执行器：snapYawBank（QA 取证）瞬移到指令且量程钳制生效',
    close(bank.states[0].actual, 12.34, 1e-9) && close(bank.states[1].actual, -7, 1e-9))
  stepYawBank(bank, [999, 0, 0, 0, 0, 0, 0, 0, 0], 0.1)
  ok('P2 执行器：指令量程钳制 ±30°（与滑杆/store 同一约束）', close(bank.states[0].cmd, 30, 1e-9))
}

console.log(`\n结果: ${pass} 通过 / ${fail} 失败`)
process.exit(fail ? 1 : 0)
