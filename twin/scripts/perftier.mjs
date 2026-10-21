// perftier.mjs — 三档画质基线探针：单帧渲染计数（calls/tris/lines/geom/textures）+ 帧时长分布
// 用法: node scripts/perftier.mjs [baseUrl] [w] [h] [quality,quality,...]
//   默认 http://127.0.0.1:4173/ 1280 720 high,medium,low
//   需先起服务：npm run build && npm run preview -- --port 4173
// 口径（重要）：
//   · 计数走 window.__aeolus_stats()（手动单帧计数，与 ?debug=1 同源），是**确定值**；
//   · 帧时长只作档间相对比较：沙箱是 SwiftShader 软渲染、核数极少，绝对 ms 无参考意义，
//     真机 GPU 才用 `npm run dev` + 本探针取实数（README「当前状态」表已注明此口径）。
//   · 顺序开页而非并发，避免并发抢 CPU 污染计时。
import puppeteer from 'puppeteer-core'
import chromium from '@sparticuz/chromium'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repoLibs = path.join(here, '..', 'nsslibs')
const base = process.argv[2] || 'http://127.0.0.1:4173/'
const w = Number(process.argv[3] || 1280)
const h = Number(process.argv[4] || 720)
const tiers = (process.argv[5] || 'high,medium,low').split(',')
const EXTRA = process.argv[6] || '' // R42：附加 query（如 layout=1x3）
// 固定机位 + 锁时刻：与 docs/research/round36 的对拍口径一致，跨轮可比
const CAM = 'cam=60,22,990&t=15'
const FRAMES = 30

// R42：每档单独起浏览器 —— 单浏览器连开 3 页在沙箱软渲染下会累积内存崩
// （ProtocolError/detached Frame），分进程隔离最稳。
async function runTier(q) {
  const browser = await puppeteer.launch({
    executablePath: await chromium.executablePath(),
    env: { ...process.env, LD_LIBRARY_PATH: repoLibs + ':/tmp/nsslibs' },
    args: [...chromium.args, '--no-sandbox', '--disable-gpu-sandbox', '--enable-unsafe-swiftshader'],
    defaultViewport: { width: w, height: h, deviceScaleFactor: 1 },
    headless: 'shell',
  })
  try {
    const page = await browser.newPage()
    const errs = []
  page.on('pageerror', (e) => errs.push(String(e).slice(0, 160)))
  await page.goto(`${base}?debug=1&q=${q}&${CAM}${EXTRA}`, { waitUntil: 'load', timeout: 90000 })
  await new Promise((r) => setTimeout(r, 22000))
  const stats = await page.evaluate(() => {
    const w = window
    return typeof w.__aeolus_stats === 'function' ? w.__aeolus_stats() : null
  })
  // 帧时长分布：连续 FRAMES 帧，返回中位/P90/最大（含首帧后长尖峰，见 treeField 延迟落位）
  const frameMs = await page.evaluate((n) => new Promise((res) => {
    const t = []
    let prev = performance.now()
    let i = 0
    const tick = () => {
      const now = performance.now()
      t.push(now - prev); prev = now
      if (++i < n) requestAnimationFrame(tick)
      else {
        t.sort((a, b) => a - b)
        res({ median: +t[Math.floor(n / 2)].toFixed(1), p90: +t[Math.floor(n * 0.9)].toFixed(1), max: +t[n - 1].toFixed(1) })
      }
    }
    requestAnimationFrame(tick)
  }), FRAMES)
    out[q] = { stats, frameMs, pageErrors: errs.slice(0, 3) }
    await page.close()
  } finally {
    await browser.close()
  }
}
const out = {}
for (const q of tiers) {
  await runTier(q)
  console.error('tier', q, 'done')
}
console.log(JSON.stringify(out, null, 1))
