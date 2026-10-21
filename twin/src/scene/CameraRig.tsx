/* oxlint-disable react/immutability -- 帧循环内 mutate refs/camera 为 R3F 控制标准模式（docs/08 D2） */
import { useEffect, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { CAM, FARM } from './terrainUtil'
import { LAYOUT } from './layouts.ts'
import { pushCameraState } from './cameraBus'
import { CAM_HOTKEYS } from './hotkeys.ts'
import { useSim } from '../state/simStore'
import {
  CAMERA_PATH, LOOK_PATH, INTRO_END,
} from './introProfile'

// ============================================================================
// 开场巡航 + 机位书签 + 自由飞行（丝滑无抖动版）
// ----------------------------------------------------------------------------
//  · 34s + 9s 环绕全局单一时间基（ease 缓入缓出，C1 连续，无停顿、无摆动、无抖动）；
//  · 消除前 5 秒黑屏与 180 度翻转：高空俯冲注视点稳定朝向风场中轴，远离垂直奇异点；
//  · 巡航期间禁用 OrbitControls 抢镜；巡航/环绕结束后平滑交接；
//  · 保持视平线稳定，移除造成摇晃抖动的侧倾(bank)与速度阶跃；
//  · 热键机位：键 1-9 = 九个塔位快速镜头（1.2s ease 平滑过渡），
//    机位真值在 ./hotkeys.ts（与 OrbitControls 约束、selftest 断言同源）；
//  · WASD 自由飞行支持。
// ============================================================================

const ORBIT_DUR = 9
const INTRO_TOTAL = INTRO_END + ORBIT_DUR
const PATH_FRAC = INTRO_END / INTRO_TOTAL
const ORBIT_A0 = Math.atan2(168, 76)
const ORBIT_A1 = THREE.MathUtils.degToRad(268)
const ORBIT_R0 = Math.hypot(76, 168)
const ORBIT_R1 = 196
const ORBIT_Y0 = 56
const ORBIT_Y1 = 66
// R42：开场收尾环绕的枢纽机组 = 布局内最近景一台（3×3 为 T07=FARM[6]，1×3 为 T03）。
// 半径/角度沿用（对最近景机组的相对取景），不随布局重设计构图。
const HUB = new THREE.Vector3(FARM[LAYOUT.units.length - 1].x, 0, FARM[LAYOUT.units.length - 1].z)

const ease = (t: number) => t * t * (3 - 2 * t)

const DEBUG_ALLOWED = (typeof import.meta !== 'undefined' && import.meta.env?.DEV === true)
  || (typeof location !== 'undefined' && new URLSearchParams(location.search).has('debug'))

const DEBUG_CAM = (() => {
  if (!DEBUG_ALLOWED || typeof location === 'undefined') return null
  const q = new URLSearchParams(location.search).get('cam')
  if (!q) return null
  const v = q.split(',').map(Number)
  if (v.length < 3 || v.slice(0, 3).some((x) => !Number.isFinite(x))) return null
  return {
    az: v[0], el: v[1], dist: v[2],
    target: new THREE.Vector3(v[3] ?? 0, v[4] ?? 22, v[5] ?? -340),
  }
})()

const NO_INTRO = typeof location !== 'undefined'
  && (new URLSearchParams(location.search).has('intro0') || (DEBUG_ALLOWED && new URLSearchParams(location.search).get('intro') === '0'))

// QA / A/B 帧精确锚点：仅 DEBUG 允许 `?introT=<s>` 冻结开场时钟（软渲染可复现指定帧）。
const INTRO_T_JUMP = (() => {
  if (!DEBUG_ALLOWED || typeof location === 'undefined') return null
  const q = new URLSearchParams(location.search).get('introT')
  if (!q) return null
  const v = Number(q)
  return Number.isFinite(v) ? THREE.MathUtils.clamp(v, 0, INTRO_TOTAL) : null
})()

// —— “目标 + 指数平滑跟随”：不再每帧硬设 position/lookAt（掉帧/切换瞬间会“顿/跳”），
//    而是每帧只追目标。τ=0.14s：加入轻微惯性，60fps 仍跟得紧，掉帧时大位移被摊平，
//    镜头带有物理惯性而非硬切（用户需求：镜头移动惯性）。
//    核心价值：把“巡航→环绕”“环绕→coast”以及任何 / 斜率切换的残余视觉跳变彻底抹平。
const CAM_SMOOTH_TAU = 0.14
const _eUp = new THREE.Vector3(0, 1, 0)
const _eLook = new THREE.Matrix4()
const _eQuat = new THREE.Quaternion()
// 复用目标/自由飞行临时对象，避免热身路径每帧 new Vector3 触发 GC
const _tPos = new THREE.Vector3()
const _tLook = new THREE.Vector3()
const _dir = new THREE.Vector3()
const _right = new THREE.Vector3()
const _mv = new THREE.Vector3()
const _camFwd = new THREE.Vector3()
const _camUp = new THREE.Vector3()
const _flyTarget = new THREE.Vector3()
const FLY_ACCEL_TAU = 0.18
const FLY_DECAY_TAU = 0.55

export default function CameraRig() {
  const controlsRef = useRef<any>(null)
  const { camera } = useThree()
  const introStart = useRef<number | null>(null)
  const bookmark = useRef<{ from: THREE.Vector3; fromT: THREE.Vector3; to: THREE.Vector3; toT: THREE.Vector3; t0: number } | null>(null)

  // 平滑跟随状态：首帧用目标自身初始化，避免起步跳变
  const smPos = useRef(new THREE.Vector3())
  const smLook = useRef(new THREE.Vector3())
  const smFov = useRef(47)
  const smInit = useRef(false)
  // 自由飞行惯性：速度向量持续存在，松键后指数衰减
  const flyVel = useRef(new THREE.Vector3())

  // WASD 自由飞行输入
  const keys = useRef<Set<string>>(new Set())
  useEffect(() => {
    const FLY = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyC', 'Space'])
    const down = (e: KeyboardEvent) => {
      if (e.repeat || !(FLY.has(e.code) || e.code === 'ShiftLeft' || e.code === 'ShiftRight')) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON') return
      keys.current.add(e.code)
      if (FLY.has(e.code)) {
        if (!useSim.getState().introDone && !DEBUG_CAM) useSim.getState().skipIntro()
        if (e.code === 'Space' && useSim.getState().introDone) e.preventDefault()
      }
    }
    const up = (e: KeyboardEvent) => { keys.current.delete(e.code) }
    const blur = () => keys.current.clear()
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', blur)
    }
  }, [])

  // 全局快捷键：Esc 跳过开场 / 1-9 塔位快速镜头（见 ./hotkeys.ts）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useSim.getState()
      if (e.key === 'Escape' || e.key === ' ' || e.key.toLowerCase() === 'y') {
        if (!s.introDone) s.skipIntro()
      }
      const n = Number(e.key)
      if (n >= 1 && n <= CAM_HOTKEYS.length) {
        const b = CAM_HOTKEYS[n - 1]
        const p = camera.position.clone()
        const ctl = controlsRef.current
        bookmark.current = {
          from: p, fromT: ctl ? ctl.target.clone() : new THREE.Vector3(0, 22, -340),
          to: b.pos.clone(), toT: b.target.clone(), t0: performance.now(),
        }
        useSim.getState().skipIntro()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [camera])

  useFrame((state, delta) => {
    if (!controlsRef.current) controlsRef.current = (state.controls as any) || null
    const ctl = controlsRef.current

    // T9 · 声场需要相机位姿（AudioField 在 Canvas 之外，走 cameraBus 旁路）。
    // 放在所有 return 分支之前：DEBUG_CAM / 书签机位 / 自由飞行 / 巡航都覆盖到。
    camera.getWorldDirection(_camFwd)
    _camUp.copy(camera.up).applyQuaternion(camera.quaternion).normalize()
    pushCameraState(camera.position, _camFwd, _camUp)

    if (DEBUG_CAM) {
      if (ctl) ctl.enabled = true
      const a = THREE.MathUtils.degToRad(DEBUG_CAM.az)
      const e = THREE.MathUtils.degToRad(DEBUG_CAM.el)
      const { dist, target } = DEBUG_CAM
      camera.position.set(
        target.x + dist * Math.cos(e) * Math.sin(a),
        target.y + dist * Math.sin(e),
        target.z + dist * Math.cos(e) * Math.cos(a),
      )
      camera.lookAt(target)
      if (ctl) { ctl.target.copy(target); ctl.update() }
      const p0 = camera as THREE.PerspectiveCamera
      p0.fov = 47
      p0.updateProjectionMatrix()
      if (!useSim.getState().introDone) useSim.getState().skipIntro()
      return
    }

    // 书签机位平滑过渡
    const bm = bookmark.current
    if (bm) {
      if (ctl) ctl.enabled = false
      const k = Math.min(1, (performance.now() - bm.t0) / 1200)
      const s = ease(k)
      camera.position.lerpVectors(bm.from, bm.to, s)
      const tg = bm.fromT.clone().lerp(bm.toT, s)
      camera.lookAt(tg)
      if (k >= 1) {
        bookmark.current = null
        if (ctl) {
          ctl.enabled = true
          ctl.target.copy(bm.toT)
          ctl.update()
        }
      }
      return
    }

    const s = useSim.getState()
    if (NO_INTRO && !s.introDone) {
      s.skipIntro()
      if (ctl) {
        ctl.enabled = true
        ctl.target.copy(CAM.target)
        ctl.update()
      }
      return
    }

    if (s.introDone) {
      if (ctl && !ctl.enabled) {
        ctl.target.copy(smLook.current)
        ctl.update()
      }
      if (ctl) ctl.enabled = true
      // WASD 自由飞行（带惯性）
      const k = keys.current
      const fwd = (k.has('KeyW') ? 1 : 0) - (k.has('KeyS') ? 1 : 0)
      const strafe = (k.has('KeyD') ? 1 : 0) - (k.has('KeyA') ? 1 : 0)
      const lift = (k.has('Space') ? 1 : 0) - (k.has('KeyC') ? 1 : 0)
      const hasInput = fwd !== 0 || strafe !== 0 || lift !== 0
      const dtClamped = Math.min(Math.max(delta, 0.001), 0.05)
      if (hasInput) {
        const speed = (k.has('ShiftLeft') || k.has('ShiftRight') ? 620 : 240)
        camera.getWorldDirection(_dir)
        _right.crossVectors(_dir, camera.up).normalize()
        _flyTarget.set(0, 0, 0)
        _flyTarget.addScaledVector(_dir, fwd * speed)
        _flyTarget.addScaledVector(_right, strafe * speed)
        _flyTarget.y += lift * speed * 0.8
        // 加速：指数趋近目标速度
        const a = 1 - Math.exp(-dtClamped / FLY_ACCEL_TAU)
        flyVel.current.lerp(_flyTarget, a)
      } else {
        // 减速：指数衰减，产生滑行惯性
        const d = Math.exp(-dtClamped / FLY_DECAY_TAU)
        flyVel.current.multiplyScalar(d)
        if (flyVel.current.lengthSq() < 0.01) flyVel.current.set(0, 0, 0)
      }
      if (flyVel.current.lengthSq() > 0) {
        _mv.copy(flyVel.current).multiplyScalar(dtClamped)
        const ny = camera.position.y + _mv.y
        if (ny < 14 || ny > 4600) {
          _mv.y = 0
          flyVel.current.y = 0
        }
        camera.position.add(_mv)
        if (ctl) { ctl.target.add(_mv); ctl.update() }
      }
      return
    }

    // 巡航期间独占控制相机，禁用 OrbitControls 干扰与夹角约束
    if (ctl) ctl.enabled = false

    // 开场独立时钟：帧间增量累加（而非绝对 elapsedTime）。首帧/编译停顿若用
    // 绝对时钟会一次跳数秒造成前几秒“黑屏/闪跳”；这里单帧钳 0.1s，停顿被涂抹，
    // 正常帧率完全按真实时长推进。
    if (introStart.current === null) {
      introStart.current = 0
    }
    let el: number
    if (INTRO_T_JUMP !== null) {
      el = INTRO_T_JUMP
    } else {
      el = introStart.current
      const dtSafe = delta > 0.5 ? 0.1 : Math.max(delta, 0.001)
      introStart.current += dtSafe
    }
    // 单一全局时间基：整个运镜一阶连续，首尾自然缓入缓出，全程丝滑无顿挫
    const u = ease(Math.min(1, el / INTRO_TOTAL))

    // —— 计算本帧目标机位/朝向/侧倾/fov（先算，再平滑应用）——
    // 复用 _tPos/_tLook（CAMERA_PATH.getPoint 会覆写目标向量，不新建对象）
    let tPos = _tPos
    let tLook = _tLook
    let tFov: number
    if (u >= PATH_FRAC) {
      // —— 收尾环绕：从后侧经西侧绕到叶轮正面 ——
      const e = (u - PATH_FRAC) / (1 - PATH_FRAC)
      const ang = THREE.MathUtils.lerp(ORBIT_A0, ORBIT_A1, e)
      const rad = THREE.MathUtils.lerp(ORBIT_R0, ORBIT_R1, e)
      const hubY = THREE.MathUtils.lerp(92, 96, e)
      tPos.set(HUB.x + Math.cos(ang) * rad, THREE.MathUtils.lerp(ORBIT_Y0, ORBIT_Y1, e), HUB.z + Math.sin(ang) * rad)
      tLook.set(HUB.x, hubY, HUB.z)
      tFov = 47
    } else {
      const progress = u / PATH_FRAC
      CAMERA_PATH.getPoint(progress, tPos)
      LOOK_PATH.getPoint(progress, tLook)
      tFov = THREE.MathUtils.lerp(52, 47, progress)
    }

    // —— 平滑应用：位置/朝向/fov 指数跟随目标 ——
    const alpha = 1 - Math.exp(-Math.min(Math.max(delta, 0.001), 0.25) / CAM_SMOOTH_TAU)
    if (!smInit.current) {
      smPos.current.copy(tPos)
      smLook.current.copy(tLook)
      smFov.current = tFov
      smInit.current = true
    } else {
      smPos.current.lerp(tPos, alpha)
      smLook.current.lerp(tLook, alpha)
      smFov.current += (tFov - smFov.current) * alpha
    }
    camera.position.copy(smPos.current)
    _eLook.lookAt(smPos.current, smLook.current, _eUp)
    _eQuat.setFromRotationMatrix(_eLook)
    camera.quaternion.slerp(_eQuat, alpha)
    const perspective = camera as THREE.PerspectiveCamera
    perspective.fov = smFov.current
    perspective.updateProjectionMatrix()
    const ctlS = controlsRef.current
    if (ctlS) ctlS.target.copy(smLook.current)

    if (el >= INTRO_TOTAL && !useSim.getState().introDone) {
      useSim.getState().skipIntro()
      if (ctl) {
        ctl.enabled = true
        ctl.target.copy(smLook.current)
        // 让 OrbitControls 内部球坐标与当前相机/焦点一致后再启用，避免交接“回弹/跳变”
        ctl.update()
      }
    }
  })

  return null
}
