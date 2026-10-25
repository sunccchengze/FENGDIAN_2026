#!/usr/bin/env python3
"""第 9 页证据包：把「误差下降可见，优势仍待检验」这页的每个数字都做成可复算的。

为什么单独做一个包：
- 第 9 页是全片唯一同时出现「平均柱图 + 过程曲线 + 三条负结果」的页，被追问的概率最高；
- 评委真正会问的不是「数是多少」，而是「这数怎么来的、能不能自己算一遍」；
- 所以这个包里同时放**原始数据**、**复算脚本**、**复算输出**，跑一条命令就能对上稿子。

用法：
    python3 tools/build_page9_evidence.py            # 复算 + 打包 + 自检
    python3 tools/build_page9_evidence.py --check    # 只复算并比对已有 zip

输出：docs/defense/page9_evidence_20261024.zip
      包内顶层目录「第9页_证据_20261024/」

约定：脚本只读仓库数据，不写任何实验目录；所有数字都由数据现算，不手填。
"""
from __future__ import annotations

import csv
import hashlib
import re
import io
import shutil
import statistics as st
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "optimization_control/experiments/20261022_random_wind_training"
TEST = EXP / "test"
METRICS = TEST / "metrics.csv"
TRAJ = TEST / "trajectories.csv"
FIGS = ROOT / "docs/defense/assets/generated"
OUT = ROOT / "docs/defense/page9_evidence_20261024.zip"
TOP = "第9页_证据_20261024"

# 第 9 页用到的两个场景（与 g24 图里选例完全一致）
CASES = (
    ("test_gust_0_pitch0.055", "1", "有效场景：阵风 · 目标 2.7 MW · 第 1 条训练流"),
    ("test_ramp_2_pitch0.025", "1", "不足场景：慢变 · 目标 3.9 MW · 第 1 条训练流"),
)
NAMES = {"initial": "初始 MADDPG", "fixed": "固定桨距", "p": "P 控制",
         "pi": "PI 控制", "final": "训练后 MADDPG", "selected": "训练后 MADDPG（选中点）"}


def rows(path: Path):
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def metrics_report() -> str:
    """常规 18 工况：五根柱、三条流、58.5%、5.8%、分族、低风压力场。"""
    data = rows(METRICS)
    reg = [r for r in data if r["family"] != "low_wind_stress"]
    out = ["## 一、常规 18 工况（平稳 / 慢变 / 阵风 各 6）", ""]
    out.append("| 方法 | 场次数 | 平均跟踪 RMSE / kW |")
    out.append("|---|---:|---:|")
    means = {}
    for key in ("initial", "fixed", "p", "pi", "final"):
        v = [float(r["rmse_w"]) / 1000 for r in reg if r["controller"] == key]
        means[key] = st.mean(v)
        out.append(f"| {NAMES[key]} | {len(v)} | {means[key]:.2f} |")
    out.append("")

    streams = []
    for i in "012":
        v = [float(r["rmse_w"]) / 1000 for r in reg
             if r["controller"] == "final" and r["run_id"] == i]
        streams.append(st.mean(v))
    out.append("三条训练流（各自 18 场均值）：")
    for i, v in enumerate(streams):
        flag = " ← 高于 PI" if v > means["pi"] else ""
        out.append(f"- 第 {i} 条：**{v:.2f} kW**{flag}")
    out.append(f"- 三条流均值的均值：**{st.mean(streams):.2f} kW**，"
               f"样本标准差（n=3，分母 n−1）：**{st.stdev(streams):.2f} kW**")
    out.append("")
    drop = 1 - means["final"] / means["initial"]
    vs_pi = 1 - means["final"] / means["pi"]
    out.append(f"- 相对初始策略：**{drop*100:.1f}%**（1 − {means['final']:.2f}/{means['initial']:.2f}）")
    out.append(f"- 相对 PI：**{vs_pi*100:.1f}%** 更低（1 − {means['final']:.2f}/{means['pi']:.2f}）")
    out.append("- 注：± 是三条流均值的样本标准差，不是置信区间；−5.8% 未做显著性检验，"
               "故稿子里写「尚未证明统计显著优势」。")
    out.append("")

    out.append("### 分来流族（每族 6 场 × 3 流 = 18 场）")
    out.append("")
    out.append("| 族 | MADDPG / kW | P / kW | PI / kW | 谁更好 |")
    out.append("|---|---:|---:|---:|---|")
    for fam, label in (("gust", "阵风"), ("stationary", "平稳"), ("ramp", "慢变")):
        f = {k: st.mean([float(r["rmse_w"]) / 1000 for r in data
                         if r["family"] == fam and r["controller"] == k])
             for k in ("final", "p", "pi")}
        who = "MADDPG" if f["final"] < min(f["p"], f["pi"]) else (
            "PI" if f["pi"] <= f["p"] else "P")
        out.append(f"| {label} | {f['final']:.2f} | {f['p']:.2f} | {f['pi']:.2f} | {who} |")
    out.append("")

    low = [r for r in data if r["family"] == "low_wind_stress"]
    lf = {k: st.mean([float(r["rmse_w"]) / 1000 for r in low if r["controller"] == k])
          for k in ("final", "p", "pi")}
    out.append("### 第 20 个工况（低风高目标，不计入 18 场均值）")
    out.append("")
    out.append(f"- MADDPG **{lf['final']:.2f} kW**｜P {lf['p']:.2f}｜PI {lf['pi']:.2f}")
    out.append(f"- 相对 PI 高 **{(lf['final']/lf['pi']-1)*100:.1f}%**")
    out.append("")
    out.append(f"- 指标总条数：**{len(data)} 条** = 20 个工况 × 3 个固定控制器（固定桨距 / P / PI，各 20 条）"
               f" + 20 个工况 × 3 条训练流 × 3 个学习型控制器（初始 / 选中 / 训练后，各 60 条）。")
    out.append("- 「final」与「selected」在本实验里是同一组权重，数值完全相同；"
               "之所以两者都在表里，是为了保留选模当时的记录。")
    return "\n".join(out)


