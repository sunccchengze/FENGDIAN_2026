// 3D 风电场：9 台风机 3x3 阵列，转子旋转、策略辅助包络随偏航偏转、按功率着色、自动环绕。
// 坐标：x 顺风（来流从 -x 吹向 +x），y 竖直，z 横向。布局与 generate_array_data.py 一致。
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const A = window.WIND_DATA.array_opt;
const POS = [];
for (let r = 0; r < 3; r++)
  for (let c = 0; c < 3; c++)
    POS.push([r * 630, (c - 1) * 378]);

// ---------- 统一偏航与独立偏航策略定义 ----------
// 基准: 9台0° | 统一前排偏航: 第一排偏航30°,其余6台固定0° | 独立偏航: 前排30°,中排20°,后排0°
const MODES = {
  none:        { yaws: POS.map(() => 0), pwr: A.turbine_powers_none, total: A.power_none, label: '基准 0° (无协同)' },
  unified:     { yaws: POS.map((_p, i) => i < 3 ? A.unified_yaw : 0), pwr: A.turbine_powers_unified, total: A.power_unified, label: '第一排统一 +' + A.unified_yaw + '°' },
  independent: { yaws: A.greedy_yaws, pwr: A.turbine_powers_independent, total: A.power_independent, label: '独立逐排偏航 (推荐)' }
};

const canvas = document.getElementById('farm');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = false;

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xf1ede6, 2400, 5600);

const camera = new THREE.PerspectiveCamera(42, 1, 10, 9000);
camera.position.set(-1500, 1150, 2000);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.target.set(630, 70, 0);
controls.maxPolarAngle = Math.PI * 0.49;
controls.minDistance = 800; controls.maxDistance = 4400;

// 灯光
scene.add(new THREE.HemisphereLight(0xc9d6e5, 0xd8cfbe, 0.95));
const sun = new THREE.DirectionalLight(0xffffff, 1.15);
sun.position.set(-900, 1700, 800); scene.add(sun);
const fill = new THREE.DirectionalLight(0xb9c8dc, 0.35);
fill.position.set(900, 600, -900); scene.add(fill);

// 地面与网格
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(4600, 3200),
  new THREE.MeshStandardMaterial({ color: 0xe4ddce, roughness: 1, metalness: 0 }));
ground.rotation.x = -Math.PI / 2; ground.position.set(630, -2, 0);
scene.add(ground);
const grid = new THREE.GridHelper(4600, 30, 0xb2a998, 0xd3ccbf);
grid.position.set(630, 0, 0); grid.material.transparent = true; grid.material.opacity = 0.45;
scene.add(grid);

// 来流方向（风从 -x 来）与环境流动气流微粒
(function windDir() {
  const mat = new THREE.MeshStandardMaterial({ color: 0x8a9bad, roughness: 0.6, transparent: true, opacity: 0.7 });
  for (let i = 0; i < 6; i++) {
    const s = new THREE.Mesh(new THREE.ConeGeometry(16, 56, 18), mat);
    s.rotation.z = -Math.PI / 2;
    s.position.set(-1800 + i * 150, 90, -1300);
    scene.add(s);
  }
})();

// 环境来流流动风速气流系统（清晰可见的三维流动气流线段 + 发光微粒，沿 -x 吹向 +x）
const NUM_WIND_STREAKS = 120;
const streakPos = new Float32Array(NUM_WIND_STREAKS * 6); // 2 个顶点/段
const streakSpeeds = new Float32Array(NUM_WIND_STREAKS);
const streakLens = new Float32Array(NUM_WIND_STREAKS);

