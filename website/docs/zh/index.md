---
pageType: home

hero:
  name: Session Exporter
  text: 浏览并导出你的 AI 编程历史
  tagline: Claude Code · Codex · Cursor · Antigravity —— 汇于一处，附带 token 与成本核算
  image:
    src: /logo.svg
    alt: Session Exporter
  actions:
    - theme: brand
      text: 开始使用
      link: /zh/guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/p2o51/session-exporter

features:
  - title: 一份列表，四种工具
    details: 将每一条 Claude Code、Codex、Cursor 和 Antigravity 会话汇聚到一起浏览。可按来源、项目文件夹、日期范围以及全文搜索进行筛选，并按最近更新、成本、token 或体积排序。
    icon: 🗂️
  - title: 多选 → ZIP 导出
    details: 逐条勾选或全选（跟随当前生效的筛选条件），然后导出一个自包含的归档 —— 内含元数据索引，以及每条会话的机器可读 JSON 和人类可读的 Markdown 记录。
    icon: 📦
  - title: 导出到 Notion
    details: 一个 CSV 加上配套的 Markdown 文件夹，Notion 会将其导入为一个数据库 —— 会话记录作为页面正文，元数据作为属性，让你在 Notion 内重建筛选。
    icon: 📓
  - title: 含缓存的 token 核算
    details: 真实的、由服务商记录的用量 —— 输入 / 输出 / 缓存读取 / 缓存写入 / 推理 token，外加缓存命中率，按会话和按选区分别统计。
    icon: 🔢
  - title: 成本估算
    details: 每条会话都根据其 token × 各模型费率来定价（缓存读取 0.1×，Anthropic 缓存写入 1.25×/2×）。Stats 面板会按模型和按日期拆解成本。
    icon: 💰
  - title: 本地且私密
    details: 直接读取你本地的会话文件 —— 没有任何数据离开你的机器。纯 Python 3.9+ 标准库，零依赖。Cursor 与 Antigravity 的数据库以严格只读方式打开。
    icon: 🔒
---
