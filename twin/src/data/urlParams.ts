// ================================================================
// URL 参数读写（2026-10-25 解冻新增）
// ----------------------------------------------------------------
// 为什么单独一个模块：顶栏三个控件（布局、七步演示、以及将来可能的其它开关）
// 都是「改一个 query 参数 → 整页导航」，如果各写一份，参数保留/覆盖/去重就会各自漂移。
// 这里只做一件事：**给定地址，只改指定参数，其余原样保留**（含 hash）。
//
// 约定：
//   · setParamHref(href, k, null) = 删除该参数（用于「退出演示」）；
//   · 一律用 set/delete，不用 append —— 同一参数不允许出现两次（旧实现手拼字符串踩过这坑）；
//   · 纯函数，不读全局、不碰 DOM，selftest 直接断言。
// ================================================================

/** 只改 `key` 一个查询参数，其余参数与 hash 原样保留。`value === null` 表示删除。 */
export function setParamHref(href: string, key: string, value: string | null): string {
  const url = new URL(href)
  if (value === null) url.searchParams.delete(key)
  else url.searchParams.set(key, value)
  return url.toString()
}

/** 七步演示面板的入口/出口。
 *  · 打开：必须 `demo=1` **且** `layout=1x3`（演示数据只对三机串列成立，见 DemoPanel 的守卫）；
 *  · 关闭：只删 `demo`，**保留 layout** —— 用户可能已经手动切到 1×3 在看三机，不该被顺手改回去。
 *  · step / q 等其它参数保持不动（从第 5 步退出再进来还在第 5 步）。 */
export function demoHref(href: string, open: boolean): string {
  if (!open) return setParamHref(href, 'demo', null)
  return setParamHref(setParamHref(href, 'layout', '1x3'), 'demo', '1')
}

/** 当前地址是否已打开演示面板（与 App.tsx 的 `has('demo')` 同口径）。 */
export function isDemoOpen(search: string | null | undefined): boolean {
  if (!search) return false
  return new URLSearchParams(search).has('demo')
}

// ----------------------------------------------------------------
// 演示出片模式 `?hud=clean`
// ----------------------------------------------------------------
// 只隐**内部控件**（声场 / 布局 / 七步 / 画质），保留标题、挂钟、数据面板、
// 三类角标与页脚声明 —— 出片时不许「干净」到把口径角标也一起去掉。
// 注意：它**不受 ?debug=1 门禁**（这是演示模式，不是调试开关）。
export function isCleanHud(search: string | null | undefined): boolean {
  if (!search) return false
  const v = new URLSearchParams(search).get('hud')
  return v === 'clean' || v === 'off' || v === '0'
}

/** 把 clean 状态写到 <body data-hud-clean>（CSS 用属性选择器，不依赖 React 重渲染）。 */
export function applyCleanHud(doc: Document, search: string | null | undefined): boolean {
  const clean = isCleanHud(search)
  if (clean) doc.body.setAttribute('data-hud-clean', '')
  else doc.body.removeAttribute('data-hud-clean')
  return clean
}

/** 出片模式下的完整地址（供顶栏/文档给出可复制链接）。 */
export function cleanHudHref(href: string, clean: boolean): string {
  return setParamHref(href, 'hud', clean ? 'clean' : null)
}
