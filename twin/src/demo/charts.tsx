// ================================================================
// R44 演示图表组件（9.19 §二 四类图）
// ----------------------------------------------------------------
// ① 同色标的基准/优化流场图   FlowFieldChart（基准/优化共用同一固定色标）
// ② 三机与总功率对比          PowerBars
// ③ 参考值—预测值及误差        RefPredCase / RefPredAll
// ④ 精度与耗时对照             AccTimeChart
// 红线（§二 原文）：不得通过自动改变色标夸大变化 —— 全部刻度为 SCALES
// 编译期常量，组件不接受任何"自适应范围"参数。
// 全部输出 <svg>（内联样式、无外部依赖）→ 步骤 7 可整图导出。
// ================================================================

import { SCALES, CC, FIELD_XS, FIELD_YS, FIELD_N, type DemoCase } from './demoData.ts'

// ---- 流场固定色标（u ∈ [0,8] m/s，多段线性）----
const U_STOPS: Array<[number, [number, number, number]]> = [
  [0.0, [15, 12, 54]],
  [1.0, [40, 36, 110]],
  [2.5, [43, 84, 200]],
  [4.5, [29, 161, 240]],
  [6.5, [103, 232, 249]],
  [7.6, [207, 250, 254]],
  [8.0, [255, 255, 255]],
]
function uColor(u: number): string {
  const [lo, hi] = SCALES.u
  if (u <= lo) return 'rgb(15,12,54)'
  if (u >= hi) return 'rgb(255,255,255)'
  for (let i = 0; i < U_STOPS.length - 1; i++) {
    const [a, ca] = U_STOPS[i]
    const [b, cb] = U_STOPS[i + 1]
    if (u >= a && u <= b) {
      const f = (u - a) / (b - a)
      const r = Math.round(ca[0] + (cb[0] - ca[0]) * f)
      const g = Math.round(ca[1] + (cb[1] - ca[1]) * f)
      const bl = Math.round(ca[2] + (cb[2] - ca[2]) * f)
      return `rgb(${r},${g},${bl})`
    }
  }
  return 'rgb(255,255,255)'
}

const FONT = "'Noto Sans SC', system-ui, sans-serif"
const MONO = "'Share Tech Mono', monospace"

interface SvgProps { svgId: string; title: string; svgRefCb?: (el: SVGSVGElement | null) => void }

