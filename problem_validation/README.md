# 项目说明

## 项目概览
本仓库围绕“把 PDDL 规划转成可读自然语言步骤，并用 VAL 校验规划”的实验流程，包含一个本地 LLM 转换脚本和一个验证示例。

## 目录结构
- `demo.py`：一键跑“NL 计划生成 → PDDL & VAL 验证”，默认批量处理 `data/inputs`。
- `nl_plan_generator/`：PDDL→自然语言 JSON 转换脚本与提示词，现支持批处理并复用同一 LLM 实例。
- `nl_plan_validator/`：将 NL JSON 生成 PDDL plan 并用 VAL 验证。
- `case_demo/`：VAL 的独立示例与错误分类说明。
- `data/`：输入与输出根目录，默认输入放在 `data/inputs/<case>/`，输出归档到 `data/runs/<run_id>/<case>/`。
- `problem_validation/`：从自然语言任务描述生成 problem.pddl 的独立 demo（支持 LLM 直生与模板兜底）。

## 环境依赖
- Python 3.10+；推荐 GPU（Qwen 默认跑在 CUDA）。
- 依赖列表见 `nl_plan_generator/requirements.txt`：`torch`、`transformers`、`accelerate`、`sentencepiece`、`python-dotenv` 等。
- 若需运行 VAL，请确保系统已安装 `validate` 命令（如 Fast Downward / VAL 套件）。

## 快速开始：一键流水线（推荐）
默认模型：环境变量 `MODEL_NAME`（若未设，demo 里用 `local:Qwen/Qwen3-4B-Instruct-2507`）。

1) 安装依赖：`pip install -r nl_plan_generator/requirements.txt`
2) 放置输入：在 `data/inputs/<case>/` 下至少包含
   - `problem.pddl`（必需）
   - 计划文件：`plan.plan` / `planner.plan` / `sample.plan` / `input.plan`（或任意 `.plan`）
   - 可选 `prompt.txt`（否则用全局 `data/inputs/sample/prompt.txt`）
   - 可选 `domain.pddl`（否则用全局 `data/inputs/domain.pddl`）
3) 运行（批量，默认）：`python demo.py`
   - 等价于 `python demo.py --batch-dir data/inputs --model local:Qwen/Qwen3-4B-Instruct-2507`
   - 每个子目录视为一个 case，只加载一次模型，逐案生成 NL JSON 后再做 VAL 验证。
4) 输出：`data/runs/<timestamp>_<model>/<case>/`
   - `nlplan.json`：自然语言计划（生成阶段）
   - `plan.plan`：还原的 PDDL plan（验证阶段）
   - `*.val.log` / `*.val.json`：VAL 结果

单案例运行
- 强制单例：`python demo.py --single --plan data/inputs/sample/planner.plan --problem data/inputs/sample/problem.pddl --prompt data/inputs/sample/prompt.txt`
- run_id 仍为 `时间戳_模型名`，输出位于 `data/runs/<run_id>/single/`。

验证开关
- 默认运行 VAL；若只想生成 NL JSON：添加 `--no-validate`。
- 不想自动追加 `(status complete)`：添加 `--no-status`（透传给验证脚本）。

## 生成器（nl_plan_generator）单独使用
- 单例：`python nl_plan_generator/generate_nl_plan.py --plan <plan> --prompt <prompt> --output <out>`
- 批量复用模型：`python nl_plan_generator/generate_nl_plan.py --batch-dir data/inputs --run-id <run_id> --output-base data/runs`
- 输出落在 `output-base/run-id/<case>/nlplan.json`。

## 验证器（nl_plan_validator）单独使用
- `python nl_plan_validator/generate_and_validate.py --input <nlplan.json> --domain <domain.pddl> --problem <problem.pddl> --outdir <dir> --logdir <dir>`
- 可用 `--no-validate` 仅生成 plan，不跑 VAL。

## 依赖与工具
- Python 3.10+，本地 LLM 通过 `LocalLLMCaller`（Transformers）。
- VAL：需要系统可执行 `validate`。
- 依赖见 `nl_plan_generator/requirements.txt`。

## Problem Validation Demo（problem_validation）
目标：给定 `prompt.txt`（用户任务）和 `domain.pddl`，生成合法的 `problem.pddl` 并通过 VAL。

运行方式（默认模板模式）：
- `python problem_validation/generate_problem.py` 或显式 `--mode template`
  - LLM 只产 JSON `{ "problem_name": ... }`，用固定模板生成 PDDL；默认重试 2 次（名称解析或 VAL 失败时）。

LLM 直生模式（可选）：
- `python problem_validation/generate_problem.py --mode llm`
  - LLM 直接输出 PDDL；若 quick check/VAL 失败，会提炼错误信息重试一次。
  - 两次失败后自动降级到模板生成，保证有可演示的可通过版本（若 domain 本身无效则仍会失败）。

重要说明：
- 需要 `problem_validation/data/inputs/` 下的 `prompt.txt`、`domain.pddl`；`rules.txt`、`app.txt` 仅在 `--mode llm` 下用于提示。
- 开始前会检查 `validate` 是否在 PATH，不存在则直接报错。
- 生成/验证输出位于 `problem_validation/data/outputs/generated_problems/demo_problem.pddl`（可用 `--output` 覆盖）。

## case_demo（保留示例）
- `case_demo/run_validate.py` 展示 VAL 使用方式。
- 错误分类见 `case_demo/ERROR_TAXONOMY.md`，案例说明见 `case_demo/plan_error_explanation.md`。
