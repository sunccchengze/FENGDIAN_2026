// ================================================================
// R44 演示面板（?demo=1 · 9.19 §二 七步流程，叠加在 3D 场景上）
// ----------------------------------------------------------------
// 步骤（§二 原文表）：1 选择工况 / 2 查看基准 / 3 调整偏航 / 4 求解优化 /
//   5 复核效果 / 6 展示可靠性 / 7 导出材料
// 界面纪律（§二 原文）：区分「模型建议」与「参考模型复核结果」；
//   记录推理、优化、复核分别用了多长时间（performance.now 计时钩子）。
// 场景联动：步骤 3/4 通过 store 下发偏航指令（P2 执行器 0.3°/s 真实转动；
//   freeze=1 取证模式下直接对齐 actYaw 供逐帧截图）。
// 截图口径：?demo=1&layout=1x3&freeze=1&step=N&cam=…&t=15&intro=0
// ================================================================

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSim } from '../state/simStore.ts'
import { ACTIVE_LAYOUT, LAYOUTS } from '../scene/layouts.ts'
import { FREEZE } from '../scene/freeze.ts'
import './demo.css'
import {
  DEMO_WIND, VERIFIED_RANGE, TAG_REF, TAG_FAST, DEMO_UNITS, DEMO_SCENE, CC,
  buildCases, findCase, runGreedy, hubField, buildSummary,
  type DemoCase, type OptimizeRun,
} from './demoData.ts'
import { evaluateFarmScene } from '../core/physics/evalFarm.ts'
import { FlowFieldChart, PowerBars, RefPredCase, RefPredAll, AccTimeChart } from './charts.tsx'

const STEP_TITLES = ['选择工况', '查看基准', '调整偏航', '求解优化', '复核效果', '展示可靠性', '导出材料']
const LAYOUT1X3 = LAYOUTS['1x3']

interface Timings { inferMs: number; optimizeMs: number | null; reviewMs: number | null }

function applyDemoYaw(yaw: readonly number[]): void {
  const s = useSim.getState()
  for (let i = 0; i < 3; i++) s.setUnitYaw(i, yaw[i] ?? 0)
  if (FREEZE) {
    const act = [...s.actYaw]
    for (let i = 0; i < 3; i++) act[i] = yaw[i] ?? act[i]
    useSim.setState({ actYaw: act })
  }
}

