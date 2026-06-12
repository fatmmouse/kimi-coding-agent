# kimi-coding-agent

一个为「连续执行 2 小时长任务」设计的 coding agent 原型，重点不在功能多，而在**可靠性**：
上下文管理、任务状态记录、失败恢复、用户中断四个机制，每个都做成可开关的 ablation，用评测数据证明其价值。

> Kimi Product Engineer 笔试题 1 的实现部分。设计与论证见 [docs/answer.md](docs/answer.md)，
> 主流 agent 调研见 [docs/research.md](docs/research.md)。

## 四个机制（与对应模块）

| 机制 | 模块 | 一句话 |
|---|---|---|
| ① 上下文管理 | [harness/context.py](harness/context.py) | 工具结果截断落盘 + 阈值触发 LLM 压缩 + 文件系统即记忆 |
| ② 任务状态 | [harness/state.py](harness/state.py) | append-only JSONL 即时落盘 + 重放式 resume + todo.md 语义层 |
| ③ 失败恢复 | [harness/recovery.py](harness/recovery.py) | API 错误分类退避重试 + 工具错误回喂自纠 + 死循环检测/熔断 |
| ④ 用户中断 | [harness/interrupt.py](harness/interrupt.py) | 安全点 steering 注入 + Ctrl-C 优雅停 + 危险命令审批门 |

provider 抽象层 [harness/providers.py](harness/providers.py) 屏蔽两种 wire 协议：
Kimi For Coding（Anthropic 协议）与 DeepSeek（OpenAI 协议），对上层只露一个 `chat()`。

## 运行

```bash
python3 -m venv .venv && .venv/bin/pip install openai anthropic

# 写 .env（不进 git）：
#   KIMI_API_KEY=sk-...
#   DEEPSEEK_API_KEY=sk-...

.venv/bin/python agent.py "在 workspace 写一个 fizzbuzz.py 并运行"
.venv/bin/python agent.py --model deepseek "..."     # 换 provider
.venv/bin/python agent.py --resume 20260612-160038   # 崩溃后续跑
```

机制开关（用于 ablation）：`--no-compact` `--no-resume` `--no-retry` `--no-interrupt`

## 评测

```bash
.venv/bin/python -m evals.scenarios --model kimi          # 跑全部场景
.venv/bin/python -m evals.scenarios --model kimi --only S2 S3
```

场景 × ablation 矩阵（[evals/scenarios.py](evals/scenarios.py)），故障注入见 [evals/chaos.py](evals/chaos.py)：

| 场景 | 验证什么 | 对照 |
|---|---|---|
| S1 | 长任务里上下文是否被压制 | compact on/off |
| S2 | API 故障下能否跑完 | retry on/off |
| S3 | kill-9 后能否从断点续跑 | resume vs 从头 |
| S4 | 工具失败能否自纠 | 单组（看 tool_fails>0 且 completed） |
| S5 | 运行中改需求能否采纳 | steer on/off |

结果落在 [evals/results/](evals/results/)。