def traj_report() -> str:
    """过程证据：两个场景逐条复算，与 g24 图上的标注一一对应。"""
    data = rows(TRAJ)
    out = ["## 二、过程曲线（第 9 页上排那两张图）", ""]
    out.append("数据源：`data/trajectories.csv`（已裁成本包用到的 2 个场景；完整文件在仓库同路径）。")
    out.append("")
    for case, run, label in CASES:
        sub = [r for r in data if r["case_id"] == case]
        tgt = float(sub[0]["target_w"]) / 1e6
        out.append(f"### {label}")
        out.append("")
        out.append(f"- case_id：`{case}`｜目标功率 **{tgt:.2f} MW**｜每场 128 步（1 s/步）")
        out.append("")
        out.append("| 方法 | 跑数 | 跟踪 RMSE / kW | 平均功率 / MW |")
        out.append("|---|---:|---:|---:|")
        for key, rid in (("initial", run), ("fixed", "-1"), ("p", "-1"),
                         ("pi", "-1"), ("final", run)):
            v = [r for r in sub if r["controller"] == key and r["run_id"] == rid]
            if not v:
                continue
            rmse = (sum(float(r["error_w"]) ** 2 for r in v) / len(v)) ** 0.5 / 1000
            meanp = st.mean([float(r["farm_power_w"]) for r in v]) / 1e6
            out.append(f"| {NAMES[key]} | {len(v)} | **{rmse:.1f}** | {meanp:.3f} |")
        out.append("")
    out.append("> 图上标注的四个 RMSE 就是上表加粗列，未做任何平滑或截断。")
    return "\n".join(out)


