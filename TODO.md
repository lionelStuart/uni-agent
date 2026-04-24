# TODO

## Token-aware 上下文压缩

### 目标

- 将当前基于字符上限的 `session_context` / `prior_context` 截断，升级为基于 token 预算的上下文构建。
- 提高 planner、goal-check、conclusion 在长会话和长工具输出场景下的稳定性。
- 优先保留对决策最有价值的信息，而不是简单保留最近或最长的文本。

### 设计原则

- 按 token 预算而不是字符数控制上下文大小。
- 按信息价值分层保留：任务约束 > 最近交互 > 失败原因 > 关键结论 > 普通输出。
- 旧历史优先摘要化，不直接拼接原文。
- 大网页、长日志、长文件内容先提炼，再进入 planner 上下文。
- prompt 组装过程需要可解释、可测试、可复现。

### 实现方案

#### 1. 引入 token 预算模块

- 新增 `src/uni_agent/context/token_budget.py`
- 提供：
  - `count_tokens(text: str, model_name: str) -> int`
  - `truncate_to_tokens(text: str, max_tokens: int, model_name: str) -> str`
  - `fit_blocks_to_budget(blocks, max_tokens, model_name) -> list[ContextBlock]`
- 优先接实际模型 tokenizer；如果当前 provider 无法直接获取 tokenizer，再提供保守 fallback。

#### 2. 将上下文块结构化

- 为 planner 输入定义统一的 `ContextBlock` 结构，而不是直接拼字符串。
- 建议字段：
  - `kind`: `system | task | recent_turn | prior_step | memory_summary | retrieval_summary`
  - `priority`: 数值优先级
  - `pinned`: 是否必须保留
  - `text`: 实际内容
  - `token_estimate`: 预估 token 数
- 由 context builder 统一排序、裁剪和拼装。

#### 3. 重构 session 压缩

- 将 `src/uni_agent/observability/client_session.py` 中当前单条字符串 `summary`，扩展为更结构化的压缩结果。
- 每轮 run 至少保留：
  - `task`
  - `status`
  - `tools_used`
  - `key_findings`
  - `failures`
  - `next_hints`
- `build_session_context_for_planner()` 改为按 token 预算拼装，而不是按字符数和条数截断。

#### 4. 重构 prior_context

- 将 `src/uni_agent/agent/orchestrator.py` 中 `_format_prior_context()` 的字符截断，改为 token-aware。
- 对每个 step 分配单步预算，例如：
  - step 描述固定保留
  - output 只保留命中片段、错误摘要和关键证据
  - 超出单步预算时优先压缩 output，再压缩错误详情
- 整体 prior log 再受总 token 预算控制。

#### 5. 增加网页/长文本提炼层

- 对 `http_fetch`、长日志、长文件读取结果新增轻量提炼逻辑，避免把原始大块文本直接喂给 planner。
- 提炼结果建议统一输出：
  - `title`
  - `page_type`
  - `key_points`
  - `recency_signals`
  - `useful_links`
  - `evidence_snippets`
- planner 主要消费提炼结果，必要时再回看原文片段。

#### 6. 为不同阶段单独配置预算

- 分别给以下阶段设置独立预算：
  - planner
  - goal-check
  - conclusion synthesis
- 不同阶段关注点不同，预算策略也应不同：
  - planner 更关注任务约束、最近失败和候选证据
  - goal-check 更关注已执行步骤和是否满足目标
  - conclusion 更关注最终证据与结论摘要

#### 7. 加入去重与滚动摘要

- 对重复错误、重复网页内容、重复 step 输出做去重。
- 当 session 历史过长时，将较旧的多轮记录合并成一个滚动摘要块，而不是保留逐条摘要。
- 滚动摘要保留：
  - 已确认的事实
  - 已失败的路径
  - 尚未解决的问题

### 分阶段实现 Round

#### Round 1：预算基础设施

- 新增 token 计数与预算裁剪模块。
- 定义统一的 `ContextBlock` 数据结构。
- 先提供独立可测的纯函数能力：
  - token 计数
  - token 截断
  - 按优先级装箱到预算内
- 这一轮不改 planner 行为，只把基础设施搭起来。

**交付物**

- `src/uni_agent/context/token_budget.py`
- `ContextBlock` 与预算裁剪单元测试

#### Round 2：`session_context` token-aware 化

- 重构 `client_session` 的摘要格式，从单字符串 summary 升级为结构化摘要。
- `build_session_context_for_planner()` 改为基于 token 预算拼装。
- 保留当前 CLI / session 存储接口，尽量不改用户使用方式。

**交付物**

- `src/uni_agent/observability/client_session.py`
- `tests/unit/test_client_session.py` 扩展覆盖 token 预算逻辑

#### Round 3：`prior_context` token-aware 化

- 重构 `orchestrator` 的 `_format_prior_context()`。
- 让 step 级输出按预算截取，而不是固定字符数。
- 保证错误摘要、关键输出、失败原因优先保留。

**交付物**

- `src/uni_agent/agent/orchestrator.py`
- 针对 replan 场景补单元测试

#### Round 4：长文本/网页提炼层

- 为 `http_fetch`、长日志、长文件结果增加轻量提炼。
- 先输出统一结构：
  - `title`
  - `page_type`
  - `key_points`
  - `evidence_snippets`
- planner 优先消费提炼结果，而不是原始大块正文。

**交付物**

- 提炼辅助模块
- `http_fetch` / planner 上下游接线
- 长网页场景测试

#### Round 5：分阶段预算策略

- 为 planner、goal-check、conclusion 配置不同预算。
- 将不同阶段的上下文构建显式拆开，而不是复用同一套字符串。
- 调整 prompt builder，使各阶段关注信息与预算一致。

**交付物**

- 阶段化 context builder
- `goal_check` / `run_conclusion` 接线
- 各阶段预算配置与测试

#### Round 6：去重与滚动摘要

- 为重复 step 输出、重复网页内容、重复错误增加去重。
- 增加旧历史滚动摘要块。
- 保证长 session 下预算稳定，不因重复内容膨胀。

**交付物**

- 去重逻辑
- 滚动摘要逻辑
- 长会话回归测试

### 建议落地顺序

1. Round 1：预算基础设施
2. Round 2：`session_context` token-aware 化
3. Round 3：`prior_context` token-aware 化
4. Round 4：长文本/网页提炼层
5. Round 5：分阶段预算策略
6. Round 6：去重与滚动摘要

### 验收标准

- 长会话下 planner prompt token 数稳定，不再靠字符截断碰运气。
- 相同任务多轮执行时，规划路径更稳定。
- replan 时能稳定记住最近失败原因和已验证结论。
- 大网页和长日志不会直接淹没 prompt。
- 单元测试覆盖：
  - token 预算裁剪
  - pinned block 永不丢失
  - 高优先级块优先保留
  - session/prior context 超预算时仍能输出有效摘要
