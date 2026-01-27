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


def sanitize_case_name(case: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", case)


def find_first(existing: list[Path]) -> Path | None:
    for p in existing:
        if p.exists():
            return p
    return None


def resolve_case_files(case_dir: Path, global_prompt: Path, global_domain: Path) -> tuple[Path, Path, Path, Path]:
    """Given a case directory, pick plan/problem/prompt/domain paths."""
    plan = find_first(
        [
            case_dir / "plan.plan",
            case_dir / "planner.plan",
            case_dir / "sample.plan",
            case_dir / "input.plan",
        ]
    )
    if plan is None:
        # fallback to any .plan
        plan_candidates = sorted(case_dir.glob("*.plan"))
        plan = plan_candidates[0] if plan_candidates else None

    problem = find_first([case_dir / "problem.pddl"])
    if problem is None:
        problem_candidates = sorted(case_dir.glob("*problem*.pddl"))
        problem = problem_candidates[0] if problem_candidates else None

    prompt = global_prompt
    if (case_dir / "prompt.txt").exists():
        prompt = case_dir / "prompt.txt"

    domain = case_dir / "domain.pddl" if (case_dir / "domain.pddl").exists() else global_domain

    return plan, problem, prompt, domain


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
    parser.add_argument("--plan", type=Path, default=PROJECT_ROOT / "data/inputs/sample/planner.plan")
    parser.add_argument("--prompt", type=Path, default=PROJECT_ROOT / "data/inputs/sample/prompt.txt")
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
    parser.add_argument("--problem", type=Path, default=PROJECT_ROOT / "data/inputs/sample/problem.pddl")
    parser.add_argument("--val-binary", default="validate")
    parser.add_argument("--no-validate", action="store_true", help="仅生成，不跑 VAL")
    parser.add_argument("--no-status", action="store_true", help="不自动追加 (status complete)")
    parser.add_argument("--batch-dir", type=Path, help="批量模式：扫描该目录的子目录，每个子目录视为一个 case（默认 data/inputs）")
    parser.add_argument("--single", action="store_true", help="强制单案例模式，忽略 --batch-dir 默认行为")

    parser.add_argument(
        "--run-id",
        help="输出目录名，默认使用 时间戳+模型名，例如 20260127_123045_Qwen3-4B-Instruct-2507",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # 默认行为：无参数时运行批量模式，目录 data/inputs
    if not args.single and args.batch_dir is None:
        args.batch_dir = PROJECT_ROOT / "data" / "inputs"

    base_prefix = args.run_id or default_run_id(args.model)

    try:
        if args.batch_dir:
            batch_dir = args.batch_dir
            if not batch_dir.exists():
                raise FileNotFoundError(f"批量目录不存在: {batch_dir}")
            case_dirs = sorted([d for d in batch_dir.iterdir() if d.is_dir()])
            if not case_dirs:
                raise RuntimeError(f"批量目录 {batch_dir} 下没有子目录可用作 case")

            run_dir_base = PROJECT_ROOT / "data" / "runs" / base_prefix

            gen_cmd = [
                sys.executable,
                str(PROJECT_ROOT / "nl_plan_generator/generate_nl_plan.py"),
                "--batch-dir",
                str(batch_dir),
                "--run-id",
                base_prefix,
                "--output-base",
                str(PROJECT_ROOT / "data" / "runs"),
                "--prompt",
                str(args.prompt),
                "--template",
                str(args.template),
                "--model",
                str(args.model),
                "--max-new-tokens",
                str(args.max_new_tokens),
                "--temperature",
                str(args.temperature),
            ]
            if args.verbose:
                gen_cmd.append("--verbose")

            stream_run(gen_cmd)

            if not args.no_validate:
                for case_dir in case_dirs:
                    plan_path, problem_path, prompt_path, domain_path = resolve_case_files(
                        case_dir, args.prompt, args.domain
                    )
                    if not problem_path:
                        print(f"⚠ 跳过 {case_dir.name}: 找不到 problem.pddl", file=sys.stderr)
                        continue

                    case_name = sanitize_case_name(case_dir.name)
                    nl_json = run_dir_base / case_name / "nlplan.json"
                    if not nl_json.exists():
                        print(f"⚠ 跳过 {case_dir.name}: 未找到生成的 nlplan.json ({nl_json})", file=sys.stderr)
                        continue

                    run_dir = run_dir_base / case_name
                    run_dir.mkdir(parents=True, exist_ok=True)

                    plan_file = "plan.plan"
                    val_cmd = [
                        sys.executable,
                        str(PROJECT_ROOT / "nl_plan_validator/generate_and_validate.py"),
                        "--input",
                        str(nl_json),
                        "--domain",
                        str(domain_path),
                        "--problem",
                        str(problem_path),
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

                    stream_run(val_cmd)
        else:
            run_dir = PROJECT_ROOT / "data" / "runs" / base_prefix / "single"
            run_dir.mkdir(parents=True, exist_ok=True)

            nl_json = run_dir / "nlplan.json"
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
                "--run-id",
                base_prefix,
                "--case-name",
                "single",
                "--output-base",
                str(PROJECT_ROOT / "data" / "runs"),
                "--model",
                str(args.model),
                "--max-new-tokens",
                str(args.max_new_tokens),
                "--temperature",
                str(args.temperature),
            ]
            if args.verbose:
                gen_cmd.append("--verbose")

            stream_run(gen_cmd)

            if not args.no_validate:
                plan_file = "plan.plan"
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
                stream_run(val_cmd)
    except Exception as exc:
        print(f"❌ demo 失败: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
