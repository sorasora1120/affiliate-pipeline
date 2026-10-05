# CrowdWorks案件収集ブックマークレット

CrowdWorksはGitHub Actionsのクラウド共有IPからのアクセスを403で拒否するため、
`job_scraper/src/crowdworks_scraper.py`（Playwright版）はクラウド側では
動かせず、ローカルPCのタスクスケジューラでしか収集できない
（`.github/workflows/job_scraper.yml`のコメント参照）。

PCが起動していない期間（留学中など）でも、自分のブラウザでCrowdWorksの
検索結果ページを開いた時にこのブックマークレットを実行すれば、同じ抽出
ロジックで案件情報をスプレッドシートの行形式（TSV）としてクリップボードに
コピーできる。自分のブラウザからの通常アクセスなので、クラウド側IPブロック
の対象にならない。

## 導入方法

1. ブラウザでブックマークバー（またはブックマーク管理）を開き、新しい
   ブックマークを作成する
2. 名前は何でもいい（例: 「CW案件収集」）
3. URL欄に `crowdworks_collect.min.txt` の中身（`javascript:` で始まる
   1行）をそのまま貼り付けて保存する

## 使い方

1. CrowdWorksで案件を検索し、検索結果一覧ページ
   （`crowdworks.jp/public/jobs/search?...`）を開く
2. 保存したブックマークをクリックする
3. 「n件コピーしました」と出たら、スプレッドシートの最終行の次の行の
   A列を選択してペースト（Ctrl+V / Cmd+V）する

キーワード検索なしの「新着の仕事」一覧ページでも動作する（その場合は
カテゴリ列が空欄になる）。

## ファイル

- `crowdworks_collect.js` — 読める版のソース（コメント付き）
- `crowdworks_collect.min.txt` — ブックマークのURL欄にそのまま貼る
  `javascript:...` の1行

ソースを直した場合は、`crowdworks_collect.min.txt` を手で直すのではなく
terserで作り直すこと（素朴な正規表現での圧縮は `"https://..."` のような
文字列中の `//` をコメントと誤認識して壊れるため、terser等の構文を正しく
解釈するミニファイアを使うこと）:

```
npx terser crowdworks_collect.js --compress --mangle -o /tmp/min.js
node -e 'const fs=require("fs");fs.writeFileSync("crowdworks_collect.min.txt","javascript:"+encodeURIComponent(fs.readFileSync("/tmp/min.js","utf8")))'
```
