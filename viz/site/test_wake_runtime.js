#!/usr/bin/env node
/* 尾流页无浏览器运行桩：加载真实 data.js/data_3d.js/interp.js，执行页面内联脚本。 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const SITE = __dirname;

class ClassList {
  constructor() { this.names = new Set(); }
  toggle(name, force) {
    if (force === undefined) force = !this.names.has(name);
    if (force) this.names.add(name); else this.names.delete(name);
    return force;
  }
  add(name) { this.names.add(name); }
  remove(name) { this.names.delete(name); }
  contains(name) { return this.names.has(name); }
}

class ElementStub {
  constructor(id) {
    this.id = id;
    this.value = id === 'yawSlider' ? '0' : '';
    this.textContent = '';
    this.style = {};
    this.classList = new ClassList();
    this.attributes = {};
    this.listeners = {};
  }
  addEventListener(type, handler) { this.listeners[type] = handler; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
}

const html = fs.readFileSync(path.join(SITE, 'wake.html'), 'utf8');
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
const elements = new Map(ids.map(id => [id, new ElementStub(id)]));
const documentListeners = {};

global.window = global;
global.document = {
  hidden: false,
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new ElementStub(id));
    return elements.get(id);
  },
  addEventListener(type, handler) { documentListeners[type] = handler; },
};
global.addEventListener = function () {};

const plotCalls = [];
global.Plotly = {
  react(id, traces, layout, config) { plotCalls.push({ id, traces, layout, config }); },
};

function runFile(relative) {
  const source = fs.readFileSync(path.join(SITE, relative), 'utf8');
  vm.runInThisContext(source, { filename: relative });
}

runFile('assets/data.js');
runFile('assets/data_3d.js');
runFile('assets/js/interp.js');

const scriptBodies = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)]
  .filter(match => !/\bsrc\s*=/.test(match[1]))
  .map(match => match[2])
  .filter(body => body.includes('const W = window.WIND_DATA'));
if (scriptBodies.length !== 1) {
  throw new Error(`预期找到 1 个尾流运行脚本，实际 ${scriptBodies.length} 个`);
}
vm.runInThisContext(scriptBodies[0], { filename: 'wake.inline.js' });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function text(id) { return String(elements.get(id).textContent); }
function latestPlot(id) { return [...plotCalls].reverse().find(call => call.id === id); }

assert(plotCalls.length === 3, `初始渲染应创建 3 张图，实际 ${plotCalls.length}`);
assert(text('kP1') === '1754', `0° P1 错误：${text('kP1')}`);
assert(text('kP2') === '436', `0° P2 错误：${text('kP2')}`);
assert(text('kPtot') === '2190', `0° Ptot 错误：${text('kPtot')}`);
assert(text('kGain') === '0.00%', `0° 增益错误：${text('kGain')}`);
assert(latestPlot('fieldPlot') && latestPlot('powerPlot') && latestPlot('splitPlot'), '初始图表缺失');

const slider = elements.get('yawSlider');
assert(typeof slider.listeners.input === 'function', '滑块 input 监听器缺失');
slider.value = '25';
slider.listeners.input();

assert(plotCalls.length === 6, `+25° 后累计应渲染 6 次，实际 ${plotCalls.length}`);
assert(text('kP1') === '1459', `+25° P1 错误：${text('kP1')}`);
assert(text('kP2') === '909', `+25° P2 错误：${text('kP2')}`);
assert(text('kPtot') === '2368', `+25° Ptot 错误：${text('kPtot')}`);
assert(text('kGain') === '+8.13%', `+25° 增益错误：${text('kGain')}`);
assert(text('causePill').includes('离散最优 +25°'), `最优状态文案错误：${text('causePill')}`);
assert(latestPlot('fieldPlot').traces[0].z.length === 32, '速度场降采样行数应为 32');
assert(latestPlot('fieldPlot').traces[0].z[0].length === 64, '速度场降采样列数应为 64');
assert(latestPlot('fieldPlot').traces[0].colorscale[0][1] === '#00441b', '低速端应为森林绿');
assert(latestPlot('fieldPlot').traces[0].colorscale.at(-1)[1] === '#f7fcfd', '高速端应为浅薄荷');
assert(['fieldPlot', 'powerPlot', 'splitPlot'].every(id => latestPlot(id).layout.height === 330), '三张动态图高度应统一为 330px');
assert(latestPlot('splitPlot').layout.legend.y === 1.18, '功率分解图例未处于顶部安全区');

console.log('wake runtime: 0° and +25° data/plots passed');