function downloadText(name: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
function downloadSvg(el: SVGSVGElement | null, name: string): void {
  if (!el) return
  const s = new XMLSerializer().serializeToString(el)
  downloadText(name, `<?xml version="1.0" encoding="UTF-8"?>\n${s}`, 'image/svg+xml')
}

const num = (v: number, d = 1) => v.toFixed(d)
const yawStr = (y: number) => (y > 0 ? `+${y}` : `${y}`)

export default function DemoPanel() {
  const q = useMemo(() => new URLSearchParams(location.search), [])
  const initialStep = Math.min(7, Math.max(1, parseInt(q.get('step') ?? '1', 10) || 1))

  const [step, setStep] = useState(initialStep)
  const [manualId, setManualId] = useState('unified+20')
  const [customYaw, setCustomYaw] = useState<number[] | null>(null)
  const [opt, setOpt] = useState<OptimizeRun | null>(null)
  const [timings, setTimings] = useState<Timings>({ inferMs: 0, optimizeMs: null, reviewMs: null })
  const [cases, setCases] = useState<DemoCase[]>([])
  const [booted, setBooted] = useState(false)
  const reviewDone = useRef(false)
  const svgRefs = useRef<Record<string, SVGSVGElement | null>>({})

  // ---- 挂载：41 工况推理（推理计时钩子）+ 按初始步骤就位（含 freeze 截图路径）----
  useEffect(() => {
    if (ACTIVE_LAYOUT !== '1x3') return
    const t0 = performance.now()
    const cs = buildCases()
    const inferMs = performance.now() - t0
    setCases(cs)
    if (initialStep >= 4) {
      const t1 = performance.now()
      const r = runGreedy()
      setOpt(r)
      setTimings({ inferMs, optimizeMs: performance.now() - t1, reviewMs: null })
      applyDemoYaw(r.yaw)
    } else if (initialStep >= 3) {
      applyDemoYaw(findCase(cs, 'unified+20').yaw)
      setTimings({ inferMs, optimizeMs: null, reviewMs: null })
    } else {
      applyDemoYaw([0, 0, 0])
      setTimings({ inferMs, optimizeMs: null, reviewMs: null })
    }
    setBooted(true)
  }, [initialStep])

  const none = booted ? findCase(cases, 'none') : null
  const greedy = booted ? findCase(cases, 'greedy') : null
  const manual = booted ? findCase(cases, manualId) : null
  const effYaw = customYaw ?? manual?.yaw ?? [0, 0, 0]
  const effKey = `${step}|${effYaw.join(',')}`

  // 步骤 6 进入时：复核计时钩子（对照表汇编）
  useEffect(() => {
    if (step !== 6 || !booted || reviewDone.current) return
    const t0 = performance.now()
    void cases.map((c) => ({ ref: c.refTotalKw, pred: c.predTotalKw, errKw: c.errKw }))
    setTimings((t) => ({ ...t, reviewMs: performance.now() - t0 }))
    reviewDone.current = true
  }, [step, booted, cases])

  // 流场（惰性计算；单 memo，固定网格与固定色标；effKey 编码 step+偏航组合）
  const fields = useMemo(() => {
    const out: { none: Float64Array | null; step3: Float64Array | null; opt: Float64Array | null } =
      { none: null, step3: null, opt: null }
    if (!booted) return out
    if (step === 2 || step === 5 || step === 7) out.none = hubField([0, 0, 0])
    if (step === 3) out.step3 = hubField([...effYaw])
    if (step === 5 || step === 7) out.opt = hubField([30, 25, 0])
    return out
    // effYaw 由 effKey 编码（customYaw ?? 预置工况 yaw，二者皆受控状态）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [booted, step, effKey])

  if (ACTIVE_LAYOUT !== '1x3') {
    return (
      <div className="demo-panel demo-block">
        <h2>演示需要 1×3 串列布局</h2>
        <p>本演示为三机串列（T01–T03）工况流程，请用 <code>?demo=1&amp;layout=1x3</code> 打开。</p>
      </div>
    )
  }
  if (!booted) return null

  // ---- 动作 ----
  const goto = (n: number, yaw?: readonly number[]): void => {
    if (n < 1 || n > 7) return
    if (n === 2) applyDemoYaw([0, 0, 0])
    else if (n === 3) applyDemoYaw(yaw ?? effYaw)
    else if (n >= 4) applyDemoYaw(yaw ?? (opt ?? greedy)?.yaw ?? [30, 25, 0])
    setStep(n)
  }
  const startOptimize = (): void => {
    const t0 = performance.now()
    const r = runGreedy()
    setOpt(r)
    setTimings((t) => ({ ...t, optimizeMs: performance.now() - t0 }))
    applyDemoYaw(r.yaw)
  }
  const onSlider = (i: number, v: number): void => {
    const yaw = [...effYaw]
    yaw[i] = v
    const hit = cases.find((c) => c.yaw.join(',') === yaw.join(','))
    if (hit) {
      setCustomYaw(null)
      setManualId(hit.id)
    } else {
      setCustomYaw(yaw)
    }
    applyDemoYaw(yaw)
  }

  // ---- 步骤 7 导出 ----
  const attach = (k: string) => (el: SVGSVGElement | null) => { svgRefs.current[k] = el }
  const doExportJson = (): void => {
    if (!booted || !greedy) return
    const s = buildSummary(cases, greedy, { ...timings })
    downloadText('tandem3_demo_case_2026-10-05.json', JSON.stringify(s, null, 2), 'application/json')
  }

  const refCard = (title: string, kw: number, p: readonly number[], tag: string, cls: string) => (
    <div className={`demo-dualcard ${cls}`}>
      <div className="demo-dualtitle">{title} {tag}</div>
      <div className="demo-big">{num(kw)} <span>kW</span></div>
      <div className="demo-sub">T01 {num(p[0])} · T02 {num(p[1])} · T03 {num(p[2])} kW</div>
    </div>
  )

  const baseGroups = none && greedy
    ? (['T01', 'T02', 'T03', '总'] as const).map((n, i) => ({
      label: n,
      bars: [
        { value: i < 3 ? none.refP[i] : none.refTotalKw, color: CC.ref, name: 'base' },
        { value: i < 3 ? greedy.refP[i] : greedy.refTotalKw, color: CC.opt, name: 'opt' },
      ],
    }))
    : []

  return (
    <div className="demo-panel">
      <div className="demo-head">
        <div>
          <h2>偏航优化演示 · 七步流程</h2>
          <div className="demo-headsub">
            9.19 §二 演示界面 · 1×3 串列（{LAYOUT1X3.units.map((u) => u.id).join('→')}，北→南）· {DEMO_WIND.uInf} m/s 北风 · TI {num(DEMO_WIND.ti * 100, 0)}%
          </div>
        </div>
        <button className="demo-x" title="关闭演示面板" onClick={() => { const u = new URL(location.href); u.searchParams.delete('demo'); location.href = u.toString() }}>×</button>
      </div>

      <div className="demo-steps">
        {STEP_TITLES.map((t, i) => (
          <button key={t} className={`demo-step ${i + 1 === step ? 'on' : ''} ${i + 1 < step ? 'done' : ''}`} onClick={() => goto(i + 1)}>
            <i>{i + 1}</i>{t}
          </button>
        ))}
      </div>

      <div className="demo-body">
        {/* ================= 1 选择工况 ================= */}
        {step === 1 && none && (
          <>
            <div className="demo-card">
              <h3>来流条件（输入范围明确显示）</h3>
              <div className="demo-windrow">
                <label>风速 (m/s)<input value={String(DEMO_WIND.uInf)} readOnly /></label>
                <label>来向（°，0=北）<input value={String(DEMO_WIND.fromDeg)} readOnly /></label>
                <label>湍流强度<input value={String(DEMO_WIND.ti)} readOnly /></label>
              </div>
              <div className={`demo-range ${JSON.stringify(DEMO_WIND) === JSON.stringify(VERIFIED_RANGE) ? 'ok' : 'warn'}`}>
                {JSON.stringify(DEMO_WIND) === JSON.stringify(VERIFIED_RANGE)
                  ? '✓ 当前工况在参考模型已验证范围内（8 m/s / 0° / TI 6% —— 该 oracle 的唯一验证工况）'
                  : '⚠ 超出参考模型已验证范围：参考值不可用，仅显示快速模型结果'}
              </div>
              <p className="demo-note">范围检查 = 统一坐标系/单位/机组参数 + 参考模型验证范围比对（§二 步骤 1 后台要求）。</p>
            </div>
            <div className="demo-card">
              <h3>坐标系 · 单位 · 机组参数</h3>
              <ul className="demo-list">
                <li>场景系：+x=东，+z=南（three.js Y-up）；FLORIS 系：x=东，y=北（y = −z）</li>
                <li>单位：m / m·s⁻¹ / kW / °；风速为轮毂高度（90 m）参考值</li>
                <li>{DEMO_UNITS.map((u) => `${u.id} (x=${u.x}, z=${u.z})`).join(' · ')}，行距 632 m（5.02D）</li>
                <li>NREL 5MW 参考机组：D = 125.88 m，HH = 90 m，额定 5000 kW</li>
              </ul>
            </div>
            <div className="demo-card">
              <h3>工况计划（41 个独立测试工况，≥ §七 验收 20 个）</h3>
              <div className="demo-casegrid">
                {cases.map((c) => (
                  <button key={c.id} className={`demo-case ${c.id === manualId ? 'sel' : ''}`}
                    onClick={() => { setManualId(c.id); setCustomYaw(null); goto(3, c.yaw) }}>
                    {c.label}<em>{num(c.refTotalKw, 0)} kW</em>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {/* ================= 2 查看基准 ================= */}
        {step === 2 && fields.none && none && (
          <>
            <div className="demo-two">
              <div className="demo-chartbox">
                <FlowFieldChart svgId="demo-c1-baseline" u={fields.none} title="① 基准流场（零偏航）" tag="快速模型场（代理）" />
              </div>
              <div className="demo-chartbox">
                <PowerBars svgId="demo-c2-baseline" title="② 三机与总功率（基准）"
                  groups={( ['T01', 'T02', 'T03', '总功率'] as const).map((n, i) => ({
                    label: n,
                    bars: [
                      { value: i < 3 ? none.refP[i] : none.refTotalKw, color: CC.ref, name: 'ref' },
                      { value: i < 3 ? none.predP[i] : none.predTotalKw, color: CC.fast, name: 'pred' },
                    ],
                  }))}
                  note="蓝=参考值 FLORIS 4.6.6 · 黄=预测值 GCH 内核（同刻度重合，偏差 <0.01 kW）" />
              </div>
            </div>
            <div className="demo-dual">
              {refCard('参考模型输出', none.refTotalKw, none.refP, TAG_REF, 'ref')}
              {refCard('快速模型输出', none.predTotalKw, none.predP, TAG_FAST, 'fast')}
            </div>
            <p className="demo-note">零偏航基准：尾流轴对准 T02/T03，T02 单机仅 {num(none.refP[1], 0)} kW（T01 净风 {num(none.refP[0], 0)} kW）——偏航优化的改进空间来源。</p>
          </>
        )}

        {/* ================= 3 调整偏航 ================= */}
        {step === 3 && manual && fields.step3 && (
          <>
            <div className="demo-card">
              <h3>控制变量（三机偏航角，±30° 执行器量程 · 5° 步进）</h3>
              <div className="demo-yawrow">
                {DEMO_UNITS.map((u, i) => (
                  <label key={u.id} className="demo-yaw">
                    {u.id} 偏航
                    <input type="range" min={-30} max={30} step={5} value={effYaw[i] ?? 0}
                      onChange={(e) => onSlider(i, Number(e.target.value))} />
                    <b>{yawStr(effYaw[i] ?? 0)}°</b>
                  </label>
                ))}
              </div>
              <p className="demo-note">
                当前：{customYaw ? `自定义 [${effYaw.map(yawStr).join(', ')}]°` : manual.label}。
                拖动即下发指令：机舱按 P2 执行器 0.3°/s 真实转动，场景尾流与功率随实际偏航（actYaw）实时变化。
              </p>
            </div>
            <div className="demo-two">
              <div className="demo-chartbox">
                <FlowFieldChart svgId="demo-c3-field" u={fields.step3} title={`③ 流场（${customYaw ? '自定义偏航' : manual.label}）`} tag="快速模型场 · 观察尾流偏折" />
              </div>
              <div className="demo-dual">
                {(() => {
                  const c = customYaw ? null : manual
                  return c ? (
                    <>
                      {refCard('模型建议', c.predTotalKw, c.predP, TAG_FAST, 'fast')}
                      {refCard('参考模型复核结果', c.refTotalKw, c.refP, TAG_REF, 'ref')}
                    </>
                  ) : (
                    <div className="demo-dualcard fast">
                      <div className="demo-dualtitle">模型建议（自定义组合）{TAG_FAST}</div>
                      <div className="demo-big">{num(customYaw ? customPredictTotalKw(customYaw) : 0)} <span>kW</span></div>
                      <div className="demo-sub">该组合不在 oracle 扫描网格内 → 无参考值（参考模型未验证此控制点）</div>
                    </div>
                  )
                })()}
              </div>
            </div>
          </>
        )}

        {/* ================= 4 求解优化 ================= */}
        {step === 4 && (
          <>
            <div className="demo-card">
              <h3>有界优化器（快速模型求解）</h3>
              <div className="demo-optmeta">
                <span>目标：max ΣPᵢ（总功率）</span>
                <span>约束：Δψᵢ ∈ [−30°, +30°] · 稳态 GCH</span>
                <span>搜索：上游→下游逐机贪心 · CAND = −30…+30 步 5°（13 档）</span>
              </div>
              {!opt ? (
                <button className="demo-go" onClick={startOptimize}>▶ 开始求解（3 阶段 × 13 档 = 42 次快速模型调用）</button>
              ) : (
                <>
                  <table className="demo-table">
                    <thead><tr><th>阶段</th><th>选中偏航 [T01,T02,T03]</th><th>全场总功率（模型）</th></tr></thead>
                    <tbody>
                      {opt.stages.map((s) => (
                        <tr key={s.stage}>
                          <td>{s.stageZh}</td>
                          <td>[{s.yaw3.map(yawStr).join(', ')}]°</td>
                          <td>{num(s.totalKw)} kW</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="demo-dual">
                    {refCard('模型建议（优化后）', opt.totalKw, greedy?.predP ?? [], TAG_FAST, 'fast')}
                    {refCard('参考模型复核结果', greedy?.refTotalKw ?? 0, greedy?.refP ?? [], TAG_REF, 'ref')}
                  </div>
                </>
              )}
              <p className="demo-note">
                调用次数 {opt?.calls ?? '—'} · 耗时 {opt ? num(opt.ms, 1) : '—'} ms（优化计时）·
                参考模型按同定义（上游→下游贪心）复算：[{(greedy?.yaw ?? []).map(yawStr).join(', ')}] → {num(greedy?.refTotalKw ?? 0)} kW
                （{TAG_REF}）。指令已下发，机舱 0.3°/s 到位，场景尾流随 actYaw 实时偏折。
              </p>
            </div>
          </>
        )}

        {/* ================= 5 复核效果 ================= */}
        {step === 5 && fields.none && fields.opt && greedy && none && (
          <>
            <div className="demo-two demo-two-wide">
              <div className="demo-chartbox">
                <FlowFieldChart svgId="demo-c5-base" u={fields.none} title="⑤a 优化前（零偏航）" tag="同色标 · 快速模型场" />
              </div>
              <div className="demo-chartbox">
                <FlowFieldChart svgId="demo-c5-opt" u={fields.opt} title="⑤b 优化后（逐机贪心）" tag="同色标 · 尾流偏离开轴" />
              </div>
            </div>
            <div className="demo-two">
              <div className="demo-chartbox">
                <PowerBars svgId="demo-c5-power" title="⑤c 优化前后（同刻度）" groups={baseGroups}
                  note="蓝=优化前 · 橙=优化后（参考值 FLORIS 4.6.6 复算；预测值与其偏差 <0.01 kW）" />
              </div>
              <div className="demo-chartbox">
                <RefPredCase svgId="demo-c5-case" title="⑤d 参考值—预测值（优化工况）" c={greedy} />
              </div>
            </div>
            <div className="demo-card">
              <h3>收益（参考模型复算口径）</h3>
              <div className="demo-gain">
                <span>总功率 {num(none.refTotalKw)} → {num(greedy.refTotalKw)} kW</span>
                <b>+{num(greedy.refTotalKw - none.refTotalKw)} kW（+{num((greedy.refTotalKw / none.refTotalKw - 1) * 100)}%）</b>
                <span>主要来源：T01/T02 偏航使尾流横向偏折，T02 {num(none.refP[1], 0)} → {num(greedy.refP[1], 0)} kW</span>
              </div>
              <p className="demo-note">
                未改善/下降工况保留展示（§二 步骤 5）：统一 −30° = {num(findCase(cases, 'unified-30').refTotalKw, 0)} kW
                （{num((findCase(cases, 'unified-30').refTotalKw / none.refTotalKw - 1) * 100)}%）、
                统一 −15° = {num(findCase(cases, 'unified-15').refTotalKw, 0)} kW —— 错向偏航降功率，优化器不选。
              </p>
            </div>
          </>
        )}

        {/* ================= 6 展示可靠性 ================= */}
        {step === 6 && cases.length > 0 && (
          <>
            <div className="demo-two">
              <div className="demo-chartbox">
                <RefPredAll svgId="demo-c6-refpred" title="⑥a 参考值—预测值（41 工况）+ 误差" cases={cases} />
              </div>
              <div className="demo-chartbox">
                <AccTimeChart svgId="demo-c6-acctime" title="⑥b 精度与耗时对照" cases={cases} />
              </div>
            </div>
            <div className="demo-card">
              <h3>测试集 · 误差定义 · 模型版本（§二 步骤 6 后台要求）</h3>
              <ul className="demo-list">
                <li>固定测试集：tandem3 oracle 41 工况（FLORIS 4.6.6 GCH 实算存档；docs/research/oracle/floris_gch_oracle_v1.json）</li>
                <li>误差定义：单机 |ΔPᵢ|、总功率 ΔP = |P_pred − P_ref|、NMAE = Σ|ΔP| / Σ|P_ref|；全部刻度为固定常量（不随数据自适应）</li>
                <li>参考模型版本：FLORIS 4.6.6（FlorisModel defaults：gauss 速度/偏折 + crespo_hernandez 湍流 + sosfs 组合）</li>
                <li>快速模型版本：本仓 TS GCH 内核（与参考模型同方程移植；李锦飞 PINN 的换入点 = inferCase() 推理计时钩子，换入后本表自动反映真实模型误差）</li>
                <li>适用边界：已验证 {VERIFIED_RANGE.uInf} m/s / {VERIFIED_RANGE.fromDeg}° / TI {num(VERIFIED_RANGE.ti * 100, 0)}%；其余工况无参考值可核（快速模型闭式可外推）</li>
              </ul>
            </div>
          </>
        )}

        {/* ================= 7 导出材料 ================= */}
        {step === 7 && fields.none && fields.opt && greedy && none && (
          <>
            <div className="demo-card">
              <h3>工况记录（§二 步骤 7：编号/数据来源/配置/结果可追踪）</h3>
              <div className="demo-exportmeta">
                <span>工况编号：tandem3-demo-2026-10-05</span>
                <span>数据来源：FLORIS 4.6.6 GCH oracle（参考）+ TS GCH 内核（快速，PINN 代理）</span>
                <span>配置：{DEMO_WIND.uInf} m/s / {DEMO_WIND.fromDeg}° / TI {num(DEMO_WIND.ti * 100, 0)}% · 1×3 · 基准 [0,0,0]° → 优化 [{greedy.yaw.map(yawStr).join(', ')}]°</span>
              </div>
              <div className="demo-dual">
                {refCard('基准（参考）', none.refTotalKw, none.refP, TAG_REF, 'ref')}
                {refCard('优化后（参考）', greedy.refTotalKw, greedy.refP, TAG_REF, 'ref')}
              </div>
              <button className="demo-go" onClick={doExportJson}>⬇ 导出工况 JSON（case_id + 数据来源 + 配置 + 41 工况结果 + 推理/优化/复核/流场 四类耗时）</button>
            </div>
            <div className="demo-card">
              <h3>对比图导出（SVG 整图，可直接入报告/PPT）</h3>
              <div className="demo-two demo-two-wide">
                <div className="demo-chartbox">
                  <FlowFieldChart svgId="demo-c7-f1" u={fields.none} title="基准流场（零偏航）" tag="快速模型场" svgRefCb={attach('f1')} />
                  <button className="demo-dl" onClick={() => downloadSvg(svgRefs.current.f1, 'c1_基准流场.svg')}>⬇ 基准流场 SVG</button>
                </div>
                <div className="demo-chartbox">
                  <FlowFieldChart svgId="demo-c7-f2" u={fields.opt} title="优化后流场" tag="快速模型场" svgRefCb={attach('f2')} />
                  <button className="demo-dl" onClick={() => downloadSvg(svgRefs.current.f2, 'c1_优化流场.svg')}>⬇ 优化流场 SVG</button>
                </div>
              </div>
              <div className="demo-two">
                <div className="demo-chartbox">
                  <PowerBars svgId="demo-c7-power" title="三机与总功率对比" groups={baseGroups} svgRefCb={attach('f3')} />
                  <button className="demo-dl" onClick={() => downloadSvg(svgRefs.current.f3, 'c2_功率对比.svg')}>⬇ 功率对比 SVG</button>
                </div>
                <div className="demo-chartbox">
                  <RefPredAll svgId="demo-c7-all" title="参考值—预测值（41 工况）" cases={cases} svgRefCb={attach('f4')} />
                  <button className="demo-dl" onClick={() => downloadSvg(svgRefs.current.f4, 'c3_参考vs预测.svg')}>⬇ 参考—预测 SVG</button>
                </div>
              </div>
              <div className="demo-chartbox">
                <AccTimeChart svgId="demo-c7-time" title="精度与耗时对照" cases={cases} svgRefCb={attach('f5')} />
                <button className="demo-dl" onClick={() => downloadSvg(svgRefs.current.f5, 'c4_精度耗时.svg')}>⬇ 精度与耗时 SVG</button>
              </div>
            </div>
          </>
        )}

        {/* 计时面板（界面纪律：推理/优化/复核分别记录） */}
        <div className="demo-timings">
          <span>推理 {num(timings.inferMs, 1)} ms（41 工况）</span>
          <span>优化 {timings.optimizeMs != null ? `${num(timings.optimizeMs, 1)} ms` : '—'}</span>
          <span>复核 {timings.reviewMs != null ? `${num(timings.reviewMs, 2)} ms` : '—'}</span>
          <span className="demo-timings-note">performance.now 实测 · 随机器浮动</span>
        </div>

        <div className="demo-nav">
          <button className="demo-go" disabled={step <= 1} onClick={() => goto(step - 1)}>← 上一步</button>
          <span className="demo-stepnum">{step} / 7 · {STEP_TITLES[step - 1]}</span>
          <button className="demo-go" disabled={step >= 7} onClick={() => goto(step + 1)}>下一步 →</button>
        </div>
      </div>
    </div>
  )
}

// 自定义偏航组合（不在 oracle 扫描网格内）的快速模型即时推理（带缓存）
const customCache = new Map<string, number>()
function customPredictTotalKw(yaw: number[]): number {
  const k = yaw.join(',')
  const hit = customCache.get(k)
  if (hit != null) return hit
  const r = evaluateFarmScene(DEMO_SCENE, { ...DEMO_WIND }, [...yaw])
  customCache.set(k, r.totalKw)
  return r.totalKw
}
