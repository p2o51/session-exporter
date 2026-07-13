---
pageType: home

hero:
  name: Session Exporter
  text: AIコーディング履歴を閲覧・エクスポート
  tagline: Claude Code · Codex · Cursor · Antigravity — トークンとコストの集計付きで、ひとつのリストに
  image:
    src: /logo.svg
    alt: Session Exporter
  actions:
    - theme: brand
      text: はじめる
      link: /ja/guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/p2o51/session-exporter

features:
  - title: 4つのツールをひとつのリストで
    details: Claude Code、Codex、Cursor、Antigravity のすべてのセッションをまとめて閲覧できます。ソース、プロジェクトフォルダ、期間、全文検索でフィルタリング。更新日時、コスト、トークン、サイズで並べ替えできます。
    icon: 🗂️
  - title: 複数選択 → ZIP エクスポート
    details: 個別に選択、または（適用中のフィルタに従って）すべて選択してから、自己完結型のアーカイブをエクスポート。メタデータのインデックスに加え、セッションごとに機械可読の JSON と人間が読める Markdown のトランスクリプトが含まれます。
    icon: 📦
  - title: Notion 向けエクスポート
    details: Notion がデータベースとしてインポートできる CSV と対応する Markdown フォルダ。トランスクリプトがページ本文、メタデータがプロパティになるので、Notion 内でフィルタを再現できます。
    icon: 📓
  - title: キャッシュ対応のトークン集計
    details: プロバイダーが実際に記録した本物の使用量 — 入力 / 出力 / キャッシュ読み取り / キャッシュ書き込み / 推論トークン、さらにキャッシュヒット率を、セッション単位・選択範囲単位で表示します。
    icon: 🔢
  - title: コスト見積もり
    details: すべてのセッションを、トークン数 × モデルごとの単価で価格算出（キャッシュ読み取りは 0.1 倍、Anthropic のキャッシュ書き込みは 1.25 倍/2 倍）。Stats パネルでモデル別・日付別にコストを分解します。
    icon: 💰
  - title: ローカルで完結、プライベート
    details: ローカルのセッションファイルを直接読み取り — 何もマシンの外に出ません。純粋な Python 3.9 以上の標準ライブラリのみで、依存ゼロ。Cursor と Antigravity のデータベースは厳密に読み取り専用で開きます。
    icon: 🔒
---
