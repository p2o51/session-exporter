<div align="center">

<img src="website/docs/public/logo.svg" width="72" alt="Session Exporter" />

# Session Exporter

**Claude Code / Codex / Cursor / Antigravity / Pi Agent の履歴を閲覧・エクスポート — トークンとコストの集計付き。**

[English](README.md) · [简体中文](README.zh-CN.md) · 日本語

[![License: MIT](https://img.shields.io/badge/License-MIT-3c5a7c.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-2f8f6f.svg)](https://www.python.org/)
[![Zero dependencies](https://img.shields.io/badge/dependencies-0-c1662f.svg)](#)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-3c5a7c.svg)](https://p2o51.github.io/session-exporter/ja/)

📖 **[ドキュメント](https://p2o51.github.io/session-exporter/ja/)** · [English](https://p2o51.github.io/session-exporter/) · [简体中文](https://p2o51.github.io/session-exporter/zh/)

</div>

---

**ローカル**で動く小さくて上品な Web アプリです。**Claude Code**・**Codex**・**Cursor**・
**Antigravity**・**Pi Agent** のセッション履歴を読み込み、閲覧・フィルタ・エクスポートできます。実測の
トークン集計（キャッシュヒットを含む）と、キャッシュを考慮した**コスト見積もり**付き。
データは一切外部に出ません。

## 特長

- **5 つのツールを 1 つのリストに** — Claude Code / Codex / Cursor / Antigravity / Pi Agent の全セッションを
  まとめて表示。ソース・プロジェクトフォルダ・期間・全文検索でフィルタでき、更新日・コスト・
  トークン・サイズで並べ替えられます。
- **複数選択 → ZIP** — 選択または全選択（現在のフィルタに追従）して、自己完結型のアーカイブを
  出力します。メタデータのインデックスに加え、セッションごとの JSON と読みやすい Markdown
  トランスクリプトを含みます。
- **Notion へエクスポート** — CSV と同名の Markdown フォルダを出力。Notion はこれをデータベース
  として取り込み（トランスクリプトをページ本文、メタデータをプロパティに）、Notion 内で
  フィルタを再構築できます。
- **キャッシュ込みのトークン集計** — プロバイダが実際に記録した 入力 / 出力 / キャッシュ読取 /
  キャッシュ書込 / 推論 トークンと、キャッシュヒット率を、セッションごと・選択ごとに集計します。
- **コスト見積もり** — 各セッションを トークン × モデル別単価 で計算。キャッシュ読取（0.1×）と
  Anthropic のキャッシュ書込（1.25× / 2×）を正しく計上します。**Stats パネル**は
  コストを**モデル別**・**日付別**に分解します。単価は編集可能な
  [`pricing.json`](pricing.json) にあります。
- **ローカルかつプライベート** — 純粋な Python 3.9+ 標準ライブラリのみ、**依存関係ゼロ**。
  Cursor と Antigravity のデータベースは厳密に読み取り専用で開きます。

## スクリーンショット

![セッション一覧と選択バー](pics/list.png)

*メイン一覧と選択バー*

![ソースフィルタチップ](pics/sources.png)

*ソースチップ*

![コストと使用量の統計](pics/stats.png)

*コスト＆使用量の統計*

## クイックスタート

```bash
git clone https://github.com/p2o51/session-exporter.git
cd session-exporter
python3 app.py
```

ブラウザが **http://127.0.0.1:8765** で開きます。ビルド不要、`pip install` 不要。

```bash
python3 app.py --port 9000     # ポートを変更
python3 app.py --no-open       # ブラウザを自動で開かない
```

初回起動時に履歴をインデックス化します（約 10 秒 — Codex は大きな rollout ファイルを
持つため、ストリーミングで読み込みます）。結果はキャッシュされるので、次回以降の起動は
一瞬です。**Refresh** で再スキャンできます。

## データの取得元

| ソース | 場所 | トークンの根拠 |
| --- | --- | --- |
| **Claude Code** | `~/.claude/projects/<folder>/<uuid>.jsonl` | `recorded` — `usage` の合計（キャッシュ作成/読取を含む） |
| **Codex** | `~/.codex/sessions/**/rollout-*.jsonl`（および `archived_sessions/`） | `recorded` — 最後の `token_count`（キャッシュ入力・推論を含む） |
| **Cursor** | グローバル SQLite `…/Cursor/User/globalStorage/state.vscdb`（読み取り専用） | `context-snapshot` — 最終コンテキストサイズであり、実支出ではない |
| **Antigravity** | `~/.gemini/antigravity{,-cli}/conversations/*.db`（読み取り専用） | `recorded` — `gen_metadata` の使用量（入力・キャッシュ読取・出力・推論） |
| **Pi Agent** | `~/.pi/agent/sessions/**/*.jsonl` | `recorded` — ターンごとの `usage`（input・output・cacheRead・cacheWrite） |

`recorded` でない数値には `~` が付き、集計を正直に保ちます。Cursor のセッションは
コスト計算の対象外です。

## プロジェクト構成

```
app.py            エントリポイント（サーバ起動、ブラウザを開く）
server.py         標準ライブラリの HTTP サーバ + JSON/zip API
model.py          メモリ + ディスクのインデックス、トークン集計
pricing.py        モデル別・キャッシュ考慮のコストエンジン
pricing.json      編集可能なモデル別単価（$/1M トークン）
exporters.py      raw-zip と Notion-zip のビルダー
parsers/          claude · codex · cursor · antigravity · pi（ソースごとに 1 契約）
web/              index.html · styles.css · app.js（UI）
website/          Rspress ドキュメントサイト（3 言語）
```

各パーサーは小さな契約（`list_sessions()` / `load_messages()`）を実装しているので、
新しいソースを追加するには [`parsers/`](parsers/) にファイルを 1 つ足すだけです。

## ドキュメント

完全なドキュメント（English / 简体中文 / 日本語）は **https://p2o51.github.io/session-exporter/** に
あります。[Rspress](https://rspress.rs/) で構築し、GitHub Actions 経由で [`website/`](website/) から
自動デプロイされます。

## ライセンス

[MIT](LICENSE) © 2026 Chen Wuyi ([@p2o51](https://github.com/p2o51))
