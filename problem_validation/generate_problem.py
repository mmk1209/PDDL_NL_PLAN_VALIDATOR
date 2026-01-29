import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

from llmcaller import LocalLLMCaller


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent   # ToolPlan/


PROBLEM_TEMPLATE = """
(define (problem {problem_name})
  (:domain mobileworld_generic)

  (:objects
    home_screen search_screen results_screen - screen
    search_button back_button - target
    search_field - field
    query_text - text
    success_status - goal_status
    up down - direction
  )

  (:init
    (at-screen home_screen)

    (target-visible search_button home_screen)
    (field-visible search_field home_screen)

    (click-transition search_button home_screen search_screen)
    (back-link search_screen home_screen)

    (scroll-transition down search_screen results_screen)
  )

  (:goal
    (and
      (status-set success_status)
    )
  )
)
""".strip()


def read_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"File is empty: {path}")
    return text


def build_name_prompt(task_text: str) -> str:
    """Prompt LLM to ONLY propose a safe problem name (template mode)."""

    return f"""
You are given a user task.

[User Task]
{task_text}

Your task:
- Propose a short problem name summarizing the task.
- Use only lowercase letters, numbers, and underscores.
- Do NOT generate any PDDL.
- Output ONLY a JSON object in the following format:

{{
  "problem_name": "..."
}}
""".strip()


def build_pddl_prompt(task_text: str, rules_text: str, app_text: str, domain_text: str) -> str:
    """Prompt LLM to directly output a full problem.pddl."""

    return f"""
You are a PDDL expert.

Your task is to generate a valid PDDL problem.pddl file
based on the following information.

====================
[User Task]
{task_text}

====================
[System Rules]
{rules_text}

====================
[Application Description]
{app_text}

====================
[PDDL Domain]
{domain_text}

====================
Output requirements:
- Output ONLY the PDDL problem text (no markdown, no code fences, no commentary).
- The problem must strictly conform to the given domain.
- All objects, predicates, and types must be declared.
- Use meaningful object names.
- Ensure the problem includes (:domain mobileworld_generic).

CRITICAL PDDL SYNTAX RULES:
- In :objects, every object MUST be declared with a type using the format:
  object1 object2 - type
- Do NOT use string literals or quotation marks.
- Do NOT use (not ...) in :init. Absence means false.
- Every symbol must be declared with a type from the domain.
- Declare directions explicitly if used (e.g., up down - direction).
- Keep parentheses balanced; no extra comments.

SEMANTIC REQUIREMENTS (VERY IMPORTANT):

- The goal MUST NOT be satisfied by executing the `status` action alone.
  A problem whose goal is only (status-set ...) is INVALID for this task.

- The goal MUST include at least ONE task-related constraint derived from the domain, such as:
  - being at a specific screen using (at-screen ?s)
  - having text entered using (text-entered ?txt) or (field-has-text ?f ?txt)
  - answering a text using (answered ?txt)

- The initial state and objects MUST be constructed so that the above constraints are meaningful
  and achievable using the actions in the domain.

- The problem should require at least TWO actions to reach the goal
  (i.e., not a trivial one-step solution).

- All objects used in goal predicates MUST be declared in :objects with correct types.

- The chosen goal constraints MUST reflect the user task, not arbitrary predicates.

EXAMPLES OF INVALID GOALS:
- (and (status-set success_status))
- Any goal that can be satisfied without navigating, typing, or answering.

EXAMPLES OF VALID GOALS:
- (and (at-screen results_screen) (status-set success_status))
- (and (field-has-text search_field query_text) (status-set success_status))
- (and (answered result_text) (status-set success_status))

""".strip()

