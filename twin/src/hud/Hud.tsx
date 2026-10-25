import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useSim, useFarmFrame } from '../state/simStore'
import { FARM } from '../scene/terrainUtil'
import { UNIT_NAMEPLATE, FARM_RATED_MW, N_UNITS } from '../data/farmSim'
import {
  LAYOUT, LAYOUTS, ACTIVE_LAYOUT, switchLayoutHref, type LayoutId,
} from '../scene/layouts.ts'
import { demoHref, isDemoOpen } from '../data/urlParams.ts' // R41-A：矩阵/滑杆口径派生自布局真值源；2026-10-25 起兼顶栏布局切换
import { FREEZE } from '../scene/freeze.ts' // R42：freeze 取证模式挂钟定格
import { ROTOR_D, WAKE_K, wakeDeflection, yawFactor } from '../data/turbinePhysics'
import { anomalyLabel } from '../data/anomaly'
import {
  YAW_RATE_DPS, YAW_DEADBAND_DEG, YAW_STOP_BAND_DEG, yawEtaFrom,
} from '../core/control/yawDrive'

// ================================================================
// 未来能源数字孪生系统 —— 大屏 HUD（v3：全读数接演示数据契约）
// ----------------------------------------------------------------
// docs/07 A1/A2/A3/A5 + docs/08 P0 的落地点：
//  · 无任何组件级硬编码读数：功率/频率/无功/环/矩阵/雷达/曲线/告警
//    全部来自 useFarmFrame()（farmSim 纯函数），互相不可能再穿帮；
//  · 时间轴驱动数据、偏航滑杆驱动功率与告警（闭环）；
//  · 术语订正 + 单位齐全 + 三级证据角标：【演示】=确定性演示数据、
//    【代理】=Jensen/双线性代理推算、【示意】=可视化皮肤/构图。
// ================================================================

const SIZE = { w: 1920, h: 1080 }

function useStageScale() {
  const [dim, setDim] = useState({ scale: 1, h: SIZE.h })
  useEffect(() => {
    // 宽度 1920 定标；设计高度随屏幕比例伸展（16:10→1200）——
    // 消除旧版 min() 等比锁死导致的上下黑边与"底部被时间条遮挡"
    const onR = () => {
      const sc = window.innerWidth / SIZE.w
      setDim({ scale: sc, h: Math.max(940, Math.round(window.innerHeight / sc)) })
    }
    onR()
    window.addEventListener('resize', onR)
    return () => window.removeEventListener('resize', onR)
  }, [])
  return dim
}

const f1 = (v: number) => v.toFixed(1)
const f2 = (v: number) => v.toFixed(2)
const intFmt = (v: number) => Math.round(v).toLocaleString('en-US')

/* ---------- 证据角标 ---------- */
const Badge = ({ k }: { k: '演示' | '代理' | '示意' }) => <span className={`evb evb-${k === '演示' ? 'd' : k === '代理' ? 'p' : 's'}`}>{k}</span>

/* ---------- 通用面板 ---------- */
function Panel({ title, en, badge, children, tall, cls }: { title: string; en?: string; badge?: '演示' | '代理' | '示意'; children: ReactNode; tall?: boolean; cls?: string }) {
  return (
    <section className={`panel${tall ? ' tall' : ''}${cls ? ` ${cls}` : ''}`}>
      <i className="c tl" /><i className="c tr" /><i className="c bl" /><i className="c br" />
      <i className="notch" />
      <header className="ptitle">
        <i className="sicon" />
        <span className="zh">{title}</span>
        {en && <span className="en">{en}</span>}
        {badge && <Badge k={badge} />}
      </header>
      <div className="pbody">{children}</div>
    </section>
  )
}

/* ---------- 运行指标三环 ---------- */
function MetricDonut({ pct, label, sub, display }: { pct: number; label: string; sub?: string; display?: string }) {
  const r = 24, c = 2 * Math.PI * r
  const p = Math.max(0, Math.min(100, pct))
  return (
    <div className="donut">
      <svg width="74" height="74" viewBox="0 0 74 74" role="img" aria-label={`${label} ${display ?? p.toFixed(0) + '%'}`}>
        <defs>
          <linearGradient id="ndGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#8fe9ff" />
            <stop offset="1" stopColor="#3d8fc0" />
          </linearGradient>
        </defs>
        <circle cx="37" cy="37" r={r} fill="rgba(8,26,40,.6)" stroke="rgba(70,130,170,.4)" strokeWidth="6" />
        <circle cx="37" cy="37" r={r} fill="none" stroke="url(#ndGrad)" strokeWidth="6"
          strokeDasharray={`${(p / 100) * c} ${c}`} strokeLinecap="butt"
          transform="rotate(-90 37 37)" className="ring-glow" />
        <text x="37" y="41" textAnchor="middle" className="donut-num">{display ?? `${p.toFixed(0)}%`}</text>
      </svg>
      <div className="dl">{label}</div>
      {sub && <div className="dsl">{sub}</div>}
    </div>
  )
}

/* ---------- 机组状态矩阵（列数随布局：3×3 三列 / 1×3 竖排，R41-A 派生）---------- */
function Matrix() {
  const frame = useFarmFrame()
  const selected = useSim((s) => s.selected)
  const setSelected = useSim((s) => s.setSelected)
  return (
    <div className={`matrix layout-${LAYOUT.id}`} role="grid" aria-label={`机组状态矩阵 ${LAYOUT.label}`}>
      {frame.units.map((u, i) => (
        <button
          key={u.id}
          role="gridcell"
          aria-label={`${u.id} ${u.status === 'alarm' ? '告警' : u.status === 'curtail' ? '限功率' : u.status === 'idle' ? '待机' : '运行'}`}
          className={`m s-${u.status}${selected === i ? ' sel' : ''}`}
          onClick={() => setSelected(selected === i ? null : i)}
        >
          <i className={`dot d-${u.status}`} />
          <span className="mid">{u.id}</span>
          <span className="mw">{(u.powerKw / 1000).toFixed(1)}</span>
        </button>
      ))}
    </div>
  )
}

