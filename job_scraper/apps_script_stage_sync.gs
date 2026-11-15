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
  // 2026-11-15〜 AI COMPANY OS のダッシュボード（dispatch-viewer/company.html）からの書き込み。AI_ で始まるタブに書く
  if (e.parameter.ai) return aiCompany(e.parameter);
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


// ===== AI COMPANY OS（dispatch-viewer/company.html、設計は dispatch-viewer/docs/ai-company-os.md）=====
// 書き込みには暗証番号が必要。Apps Script の「プロジェクトの設定 → スクリプト プロパティ」に AI_PIN を入れておく（リポジトリには書かない）。
// 返事は JSONP（callback があれば）なので、ページ側で成功・失敗がわかる。
var AI_STATUSES = ["待ち", "実行中", "確認中", "完了", "失敗"];
function aiCompany(p) {
  var out = function (o) {
    var t = JSON.stringify(o);
    if (p.callback && /^[A-Za-z_$][\w$]*$/.test(p.callback)) return ContentService.createTextOutput(p.callback + "(" + t + ")").setMimeType(ContentService.MimeType.JAVASCRIPT);
    return ContentService.createTextOutput(t).setMimeType(ContentService.MimeType.JSON);
  };
  var pin = PropertiesService.getScriptProperties().getProperty("AI_PIN");
  if (!pin) return out({ ok: false, error: "AI_PIN がまだ設定されていません（スクリプト プロパティ）" });
  if (String(p.pin || "") !== pin) return out({ ok: false, error: "暗証番号がちがいます" });
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var now = Utilities.formatDate(new Date(), "America/Toronto", "yyyy-MM-dd HH:mm");
  var log = function (who, what, result) { ss.getSheetByName("AI_Activity").appendRow([now, who, what, result]); };
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var a = p.ai;
    if (a === "ping") return out({ ok: true });
    if (a === "addTask") {
      var title = String(p.title || "").trim();
      if (!title) return out({ ok: false, error: "タイトルが空です" });
      var sh = ss.getSheetByName("AI_Tasks"), last = sh.getLastRow(), max = 0;
      if (last > 1) sh.getRange(2, 1, last - 1, 1).getValues().forEach(function (r) { var n = parseInt(String(r[0]).replace(/^T/, ""), 10); if (n > max) max = n; });
      var id = "T" + (max + 1);
      sh.appendRow([id, title, String(p.dept || "CEO"), "待ち", "", "", String(p.note || ""), now, now, "", "Sora"]);
      log("Sora", "タスクを追加：" + id + " " + title, "ok");
      return out({ ok: true, id: id });
    }
    if (a === "setStatus") {
      if (AI_STATUSES.indexOf(p.status) < 0) return out({ ok: false, error: "状態がおかしい" });
      var row = aiFind(ss.getSheetByName("AI_Tasks"), p.id);
      if (!row) return out({ ok: false, error: "タスクが見つかりません" });
      ss.getSheetByName("AI_Tasks").getRange(row, 4).setValue(p.status);
      ss.getSheetByName("AI_Tasks").getRange(row, 9).setValue(now);
      log("Sora", "タスク " + p.id + " を「" + p.status + "」に", "ok");
      return out({ ok: true });
    }
    if (a === "decide") {
      if (p.decision !== "承認" && p.decision !== "却下") return out({ ok: false, error: "承認か却下だけ" });
      var ap = ss.getSheetByName("AI_Approvals"), r = aiFind(ap, p.id);
      if (!r) return out({ ok: false, error: "承認の行が見つかりません" });
      var v = ap.getRange(r, 1, 1, 10).getValues()[0];   // A id … E ハッシュ F 期限 G 状態
      if (v[6] !== "待ち") return out({ ok: false, error: "もう「" + v[6] + "」になっています（二重の操作はできません）" });
      if (String(v[4]) !== String(p.hash || "")) { log("Sora", "承認 " + p.id + " を止めた", "内容が変わっていた"); return out({ ok: false, error: "内容が書きかえられています。開き直して確認してください" }); }
      var exp = v[5] ? new Date(v[5]) : null;
      if (exp && !isNaN(exp) && exp < new Date()) { ap.getRange(r, 7).setValue("期限切れ"); log("Sora", "承認 " + p.id, "期限切れ"); return out({ ok: false, error: "期限が切れています" }); }
      ap.getRange(r, 7, 1, 2).setValues([[p.decision, now]]);
      log("Sora", "承認 " + p.id + " を「" + p.decision + "」", "ok");
      return out({ ok: true });
    }
    if (a === "setSchedule") {
      var sc = ss.getSheetByName("AI_Schedules"), rr = aiFind(sc, p.name);
      if (!rr) return out({ ok: false, error: "自動化が見つかりません" });
      var on = p.on === "1" ? "オン" : "オフ";
      sc.getRange(rr, 4).setValue(on);
      log("Sora", "自動化「" + p.name + "」を" + on, "ok（実際の定期実行は Claude が合わせる）");
      return out({ ok: true });
    }
    return out({ ok: false, error: "知らない操作です" });
  } catch (err) {
    return out({ ok: false, error: String(err) });
  } finally {
    lock.releaseLock();
  }
}
function aiFind(sheet, key) {
  var last = sheet.getLastRow();
  if (last < 2) return 0;
  var col = sheet.getRange(2, 1, last - 1, 1).getValues();
  for (var i = 0; i < col.length; i++) if (String(col[i][0]) === String(key)) return i + 2;
  return 0;
}