for (let i = 0; i < NUM_WIND_STREAKS; i++) {
  const sx = -2400 + Math.random() * 4800;
  const sy = 25 + Math.random() * 150;
  const sz = -1600 + Math.random() * 3200;
  const len = 90 + Math.random() * 120;
  streakPos[i * 6]     = sx;       streakPos[i * 6 + 1] = sy; streakPos[i * 6 + 2] = sz;
  streakPos[i * 6 + 3] = sx + len; streakPos[i * 6 + 4] = sy; streakPos[i * 6 + 5] = sz;
  streakSpeeds[i] = 320 + Math.random() * 260;
  streakLens[i] = len;
}
const streakGeo = new THREE.BufferGeometry();
streakGeo.setAttribute('position', new THREE.BufferAttribute(streakPos, 3));
const streakMat = new THREE.LineBasicMaterial({
  color: 0x547394,
  transparent: true,
  opacity: 0.75,
  linewidth: 2
});
const windStreaks = new THREE.LineSegments(streakGeo, streakMat);
scene.add(windStreaks);

// 发光气流微粒
const NUM_WIND_PARTICLES = 160;
const windPos = new Float32Array(NUM_WIND_PARTICLES * 3);
const windSpeeds = new Float32Array(NUM_WIND_PARTICLES);
for (let i = 0; i < NUM_WIND_PARTICLES; i++) {
  windPos[i * 3]     = -2400 + Math.random() * 4800;
  windPos[i * 3 + 1] = 30 + Math.random() * 140;
  windPos[i * 3 + 2] = -1500 + Math.random() * 3000;
  windSpeeds[i] = 340 + Math.random() * 240;
}
const windGeo = new THREE.BufferGeometry();
windGeo.setAttribute('position', new THREE.BufferAttribute(windPos, 3));
const windMat = new THREE.PointsMaterial({
  color: 0x6b8cae,
  size: 20,
  transparent: true,
  opacity: 0.85,
  depthWrite: false
});
const windParticles = new THREE.Points(windGeo, windMat);
scene.add(windParticles);

// 功率色阶：陶土(低) -> 雾蓝(中) -> 鼠尾草(高)
const P_MIN = 400, P_MAX = 1760;
function powerColor(p) {
  const t = Math.max(0, Math.min(1, (p - P_MIN) / (P_MAX - P_MIN)));
  const c = new THREE.Color(),
    low = new THREE.Color(0xb98484), mid = new THREE.Color(0x6b8cae), high = new THREE.Color(0x6f8761);
  if (t < 0.5) c.copy(low).lerp(mid, t * 2);
  else c.copy(mid).lerp(high, (t - 0.5) * 2);
  return c;
}

const HUB_H = 90, ROTOR_R = 63;
const towerMat = new THREE.MeshStandardMaterial({ color: 0xf3f0e8, roughness: 0.7 });
const nacMat   = new THREE.MeshStandardMaterial({ color: 0xeae5d8, roughness: 0.6 });
const bladeMat = new THREE.MeshStandardMaterial({ color: 0xf7f4ec, roughness: 0.45, side: THREE.DoubleSide });

function makeTurbine() {
  const g = new THREE.Group();
  const tower = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 5, HUB_H, 18), towerMat);
  tower.position.y = HUB_H / 2; g.add(tower);
  const nacelle = new THREE.Mesh(new THREE.BoxGeometry(22, 10, 13), nacMat);
  nacelle.position.set(0, HUB_H, 0); g.add(nacelle);

  // yaw 组（绕竖直 y 旋转；默认转子朝向 -x 来流）
  const yawGroup = new THREE.Group(); yawGroup.position.set(0, HUB_H, 0); g.add(yawGroup);
  const hub = new THREE.Mesh(new THREE.SphereGeometry(6.5, 18, 18),
    new THREE.MeshStandardMaterial({ color: 0xd8d2c4, roughness: 0.5 }));
  yawGroup.add(hub);
  // 自旋组（绕转子轴 x 旋转）
  const spinGroup = new THREE.Group(); yawGroup.add(spinGroup);
  for (let b = 0; b < 3; b++) {
    // 叶片沿 y 方向外伸；绕 x 旋转即自旋
    const blade = new THREE.Mesh(new THREE.BoxGeometry(3.5, ROTOR_R * 1.75, 2.2), bladeMat);
    blade.position.set(0, ROTOR_R * 0.88, 0);
    const bg = new THREE.Group(); bg.add(blade); bg.rotation.x = b * Math.PI * 2 / 3;
    spinGroup.add(bg);
  }
  // 默认转子朝向 -x（叶片在 y-z 平面），yaw 角为 0 时已正确，偏航时绕 y 转即可
  return { group: g, yawGroup, spinGroup };
}

