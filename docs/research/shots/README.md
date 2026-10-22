# 截图验货记录

> **2026-09-13（R38-T2）起本目录是全仓唯一证据树**：原 `twin/docs/research/shots/` 的 R30–R34 自截图
> （21 个文件）已 `git mv` 进来；`twin/shots/` 下 16 个 0 字节 PNG（崩溃残留的"分步 A/B 序列"＝假证据）已删除。
> 下方清单为历轮**原始登记**，按时间追加，不改写历史措辞；树结构与规矩见文末两节。


- `r4_final_holo.png`：统一全息风机的上一版基线。
- `r5_holo_real_transparent_final.png`：R5，NREL 真实几何初版全息化（保留供对比）。
- `r6_holo_real_tinted.png`：R6，降低能量值与线框不透明度后的冰青版本，避免白色实体观感。
- `r7_white_no_turbine_bloom.png`：R7，按用户反馈改为纯白线条，并将风机从加色泛光路径中收回，远景保持清晰轮廓。
- `r9_extended_closeup_t07.png`：R9，开场巡航延长到约 28 秒，最终推进到 T07 近景以检查真实翼型线框。
- `r10_low_angle_closeup.png`：R10，终点改为低机位轻微仰视，主风机下半段自然出框，贴近用户参考构图。
- `r11_continuous_spline_intro.png`：R11，改为单条连续 Catmull-Rom 运镜轨迹，经过全景构图节点时不停顿，最终保持低机位轻微仰视。
- `r12_drone_aerial_showcase.png`：R12，加入正上方俯瞰、远处绕场、快速前推、机组间穿梭与机身侧倾节点，开场总长约 34 秒。
- `r17_no_bloom_white_edges.png`：R17，关闭 Bloom 后的开场帧，用于验证天空下半球无指数溢出白团、风机轮廓保持纯白。

截图脚本在沙箱中使用 SwiftShader；其边缘颗粒属于软件渲染伪影，真机 GPU 预览会更干净。

## v3 交付轮证据（2026-08-28，`?debug=1` 固定机位 + `&t=` 时刻锁定，可复现）
- `after_hero_1920.png`：P0 后基线，1920×1080，`?t=10.2&cam=0,22,990,0,22,-340`。对应"前"图：`w1_south_hero.png`。
- `after_az92_east.png` / `after_az272_west.png` / `after_az182_north.png`：三方位视角巡检（白线均亮 210–218，无变暗；docs/08 §〇）。
- `after_rotor_upwind_closeup.png` / `after_rotor_downwind_closeup.png`：A4 转子迎风近距对拍（北侧见叶盘正面，南侧见机舱尾锥）。
- `after_optimize.png`：E3/E6 联动闭环实拍——一键寻优后 5 路滑杆停在 −1.5…−33°、告警卡（偏航偏差超限·可定位）、功率 4.82→6.00MW（+24.3%）、wake 40.9→26.5%。
- `after_curtail_12mw.png`：研究内容③闭环——指令 12MW → total=12.00MW、9 机 curtail、DERATE 告警。
- `after_wake_veil_on.png` / `after_wake_veil_off.png`：同 t 同相位真 A/B（abdiff：31,457 显著像素，集中于轮毂高走廊与尾流羽带；粒子亮度 P50=122/P90=243）。
- `after_hero_noveil.png`：hero 机位关纱对照。
- `after_narrow_1280.png` / `after_mobile_390.png`：窄屏/竖屏适配（等比居中+竖屏提示条，无溢出）。
注：SwiftShader 软渲染边缘颗粒为沙箱伪影；真机 GPU 更干净。旧 `w*/r*` 图仍为各轮历史基线，未删除。

## round24 夜间压暗证据（2026-08-30）
- `r24-night-closeup-before.png` / `r24-night-closeup-after.png`：夜间特写 A/B（t=23 同月光角，cam=35,22,200）——地面 meanL 46.4→~39.6，中频亮带 49%→28%（棱柱侧面青蓝→暗色）。
- `r24-night-hero-after.png`：夜间英雄机位 after（r23 画面中央"全场功率总览"3D 标注已消失，其余 4 标注仍在）。
- `r24-day-closeup-before.png`：日间特写 before（t=12，cam=35,22,200），after 在 round25 重拍。
- `r24-intro8s-after.png`：round24 开场 8s 渲染验证（相机按剖面表到位，无崩溃）。
- `r24-night-hero-after.png` / `r24-day-closeup-before.png` 等前值用于 round25 前后对拍。