// ---- ① 流场图（同色标基准/优化共用；轮毂高度截面 · 展示口径）----
export function FlowFieldChart({ svgId, svgRefCb, title, u, tag }: SvgProps & { u: Float64Array; tag: string }) {
  const W = 300, H = 344
  const PX0 = 34, PY0 = 26, PW = 250, PH = 268
  const xOf = (x: number) => PX0 + ((x - FIELD_XS[0]) / (FIELD_XS[FIELD_N - 1] - FIELD_XS[0])) * PW
  const yOf = (y: number) => PY0 + ((FIELD_YS[FIELD_N - 1] - y) / (FIELD_YS[FIELD_N - 1] - FIELD_YS[0])) * PH
  const cw = PW / (FIELD_N - 1)
  const chh = PH / (FIELD_N - 1)
  const rects: React.ReactNode[] = []
  for (let j = 0; j < FIELD_N; j++) {
    for (let i = 0; i < FIELD_N; i++) {
      const val = u[j * FIELD_N + i]
      rects.push(
        <rect key={j * FIELD_N + i} x={xOf(FIELD_XS[i]) - cw / 2} y={yOf(FIELD_YS[j]) - chh / 2}
          width={cw + 0.6} height={chh + 0.6} fill={uColor(val)} />,
      )
    }
  }
  // 机组标记（T01 北/上游 → T03 南）
  const units = [
    { x: -100, y: 1272, id: 'T01' },
    { x: -100, y: 640, id: 'T02' },
    { x: -100, y: 8, id: 'T03' },
  ]
  // 色标（固定 [0,8] m/s）
  const LX = 268, LY = 40, LH = 220
  const stops = U_STOPS.map(([v]) => <stop key={v} offset={`${(v / 8) * 100}%`} stopColor={uColor(v)} />)
  return (
    <svg id={svgId} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', background: 'rgba(2,10,18,0.92)' }}
      xmlns="http://www.w3.org/2000/svg" fontFamily={FONT} ref={svgRefCb}>
      <rect x={PX0} y={PY0} width={PW} height={PH} fill="#020a12" />
      {rects}
      <rect x={PX0} y={PY0} width={PW} height={PH} fill="none" stroke={CC.axis} strokeWidth={1} />
      {units.map((t) => (
        <g key={t.id}>
          <circle cx={xOf(t.x)} cy={yOf(t.y)} r={5.5} fill="#0b1220" stroke="#e2f6ff" strokeWidth={1.6} />
          <text x={xOf(t.x) + 8} y={yOf(t.y) + 3.5} fontSize={10} fill="#e2f6ff" fontFamily={MONO}>{t.id}</text>
        </g>
      ))}
      {/* 来向箭头：北风（自上而下 = 自北向南） */}
      <g stroke="#9adcff" strokeWidth={1.4} fill="#9adcff">
        <line x1={xOf(220)} y1={PY0 + 8} x2={xOf(220)} y2={PY0 + 30} />
        <path d={`M ${xOf(220) - 4} ${PY0 + 26} L ${xOf(220)} ${PY0 + 33} L ${xOf(220) + 4} ${PY0 + 26} Z`} stroke="none" />
      </g>
      <text x={xOf(220) - 6} y={PY0 + 20} fontSize={9} fill="#9adcff">北风</text>
      <text x={12} y={14} fontSize={12} fill={CC.textHi}>{title}</text>
      <text x={12} y={H - 26} fontSize={9} fill={CC.text}>{tag}</text>
      <text x={12} y={H - 13} fontSize={9} fill={CC.text}>轮毂高度截面（90 m）· 展示口径，非二维物理问题</text>
      <defs>
        <linearGradient id={`${svgId}-cb`} x1="0" y1="1" x2="0" y2="0">{stops}</linearGradient>
      </defs>
      <rect x={LX} y={LY} width={12} height={LH} fill={`url(#${svgId}-cb)`} stroke={CC.axis} strokeWidth={0.8} />
      {[0, 2, 4, 6, 8].map((v) => (
        <g key={v}>
          <line x1={LX + 12} y1={LY + LH - (v / 8) * LH} x2={LX + 16} y2={LY + LH - (v / 8) * LH} stroke={CC.axis} strokeWidth={0.8} />
          <text x={LX + 18} y={LY + LH - (v / 8) * LH + 3} fontSize={8.5} fill={CC.text} fontFamily={MONO}>{v}</text>
        </g>
      ))}
      <text x={LX + 4} y={LY - 8} fontSize={8.5} fill={CC.text}>u (m/s)</text>
      <text x={LX - 4} y={LY + LH + 14} fontSize={8} fill={CC.text}>固定色标 0–8</text>
    </svg>
  )
}

// ---- ② 三机与总功率对比（固定 0–3600 kW）----
export interface PowerBarGroup {
  label: string
  bars: Array<{ value: number; color: string; name: string }>
}
export function PowerBars({ svgId, svgRefCb, title, groups, note }: SvgProps & { groups: PowerBarGroup[]; note?: string }) {
  const W = 300, H = 216
  const PX0 = 40, PY0 = 24, PW = 244, PH = 150
  const [lo, hi] = SCALES.p
  const yOf = (v: number) => PY0 + PH - ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * PH
  const gw = PW / groups.length
  const bw = Math.min(30, gw / (groups[0]?.bars.length + 1.2))
  return (
    <svg id={svgId} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', background: 'rgba(2,10,18,0.92)' }}
      xmlns="http://www.w3.org/2000/svg" fontFamily={FONT} ref={svgRefCb}>
      <text x={12} y={14} fontSize={12} fill={CC.textHi}>{title}</text>
      {[0, 900, 1800, 2700, 3600].map((v) => (
        <g key={v}>
          <line x1={PX0} y1={yOf(v)} x2={PX0 + PW} y2={yOf(v)} stroke={CC.grid} strokeWidth={0.8} />
          <text x={PX0 - 5} y={yOf(v) + 3} fontSize={8.5} fill={CC.text} textAnchor="end" fontFamily={MONO}>{v}</text>
        </g>
      ))}
      <line x1={PX0} y1={PY0 + PH} x2={PX0 + PW} y2={PY0 + PH} stroke={CC.axis} strokeWidth={1} />
      {groups.map((g, gi) => {
        const gx = PX0 + gi * gw + gw / 2
        return (
          <g key={g.label}>
            {g.bars.map((b, bi) => {
              const x = gx - (g.bars.length * bw + (g.bars.length - 1) * 4) / 2 + bi * (bw + 4)
              const y = yOf(b.value)
              return (
                <g key={b.name}>
                  <rect x={x} y={y} width={bw} height={PY0 + PH - y} fill={b.color} opacity={0.92} />
                  <text x={x + bw / 2} y={y - 3} fontSize={8.5} fill={CC.textHi} textAnchor="middle" fontFamily={MONO}>
                    {b.value >= 1000 ? (b.value / 1000).toFixed(2) : Math.round(b.value)}
                  </text>
                </g>
              )
            })}
            <text x={gx} y={PY0 + PH + 14} fontSize={9.5} fill={CC.text} textAnchor="middle">{g.label}</text>
          </g>
        )
      })}
      <text x={12} y={H - 8} fontSize={9} fill={CC.text}>{note ?? `固定刻度 0–3600 kW · 参考=FLORIS 4.6.6，预测=GCH 内核（重合即偏差 < 0.01 kW）`}</text>
    </svg>
  )
}

