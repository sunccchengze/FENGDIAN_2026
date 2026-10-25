import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './styles/theme.css'
import { startSimClock, useSim, farmFrameNow } from './state/simStore'
import { snapYawBank } from './core/control/yawDrive'
import { audioEngine } from './audio/audioEngine'
import { pickSourceFromQuery } from './data/telemetry'
import { debugEnabled } from './data/debug'
import { bindFloris3D } from './data/florisData'
import { applyCleanHud } from './data/urlParams'

// FLORIS 三维速度场（真实数据件 135KB）：异步绑定，不阻塞首帧；
// 绑定成功后风纱/流线在覆盖区自动切换为真场采样（florisData.sampleWorldU）
void import('./data/floris3dData.mjs')
  .then((m) => { bindFloris3D(m.default as never) })
  .catch(() => { /* 生产裁剪时静默退回解析尾流场 */ })

// 全局仿真时钟（真实 50s = 模拟 24h）：时间轴真正驱动 HUD 与 3D
startSimClock()
// 遥测源装配：默认 DemoSource（本地确定性）；?ws= 显式开启实时源（v3 接口）
pickSourceFromQuery().start()
// 调试探针（仅 DEV/?debug=1）：供 QA 自动化注入指令、读取 store
if (debugEnabled()) {
  // snapYaw：把偏航执行器瞬移到指令角（稳态取证用；正常界面必须看 0.3°/s 的真实滞后）
  const snapYaw = (cmds?: number[]) => {
    const st = useSim.getState()
    snapYawBank(st.yawBank, cmds ?? st.unitYaw)
    useSim.setState({ actYaw: st.yawBank.states.map((s2) => s2.actual) })
  }
  // audio：声场引擎只读探针（QA 验证 AudioContext 状态 / 声场求值，不可越权改节点）
  ;(window as unknown as Record<string, unknown>).__aeolus = { useSim, farmFrameNow, snapYaw, audio: audioEngine }
  const tq = new URLSearchParams(location.search).get('t')
  if (tq && Number.isFinite(Number(tq))) useSim.setState({ tHours: Number(tq), playing: false })
}

// `?hud=clean` 出片模式：在**首帧之前**就把 <body data-hud-clean> 挂上，
// 否则会在挂载后的一帧里闪出布局/七步/画质按钮，录屏里就是一个可见的跳变。
applyCleanHud(document, location.search)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