## round25 开场丝滑 + 日间/基线证据（2026-08-30）
- `r25-intro8s-after.png` / `r25-intro20s-after.png` / `r25-intro30s-after.png`：开场 8/20/30 秒精确锚点帧（`?introT=<s>` 冻结开场时钟，消除软渲染 waitMs 漂移），相机分别贴 T03 附近、T05/T07 对角穿场、T07 前低机位终点，与速度剖面表一致。
- `r25-hero-1920.png`：英雄机位巡检（`?t=10.2&cam=0,22,990`，1920×1200）。
- `r25-az-east.png` / `r25-az-west.png`：东/西两方位巡检。
- `r25-day-closeup-after.png`：日间地面 A/B after（t=12，cam=35,22,200，1920×1200，与 r24-day-closeup-before.png 同构图）。像素测量：亮带 p90 58.7→50.8（+地面整体下沉），中位色相 203.1→202.8 基本不动；round24 表格里"中位色相应 201→>207"的目标因白线稿/电缆等线稿像素参与统计未直接复现，但亮带收敛是主指标，已完成。
- `r25-baseline-dawn-0612-after.png` / `r25-baseline-morning-0800-after.png`：日间参考基线双帧同机位对比 after（cam=0,22,990，q=high）。实测风机亮边 77.6→77.8（基本一致，无回归）；天空读数差为极光/星空随 uTime 动画的相位噪声（SkyAurora.tsx 证），非 LightRig 改动。
```

## 热键机位 4789 修复证据（2026-09-06，`?intro0=1&t=10` + 真实按键链路，可复现）
- `hot4789_before_4.png` / `hot4789_after_4.png`：4 号 T04 平视——修前塔筒顶天立地双裁只剩机舱+断叶；修后转子三叶全框 3/4 侧视。
- `hot4789_before_7.png` / `hot4789_after_7.png`：7 号 T07 仰拍——修前机舱巨物特写桨叶出框；修后水线到叶尖全塔+转子。
- `hot4789_before_8.png` / `hot4789_after_8.png`：8 号 T08 仰拍——修前三叶尖三方出框；修后对称正面仰拍居中。
- `hot4789_before_9.png` / `hot4789_after_9.png`：9 号 T09 仰拍——修前塔筒特写；修后全塔+转子，海岛+集电线路前景。

## 去雾恢复证据（2026-09-06，`?cam=2.6,17,1393,0,22,-340&t=10` hero 机位，可复现）
- `fog_before_022.png` / `fog_after_013.png`：恢复 R32-C-round4 用户已验收的雾密度（0.00022→0.00013，
  系 a98a2eb 合并时丢失的 1 行）；远峰雪岩对比恢复、中景山体脱灰，空气感保留。

## 各轮图片的归属（合并后速查）

| 位置 | 内容 | 正文说明在哪 |
|---|---|---|
| `r30_base_*.png`、`r31_*.png`（平铺） | R30 海洋重构基线 / R31 开放外海与接地投影 | `docs/research/round30_海洋重构.md`、`round31_开放外海与接地投影.md` |
| `r32/` `r33/` `r34/` | R32 分形海岸线 · R33 草地实验（未挂载）· R34 海洋真实化 | `docs/10_R28-R32_地形海洋重做.md`、`docs/09_R34_海洋真实化.md`；**三个目录各有一份 README**（补 docs/10 挂账） |
| `r29_ocean_*.png`、`r29b_*.png`（平铺） | R29 海洋地面 | `docs/research/round29_海洋地面.md`（R38 已把表内临时名改为实际文件名） |
| `r36/`（含 `moon/`、`nightland/`、`gold/`） | R36 岸距/碎浪/远岸森林、R36b 月落、R36c 夜陆、R37 色温 | `docs/research/round36_海岸真实化与远岸森林.md` |
| `after_*.png`、`before_*.png`、`hot4789_*`、`fog_*` | v3 交付轮与各专项对拍 | `docs/08_合并评审_最终清单.md` |

## 两条硬规矩（已进 `npm run selftest`，R38 起）

1. **不许空壳证据**——`docs/**` 与 `image-search/**` 下任何图片为 0 字节即自检失败；
2. **不许断链**——`docs/**/*.md` 引用的每个 `<文件名>.png`（独立 token；通配符、`<占位符>` 与命令行示例除外——写占位符请一律用尖括号，
   否则守卫会把它当真链接）
   必须能在证据树里找到同名文件。改名/移树而漏改文档会直接红。

跑法 `cd twin && npm run selftest`（末两项即本目录守卫）。例外表 `GONE` 只登记
"按裁决删除、历史文档仍会提及"的资产（现为 Round-9 删的 `sky-realistic-cyan.png`，1.9 MB 无许可位图），
**不许为了通过检查往里塞**。

## 拍摄 SOP（新轮次照抄）

```bash
bash twin/scripts/bootstrap.sh                    # 沙箱重置后恢复 chromium + NSS 桩库
cd twin && npm run dev -- --host 0.0.0.0
node scripts/shot.mjs 'http://127.0.0.1:5173/?debug=1&t=10&cam=0,22,990' \
  ../docs/research/shots/rNN_<主题>.png 12000 1920 1080
python3 scripts/abdiff.py before.png after.png rNN_label   # 帧差（同相位才算 A/B）
python3 scripts/framestats.py before.png after.png         # 亮度/饱和，守"不得更亮"红线
```
沙箱是 SwiftShader 软渲染：**像素可读，帧率数字一律不可引用**。

## 证据孤儿登记（2026-10-22 全仓审计 AUD-20）

按文件名全仓检索：本目录 230 张中约 85 张没有任何文档引用（约 95.9 MiB），
包括失败尝试、A/B 对照与未及登记的中间帧。口径（用户「不要删除成果」）：
中期答辩前不删不动；新截图入库须由引用文档同轮登记文件名；结题后统一分诊
（补引用 / 转记失败尝试 / 经裁定归档 Release 后再议回收体积）。
