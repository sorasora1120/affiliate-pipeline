/**
 * CrowdWorks案件収集ブックマークレット（手動・ブラウザ実行用）
 *
 * 背景: CrowdWorksはGitHub Actionsのクラウド共有IPからのアクセスを403で
 * 拒否するため、job_scraper/src/crowdworks_scraper.py（Playwright版）は
 * クラウド側では動かせず、ローカルPCのタスクスケジューラでしか収集できない
 * （job_scraper.ymlのコメント参照）。留学中などPCが起動していない期間でも、
 * 自分のブラウザ・自分の回線でCrowdWorksの検索結果ページを開いた時に
 * このスクリプトを実行すれば、同じ抽出ロジックで案件情報をスプレッドシートの
 * 行形式（TSV）としてクリップボードにコピーできる。自分のブラウザからの
 * 通常アクセスなので、クラウド側IPブロックの対象にならない。
 *
 * 使い方:
 *   1. 下記の crowdworks_collect.min.js の中身（javascript:で始まる1行）を
 *      ブラウザのブックマークのURL欄に貼り付けて保存する
 *   2. CrowdWorksで検索した結果一覧ページ（crowdworks.jp/public/jobs/search?...）
 *      を開き、そのブックマークをクリックする
 *   3. 「n件コピーしました」と出たら、スプレッドシートの最終行の次の行のA列を
 *      選択してペースト（Ctrl+V / Cmd+V）する
 *
 * 出力する列は sheets_writer.py の HEADER と同じ並び。スクレイパーが直接
 * 埋められない列（提案文・依頼者名・評価など、後段のworker_matcher.py等が
 * 埋める列）は空欄のまま出力する。
 */
(function () {
  "use strict";

  // --- deadline_utils.normalize_deadline() のJS移植 ---
  function normalizeDeadline(rawText, detectedDate) {
    if (!rawText) return "不明";
    var m = rawText.match(/あと\s*(\d+)\s*日/);
    if (m) {
      var days = parseInt(m[1], 10);
      var d = new Date(detectedDate.getTime());
      d.setDate(d.getDate() + days);
      return fmtDate(d);
    }
    m = rawText.match(/(\d{4})[\/\-年](\d{1,2})[\/\-月](\d{1,2})日?/);
    if (m) {
      var y = +m[1], mo = +m[2], day = +m[3];
      var dt = new Date(y, mo - 1, day);
      if (dt.getFullYear() === y && dt.getMonth() === mo - 1 && dt.getDate() === day) {
        return fmtDate(dt);
      }
      return "不明";
    }
    return "不明";
  }

  function pad(n) { return String(n).length < 2 ? "0" + n : String(n); }
  function fmtDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function fmtDateTime(d) { return fmtDate(d) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes()); }

  // 実行中のブラウザのタイムゾーンに関わらず、検出日時はJSTで記録する
  // （既存シートの「検出日時」列と揃えるため）
  function jstNow() {
    var now = new Date();
    var utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
    return new Date(utcMs + 9 * 60 * 60000);
  }

  // --- crowdworks_scraper.py の正規表現をそのまま移植 ---
  var BUDGET_RANGE_RE = /[\d,]+\s*円\s*[〜~]\s*[\d,]+\s*円/;
  var BUDGET_SHORTHAND_RE = /[\d,]+\s*万\s*円|[\d,]+\s*千\s*円/;
  var BUDGET_RE = /[¥￥][\d,]+|[\d,]+\s*円/;
  var DEADLINE_RE = /あと\s*\d+\s*日|\d{4}[\/\-]\d{1,2}[\/\-]\d{1,2}/;
  var DETAIL_URL_RE = /\/public\/jobs\/(\d+)/;

  var pageUrl = new URL(location.href);
  var keyword = pageUrl.searchParams.get("search[keywords]") || "";

  var links = Array.prototype.slice.call(document.querySelectorAll("a[href*='/public/jobs/']"));
  var seenIds = {};
  var rows = [];
  var detectedDate = jstNow();
  var detectedAt = fmtDateTime(detectedDate);

  for (var i = 0; i < links.length; i++) {
    var link = links[i];
    var href = link.getAttribute("href") || "";
    var m = href.match(DETAIL_URL_RE);
    if (!m) continue;
    var jobId = m[1];
    if (seenIds[jobId]) continue;
    seenIds[jobId] = true;

    var title = (link.textContent || "").trim();
    if (title.length < 3) continue;

    var fullUrl = href.indexOf("http") === 0 ? href : "https://crowdworks.jp" + href;

    var surrounding = title;
    var li = link.closest("li");
    if (li) {
      surrounding = li.textContent || title;
    } else if (link.parentElement && link.parentElement.parentElement) {
      surrounding = link.parentElement.parentElement.textContent || title;
    }

    // 「おすすめの仕事」等、検索キーワードと無関係なウィジェットのリンクを除外
    if (keyword && title.indexOf(keyword) === -1 && surrounding.indexOf(keyword) === -1) continue;

    var budgetText = "不明";
    var bm = surrounding.match(BUDGET_RANGE_RE);
    if (bm) {
      budgetText = bm[0];
    } else {
      bm = surrounding.match(BUDGET_RE) || surrounding.match(BUDGET_SHORTHAND_RE);
      if (bm) budgetText = bm[0];
    }

    var deadlineText = "不明";
    var dm = surrounding.match(DEADLINE_RE);
    if (dm) deadlineText = normalizeDeadline(dm[0], detectedDate);

    // sheets_writer.py の HEADER と同じ列順。
    // ["ステータス","プラットフォーム","タイトル","カテゴリ","予算","締切","URL","検出日時",
    //  "提案文（下書き）","依頼者名","評価","実績件数","利益目安（円）","ワーカー提示額（円）",
    //  "ワーカー向けメッセージ","クライアント提案文（詳細版）","検出日","進捗ステージ"]
    rows.push([
      "未チェック", "CrowdWorks", title, keyword, budgetText, deadlineText,
      fullUrl, detectedAt, "", "", "", "", "", "", "", "",
      detectedAt.slice(0, 10), ""
    ].join("\t"));
  }

  if (rows.length === 0) {
    alert("案件が見つかりませんでした。CrowdWorksの検索結果一覧ページで実行してください。");
    return;
  }

  var tsv = rows.join("\n");

  function done(copied) {
    var msg = copied
      ? rows.length + "件コピーしました。\nスプレッドシートの最終行の次の行のA列を選んで貼り付けてください。"
      : "自動コピーに失敗しました。表示されたテキストを手動でコピーしてください。";
    if (copied) {
      alert(msg);
    } else {
      window.prompt(msg, tsv);
    }
  }

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(tsv).then(function () { done(true); }, function () { done(false); });
  } else {
    done(false);
  }
})();