/* ---------- 风况雷达（用户定案：雷达扫描制，撤风玫瑰；数据同源） ---------- */
const DIRS16 = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

function Radar() {
  const frame = useFarmFrame()
  // P2：雷达尾流走廊画【实际偏航】（与 AirflowField 烟羽、farmSim GCH 同源）
  const actYaw = useSim((st) => st.actYaw)
  const airflow = useSim((st) => st.airflow)
  const setAirflow = useSim((st) => st.setAirflow)
  const C = 118, R = 96
  const cx = FARM.reduce((a, f) => a + f.x, 0) / FARM.length
  const cz = FARM.reduce((a, f) => a + f.z, 0) / FARM.length
  const S = (R - 12) / 1150 // 场域缩比：±1150m → 雷达盘
  const fromDeg = ((frame.windFromDeg % 360) + 360) % 360
  const th = (fromDeg * Math.PI) / 180
  const fx = Math.sin(th), fz = Math.cos(th) // 风的去向（水平面）
  const domI = Math.floor((fromDeg + 11.25) / 22.5) % 16
  const blips = FARM.map((f, i) => {
    const u = frame.units[i]
    const px = C + (f.x - cx) * S
    const py = C + (f.z - cz) * S
    const p = u ? Math.max(0, Math.min(1, u.powerKw / 5000)) : 0
    // BUG-FIX：走廊须用对风偏差（与 wakeDeficit / AirflowField 同源），非指令角
    // Δψ = 实际偏航偏差（指令与实际之间的滞后在雷达上同样可见）
    const yaw = actYaw[i] ?? 0
    // 尾流走廊：与 3D 粒子同一套 Jensen 扩张+偏航偏折公式（同源）
    const edge = (sgn: 1 | -1) => {
      const pts: string[] = []
      for (let j = 0; j <= 8; j++) {
        const x = 40 + j * 108
        const half = (ROTOR_D / 2 + WAKE_K * x) * S
        const off = wakeDeflection(yaw, x) * S
        pts.push(`${(px + fx * x * S + (fz * (off + half * sgn))).toFixed(1)},${(py + fz * x * S + (-fx * (off + half * sgn))).toFixed(1)}`)
      }
      return pts
    }
    const poly = [...edge(1), ...edge(-1).reverse()].join(' ')
    return (
      <g key={f.id}>
        <polygon points={poly} fill="rgba(130,225,255,.09)" stroke="rgba(150,235,255,.32)" strokeWidth="0.5" />
        <circle cx={px} cy={py} r={3.1 + 5.4 * p} fill="none" stroke="rgba(190,240,255,.9)" strokeWidth="1.1" opacity={0.28 + 0.62 * p} />
        <circle cx={px} cy={py} r="1.7" fill="#d9f4ff" />
      </g>
    )
  })
  return (
    <div className="radar">
      <svg className="radar-svg" width="236" height="236" viewBox="0 0 236 236" role="img"
        aria-label={`风况雷达：风速 ${f1(frame.windSpeed)} 米每秒，来流方位 ${Math.round(fromDeg)} 度（${DIRS16[domI]}），亮环为机组功率，走廊为尾流偏折`}>
        <defs>
          <radialGradient id="radarBg" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(18,64,102,.5)" />
            <stop offset="72%" stopColor="rgba(8,30,50,.38)" />
            <stop offset="100%" stopColor="rgba(4,16,28,.05)" />
          </radialGradient>
          <linearGradient id="sweepG" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="rgba(150,235,255,.34)" />
            <stop offset="100%" stopColor="rgba(150,235,255,0)" />
          </linearGradient>
        </defs>
        <circle cx={C} cy={C} r={R + 9} fill="url(#radarBg)" stroke="rgba(110,215,255,.34)" strokeWidth="1" />
        {[0.36, 0.68, 1].map((f) => (
          <circle key={f} cx={C} cy={C} r={R * f} fill="none" stroke="rgba(110,215,255,.2)" strokeWidth="0.7" />
        ))}
        <line x1={C - R} y1={C} x2={C + R} y2={C} stroke="rgba(120,210,250,.12)" strokeWidth="0.6" />
        <line x1={C} y1={C - R} x2={C} y2={C + R} stroke="rgba(120,210,250,.12)" strokeWidth="0.6" />
        {/* 扫描束（示意） */}
        <g className="sweep">
          <path d={`M${C},${C} L${C},${C - R} A${R},${R} 0 0 1 ${C + R * 0.5},${C - R * 0.866} Z`} fill="url(#sweepG)" />
          <line x1={C} y1={C} x2={C} y2={C - R} stroke="rgba(190,246,255,.8)" strokeWidth="1.3" />
        </g>
        {blips}
        <g className="windvec">
          <line x1={C - fx * (R + 9)} y1={C - fz * (R + 9)} x2={C} y2={C} stroke="#c9f2ff" strokeWidth="1.5" />
          <path d={`M${C},${C} l${-fx * 11 + fz * 5.4},${-fz * 11 - fx * 5.4} M${C},${C} l${-fx * 11 - fz * 5.4},${-fz * 11 + fx * 5.4}`} stroke="#c9f2ff" strokeWidth="1.5" fill="none" />
        </g>
        <circle cx={C} cy={C} r={2.5} fill="#bfefff" />
        <text x={C} y={11} fontSize="9" fill="#8fc6e4" textAnchor="middle">N</text>
        <text x={C + 4} y={C - R * 0.36 + 9} fontSize="7" fill="#54819f">400m</text>
        <text x={C + 4} y={C - R * 0.68 + 9} fontSize="7" fill="#54819f">800m</text>
      </svg>
      <div className="radar-readout">
        <b>{f1(frame.windSpeed)} m/s</b>
        <span>来流方位 {intFmt(fromDeg)}° · {DIRS16[domI]} · 尾流损失 {intFmt(frame.wakeLossPct)}%</span>
        <em>亮环=机组功率 · 走廊=尾流（随偏航扭曲）· 扫描束为示意</em>
      </div>
      <button type="button" className={`btn ghost sm airflow-btn${airflow ? ' on' : ''}`} onClick={() => setAirflow(!airflow)} aria-pressed={airflow}>
        三维气流场：{airflow ? '开' : '关'}
      </button>
    </div>
  )
}

