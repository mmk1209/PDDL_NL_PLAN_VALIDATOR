import argparse
import json
import os
from pathlib import Path

from llmcaller import LocalLLMCaller

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_user_prompt(plan_text: str, template_text: str, extra_prompt: str | None) -> str:
    prompt = template_text.replace("{{PDDL_PLAN}}", plan_text)
    if extra_prompt:
        prompt = f"{prompt}\n\n{extra_prompt.strip()}"
    return prompt


def find_first(candidates: list[Path]) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


def sanitize_case_name(case: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in case)


def resolve_case_files(case_dir: Path, global_prompt: Path) -> tuple[Path | None, Path]:
    """Return (plan_path, prompt_path) for a case dir."""
    plan = find_first(
        [
            case_dir / "plan.plan",
            case_dir / "planner.plan",
            case_dir / "sample.plan",
            case_dir / "input.plan",
        ]
    )
    if plan is None:
        plan_candidates = sorted(case_dir.glob("*.plan"))
        plan = plan_candidates[0] if plan_candidates else None

    prompt = case_dir / "prompt.txt" if (case_dir / "prompt.txt").exists() else global_prompt
    return plan, prompt


def parse_args():
    parser = argparse.ArgumentParser(description="Generate NL JSON plan from PDDL plan using local LLM.")
    parser.add_argument(
        "--plan",
        type=Path,
        default=PROJECT_ROOT / "data" / "inputs" / "sample" / "planner.plan",
        help="Path to PDDL plan file (single mode).",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=PROJECT_ROOT / "data" / "inputs" / "sample" / "prompt.txt",
        help="Path to required user task prompt text.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=BASE_DIR / "prompts" / "pddl_to_nl.txt",
        help="Path to system/user prompt template with {{PDDL_PLAN}} placeholder.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "nlplan" / "output.json",
        help="Where to write JSON output (single mode default).",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=PROJECT_ROOT / "data" / "runs",
        help="Base directory for outputs in batch mode or when --run-id is provided.",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="When provided, outputs are written to output-base/run-id/<case>/nlplan.json",
    )
    parser.add_argument(
        "--case-name",
        type=str,
        default="single",
        help="Case name used with --run-id in single mode.",
    )
    parser.add_argument(
        "--batch-dir",
        type=Path,
        help="Batch mode: scan subdirectories under this path, each as a case.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("MODEL_NAME", "local:Qwen/Qwen3-4B-Instruct-2507"),
        help="Local model name (use 'local:' prefix).",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=1024,
        help="Max new tokens to generate.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose LLM call info.",
    )
    return parser.parse_args()


def generate_one(plan_path: Path, prompt_path: Path, template_text: str, llm: LocalLLMCaller, temperature: float, max_new_tokens: int):
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    extra_prompt = read_file(prompt_path).strip()
    if not extra_prompt:
        raise ValueError(f"Prompt file is empty; please provide task content in {prompt_path}")

    plan_text = read_file(plan_path)

    full_prompt = build_user_prompt(plan_text, template_text, extra_prompt)

    system_prompt = "You are a precise converter from PDDL plans to JSON."
    responses, token_stats = llm.get_completion(
        prompt=full_prompt,
        system_instruction=system_prompt,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
    )

    if not responses:
        raise RuntimeError("LLM did not return any response")

    raw_output = responses[0]

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned invalid JSON: {exc}\nRaw output:\n{raw_output}") from exc

    return parsed, token_stats


def main():
    args = parse_args()

    if args.batch_dir and args.run_id is None:
        raise ValueError("--batch-dir 需要配合 --run-id 来组织输出")

    llm = LocalLLMCaller(model=args.model)
    template_text = read_file(args.template)

    def target_output(case: str) -> Path:
        case_safe = sanitize_case_name(case)
        if args.run_id:
            return args.output_base / args.run_id / case_safe / "nlplan.json"
        return args.output

    if args.batch_dir:
        case_dirs = sorted([d for d in args.batch_dir.iterdir() if d.is_dir()])
        if not case_dirs:
            raise RuntimeError(f"批量目录 {args.batch_dir} 下没有子目录")

        for case_dir in case_dirs:
            plan_path, prompt_path = resolve_case_files(case_dir, args.prompt)
            if not plan_path:
                print(f"⚠ 跳过 {case_dir.name}: 找不到 plan 文件")
                continue

            try:
                parsed, token_stats = generate_one(
                    plan_path,
                    prompt_path,
                    template_text,
                    llm,
                    args.temperature,
                    args.max_new_tokens,
                )
            except Exception as exc:
                print(f"❌ 生成 {case_dir.name} 失败: {exc}")
                continue

            out_path = target_output(case_dir.name)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✔ 生成 {case_dir.name}: {out_path}")
            print("Token stats:", json.dumps(token_stats, ensure_ascii=False, indent=2))
    else:
        parsed, token_stats = generate_one(
            args.plan,
            args.prompt,
            template_text,
            llm,
            args.temperature,
            args.max_new_tokens,
        )
        out_path = target_output(args.case_name)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps(parsed, ensure_ascii=False, indent=2))
        print("Token stats:", json.dumps(token_stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