function makeWake(yawDeg=0, startX=0, startZ=0) {
  // 3×3 策略模式使用可复现的物理启发式包络：中心线由偏航几何关系给出，
  // 外扩流管只承担控制策略示意，不冒充 fields_3d / fields_array 的数值速度场。
  const L = 950;
  const pts = extractWakeCenterline(startX, startX+L, startZ, yawDeg);
  // 确定性 meandering：用两组正弦扰动表达轻微摆动，刷新或切换策略时不随机漂移。
  pts.forEach((p,i)=>{
    const jitter = Math.sin((p.x*0.008)+i*0.15)*3.5 + Math.sin(p.x*0.021+i*0.37)*0.6;
    p.z += jitter;
    p.y += Math.sin(p.x*0.013+i*0.19)*0.5;
  });
  // 双层：外层宽缓边界层，内层核心亏损
  const outer = buildWakeLoft(pts, 58, 72, 0x7d9ebb, 0.16);
  const inner = buildWakeLoft(pts, 32, 48, 0x547394, 0.22);
  const g = new THREE.Group();
  // outer/Inner 都是 Group，取其 children 合并
  outer.children.forEach(c=>g.add(c.clone()));
  inner.children.forEach(c=>g.add(c.clone()));
  return g;
}

const turbines = [], wakes = [];

// ---------- 双机 FLORIS 数据模式：三维速度网格采样 + 辅助中心线包络 + 几何风机 ----------
const REAL = window.WIND_3D_REAL || {};
const realYaws = Object.keys(REAL).sort((a, b) => parseFloat(a) - parseFloat(b));
let realGroup = new THREE.Group(); realGroup.visible = false; scene.add(realGroup);
let realTurbines = [];

// 三线性插值采样 FLORIS 三维数值速度场
function sampleRealU(fd, x, y, z) {
  const xs = fd.x, ys = fd.y, zs = fd.z, u = fd.u;
  const nx = xs.length, ny = zs.length, nz = ys.length;
  if (x < xs[0] || x > xs[nx - 1] || y < ys[0] || y > ys[nz - 1] || z < zs[0] || z > zs[nz - 1]) return 8.0;
  let ix = 0; while (ix < nx - 2 && xs[ix + 1] < x) ix++;
  let il = 0; while (il < nz - 2 && ys[il + 1] < y) il++;
  let ih = 0; while (ih < ny - 2 && zs[ih + 1] < z) ih++;
  const tx = (x - xs[ix]) / (xs[ix + 1] - xs[ix]);
  const ty = (y - ys[il]) / (ys[il + 1] - ys[il]);
  const tz = (z - zs[ih]) / (zs[ih + 1] - zs[ih]);
  let val = 0;
  for (let dh = 0; dh <= 1; dh++)
    for (let dl = 0; dl <= 1; dl++)
      for (let dxx = 0; dxx <= 1; dxx++) {
        let v = u[ih + dh][dl ? il + 1 : il][dxx ? ix + 1 : ix];
        if (v === null || !isFinite(v)) v = 8.0;
        const w = (dxx ? tx : 1 - tx) * (dl ? ty : 1 - ty) * (dh ? tz : 1 - tz);
        val += v * w;
      }
  return val;
}