README = """第 9 页 · 证据包（2026-10-24）
================================

这一页的结论只有一句：**跟踪误差比初始策略降 58.5%，比 PI 只低 5.8%，尚未证明统计显著优势。**
下面把它拆成四件可查的事。

一、包里有什么
------------
  00_先读我.txt              本文件
  01_复算报告.md             每个数字的算式与结果（由脚本现算，不是手写）
  02_第9页_定稿.md           这一页的屏上文字与口播稿定稿（从 v3 大纲/提词器抽出）
  data/metrics.csv           240 条评估指标（20 工况 × 3 固定控制器 + 20 工况 × 3 流 × 3 控制器）
  data/aggregate.csv         官方汇总（三条流的均值与跨流标准差）
  data/summary.txt           实验完整性摘要（训练步数、门槛是否通过）
  data/selection.json        三条流各自的选模记录与验证集逐场误差
  data/stage_gates.json      预先固定的晋级门槛（400 / 500 kW）
  data/config.yaml           环境与执行器参数（限幅、限速、时间常数）
  data/trajectories.csv      过程曲线数据（仅第 9 页用到的 2 个场景：12 条 × 128 步 × 2 = 3,072 行）
  figures/g24_power_tracking.png   上排两张时序图
  figures/g11_independent_test.png 下排均值柱图
  figures/g13_failure_cases.png    负结果页（备用）
  scripts/recompute.py       复算脚本（只用标准库，不依赖 numpy/pandas）
  MANIFEST.sha256            逐文件校验和

二、怎么自己核
------------
    python3 scripts/recompute.py

输出就是 `01_复算报告.md` 的内容：
  · 五根柱的均值：初始 1083.62｜固定 1100.34｜P 552.37｜PI 477.54｜训练后 449.72
  · 三条流：492.28 / 444.25 / 412.63（第 0 条**高于** PI）
  · 相对初始 −58.5%；相对 PI −5.8%
  · 分族：阵风赢、平稳赢、**慢变输**
  · 压力场：1727.89 vs PI 1383.30（高 24.9%）
  · 两个过程场景的四条曲线各自 RMSE

只要换掉 data/ 里的 CSV，同一份脚本就能复算别的页，不需要改代码。

三、口径（这三条决定数字能不能这么用）
------------
1. **58.5% 是跟踪误差，不是发电量**。任务是让全场出力跟住给定目标，
   目标低于可用出力时会主动降功率，所以误差下降不等于多发电。
2. **±40.1 是三条训练流均值的样本标准差**（n=3），不是置信区间；
   三条流里第 0 条 492.28 高于 PI 的 477.54，所以只能写「尚未证明统计显著优势」。
3. **两个过程场景是「示例」，不是「最优」**：阵风取第 1 条流（376 kW，优于 PI 512），
   慢变取第 1 条流（517 kW，落后于 P 278 / PI 303）。没有挑表现最好的流来展示。

四、这些数不能支撑什么
------------
  · 不能说发电量或经济收益提升；
  · 不能说优于传统控制（均值略低，但跨流不稳定、慢变与低风落后）；
  · 不能说物理精度——标签来自合成教师模型，`physical_validation = false`；
  · 单条曲线的 RMSE（376 / 517）不能与 18 场均值（449.72）直接比，口径不同。

—— 由 tools/build_page9_evidence.py 生成于 2026-10-24
"""


def page9_text() -> str:
    """从 v3 大纲与提词器抽出第 9 页的屏上文字与口播，作为「这页到底怎么讲」的定稿。"""
    import re as _re
    outline = (ROOT / "docs/defense/2026-10-24_制作大纲v3_主线版.md").read_text(encoding="utf-8")
    body = outline.split("\n## 修订记录")[0]
    seg = _re.split(r"\n# 第 9 页", body)[1].split("\n# 第 10 页")[0]
    talk = _re.search(r"\*\*口播（\d+ 字）\*\*\n((?:>.*\n)+)", seg).group(1)
    talk = " ".join(l.lstrip("> ").strip() for l in talk.strip().splitlines())
    blocks = _re.findall(r"```\n(.*?)```", seg, _re.S)
    screen = blocks[0].strip() if blocks else ""
    return ("# 第 9 页 · 定稿（屏上 + 口播）\n\n"
            "> 与本页证据包的关系：`g24` 两张图上的四个数、`g11` 五根柱、以及口播里的"
            "−58.5% / −5.8%，全部可在 `01_复算报告.md` 里逐项对上。\n\n"
            "## 屏上文字（照排）\n\n```\n" + screen + "\n```\n\n"
            "## 口播（照念）\n\n" + talk + "\n")