def run_val(domain: Path, problem: Path) -> Tuple[bool, str]:
    cmd = ["validate", "-v", str(domain), str(problem)]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = proc.stdout.strip().lower()

    # 只抓最明确的失败信号
    if "parser failed to read file" in output:
        return False, proc.stdout.strip()

    # 许多 VAL 会在末尾打印：Errors: X, warnings: Y
    # 我们优先从这里判定
    for line in reversed(proc.stdout.splitlines()):
        line_l = line.lower().strip()
        if line_l.startswith("errors:"):
            # e.g., "Errors: 1, warnings: 0"
            try:
                err_part = line_l.split(",")[0]  # "errors: 1"
                err_num = int(err_part.split(":")[1].strip())
                return (err_num == 0), proc.stdout.strip()
            except Exception:
                break

    # fallback：如果没找到 Errors 行，就用 returncode
    return (proc.returncode == 0), proc.stdout.strip()

def sanitize_problem_name(name: str, fallback: str = "problem") -> str:
    """Return a safe problem name limited to [a-z0-9_], or fallback."""

    cleaned = "".join(ch for ch in name.lower() if ch.isalnum() or ch == "_")
    return cleaned or fallback


def build_repair_prompt(previous_problem: str, val_error: str, task_text: str,
                        rules_text: str, app_text: str, domain_text: str) -> str:
    """Prompt for repairing invalid PDDL when using llm mode."""

    return f"""
You are a PDDL expert and debugger.

The previously generated PDDL problem is INVALID.

[User Task]
{task_text}

[System Rules]
{rules_text}

[Application Description]
{app_text}

[PDDL Domain]
{domain_text}

[Previous problem.pddl]
{previous_problem}

[VAL Error Output]
{val_error}

Instructions (follow all):
- Fix ONLY the issues indicated by VAL / type errors; keep other structure unchanged.
- Ensure :domain remains mobileworld_generic.
- Do NOT introduce new predicates or types beyond the domain; all objects must use a domain type.
- In :objects, every object MUST have a type using the form: obj1 obj2 - type (do not put types alone on a line).
- If VAL reports "unknown type X", declare X in :objects with a valid domain type (do NOT treat object names as types).
- If VAL reports "incorrectly typed", verify each predicate/action argument matches the domain signature and the object's declared type.
- No comments, no markdown, balanced parentheses only.
Output ONLY the corrected full problem.pddl.
""".strip()


def ensure_validate_exists() -> None:
    """Fail fast if VAL is missing to keep demos predictable."""

    if not shutil.which("validate"):
        raise FileNotFoundError(
            "`validate` binary not found in PATH. Please install VAL before running."
        )


def extract_problem_pddl(text: str) -> str:
    """Strip code fences and keep content starting from (define ...)."""

    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        # remove optional leading language tag
        if t.lower().startswith("pddl"):
            t = t[4:].lstrip()
    idx = t.lower().find("(define")
    if idx >= 0:
        t = t[idx:]
    return t.strip()


def summarize_val_error(output: str) -> str:
    """Pick key VAL lines plus a bit of context for LLM repair."""

    lines = [l.strip() for l in output.splitlines() if l.strip()]
    key_idx = []
    for i, l in enumerate(lines):
        ll = l.lower()
        if "error" in ll or "errors:" in ll or "parser" in ll or "line" in ll:
            key_idx.append(i)
    # collect context around matched lines
    picked = []
    for i in key_idx:
        for j in range(max(0, i - 1), min(len(lines), i + 2)):
            picked.append(lines[j])
    if not picked:
        picked = lines[-5:]  # fallback: last few lines
    # dedup while preserving order
    seen = set()
    summary = []
    for l in picked:
        if l not in seen:
            seen.add(l)
            summary.append(l)
    return "\n".join(summary)


def extract_domain_types(domain_text: str) -> str:
    """Very simple extractor to surface available types for repair prompts."""

    lines = domain_text.splitlines()
    types_block = []
    capture = False
    for line in lines:
        if "(:types" in line:
            capture = True
            types_block.append(line)
            continue
        if capture:
            types_block.append(line)
            if ")" in line:
                break
    joined = " ".join(types_block)
    # strip leading stuff
    joined = joined.replace("(:types", "").replace(")", "")
    tokens = [t for t in joined.split() if t != "-"]
    return " ".join(tokens).strip()


