import { useRef } from 'react'
import { debugEnabled } from '../data/debug'
import { useFrame, useThree } from '@react-three/fiber'
import { useSim } from '../state/simStore'

// ============================================================================
// 自适应画质调节器（D5 修复与防抖平滑）
// ----------------------------------------------------------------------------
// · 以帧时 EMA 判断 GPU 档位：持续 >26ms 降档，持续 <13ms 且自动模式升档；
// · 降档/升档设置 8 秒冷却期，杜绝临界帧率下的反复切换与 FBO/后处理重建黑屏；
// · 提供 ?q=low|medium|high 手动锁档（QA/低配答辩现场兜底）。
// 目标：1080p 高档 ≥55fps（docs/02 §9 性能预算），软渲染 QA 环境自动落 low。
// ============================================================================

const ORDER = ['low', 'medium', 'high'] as const

export default function PerfGovernor() {
  const { gl } = useThree()
  const ema = useRef(16)
  const acc = useRef(0)
  const lastShiftAt = useRef(0)
  const frozen = useRef(false)
  const introEndAt = useRef(0)
  const lock = useRef<string | null>(
    typeof location !== 'undefined' && debugEnabled()
      ? (new URLSearchParams(location.search).get('q') as 'low' | 'medium' | 'high' | null)
      : null,
  )

  useFrame((_, dt) => {
    if (lock.current) {
      // 锁档一次性生效，并关闭自适应（manual=true → qualityAuto=false）：
      // README 口径是「画质锁定」——此前锁后仍被自动降档覆写，
      // 软渲染 QA 里 ?q=high 会在 ~2s 后跌回 low（R36 树木层 low=0 直接消失）。
      const q = lock.current as 'low' | 'medium' | 'high'
      lock.current = null
      if (ORDER.includes(q)) useSim.getState().setQuality(q, true)
    }
    const d = Math.min(100, dt * 1000)
    ema.current = ema.current * 0.96 + d * 0.04
    acc.current += dt
    if (acc.current < 3) return
    acc.current = 0
    const s = useSim.getState()
    if (!s.qualityAuto) return
    // 开场运镜期间（以及结束后 5s）冻结画质自适应：
    // 首段 shader 编译/PMREM 常见几秒高帧时，若立即 high→medium→low 连续降档，
    // EffectComposer 与 Canvas dpr 会各重建一次，真机上正是“开场两次黑屏”的来源。
    if (!s.introDone || performance.now() - introEndAt.current < 5000) {
      if (!frozen.current && s.introDone) {
        frozen.current = true
        introEndAt.current = performance.now()
      }
      return
    }
    // 切换冷却期保护（至少 8s 防抖，避免频繁重建 WebGL 后处理管线）
    const now = performance.now()
    if (now - lastShiftAt.current < 8000) return

    const cur = ORDER.indexOf(s.quality)
    if (ema.current > 26 && cur > 0) {
      lastShiftAt.current = now
      s.setQuality(ORDER[cur - 1] as 'low' | 'medium' | 'high')
    } else if (ema.current < 13 && cur < 2) {
      lastShiftAt.current = now
      s.setQuality(ORDER[cur + 1] as 'medium' | 'high')
    }
  })

  // dpr 由 App 侧 <Canvas dpr=...> 与 quality 联动（避免与 R3F 的像素比管理打架）
  void gl
  return null
}
