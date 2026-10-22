// ================================================================
// 遥测接入适配层（Telemetry Adapter）
// ----------------------------------------------------------------
// 对应申请书"数据传输协议适配"承诺与 docs/02 §5 数据流设计：
//   TelemetrySource 是数据源接口；默认 DemoSource = 本地确定性仿真
//   （farmSim 直接驱动，无需网络）；WsSource = DTAP(JSON) over
//   WebSocket 的实现骨架，仅当显式传入 ?ws=<url> 时启用。
// 诚实口径：当前站点出厂态 = DemoSource；未连接任何真实 SCADA/OPC。
// v3（2027 阶段五）联调时按此契约实现真实源，HUD/3D 零改动。
// ================================================================

import { useSim } from '../state/simStore'
import { debugEnabled } from './debug'
import { N_UNITS } from './farmSim.ts' // R41-A：DTAP 校验长度 = 场内机组数（docs/13 §4.1）

export interface TelemetryPatch {
  /** 仿真时刻（小时）；提供则 seek */
  tHours?: number
  /** 全场统一的"来风"由本地剖面继续驱动；接入真值时扩展此字段 */
  unitYaw?: number[]
  targetMW?: number
  playing?: boolean
}

export interface TelemetrySource {
  readonly kind: 'demo' | 'ws'
  start(): void
  stop(): void
}

/** 演示源：本地时钟（startSimClock）已驱动状态，这里是无副作用占位 */
export const demoSource: TelemetrySource = {
  kind: 'demo',
  start() {},
  stop() {},
}

export function applyPatch(p: TelemetryPatch): void {
  const s = useSim.getState()
  if (typeof p.tHours === 'number' && Number.isFinite(p.tHours)) s.seek(p.tHours)
  if (typeof p.targetMW === 'number' && Number.isFinite(p.targetMW)) s.setTargetMW(p.targetMW)
  if (Array.isArray(p.unitYaw) && p.unitYaw.length === N_UNITS) {
    p.unitYaw.forEach((v, i) => { if (Number.isFinite(v)) s.setUnitYaw(i, v) })
  }
  if (typeof p.playing === 'boolean' && p.playing !== s.playing) s.togglePlay()
}

/**
 * DTAP over WebSocket 骨架：JSON 行 {tHours?, unitYaw?, targetMW?, playing?}。
 * 校验失败/断线 → 自动回退 DemoSource（不阻塞演示，零后端红线）。
 */
export function createWsSource(url: string, onError?: (m: string) => void): TelemetrySource {
  let ws: WebSocket | null = null
  return {
    kind: 'ws',
    start() {
      try {
        ws = new WebSocket(url)
        ws.onmessage = (ev) => {
          try {
            const p = JSON.parse(String(ev.data)) as TelemetryPatch
            applyPatch(p)
          } catch {
            onError?.('DTAP 帧格式不合法，已忽略')
          }
        }
        ws.onclose = () => { onError?.('遥测断线，回退演示数据'); ws = null }
        ws.onerror = () => { onError?.('遥测不可达，回退演示数据') }
      } catch {
        onError?.('遥测初始化失败，回退演示数据')
      }
    },
    stop() {
      ws?.close()
      ws = null
    },
  }
}

/** 站点装配入口：默认 demo；?ws= 显式开启实时源。
 *  安全闸（AUD-10）：?ws= 仅在调试模式（DEV 或 ?debug=1）下生效，且地址必须能
 *  解析为 ws:/wss:——否则任何人发一条带 ?ws= 的链接即可遥控打开者的界面。
 *  将来接入真实遥测时应改为部署期配置的同源 wss 地址，而非 URL 参数。 */
export function pickSourceFromQuery(): TelemetrySource {
  if (typeof location !== 'undefined') {
    const u = new URLSearchParams(location.search).get('ws')
    if (u && debugEnabled()) {
      let protoOk = false
      try {
        const p = new URL(u).protocol
        protoOk = p === 'ws:' || p === 'wss:'
      } catch {
        protoOk = false
      }
      if (protoOk) {
        console.info('[AEOLUS] 遥测源 = WebSocket', u, '（接口为 v3 DTAP 骨架，字段见 TelemetryPatch）')
        return createWsSource(u, (m) => console.warn('[AEOLUS telemetry]', m))
      }
      console.warn('[AEOLUS telemetry] ?ws= 地址不是合法的 ws:/wss: URL，已忽略，回退演示数据')
    } else if (u) {
      console.warn('[AEOLUS telemetry] ?ws= 仅在 ?debug=1（或 DEV 构建）下生效，已回退演示数据')
    }
  }
  return demoSource
}
