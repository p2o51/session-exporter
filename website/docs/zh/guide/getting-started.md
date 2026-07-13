# 开始使用

Session Exporter 是一个小巧的本地 Web 应用，它读取你的 **Claude Code**、**Codex**、**Cursor** 和 **Antigravity** 会话历史，让你浏览和筛选，并将其导出 —— 附带 token 与成本核算。

它完全运行在你的机器上，不会把任何东西上传到任何地方。

## 环境要求

- **Python 3.9+** —— 仅此而已。本应用只使用 Python 标准库，**零第三方依赖**。
- macOS、Linux 或 Windows。（会话文件的位置会自动检测；参见 [数据与隐私](/zh/guide/data-sources)。）

## 安装与运行

```bash
git clone https://github.com/p2o51/session-exporter.git
cd session-exporter
python3 app.py
```

你的浏览器会打开 **http://127.0.0.1:8765**。安装就到此为止 —— 没有构建步骤，也无需 `pip install`。

### 选项

```bash
python3 app.py --port 9000     # 使用不同的端口
python3 app.py --no-open       # 不自动打开浏览器
python3 app.py --host 0.0.0.0  # 绑定所有网络接口（小心 —— 这会将其暴露到你的局域网）
```

## 首次启动

首次启动会对你的历史进行**索引**。尤其是 Codex，可能会保留数十 GB 的 rollout 文件，因此这大约需要 10 秒。Session Exporter 是流式读取这些文件，而非整体加载，所以内存占用始终平稳。

结果会缓存到 `.cache/index.json`，并以你的会话文件的指纹作为键 —— 因此**后续启动都是瞬时的**。每当你的历史发生变化时，点击顶栏的 **Refresh** 即可重新扫描。

## 你会看到什么

- 一个**顶栏**，显示会话总数、token 总量、估算的总成本，以及一个 Refresh 按钮。
- 一个**左侧栏**的筛选器：搜索、来源、项目和日期范围。
- 一个**主表格**列出会话，各列为来源、项目、更新日期、消息数、token、成本和缓存命中率。
- 点击任意一行可打开**详情抽屉**，其中包含完整记录以及 token / 成本拆解。
- 勾选若干行会显示**导出栏**，并可打开 **Stats** 面板查看按模型和按日期的成本。

下一步：[浏览与导出](/zh/guide/browsing-exporting)。