// ---- ③a 参考值—预测值（单工况：逐机功率 + 有效风速）----
export function RefPredCase({ svgId, svgRefCb, title, c }: SvgProps & { c: DemoCase }) {
  const W = 300, H = 232
  const PX0 = 40, PY0 = 30, PW = 244, PH = 74
  const yP = (v: number) => PY0 + PH - ((Math.min(SCALES.p[1], v) / SCALES.p[1])) * PH
  const YU0 = PY0 + PH + 56
  const PHU = 74
  const yU = (v: number) => YU0 + PHU - (((Math.min(SCALES.uEff[1], Math.max(SCALES.uEff[0], v))) - SCALES.uEff[0]) / (SCALES.uEff[1] - SCALES.uEff[0])) * PHU
  const names = ['T01', 'T02', 'T03']
  const gw = PW / 3
  return (
    <svg id={svgId} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', background: 'rgba(2,10,18,0.92)' }}
      xmlns="http://www.w3.org/2000/svg" fontFamily={FONT} ref={svgRefCb}>
      <text x={12} y={14} fontSize={12} fill={CC.textHi}>{title}</text>
      <text x={12} y={26} fontSize={9} fill={CC.text}>① 逐机功率 (kW) · 固定 0–3600</text>
      {[0, 900, 1800, 2700, 3600].map((v) => (
        <line key={v} x1={PX0} y1={yP(v)} x2={PX0 + PW} y2={yP(v)} stroke={CC.grid} strokeWidth={0.7} />
      ))}
      {names.map((n, i) => {
        const gx = PX0 + i * gw + gw / 2
        return (
          <g key={n}>
            <rect x={gx - 26} y={yP(c.refP[i])} width={24} height={PY0 + PH - yP(c.refP[i])} fill={CC.ref} opacity={0.92} />
            <rect x={gx + 2} y={yP(c.predP[i])} width={24} height={PY0 + PH - yP(c.predP[i])} fill={CC.fast} opacity={0.92} />
            <text x={gx - 14} y={yP(c.refP[i]) - 3} fontSize={8.5} fill={CC.textHi} textAnchor="middle" fontFamily={MONO}>{Math.round(c.refP[i])}</text>
            <text x={gx} y={PY0 + PH + 13} fontSize={9.5} fill={CC.text} textAnchor="middle">{n}</text>
          </g>
        )
      })}
      <text x={12} y={YU0 - 8} fontSize={9} fill={CC.text}>② 逐机有效风速 (m/s) · 固定 4–9</text>
      {[4, 5, 6, 7, 8, 9].map((v) => (
        <line key={v} x1={PX0} y1={yU(v)} x2={PX0 + PW} y2={yU(v)} stroke={CC.grid} strokeWidth={0.7} />
      ))}
      {names.map((n, i) => {
        const gx = PX0 + i * gw + gw / 2
        return (
          <g key={n}>
            <rect x={gx - 26} y={yU(c.refUEff[i])} width={24} height={YU0 + PHU - yU(c.refUEff[i])} fill={CC.ref} opacity={0.92} />
            <rect x={gx + 2} y={yU(c.predUAvg[i])} width={24} height={YU0 + PHU - yU(c.predUAvg[i])} fill={CC.fast} opacity={0.92} />
            <text x={gx - 14} y={yU(c.refUEff[i]) - 3} fontSize={8.5} fill={CC.textHi} textAnchor="middle" fontFamily={MONO}>{c.refUEff[i].toFixed(2)}</text>
            <text x={gx} y={YU0 + PHU + 13} fontSize={9.5} fill={CC.text} textAnchor="middle">{n}</text>
          </g>
        )
      })}
      <g fontSize={8.5} fill={CC.text}>
        <rect x={PX0} y={H - 22} width={10} height={10} fill={CC.ref} />
        <text x={PX0 + 14} y={H - 13}>参考值 {c.refTotalKw.toFixed(1)} kW（总）</text>
        <rect x={PX0 + 120} y={H - 22} width={10} height={10} fill={CC.fast} />
        <text x={PX0 + 134} y={H - 13}>预测值 {c.predTotalKw.toFixed(1)} kW</text>
      </g>
      <text x={12} y={H - 2} fontSize={8.5} fill={CC.err}>
        偏差：总功率 {(Math.abs(c.errKw) * 1000).toFixed(3)} mW / 单机最大 {c.maxUnitErrKw.toExponential(1)} kW（浮点噪声级）
      </text>
    </svg>
  )
}

