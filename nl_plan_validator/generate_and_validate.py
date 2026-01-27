import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Any


def load_steps(json_path: str) -> List[Dict[str, Any]]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    steps = data.get("steps")
    if not isinstance(steps, list):
        raise ValueError("JSON 中缺少 steps 数组")

    # 保持 step 顺序（若有 step 字段则按数值排序）
    if all(isinstance(s, dict) and "step" in s for s in steps):
        steps = sorted(steps, key=lambda x: x.get("step"))

    return steps


def format_action(action: str, args: Dict[str, Any]) -> str:
    """将单步动作转为 PDDL plan 行"""
    if args is None:
        args = {}

    # 保留 JSON 中的键顺序（Python3.7+ dict 保序）
    arg_values = list(args.values())

    parts = [action] + [str(v) for v in arg_values]
    return f"({ ' '.join(parts) })"


def build_plan_lines(steps: List[Dict[str, Any]], append_status: bool = True) -> List[str]:
    lines: List[str] = []
    for s in steps:
        action = s.get("action")
        if not action:
            raise ValueError(f"缺少 action 字段: {s}")
        args = s.get("args", {}) or {}
        lines.append(format_action(action, args))

    if append_status and not any(s.get("action") == "status" for s in steps):
        lines.append("(status complete)")

    return lines


def write_plan_file(lines: List[str], outdir: str, plan_name: str = None) -> str:
    os.makedirs(outdir, exist_ok=True)
    if not plan_name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_name = f"plan_{timestamp}.plan"
    path = os.path.join(outdir, plan_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


# -------------------------
# VAL runner
# -------------------------

def run_val(domain: str, problem: str, plan: str, binary: str = "validate") -> Dict[str, Any]:
    cmd = [binary, domain, problem, plan]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return {
        "plan_path": plan,
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "command": " ".join(cmd),
    }


def save_val_log(result: Dict[str, Any], log_dir: str, plan_name: str):
    os.makedirs(log_dir, exist_ok=True)
    stem, _ = os.path.splitext(plan_name)
    log_path = os.path.join(log_dir, f"{stem}.val.log")
    meta_path = os.path.join(log_dir, f"{stem}.val.json")

    # text log
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"time: {datetime.now().isoformat()}\n")
        f.write(f"command: {result['command']}\n")
        f.write(f"exit_code: {result['exit_code']}\n")
        f.write("\n--- stdout ---\n")
        f.write(result["stdout"] + "\n")
        if result["stderr"]:
            f.write("\n--- stderr ---\n")
            f.write(result["stderr"] + "\n")

    # compact json meta
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return log_path, meta_path


# -------------------------
# CLI
# -------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="从 NL plan JSON 生成 PDDL plan 并用 VAL 验证"
    )
    parser.add_argument("--input", default="data/nlplan/output.json", help="NL plan JSON 路径")
    parser.add_argument("--domain", default="data/inputs/domain.pddl", help="domain.pddl 路径")
    parser.add_argument("--problem", default="data/inputs/problem.pddl", help="problem.pddl 路径")
    parser.add_argument("--outdir", default="data/refinedpddl", help="生成的 plan 存放目录")
    parser.add_argument("--logdir", default="data/validate", help="VAL 日志存放目录")
    parser.add_argument("--plan-name", default=None, help="指定输出文件名（默认带时间戳）")
    parser.add_argument("--val-binary", default="validate", help="VAL 可执行名，默认 validate")
    parser.add_argument("--no-validate", action="store_true", help="仅生成 plan，不运行 VAL")
    parser.add_argument("--no-status", action="store_true", help="不自动追加 (status complete)")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        steps = load_steps(args.input)
        plan_lines = build_plan_lines(steps, append_status=not args.no_status)
        plan_path = write_plan_file(plan_lines, args.outdir, args.plan_name)
    except Exception as e:
        print(f"❌ 生成 plan 失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✔ 生成 plan: {plan_path}")

    if args.no_validate:
        return

    # 运行 VAL
    result = run_val(args.domain, args.problem, plan_path, args.val_binary)
    plan_filename = os.path.basename(plan_path)
    log_path, meta_path = save_val_log(result, args.logdir, plan_filename)

    print(f"▶ 命令: {result['command']}")
    print(result["stdout"])
    if result["stderr"]:
        print("--- stderr ---")
        print(result["stderr"])
    print(f"📝 VAL 日志: {log_path}")

    if result["success"]:
        print("✅ VAL 验证通过")
    else:
        print(f"⚠ VAL 验证失败，退出码 {result['exit_code']}")
        sys.exit(result["exit_code"] or 1)


if __name__ == "__main__":
    main()
