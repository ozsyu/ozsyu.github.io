#!/usr/bin/env python3
"""
369 サイト生成スクリプト（比較記事つき）

products.json から、商品一覧ページと容量帯ごとの比較記事を生成する。
記事の中身は楽天公式APIで取得した仕様と価格だけを根拠にしている。
使用感の記述は notes.json、レビューの総括は reviews.json から読む。

使い方:
    python build_site.py
"""

import html
import json
import os
import re
import shutil
import sys
from datetime import date

STORE = "products.json"
NOTES = "notes.json"
REVIEWS = "reviews.json"
OUT = "site"
BASE_URL = "https://ozsyu.github.io"   # 公開URL。独自ドメインにしたらここを直す
# Googleサーチコンソールの所有権確認用。消すと未確認に戻るので残しておくこと
GOOGLE_VERIFY = "Kb2NCJSVxiX0KRuGZumT1xqZFLP-Zv7CF6bCa7jksmE"

SITE_NAME = "369"
SITE_TAGLINE = "プロ目線で選ぶ、長く使えるアイテムを実際に使う道具を値段で並べて見比べてみる。"
SITE_DESC = ("石材と土木の現場で道具を使う目線から、ポータブル電源と宅配ボックスを"
             "容量・重量・価格で比較しています。")
TODAY = date.today().strftime("%Y年%m月%d日")

SECTIONS = [
    {
        "label": "ポータブル電源",
        "slug": "portable-power",
        "lead": "現場で発電機を回すほどではない、でもコンセントが要る。そういう場面で使う"
                "ポータブル電源です。1kWhを超えると値段が一気に上がるので、"
                "何を動かしたいかを先に決めると選びやすくなります。",
    },
    {
        "label": "宅配ボックス",
        "slug": "delivery-box",
        "lead": "置き型は安く済みますが、風で動くものと動かないものがあります。"
                "アンカーで固定できるか、土間に据えるかで選ぶものが変わるので、"
                "重量と容量を見比べられるようにしました。",
    },
]

# ------------------------------------------------------------------ 比較記事の区分
ARTICLES = [
    {
        "id": "power-under500",
        "label": "ポータブル電源",
        "title": "500Wh以下のポータブル電源を比較",
        "key": "wh", "min": 0, "max": 500,
        "intro": "スマホやノートPC、照明、小型の扇風機まで。車中泊や停電時の最低限を"
                 "まかなう帯です。この容量なら本体が5〜7kg程度に収まるので、"
                 "片手で持って現場に放り込めます。電子レンジや電動工具は動きません。",
        "pick": "現場に持ち歩くなら、この帯は重量で選んで構いません。容量差より、"
                "毎日持つときの1kgの差のほうが効きます。",
    },
    {
        "id": "power-500to1000",
        "label": "ポータブル電源",
        "title": "500〜1000Whのポータブル電源を比較",
        "key": "wh", "min": 500, "max": 1000,
        "intro": "小型冷蔵庫を半日、扇風機なら丸一日。一泊の車中泊や、"
                 "停電した夜をしのぐのに過不足のない帯です。重量は6〜12kgで、"
                 "持ち運べる上限がこのあたりになります。",
        "pick": "この帯から電池の種類を見てください。リン酸鉄リチウムは"
                "充放電の回数が三元系より多く取れるので、長く使うつもりなら差が出ます。",
    },
    {
        "id": "power-1000to2000",
        "label": "ポータブル電源",
        "title": "1000〜2000Whのポータブル電源を比較",
        "key": "wh", "min": 1000, "max": 2000,
        "intro": "電子レンジやドライヤー、小型の電動工具まで届く帯です。"
                "ここから重量が10kgを超えて、気軽に持ち歩くものではなくなります。"
                "車に積んで現場に置く、あるいは家に備えるという使い方が中心です。",
        "pick": "定格出力を必ず確認してください。容量が足りていても、定格が低いと"
                "消費電力の大きい工具は起動しません。1500W以上あると選択肢が広がります。",
    },
    {
        "id": "power-over2000",
        "label": "ポータブル電源",
        "title": "2000Wh以上の大容量ポータブル電源を比較",
        "key": "wh", "min": 2000, "max": 99999,
        "intro": "停電時に家電をひととおり動かす、あるいは電源のない現場で一日作業する"
                 "ための容量です。20kgを超えるものが多く、据え置いて使う前提になります。"
                "価格も20万円前後からで、発電機と比較検討する領域です。",
        "pick": "この価格帯なら保証期間を見てください。3年と5年では、"
                "実質的な年あたりの負担がかなり変わります。",
    },
    {
        "id": "box-under60",
        "label": "宅配ボックス",
        "title": "容量60L以下の宅配ボックスを比較",
        "key": "liters", "min": 0, "max": 60,
        "intro": "日用品や書籍など、小ぶりな荷物を受けるための大きさです。"
                "玄関まわりが狭い家に向きますが、まとめ買いをする家庭には手狭です。",
        "pick": "小型のものほど軽いので、風で動きます。設置場所が吹きさらしなら、"
                "アンカー固定に対応しているかを先に確認してください。",
    },
    {
        "id": "box-60to100",
        "label": "宅配ボックス",
        "title": "容量60〜100Lの宅配ボックスを比較",
        "key": "liters", "min": 60, "max": 100,
        "intro": "いちばん選ばれている帯です。段ボール1〜2個、日用品のまとめ買いが入ります。"
                 "ポスト一体型の製品が多く、玄関まわりを1台で片づけられます。",
        "pick": "重量が15kgを超えると、荷物が入った状態ではまず動きません。"
                "固定なしで済ませたいなら、本体重量を見てください。",
    },
    {
        "id": "box-over100",
        "label": "宅配ボックス",
        "title": "容量100L以上の大型宅配ボックスを比較",
        "key": "liters", "min": 100, "max": 9999,
        "intro": "段ボールを複数個まとめて受けられる大きさです。通販の利用が多い家庭や、"
                 "二世帯で使う場合に向きます。そのぶん場所を取るので、"
                 "設置場所の幅と奥行きを先に測ってください。",
        "pick": "大型は基礎や土間に据えると安定します。置くだけで済ませる場合でも、"
                "アンカー対応の製品を選んでおくと後から固定できます。",
    },
]