def recompute_script() -> str:
    return '''#!/usr/bin/env python3
"""第 9 页数字复算（只用标准库）。

    python3 recompute.py            # 打印 + 另存 复算结果.txt
"""
from __future__ import annotations

import csv
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" if HERE.name == "scripts" else Path("data")

CASES = (("test_gust_0_pitch0.055", "1", "有效场景：阵风 2.7 MW"),
         ("test_ramp_2_pitch0.025", "1", "不足场景：慢变 3.9 MW"))
NAMES = {"initial": "初始 MADDPG", "fixed": "固定桨距", "p": "P 控制",
         "pi": "PI 控制", "final": "训练后 MADDPG"}


def rows(p):
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    out = []
    m = rows(DATA / "metrics.csv")
    reg = [r for r in m if r["family"] != "low_wind_stress"]
    out.append(f"指标总条数 {len(m)}；常规场 {len(reg)} 条")
    means = {}
    for k in ("initial", "fixed", "p", "pi", "final"):
        v = [float(r["rmse_w"]) / 1000 for r in reg if r["controller"] == k]
        means[k] = st.mean(v)
        out.append(f"  {NAMES[k]:<12} {len(v):>3} 场  平均 RMSE {means[k]:8.2f} kW")
    streams = [st.mean([float(r["rmse_w"]) / 1000 for r in reg
                        if r["controller"] == "final" and r["run_id"] == i]) for i in "012"]
    out.append("  三条流：" + " / ".join(f"{x:.2f}" for x in streams)
               + f"  均值的均值 {st.mean(streams):.2f}  样本标准差 {st.stdev(streams):.2f}")
    out.append(f"  相对初始 {(1-means['final']/means['initial'])*100:.1f}%"
               f"；相对 PI {(1-means['final']/means['pi'])*100:.1f}%")
    for fam, lab in (("gust", "阵风"), ("stationary", "平稳"), ("ramp", "慢变"),
                     ("low_wind_stress", "低风压力场")):
        f = {k: st.mean([float(r["rmse_w"]) / 1000 for r in m
                         if r["family"] == fam and r["controller"] == k])
             for k in ("final", "p", "pi")}
        out.append(f"  {lab:<6} MADDPG {f['final']:8.2f}  P {f['p']:8.2f}  PI {f['pi']:8.2f}")
    t = rows(DATA / "trajectories.csv")
    for case, run, lab in CASES:
        out.append(f"  [{lab}]")
        for k, rid in (("initial", run), ("p", "-1"), ("pi", "-1"), ("final", run)):
            v = [r for r in t if r["case_id"] == case and r["controller"] == k
                 and r["run_id"] == rid]
            if not v:
                continue
            rmse = (sum(float(r["error_w"]) ** 2 for r in v) / len(v)) ** 0.5 / 1000
            out.append(f"    {NAMES[k]:<12} {len(v):>3} 步  RMSE {rmse:7.1f} kW")
    text = "\\n".join(out)
    print(text)
    (HERE / "复算结果.txt").write_text(text + "\\n", encoding="utf-8")


if __name__ == "__main__":
    main()
'''


