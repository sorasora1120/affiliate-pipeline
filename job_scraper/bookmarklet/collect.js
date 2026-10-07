/**
 * 案件収集ブックマークレット（CrowdWorks / ランサーズ、手動・ブラウザ実行用）
 *
 * CrowdWorksはGitHub Actionsのクラウド共有IPを403で拒否し、ランサーズは
 * ボット確認画面を出すため、どちらもクラウドから自動収集できない
 * （2026-10-07にランサーズも実際に試して確認）。自分のブラウザで検索結果を
 * 開いてこのブックマークを押せば、表示中の案件をスプレッドシートの行形式
 * （TSV）でクリップボードにコピーする。普通に閲覧しているページを読むだけ。
 *
 * 出力列は sheets_writer.py の HEADER と同じ並び。依頼者情報・提案文などは
 * 空欄で、貼り付けた後の定期マッチング（worker_match.yml）が埋める。
 */
(function () {
  "use strict";

  var SITES = {
    "crowdworks.jp": {
      platform: "CrowdWorks", detailUrl: "https://crowdworks.jp/public/jobs/",
      detailRe: /\/public\/jobs\/(\d+)/, linkSel: "a[href*='/public/jobs/']", keywordParam: "search[keywords]",
    },
    "www.lancers.jp": {
      platform: "ランサーズ", detailUrl: "https://www.lancers.jp/work/detail/",
      detailRe: /\/work\/detail\/(\d+)/, linkSel: "a[href*='/work/detail/']", keywordParam: "keyword",
    },
  };
  var site = SITES[location.hostname];
  if (!site) {
    alert("CrowdWorksかランサーズの検索結果ページで実行してください。");
    return;
  }

  // worker_match.ymlのWORKER_MATCH_CATEGORIESと同じ。検索語がこの中に無いと
  // マッチング対象にならないため、その場合は「Web制作」として登録する
  // （中身がサイト制作かどうかはマッチング側がタイトルで判定する）。
  var CATEGORIES = [
    "サイト制作", "ホームページ制作", "ECサイト構築", "ECサイト制作", "ネットショップ構築", "ネットショップ",
    "Shopify", "コーポレートサイト制作", "LP制作", "ランディングページ制作", "サイトリニューアル", "Web制作",
    "ホームページ作成", "LP作成", "ランディングページ作成", "ネットショップ制作", "WordPress制作", "WordPress構築",
    "STUDIO制作", "ペライチ制作", "Wix制作", "ホームページ改修", "ホームページリニューアル", "コーポレートサイト作成",
    "採用サイト制作", "オウンドメディア構築", "ネットショップ開設",
  ];

  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function fmtDate(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function fmtDateTime(d) { return fmtDate(d) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes()); }
  // ブラウザのタイムゾーンに関わらず検出日時はJSTで記録する（既存シートに合わせる）
  function jstNow() {
    var now = new Date();
    return new Date(now.getTime() + now.getTimezoneOffset() * 60000 + 9 * 3600000);
  }

  // deadline_utils.normalize_deadline() 相当（ランサーズの「残り N 日」にも対応）
  function normalizeDeadline(raw, today) {
    var m = raw.match(/(?:あと|残り)\s*(\d+)\s*日/);
    if (m) {
      var d = new Date(today.getTime());
      d.setDate(d.getDate() + parseInt(m[1], 10));
      return fmtDate(d);
    }
    m = raw.match(/(\d{4})[\/\-年](\d{1,2})[\/\-月](\d{1,2})/);
    if (m) {
      var dt = new Date(+m[1], +m[2] - 1, +m[3]);
      if (dt.getMonth() === +m[2] - 1) return fmtDate(dt);
    }
    return "不明";
  }

  var BUDGET_RANGE_RE = /[\d,]+\s*万?\s*円\s*[〜~]\s*[\d,]+\s*万?\s*円/;
  var BUDGET_SHORTHAND_RE = /[\d,]+\s*[万千]\s*円/;
  var BUDGET_RE = /[¥￥]\s*[\d,]+|[\d,]+\s*円/;
  var DEADLINE_RE = /(?:あと|残り)\s*\d+\s*日|\d{4}[\/\-年]\d{1,2}[\/\-月]\d{1,2}/;

  function jobId(a) {
    var m = (a.getAttribute("href") || "").match(site.detailRe);
    return m ? m[1] : null;
  }

  // 1件分の案件カード: リンクから親へ辿り、他の案件へのリンクを含まない
  // 一番外側の要素をカードとみなす（サイトのクラス名に依存しないため）。
  function cardOf(link, id) {
    var el = link, card = link;
    for (var i = 0; i < 8 && el.parentElement; i++) {
      el = el.parentElement;
      var links = el.querySelectorAll(site.linkSel);
      for (var j = 0; j < links.length; j++) {
        var other = jobId(links[j]);
        if (other && other !== id) return card;
      }
      card = el;
    }
    return card;
  }

  var keyword = new URL(location.href).searchParams.get(site.keywordParam) || "";
  var category = CATEGORIES.indexOf(keyword) !== -1 ? keyword : "Web制作";
  var today = jstNow();
  var detectedAt = fmtDateTime(today);

  var links = document.querySelectorAll(site.linkSel);
  var seen = {};
  var rows = [];
  for (var i = 0; i < links.length; i++) {
    var id = jobId(links[i]);
    if (!id || seen[id]) continue;
    seen[id] = true;

    var card = cardOf(links[i], id);
    // 画像だけのリンクもあるので、カード内の同じ案件へのリンクで一番長い文字列をタイトルにする
    var title = "";
    var sameLinks = card.querySelectorAll(site.linkSel);
    for (var k = 0; k < sameLinks.length; k++) {
      var t = (sameLinks[k].textContent || "").trim().replace(/\s+/g, " ");
      if (jobId(sameLinks[k]) === id && t.length > title.length) title = t;
    }
    if (title.length < 3) continue;

    // 「おすすめの仕事」等の枠はサイドバー・ヘッダー・フッターにあるので除外する。
    // 以前は「カードに検索語が含まれない案件」を除外していたが、ランサーズは
    // 説明文で検索がヒットするためカードに検索語が出ないことが多く、検索結果の
    // 大半まで捨てていた（2026-10-07、4件しか取れないとの報告）。無関係な案件は
    // マッチング側のタイトル判定で外れる。
    if (card.closest("aside, nav, header, footer")) continue;
    var text = card.textContent || "";

    var bm = text.match(BUDGET_RANGE_RE) || text.match(BUDGET_RE) || text.match(BUDGET_SHORTHAND_RE);
    var budget = bm ? bm[0].replace(/\s+/g, " ") : "不明";
    var dm = text.match(DEADLINE_RE);
    var deadline = dm ? normalizeDeadline(dm[0], today) : "不明";

    rows.push([
      "未チェック", site.platform, title, category, budget, deadline,
      site.detailUrl + id,
      detectedAt, "", "", "", "", "", "", "", "", detectedAt.slice(0, 10), "",
    ].join("\t"));
  }

  if (!rows.length) {
    alert("案件が見つかりませんでした。" + site.platform + "の検索結果一覧ページで実行してください。");
    return;
  }
  var tsv = rows.join("\n");
  var msg = rows.length + "件コピーしました。\nスプレッドシート「案件一覧」の最終行の次の行のA列を選んで貼り付けてください。";
  function fallback() {
    window.prompt("自動コピーできませんでした。下の文字を全部コピーして貼り付けてください。", tsv);
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(tsv).then(function () { alert(msg); }, fallback);
  } else {
    fallback();
  }
})();
