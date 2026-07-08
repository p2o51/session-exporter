# Notion へエクスポート

**Export for Notion** ボタンは、Notion の CSV / Markdown インポーター向けに形作られたアーカイブを生成します。各セッションはデータベースの行になり、ページ本文が完全なトランスクリプト、プロパティがメタデータになります — そのため、Notion 内で同じフィルタを再現できます。

## アーカイブ

```
sessions-notion.zip
├── Sessions.csv           # セッションごとに 1 行。列が DB プロパティになる
├── HOW_TO_IMPORT.txt
└── Sessions/
    ├── <Session title>.md # トランスクリプト。ファイル名は CSV の「Name」列と一致
    └── …
```

仕組みのポイントは、各 Markdown ファイルの名前が、その CSV 行の `Name` 値と**完全に一致**することです。Notion は自動でそれらを紐付けます: 行のプロパティは CSV から、ページ本文は一致する `.md` から取得されます。

## 列 → プロパティ

`Sessions.csv` は次の列を持ち、Notion がそれらをデータベースのプロパティに変換します:

| 列 | Notion のプロパティタイプ |
| --- | --- |
| Name | タイトル |
| Source | テキスト / セレクト |
| Project, Project Path | テキスト |
| Created, Updated | 日付 |
| Model | テキスト / セレクト |
| Messages, Total / Input / Output / Cache Read / Reasoning Tokens | 数値 |
| Cache Hit Rate | テキスト |
| Cost (USD), Cost Estimated | 数値 / テキスト |
| Token Basis, Session ID | テキスト |

## インポート

1. アーカイブを**解凍**し、`Sessions.csv` と `Sessions/` フォルダが並んで配置されるようにします。
2. Notion でサイドバーを開き、**Import → CSV**（または **Markdown & CSV**）を選びます。
3. **`Sessions.csv`** を選択します。Notion がデータベースを作成し、各行のトランスクリプトをページ本文としてインポートし、列をプロパティに変換します。
4. それらのプロパティを使って、Notion 内で**フィルタを再現**します — Source や Project でフィルタ、Updated や Total Tokens や Cost で並べ替え、Model でグループ化、といった具合です。

zip 内の `HOW_TO_IMPORT.txt` に、これらの手順が参照用に繰り返し記載されています。

## ヒント: エクスポート前にフィルタする

どちらのエクスポートも現在の選択を反映します。よくある流れ: リストをフィルタし（例: あるプロジェクト、直近 30 日間）、**すべて選択** してから **Export for Notion** — ちょうどそのスライスが、インポート可能なデータベースとして得られます。
