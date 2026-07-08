# Export to Notion

The **Export for Notion** button produces an archive shaped for Notion's CSV / Markdown importer. Each session becomes a database row whose page body is the full transcript, and whose properties are the metadata — so you can rebuild the same filters inside Notion.

## The archive

```
sessions-notion.zip
├── Sessions.csv           # one row per session; columns become DB properties
├── HOW_TO_IMPORT.txt
└── Sessions/
    ├── <Session title>.md # transcript; filename matches the CSV "Name" column
    └── …
```

The trick is that each Markdown file's name **exactly matches** the `Name` value of its CSV row. Notion pairs them automatically: the row's properties come from the CSV, and its page body comes from the matching `.md`.

## Columns → properties

`Sessions.csv` carries these columns, which Notion turns into database properties:

| Column | Notion property type |
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

## Importing

1. **Unzip** the archive so `Sessions.csv` and the `Sessions/` folder sit side by side.
2. In Notion, open the sidebar and choose **Import → CSV** (or **Markdown & CSV**).
3. Select **`Sessions.csv`**. Notion creates a database, imports each row's transcript as the page body, and turns the columns into properties.
4. **Rebuild your filters** inside Notion using those properties — filter by Source or Project, sort by Updated or Total Tokens or Cost, group by Model, and so on.

`HOW_TO_IMPORT.txt` inside the zip repeats these steps for reference.

## Tip: filter before you export

Both exports honour your current selection. A common flow: filter the list (e.g. one project, the last 30 days), **Select all**, then **Export for Notion** — you get exactly that slice as a ready-to-import database.
