/* oxlint-disable react/immutability -- 帧循环内 mutate 灯光/雾为 R3F 标准模式（docs/08 D2） */
import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { dayNight, sunWarmth } from '../data/farmSim'
import { useSim } from '../state/simStore'
import { skyState } from './lightState'
import { FREEZE } from './freeze.ts'

// ============================================================
// 昼夜光照装置（任务#2/#3/#10 修订版）
//  · 卡顿根因：仿真时钟 setInterval(100ms) 量化推进，灯光此前按量化值
//    重算 → 太阳一跳一跳。改本组件自带连续钟（与 store 同速 24h/50s，
//    拖轴/暂停时同步），天体位置每帧平滑；
//  · 日出错位根因：夜光位置曾 max(180, y) 硬抬到地平上，18-19 点附近
//    出现"假日出"。现夜=月亮方向（moonDir 构造性高于地平线），
//    晨昏带用 dayF 对太阳/月亮方向与强度做连续混合——金色时刻的
//    长影由真实的低角度产生，不再靠 clamp；
//  · 强度（"以假乱真"诉求）：白天主光 0.34→1.94 连续，半球光压低拉对比，
//    阴影贴图 high 档 4096、相机收紧到 ±1500（纹素密度 ~0.73m），
//    exposure 联动 App=1.14；
//  · 雾/背景随昼夜单色相微移（克制原则：不引入新色相）。
// ============================================================

const C_NIGHT_BG = new THREE.Color('#010305')
const C_DAY_BG = new THREE.Color('#28455e')
const C_NIGHT_FOG = new THREE.Color('#040911')
const C_DAY_FOG = new THREE.Color('#47688a')
const TARGET = new THREE.Vector3(-100, 45, -640)

const wrap24 = (t: number) => ((t % 24) + 24) % 24

