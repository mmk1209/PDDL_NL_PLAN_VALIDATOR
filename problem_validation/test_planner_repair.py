import subprocess
from pathlib import Path
from typing import Tuple

from llmcaller import LocalLLMCaller


# -------------------------
# Configuration
# -------------------------

DOMAIN = Path("problem_validation/data/inputs/domain.pddl")
PROBLEM = Path("problem_validation/data/outputs/generated_problems/problem.pddl")

PLANNER_CMD = "fast-downward.py"
PLANNER_ARGS = "--alias lama-first"

MAX_RETRIES = 5
MODEL = "local:Qwen/Qwen3-4B-Instruct-2507"


# -------------------------
# Utilities
# -------------------------
def classify_planner_error(log: str) -> str:
    """
    Classify planner failure type.
    Returns: "structural" | "semantic"
    """
    l = log.lower()

    structural_keywords = [
        "duplicate object",
        "translator",
        "parse",
        "unknown",
        "undefined",
        "constant",
    ]

    if any(k in l for k in structural_keywords):
        return "structural"

    # default: planner ran but no solution found
    return "semantic"



def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run_planner(domain: Path, problem: Path) -> Tuple[bool, str]:
    cmd = [PLANNER_CMD] + PLANNER_ARGS.split() + [str(domain), str(problem)]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc.returncode == 0, proc.stdout.strip()


def extract_problem_pddl(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
    idx = t.lower().find("(define")
    if idx >= 0:
        t = t[idx:]
    return t.strip()

def build_planner_structural_repair_prompt(
    previous_problem: str,
    planner_log: str,
    domain_text: str,
) -> str:
    return f"""
You are a PDDL expert.

The planner failed due to a STRUCTURAL or NAMING error
(e.g., duplicate objects, invalid constants, parser issues).

====================
[Planner Error]
{planner_log}

====================
[PDDL Domain]
{domain_text}

====================
[Previous problem.pddl]
{previous_problem}

====================

Your task:
- Fix ONLY the structural / naming issue reported by the planner.
- Do NOT change the task semantics.
- You MAY rename or remove conflicting objects.
- Keep the domain unchanged.
- Do NOT invent new predicates or types.
- Output ONLY the corrected full problem.pddl.
""".strip()



def build_planner_repair_prompt(
    previous_problem: str,
    planner_log: str,
    domain_text: str,
) -> str:
    return f"""
You are a PDDL planning expert.

The problem is syntactically valid, but the planner FAILED to find a plan.

====================
[Planner Log]
{planner_log}

====================
[PDDL Domain]
{domain_text}

====================
[Previous problem.pddl]
{previous_problem}

====================

CRITICAL REASONING TASK (you MUST follow this):
1. Identify which action can achieve each goal predicate.
2. For each such action, list ALL required preconditions.
3. Check whether each precondition is achievable from the initial state.
4. Identify the FIRST unreachable predicate in the causal chain.
5. Modify the problem to make that predicate achievable.

HINT (very important):
- To achieve (field-has-text ?f ?txt), the action input_text is required.
- input_text REQUIRES (focused ?f).
- A field becomes focused ONLY via click_focus_field, double_tap_focus_field, or long_press_focus_field.
- These actions require corresponding predicates:
    (click-focus ?target ?screen ?field)
    (doubletap-focus ...)
    (longpress-focus ...)

If no such predicate exists in :init, you MUST ADD one.

RULES:
- You MAY modify :objects, :init, and :goal.
- Keep the domain unchanged.
- Do NOT invent new predicates or types.
- Prefer minimal changes that make the plan solvable.
- Output ONLY the corrected full problem.pddl.

EXPECTED TYPE OF FIX:
Add a missing focus relationship, for example:
    (click-focus search_button search_screen search_field)
""".strip()

def summarize_planner_error(output: str) -> str:
    """
    Extract only the most relevant error lines and nearby context
    from fast-downward output for LLM repair.
    """
    lines = [l.rstrip() for l in output.splitlines() if l.strip()]
    key_idx = []

    keywords = ["error", "fatal", "duplicate", "undefined", "unknown", "failed"]

    for i, line in enumerate(lines):
        ll = line.lower()
        if any(k in ll for k in keywords):
            key_idx.append(i)

    picked = []
    for i in key_idx:
        # take 1 line before and after for context
        for j in range(max(0, i - 1), min(len(lines), i + 2)):
            picked.append(lines[j])

    if not picked:
        # fallback: last few lines
        picked = lines[-6:]

    # deduplicate while preserving order
    seen = set()
    summary = []
    for l in picked:
        if l not in seen:
            seen.add(l)
            summary.append(l)

    return "\n".join(summary)

# -------------------------
# Main loop
# -------------------------

def main():
    domain_text = read_text(DOMAIN)
    llm = LocalLLMCaller(model=MODEL)

    print("📄 Using existing problem:")
    print(PROBLEM)

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n🚀 Attempt {attempt}/{MAX_RETRIES}")

        ok, planner_log = run_planner(DOMAIN, PROBLEM)


        if ok:
            print("✅ Planner solved the problem.")
            return

        print("❌ Planner failed → sending log to LLM for repair.")

        previous_problem = read_text(PROBLEM)

        planner_summary = summarize_planner_error(planner_log)

        print("========== PLANNER ERROR SUMMARY ==========")
        print(planner_summary)
        print("===========================================")

        error_type = classify_planner_error(planner_summary)
        print(f"🧭 Detected planner error type: {error_type}")

        if error_type == "structural":
            repair_prompt = build_planner_structural_repair_prompt(
                previous_problem=previous_problem,
                planner_log=planner_summary,
                domain_text=domain_text,
            )
        else:
            repair_prompt = build_planner_repair_prompt(
                previous_problem=previous_problem,
                planner_log=planner_summary,
                domain_text=domain_text,
            )



        responses, _ = llm.get_completion(
            prompt=repair_prompt,
            system_instruction="You are a precise PDDL problem debugger.",
            temperature=0.2,
            max_new_tokens=1500,
        )

        if not responses:
            raise RuntimeError("LLM returned no output.")

        new_problem = extract_problem_pddl(responses[0])

        print("📝 New problem generated by LLM:")
        print(new_problem)

        write_text(PROBLEM, new_problem)
        print("💾 problem.pddl overwritten, retrying planner...")

    print("\n💥 All retries exhausted. Planner still failing.")


if __name__ == "__main__":
    main()