// 构建高精度 2D 水平流场截面云图 Canvas 纹理
function buildFlowTexture(fd, zHeight) {
  const W = 320, H = 160;
  const canvas2d = document.createElement('canvas');
  canvas2d.width = W; canvas2d.height = H;
  const ctx = canvas2d.getContext('2d');
  const imgData = ctx.createImageData(W, H);
  const data = imgData.data;

  const xMin = -200, xMax = 900;
  const yMin = -300, yMax = 300;
  const flowStops = [
    [0,68,27], [0,109,44], [35,139,69], [65,174,118], [102,194,164],
    [153,216,201], [204,236,230], [229,245,249], [247,252,253]
  ];

  for (let py = 0; py < H; py++) {
    // py=0 对应 yMax (+300), py=H-1 对应 yMin (-300)
    const yLat = yMax - (py / (H - 1)) * (yMax - yMin);
    for (let px = 0; px < W; px++) {
      const xDown = xMin + (px / (W - 1)) * (xMax - xMin);
      const uVal = sampleRealU(fd, xDown, yLat, zHeight);
      const idx = (py * W + px) * 4;

      // 与二维图同源的 ColorBrewer BuGn 反向顺序色阶：低速深绿，高速浅薄荷。
      const t = Math.max(0, Math.min(1, (uVal - 2.8) / 5.2));
      const scaled = t * (flowStops.length - 1);
      const lo = Math.min(flowStops.length - 2, Math.floor(scaled));
      const mix = scaled - lo;
      const r = Math.round(flowStops[lo][0] + (flowStops[lo + 1][0] - flowStops[lo][0]) * mix);
      const g = Math.round(flowStops[lo][1] + (flowStops[lo + 1][1] - flowStops[lo][1]) * mix);
      const b = Math.round(flowStops[lo][2] + (flowStops[lo + 1][2] - flowStops[lo][2]) * mix);
      const a = Math.round(225 - t * 150);
      data[idx] = r; data[idx + 1] = g; data[idx + 2] = b; data[idx + 3] = a;
    }
  }
  ctx.putImageData(imgData, 0, 0);

  const tex = new THREE.CanvasTexture(canvas2d);
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  return tex;
}

// 根据偏航几何关系构建辅助中心线；该线不是从速度场反演得到
function extractWakeCenterline(startX, endX, startLat, yawDeg) {
  const hubH = 90;
  const pts = [];
  const dx = 20;
  let curX = startX;
  const yawRad = yawDeg * Math.PI / 180;
  while (curX <= endX) {
    const shift = -Math.sin(yawRad) * (curX - startX) * 0.16;
    pts.push(new THREE.Vector3(curX, hubH, startLat + shift));
    curX += dx;
  }
  return pts;
}

