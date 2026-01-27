#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def sanitize_model_name(name: str) -> str:
    """Make model name filesystem-friendly by stripping path and replacing special chars."""
    tail = name.split("/")[-1]
    return re.sub(r"[^A-Za-z0-9._-]", "_", tail)


def default_run_id(model: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{sanitize_model_name(model)}"


def stream_run(cmd: list[str]):
    print(f"==> 执行: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="")

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"命令失败，退出码 {proc.returncode}: {' '.join(cmd)}")


def parse_args():
    parser = argparse.ArgumentParser(description="一键生成 NL 计划并用 VAL 验证的 demo")
    # 生成阶段参数（沿用原脚本默认值）
    parser.add_argument("--plan", type=Path, default=PROJECT_ROOT / "data/inputs/sample.plan")
    parser.add_argument("--prompt", type=Path, default=PROJECT_ROOT / "data/inputs/prompt.txt")
    parser.add_argument(
        "--template",
        type=Path,
        default=PROJECT_ROOT / "nl_plan_generator/prompts/pddl_to_nl.txt",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("MODEL_NAME", "local:Qwen/Qwen3-4B-Instruct-2507"),
        help="local 模型名（会用于 run_id）",
    )
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--verbose", action="store_true")

    # 验证阶段参数
    parser.add_argument("--domain", type=Path, default=PROJECT_ROOT / "data/inputs/domain.pddl")
    parser.add_argument("--problem", type=Path, default=PROJECT_ROOT / "data/inputs/problem.pddl")
    parser.add_argument("--val-binary", default="validate")
    parser.add_argument("--no-validate", action="store_true", help="仅生成，不跑 VAL")
    parser.add_argument("--no-status", action="store_true", help="不自动追加 (status complete)")

    parser.add_argument(
        "--run-id",
        help="输出目录名，默认使用 时间戳+模型名，例如 20260127_123045_Qwen3-4B-Instruct-2507",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    run_id = args.run_id or default_run_id(args.model)
    run_dir = PROJECT_ROOT / "data" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    nl_json = run_dir / "nlplan.json"
    plan_file = "plan.plan"

    gen_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "nl_plan_generator/generate_nl_plan.py"),
        "--plan",
        str(args.plan),
        "--prompt",
        str(args.prompt),
        "--template",
        str(args.template),
        "--output",
        str(nl_json),
        "--model",
        str(args.model),
        "--max-new-tokens",
        str(args.max_new_tokens),
        "--temperature",
        str(args.temperature),
    ]
    if args.verbose:
        gen_cmd.append("--verbose")

    val_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "nl_plan_validator/generate_and_validate.py"),
        "--input",
        str(nl_json),
        "--domain",
        str(args.domain),
        "--problem",
        str(args.problem),
        "--outdir",
        str(run_dir),
        "--logdir",
        str(run_dir),
        "--plan-name",
        plan_file,
        "--val-binary",
        str(args.val_binary),
    ]
    if args.no_status:
        val_cmd.append("--no-status")

    try:
        stream_run(gen_cmd)
        if not args.no_validate:
            stream_run(val_cmd)
    except Exception as exc:
        print(f"❌ demo 失败: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
