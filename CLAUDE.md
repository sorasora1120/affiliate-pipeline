# CLAUDE.md（affiliate-pipeline）

セッション開始時に必ず `progress.md` を読んでから作業すること。作業の区切りで `progress.md` を更新してコミットする。

## ユーザーについて
- 返事は日本語で、短く。質問は最小限にして手を動かす（迷ったら妥当な方を選び、何を選んだか一言書く）
- 留学中の高校生（18歳未満）。iPad / iPhone で見ている
- 学校のネットワークは github.com / github.io がブロックされる。ページを渡すときは
  `https://rawcdn.githack.com/sorasora1120/<repo>/<コミットSHA>/<path>` の形（コミット固定）で渡す
  （raw.githack.com は 429 になったので使わない）
- ビューア（dispatch-viewer）は開くと最新版へ自動で移るので、直すたびに新しいリンクを渡さない。直したら
  `viewer_version.yml` を手動実行（スプレッドシートの「設定」タブ B1 に最新SHAを書く。2026-10-09〜）

## ビジネスの全体像
- CrowdWorks の Web制作案件を自動収集 → 「ソラ」として応募 → 海外のワーカーに予算−手数料−利益で外注する
- 応募アカウントは**親の名義**（CrowdWorks は18歳以上が条件のため）。報酬は登録者と同名義の口座に出る
- **2026-10-20〜 最初の1件が決まるまでは作るのが Claude**（ユーザー「それで行こう」。応募213件・返信0件だったため）。
  `config.FIRST_JOB_MODE`（既定 "1"）：見積りは予算の範囲の一番下（`low_budget_yen`）、ワーカー代0で利益＝金額−手数料（`split_amount_self`）、
  納期は短め（`_DAYS_SELF`）、提案文に「制作にはAIも活用しています」と正直に書く、Illustrator の AI 形式は書かない、
  「AI不可」の案件は「対象外（AI不可）」で外す（`forbids_ai`）。ワーカー向けメッセージの欄は「作るのは Claude…」の自分用メモ。
  1件決まったら、ユーザーと相談して FIRST_JOB_MODE を "0" に戻す（見積りは範囲の真ん中・作るのはワーカー）
- 関連リポジトリ
  - `affiliate-pipeline`（ここ）: 収集・マッチング・提案文生成（GitHub Actions + Googleスプレッドシート）
  - `dispatch-viewer`: スプレッドシートを読むビューア（index.html）と営業ページ（sales.html）
  - `sorasora1120.github.io`: ポートフォリオ（提案文からリンクしている）

## 守ること（変えない）
- 提案の**自動送信はしない**（規約違反）。人間がコピペで送る。Lancers のボット判定を回避する処理も書かない
- X の DM 送信も自動化しない
- 制作サンプルは必ず「架空の店舗」と明記する
- ワーカーの制作サイトは「チーム（連携しているデザイナー・エンジニア）の実績」としてだけ載せる。ソラ本人の実績と書かない
- 経験年数・件数などの数字を盛らない／作らない
- 利益計算は手数料込み：CrowdWorks は 10万円以下の部分 20%・10〜20万円 10%・20万円超 5%。
  利益 = マージン、ワーカーへの見積 = 金額 − 手数料 − マージン（`worker_matcher.split_amount`）

## コードのルール
- 案件カテゴリと除外キーワードは3箇所を揃える：
  `job_scraper/config.py`、`.github/workflows/cw_collect_attempt.yml` の `JOB_KEYWORDS` /
  `worker_match.yml` の `WORKER_MATCH_CATEGORIES`・`WORKER_MATCH_EXCLUDE_KEYWORDS`、
  `dispatch-viewer/index.html` の同名の JS 定数
  （「題名に制作の作業がはっきり書いてあれば外さない」除外語 `worker_matcher.SOFT_EXCLUDE_KEYWORDS` も、
  dispatch-viewer と docs の index.html の `SOFT_EXCLUDE_KEYWORDS`・`isExcluded` と揃える）
- 2026-10-12〜、サイト制作のほかに**チラシ・名刺・ロゴ・バナー・パッケージのデザインの仕事**も拾う（ユーザー「じゃあ仕事増やそう」。
  ワーカーには Fiverr で仕事が決まってから頼む）。判定は `worker_matcher.job_passes`（サイト制作の今までの判定 か `is_design_job`）。
  `design_kind` / `is_design_job` / `DESIGN_EXCLUDE_EXEMPT` を変えたら、dispatch-viewer と docs の `isDesignJob`・`DESIGN_*` も揃える。
  Instagram投稿・未経験歓迎などの大量募集、配布・入力・施工などの作業は `_DESIGN_BLOCK_RE` で外す。提案文は `DESIGN_SAMPLES_URL`
  （ポートフォリオの design.html、架空のお店のサンプル）を案内する
- cron は毎時0分を避けて分をずらす（0分は数時間遅れたことがある）
- スプレッドシートの列：S=応募者数、T=募集文。列を足すときは `SheetsWriter` が足りない列を追加する作りを保つ
- テスト：`cd job_scraper && python -m unittest discover -s tests -v`。
  `| tail` などでパイプすると終了コードが隠れるので、結果は終了コードで判断する
- 変更したら必ずテストを通してからコミット
- 相談で使う道具（手動のワークフロー、注釈に結果が出る）：`find_job.yml`（題名の一部で案件をさがす。読むだけ）・
  `set_stage.yml`（URLで1行の進捗ステージを付ける。ユーザーがビューアのボタンを押し忘れた時）

## Git
- 作業ブランチの指定がなければ `main` に直接コミット＆push（これまでずっとそうしている）
- push が 5xx やネットワークエラーで失敗したら 2s→4s→8s→16s で再試行
- コミットメッセージ末尾には、そのセッションで指示される帰属行（`Co-Authored-By:` と `Claude-Session:`）を付ける
- コミット・PR・コード内にモデルIDを書かない