function buildWakeLoft(pts, startRadius, expandRate, colHex, opacity) {
  const g = new THREE.Group();
  const numRings = pts.length;
  const numSegs = 24;
  const vertices = [], uvs = [], indices = [];

  for (let r = 0; r < numRings; r++) {
    const pt = pts[r];
    const dist = r / (numRings - 1);
    const rad = startRadius + dist * expandRate;
    for (let s = 0; s <= numSegs; s++) {
      const phi = (s / numSegs) * Math.PI * 2;
      const dy = Math.sin(phi) * rad;
      const dz = Math.cos(phi) * rad;
      vertices.push(pt.x, pt.y + dy, pt.z + dz);
      uvs.push(dist, s / numSegs);
    }
  }

  for (let r = 0; r < numRings - 1; r++) {
    for (let s = 0; s < numSegs; s++) {
      const a = r * (numSegs + 1) + s;
      const b = (r + 1) * (numSegs + 1) + s;
      const c = (r + 1) * (numSegs + 1) + (s + 1);
      const d = r * (numSegs + 1) + (s + 1);
      indices.push(a, b, d);
      indices.push(b, c, d);
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  geo.computeVertexNormals();

  const mat = new THREE.MeshStandardMaterial({
    color: colHex,
    roughness: 0.35,
    metalness: 0.1,
    transparent: true,
    opacity: opacity,
    side: THREE.DoubleSide,
    depthWrite: false
  });
  g.add(new THREE.Mesh(geo, mat));

  // 经纬肋线环
  const ringStep = Math.max(1, Math.floor(numRings / 4));
  for (let r = 1; r < numRings; r += ringStep) {
    const ringPts = [];
    const pt = pts[r];
    const rad = startRadius + (r / (numRings - 1)) * expandRate;
    for (let s = 0; s <= numSegs; s++) {
      const phi = (s / numSegs) * Math.PI * 2;
      ringPts.push(new THREE.Vector3(pt.x, pt.y + Math.sin(phi) * rad, pt.z + Math.cos(phi) * rad));
    }
    const rGeo = new THREE.BufferGeometry().setFromPoints(ringPts);
    const rMat = new THREE.LineBasicMaterial({
      color: 0x9db1c7,
      transparent: true,
      opacity: opacity * 1.5
    });
    g.add(new THREE.LineLoop(rGeo, rMat));
  }
  return g;
}

function buildRealFlow(yawKey) {
  try {
    const fd = REAL[yawKey]; if (!fd) return;
    while (realGroup.children.length) {
      const ch = realGroup.children[0]; realGroup.remove(ch);
      if (ch.geometry) ch.geometry.dispose();
      if (ch.material) {
        if (ch.material.map) ch.material.map.dispose();
        ch.material.dispose();
      }
    }
    realTurbines = [];

    const yawDeg = parseFloat(yawKey);
    const yawRad = yawDeg * Math.PI / 180;

    // 1. 三维平滑气动尾流流管
    const pts1 = extractWakeCenterline(0, 630, 0, yawDeg);
    const wakeMesh1 = buildWakeLoft(pts1, 63, 50, 0x6b8cae, 0.25 + wakeOpacity * 0.35);
    realGroup.add(wakeMesh1);

    const pts2 = extractWakeCenterline(630, 1100, 0, 0);
    const wakeMesh2 = buildWakeLoft(pts2, 63, 40, 0x8aa17a, 0.2 + wakeOpacity * 0.3);
    realGroup.add(wakeMesh2);

    // 2. 轮毂高度水平流场云图 (y=90m)
    const hubTex = buildFlowTexture(fd, 90);
    const hubPlaneGeo = new THREE.PlaneGeometry(1100, 600);
    const hubPlaneMat = new THREE.MeshBasicMaterial({
      map: hubTex,
      transparent: true,
      opacity: 0.55 + wakeOpacity * 0.35,
      side: THREE.DoubleSide,
      depthWrite: false
    });
    const hubPlane = new THREE.Mesh(hubPlaneGeo, hubPlaneMat);
    hubPlane.rotation.x = -Math.PI / 2;
    hubPlane.position.set(350, 90, 0);
    realGroup.add(hubPlane);

    // 3. 地面流场投影云图 (y=1.5m)
    const groundTex = buildFlowTexture(fd, 40);
    const groundPlaneMat = new THREE.MeshBasicMaterial({
      map: groundTex,
      transparent: true,
      opacity: 0.4 + wakeOpacity * 0.3,
      side: THREE.DoubleSide,
      depthWrite: false
    });
    const groundPlane = new THREE.Mesh(hubPlaneGeo, groundPlaneMat);
    groundPlane.rotation.x = -Math.PI / 2;
    groundPlane.position.set(350, 1.5, 0);
    realGroup.add(groundPlane);

    // 4. 与双机数值算例对应的几何风机
    [0, 630].forEach((px, ti) => {
      const t = makeTurbine(); t.group.position.set(px, 0, 0);
      t.yawGroup.rotation.y = (ti === 0 ? yawRad : 0);
      const m = window.WIND_DATA.multi, i8 = m.wind_speeds.indexOf(8), j = m.yaw_angles.indexOf(yawDeg);
      const pwr = ti === 0 ? m.p1[i8][j] : m.p2[i8][j];
      const lamp = new THREE.Mesh(new THREE.CylinderGeometry(8, 8, 5, 20),
        new THREE.MeshStandardMaterial({ color: powerColor(pwr), emissive: powerColor(pwr), emissiveIntensity: 0.8 }));
      lamp.position.y = 2.5; t.group.add(lamp);
      realGroup.add(t.group); realTurbines.push(t);
    });

  } catch (err) {
    console.error('buildRealFlow error:', err);
  }
}

POS.forEach(([x, z]) => {
  const t = makeTurbine(); t.group.position.set(x, 0, z); scene.add(t.group);
  // 策略辅助包络：初始按 0° 生成，确定性摆动只帮助观察控制方向
  const w = makeWake(0, x, z); scene.add(w);
  turbines.push(t); wakes.push(w);
  // 塔底功率灯
  const lamp = new THREE.Mesh(new THREE.CylinderGeometry(9, 9, 6, 22),
    new THREE.MeshStandardMaterial({ color: 0x6b8cae, emissive: 0x6b8cae, emissiveIntensity: 0.7, transparent: true, opacity: 0.92 }));
  lamp.position.y = 3; t.group.add(lamp); t.lamp = lamp;
});

let mode = 'none', view = 'schematic', realYaw = '+00';
let spinning = true, rotorSpin = true, wakeOpacity = 0.35, autoAngle = 0;

function setGroupVisibility(g, vis) { g.visible = vis; }

function applyMode() {
  const md = MODES[mode];
  turbines.forEach((t, i) => {
    const yawRad = md.yaws[i] * Math.PI / 180;
    t.yawGroup.rotation.y = yawRad;
    // 按新偏航角重建确定性策略辅助包络，不作为 CFD 等值面
    const [x, z] = POS[i];
    const oldW = wakes[i];
    scene.remove(oldW);
    // 释放旧几何
    oldW.traverse(ch=>{
      if(ch.geometry) ch.geometry.dispose();
      if(ch.material){
        if(ch.material.map) ch.material.map.dispose();
        ch.material.dispose();
      }
    });
    const newW = makeWake(md.yaws[i], x, z);
    newW.visible = wakeOpacity > 0.01;
    scene.add(newW);
    wakes[i] = newW;
    const c = powerColor(md.pwr[i]);
    t.lamp.material.color.copy(c); t.lamp.material.emissive.copy(c);
  });
  const base = MODES.none.total, gain = (md.total - base) / base * 100;
  document.getElementById('farmKpis').innerHTML =
    fkpi(Math.round(md.total) + ' kW', '全场总功率') +
    fkpi((gain >= 0 ? '+' : '') + gain.toFixed(1) + '%', '相对基准增益', gain > 0.5 ? 'up' : gain < -0.5 ? 'down' : 'flat') +
    fkpi(md.label, '当前策略', 'flat', true);
  document.getElementById('farmLegend').innerHTML =
    '<span><i style="background:#b98484"></i>低速尾流</span>' +
    '<span><i style="background:#6b8cae"></i>过渡</span>' +
    '<span><i style="background:#6f8761"></i>高速来流</span>';
}

function applyReal() {
  buildRealFlow(realYaw);
  if (realTurbines[0]) realTurbines[0].yawGroup.rotation.y = parseFloat(realYaw) * Math.PI / 180;
  if (realTurbines[1]) realTurbines[1].yawGroup.rotation.y = 0;
  // 使用 cases_multi.csv 导出的 8 m/s 双机 FLORIS 数值功率
  const m = window.WIND_DATA.multi, i8 = m.wind_speeds.indexOf(8);
  const j = m.yaw_angles.indexOf(parseFloat(realYaw));
  const p1 = m.p1[i8][j], p2 = m.p2[i8][j], ptot = m.ptot[i8][j];
  const base = m.ptot[i8][m.yaw_angles.indexOf(0)];
  const gain = (ptot - base) / base * 100;
  document.getElementById('farmKpis').innerHTML =
    fkpi(Math.round(p1) + ' / ' + Math.round(p2) + ' kW', '上游 / 下游 P₁ / P₂') +
    fkpi(Math.round(ptot) + ' kW', '全场总功率') +
    fkpi((gain >= 0 ? '+' : '') + gain.toFixed(1) + '%', '相对基准增益', gain > 0.5 ? 'up' : gain < -0.5 ? 'down' : 'flat');
  document.getElementById('farmLegend').innerHTML =
    '<span><i style="background:#b98484"></i>低速尾流</span>' +
    '<span><i style="background:#6b8cae"></i>过渡</span>' +
    '<span><i style="background:#6f8761"></i>高速来流</span>';
}

function setView(v) {
  view = v;
  const isReal = v === 'real';
  realGroup.visible = isReal;
  turbines.forEach(t => setGroupVisibility(t.group, !isReal));
  wakes.forEach(w => setGroupVisibility(w, !isReal && wakeOpacity > 0.01));
  document.getElementById('modeSeg').style.display = isReal ? 'none' : 'inline-flex';
  document.getElementById('yawWrap').style.display = isReal ? 'inline-flex' : 'none';
  controls.target.set(isReal ? 220 : 630, 70, 0);
  if (isReal) applyReal(); else applyMode();
}
function fkpi(v, l, cls, txt) {
  return '<div class="fkpi"><div class="fk-v ' + (cls || '') + '">' + v + '</div><div class="fk-l">' + l + '</div></div>';
}

// 控件
document.getElementById('viewSeg').addEventListener('click', e => {
  if (!e.target.dataset.view) return;
  setView(e.target.dataset.view);
  [...e.currentTarget.children].forEach(b => b.classList.toggle('active', b === e.target));
});
document.getElementById('modeSeg') ? document.getElementById('modeSeg').addEventListener('click', e => {
  if (!e.target.dataset.mode) return;
  mode = e.target.dataset.mode;
  [...e.currentTarget.children].forEach(b => b.classList.toggle('active', b === e.target));
  applyMode();
}) : null;
const realYawSel = document.getElementById('realYaw');
if (realYawSel) {
  realYaws.forEach(k => { const o = document.createElement('option'); o.value = k; o.textContent = (parseFloat(k) >= 0 ? '+' : '') + k + '°'; realYawSel.appendChild(o); });
  realYawSel.value = '+00';
  realYawSel.onchange = () => { realYaw = realYawSel.value; applyReal(); };
}
document.getElementById('wakeOpacity').oninput = function () {
  wakeOpacity = parseFloat(this.value);
  if (view === 'schematic') {
    wakes.forEach(w => { w.visible = wakeOpacity > 0.01; w.children[0].material.opacity = wakeOpacity; });
  } else {
    wakes.forEach(w => { w.visible = false; });
  }
  if (realGroup) {
    realGroup.traverse(ch => {
      if (ch.material && ch.material.transparent) {
        ch.material.opacity = Math.max(0.08, wakeOpacity * 0.9);
      }
    });
  }
};
document.getElementById('chkSpin').onchange = e => spinning = e.target.checked;
document.getElementById('chkRotor').onchange = e => rotorSpin = e.target.checked;

function resize() {
  const r = canvas.parentElement.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / r.height; camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);

const clock = new THREE.Clock();
function loop() {
  requestAnimationFrame(loop);
  const dt = clock.getDelta();
  if (rotorSpin) {
    const all = view === 'real' ? realTurbines : turbines;
    all.forEach(t => t.spinGroup.rotation.x += dt * 4.2);
  }
  // 更新环境来流气流线段与微粒
  const sArr = streakGeo.attributes.position.array;
  for (let i = 0; i < NUM_WIND_STREAKS; i++) {
    const dx = dt * streakSpeeds[i];
    sArr[i * 6]     += dx;
    sArr[i * 6 + 3] += dx;
    if (sArr[i * 6] > 2400) {
      const len = streakLens[i];
      sArr[i * 6]     = -2400;
      sArr[i * 6 + 3] = -2400 + len;
    }
  }
  streakGeo.attributes.position.needsUpdate = true;

  const wArr = windGeo.attributes.position.array;
  for (let i = 0; i < NUM_WIND_PARTICLES; i++) {
    wArr[i * 3] += dt * windSpeeds[i];
    if (wArr[i * 3] > 2400) wArr[i * 3] = -2400;
  }
  windGeo.attributes.position.needsUpdate = true;

  if (spinning) {
    autoAngle += dt * 0.12;
    const isReal = view === 'real';
    const cx = isReal ? 250 : 630, rad = isReal ? 950 : 1700;
    camera.position.x = cx + Math.cos(autoAngle) * rad * 0.9;
    camera.position.z = Math.sin(autoAngle) * (isReal ? 620 : 950);
    camera.position.y = (isReal ? 520 : 1080) + Math.sin(autoAngle * 0.5) * 60;
    camera.lookAt(cx, 70, 0);
  }
  controls.update();
  renderer.render(scene, camera);
}
resize(); applyMode(); loop();
