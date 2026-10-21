import { useEffect } from 'react'
import { useSim, farmFrameNow } from '../state/simStore'
import { cameraPos, cameraFwd, cameraUp } from '../scene/cameraBus'
import { audioEngine } from './audioEngine'
import { windAt } from '../data/farmSim'
import { phaseT } from '../scene/freeze.ts'

// ============================================================================
// T9 · AudioField —— 声场驱动层（挂在 Canvas 之外）
// ----------------------------------------------------------------------------
//  · 用 rAF 而不是 R3F 的 useFrame：软渲染/掉帧时画面可以慢，声音不能断；
//    也避免音频调度被 EffectComposer 的长帧拖住（Web Audio 有自己的时钟）；
//  · 每帧读：相机位姿（cameraBus）+ 仿真帧（farmFrameNow，与 HUD/3D 同一帧）；
//  · 未开声（audioOn=false / 无用户手势）时只跑纯函数求值，零节点操作、零开销；
//  · 标签页隐藏 → suspend()，回到前台 → resume()（浏览器省电与自动播放策略）；
//  · 开场巡航期间不发声：introDone 之前声场增益归零（画面还在装配，出声很怪），
//    开场一结束海面底噪淡入 —— 与 splash 淡出同节奏。
// ============================================================================

const _units = new Array<{ x: number; z: number; rpm: number; uEff: number }>(9)
for (let i = 0; i < _units.length; i++) _units[i] = { x: 0, z: 0, rpm: 0, uEff: 0 }

export default function AudioField() {
  // 开声/关声（store → 引擎）。开声走 ensure()：AudioContext 只能在用户手势链里
  // 创建/恢复，这个 effect 由 HUD 按钮点击同步触发，落在手势窗口内。
  const audioOn = useSim((s) => s.audioOn)
  const audioVol = useSim((s) => s.audioVol)
  const introDone = useSim((s) => s.introDone)
  const gesturePending = useSim((s) => s.audioGesturePending)
  useEffect(() => {
    audioEngine.setVolume(audioVol)
    if (!audioOn) {
      audioEngine.mute()
      return
    }
    if (!introDone) return // 开场里：只记账，开场结束由下面那条 effect 补 ensure()
    void audioEngine.ensure().then((ok) => {
      if (!ok && useSim.getState().audioOn) useSim.setState({ audioOn: false })
    })
  }, [audioOn, audioVol, introDone])

  // 开场巡航期间按下过声音按钮 → 开场一结束补一次手势恢复
  useEffect(() => {
    if (!introDone || !audioOn || !gesturePending) return
    useSim.setState({ audioGesturePending: false })
    void audioEngine.ensure().then((ok) => {
      if (!ok && useSim.getState().audioOn) useSim.setState({ audioOn: false })
    })
  }, [introDone, audioOn, gesturePending])

  // 快捷键 M：声场开关（与 CameraRig 的 Esc/1-9 同族；输入框内不抢键）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || (e.key !== 'm' && e.key !== 'M')) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      const st = useSim.getState()
      if (!st.audioOn && !st.introDone) useSim.setState({ audioGesturePending: true })
      st.setAudioOn(!st.audioOn)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    let raf = 0
    let stopped = false

    const onVis = () => {
      if (document.hidden) audioEngine.suspend()
      else audioEngine.resume()
    }
    document.addEventListener('visibilitychange', onVis)

    const loop = () => {
      if (stopped) return
      raf = requestAnimationFrame(loop)
      const s = useSim.getState()
      // 未开声：引擎内部只做纯函数求值（保留 lastFrame 供 HUD 读数），不碰节点
      const t = phaseT(performance.now() / 1000)
      const frame = farmFrameNow()
      const n = Math.min(_units.length, frame.units.length)
      for (let i = 0; i < n; i++) {
        const u = frame.units[i]
        const slot = _units[i]
        slot.x = u.x
        slot.z = u.z
        slot.rpm = u.rpm
        slot.uEff = u.uEff
      }
      // 开场巡航期间整体门控到 0（引擎侧 τ=0.9s 淡入淡出，不硬切）
      audioEngine.setGate(s.introDone ? 1 : 0)
      const w0 = windAt(s.tHours)
      audioEngine.update({
        lx: cameraPos().x,
        ly: cameraPos().y,
        lz: cameraPos().z,
        fx: cameraFwd().x,
        fy: cameraFwd().y,
        fz: cameraFwd().z,
        ux: cameraUp().x,
        uy: cameraUp().y,
        uz: cameraUp().z,
        tHours: s.tHours,
        t,
        windSpeed: w0.u,
        windFromDeg: w0.fromDeg,
        units: _units,
      })
    }
    raf = requestAnimationFrame(loop)

    return () => {
      stopped = true
      cancelAnimationFrame(raf)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  return null
}
