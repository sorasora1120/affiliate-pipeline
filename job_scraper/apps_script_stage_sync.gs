/**
 * Dispatchビューアの進行状況（②採用待ち等）を、みんなで同じスプレッドシートに
 * 書き込んで共有するためのWeb App。
 *
 * デプロイ手順:
 *   1. 案件一覧のスプレッドシートを開く
 *   2. 「拡張機能」→「Apps Script」
 *   3. 出てきたエディタの中身を全部消して、このファイルの内容を貼り付ける
 *   4. 右上の「デプロイ」→「新しいデプロイ」
 *   5. 種類の選択（歯車アイコン）で「ウェブアプリ」を選ぶ
 *   6. 「次のユーザーとして実行」＝自分、「アクセスできるユーザー」＝全員　に設定
 *   7. 「デプロイ」→ 初回は権限の承認を求められるので許可する
 *   8. 発行された「ウェブアプリのURL」（https://script.google.com/macros/s/.../exec）
 *      をコピーしてClaudeに渡す → docs/index.htmlのAPPS_SCRIPT_URLに設定してもらう
 *
 * シート名・列名を変更した場合はこのファイルも合わせて直すこと。
 *
 * 直したあと（同じURLのまま新しい版にする）: 「デプロイ」→「デプロイを管理」→ 鉛筆 → バージョン「新バージョン」→「デプロイ」
 */
function doGet(e) {
  // 2026-11-02〜 お店マップ（dispatch-viewer/shops.html）の印（📨送った・💬返事あり など）を「お店マップ」タブの K列（状態）・L列（更新日時）に書く
  if (e.parameter.shop) return saveShopMark(e.parameter);
  var url = e.parameter.url;
  var stage = e.parameter.stage;
  if (!url || !stage) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: "url/stage が必要です" }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("案件一覧");
    var data = sheet.getDataRange().getValues();
    var header = data[0];
    var urlCol = header.indexOf("URL");
    var stageCol = header.indexOf("進捗ステージ");
    if (urlCol === -1 || stageCol === -1) {
      return ContentService.createTextOutput(JSON.stringify({ ok: false, error: "列が見つかりません" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    for (var i = 1; i < data.length; i++) {
      if (data[i][urlCol] === url) {
        sheet.getRange(i + 1, stageCol + 1).setValue(stage);
        return ContentService.createTextOutput(JSON.stringify({ ok: true }))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: "該当URLが見つかりません" }))
      .setMimeType(ContentService.MimeType.JSON);
  } finally {
    lock.releaseLock();
  }
}

function saveShopMark(p) {
  var out = function (o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); };
  var name = p.shop, lat = parseFloat(p.lat), lon = parseFloat(p.lon), state = p.state || "";
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("お店マップ");
    if (!sheet) return out({ ok: false, error: "お店マップのタブがありません" });
    var data = sheet.getRange(1, 1, sheet.getLastRow(), 7).getValues();   // A 名前 … F 緯度 G 経度
    for (var i = 1; i < data.length; i++) {
      if (data[i][0] === name && Math.abs(parseFloat(data[i][5]) - lat) < 0.0002 && Math.abs(parseFloat(data[i][6]) - lon) < 0.0002) {
        var now = Utilities.formatDate(new Date(), "America/Toronto", "yyyy-MM-dd HH:mm");
        sheet.getRange(i + 1, 11, 1, 2).setValues([[state, state ? now : ""]]);   // K 状態・L 更新日時
        return out({ ok: true, row: i + 1 });
      }
    }
    return out({ ok: false, error: "お店が見つかりません" });
  } finally {
    lock.releaseLock();
  }
}
