import { Component, Suspense, useState, type ReactNode, useEffect } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { debugEnabled } from './data/debug'
import SkyAurora from './scene/SkyAurora'
import LightRig from './scene/LightRig'
import WorldTerrain from './scene/WorldTerrain'
import TreeField from './scene/treeField'
import NightPulse from './scene/NightPulse'
import SparkleGround from './scene/SparkleGround'
import WindVeil from './scene/WindVeil'
import AirflowField from './scene/AirflowField'
import TurbineField from './scene/TurbineField'
import CableNetwork from './scene/CableNetwork'
import Substation from './scene/Substation'
import Callouts from './scene/Callouts'
import Effects from './scene/Effects'
import EnvSetup from './scene/EnvSetup'
import CameraRig from './scene/CameraRig'
import { ORBIT_MIN_DISTANCE, ORBIT_MAX_DISTANCE, ORBIT_MAX_POLAR_DEG } from './scene/hotkeys.ts'
import PerfGovernor from './scene/PerfGovernor'
import Hud from './hud/Hud'
import AudioField from './audio/AudioField'
import GrassField from './scene/grassField'
import { useSim } from './state/simStore'
import { FREEZE } from './scene/freeze.ts'
import DemoPanel from './demo/DemoPanel.tsx'

// ============================================================================
// 装配壳（v3）
//  · D6：ErrorBoundary（场景崩溃 → 品牌错误屏，不再整页白屏）；
//  · WebGL 上下文丢失 → 捕获、暂停仿真、给出恢复按钮；
//  · 首帧黑屏修复：品牌 Loading 屏在 Canvas onCreated + 首帧后淡出；
//  · 开场巡航期间：任意点击画布 = 跳过（C5）；
//  · dpr 与画质档联动（high ≤2 / medium ≤1.5 / low =1）。
// ============================================================================

