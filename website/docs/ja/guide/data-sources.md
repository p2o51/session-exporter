# データとプライバシー

Session Exporter は、ローカルのセッションファイルを直接読み取ります。**何もマシンの外に出ません** — アカウントもテレメトリもなく、`127.0.0.1` 上であなた自身のブラウザに UI を配信する以外のネットワーク通信はありません。

## データの出どころ

| ソース | 場所 | トークンの根拠 |
| --- | --- | --- |
| **Claude Code** | `~/.claude/projects/<folder>/<uuid>.jsonl` | `recorded` — キャッシュの作成/読み取りを含む `usage` を合算 |
| **Codex** | `~/.codex/sessions/**/rollout-*.jsonl`（および `archived_sessions/`） | `recorded` — 最終的な `token_count` イベント（キャッシュ入力と推論を含む） |
| **Cursor** | グローバル SQLite DB `…/Cursor/User/globalStorage/state.vscdb` | `context-snapshot` — 後述 |
| **Antigravity** | `~/.gemini/antigravity{,-cli}/conversations/*.db` | `recorded` — `gen_metadata` の使用量（入力・キャッシュ読取・出力・推論） |

### Claude Code

各プロジェクトフォルダには、セッションごとに 1 つの JSONL ファイルが入っています。トークン使用量はすべてのアシスタントターンの `usage` オブジェクトから合算され、正確なコスト算出のために 5 分 / 1 時間のキャッシュ書き込みの内訳が読み取られます。プロジェクトパスは、ログに記録された `cwd` から取得されます。

### Codex

ロールアウトファイルは数百メガバイトに達することがあります。Session Exporter はそれらをストリーミング処理します — バイトレベルでメッセージを数え、先頭（セッションのメタデータ、最初のユーザーメッセージ、モデル）と末尾（最終的なトークン数）のみを JSON パースします — そのため 650 MB のセッションも 1 秒未満で一覧に表示されます。非常に大きなセッションのメッセージ数は高速なバイトレベルの推定値です（システムターン数ターン分の誤差あり）。それ以外のすべての数値は正確です。

### Cursor

Cursor はすべてを 1 つの大きな SQLite データベースに保存します。Session Exporter はそれを**厳密に読み取り専用**（`?mode=ro`、フォールバックは `?immutable=1`）で開き、インデックス付きの主キー参照しか行いません — Cursor が実行中であっても、稼働中の Cursor データベースへの書き込み、ロック、その他の変更を一切行いません。

Cursor は累積のトークン消費量やキャッシュの動作を記録せず、セッションの最終的なコンテキストウィンドウのサイズだけを記録します。Session Exporter はその数値を `context-snapshot`（`~` で表示）として正直に提示し、でっち上げるのではなく、コストを計算**しません**。

### Antigravity

Antigravity（IDE と CLI）は、`~/.gemini/antigravity/conversations/` と `~/.gemini/antigravity-cli/conversations/` の下に会話ごとに 1 つの SQLite データベースを保存します。Session Exporter は各 DB を**読み取り専用**で開き（WAL サイドカーにブロックされないよう `?immutable=1` を優先）、`gen_metadata` / `steps` / `trajectory_metadata_blob` 内の protobuf ブロブを小さな wire-format リーダーでデコードします — サードパーティの protobuf 依存はありません。

トークン合計は記録済みの生成メタデータ（キャッシュされていない入力、キャッシュ読取、出力テキスト、推論）から取得します。ワークスペースパスは trajectory メタデータから取得します。レガシーな暗号化 `.pb` 会話ファイルはスキップされ、SQLite の `.db` 形式のみがサポートされます。

## キャッシュ

スキャン結果はアプリの隣の `.cache/index.json` に書き込まれ、セッションファイルのフィンガープリント（パス + サイズ + 更新時刻）をキーにします。何も変わっていなければ、再起動時にキャッシュから瞬時に読み込まれます。ファイルが変わったり、**Refresh** をクリックしたりすると、インデックスが再構築されます。`.cache/` を削除すると新規スキャンが強制されるだけで、安全です。

コストは読み込みのたびにキャッシュされたインデックスへ適用されるため、`pricing.json` の編集は次回起動時（または **↻ Reload prices** で即座に）、データを再パースすることなく反映されます。

## 別のソースを追加する

各パーサーは `parsers/` 内の単一ファイルで、小さな契約 — `list_sessions()` と `load_messages()` — を実装しています。別のツールを追加するのは新しいファイル 1 つだけで、アプリの他の部分はそれについて何も知る必要がありません。
