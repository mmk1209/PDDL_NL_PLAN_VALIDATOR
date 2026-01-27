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


def parse_args():
    parser = argparse.ArgumentParser(description="Generate NL JSON plan from PDDL plan using local LLM.")
    parser.add_argument(
        "--plan",
        type=Path,
        default=PROJECT_ROOT / "data" / "inputs" / "sample.plan",
        help="Path to PDDL plan file.",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=PROJECT_ROOT / "data" / "inputs" / "prompt.txt",
        help="Path to required user task prompt text (default: data/inputs/prompt.txt).",
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
        help="Where to write JSON output.",
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


def main():
    args = parse_args()

    llm = LocalLLMCaller(model=args.model)

    if not args.prompt.exists():
        raise FileNotFoundError(f"Prompt file not found: {args.prompt}")
    extra_prompt = read_file(args.prompt).strip()
    if not extra_prompt:
        raise ValueError(f"Prompt file is empty; please provide task content in {args.prompt}")

    plan_text = read_file(args.plan)
    template_text = read_file(args.template)

    full_prompt = build_user_prompt(plan_text, template_text, extra_prompt)

    system_prompt = "You are a precise converter from PDDL plans to JSON."
    responses, token_stats = llm.get_completion(
        prompt=full_prompt,
        system_instruction=system_prompt,
        temperature=args.temperature,
        max_new_tokens=args.max_new_tokens,
    )

    if not responses:
        raise RuntimeError("LLM did not return any response")

    raw_output = responses[0]

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned invalid JSON: {exc}\nRaw output:\n{raw_output}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    print("Token stats:", json.dumps(token_stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
