# 数据与隐私

Session Exporter 直接读取你本地的会话文件。**没有任何东西离开你的机器** —— 没有账号、没有遥测，也没有任何网络调用，除了在 `127.0.0.1` 上把 UI 提供给你自己的浏览器。

## 数据来自哪里

| 来源 | 位置 | Token 依据 |
| --- | --- | --- |
| **Claude Code** | `~/.claude/projects/<folder>/<uuid>.jsonl` | `recorded` —— 汇总 `usage`，包含缓存的创建 / 读取 |
| **Codex** | `~/.codex/sessions/**/rollout-*.jsonl`（以及 `archived_sessions/`） | `recorded` —— 最终的 `token_count` 事件（包含缓存输入与推理） |
| **Cursor** | 全局 SQLite 数据库 `…/Cursor/User/globalStorage/state.vscdb` | `context-snapshot` —— 见下文 |
| **Antigravity** | `~/.gemini/antigravity{,-cli}/conversations/*.db` | `recorded` —— `gen_metadata` 用量（输入、缓存读、输出、推理） |
| **Pi Agent** | `~/.pi/agent/sessions/**/*.jsonl` | `recorded` —— 每轮 `usage`（input、output、cacheRead、cacheWrite） |

### Claude Code

每个项目文件夹为每条会话保存一个 JSONL 文件。Token 用量由每个助手轮次的 `usage` 对象汇总而来，并读取出 5 分钟 / 1 小时的缓存写入拆分以精确计算成本。项目路径来自日志中记录的 `cwd`。

### Codex

Rollout 文件可能达到数百 MB。Session Exporter 采用流式读取 —— 在字节层面计数消息，只对头部（会话元数据、首条用户消息、模型）和尾部（最终的 token 计数）做 JSON 解析 —— 因此一条 650 MB 的会话可以在远不到一秒内列出。超大会话的消息计数是一个快速的字节层面估算（相差正负几个系统轮次）；其他每一个数字都是精确的。

### Cursor

Cursor 把一切都存储在一个大型的 SQLite 数据库中。Session Exporter 以**严格只读**方式打开它（`?mode=ro`，失败时回退到 `?immutable=1`），并且只做带索引的主键查找 —— 它绝不会写入、锁定或以其他方式触碰你正在使用的 Cursor 数据库，即便 Cursor 正在运行。

Cursor 不记录累计的 token 花费或缓存活动 —— 只记录会话最终上下文窗口的大小。Session Exporter 会如实地将这个数字呈现为 `context-snapshot`（用 `~` 标记），并且**不**为它计算成本，而不是凭空捏造一个。

### Antigravity

Antigravity（IDE 与 CLI）在 `~/.gemini/antigravity/conversations/` 和 `~/.gemini/antigravity-cli/conversations/` 下为每条会话保存一个 SQLite 数据库。Session Exporter 以**只读**方式打开（优先 `?immutable=1`，避免 WAL 旁路文件阻塞扫描），并用一个很小的 protobuf wire-format 读取器解码 `gen_metadata` / `steps` / `trajectory_metadata_blob` 中的二进制 —— 无需第三方 protobuf 依赖。

Token 总量来自已记录的生成元数据（未缓存输入、缓存读、输出文本、推理）。工作区路径来自 trajectory 元数据。旧版加密的 `.pb` 会话文件会被跳过；只支持 SQLite `.db` 格式。

### Pi Agent

Pi Agent 在 `~/.pi/agent/sessions/<encoded-cwd>/` 下为每条会话保存一个 JSONL 文件。文件以 `type:"session"` 头开始（id、cwd、timestamp），随后是 `message` 事件流。助手轮次带有记录的 `usage`（`input` / `output` / `cacheRead` / `cacheWrite`）。Session Exporter 汇总这些字段，并把 text、thinking、toolCall 块渲染进转录。

## 缓存

扫描结果会写入应用旁边的 `.cache/index.json`，并以你的会话文件的指纹（路径 + 大小 + 修改时间）作为键。如果没有变化，重新启动时会瞬时从缓存加载。如果文件有变化，或者你点击了 **Refresh**，索引就会重建。删除 `.cache/` 只会强制一次全新扫描 —— 这是安全的。

成本会在每次加载时应用到缓存的索引上，因此编辑 `pricing.json` 会在下次启动时生效（或通过 **↻ Reload prices** 立即生效），无需重新解析你的数据。

## 添加另一种来源

每个解析器都是 `parsers/` 目录下的单个文件，实现一个小型契约 —— `list_sessions()` 和 `load_messages()`。添加另一种工具就是一个新文件；应用中的其他部分都无需知道它的存在。