PAGES = [
    ("about.html", "このサイトについて", """
<p>369は、石材と土木の仕事をしている運営者が、現場で実際に使う道具を
値段と仕様で並べて見比べるために作ったサイトです。</p>
<h3>掲載しているデータについて</h3>
<p>商品情報は楽天ウェブサービスが公開している公式APIから取得しています。
容量や重量といった仕様は、各ショップの商品説明文から自動的に抜き出したものです。
転記の誤りがあり得ますので、購入前には必ず商品ページでご確認ください。</p>
<h3>「おすすめ」の根拠について</h3>
<p>比較記事に付けている「最軽量」「最安」「レビュー最多」といった印は、
すべて取得したデータから機械的に判定したものです。
運営者の主観で順位を付けてはいません。</p>
<h3>使った商品と、使っていない商品</h3>
<p>運営者が実際に使った商品には「使ってみて」という欄を付けています。
ここだけは実体験です。付いていない商品は使っていません。
使ってもいない道具の使用感を書くつもりはないので、そこは正直に分けています。</p>
<p>「レビューまとめ」の欄は、楽天に投稿されたレビューを運営者が読んで
要約したものです。こちらも書いていない商品には表示されません。</p>
"""),
    ("privacy.html", "プライバシーポリシー", """
<h3>アクセス情報について</h3>
<p>当サイトは静的なページのみで構成されており、運営者が閲覧者の個人情報を
直接取得することはありません。</p>
<h3>外部サービスについて</h3>
<p>当サイトは楽天アフィリエイトを利用しています。商品リンクをクリックした際、
楽天グループが提供するプログラムによってCookieが利用され、
どのサイト経由で訪問したかが記録される場合があります。
これは購入の成果を判定するためのもので、氏名や住所などの個人情報を
運営者が知ることはありません。</p>
<p>Cookieの利用はブラウザの設定で拒否できます。方法はお使いのブラウザの
説明をご確認ください。</p>
"""),
    ("disclaimer.html", "免責事項", """
<h3>アフィリエイトについて</h3>
<p>当サイトは楽天アフィリエイトによる広告を掲載しています。
リンクから商品を購入された場合、運営者に紹介料が支払われます。</p>
<h3>掲載情報について</h3>
<p>価格、在庫、レビュー件数、商品仕様は、データを取得した時点のものです。
実際の販売条件と異なる場合がありますので、最新の情報は各商品ページで
必ずご確認ください。</p>
<h3>損害について</h3>
<p>当サイトの情報を利用したことで生じたいかなる損害についても、
運営者は責任を負いかねます。商品の購入および使用は、
ご自身の判断と責任のもとで行ってください。</p>
"""),
]