// ---- ③b 参考值—预测值（41 工况全集 + 误差）----
export function RefPredAll({ svgId, svgRefCb, title, cases }: SvgProps & { cases: DemoCase[] }) {
  const W = 300, H = 236
  const A = { x0: 40, y0: 28, w: 118, h: 150 }   // 散点（总功率）
  const B = { x0: 178, y0: 28, w: 112, h: 150 }  // 误差（对数）
  const lo = 2650, hi = 3350
  const xA = (v: number) => A.x0 + ((v - lo) / (hi - lo)) * A.w
  const yA = (v: number) => A.y0 + A.h - ((v - lo) / (hi - lo)) * A.h
  const [elo, ehi] = SCALES.errKwLog
  const yB = (v: number) => B.y0 + B.h - ((Math.log10(Math.max(elo, v)) - Math.log10(elo)) / (Math.log10(ehi) - Math.log10(elo))) * B.h
  return (
    <svg id={svgId} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', background: 'rgba(2,10,18,0.92)' }}
      xmlns="http://www.w3.org/2000/svg" fontFamily={FONT} ref={svgRefCb}>
      <text x={12} y={14} fontSize={12} fill={CC.textHi}>{title}</text>
      <text x={A.x0} y={24} fontSize={8.5} fill={CC.text}>总功率 参考 vs 预测（固定 2650–3350）</text>
      <rect x={A.x0} y={A.y0} width={A.w} height={A.h} fill="none" stroke={CC.axis} strokeWidth={0.9} />
      <line x1={xA(lo)} y1={yA(lo)} x2={xA(hi)} y2={yA(hi)} stroke={CC.err} strokeWidth={1} strokeDasharray="4 3" opacity={0.8} />
      {cases.map((c) => (
        <g key={c.id}>
          <circle cx={xA(c.refTotalKw)} cy={yA(c.predTotalKw)} r={2.6} fill={c.id === 'none' ? CC.none : c.id === 'greedy' ? CC.opt : CC.fast} opacity={0.95} />
        </g>
      ))}
      <text x={A.x0} y={A.y0 + A.h + 12} fontSize={8.5} fill={CC.text} fontFamily={MONO}>2650        3350 kW</text>
      <text x={B.x0} y={24} fontSize={8.5} fill={CC.text}>单机最大偏差 (kW) · 对数 1e-14–1e-9</text>
      <rect x={B.x0} y={B.y0} width={B.w} height={B.h} fill="none" stroke={CC.axis} strokeWidth={0.9} />
      {[1e-14, 1e-12, 1e-10, 1e-9].map((v) => (
        <g key={v}>
          <line x1={B.x0} y1={yB(v)} x2={B.x0 + B.w} y2={yB(v)} stroke={CC.grid} strokeWidth={0.7} />
          <text x={B.x0 + B.w + 3} y={yB(v) + 3} fontSize={7.5} fill={CC.text} fontFamily={MONO}>{v.toExponential(0).replace('e-', 'e-')}</text>
        </g>
      ))}
      {cases.map((c, i) => (
        <circle key={c.id} cx={B.x0 + 8 + (i / (cases.length - 1)) * (B.w - 16)} cy={yB(c.maxUnitErrKw)} r={1.8} fill={CC.fast} opacity={0.9} />
      ))}
      <text x={B.x0} y={B.y0 + B.h + 12} fontSize={8.5} fill={CC.text}>横轴=41 工况顺序（none→统一→上游→中游→greedy）</text>
      <text x={12} y={H - 14} fontSize={8.5} fill={CC.text}>
        41 工况（≥20 独立工况验收）· 快速模型为闭式内核（无训练）→ 全部为未参与训练的独立测试工况
      </text>
      <text x={12} y={H - 2} fontSize={8.5} fill={CC.err}>
        最大单机偏差 {Math.max(...cases.map((c) => c.maxUnitErrKw)).toExponential(2)} kW = 浮点实现噪声（同方程移植），非模型误差
      </text>
    </svg>
  )
}