export default function LightRig() {
  const quality = useSim((s) => s.quality)
  const sunRef = useRef<THREE.DirectionalLight>(null!)
  const keyNight = useRef<THREE.DirectionalLight>(null!)
  const hemiRef = useRef<THREE.HemisphereLight>(null!)
  const fillA = useRef<THREE.DirectionalLight>(null!)
  const fillB = useRef<THREE.DirectionalLight>(null!)
  const fillC = useRef<THREE.DirectionalLight>(null!)
  const { scene } = useThree()

  const shadowOn = quality !== 'low'
  const mapSize = quality === 'high' ? 4096 : 2048

  const shadowTarget = useMemo(() => {
    const o = new THREE.Object3D()
    o.position.copy(TARGET)
    return o
  }, [])
  const tmp = useMemo(() => ({
    dir: new THREE.Vector3(),
    col: new THREE.Color(),
    simT: -1,
  }), [])

  useFrame((_state, delta) => {
    const s = useSim.getState()
    // —— 连续仿真钟：与 startSimClock 同速率；暂停/跳变时吸附 store 值 ——
    if (tmp.simT < 0) tmp.simT = s.tHours
    // 循环距离（wrap 感知）：24:00→0:00 自然换日 gap≈0.048，不再误判为
    // "跳变 23.95h"而吸附——那正是午夜画面卡一下的放大器
    let g = wrap24(s.tHours) - wrap24(tmp.simT)
    if (g > 12) g -= 24
    if (g < -12) g += 24
    // 开场运镜期间（introDone=false）startSimClock 不推进 tHours，这里也必须
    // 同步冻结连续钟——否则天空/光照会在 43s 里从 06:00 悄悄走到 ~06:20，
    // 而 HUD 时间轴停在 06:00，开场一结束光照才被吸附回 06:00（"开场后光照跳变"）。
    if (FREEZE || !s.playing || !s.introDone || Math.abs(g) > 0.6) tmp.simT = s.tHours // R42 freeze：连续钟恒吸附 store
    else tmp.simT = wrap24(tmp.simT + Math.min(0.1, delta) * (24 / 50))

    const dn = dayNight(tmp.simT)
    // smoothstep 缓入晨昏，日出/日落有 2-3 秒（真实时间）的渐变而非突变
    const fd = dn.dayF * dn.dayF * (3 - 2 * dn.dayF)
    const mf = dn.moonF * dn.moonF * (3 - 2 * dn.moonF)
    skyState.dayF = fd
    // R37 太阳色温：仰角连续驱动（红→金→白）进共享天光总线，场景各层消费。
    // 用连续钟 tmp.simT（非量化 tHours），拖时间轴时色温平滑变化不跳变。
    const warm = sunWarmth(tmp.simT)
    skyState.warmF = warm
    skyState.sunDir.set(...dn.sunDir)
    skyState.moonDir.set(...dn.moonDir)
    const night = 1 - fd

    if (sunRef.current) {
      // 方向：太阳权重 fd、月亮权重 mf 连续交叉——日落瞬间合光仍偏西（余晖），
      // 入夜渐交棒月亮；两臂在晨昏交界同点（对日点），无方位跳变
      tmp.dir.set(
        dn.sunDir[0] * fd + dn.moonDir[0] * mf,
        Math.max(0.045, dn.sunDir[1] * fd + dn.moonDir[1] * mf),
        dn.sunDir[2] * fd + dn.moonDir[2] * mf,
      ).normalize()
      const R = 2600
      sunRef.current.position.set(TARGET.x + tmp.dir.x * R, TARGET.y + tmp.dir.y * R, TARGET.z + tmp.dir.z * R)
      sunRef.current.intensity = 0.34 + 1.6 * fd
      tmp.col.setHex(0xcfe4ff).lerp(new THREE.Color(0xf6fbff), fd)
      // R37 太阳色温：仰角连续驱动 —— 日出橙红 → 金 → 白（风机纯白线稿不受灯光影响）。
      tmp.col.lerp(new THREE.Color(0xff9a4d), warm * 0.6)
      sunRef.current.color.copy(tmp.col)
    }
    if (keyNight.current) keyNight.current.intensity = 0.62 * (0.3 + 0.7 * night)
    if (hemiRef.current) {
      // 白天压半球光 → 阴影对比更"真实"（不糊成一片）
      // 进一步压低白天半球光 0.42+0.24fd → 0.32+0.12fd，让真实阴影贴图对比度更高
      hemiRef.current.intensity = 0.32 + 0.12 * fd
      hemiRef.current.color.setHex(0x123448).lerp(new THREE.Color(0x8fb6d0), fd * 0.75)
    }
    // 夜基补光白天让位更彻底：白天强度 ×0.35，夜间保持原有，阴影不被冲淡
    if (fillA.current) fillA.current.intensity = 0.13 * (0.35 + 0.65 * night)
    if (fillB.current) fillB.current.intensity = 0.16 * (0.35 + 0.65 * night)
    if (fillC.current) fillC.current.intensity = 0.26 * (0.35 + 0.65 * night)
    if (scene.fog && (scene.fog as THREE.FogExp2).isFogExp2) {
      (scene.fog as THREE.FogExp2).color.copy(C_NIGHT_FOG).lerp(C_DAY_FOG, fd * 0.62)
    }
    if (scene.background && (scene.background as THREE.Color).isColor) {
      (scene.background as THREE.Color).copy(C_NIGHT_BG).lerp(C_DAY_BG, fd * 0.72)
    }
  })

  return (
    <>
      <hemisphereLight ref={hemiRef} args={['#123448', '#010408', 0.42]} />
      {/* 夜基补光（v3 构图基准，白天按 fd 让位，阴影对比度优化） */}
      <directionalLight ref={fillA} position={[700, 900, -500]} intensity={0.13} color="#a8d9ff" />
      <directionalLight ref={fillB} position={[-600, 500, 900]} intensity={0.16} color="#3f88b8" />
      <directionalLight ref={keyNight} position={[-750, 1250, -650]} intensity={0.85} color="#d6e6ff" />
      <directionalLight ref={fillC} position={[500, 420, 1150]} intensity={0.26} color="#86b8dc" />
      {/* 主灯：太阳/月亮连续混合，全场唯一阴影源 */}
      <directionalLight
        ref={sunRef}
        intensity={0.34}
        castShadow={shadowOn}
        shadow-mapSize={[mapSize, mapSize]}
        shadow-camera-near={140}
        shadow-camera-far={6400}
        shadow-camera-left={-1500}
        shadow-camera-right={1500}
        shadow-camera-top={1500}
        shadow-camera-bottom={-1500}
        shadow-bias={-0.00035}
        shadow-normalBias={1.4}
      >
        <primitive object={shadowTarget} attach="target" />
      </directionalLight>
    </>
  )
}
