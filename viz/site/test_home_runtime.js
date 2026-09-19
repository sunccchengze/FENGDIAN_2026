#!/usr/bin/env node
/* 首页数字风洞无浏览器运行桩：执行真实内联 Canvas 脚本，验证鼠标耦合、九机绘制和响应式重绘。 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const SITE = __dirname;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function runPage(name) {
  const html = fs.readFileSync(path.join(SITE, name), 'utf8');
  const start = html.indexOf('// 2. 首页 3×3 数字风洞');
  const end = html.indexOf('// 3. 数字进入视口滚动动画', start);
  assert(start >= 0 && end > start, `${name} 数字风洞脚本边界缺失`);
  const source = html.slice(start, end);

  const calls = [];
  const gradients = [];
  const context2d = {
    setTransform(...args) { calls.push(['setTransform', ...args]); },
    clearRect(...args) { calls.push(['clearRect', ...args]); },
    createLinearGradient(...args) {
      const stops = [];
      gradients.push(stops);
      return { addColorStop(offset, color) { stops.push([offset, color]); } };
    },
    beginPath() { calls.push(['beginPath']); },
    moveTo(...args) { calls.push(['moveTo', ...args]); },
    lineTo(...args) { calls.push(['lineTo', ...args]); },
    bezierCurveTo(...args) { calls.push(['bezierCurveTo', ...args]); },
    closePath() { calls.push(['closePath']); },
    stroke() { calls.push(['stroke']); },
    fill() { calls.push(['fill']); },
    arc(...args) { calls.push(['arc', ...args]); },
    save() { calls.push(['save']); },
    restore() { calls.push(['restore']); },
    translate(...args) { calls.push(['translate', ...args]); },
    scale(...args) { calls.push(['scale', ...args]); },
    fillRect(...args) { calls.push(['fillRect', ...args]); },
    strokeRect(...args) { calls.push(['strokeRect', ...args]); },
    fillText(...args) { calls.push(['fillText', ...args]); },
    set lineWidth(value) { this._lineWidth = value; },
    set strokeStyle(value) { this._strokeStyle = value; },
    set fillStyle(value) { this._fillStyle = value; },
    set font(value) { this._font = value; },
  };

  const listeners = {};
  const cssVars = new Map();
  let rect = { left: 0, top: 0, width: 520, height: 520 };
  const stage = {
    addEventListener(type, handler) { listeners[type] = handler; },
    getBoundingClientRect() { return rect; },
    style: { setProperty(key, value) { cssVars.set(key, value); } },
  };
  const canvas = {
    width: 0,
    height: 0,
    style: {},
    getContext(type) {
      assert(type === '2d', `${name} Canvas context 应为 2d`);
      return context2d;
    },
  };
  const yawValue = { textContent: '' };
  const documentListeners = {};
  let resizeCallback = null;

  const sandbox = {
    console,
    Math,
    performance: { now: () => 1000 },
    document: {
      hidden: false,
      getElementById(id) {
        return { windStage: stage, 'farm-stage-canvas': canvas, stageYawValue: yawValue }[id] || null;
      },
      addEventListener(type, handler) { documentListeners[type] = handler; },
    },
    window: null,
    requestAnimationFrame() { return 1; },
    cancelAnimationFrame() {},
    IntersectionObserver: class {
      constructor(callback) { this.callback = callback; }
      observe() {}
    },
    ResizeObserver: class {
      constructor(callback) { resizeCallback = callback; }
      observe() {}
    },
  };
  sandbox.window = sandbox;
  sandbox.window.devicePixelRatio = 1;
  sandbox.window.matchMedia = () => ({ matches: true });
  sandbox.window.addEventListener = () => {};

  vm.runInContext(source, vm.createContext(sandbox), { filename: `${name}.wind-stage.js` });

  assert(canvas.width === 520 && canvas.height === 520, `${name} 初始 Canvas 尺寸错误：${canvas.width}×${canvas.height}`);
  assert(typeof listeners.pointermove === 'function', `${name} 缺少 stage pointermove 监听器`);
  assert(typeof listeners.pointerleave === 'function', `${name} 缺少 stage pointerleave 监听器`);
  assert(typeof resizeCallback === 'function', `${name} ResizeObserver 未注册`);
  const turbineLabels = calls.filter(call => call[0] === 'fillText' && /^T[1-9]$/.test(String(call[1])));
  assert(turbineLabels.length >= 9, `${name} 初始绘制未覆盖九台风机标签：${turbineLabels.length}`);
  assert(calls.some(call => call[0] === 'bezierCurveTo'), `${name} 未绘制尾流包络`);
  assert(gradients.some(stops => stops.length >= 2), `${name} 未绘制连续流线渐变`);

  for (let i = 0; i < 36; i++) listeners.pointermove({ clientX: 520, clientY: 230 });
  const yaw = Number.parseFloat(yawValue.textContent);
  assert(yaw > 20 && yaw <= 25, `${name} 鼠标右移后第一排偏航响应错误：${yawValue.textContent}`);
  assert(cssVars.get('--stage-x') === '100.0%', `${name} 鼠标光斑横坐标未耦合：${cssVars.get('--stage-x')}`);
  assert(cssVars.get('--drift-x') === '3.50px', `${name} 空间视差未耦合：${cssVars.get('--drift-x')}`);
  assert(!calls.some(call => call[0] === 'fillText' && /kW/.test(String(call[1]))), `${name} 出现无来源动态功率读数`);

  rect = { left: 0, top: 0, width: 390, height: 620 };
  resizeCallback();
  assert(canvas.width === 390 && canvas.height === 620, `${name} 移动端响应式重绘错误：${canvas.width}×${canvas.height}`);

  listeners.pointerleave();
  assert(cssVars.get('--drift-x') === '0px' && cssVars.get('--drift-y') === '0px', `${name} 鼠标离开后视差未复位`);
  assert(typeof documentListeners.visibilitychange === 'function', `${name} 标签页休眠监听器缺失`);
}

runPage('index.html');
runPage('index_v2.html');
console.log('home runtime: digital wind tunnel pointer, canvas and responsive redraw passed');