CSS = """
:root {
  --bg:#fff; --tint:#f4f4f1; --ink:#1f1d1a; --soft:#6f6b64;
  --rule:#dedcd6; --mark:#e8a800; --link:#2c5c85;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic Medium",Meiryo,system-ui,sans-serif;
 line-height:1.8;font-size:16px;-webkit-font-smoothing:antialiased}
a{color:var(--link)}
.wrap{max-width:1100px;margin:0 auto;padding:0 22px}

.masthead{border-bottom:1px solid var(--rule);background:#f7f8f9}
.banner{display:block;max-width:1500px;margin:0 auto}
.banner img{display:block;width:100%;height:auto}

nav.tabs{border-bottom:1px solid var(--rule);background:var(--tint)}
nav.tabs .wrap{display:flex;flex-wrap:wrap;padding:0 22px}
nav.tabs a{padding:12px 16px;text-decoration:none;color:var(--ink);font-size:14.5px;
 border-bottom:3px solid transparent;margin-bottom:-1px}
nav.tabs a:hover{background:var(--bg)}
nav.tabs a.on{border-bottom-color:var(--mark);font-weight:700}

main .wrap{padding-top:32px;padding-bottom:56px}
h2.head{font-size:22px;margin:0 0 8px;line-height:1.5}
.lead{max-width:64ch;margin:0 0 28px}
.lead p{margin:0}
.stamp{color:var(--soft);font-size:12.5px;margin:0 0 22px}

.sect-title{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
 border-bottom:2px solid var(--ink);padding-bottom:7px;margin:44px 0 20px}
.sect-title h2{font-size:18px;margin:0}
main .wrap>.sect-title:first-child{margin-top:0}
.sect-title a{font-size:13.5px;text-decoration:none}

.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:13px 0;
 border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);font-size:14px}
.controls .group{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.controls .cap{color:var(--soft);font-size:12.5px}
.controls button{font:inherit;font-size:13px;padding:5px 12px;border:1px solid var(--rule);
 background:var(--bg);color:var(--ink);cursor:pointer;border-radius:999px}
.controls button:hover{border-color:var(--ink)}
.controls button[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:#fff;font-weight:700}
.controls button:focus-visible{outline:2px solid var(--link);outline-offset:2px}
.count{margin:14px 0 10px;color:var(--soft);font-size:13px}

.grid{list-style:none;margin:0;padding:0}
.card{display:grid;grid-template-columns:210px 1fr 236px;gap:22px;padding:24px 0;
 border-bottom:1px solid var(--rule);align-items:start}
.body{min-width:0}
.thumb{position:relative;display:block;background:var(--tint);border:1px solid var(--rule);
 aspect-ratio:4/3;overflow:hidden}
.thumb img{width:100%;height:100%;object-fit:contain}
.chip{position:absolute;left:0;top:0;background:var(--ink);color:#fff;font-size:11.5px;
 padding:4px 10px;letter-spacing:.04em}
.card h3{font-size:16px;line-height:1.6;margin:0 0 7px;font-weight:600}
.card h3 a{color:var(--ink);text-decoration:none}
.card h3 a:hover{text-decoration:underline}
.blurb{margin:0 0 9px;font-size:13.5px;line-height:1.75;color:var(--soft)}
.note{margin:0 0 9px;padding:10px 12px;background:var(--tint);border-left:4px solid var(--mark);
 font-size:13.5px;line-height:1.75}
.note b{display:block;font-size:11px;color:var(--soft);margin-bottom:3px;font-weight:600}
.price{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin:0 0 8px}
.price small{font-size:12px;font-weight:400}

.side{border-left:1px solid var(--rule);padding-left:18px}
.score{display:flex;align-items:baseline;gap:8px}
.score .num{font-size:27px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
.score .s{color:var(--mark);letter-spacing:1px;font-size:14px}
.side .cnt{font-size:11.5px;color:var(--soft);margin:4px 0 0;font-variant-numeric:tabular-nums}
.side .sum{margin:11px 0 0;font-size:12.5px;line-height:1.8;padding-top:11px;
 border-top:1px dotted var(--rule)}
.side .sum b{display:block;font-size:10.5px;color:var(--soft);font-weight:600;margin-bottom:3px}
.side .none{margin:11px 0 0;font-size:11.5px;color:var(--soft);line-height:1.7}
.go{display:block;text-align:center;margin-top:13px;padding:9px;background:var(--ink);
 color:#fff;text-decoration:none;font-size:13.5px}
.go:hover{background:var(--link)}

/* 比較表 */
.tablewrap{overflow-x:auto;margin:6px 0 30px;border:1px solid var(--rule)}
table.cmp{border-collapse:collapse;width:100%;font-size:13.5px;min-width:660px;background:var(--bg)}
table.cmp th,table.cmp td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--rule);
 vertical-align:top}
table.cmp thead th{background:var(--tint);font-size:12.5px;font-weight:600;white-space:nowrap;
 border-bottom:2px solid var(--ink)}
table.cmp td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.cmp tbody tr:last-child td{border-bottom:0}
table.cmp a{text-decoration:none;font-weight:600}
table.cmp a:hover{text-decoration:underline}
.tag{display:inline-block;background:var(--mark);color:var(--ink);font-size:10.5px;
 font-weight:700;padding:2px 7px;margin-right:5px;white-space:nowrap}

.awards{list-style:none;margin:0 0 30px;padding:0;display:grid;
 grid-template-columns:repeat(3,1fr);gap:16px}
.awards li{border:1px solid var(--rule);border-top:4px solid var(--mark);padding:16px 18px}
.awards h4{margin:0 0 4px;font-size:12px;color:var(--soft);font-weight:600}
.awards .nm{font-size:14px;font-weight:600;line-height:1.55;margin:0 0 6px}
.awards .nm a{color:var(--ink);text-decoration:none}
.awards .nm a:hover{text-decoration:underline}
.awards .why{margin:0;font-size:12.5px;color:var(--soft);line-height:1.7}

.arts{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:16px}
.arts li{border:1px solid var(--rule);padding:18px 20px}
.arts h3{margin:0 0 5px;font-size:15.5px;line-height:1.55}
.arts h3 a{color:var(--ink);text-decoration:none}
.arts h3 a:hover{text-decoration:underline}
.arts p{margin:0;font-size:12.5px;color:var(--soft);font-variant-numeric:tabular-nums}

/* トップ上段の写真 */
.hero{list-style:none;margin:0 0 34px;padding:0;display:grid;
 grid-template-columns:repeat(3,1fr);gap:22px}
.hero li{border:1px solid var(--rule);display:flex;flex-direction:column;background:var(--bg)}
.hero .ph{position:relative;display:block;aspect-ratio:1/1;background:var(--tint);overflow:hidden}
.hero .ph img{width:100%;height:100%;object-fit:contain}
.hero .rank{position:absolute;left:0;top:0;background:var(--ink);color:#fff;
 font-size:15px;font-weight:700;width:34px;height:34px;display:flex;
 align-items:center;justify-content:center;font-variant-numeric:tabular-nums}
.hero .cat{position:absolute;right:0;top:0;background:var(--mark);color:var(--ink);
 font-size:11px;font-weight:700;padding:4px 10px}
.hero .t{padding:14px 16px 16px;display:flex;flex-direction:column;flex:1}
.hero h3{margin:0 0 8px;font-size:14.5px;line-height:1.6;font-weight:600}
.hero h3 a{color:var(--ink);text-decoration:none}
.hero h3 a:hover{text-decoration:underline}
.hero .sp{margin:0 0 10px;font-size:12.5px;color:var(--soft);line-height:1.7}
.hero .ft{margin-top:auto;display:flex;align-items:baseline;justify-content:space-between;
 gap:10px;padding-top:10px;border-top:1px solid var(--rule)}
.hero .pr{font-size:19px;font-weight:700;font-variant-numeric:tabular-nums}
.hero .pr small{font-size:11px;font-weight:400}
.hero .rv{font-size:11px;color:var(--soft);text-align:right;line-height:1.5;
 font-variant-numeric:tabular-nums}
.hero .rv .s{color:var(--mark);font-size:12px;letter-spacing:1px}

.tiles{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:0;padding:0;list-style:none}
.tile{border:1px solid var(--rule);border-top:5px solid var(--mark);padding:22px}
.tile h3{margin:0 0 8px;font-size:18px}
.tile p{margin:0 0 12px;font-size:14px}
.tile .nums{color:var(--soft);font-size:13px;font-variant-numeric:tabular-nums}
.tile a.enter{display:inline-block;margin-top:12px;font-weight:600;text-decoration:none}

.art{max-width:74ch}
.art h3{font-size:17px;margin:34px 0 8px;padding-bottom:5px;border-bottom:2px solid var(--ink)}
.art p{margin:0 0 16px}
.doc{max-width:68ch}
.doc h3{font-size:16px;margin:28px 0 6px}
.doc p{margin:0 0 14px}

footer{border-top:1px solid var(--rule);background:var(--tint);margin-top:20px}
footer .wrap{padding:26px 22px 40px;font-size:12.5px;color:var(--soft)}
footer .flinks{margin:0 0 14px;display:flex;flex-wrap:wrap;gap:16px}
footer .flinks a{text-decoration:none}
footer p{margin:0 0 7px;max-width:70ch}

@media (max-width:880px){
  .card{grid-template-columns:150px 1fr;gap:16px}
  .side{grid-column:1/-1;border-left:0;padding-left:0;border-top:1px solid var(--rule);padding-top:12px}
  .side .sum{border-top:0;padding-top:0}
  .awards{grid-template-columns:1fr}
  .arts,.tiles{grid-template-columns:1fr}
  .hero{grid-template-columns:1fr 1fr;gap:16px}
}
@media (max-width:560px){
  .card{grid-template-columns:100px 1fr}
  .card h3{font-size:14.5px}
  .hero{grid-template-columns:1fr}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

APP_JS = """
(function () {
  var data = window.ITEMS || [];
  var list = document.getElementById('list');
  var count = document.getElementById('count');
  if (!list) return;
  var state = { sort: 'reviews', band: 'all' };
  var bands = {
    all: function () { return true; },
    low: function (p) { return p.price < LOW; },
    mid: function (p) { return p.price >= LOW && p.price < HIGH; },
    high: function (p) { return p.price >= HIGH; }
  };
  var sorters = {
    reviews: function (a, b) { return b.review_count - a.review_count; },
    rated: function (a, b) {
      if (b.review_average !== a.review_average) return b.review_average - a.review_average;
      return b.review_count - a.review_count;
    },
    cheap: function (a, b) { return a.price - b.price; },
    dear: function (a, b) { return b.price - a.price; }
  };
  function render() {
    var rows = data.filter(function (p) { return bands[state.band](p); });
    rows.sort(sorters[state.sort]);
    rows.sort(function (a, b) {
      return ((b.note || b.summary) ? 1 : 0) - ((a.note || a.summary) ? 1 : 0);
    });
    count.textContent = rows.length + '件を表示中（全' + data.length + '件）';
    if (!rows.length) {
      list.innerHTML = '<li>この価格帯の商品はありません。別の帯を選んでください。</li>';
      return;
    }
    list.innerHTML = rows.map(window.cardHTML).join('');
  }
  document.querySelectorAll('[data-sort],[data-band]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var kind = btn.dataset.sort ? 'sort' : 'band';
      state[kind] = btn.dataset.sort || btn.dataset.band;
      document.querySelectorAll('[data-' + kind + ']').forEach(function (b) {
        b.setAttribute('aria-pressed', String(b === btn));
      });
      render();
    });
  });
  render();
})();
"""

CARD_JS = """
window.cardHTML = function (p) {
  var full = Math.round(p.review_average);
  var stars = '';
  for (var i = 0; i < 5; i++) stars += (i < full ? '\\u2605' : '\\u2606');
  var yen = p.price.toLocaleString('ja-JP');
  var rev = p.review_count.toLocaleString('ja-JP');
  var link = 'href="' + p.url + '" target="_blank" rel="nofollow sponsored noopener"';
  var side = '<div class="side">'
    + '<div class="score"><span class="num">' + p.review_average.toFixed(2) + '</span>'
    +   '<span class="s">' + stars + '</span></div>'
    + '<p class="cnt">楽天レビュー ' + rev + '件の平均</p>'
    + (p.summary
        ? '<p class="sum"><b>レビューまとめ</b>' + p.summary + '</p>'
        : '<p class="none">この商品はまだレビューを読み込んでいません。数値は楽天の集計値です。</p>')
    + '<a class="go" ' + link + '>楽天で見る</a>'
    + '</div>';
  return '<li class="card">'
    + '<a class="thumb" ' + link + '>'
    +   (p.img ? '<img src="' + p.img + '" alt="" loading="lazy">' : '')
    +   '<span class="chip">' + p.label + '</span>'
    + '</a>'
    + '<div class="body">'
    +   '<h3><a ' + link + '>' + p.name + '</a></h3>'
    +   '<p class="price">' + yen + '<small>円</small></p>'
    +   (p.note ? '<p class="note"><b>使ってみて</b>' + p.note + '</p>' : '')
    +   (p.blurb ? '<p class="blurb">' + p.blurb + '</p>' : '')
    + '</div>'
    + side
    + '</li>';
};
"""


# ------------------------------------------------------------------ 仕様の抽出
def extract(product):
    """商品説明から仕様を数値で取り出す。読み取れないものは None のままにする。"""
    text = (product.get("caption") or "") + " " + (product.get("catch") or "")
    name = product.get("name") or ""
    spec = {"wh": None, "w": None, "kg": None, "battery": None, "solar": False,
            "liters": None, "material": None, "post": False, "anchor": False}

    m = re.search(r"(\d{3,5})\s*Wh", text)
    if m:
        v = int(m.group(1))
        if 100 <= v <= 20000:
            spec["wh"] = v
    for m in re.finditer(r"(?:AC出力|定格出力|出力)[^\d]{0,12}?(\d{3,4})\s*W(?![h仕])", text):
        w = int(m.group(1))
        # ソーラー入力など別の数値を拾うことがあるので、容量と釣り合わない値は捨てる
        if spec["wh"] and w * 4 < spec["wh"]:
            continue
        spec["w"] = w
        break
    for m in re.finditer(r"(?:重[さ量]|本体重量)[^\d]{0,8}?(\d{1,3}(?:\.\d)?)\s*kg", text):
        kg = float(m.group(1))
        # 明らかにおかしい値は採らない。付属品の重さを拾うことがあるため。
        if spec["wh"] and kg < spec["wh"] / 150:
            continue          # 1kWh級で数kgはあり得ない
        if not 0.5 <= kg <= 200:
            continue
        spec["kg"] = kg
        break
    if "リン酸鉄" in text:
        spec["battery"] = "リン酸鉄"
    elif "三元系" in text:
        spec["battery"] = "三元系"
    if re.search(r"ソーラーパネル.{0,6}(セット|付)|Solar Generator", name):
        spec["solar"] = True

    m = re.search(r"(?:容量|有効内寸容量|収納容量)[^\d]{0,10}?(\d{2,3})\s*(?:L|リットル|ℓ)", text)
    if not m:
        m = re.search(r"(\d{2,3})\s*L(?:の大容量|サイズ|タイプ)", text)
    if m:
        v = int(m.group(1))
        if 10 <= v <= 500:
            spec["liters"] = v
    for material in ("ステンレス", "スチール", "アルミ", "木製", "樹脂"):
        if material in text:
            spec["material"] = material
            break
    if "一体型" in name or "ポスト付" in name:
        spec["post"] = True
    if "アンカー" in text:
        spec["anchor"] = True
    return spec


def blurb_from(spec, label):
    facts, hint = [], ""
    if label == "ポータブル電源":
        if spec["wh"]:
            v = spec["wh"]
            facts.append(f"{v:,}Wh")
            if v < 400:
                hint = "スマホやノートPCの充電が主な用途になる容量です。"
            elif v < 800:
                hint = "扇風機や小型の冷蔵庫を数時間まかなえる容量です。"
            elif v < 1600:
                hint = "電動工具や電子レンジを短時間なら動かせる容量です。"
            else:
                hint = "現場の工具や停電時の家電をひととおり動かせる容量です。"
        if spec["w"]:
            facts.append(f"定格{spec['w']:,}W")
        if spec["kg"]:
            facts.append(f"{spec['kg']:g}kg")
        if spec["battery"]:
            facts.append(f"{spec['battery']}リチウム")
        if spec["solar"]:
            facts.append("ソーラーパネル付き")
    else:
        if spec["liters"]:
            v = spec["liters"]
            facts.append(f"容量{v}L")
            if v < 50:
                hint = "小ぶりな荷物向けです。まとめ買いには手狭かもしれません。"
            elif v < 100:
                hint = "日用品のまとめ買いが入る、標準的な大きさです。"
            else:
                hint = "段ボール複数個を受けられる大型です。設置場所の幅を先に測ってください。"
        if spec["material"]:
            facts.append(f"{spec['material']}製")
        if spec["kg"]:
            facts.append(f"{spec['kg']:g}kg")
        if spec["post"]:
            facts.append("ポスト一体型")
        if spec["anchor"]:
            facts.append("アンカー固定に対応")
    if len(facts) < 2 and not hint:
        return ""
    return "／".join(facts) + "。" + ("　" + hint if hint else "")


# ------------------------------------------------------------------ 部品
def esc(text):
    return html.escape(str(text), quote=True)


def shorten(name, limit=58):
    cleaned = name
    while cleaned.startswith(("【", "＼", "＜")):
        end = max(cleaned.find("】"), cleaned.find("／"), cleaned.find("＞"))
        if end == -1 or end > 60:
            break
        cleaned = cleaned[end + 1:].lstrip()
    cleaned = (cleaned or name).split("|")[0].strip()
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def load_map(path, what):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if ":" in k and v}
    except Exception:
        print(f"{path} が読めません。{what}なしで生成します。", file=sys.stderr)
        return {}


def payload_of(items):
    rows = [{
        "label": esc(p["label"]),
        "name": esc(shorten(p["name"])),
        "price": p["price"],
        "review_count": p["review_count"],
        "review_average": round(float(p["review_average"]), 2),
        "url": p["url"],
        "img": p["images"][0] if p["images"] else "",
        "blurb": esc(p["_blurb"]),
        "note": esc(p["_note"]),
        "summary": esc(p["_summary"]),
    } for p in items]
    rows.sort(key=lambda x: (0 if (x["note"] or x["summary"]) else 1, -x["review_count"]))
    return rows


def link_attrs(product):
    return (f'href="{esc(product["url"])}" target="_blank" '
            f'rel="nofollow sponsored noopener"')


def page(title, body, active, depth=0, extra_js=""):
    root = "../" if depth else ""
    # トップは大きく、下層ページは帯を細くして本文を先に見せる
    banner, bh, bw = (("banner.jpg", 418, 2172) if active == "index"
                      else ("banner-slim.jpg", 372, 2400))
    tabs = [("トップ", root + "index.html", active == "index")]
    for s in SECTIONS:
        tabs.append((s["label"], f"{root}{s['slug']}/index.html", active == s["slug"]))
    tabs.append(("比較記事", root + "articles.html", active in ("articles", "article")))
    tabs.append(("このサイトについて", root + "about.html", active == "about.html"))

    nav = "".join(
        f'<a href="{esc(url)}"{" class=\'on\'" if on else ""}>{esc(label)}</a>'
        for label, url, on in tabs
    )
    flinks = "".join(f'<a href="{root}{fn}">{esc(t)}</a>' for fn, t, _ in PAGES)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(SITE_DESC)}">
<meta name="google-site-verification" content="{GOOGLE_VERIFY}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(SITE_DESC)}">
<meta property="og:type" content="website">
<link rel="stylesheet" href="{root}style.css">
</head>
<body>
<header class="masthead">
  <a class="banner" href="{root}index.html">
    <img src="{root}{banner}" alt="369 SELECT　暮らしのそばに、いいモノを。"
         width="{bw}" height="{bh}">
  </a>
</header>
<nav class="tabs"><div class="wrap">{nav}</div></nav>
<main><div class="wrap">
{body}
</div></main>
<footer><div class="wrap">
  <p class="flinks"><a href="{root}index.html">トップ</a>{flinks}</p>
  <p>当サイトは楽天アフィリエイトを利用しています。掲載リンクから商品を購入すると、運営者に紹介料が入ります。</p>
  <p>商品情報は楽天ウェブサービスの公式APIから取得しています。星印は運営者の評価ではなく、楽天レビューの平均値です。</p>
  <p>Supported by <a href="https://webservice.rakuten.co.jp/" target="_blank" rel="noopener">楽天ウェブサービス</a>　&copy; {esc(SITE_NAME)}</p>
</div></footer>
<script src="{root}card.js"></script>
{extra_js}
</body>
</html>
"""