/* ---------- 实时功率曲线（数据契约驱动 + 时间游标） ---------- */
function PowerChart() {
  const frame = useFarmFrame()
  const W = 640, H = 104, ML = 40, MR = 14, MT = 10, MB = 20
  const xs = (i: number) => ML + (i / 47) * (W - ML - MR)
  const ys = (v: number) => MT + (1 - v / FARM_RATED_MW) * (H - MT - MB)
  const { line, area } = useMemo(() => {
    const mk = (arr: number[]) => arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(' ')
    const l = mk(frame.daySeries)
    return { line: l, area: `${l} L${xs(47).toFixed(1)},${ys(0).toFixed(1)} L${xs(0).toFixed(1)},${ys(0).toFixed(1)} Z` }
  }, [frame])
  const fcLine = useMemo(() => frame.fcSeries.map((v, i) => `${i === 0 ? 'M' : 'L'}${xs(i).toFixed(1)},${ys(Math.max(v, frame.daySeries[i]) + 0.6).toFixed(1)}`).join(' '), [frame])
  // 对风基准（γ=0、不限功率）：与实线同轴画，直观展示"偏航+限电"的净效果
  const baseLine = useMemo(() => frame.baseSeries.map((v, i) => `${i === 0 ? 'M' : 'L'}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(' '), [frame])
  const ci = (frame.tHours / 24) * 47
  return (
    <div className="chart">
      <div className="legend">
        <span className="k act" />Actual（代理推算）
        <span className="k base" />对风基准 γ=0
        <span className="k fc" />Forecast +2h
      </div>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="pgrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="rgba(90,215,255,.34)" />
            <stop offset="1" stopColor="rgba(90,215,255,.02)" />
          </linearGradient>
        </defs>
        {[0, 10, 20, 30, 40].map((v) => (
          <g key={v}>
            <line x1={ML} x2={W - MR} y1={ys(v)} y2={ys(v)} stroke="rgba(100,175,215,.12)" strokeWidth="0.7" />
            <text x={ML - 4} y={ys(v) + 3} fontSize="8.5" fill="#5f8db0" textAnchor="end">{v}</text>
          </g>
        ))}
        {[0, 8, 12, 16, 20, 24].map((h) => (
          <text key={h} x={ML + (h / 24) * (W - ML - MR)} y={H - 9} fontSize="8.5" fill="#5f8db0" textAnchor="middle">{h === 0 ? '0' : `${h}:00`}</text>
        ))}
        <text x={5} y={MT + 26} fontSize="9" fill="#7096b4">Power (MW)</text>
        <path d={area} fill="url(#pgrad)" />
        <path d={line} fill="none" stroke="#66dcff" strokeWidth="1.8" className="chart-glow" />
        <path d={baseLine} fill="none" stroke="rgba(150,205,240,.42)" strokeWidth="1" strokeDasharray="1.5 2.5" />
        <path d={fcLine} fill="none" stroke="rgba(190,235,255,.5)" strokeWidth="1.1" strokeDasharray="4 3" />
        <line x1={xs(Math.floor(ci))} x2={xs(Math.floor(ci))} y1={MT} y2={H - MB} stroke="rgba(200,240,255,.35)" strokeWidth="0.8" strokeDasharray="2 2" />
        <circle cx={xs(Math.min(47, ci))} cy={ys(frame.daySeries[Math.min(47, Math.round(ci))])} r="3.2" fill="#dff6ff" className="chart-glow" />
      </svg>
    </div>
  )
}

/* ---------- 偏航执行器滑杆（联动 3D + 功率 + 告警） ---------- */
function ServoSlider({ i }: { i: number }) {
  const unitYaw = useSim((s) => s.unitYaw)
  const setUnitYaw = useSim((s) => s.setUnitYaw)
  // P2 · 执行器实况：实际角 / 速率 / 是否在转（10Hz 轮询，与仿真时钟同节拍）
  const act = useActuator(i)
  const uid = FARM[i]?.id ?? '-'
  const v = unitYaw[i] ?? 0
  const err = v - act.actual
  const inDeadband = !act.slewing && Math.abs(err) <= YAW_DEADBAND_DEG
  const eta = yawEtaFrom(v, act.actual)
  return (
    <div className="srow">
      <span className="slab">偏航执行器{i + 1}<em>→ {uid}</em></span>
      <div className="track">
        <input
          type="range" min={-30} max={30} step={0.5} value={v}
          aria-label={`偏航执行器 ${i + 1} 指令，控制机组 ${uid}`}
          aria-valuetext={`指令 ${v.toFixed(1)} 度，实际 ${act.actual.toFixed(1)} 度`}
          onChange={(e) => setUnitYaw(i, Number(e.target.value))}
          onDoubleClick={() => setUnitYaw(i, 0)}
          title={`拖动下发偏航指令；双击复位 0°。执行器按 ${YAW_RATE_DPS}°/s 速率限制 + ±${YAW_DEADBAND_DEG}° 死区跟踪（P2）`}
          style={{ ['--p' as string]: `${((v + 30) / 60) * 100}%` }}
        />
        <div className="trk">
          <i className="fill" style={{ width: `${((v + 30) / 60) * 100}%` }} />
          {/* 实际角游标：指令与实际之间的滞后一眼可见 */}
          <i className={`act${act.slewing ? ' moving' : ''}`} style={{ left: `${((act.actual + 30) / 60) * 100}%` }} />
          <i className="head" style={{ left: `${((v + 30) / 60) * 100}%` }} />
        </div>
      </div>
      <span className="sval" title={inDeadband
        ? `指令偏差 ${err >= 0 ? '+' : ''}${err.toFixed(1)}° 落在 ±${YAW_DEADBAND_DEG}° 死区内：偏航电机按设计不启停`
        : act.slewing
          ? `偏航中 ${act.rate >= 0 ? '+' : ''}${act.rate.toFixed(2)}°/s · 剩余 ${Math.abs(err).toFixed(1)}° · 约 ${eta.toFixed(0)} s 到位`
          : `到位残差 ${err >= 0 ? '+' : ''}${err.toFixed(1)}°（停机带 ±${YAW_STOP_BAND_DEG}°）`}>
        {Math.abs(v) < 0.05 ? '0°' : `${v > 0 ? '+' : ''}${v.toFixed(1)}°`}
        <em className={act.slewing ? 'dpsi-slew' : Math.abs(v) < 0.05 ? 'dpsi-zero' : 'dpsi-off'}>
          {act.slewing ? `↻ ${act.actual >= 0 ? '+' : ''}${act.actual.toFixed(1)}°` : `Δψ ${act.actual >= 0 ? '+' : ''}${act.actual.toFixed(1)}°`}
        </em>
      </span>
    </div>
  )
}

/** 执行器实况轮询（10Hz，与 startSimClock 同节拍；只在有变化时 setState） */
function useActuator(i: number): { actual: number; rate: number; slewing: boolean; cycles: number } {
  const [a, setA] = useState(() => ({ actual: 0, rate: 0, slewing: false, cycles: 0 }))
  useEffect(() => {
    const iv = setInterval(() => {
      const st = useSim.getState().yawBank.states[i]
      if (!st) return
      const n = { actual: st.actual, rate: st.rate, slewing: st.slewing, cycles: st.cycles }
      setA((p) =>
        Math.abs(p.actual - n.actual) < 0.05 && p.slewing === n.slewing && p.cycles === n.cycles ? p : n,
      )
    }, 100)
    return () => clearInterval(iv)
  }, [i])
  return a
}

/* ---------- T9 · 声场控制（海浪 / 碎浪 / 风机切风 · 程序化 Web Audio） ----------
   组件只写 store；AudioContext 的创建/恢复/静音全在 AudioField 的 effect 里
   （由本按钮的点击同步触发 → 仍落在浏览器要求的用户手势链内）。 */
function SoundControl() {
  const audioOn = useSim((s) => s.audioOn)
  const setAudioOn = useSim((s) => s.setAudioOn)
  const vol = useSim((s) => s.audioVol)
  const setAudioVol = useSim((s) => s.setAudioVol)
  const introDone = useSim((s) => s.introDone)
  const gesturePending = useSim((s) => s.audioGesturePending)

  const toggle = () => {
    if (!audioOn && !introDone) useSim.setState({ audioGesturePending: true })
    setAudioOn(!audioOn)
  }

  return (
    <div className="sound" title="程序化声场（Web Audio · 零外部音频资产）：涌浪底噪随浪高起伏 / 贴岸加拍岸碎浪 / 风机切风随转速与距离调制 + 传动链音调，HRTF 3D 定位 · 快捷键 M">
      <span>声场</span>
      <button
        type="button" className={audioOn ? 'on' : ''} onClick={toggle}
        aria-pressed={audioOn} aria-label={audioOn ? '关闭声场（M）' : '开启声场（M）'}
      >
        {audioOn ? '♪ 开' : '♪ 关'}
      </button>
      <input
        type="range" min={0} max={100} step={1} value={Math.round(vol * 100)}
        disabled={!audioOn} aria-label="声场音量"
        onChange={(e) => setAudioVol(Number(e.target.value) / 100)}
      />
      {audioOn && gesturePending && !introDone && <i className="sndwarn">开场结束后自动开声</i>}
    </div>
  )
}

/* ---------- 布局切换（2026-10-25 解冻新增）：3×3 ↔ 1×3 串列 ----------
   为什么是整页导航而不是热切换：`ACTIVE_LAYOUT / LAYOUT / FARM / CAM_HOTKEYS`
   都是模块加载时定死的几何真值（整棵场景图、机位表、集电回路、告警引擎都按它建模），
   热切换等于把 9 个消费者全改成响应式并重建场景，收益不抵风险（见 README §布局切换）。
   这里只换 URL 的 `layout` 一个参数再导航，其余参数（demo / step / q …）原样带走，
   所以「七步演示面板开着时点切换」不会把演示丢掉。 */
function LayoutSwitch() {
  const [pending, setPending] = useState<LayoutId | null>(null)
  const ids: LayoutId[] = ['3x3', '1x3']
  const go = (id: LayoutId) => {
    if (id === ACTIVE_LAYOUT || pending) return
    setPending(id)
    window.location.assign(switchLayoutHref(window.location.href, id))
  }
  return (
    <div
      className="layoutsw"
      role="group"
      aria-label={`当前布局：${LAYOUT.label}（可切换）`}
      title={`布局切换：3×3 阵列（9 台）↔ 1×3 串列（3 台）。当前 ${LAYOUT.label}。两套几何的功率数字不可混用`}
    >
      <span>布局</span>
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          className={ACTIVE_LAYOUT === id ? 'on' : ''}
          aria-pressed={ACTIVE_LAYOUT === id}
          aria-label={`切换到 ${LAYOUTS[id].label}`}
          disabled={pending !== null}
          onClick={() => go(id)}
        >
          {pending === id ? '…' : id === '3x3' ? '3×3' : '1×3'}
        </button>
      ))}
    </div>
  )
}

/* ---------- 七步演示面板入口（2026-10-25 解冻补：之前只能手打 ?demo=1） ----------
   打开时同时确保 layout=1x3（演示数据只对三机串列成立）；关闭时只删 demo，
   不动 layout —— 用户可能正用 1×3 看三机，不该被顺手切回九机。 */
function DemoSwitch() {
  const [pending, setPending] = useState(false)
  const open = isDemoOpen(typeof location === 'undefined' ? null : location.search)
  const go = () => {
    if (pending) return
    setPending(true)
    window.location.assign(demoHref(window.location.href, !open))
  }
  return (
    <div className="demosw" role="group" aria-label={open ? '七步演示已打开' : '打开七步演示'}>
      <span>看板</span>
      <button
        type="button"
        className={open ? 'on' : ''}
        aria-pressed={open}
        disabled={pending}
        title={open
          ? '关闭七步演示面板（回到常规 HUD；布局不变）'
          : '打开七步演示面板：选工况 → 查基准 → 调航向 → 求解 → 复核 → 可靠性 → 导出（自动切到 1×3 三机串列）'}
        onClick={go}
      >
        {pending ? '…' : open ? '七步 · 关' : '七步 · 开'}
      </button>
    </div>
  )
}

/* ---------- 告警通知（引擎驱动，含定位与确认） ---------- */
function Alarms() {
  const frame = useFarmFrame()
  const acked = useSim((s) => s.ackedAlarms)
  const ackAlarm = useSim((s) => s.ackAlarm)
  const setSelected = useSim((s) => s.setSelected)
  const list = frame.alarms.filter((a) => !acked.includes(a.key))
  if (list.length === 0) {
    return (
      <div className="alist">
        <div className="aempty"><i className="adot ok" />全场无活动告警（阈值引擎每 10 模拟分钟扫描一次）</div>
      </div>
    )
  }
  return (
    <div className="alist">
      {list.map((a) => (
        <div key={a.key} className={`ait lv-${a.level}`}>
          <i className={`adot ${a.level === 'crit' ? 'red' : 'cyan'}`} />
          <div className="atext">
            <b>{a.zh}</b>
            <em>{a.en}{a.tid ? ` · ${a.tid}` : ''} · {a.part}</em>
          </div>
          <span className="atime">{a.minutesAgo <= 1 ? '刚刚' : `${a.minutesAgo}分钟前`}</span>
          {a.tid && (
            <button className="afind" onClick={() => {
              const idx = FARM.findIndex((f) => f.id === a.tid)
              if (idx >= 0) setSelected(idx)
            }}>定位</button>
          )}
          <button className="aack" onClick={() => ackAlarm(a.key)} aria-label="确认告警">✓</button>
        </div>
      ))}
    </div>
  )
}

/* ---------- 单机信息卡（选中机组时出现） ---------- */
/** 偏航执行器读数块（P2）：指令 → 实际的滞后、速率、死区状态、余弦损失。
 *  放在卡片子组件里，保证 hook 不在 TurbineCard 的提前 return 之后调用。 */
function ActuatorRows({ i, cmd }: { i: number; cmd: number }) {
  const act = useActuator(i)
  const eta = yawEtaFrom(cmd, act.actual)
  const err = cmd - act.actual
  const cosLoss = (1 - yawFactor(act.actual)) * 100
  return (
    <>
      <label>偏航执行器</label>
      <span>
        指令 {cmd >= 0 ? '+' : ''}{f1(cmd)}° → 实际 {act.actual >= 0 ? '+' : ''}{f1(act.actual)}° ·{' '}
        {act.slewing
          ? `偏航中 ${act.rate >= 0 ? '+' : ''}${f2(act.rate)}°/s · 约 ${eta.toFixed(0)} s 到位`
          : Math.abs(err) <= YAW_DEADBAND_DEG
            ? `死区保持 ±${YAW_DEADBAND_DEG}°（电机不启停）`
            : '已到位抱闸'}
        <Badge k="代理" />
      </span>
      <label>偏航代价</label>
      <span>余弦损失 {f2(cosLoss)}%（cos^1.88）· 本次起动累计 {act.cycles} 次</span>
    </>
  )
}

function TurbineCardBody({ i }: { i: number }) {
  const setSelected = useSim((s) => s.setSelected)
  const cmd = useSim((s) => s.unitYaw[i] ?? 0)
  const frame = useFarmFrame()
  const u = frame.units[i]
  if (!u) return null
  return (
    <div className="tcard" role="dialog" aria-label={`${u.id} 机组信息卡`}>
      <header>
        <b>{u.id}</b>
        <span>{UNIT_NAMEPLATE.model}</span>
        <button onClick={() => setSelected(null)} aria-label="关闭">✕</button>
      </header>
      <div className="tgrid">
        <label>状态</label><i className={`st s-${u.status}`}>{u.status === 'alarm' ? '告警' : u.status === 'curtail' ? '限功率' : u.status === 'idle' ? '待机' : '运行'}</i>
        <label>有功功率</label><span>{intFmt(u.powerKw)} kW / {intFmt(UNIT_NAMEPLATE.ratedKw)} kW<Badge k="代理" /></span>
        <label>偏航角</label><span>{f1(u.yawDeg)}°（实际对风偏差 {f1(u.yawErrDeg)}°，来自执行器）<Badge k="代理" /></span>
        <ActuatorRows i={i} cmd={cmd} />
        <label>转子转速</label><span>{f2(u.rpm)} rpm</span>
        <label>来流风速</label><span>{f1(u.uEff)} m/s（自由流 {f1(u.uFree)}）</span>
        <label>尾流损失</label><span>{f1(u.wakeLossPct)}%</span>
        <label>发电机温度</label><span>{intFmt(u.tempC)} °C</span>
        <label>机组坐标</label><span>x {u.x.toFixed(0)} · z {u.z.toFixed(0)} m<Badge k="示意" /></span>
      </div>
    </div>
  )
}

function TurbineCard() {
  const selected = useSim((s) => s.selected)
  if (selected === null) return null
  return <TurbineCardBody i={selected} />
}

/* ---------- 顶部标题装饰 ---------- */
function Wings({ flip }: { flip?: boolean }) {
  return (
    <svg className={`wings${flip ? ' flip' : ''}`} viewBox="0 0 380 44" width="380" height="44" aria-hidden="true">
      <defs>
        <linearGradient id="wg" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="rgba(130,220,255,.9)" />
          <stop offset="1" stopColor="rgba(70,160,220,.35)" />
        </linearGradient>
      </defs>
      <g fill="none" stroke="url(#wg)" strokeWidth="1.6">
        <path d="M4 36 L104 36 L136 14 L214 14 L250 30 L376 30" />
        <path d="M14 41 L110 41 L140 21 L210 21 L244 36 L370 36" stroke="rgba(110,200,250,.35)" strokeWidth="1" />
      </g>
      {[64, 84, 130, 172, 190, 230, 262, 300, 340].map((x, i) => (
        <line key={i} x1={x} y1={i % 2 ? 36 : 16} x2={x} y2={(i % 2 ? 36 : 16) + (i % 2 ? -10 : 10)} stroke="rgba(150,225,255,.55)" strokeWidth="1" />
      ))}
      {[[106, 36], [138, 14], [250, 30]].map(([x, y], i) => (
        <rect key={i} x={x - 3.2} y={y - 3.2} width="6.4" height="6.4" fill="rgba(170,235,255,.95)" transform={`rotate(45 ${x} ${y})`} />
      ))}
    </svg>
  )
}

function CornerWings({ flip }: { flip?: boolean }) {
  return (
    <svg className={`cwings${flip ? ' flip' : ''}`} viewBox="0 0 340 64" width="340" height="64" aria-hidden="true">
      <defs>
        <linearGradient id="cwg" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="rgba(160,235,255,.95)" />
          <stop offset="1" stopColor="rgba(70,150,210,.2)" />
        </linearGradient>
      </defs>
      <g fill="none" stroke="url(#cwg)" strokeWidth="1.8">
        <path d="M0 44 L96 44 L118 22 L196 22 L232 40 L340 40" />
        <path d="M8 52 L102 52 L126 32 L198 32 L238 48 L334 48" stroke="rgba(120,205,250,.35)" strokeWidth="1.2" />
        <path d="M16 60 L108 60 L134 42 L202 42 L244 56 L326 56" stroke="rgba(120,205,250,.2)" strokeWidth="1" />
      </g>
      {[96, 120, 232, 258, 300].map((x, i) => (
        <line key={i} x1={x} y1={i % 2 ? 30 : 46} x2={x} y2={(i % 2 ? 30 : 46) + (i % 2 ? 10 : -8)} stroke="rgba(160,230,255,.6)" strokeWidth="1.2" />
      ))}
      {[[104, 44], [200, 32]].map(([x, y], i) => (
        <rect key={i} x={x - 3} y={y - 3} width="6" height="6" fill="rgba(180,240,255,.95)" transform={`rotate(45 ${x} ${y})`} />
      ))}
    </svg>
  )
}

/* ---------- 控制控制台（目标功率闭环 + 寻优） ---------- */
function ControlConsole() {
  const targetMW = useSim((s) => s.targetMW)
  const setTargetMW = useSim((s) => s.setTargetMW)
  const runOptimize = useSim((s) => s.runOptimize)
  const resetYaw = useSim((s) => s.resetYaw)
  const note = useSim((s) => s.optimizeNote)
  return (
    <div className="console">
      <div className="srow">
        <span className="slab">需求功率<em>{targetMW >= FARM_RATED_MW ? '不限' : `${f1(targetMW)} MW`}</em></span>
        <div className="track">
          <input
            type="range" min={4} max={FARM_RATED_MW} step={0.5} value={targetMW}
            aria-label="需求功率目标"
            aria-valuetext={`${f1(targetMW)} 兆瓦`}
            onChange={(e) => setTargetMW(Number(e.target.value))}
            style={{ ['--p' as string]: `${((targetMW - 4) / (FARM_RATED_MW - 4)) * 100}%` }}
          />
          <div className="trk"><i className="fill" style={{ width: `${((targetMW - 4) / (FARM_RATED_MW - 4)) * 100}%` }} /><i className="head" style={{ left: `${((targetMW - 4) / (FARM_RATED_MW - 4)) * 100}%` }} /></div>
        </div>
        <span className="sval" title="需求功率/装机容量的指令比">{f1((targetMW / FARM_RATED_MW) * 100)}%</span>
      </div>
      <div className="cbtns">
        <button className="cbtn primary" onClick={runOptimize} title="按 Jensen 代理模型逐排寻优各机偏航角（研究内容③：功率输入→偏航输出）">
          下发偏航寻优 <Badge k="代理" />
        </button>
        <button className="cbtn" onClick={resetYaw}>复位对风 0°</button>
      </div>
      {note && <div className="cnote">{note}</div>}
    </div>
  )
}

/* 对风基准偏差 + 平均转速（与图表基准曲线同一口径） */
function KpiDelta({ frame }: { frame: ReturnType<typeof useFarmFrame> }) {
  const cmdMW = useSim((s) => s.targetMW)
  const ci = Math.min(47, Math.max(0, Math.round((frame.tHours / 24) * 47)))
  const baseNow = frame.baseSeries[ci] ?? frame.totalMW
  const dev = frame.totalMW - baseNow
  const curtailed = cmdMW < FARM_RATED_MW - 1e-6
  return (
    <div className="kpi-delta">
      <span className={dev >= 0.05 ? 'up' : dev <= -0.05 ? 'dn' : ''}>
        {dev >= 0 ? '+' : ''}{f1(dev)} MW <em>vs 对风基准</em>
      </span>
      <span>平均转速 {f1(frame.meanRpm)} rpm</span>
      {curtailed && <span className="lim">限功率 {f1(cmdMW)} MW</span>}
    </div>
  )
}

/* ---------- 随机异常：事件导演（触发/自动修复/弹窗计时） ---------- */
const ANOMALY_AUTO_MS = 10000
const ANOMALY_MODAL_MS = 10000

function AnomalyDirector() {
  const tHours = useSim((s) => s.tHours)
  const cycle = useSim((s) => s.anomalyCycle)
  const anomalyActive = useSim((s) => s.anomalyActive)
  const anomalyModal = useSim((s) => s.anomalyModal)
  const ensureAnomalyPlan = useSim((s) => s.ensureAnomalyPlan)
  const stepAnomaly = useSim((s) => s.stepAnomaly)
  const repairAnomaly = useSim((s) => s.repairAnomaly)
  const closeAnomalyModal = useSim((s) => s.closeAnomalyModal)
  const prevT = useRef(tHours)

  // 确保当前模拟日有剧本（页面加载 / 新一天换剧本）
  useEffect(() => { ensureAnomalyPlan(cycle) }, [cycle, ensureAnomalyPlan])

  // 时间推进（播放/拖轴）→ 检查触发；跨日则换新剧本
  useEffect(() => {
    const prev = prevT.current
    if (Math.abs(prev - tHours) < 1e-9) return
    stepAnomaly(prev, tHours)
    prevT.current = tHours
  }, [tHours, stepAnomaly])

  // 异常激活后 10s 未手动修复 → 自动修复
  useEffect(() => {
    if (!anomalyActive) return
    const id = window.setTimeout(() => repairAnomaly(true), ANOMALY_AUTO_MS)
    return () => window.clearTimeout(id)
  }, [anomalyActive, repairAnomaly])

  // 修复结果弹窗 10s 后自动关闭
  useEffect(() => {
    if (!anomalyModal) return
    const id = window.setTimeout(() => closeAnomalyModal(), ANOMALY_MODAL_MS)
    return () => window.clearTimeout(id)
  }, [anomalyModal, closeAnomalyModal])

  return null
}

/* ---------- 异常提示条（顶部居中，含“修复异常情况”按钮） ---------- */
function AnomalyBanner() {
  const active = useSim((s) => s.anomalyActive)
  const repairAnomaly = useSim((s) => s.repairAnomaly)
  if (!active) return null
  const label = anomalyLabel(active)
  const tid = active.turbineIndex !== null ? FARM[active.turbineIndex].id : '并网点'
  return (
    <div className={`anom-banner lv-${active.severity}`} role="alert" aria-live="assertive">
      <div className="anom-head">
        <i className="anom-dot" />
        <b>异常事件 · {label.level}</b>
        <span className="anom-chip">强度 {label.gain}</span>
        <span className="anom-time">{label.time}</span>
      </div>
      <div className="anom-body">
        <strong>{active.titleZh}<em>{active.titleEn} · {tid}</em></strong>
        <p>{active.descZh}</p>
      </div>
      <div className="anom-foot">
        <span className="anom-auto">10s 未处理将自动修复</span>
        <button className="anom-btn" onClick={() => repairAnomaly(false)}>修复异常情况</button>
      </div>
      <i className="anom-progress" />
    </div>
  )
}

/* ---------- 修复结果弹窗（步骤逐条浮现，10s 自动关闭） ---------- */
function AnomalyModal() {
  const modal = useSim((s) => s.anomalyModal)
  const closeAnomalyModal = useSim((s) => s.closeAnomalyModal)
  if (!modal) return null
  const { plan, auto } = modal
  return (
    <div className="anom-overlay" onClick={closeAnomalyModal}>
      <div className="anom-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <header className="anom-m-head">
          <span>{auto ? '系统已自动完成修复' : '异常修复完成'}</span>
          <button onClick={closeAnomalyModal} aria-label="关闭">✕</button>
        </header>
        <div className="anom-m-kind">
          <b>{plan.titleZh}</b>
          <em>{plan.titleEn}</em>
        </div>
        <ol className="anom-steps">
          {plan.steps.map((st, i) => (
            <li key={i} style={{ ['--i' as string]: i }}>{st}</li>
          ))}
        </ol>
        <footer className="anom-m-foot">通报 10s 后自动关闭 · 已恢复全场运行</footer>
      </div>
    </div>
  )
}

/* ---------- 主组件 ---------- */
export default function Hud() {
  const { scale, h: stageH } = useStageScale()
  const playing = useSim((s) => s.playing)
  const togglePlay = useSim((s) => s.togglePlay)
  const seek = useSim((s) => s.seek)
  const tHours = useSim((s) => s.tHours)
  const introDone = useSim((s) => s.introDone)
  const skipIntro = useSim((s) => s.skipIntro)
  const quality = useSim((s) => s.quality)
  const setQuality = useSim((s) => s.setQuality)
  const frame = useFarmFrame()
  const barRef = useRef<HTMLDivElement>(null)
  // R42 freeze：真实挂钟也冻住（否则 HUD 时间戳每秒跳一位，像素差永不归零）。
  // 取证模式钉在 00:00:00，不依赖 new Date() 的墙钟。
  const [wall, setWall] = useState(() => (FREEZE ? '00:00:00' : new Date().toLocaleTimeString('zh-CN', { hour12: false })))

  useEffect(() => {
    if (FREEZE) return
    const iv = setInterval(() => setWall(new Date().toLocaleTimeString('zh-CN', { hour12: false })), 1000)
    return () => clearInterval(iv)
  }, [])

  const hh = String(Math.floor(tHours)).padStart(2, '0')
  const mm = String(Math.floor((tHours % 1) * 60)).padStart(2, '0')
  const runN = frame.units.filter((u) => u.status === 'run').length
  const maxTempC = Math.max(0, ...frame.units.map((u) => u.tempC))
  const curtN = frame.units.filter((u) => u.status === 'curtail').length
  const alarmN = frame.units.filter((u) => u.status === 'alarm').length

  const seekFromEvent = (e: React.PointerEvent) => {
    const el = barRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    seek(((e.clientX - r.left) / r.width) * 24)
  }

  return (
    <div className="hud">
      <div className="stage" style={{ width: SIZE.w, height: stageH, transform: `translate(-50%, -50%) scale(${scale})` }}>
        {/* ===== 顶部 ===== */}
        <header className="topbar">
          <div className="cornorn l" /><div className="cornorn r" />
          <CornerWings />
          <CornerWings flip />
          <Wings />
          <Wings flip />
          <h1 className="title">未来能源数字孪生系统</h1>
          <div className="subtitle">风电场偏航优化 · 数字孪生演示平台 — AEOLUS TWIN <Badge k="演示" /></div>
          <div className="wallclock">本地 {wall || '--:--:--'} · 仿真 {hh}:{mm}</div>
          <SoundControl />
          <LayoutSwitch />
          <DemoSwitch />
          <div className="quality">
            <span>画质</span>
            {(['high', 'medium', 'low'] as const).map((q) => (
              <button key={q} className={quality === q ? 'on' : ''} onClick={() => setQuality(q, true)} aria-label={`画质 ${q}`}>
                {q === 'high' ? '高' : q === 'medium' ? '中' : '低'}
              </button>
            ))}
          </div>
          <div className="tline" />
        </header>

        {/* ===== 左列 ===== */}
        <div className="col left">
          <Panel title="全场功率总览" en="(MW)" badge="演示">
            <div className="kpi-xl">{f1(frame.totalMW)}<span className="unit">MW</span></div>
            <KpiDelta frame={frame} />
            <div className="kpi-sub">
              <span>今日电量 {intFmt(frame.energyTodayMWh)} MWh · 年估 {intFmt(frame.energyYearEstMWh)} MWh</span>
              <span>容量系数 {f1(frame.cfPct)}%（按演示日剖面外推）</span>
            </div>
          </Panel>

          <div className="row2">
            <Panel title="发电机温度" en="峰值 (℃)" badge="代理">
              <div className={`kpi-md${maxTempC > 93 ? ' warn' : ''}`}>{f1(maxTempC)}</div>
              <div className="kpi-sub"><span>报警阈值 96℃ · 与告警引擎同源</span></div>
            </Panel>
            <Panel title="等效满发小时" en="h · 今日" badge="代理">
              <div className="kpi-md">{f1(frame.energyTodayMWh / FARM_RATED_MW)}</div>
              <div className="kpi-sub"><span>今日电量 ÷ 装机 {intFmt(FARM_RATED_MW)} MW</span></div>
            </Panel>
          </div>

          <Panel title="运行机组数" en="Units">
            <div className="kpi-row">
              <span className="kpi-xl sm">{frame.runningCount}</span><span className="unit">/ {frame.units.length} 台</span>
            </div>
            <div className="kpi-sub"><span>运行 {runN} · 限功率 {curtN} · 告警 {alarmN}</span></div>
          </Panel>

          <Panel title="运行指标" en="Metrics" tall badge="代理">
            <div className="donuts">
              <MetricDonut pct={frame.yawPrecPct} label="对风精度" sub="mean|Δψ|" />
              <MetricDonut pct={frame.targetPct} label="功率达成" sub="actual/target" />
              <MetricDonut pct={Math.min(100, frame.wakeLossPct)} label="尾流损失" sub="环=0-100%" />
            </div>
          </Panel>

          <Panel title="机组状态矩阵" en={`Matrix ${LAYOUT.label}`} badge="演示">
            <Matrix />
          </Panel>

          <Panel title="实时功率" en="Real-time Power" badge="代理" cls="pchart">
            <PowerChart />
          </Panel>
        </div>

        {/* ===== 右列 ===== */}
        <div className="col right">
          <Panel title="风况雷达" en="Wind Radar" badge="代理">
            <Radar />
          </Panel>

          <Panel title="偏航角度" en="(deg)" cls="pservo">
            <div className="servos">
              {Array.from({ length: N_UNITS }, (_, i) => <ServoSlider key={i} i={i} />)}
            </div>
            <ControlConsole />
          </Panel>

          <Panel title="报警通知" en="Alarms" badge="演示" cls="palarms">
            <Alarms />
          </Panel>
        </div>


      {/* ===== 底部时间轴 ===== */}
        <footer className="timeline">
          <button className="play" onClick={togglePlay} aria-label={playing ? '暂停时间轴' : '播放时间轴'}>
            {playing ? <i className="pause" /> : <i className="tri" />}
          </button>
          <span className="clock">{hh}:{mm}</span>
          <div
            className="tlbar"
            ref={barRef}
            onPointerDown={(e) => { seekFromEvent(e) }}
            role="slider" aria-label="仿真时间轴" aria-valuemin={0} aria-valuemax={24} aria-valuenow={Math.round(tHours * 10) / 10}
          >
            <i className="tlfill" style={{ width: `${(tHours / 24) * 100}%` }} />
            <i className="tlhead" style={{ left: `${(tHours / 24) * 100}%` }} />
            {[...Array(24)].map((_, i) => <i key={i} className="tick" style={{ left: `${(i / 24) * 100}%` }} />)}
          </div>
          <span className="tail" title="24 小时仿真 = 真实 50 秒循环">24h/50s</span>
          <button className="fbtn" aria-label="全屏切换" onClick={() => {
            if (document.fullscreenElement) void document.exitFullscreen()
            else void document.documentElement.requestFullscreen?.().catch(() => undefined)
          }}>⛶</button>
        </footer>

        {/* 单机信息卡 */}
        <TurbineCard />

        {/* 开场巡航跳过（C5） */}
        {!introDone && (
          <button className="skip-btn" onClick={skipIntro} aria-label="跳过开场动画">
            跳过开场 <kbd>Esc</kbd>
          </button>
        )}

        <div className="demo-note">浏览器端演示数据 · 非 SCADA/FLORIS 实时值 <Badge k="演示" /></div>
      </div>

      {/* 随机异常：触发/自动修复/手动修复 */}
      <AnomalyDirector />
      <AnomalyBanner />
      <AnomalyModal />
    </div>
  )
}
