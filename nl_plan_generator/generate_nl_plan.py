import json
import os
from pathlib import Path

from llmcaller import LocalLLMCaller

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main():
    model_name = os.getenv("MODEL_NAME", "local:Qwen/Qwen3-4B-Instruct-2507")
    llm = LocalLLMCaller(model=model_name)

    sample_plan = read_file(PROJECT_ROOT / "data" / "inputs" / "sample.plan")
    prompt_template = read_file(BASE_DIR / "prompts" / "pddl_to_nl.txt")

    full_prompt = prompt_template.replace("{{PDDL_PLAN}}", sample_plan)

    system_prompt = "You are a precise converter from PDDL plans to JSON."
    responses, token_stats = llm.get_completion(
        prompt=full_prompt,
        system_instruction=system_prompt,
        temperature=0.2,
        max_new_tokens=1024,
    )

    if not responses:
        raise RuntimeError("LLM did not return any response")

    raw_output = responses[0]

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned invalid JSON: {exc}\nRaw output:\n{raw_output}") from exc

    output_path = PROJECT_ROOT / "data" / "nlplan" / "output.json"
    output_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    print("Token stats:", json.dumps(token_stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
