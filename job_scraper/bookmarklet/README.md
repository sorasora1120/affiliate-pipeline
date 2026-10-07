# 案件収集ブックマークレット（CrowdWorks / ランサーズ）

CrowdWorksはGitHub Actionsのクラウド共有IPからのアクセスを403で拒否し、
ランサーズはボット確認画面を出すため、どちらもクラウドから自動収集できない。
自分のブラウザで検索結果を開いてこのブックマークを押すと、表示中の案件を
スプレッドシート「案件一覧」の行形式でクリップボードにコピーする。

## 導入方法

1. ブラウザで新しいブックマークを作る（名前は「案件収集」など何でもいい）
2. URL欄に `collect.min.txt` の中身（`javascript:` で始まる1行）をそのまま貼って保存する

## 使い方

1. CrowdWorksかランサーズで案件を検索し、検索結果一覧を開く
   （「サイト制作」「LP制作」「ホームページ制作」などで検索すると良い）
2. 保存したブックマークを押す
3. 「n件コピーしました」と出たら、スプレッドシート「案件一覧」の最終行の次の行の
   A列を選んで貼り付ける

貼り付けた案件は、次の定期マッチング（1日3回）で自動的に判定される。サイト制作と
関係ない案件はそこで外れ、残ったものがDispatchビューアの「送れる案件」に出る。
ページの作りが変わって0件になったら、ブックマークのコードを直す必要がある。

## ファイル

- `collect.js` — 読める版のソース
- `collect.min.txt` — ブックマークのURL欄に貼る1行

ソースを直したら `collect.min.txt` はterserで作り直すこと（素朴な正規表現での圧縮は
`"https://..."` の `//` をコメントと誤認して壊れる）:

```
npx terser collect.js --compress --mangle -o /tmp/min.js
node -e 'const fs=require("fs");fs.writeFileSync("collect.min.txt","javascript:"+encodeURIComponent(fs.readFileSync("/tmp/min.js","utf8")))'
```
