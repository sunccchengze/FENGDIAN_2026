// ================================================================
// 渲染相位冻结（R42 #1 · 2026-10-05）
// 背景：场景的波/粒子/转子/闪烁全部以**挂钟**为相位源（three.js Clock /
// performance.now），`?t=15` 只冻结了模拟小时，没冻结渲染相位 —— round41 §3.1
// 实测同构建自差 35.8% 像素 > 跨构建差 28.2%，像素差因此**不是**有效等价判据。
// `?freeze=1` 把所有可见相位统一换成固定常量，使同参数两次渲染逐像素一致，
// 像素差（abdiff）重新成为可用判据。**默认关闭，演示体验不变**。
// ================================================================

export const FROZEN_PHASE = 15 // 冻结相位（秒）：任意常量，取 15 与默认模拟小时同数

/** 纯函数版：给定 URL search 与挂钟相位，返回该帧应使用的渲染相位（可单测）。 */
export function phaseFor(search: string | null | undefined, live: number): number {
  if (!search) return live
  try {
    if (new URLSearchParams(search).get('freeze') === '1') return FROZEN_PHASE
  } catch {
    return live
  }
  return live
}

/** 浏览器端标志：?freeze=1 时冻结（取证开关，须与其它调试开关同闸：DEV 或 ?debug=1；
 *  node/selftest 环境恒 false，走挂钟） */
const FREEZE_ALLOWED =
  (typeof import.meta !== 'undefined' && import.meta.env?.DEV === true) ||
  (typeof location !== 'undefined' && new URLSearchParams(location.search).has('debug'))
export const FREEZE = FREEZE_ALLOWED && phaseFor(
  typeof location !== 'undefined' && typeof location.search === 'string' ? location.search : null,
  0,
) === FROZEN_PHASE

/** 相位适配：所有可见动画的相位源统一过这道闸（live = clock.elapsedTime / perf.now 秒） */
export function phaseT(live: number): number {
  return FREEZE ? FROZEN_PHASE : live
}