class SceneBoundary extends Component<{ children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: unknown) {
    return { err: e instanceof Error ? e.message : String(e) }
  }
  componentDidCatch(e: unknown) {
    console.error('[AEOLUS] scene error', e)
  }
  render() {
    if (this.state.err) {
      return (
        <div className="fatal-screen">
          <div className="fatal-card">
            <h2>渲染层异常</h2>
            <p>{this.state.err}</p>
            <button onClick={() => location.reload()}>重新载入</button>
            <em>AEOLUS TWIN · 错误已隔离在 3D 层，HUD 数值口径不受影响</em>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

// 调试钩子：仅本机（localhost/127.0.0.1）暴露 store，供无头验证与控制台调试；外网构建不生效
if (typeof window !== 'undefined' && /^(localhost|127\.0\.0\.1)$/.test(window.location.hostname)) {
  ;(window as unknown as { __sim: typeof useSim }).__sim = useSim
}

export default function App() {
  // R42 freeze=1 取证模式：CSS 动画全停（配合 JS 相位闸，见 freeze.ts）
  useEffect(() => {
    if (FREEZE) document.body.dataset.freeze = '1'
  }, [])
  const quality = useSim((s) => s.quality)
  const setFatal = useSim((s) => s.setFatal)
  const fatal = useSim((s) => s.fatal)
  const skipIntro = useSim((s) => s.skipIntro)
  const [ready, setReady] = useState(false)

  return (
    <>
      <div
        className="canvas-wrap"
        onPointerDown={() => {
          if (!useSim.getState().introDone) skipIntro()
        }}
      >
        <SceneBoundary>
          <Canvas
            shadows="soft"
            gl={{ antialias: false, powerPreference: 'high-performance', failIfMajorPerformanceCaveat: false }}
            dpr={quality === 'high' ? [1, 1.5] : quality === 'medium' ? [1, 1.25] : [1, 1]}
            camera={{ position: [-100, 1450, 250], fov: 52, near: 1, far: 18000 }}
            onCreated={({ gl, scene, camera }) => {
              gl.toneMapping = THREE.ACESFilmicToneMapping
              gl.toneMappingExposure = 1.14
              scene.fog = new THREE.FogExp2('#040911', 0.00013) // C4：0.00022→0.00013 —— 4500m峰从63%雾洗降到25%，去“大雾”，留空气感
              const canvas = gl.domElement
              canvas.addEventListener('webglcontextlost', (e) => {
                e.preventDefault()
                setFatal('WebGL 上下文丢失（显卡驱动重置或显存不足）。')
              })
              canvas.addEventListener('webglcontextrestored', () => setFatal(null))
              // 首帧后不立即隐藏 Loading：再等一小段预热（3 帧 + 400ms），
              // 让 PMREM/shader 首次编译的停顿发生在 Loading 屏期间，
              // 用户看到的第一眼就是已就绪、直接开跑的开场，不再有“首秒卡死”。
              let warmFrames = 0
              const warmT0 = performance.now()
              const warm = () => {
                warmFrames++
                if (warmFrames >= 2 && performance.now() - warmT0 >= 120) { setReady(true); return }
                requestAnimationFrame(warm)
              }
              requestAnimationFrame(warm)
              if (debugEnabled()) {
                ;(window as unknown as Record<string, unknown>).__aeolus_cam = camera
                ;(window as unknown as Record<string, unknown>).__aeolus_scene = scene
                ;(window as unknown as Record<string, unknown>).__aeolus_stats = () => {
                  // 手动单帧渲染计数（EffectComposer 存在时 gl.info 只反映后期 pass）
                  const prevTone = gl.toneMapping
                  gl.toneMapping = THREE.NoToneMapping
                  gl.info.reset()
                  gl.render(scene, camera)
                  gl.toneMapping = prevTone
                  return {
                    calls: gl.info.render.calls, triangles: gl.info.render.triangles,
                    lines: gl.info.render.lines, geometries: gl.info.memory.geometries,
                    textures: gl.info.memory.textures,
                  }
                }
              }
            }}
          >
            <color attach="background" args={['#010305']} />
            <LightRig />
            <Suspense fallback={null}>
              <EnvSetup />
              <SkyAurora />
              <WorldTerrain />
              <TreeField />
              {/* P1 · T8：草地系统正式挂载（相机跟随分块 + 视距裁决，见 grassField.tsx） */}
              <GrassField />
              <NightPulse />
              <SparkleGround count={4600} />
              <WindVeil />
              <AirflowField />
              <CableNetwork />
              <Substation />
              <TurbineField />
              <Callouts />
            </Suspense>
            <CameraRig />
            <PerfGovernor />
            <OrbitControls
              makeDefault
              maxPolarAngle={THREE.MathUtils.degToRad(ORBIT_MAX_POLAR_DEG)}
              minDistance={ORBIT_MIN_DISTANCE}
              maxDistance={ORBIT_MAX_DISTANCE}
              enableDamping
              dampingFactor={0.035}
              enableZoom
              zoomSpeed={0.7}
              rotateSpeed={0.65}
              panSpeed={0.7}
            />
            <Effects />
          </Canvas>
        </SceneBoundary>
        {!ready && !fatal && (
          <div className="splash">
            <div className="splash-logo">AEOLUS TWIN</div>
            <div className="splash-sub">风电场偏航优化 · 数字孪生系统</div>
            <div className="splash-bar"><i /></div>
            <em>正在装配全息场景 · 零外部请求</em>
          </div>
        )}
        {fatal && (
          <div className="fatal-screen">
            <div className="fatal-card">
              <h2>图形上下文丢失</h2>
              <p>{fatal}</p>
              <button onClick={() => location.reload()}>重新载入</button>
            </div>
          </div>
        )}
      </div>
      <Hud />
      {/* T9 · 声场驱动层（Canvas 之外，rAF + Web Audio 自有时钟：软渲染掉帧不影响声音） */}
      <AudioField />
      {/* R44 · 9.19 §二 七步演示面板（?demo=1；建议配 ?layout=1x3） */}
      {new URLSearchParams(window.location.search).has('demo') && <DemoPanel />}
    </>
  )
}