// ---- ④ 精度与耗时对照 ----
export function AccTimeChart({ svgId, svgRefCb, title, cases }: SvgProps & { cases: DemoCase[] }) {
  const W = 300, H = 224
  const PX0 = 44, PY0 = 30, PW = 244, PH = 138
  const [lo, hi] = SCALES.msLog
  const xOf = (i: number) => PX0 + (i / (cases.length - 1)) * PW
  const yOf = (v: number) => PY0 + PH - ((Math.log10(Math.max(lo, Math.min(hi, v))) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * PH
  const refMean = cases.reduce((s, c) => s + c.refSec * 1000, 0) / cases.length
  const predMean = cases.reduce((s, c) => s + c.predMs, 0) / cases.length
  const p95 = [...cases.map((c) => c.predMs)].sort((a, b) => a - b)[Math.floor(cases.length * 0.95)]
  const maxErr = Math.max(...cases.map((c) => c.maxUnitErrKw))
  const nmae = (cases.reduce((s, c) => s + Math.abs(c.errKw), 0) / cases.reduce((s, c) => s + c.refTotalKw, 0)) * 100
  return (
    <svg id={svgId} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', background: 'rgba(2,10,18,0.92)' }}
      xmlns="http://www.w3.org/2000/svg" fontFamily={FONT} ref={svgRefCb}>
      <text x={12} y={14} fontSize={12} fill={CC.textHi}>{title}</text>
      <text x={12} y={26} fontSize={9} fill={CC.text}>单工况求解耗时 (ms) · 对数 0.05–20 · 横轴=41 工况</text>
      <rect x={PX0} y={PY0} width={PW} height={PH} fill="none" stroke={CC.axis} strokeWidth={0.9} />
      {[0.1, 1, 10].map((v) => (
        <g key={v}>
          <line x1={PX0} y1={yOf(v)} x2={PX0 + PW} y2={yOf(v)} stroke={CC.grid} strokeWidth={0.7} />
          <text x={PX0 - 5} y={yOf(v) + 3} fontSize={8.5} fill={CC.text} textAnchor="end" fontFamily={MONO}>{v}</text>
        </g>
      ))}
      {cases.map((c, i) => (
        <g key={c.id}>
          <circle cx={xOf(i)} cy={yOf(c.refSec * 1000)} r={2.4} fill={CC.ref} opacity={0.9} />
          <circle cx={xOf(i)} cy={yOf(c.predMs)} r={2.4} fill={CC.fast} opacity={0.9} />
        </g>
      ))}
      <text x={PX0} y={PY0 + PH + 13} fontSize={8.5} fill={CC.text}>横轴：none → 统一×13 → 上游×13 → 中游×13 → greedy</text>
      <g fontSize={9} fill={CC.text}>
        <circle cx={20} cy={H - 58} r={3} fill={CC.ref} />
        <text x={28} y={H - 55}>FLORIS 4.6.6 实算（oracle 生成机墙钟，存档值）均值 {refMean.toFixed(1)} ms</text>
        <circle cx={20} cy={H - 42} r={3} fill={CC.fast} />
        <text x={28} y={H - 39}>GCH 内核（浏览器端）均值 {predMean.toFixed(2)} ms · P95 {p95.toFixed(2)} ms（&lt;1 s 交互预算 ✓）</text>
      </g>
      <text x={12} y={H - 22} fontSize={9} fill={CC.text}>精度：NMAE(总功率) = {nmae.toExponential(2)}% · 单机最大偏差 {maxErr.toExponential(1)} kW</text>
      <text x={12} y={H - 8} fontSize={8.5} fill={CC.err}>两组耗时不在同一机器测得（FLORIS 为生成环境存档、内核为当前浏览器实测）；量级差 ~{Math.round(refMean / Math.max(predMean, 1e-9))}× 仅作量级参考，不作同机加速比结论</text>
    </svg>
  )
}
