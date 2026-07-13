<div align="center">

<img src="website/docs/public/logo.svg" width="72" alt="Session Exporter" />

# Session Exporter

**浏览并导出你的 Claude Code / Codex / Cursor / Antigravity 会话历史 —— 附带 token 与花费统计。**

[English](README.md) · 简体中文 · [日本語](README.ja.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-3c5a7c.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-2f8f6f.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-c1662f.svg)](#)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-3c5a7c.svg)](https://p2o51.github.io/session-exporter/zh/)

📖 **[文档](https://p2o51.github.io/session-exporter/zh/)** · [English](https://p2o51.github.io/session-exporter/) · [日本語](https://p2o51.github.io/session-exporter/ja/)

</div>

---

一个小巧、典雅的**本地**网页工具：读取你的 **Claude Code**、**Codex**、**Cursor**、
**Antigravity** 会话历史，让你浏览、筛选并导出，附带真实的 token 统计（含缓存命中）和
**缓存感知的花费估算**。所有数据都不出本机。

## 功能

- **四个工具，一个列表** —— 所有 Claude Code / Codex / Cursor / Antigravity 会话汇总在一起。
  可按来源、项目文件夹、日期区间、全文搜索筛选；可按时间、花费、token、大小排序。
- **多选 → ZIP 导出** —— 勾选或全选（跟随当前筛选），导出一个自包含压缩包：元数据索引，
  外加每个会话的 JSON 和可读的 Markdown 转录。
- **导出到 Notion** —— 一个 CSV + 同名 Markdown 文件夹，Notion 会把它导入成数据库
  （转录作为页面正文，元数据作为属性），于是你能在 Notion 里重建筛选。
- **含缓存的 token 统计** —— 厂商真实记录的 输入 / 输出 / 缓存读 / 缓存写 / 推理 token，
  以及缓存命中率，按会话和按选中项统计。
- **花费估算** —— 每个会话按 token × 各模型单价计价，缓存读（0.1×）和 Anthropic 缓存写
  （1.25× / 2×）都正确计费。**Stats 面板**按**模型**和**日期**拆分花费。单价存放在可编辑的
  [`pricing.json`](pricing.json) 里。
- **本地且私密** —— 纯 Python 3.9+ 标准库，**零依赖**。Cursor 与 Antigravity 数据库严格只读打开。

## 快速开始

```bash
git clone https://github.com/p2o51/session-exporter.git
cd session-exporter
python3 app.py
```

浏览器会打开 **http://127.0.0.1:8765**。无需构建、无需 `pip install`。

```bash
python3 app.py --port 9000     # 换端口
python3 app.py --no-open       # 不自动打开浏览器
```

首次启动会索引你的历史（约 10 秒 —— Codex 的 rollout 文件很大，采用流式读取），结果会缓存，
之后启动秒开。点 **Refresh** 重新扫描。

## 数据来源

| 来源 | 位置 | Token 依据 |
| --- | --- | --- |
| **Claude Code** | `~/.claude/projects/<文件夹>/<uuid>.jsonl` | `recorded` —— 汇总 `usage`，含缓存创建/读取 |
| **Codex** | `~/.codex/sessions/**/rollout-*.jsonl`（及 `archived_sessions/`） | `recorded` —— 最后一次 `token_count`（含缓存输入与推理） |
| **Cursor** | 全局 SQLite `…/Cursor/User/globalStorage/state.vscdb`（只读） | `context-snapshot` —— 最终上下文大小，非真实花费 |
| **Antigravity** | `~/.gemini/antigravity{,-cli}/conversations/*.db`（只读） | `recorded` —— `gen_metadata` 用量（输入、缓存读、输出、推理） |

非 `recorded` 的数字会标 `~`，让统计诚实透明；Cursor 会话不计价。

## 项目结构

```
app.py            入口（启动服务器、打开浏览器）
server.py         标准库 HTTP 服务器 + JSON/zip API
model.py          内存 + 磁盘索引，token 汇总
pricing.py        按模型、缓存感知的花费引擎
pricing.json      可编辑的各模型单价（$/1M tokens）
exporters.py      raw-zip 与 Notion-zip 构建
parsers/          claude · codex · cursor · antigravity（每个来源一份契约）
web/              index.html · styles.css · app.js（界面）
website/          Rspress 文档站（三语）
```

每个解析器实现一份很小的契约（`list_sessions()` / `load_messages()`），所以新增来源
只需在 [`parsers/`](parsers/) 里加一个文件。

## 文档

完整文档（English / 简体中文 / 日本語）在 **https://p2o51.github.io/session-exporter/**，
用 [Rspress](https://rspress.rs/) 构建，通过 GitHub Actions 从 [`website/`](website/) 自动部署。

## License

[MIT](LICENSE) © 2026 Chen Wuyi ([@p2o51](https://github.com/p2o51))