# ------------------------------------------------------------------ 比較記事
def pick_awards(group, label):
    """データから機械的に「推せる理由」を決める。主観は入れない。"""
    awards = []
    most = max(group, key=lambda p: p["review_count"])
    awards.append(("いちばん売れている", most,
                   f"レビュー{most['review_count']:,}件。"
                   f"この帯でもっとも多くの人が買っています。"))
    cheap = min(group, key=lambda p: p["price"])
    if cheap is not most:
        awards.append(("いちばん安い", cheap,
                       f"{cheap['price']:,}円。この帯の最安です。"))
    weighed = [p for p in group if p["_spec"]["kg"]]
    if label == "ポータブル電源" and weighed:
        light = min(weighed, key=lambda p: p["_spec"]["kg"])
        if light not in (most, cheap):
            awards.append(("いちばん軽い", light,
                           f"{light['_spec']['kg']:g}kg。持ち運ぶならこれです。"))
    if label == "宅配ボックス" and weighed:
        heavy = max(weighed, key=lambda p: p["_spec"]["kg"])
        if heavy not in (most, cheap):
            awards.append(("いちばん動きにくい", heavy,
                           f"本体{heavy['_spec']['kg']:g}kg。"
                           f"風で動かしたくないならこれです。"))
    rated = [p for p in group if p["review_count"] >= 30]
    if rated:
        best = max(rated, key=lambda p: p["review_average"])
        if best not in [a[1] for a in awards]:
            awards.append(("評価がいちばん高い", best,
                           f"平均{best['review_average']:.2f}"
                           f"（{best['review_count']:,}件）。"))
    return awards[:3]


