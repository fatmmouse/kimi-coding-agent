# 主流 Coding Agent 四机制调研笔记

> 调研时间：2026-06-12。方法：浅 clone 开源仓库定向读码（Kimi CLI / Codex CLI / pi / MiMo Code），
> Claude Code 用 npm 官方公开分发包（v1.0.88 完整 JS bundle）grep 机制字符串 + 官方文档，不使用任何泄露材料。
> 调研对象代码位置：`/tmp/agent-research/`（不入库）。

## 一张总表

| 机制 | Kimi CLI (Moonshot) | Codex CLI (OpenAI) | Claude Code (Anthropic) | MiMo Code (小米) | pi (badlogic) |
|---|---|---|---|---|---|
| **上下文管理** | 双条件触发 auto-compact：用量 ≥ 85% 或 剩余空间 < 50k 预留（`config.py:88-95`）；LLM 摘要替换旧历史，保留最近 2 条消息（`soul/compaction.py` SimpleCompaction）；token 先 chars/4 估算、下次真实 usage 校正 | `compact.rs` + remote 变体；compact 注入消息限 20k tokens（`COMPACT_USER_MESSAGE_MAX_TOKENS`）；`context_manager/` 独立模块管历史 | auto-compact + **microcompact**（轻量压缩工具结果）；UI 常驻「Context left until auto-compact」；摘要 prompt 分节：Primary Request and Intent / Pending Tasks / Current Work…；工具结果超 40k 字符截断 | 「近乎无限上下文」实质 = 阈值触发 **checkpoint-writer 子代理**把状态固化到 11 段 `checkpoint.md`（活跃意图/下一步/任务树/文件/错误修复…），不靠丢历史 | `harness/compaction/`：reserveTokens 16384 + keepRecentTokens 20000，按 turn 边界找切点（`findCutPoint`）；工具输出默认 2000 行 / 50KB 截断 |
| **任务状态** | 每会话目录 `context.jsonl`（LLM 消息）+ `wire.jsonl`（事件流）双文件（`session.py:150-262`） | rollout JSONL：`~/.codex/sessions/rollout-<ts>-<uuid>.jsonl`，append + 显式 flush，可 jq/fx 直接检查、可重放（`rollout/src/recorder.rs`） | 会话 JSONL（`~/.claude/projects/...`）+ TodoWrite 任务清单（harness 注入「todo list is currently empty」类提醒驱动模型维护）；resume 注入「This session is being continued from a previous conversation…」 | SQLite 存原始轨迹（权威）+ 记忆文件树为索引缓存：`MEMORY.md`（项目级 4 段）/ `checkpoint.md`（会话级）/ `tasks/<id>/progress.md`（子代理任务级）；scope 分 global/projects/sessions | 会话树结构（SessionTreeEntry），支持分支摘要（branch-summarization） |
| **失败恢复** | kosong 层 `RetryableChatProvider` 协议 + **官方自带 ChaosChatProvider 故障注入测试**（按概率注 429/500/502/503 + 损坏 tool call，`chat_provider/chaos.py`）；工具错误类型化（NotFound/Parse/Validate/Runtime）回喂模型；工具调用去重跟踪（`_last_tool_calls`，防死循环） | 指数退避：初始 200ms × 2^n，jitter 0.9–1.1（`util.rs:85-89`）；流式中断后同 turn 重试/fallback（`client.rs` 注释） | 可见重试「Retrying in X seconds… (attempt N)」；工具错误以 tool result 形式回喂模型自纠 | 继承 OpenCode provider 重试；子代理失败由 subagent-progress-checker 插件兜底 | 工具错误回喂；harness 测试集（vitest.harness.config.ts）专测恢复路径 |
| **用户中断** | asyncio 取消传播：LLM step 和工具等待**可中断**，但 context 写入用 `asyncio.shield` 保护（`kimisoul.py:1174`「shield the context manipulation from interruption」）→ 中断只发生在安全点，状态永远一致；`StepInterrupted` 事件上报 UI | 协议层 SQ/EQ 队列：`Op::Interrupt` 提交 → `TurnAborted(reason=Interrupted)` 事件（`protocol.rs:482,1595`）；中断是一等公民操作而非信号 hack | Esc 中断 → 注入「[Request interrupted by user]」/「…for tool use]」作为消息，模型下轮看得见**被打断在哪**；运行中输入排队，工具边界注入（steering） | 继承 OpenCode TUI 中断 | abort 信号贯穿 agent loop |

## 各家最值得抄的一招

1. **Kimi CLI — 中断安全点 + shield**：把「哪些操作可被取消、哪些必须原子完成」显式划分。LLM 调用、工具执行可取消；消息列表的增长（context growth）不可取消。这保证任何时刻杀掉 turn，状态文件都不会是半写状态。
2. **Kimi CLI — compact.md 压缩提示词的优先级设计**：当前任务状态 > 错误与解法 > 代码演化（只留最终版）> 环境 > 设计决策 > TODO，输出为结构化 XML（current_focus / completed_tasks / active_issues / code_state…）。压缩不是「缩短」而是「按重要性重排丢弃」。
3. **Codex — rollout 即真相**：append-only JSONL 是会话的唯一权威记录，崩溃后从它重建；文件本身人类可读（jq 即可审计）。
4. **Codex — 退避参数**：200ms 起步 ×2 指数 + 0.9–1.1 jitter，重试预算耗尽才升级为换端点/报错。
5. **Claude Code — 中断也是上下文**：用户打断不是悄悄停止，而是把「[Request interrupted by user]」写进对话，模型恢复时知道自己被打断在哪、为什么。
6. **Claude Code — 双层压缩**：microcompact（只压工具结果等低价值大块）先行，全量 auto-compact 兜底；UI 持续显示离 auto-compact 还有多远。
7. **MiMo Code — 记忆固化到文件而非对话**：跨阈值时由专门子代理把状态写成结构化 checkpoint.md（11 段），「无限上下文」的本质是把状态从对话搬到文件系统；Dream 离线整合时**以原始轨迹为权威、记忆文件只是缓存**。
8. **pi — 按 turn 边界切割**：compaction 切点永远落在完整 turn 边界（user→assistant→tools 为一个原子单元），绝不把 tool_call 和 tool_result 切散——切散会直接造成 API 400。
9. **Kimi CLI — 官方 chaos provider**：故障恢复不是「写了就算」，是用可复现（带 seed）的故障注入测出来的。我们的 evals/chaos.py 与此同构。

## 对我们设计的直接输入

- 机制①：双条件触发（占比 + 预留），阈值取 0.75（窗口小，留更多余量）；压缩提示词参考 Kimi compact.md 的优先级 + Claude Code 的分节；保留最近 N 轮完整 turn（pi 的边界原则）
- 机制②：append-only JSONL 为权威（Codex），todo.md 为语义层（Claude Code），resume 时注入「本会话由先前会话续接」标记
- 机制③：退避参数直接用 Codex 的（200ms ×2 + jitter）；错误分类学 Kimi 的类型化工具错误；评测用 chaos 注入（Kimi 官方同款思路），带 seed 可复现
- 机制④：安全点 = 工具调用边界（Kimi shield 思想的同步版）；中断写进对话（Claude Code）；steering 队列在安全点注入
