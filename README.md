# 项目说明

## 项目概览
本仓库围绕“把 PDDL 规划转成可读自然语言步骤，并用 VAL 校验规划”的实验流程，包含一个本地 LLM 转换脚本和一个验证示例。

## 目录结构
- `nl_plan_generator/`：PDDL→自然语言 JSON 转换脚本与提示词。
- `case_demo/`：使用 VAL 的验证示例（含错误分类说明与样例 plan）。
- `run_qwen.py`：最小化的 Qwen 本地推理示例。
- `archive/`：旧版 PDDL 域/问题文件。

## 环境依赖
- Python 3.10+；推荐 GPU（Qwen 默认跑在 CUDA）。
- 依赖列表见 `nl_plan_generator/requirements.txt`：`torch`、`transformers`、`accelerate`、`sentencepiece`、`python-dotenv` 等。
- 若需运行 VAL，请确保系统已安装 `validate` 命令（如 Fast Downward / VAL 套件）。

## 工作流 1：PDDL 计划 → 自然语言 JSON
1) 安装依赖：`pip install -r nl_plan_generator/requirements.txt`。
2) 可在环境变量指定模型：`MODEL_NAME="local:Qwen/Qwen3-4B-Instruct-2507"`（默认），模型使用 `transformers` 本地加载。
3) 运行：`python nl_plan_generator/generate_nl_plan.py`。
4) 脚本逻辑（见 `nl_plan_generator/generate_nl_plan.py`）：读取样例计划 `data/sample.plan` 与提示词 `prompts/pddl_to_nl.txt`，调用 `LocalLLMCaller` 生成 JSON，写入并打印 `data/output.json`，同时输出 token 统计。
5) 提示词约束：仅输出 JSON，`steps` 数组中包含 `step`/`action`/`args`/`description` 字段，动作名与参数名保持原样。

## 工作流 2：VAL 计划验证示例
1) 参考 `case_demo/run_validate.py`：遍历 `problem/` 与 `plan/` 目录的配对文件，执行 `validate -v domain.pddl <problem> <plan>`。
2) 运行：在有 `validate` 的环境中执行 `python case_demo/run_validate.py`（如需使用仓库自带的 `case_demo/domain.pddl`、`case_demo/problem.pddl`，请按脚本常量把文件放入 `problem/`、`plan/` 目录或调整常量）。
3) 输出：
   - 原始日志：`case_demo/results/raw/<task_id>.json`
   - 去重概要：`case_demo/results/dataset.jsonl`
   - 汇总统计：`case_demo/results/summary.json`（含有效率与错误分布）
4) 错误分类规则见 `case_demo/ERROR_TAXONOMY.md`：`valid`、`bad_plan`、`type_error`、`unsatisfied_precondition`、`unknown` 等。
5) 示例解读见 `case_demo/plan_error_explanation.md`：`E1.plan` 前置条件不满足，`E2.plan` 可执行但未达成目标，`success.plan` 为正确闭环。


## 建议的后续补充
- 在根目录新建 `problem/`、`plan/` 示例并更新脚本常量，便于开箱即用。
- 在 README 中补充常见故障排查（显存不足、`validate` 安装指引）。
- 可增加 Makefile/脚本一键串联“生成 NL plan → 还原/转换为 PDDL → VAL 验证”的端到端流程。
