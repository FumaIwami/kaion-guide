/**
 * 攻略ガイドの投稿フォーム一式を作る（Google Apps Script・1 回だけ実行）
 *
 * 作るもの:
 *  1. 投稿フォーム（ページ / 内容 / 名前(任意)）
 *  2. 回答シート（非公開）… E 列「承認」にチェックボックス
 *  3. 公開用シート（リンクを知っている人は閲覧可）… 承認された行だけが自動でコピーされる
 *  4. 自動コピーのトリガー（チェックを付けた/外した時 + 1 時間ごとの保険）
 *
 * 実行後、「実行ログ」に config.json へ貼る 3 つの値が出ます。
 */

const PAGES = ['はじめにやること', 'お金の稼ぎ方', '探検隊', '鍛冶・装備', '会社・株', 'ジェムの使い道'];
const TITLE = '会社経営オンライン 攻略ガイド 情報投稿';

function setup() {
  const props = PropertiesService.getScriptProperties();
  if (props.getProperty('RESP_ID')) {
    throw new Error('すでに作成済みです（二重に作らないよう止めました）。');
  }

  // 1. フォーム
  const form = FormApp.create(TITLE);
  form.setDescription('攻略ガイドに載せたい情報を送ってください。運営が確認してから掲載します。\n個人情報（本名・連絡先など）は書かないでください。');
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);
  form.setConfirmationMessage('送信ありがとうございました。運営が確認してから掲載します。');
  const pageItem = form.addListItem().setTitle('ページ').setChoiceValues(PAGES).setRequired(true);
  form.addParagraphTextItem().setTitle('内容').setRequired(true);
  form.addTextItem().setTitle('名前（掲載してよい場合のみ）').setHelpText('空欄なら名前は載りません。').setRequired(false);

  // 2. 回答シート（非公開）
  const resp = SpreadsheetApp.create(TITLE + '（回答・非公開）');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, resp.getId());
  SpreadsheetApp.flush();
  Utilities.sleep(3000);
  const sh = findResponseSheet_(resp);
  sh.getRange('E1').setValue('承認');
  sh.getRange('E2:E2000').insertCheckboxes();
  sh.setFrozenRows(1);
  sh.setColumnWidth(3, 480);

  // 3. 公開用シート（承認分だけ）
  const pub = SpreadsheetApp.create(TITLE + '（公開用・承認済みのみ）');
  pub.getSheets()[0].getRange(1, 1, 1, 4).setValues([['タイムスタンプ', 'ページ', '内容', '名前']]);
  DriveApp.getFileById(pub.getId()).setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

  props.setProperties({ RESP_ID: resp.getId(), PUB_ID: pub.getId() });

  // 4. トリガー
  ScriptApp.newTrigger('sync').forSpreadsheet(resp).onEdit().create();
  ScriptApp.newTrigger('sync').forSpreadsheet(resp).onFormSubmit().create();
  ScriptApp.newTrigger('sync').timeBased().everyHours(1).create();

  // 事前入力 URL から entry ID を取る
  const pre = form.createResponse().withItemResponse(pageItem.createResponse(PAGES[0])).toPrefilledUrl();
  const entry = (pre.match(/(entry\.\d+)=/) || [])[1] || '';

  const out = {
    form_url: form.getPublishedUrl(),
    form_page_entry: entry,
    approved_csv_url: 'https://docs.google.com/spreadsheets/d/' + pub.getId() + '/export?format=csv'
  };
  Logger.log('▼ これを丸ごとコピーして Claude に渡してください');
  Logger.log(JSON.stringify(out, null, 2));
  Logger.log('回答シート（承認はここで E 列にチェック）: ' + resp.getUrl());
}

/** 承認（E 列 = TRUE）の行だけを公開用シートへ写す */
function sync() {
  const props = PropertiesService.getScriptProperties();
  const resp = SpreadsheetApp.openById(props.getProperty('RESP_ID'));
  const pub = SpreadsheetApp.openById(props.getProperty('PUB_ID')).getSheets()[0];
  const values = findResponseSheet_(resp).getDataRange().getValues();
  const rows = [['タイムスタンプ', 'ページ', '内容', '名前']];
  for (let i = 1; i < values.length; i++) {
    const r = values[i];
    if (r[4] === true && r[1] && r[2]) {
      const ts = r[0] instanceof Date ? Utilities.formatDate(r[0], 'Asia/Tokyo', 'yyyy/MM/dd') : String(r[0]);
      rows.push([ts, r[1], r[2], r[3] || '']);
    }
  }
  pub.clearContents();
  pub.getRange(1, 1, rows.length, 4).setValues(rows);
}

function findResponseSheet_(ss) {
  const s = ss.getSheets().find(x => x.getFormUrl()) || ss.getSheets()[0];
  return s;
}
