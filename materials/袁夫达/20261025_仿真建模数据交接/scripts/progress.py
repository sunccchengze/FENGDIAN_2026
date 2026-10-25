# -*- coding: utf-8 -*-
"""看训练进度：一条命令打印当前轮次、损失、最优轮次、早停倒计时和预计剩余时间。

用法
----
    # 看一次
    .\\.venv\\Scripts\\python.exe pinn_wind_data\\progress.py

    # 每 15 秒自动刷新，Ctrl+C 退出
    .\\.venv\\Scripts\\python.exe pinn_wind_data\\progress.py --watch

不需要 TensorFlow，纯读日志，随便哪个 python 都能跑。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Windows 控制台默认 GBK，进度条里的方块字符会报 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
DEFAULT_LOG = HERE / "out" / "training_log.txt"
BUNDLE = HERE.parent / "PINNs_multi_turbine_wake_simulation-outputchange" / "OutputChange" / "wind_iochanged_9ms"

EPOCH_RE = re.compile(r"^Epoch\s+(\d+)/(\d+)\s*$")
LOSS_RE = re.compile(
    r"-\s*(\d+)s\s*-\sloss:\s*([0-9.eE+-]+)\s*-\s*val_loss:\s*([0-9.eE+-]+)"
)
SPARK = "▁▂▃▄▅▆▇█"


def read_any_encoding(path: Path) -> str:
    """PowerShell 的 Tee-Object 默认写 UTF-16，Python 默认写 UTF-8，这里按 BOM 自动识别。"""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig", errors="replace")
    if raw[:1] == b"\x00" or raw[1:2] == b"\x00":
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def parse_log(path: Path) -> dict:
    if not path.is_file():
        return {"ok": False, "reason": f"找不到日志：{path}"}
    text = read_any_encoding(path)
    lines = text.splitlines()

    total = None
    current = 0
    records: list[tuple[int, float, float, int]] = []   # (epoch, loss, val_loss, sec)
    finished = False
    final_dir = None
    for raw in lines:
        line = raw.strip()
        m = EPOCH_RE.match(line)
        if m:
            current, total = int(m.group(1)), int(m.group(2))
            continue
        m = LOSS_RE.search(line)
        if m:
            records.append((current or len(records) + 1, float(m.group(2)), float(m.group(3)), int(m.group(1))))
            continue
        if "Trained model saved" in line:
            finished = True
            final_dir = line.split("saved:")[-1].strip()

    if total is None:
        return {"ok": False, "reason": "日志里还没有 Epoch 行（模型还在加载或数据校验中）"}
    return {
        "ok": True, "log": path, "total": total, "current": current,
        "records": records, "finished": finished, "final_dir": final_dir,
    }


def sparkline(values: list[float], use_log: bool = True) -> str:
    """损失跨几个数量级，用对数刻度画才能看出形状。"""
    if not values:
        return ""
    v = [math.log10(max(x, 1e-12)) for x in values] if use_log else list(values)
    lo, hi = min(v), max(v)
    if hi - lo < 1e-12:
        return SPARK[len(SPARK) // 2] * len(values)
    return "".join(
        SPARK[min(len(SPARK) - 1, int((x - lo) / (hi - lo) * (len(SPARK) - 1)))] for x in v
    )


def latest_report() -> dict | None:
    runs = [p for p in BUNDLE.glob("training_*")
            if p.is_dir() and (p / "training_report.json").is_file()]
    if not runs:
        return None
    runs.sort(key=lambda p: (p / "training_report.json").stat().st_mtime)
    return json.loads((runs[-1] / "training_report.json").read_text(encoding="utf-8"))


def render(state: dict, patience: int) -> str:
    if not state["ok"]:
        return f"[等待] {state['reason']}"

    total, current = state["total"], state["current"]
    recs = state["records"]
    done = len(recs)
    out = []

    # 进度条
    width = 36
    filled = int(width * min(done, total) / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = 100.0 * min(done, total) / total
    out.append(f"进度  [{bar}] {done}/{total}  ({pct:.0f}%)")

    if recs:
        epochs = [r[0] for r in recs]
        losses = [r[1] for r in recs]
        vals = [r[2] for r in recs]
        secs = [r[3] for r in recs]
        best_i = min(range(len(vals)), key=lambda i: vals[i])
        best_val = vals[best_i]
        since_best = done - 1 - best_i
        avg_s = sum(secs[1:]) / max(1, len(secs) - 1) if len(secs) > 1 else secs[0]

        out.append(f"轮次   当前第 {current} 轮 / 共 {total} 轮，已完成 {done} 轮")
        drop = 100 * (1 - best_val / max(vals[0], 1e-12))
        out.append(f"损失   train {losses[-1]:.5f}   val {vals[-1]:.5f}   "
                   f"最优 val {best_val:.5f}（第 {epochs[best_i]} 轮，较首轮下降 {drop:.1f}%）")
        out.append(f"曲线   train {sparkline(losses[-24:])}  (对数刻度, 左旧右新)")
        out.append(f"       val   {sparkline(vals[-24:])}")
        recent = ", ".join(f"{v:.5f}" for v in vals[-5:])
        out.append(f"近5轮 val  {recent}")
        out.append(f"早停   距最优已 {since_best} 轮，耐心上限 {patience} 轮"
                   f"（还剩 {max(0, patience - since_best)} 轮余量）")
        elapsed = timedelta(seconds=int(sum(secs)))
        remain = max(0, total - done) * avg_s
        out.append(f"耗时   已用 {elapsed}，平均 {avg_s:.0f} 秒/轮，"
                   f"跑满 200 轮还需约 {timedelta(seconds=int(remain))}")
        out.append(f"       （若在第 {epochs[best_i] + patience} 轮触发早停，"
                   f"约 {timedelta(seconds=int(max(0, epochs[best_i] + patience - done) * avg_s))} 后结束）")

    if state["finished"]:
        rep = latest_report()
        out.append("")
        out.append("[完成] 训练已完成" + (f"：{state['final_dir']}" if state["final_dir"] else ""))
        if rep:
            out.append(f"   轮次 {rep['epochs_completed']}，可训练参数 {rep['trainable_parameters']}，"
                       f"原权重未变 {rep['original_parameters_unchanged']}")
            out.append(f"   留出集误差：")
            for name in ("P1", "P2", "P3", "Ueff1", "Ueff2", "Ueff3"):
                m = rep["test_metrics"][name]
                unit = "kW" if name.startswith("P") else "m/s"
                val = m["MAE"] / 1e3 if unit == "kW" else m["MAE"]
                out.append(f"     {name:6s} MAE {val:8.1f} {unit}")
            out.append(f"   负输出 {rep['negative_test_output_count']} 个")
            out.append("   下一步：pinn_wind_data\\.venv-tf\\Scripts\\python.exe pinn_wind_data\\analyze_training.py")
    else:
        out.append("")
        out.append(f"（{datetime.now():%H:%M:%S} 刷新；训练进程仍在跑）")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--watch", action="store_true", help="每 N 秒刷新")
    ap.add_argument("--interval", type=int, default=15)
    ap.add_argument("--patience", type=int, default=30)
    args = ap.parse_args()

    while True:
        state = parse_log(args.log)
        body = render(state, args.patience)
        if args.watch:
            os.system("cls" if os.name == "nt" else "clear")
        print(body)
        if not args.watch or state.get("finished") or not state.get("ok"):
            if not args.watch:
                print("\n提示：加 --watch 可自动刷新")
            return 0
        time.sleep(max(2, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