def comparison_table(group, label):
    if label == "ポータブル電源":
        heads = ["商品", "容量", "定格出力", "重量", "電池", "価格", "レビュー"]
        def row(p):
            s = p["_spec"]
            return [
                f'<a {link_attrs(p)}>{esc(shorten(p["name"], 44))}</a>',
                f'{s["wh"]:,}Wh' if s["wh"] else "—",
                f'{s["w"]:,}W' if s["w"] else "—",
                f'{s["kg"]:g}kg' if s["kg"] else "—",
                s["battery"] or "—",
                f'{p["price"]:,}円',
                f'{p["review_average"]:.2f}／{p["review_count"]:,}件',
            ]
    else:
        heads = ["商品", "容量", "材質", "重量", "ポスト", "固定", "価格", "レビュー"]
        def row(p):
            s = p["_spec"]
            return [
                f'<a {link_attrs(p)}>{esc(shorten(p["name"], 44))}</a>',
                f'{s["liters"]}L' if s["liters"] else "—",
                s["material"] or "—",
                f'{s["kg"]:g}kg' if s["kg"] else "—",
                "一体型" if s["post"] else "なし",
                "アンカー可" if s["anchor"] else "—",
                f'{p["price"]:,}円',
                f'{p["review_average"]:.2f}／{p["review_count"]:,}件',
            ]

    body = []
    for p in group:
        cells = row(p)
        tds = [f"<td>{cells[0]}</td>"]
        tds += [f'<td class="num">{esc(c)}</td>' for c in cells[1:]]
        body.append("<tr>" + "".join(tds) + "</tr>")

    return (f'<div class="tablewrap"><table class="cmp"><thead><tr>'
            + "".join(f"<th>{esc(h)}</th>" for h in heads)
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def dedupe(group, key):
    """同じ商品の重複出品をまとめる。仕様と価格が一致するものは1つにする。"""
    best = {}
    for p in sorted(group, key=lambda x: -x["review_count"]):
        sig = (p["price"], p["_spec"][key], p["_spec"]["kg"])
        if sig not in best:
            best[sig] = p
    return list(best.values())


def article_page(article, group):
    group = dedupe(group, article["key"])
    group = sorted(group, key=lambda p: -p["review_count"])[:10]
    label = article["label"]
    awards = pick_awards(group, label)

    award_html = "".join(f"""<li>
  <h4>{esc(tag)}</h4>
  <p class="nm"><a {link_attrs(p)}>{esc(shorten(p["name"], 40))}</a></p>
  <p class="why">{esc(why)}</p>
</li>""" for tag, p, why in awards)

    key = article["key"]
    values = [p["_spec"][key] for p in group if p["_spec"][key]]
    unit = "Wh" if key == "wh" else "L"
    span = (f"この記事で扱っているのは{min(values):,}{unit}から{max(values):,}{unit}まで、"
            f"{len(group)}機種です。") if values else ""

    body = f"""<div class="lead">
  <h2 class="head">{esc(article['title'])}</h2>
  <p class="stamp">{esc(TODAY)}時点のデータ／掲載{len(group)}件</p>
  <p>{esc(article['intro'])}</p>
</div>

<div class="art">
  <h3>まずは一覧で見る</h3>
  <p>{esc(span)}楽天のレビュー件数が多い順に並べています。表は横にスクロールできます。</p>
</div>
{comparison_table(group, label)}

<div class="art">
  <h3>データから見た選択肢</h3>
  <p>下の3つは、取得したデータから機械的に選んだものです。
     運営者の好みで順位を付けてはいません。</p>
</div>
<ul class="awards">{award_html}</ul>

<div class="art">
  <h3>選ぶときの目安</h3>
  <p>{esc(article['pick'])}</p>
  <p>仕様の数値は各ショップの商品説明から読み取ったものです。
     表に「—」とあるものは、説明文から値を読み取れなかった商品です。
     購入前には商品ページで確認してください。</p>
</div>

<div class="sect-title"><h2>この帯の商品を詳しく見る</h2></div>
<ul class="grid" id="picks"></ul>
"""
    js = f"""<script>
window.PICKS = {json.dumps(payload_of(group), ensure_ascii=False)};
document.getElementById('picks').innerHTML = window.PICKS.map(window.cardHTML).join('');
</script>"""
    return page(f"{article['title']}｜{SITE_NAME}", body, "article", 1, js)


def articles_index(built):
    cards = "".join(f"""<li>
  <h3><a href="articles/{a['id']}.html">{esc(a['title'])}</a></h3>
  <p>{n}件を比較／{esc(a['label'])}</p>
</li>""" for a, n in built)
    body = f"""<div class="lead">
  <h2 class="head">比較記事</h2>
  <p>容量帯ごとに、仕様と価格を表にして並べています。
     数値はすべて楽天の公式APIから取得したものです。</p>
</div>
<ul class="arts">{cards}</ul>
"""
    return page(f"比較記事｜{SITE_NAME}", body, "articles", 0)


# ------------------------------------------------------------------ 一覧ページ
def section_page(section, products):
    items = [p for p in products if p["label"] == section["label"]]
    payload = payload_of(items)
    prices = sorted(p["price"] for p in items)
    low, high = prices[len(prices) // 3], prices[len(prices) * 2 // 3]

    body = f"""<div class="lead">
  <h2 class="head">{esc(section['label'])}を{len(items)}件、並べています</h2>
  <p>{esc(section['lead'])}</p>
</div>

<div class="controls">
  <div class="group">
    <span class="cap">並び順</span>
    <button data-sort="reviews" aria-pressed="true">レビューが多い順</button>
    <button data-sort="rated" aria-pressed="false">評価が高い順</button>
    <button data-sort="cheap" aria-pressed="false">安い順</button>
    <button data-sort="dear" aria-pressed="false">高い順</button>
  </div>
  <div class="group">
    <span class="cap">価格帯</span>
    <button data-band="all" aria-pressed="true">すべて</button>
    <button data-band="low" aria-pressed="false">～{low:,}円</button>
    <button data-band="mid" aria-pressed="false">{low:,}～{high:,}円</button>
    <button data-band="high" aria-pressed="false">{high:,}円～</button>
  </div>
</div>
<p class="count" id="count"></p>
<ul class="grid" id="list"></ul>
"""
    js = f"""<script>
var LOW = {low}, HIGH = {high};
window.ITEMS = {json.dumps(payload, ensure_ascii=False)};
</script>
<script src="../app.js"></script>"""
    return page(f"{section['label']}の一覧｜{SITE_NAME}", body, section["slug"], 1, js)


def top_three(products):
    """レビュー件数の多い3点。ただし分類が偏らないよう、各分類から最低1つ入れる。"""
    ranked = sorted(products, key=lambda p: -p["review_count"])
    chosen = []
    for s in SECTIONS:
        head = next((p for p in ranked if p["label"] == s["label"]), None)
        if head:
            chosen.append(head)
    for p in ranked:
        if len(chosen) >= 3:
            break
        if p not in chosen:
            chosen.append(p)
    return sorted(chosen, key=lambda p: -p["review_count"])[:3]


def hero_html(products):
    cards = []
    for i, p in enumerate(top_three(products), 1):
        full = round(p["review_average"])
        stars = "★" * full + "☆" * (5 - full)
        img = p["images"][0] if p["images"] else ""
        photo = (f'<img src="{esc(img)}" alt="" loading="eager">' if img else "")
        spec = p["_blurb"].split("。")[0] + "。" if p["_blurb"] else ""
        cards.append(f"""<li>
  <a class="ph" {link_attrs(p)}>{photo}
    <span class="rank">{i}</span><span class="cat">{esc(p['label'])}</span>
  </a>
  <div class="t">
    <h3><a {link_attrs(p)}>{esc(shorten(p['name'], 42))}</a></h3>
    <p class="sp">{esc(spec)}</p>
    <div class="ft">
      <span class="pr">{p['price']:,}<small>円</small></span>
      <span class="rv"><span class="s">{stars}</span> {p['review_average']:.2f}<br>
        レビュー{p['review_count']:,}件</span>
    </div>
  </div>
</li>""")
    return '<ul class="hero">' + "".join(cards) + "</ul>"


def index_page(products, built):
    tiles = []
    for s in SECTIONS:
        items = [p for p in products if p["label"] == s["label"]]
        if not items:
            continue
        prices = sorted(p["price"] for p in items)
        tiles.append(f"""<li class="tile">
  <h3>{esc(s['label'])}</h3>
  <p>{esc(s['lead'][:70])}…</p>
  <p class="nums">{len(items)}件掲載／中心価格 {prices[len(prices) // 2]:,}円</p>
  <a class="enter" href="{s['slug']}/index.html">{esc(s['label'])}を見比べる</a>
</li>""")

    arts = "".join(f"""<li>
  <h3><a href="articles/{a['id']}.html">{esc(a['title'])}</a></h3>
  <p>{n}件を比較／{esc(a['label'])}</p>
</li>""" for a, n in built[:6])

    body = f"""<div class="sect-title">
  <h2>いま、いちばん読まれている3点</h2>
  <a href="articles.html">比較記事を見る</a>
</div>
{hero_html(products)}

<div class="lead">
  <p>商品情報は楽天の公式APIから取得しています。仕様と値段を表にして、
     見比べられるようにしたサイトです。</p>
</div>

<ul class="tiles">{"".join(tiles)}</ul>

<div class="sect-title">
  <h2>容量帯ごとの比較記事</h2>
  <a href="articles.html">すべて見る</a>
</div>
<ul class="arts">{arts}</ul>
"""
    return page(f"{SITE_NAME}｜{SITE_TAGLINE}", body, "index", 0)


def doc_page(filename, title, body_html):
    body = f'<div class="doc"><h2 class="head">{esc(title)}</h2>{body_html}</div>'
    return page(f"{title}｜{SITE_NAME}", body, filename, 0)


def main():
    if not os.path.exists(STORE):
        sys.exit(f"{STORE} がありません。先に rakuten_collect.py を実行してください。")
    with open(STORE, encoding="utf-8") as f:
        products = [p for p in json.load(f) if p.get("url") and p.get("price")]
    if not products:
        sys.exit("商品データが空です。")

    notes = load_map(NOTES, "ひと言")
    reviews = load_map(REVIEWS, "レビューまとめ")

    for p in products:
        p["_spec"] = extract(p)
        p["_blurb"] = blurb_from(p["_spec"], p["label"])
        p["_note"] = notes.get(p["code"], "")
        p["_summary"] = reviews.get(p["code"], "")

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "articles"))

    for name, content in (("style.css", CSS), ("app.js", APP_JS), ("card.js", CARD_JS)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(content)

    for image in ("banner.jpg", "banner-slim.jpg"):
        if os.path.exists(image):
            shutil.copy(image, os.path.join(OUT, image))
        else:
            print(f"警告: {image} が見つかりません。ヘッダー画像なしで生成します。",
                  file=sys.stderr)

    # 比較記事
    built = []
    for a in ARTICLES:
        group = [p for p in products
                 if p["label"] == a["label"]
                 and p["_spec"][a["key"]]
                 and a["min"] <= p["_spec"][a["key"]] < a["max"]]
        group = dedupe(group, a["key"])
        if len(group) < 4:
            print(f"  記事を作りませんでした（対象{len(group)}件）: {a['title']}")
            continue
        with open(os.path.join(OUT, "articles", f"{a['id']}.html"), "w", encoding="utf-8") as f:
            f.write(article_page(a, group))
        built.append((a, min(len(group), 10)))

    with open(os.path.join(OUT, "articles.html"), "w", encoding="utf-8") as f:
        f.write(articles_index(built))
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_page(products, built))
    for s in SECTIONS:
        folder = os.path.join(OUT, s["slug"])
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(section_page(s, products))
    for filename, title, content in PAGES:
        with open(os.path.join(OUT, filename), "w", encoding="utf-8") as f:
            f.write(doc_page(filename, title, content))

    open(os.path.join(OUT, ".nojekyll"), "w").close()

    # 検索エンジン向け
    urls = ["index.html", "articles.html"] + [f"{s['slug']}/index.html" for s in SECTIONS]
    urls += [f"articles/{a['id']}.html" for a, _ in built]
    urls += [fn for fn, _, _ in PAGES]
    stamp = date.today().isoformat()
    entries = "".join(
        f"\n  <url><loc>{BASE_URL}/{u}</loc><lastmod>{stamp}</lastmod></url>"
        for u in urls
    )
    with open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                f"{entries}\n</urlset>\n")
    with open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    print(f"\n{OUT}/ に書き出しました。商品 {len(products)}件。")
    print(f"  比較記事 {len(built)}本:")
    for a, n in built:
        print(f"    articles/{a['id']}.html  {a['title']}（{n}件）")
    print("  index.html / articles.html / about.html / privacy.html / disclaimer.html")
    for s in SECTIONS:
        print(f"  {s['slug']}/index.html")
    print("  style.css / app.js / card.js / sitemap.xml / robots.txt")


if __name__ == "__main__":
    main()
