# 导出到 Notion

**Export for Notion** 按钮会生成一个为 Notion 的 CSV / Markdown 导入器量身定制的归档。每条会话都会成为数据库中的一行，其页面正文是完整的会话记录，其属性则是元数据 —— 这样你就能在 Notion 内重建相同的筛选。

## 归档结构

```
sessions-notion.zip
├── Sessions.csv           # 每条会话一行；各列成为数据库属性
├── HOW_TO_IMPORT.txt
└── Sessions/
    ├── <Session title>.md # 会话记录；文件名与 CSV 的 "Name" 列匹配
    └── …
```

其中的关键在于：每个 Markdown 文件的名称**恰好匹配**其 CSV 行的 `Name` 值。Notion 会自动将二者配对：行的属性来自 CSV，而其页面正文来自匹配的 `.md`。

## 列 → 属性

`Sessions.csv` 承载以下列，Notion 会将它们转化为数据库属性：

| 列 | Notion 属性类型 |
| --- | --- |
| Name | Title |
| Source | Text / Select |
| Project, Project Path | Text |
| Created, Updated | Date |
| Model | Text / Select |
| Messages, Total / Input / Output / Cache Read / Reasoning Tokens | Number |
| Cache Hit Rate | Text |
| Cost (USD), Cost Estimated | Number / Text |
| Token Basis, Session ID | Text |

## 导入

1. **解压**归档，让 `Sessions.csv` 和 `Sessions/` 文件夹并排放置。
2. 在 Notion 中，打开侧边栏并选择 **Import → CSV**（或 **Markdown & CSV**）。
3. 选择 **`Sessions.csv`**。Notion 会创建一个数据库，将每一行的会话记录导入为页面正文，并将各列转化为属性。
4. 在 Notion 内使用这些属性**重建你的筛选** —— 按 Source 或 Project 筛选，按 Updated 或 Total Tokens 或 Cost 排序，按 Model 分组，等等。

zip 内的 `HOW_TO_IMPORT.txt` 重复了这些步骤以供参考。

## 提示：先筛选，再导出

两种导出都会遵从你当前的选择。一个常见流程是：筛选列表（例如某一个项目、最近 30 天），**全选**，然后 **Export for Notion** —— 你就能得到恰好那一部分内容，作为一个可直接导入的数据库。
