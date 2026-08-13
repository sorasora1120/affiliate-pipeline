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
 */
function doGet(e) {
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