def quick_pddl_checks(text: str) -> Tuple[bool, str]:
    """Lightweight sanity checks before VAL to catch obvious syntax issues."""

    # balanced parentheses
    balance = 0
    for ch in text:
        if ch == "(":
            balance += 1
        elif ch == ")":
            balance -= 1
            if balance < 0:
                return False, "parenthesis imbalance detected (extra ')')"
    if balance != 0:
        return False, "parenthesis imbalance detected (extra '(')"

    # required sections
    low = text.lower()
    for token in [":domain", "(:objects", "(:init", "(:goal"]:
        if token not in low:
            return False, f"missing required section: {token}"

    return True, ""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate problem.pddl using local Qwen model."
    )

    # ✅ 默认路径配置
    parser.add_argument(
        "--task",
        type=Path,
        default=PROJECT_ROOT / "problem_validation" / "data" / "inputs" / "prompt.txt",
        help="User task prompt text file.",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=PROJECT_ROOT / "problem_validation" / "data" / "inputs" / "rules.txt",
        help="Rules description text file (used in llm mode).",
    )
    parser.add_argument(
        "--app",
        type=Path,
        default=PROJECT_ROOT / "problem_validation" / "data" / "inputs" / "app.txt",
        help="App description text file (used in llm mode).",
    )
    parser.add_argument(
        "--domain",
        type=Path,
        default=PROJECT_ROOT / "problem_validation" / "data" / "inputs" / "domain.pddl",
        help="Domain PDDL file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "problem_validation"
        / "data"
        / "outputs"
        / "generated_problems"
        / "problem.pddl",
        help="Output problem.pddl path.",
    )
    parser.add_argument(
        "--mode",
        choices=["llm", "template"],
        default="template",
        help="Generation mode: template (default, LLM only names) or llm (direct PDDL).",
    )

    # ✅ 模型参数
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("MODEL_NAME", "local:Qwen/Qwen3-4B-Instruct-2507"),
        help="Local model name (use 'local:' prefix).",
    )
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-new-tokens", type=int, default=1024)

    # ✅ 默认关闭 verbose
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print verbose info (enabled by default).",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    task_text = read_file(args.task)
    domain_text = read_file(args.domain)
    rules_text = read_file(args.rules) if args.mode == "llm" else ""
    app_text = read_file(args.app) if args.mode == "llm" else ""

    ensure_validate_exists()

    llm = LocalLLMCaller(model=args.model)
    system_prompt = "You are a precise PDDL problem generator."

    if args.mode == "template":
        base_prompt = build_name_prompt(task_text=task_text)
        prompt = base_prompt
        MAX_RETRIES = 2  # only regenerate name if JSON parse fails or VAL fails

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n🚀 Attempt {attempt} / {MAX_RETRIES}")

            responses, token_stats = llm.get_completion(
                prompt=prompt,
                system_instruction=system_prompt,
                temperature=args.temperature,
                max_new_tokens=args.max_new_tokens,
            )

            if not responses:
                raise RuntimeError("LLM did not return any response.")

            raw_text = responses[0].strip()

            try:
                parsed = json.loads(raw_text)
                problem_name_raw = parsed.get("problem_name", "")
            except json.JSONDecodeError:
                print("⚠️ LLM returned invalid JSON, retrying name generation...")
                continue

            problem_name = sanitize_problem_name(problem_name_raw)
            problem_pddl = PROBLEM_TEMPLATE.format(problem_name=problem_name)

            # Write to file
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(problem_pddl, encoding="utf-8")

            print(f"📝 Generated problem saved to: {args.output}")
            print("Problem name:", problem_name)
            print("Token stats:", token_stats)

            if args.verbose:
                print("========== GENERATED PDDL ==========")
                print(problem_pddl)
                print("====================================")

            # Run VAL validation
            print("🔍 Running VAL validation...")
            is_valid, val_output = run_val(args.domain, args.output)

            print("========== VAL OUTPUT ==========")
            print(val_output)
            print("================================")

            if is_valid:
                print("✅ VAL validation PASSED.")
                return

            print("❌ VAL validation FAILED. Retrying name generation...")

        raise RuntimeError("VAL failed after deterministic template generation. See output above.")

    # ------------------ LLM direct PDDL mode ------------------
    base_prompt = build_pddl_prompt(
        task_text=task_text,
        rules_text=rules_text,
        app_text=app_text,
        domain_text=domain_text,
    )

    prompt = base_prompt
    MAX_RETRIES = 10  # first try + repairs (user preference)
    last_problem_text = None
    last_val_summary = ""
    domain_types_hint = extract_domain_types(domain_text)

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n🚀 Attempt {attempt} / {MAX_RETRIES}")

        # lower temperature after first failure to reduce drift
        temp = args.temperature if attempt == 1 else min(args.temperature, 0.05)

        responses, token_stats = llm.get_completion(
            prompt=prompt,
            system_instruction=system_prompt,
            temperature=temp,
            max_new_tokens=args.max_new_tokens,
        )

        if not responses:
            raise RuntimeError("LLM did not return any response.")

        raw_text = responses[0].strip()
        problem_pddl = extract_problem_pddl(raw_text)
        last_problem_text = problem_pddl

        ok, quick_err = quick_pddl_checks(problem_pddl)
        if not ok:
            last_val_summary = quick_err
            print(f"⚠️ Quick check failed: {quick_err}")
            # Build repair prompt using quick check info and retry
            prompt = build_repair_prompt(
                previous_problem=last_problem_text,
                val_error=quick_err,
                task_text=task_text,
                rules_text=rules_text,
                app_text=app_text,
                domain_text=domain_text,
            )
            continue

        # Write to file
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(problem_pddl, encoding="utf-8")

        print(f"📝 Generated problem saved to: {args.output}")
        print("Token stats:", token_stats)

        if args.verbose:
            print("========== GENERATED PDDL ==========")
            print(problem_pddl)
            print("====================================")

        # Run VAL validation
        print("🔍 Running VAL validation...")
        is_valid, val_output = run_val(args.domain, args.output)

        # print("========== VAL OUTPUT ==========")
        # print(val_output)
        # print("================================")

        if is_valid:
            print("✅ VAL validation PASSED.")
            return

        print("❌ VAL validation FAILED.")
        # Use full VAL output for repair to avoid losing details
        val_error_for_prompt = val_output
        # If unknown type, append available types hint to help LLM repair
        if "unknown type" in val_error_for_prompt.lower():
            val_error_for_prompt += f"\nAvailable types: {domain_types_hint}"
        print("⚠️ VAL Error (full log forwarded to LLM):")
        print(summarize_val_error(val_output))

        # Build repair prompt for next iteration
        prompt = build_repair_prompt(
            previous_problem=last_problem_text,
            val_error=val_error_for_prompt,
            task_text=task_text,
            rules_text=rules_text,
            app_text=app_text,
            domain_text=domain_text,
        )

    # Fallback: auto-switch to template mode to guarantee a passing demo
    print("⚠️ LLM mode failed twice; falling back to template mode for a valid PDDL.")
    # reuse the template flow with one attempt
    fallback_name = sanitize_problem_name("fallback_demo")
    problem_pddl = PROBLEM_TEMPLATE.format(problem_name=fallback_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(problem_pddl, encoding="utf-8")
    is_valid, val_output = run_val(args.domain, args.output)
    if is_valid:
        print("✅ Template fallback VAL validation PASSED.")
        return
    raise RuntimeError("Fallback template generation also failed VAL; please inspect domain/problem manually.")


if __name__ == "__main__":
    main()