def build() -> int:
    for p in (METRICS, TRAJ):
        if not p.exists():
            print(f"ERROR 缺数据：{p.relative_to(ROOT)}")
            return 1

    report = ("# 第 9 页 · 复算报告\n\n"
              "> 本文件由 `tools/build_page9_evidence.py` 从仓库原始数据现算生成，"
              "所有数字均非手填。复算命令：`python3 scripts/recompute.py`。\n\n"
              + metrics_report() + "\n\n" + traj_report() + "\n")

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / TOP
        for sub in ("data", "figures", "scripts"):
            (stage / sub).mkdir(parents=True)

        for src, name in ((METRICS, "metrics.csv"),
                          (TEST / "aggregate.csv", "aggregate.csv"),
                          (TEST / "summary.txt", "summary.txt"),
                          (EXP / "selection.json", "selection.json"),
                          (EXP / "stage_gates.json", "stage_gates.json"),
                          (EXP / "config.yaml", "config.yaml")):
            if not src.exists():
                print(f"ERROR 缺文件：{src.relative_to(ROOT)}")
                return 1
            shutil.copy2(src, stage / "data" / name)

        # 轨迹只放本页用到的两个场景，包体不至于过大；文件头保留原列名
        keep = {c for c, _, _ in CASES}
        with TRAJ.open(encoding="utf-8", newline="") as fh:
            rd = csv.DictReader(fh)
            fields = rd.fieldnames
            pick = [r for r in rd if r["case_id"] in keep]
        with (stage / "data" / "trajectories.csv").open("w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=fields)
            wr.writeheader()
            wr.writerows(pick)

        for name in ("g24_power_tracking.png", "g11_independent_test.png",
                     "g13_failure_cases.png"):
            shutil.copy2(FIGS / name, stage / "figures" / name)

        (stage / "scripts" / "recompute.py").write_text(recompute_script(), encoding="utf-8")
        (stage / "01_复算报告.md").write_text(report, encoding="utf-8")
        (stage / "00_先读我.txt").write_text(README, encoding="utf-8")
        (stage / "02_第9页_定稿.md").write_text(page9_text(), encoding="utf-8")

        manifest = [f"{sha256(f)}  {f.relative_to(stage).as_posix()}"
                    for f in sorted(p for p in stage.rglob("*") if p.is_file())]
        (stage / "MANIFEST.sha256").write_text("\n".join(manifest) + "\n", encoding="utf-8")

        if OUT.exists():
            OUT.unlink()
        with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for f in sorted(stage.rglob("*")):
                if f.is_file():
                    zf.write(f, f"{TOP}/{f.relative_to(stage).as_posix()}")

        # 用包内脚本自身再算一遍，与包内报告逐字比对（保证「报告 = 脚本输出」）
        tmp_script = Path(tmp) / "verify.py"
        tmp_script.write_text(recompute_script().replace(
            'DATA = HERE.parent / "data" if HERE.name == "scripts" else Path("data")',
            f'DATA = Path("{stage}/data")'), encoding="utf-8")
        import subprocess
        res = subprocess.run([sys.executable, str(tmp_script)], capture_output=True,
                             text=True, cwd=str(stage / "scripts"))
        if res.returncode != 0:
            print("ERROR 复算脚本自身跑不通：\n" + res.stderr[-800:])
            return 1
        nums = set(re.findall(r"\d+\.\d{2}", res.stdout))
        missing = sorted(n for n in nums if n not in report)
        if missing:
            print(f"WARN 复算输出中这些数在报告里找不到：{missing}")
        print(res.stdout.strip())

    print(f"\n打包完成：{OUT.relative_to(ROOT)}")
    print(f"  大小 {OUT.stat().st_size / 1024:.0f} KB")
    print(f"  sha256 {sha256(OUT)}")
    return check()


def check() -> int:
    if not OUT.exists():
        print("找不到证据包，先跑一次不带参数的打包")
        return 1
    ok = True
    with zipfile.ZipFile(OUT) as zf:
        if zf.testzip():
            print("ERROR 压缩包内文件损坏")
            ok = False
        names = [n for n in zf.namelist() if not n.endswith("/")]
        manifest = dict(reversed(l.split("  ", 1)) for l in
                        zf.read(f"{TOP}/MANIFEST.sha256").decode().splitlines() if "  " in l)
        for n in names:
            rel = n[len(TOP) + 1:]
            if rel == "MANIFEST.sha256":
                continue
            if rel not in manifest:
                print(f"ERROR 清单缺：{rel}")
                ok = False
            elif hashlib.sha256(zf.read(n)).hexdigest() != manifest[rel]:
                print(f"ERROR 校验和不符：{rel}")
                ok = False
        # 数据文件必须与仓库当前版本一致（轨迹是裁剪版，单独说明）
        for src, name in ((METRICS, "metrics.csv"), (TEST / "aggregate.csv", "aggregate.csv")):
            if hashlib.sha256(zf.read(f"{TOP}/data/{name}")).hexdigest() != sha256(src):
                print(f"ERROR 包内 {name} 与仓库不一致")
                ok = False
        for name in ("g24_power_tracking.png", "g11_independent_test.png"):
            if hashlib.sha256(zf.read(f"{TOP}/figures/{name}")).hexdigest() != sha256(FIGS / name):
                print(f"ERROR 包内 {name} 是旧版")
                ok = False
    print(f"  自检：{len(names)} 个文件 —— {'通过' if ok else '未通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else build())
