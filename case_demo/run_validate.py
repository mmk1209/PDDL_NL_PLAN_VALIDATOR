import subprocess
import json
import os
from datetime import datetime
import hashlib
import re
from collections import Counter

DOMAIN_FILE = "domain.pddl"
PROBLEM_DIR = "problem"
PLAN_DIR = "plan"

RESULT_ROOT = "results"
RAW_DIR = os.path.join(RESULT_ROOT, "raw")
DATASET_FILE = os.path.join(RESULT_ROOT, "dataset.jsonl")
SUMMARY_FILE = os.path.join(RESULT_ROOT, "summary.json")


# -------------------------
# Directory bootstrap
# -------------------------

def ensure_dirs():
    """
    Ensure only expected directories exist.
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(RESULT_ROOT, exist_ok=True)


ensure_dirs()


# -------------------------
# Utilities
# -------------------------

def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def parse_task_id(filename: str) -> str:
    # "2.problem.pddl" -> "2"
    return filename.split(".")[0]


# -------------------------
# VAL output parser
# -------------------------

# Error pattern registry
ERROR_PATTERNS = [
    # Semantic errors
    ("unsatisfied_precondition", r"unsatisfied precondition"),
    ("type_error", r"type problem"),

    # Plan format / structure errors
    ("bad_plan", r"bad plan description"),
    ("bad_plan", r"bad plan"),
    ("bad_plan", r"failed plans"),

    # Parser / IO errors
    ("parser_error", r"parser"),
    ("parser_error", r"failed to read"),

    # System / crash errors
    ("segfault", r"segmentation fault|段错误|core dumped"),

]



def extract_error_signature(text: str):
    """
    Find first matched error pattern in full text and extract nearby context.
    """
    lower = text.lower()
    lines = text.splitlines()

    for tag, pattern in ERROR_PATTERNS:
        # ① First: match against full text
        if not re.search(pattern, lower, re.IGNORECASE):
            continue

        # ② Second: locate the first matching line for context
        for idx, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                start = max(0, idx - 5)
                end = min(len(lines), idx + 10)
                snippet = "\n".join(lines[start:end]).strip()
                return tag, snippet

        # ③ Fallback: pattern matched globally but not line-locatable
        return tag, text[:800].strip()

    return "unknown", None

def parse_val_output(text: str):
    """
    Robust VAL output parser based on keyword detection instead of fragile regex.
    """

    parsed = {
        "success": False,
        "error_type": None,
        "error_signature": None,
        "message": None,
    }

    lower = text.lower()

    # ------------------
    # Success detection
    # ------------------
    if re.search(r"^\s*plan valid\s*$", lower, re.MULTILINE):
        parsed["success"] = True
        parsed["error_type"] = "valid"
        parsed["error_signature"] = "Plan valid"
        parsed["message"] = "Plan valid"
        return parsed

    # ------------------
    # Remove noisy type-checking lines
    # ------------------
    cleaned_lines = [
        line for line in text.splitlines()
        if not line.lower().startswith("type-checking")
        and "...action passes type checking" not in line.lower()
    ]
    cleaned_text = "\n".join(cleaned_lines).strip()

    # ------------------
    # Keyword-based error extraction
    # ------------------
    error_type, signature = extract_error_signature(cleaned_text)

    parsed["success"] = False
    parsed["error_type"] = error_type
    parsed["error_signature"] = signature or "Unrecognized error pattern"
    parsed["message"] = cleaned_text[:2000]

    return parsed


# -------------------------
# Core runner
# -------------------------

def run_validate(task_id: str):
    problem_file = f"{PROBLEM_DIR}/{task_id}.problem.pddl"
    plan_file = f"{PLAN_DIR}/{task_id}.plan"
    raw_file = os.path.join(RAW_DIR, f"{task_id}.json")

    command = ["validate", "-v", DOMAIN_FILE, problem_file, plan_file]
    command_str = " ".join(command)

    print(f"▶ Validating task {task_id}")

    proc = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    exit_code = proc.returncode
    success = (exit_code == 0)

    combined_output = stdout + "\n" + stderr
    output_hash = sha1(combined_output)

    parsed = parse_val_output(combined_output)

    record = {
        "task_id": task_id,
        "domain_file": DOMAIN_FILE,
        "problem_file": problem_file,
        "plan_file": plan_file,
        "command": command_str,
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "exit_code": exit_code,
        "output_hash": output_hash,
        "parsed": parsed,
        # Keep raw logs only in raw json
        "stdout": stdout,
        "stderr": stderr,
    }

    # Save raw JSON
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"  ✔ Raw saved -> {raw_file}")

    # Append lightweight record to dataset.jsonl
    append_to_dataset(record)

    return record


# -------------------------
# Dataset management
# -------------------------
def reset_dataset():
    """
    Clear dataset.jsonl before each run.
    """
    os.makedirs(os.path.dirname(DATASET_FILE), exist_ok=True)
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        pass
    print("🧹 dataset.jsonl reset.")


def load_existing_hashes():
    hashes = set()

    if not os.path.exists(DATASET_FILE):
        return hashes

    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                h = obj.get("output_hash")
                if h:
                    hashes.add(h)
            except Exception:
                continue

    return hashes


def append_to_dataset(record):
    """
    Append a compact version of record into dataset.jsonl
    """
    existing_hashes = load_existing_hashes()
    h = record["output_hash"]

    if h in existing_hashes:
        print("  ⚠ Duplicate record detected, skip appending.")
        return

    # Keep dataset.jsonl compact (no stdout/stderr)
    compact = {
        "task_id": record["task_id"],
        "success": record["success"],
        "exit_code": record["exit_code"],
        "output_hash": record["output_hash"],
        "parsed": record["parsed"],
        "timestamp": record["timestamp"],
    }

    with open(DATASET_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(compact, ensure_ascii=False) + "\n")

    print("  ✔ Appended to dataset.jsonl")


# -------------------------
# Summary generation
# -------------------------

def generate_summary():
    total = 0
    valid = 0
    class_counter = Counter()

    if not os.path.exists(DATASET_FILE):
        return

    with open(DATASET_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue

            total += 1

            parsed = obj.get("parsed", {})
            is_valid = parsed.get("success", False)

            if is_valid:
                valid += 1
                class_counter["valid"] += 1
            else:
                etype = parsed.get("error_type", "unknown")
                class_counter[etype] += 1

    summary = {
        "total_records": total,
        "valid_plans": valid,
        "invalid_plans": total - valid,
        "valid_rate": round(valid / total, 3) if total > 0 else 0,
        "classification": dict(class_counter),
        "generated_at": datetime.now().isoformat()
    }

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"📊 Summary updated -> {SUMMARY_FILE}")


# -------------------------
# Main
# -------------------------

def main():
    reset_dataset()
    tasks = []

    for filename in sorted(os.listdir(PROBLEM_DIR)):
        if not filename.endswith(".problem.pddl"):
            continue

        task_id = parse_task_id(filename)
        plan_path = f"{PLAN_DIR}/{task_id}.plan"

        if not os.path.exists(plan_path):
            print(f"⚠ Plan missing for task {task_id}, skipped.")
            continue

        tasks.append(task_id)

    print(f"Found {len(tasks)} tasks: {tasks}\n")

    for task_id in tasks:
        run_validate(task_id)

    generate_summary()
    print("\n✅ All done.")


if __name__ == "__main__":
    main()
