#!/usr/bin/env python3
"""
369 サイト生成スクリプト（比較記事つき）

products.json から、商品一覧ページと容量帯ごとの比較記事を生成する。
記事の中身は楽天公式APIで取得した仕様と価格だけを根拠にしている。
使用感の記述は notes.json、レビューの総括は reviews.json から読む。

使い方:
    python build_site.py
"""

import csv
import html
import json
import os
import re
import shutil
import sys
from datetime import date

import fieldreview  # 実使用レビューの読み込み（同じフォルダの fieldreview.py）
import specs       # 仕様の抽出と検証（同じフォルダの specs.py）

STORE = "products.json"
NOTES = "notes.json"            # 旧：ひと言メモ。reviews.json に置き換わった（互換のため残す）
REVIEWS = "reviews.json"        # 実使用レビュー（運営者が書いたものだけ）
OUT = "site"
BASE_URL = "https://ozsyu.github.io"   # 公開URL。独自ドメインにしたらここを直す
# Googleサーチコンソールの所有権確認用。消すと未確認に戻るので残しておくこと
GOOGLE_VERIFY = "Kb2NCJSVxiX0KRuGZumT1xqZFLP-Zv7CF6bCa7jksmE"

SITE_NAME = "369"
SITE_TAGLINE = "プロ目線で選ぶ、長く使えるアイテムを実際に使う道具を値段で並べて見比べてみる。"
SITE_DESC = ("石材と土木の現場で道具を使う目線から、ポータブル電源と宅配ボックスを"
             "容量・重量・価格で比較しています。")
TODAY = date.today().strftime("%Y年%m月%d日")

BUILT_IDS = set()   # 実際に生成した比較記事のID。内部リンクの有無を決める

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
        "axis": "wh", "min": 0, "max": 500,
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
        "axis": "wh", "min": 500, "max": 1000,
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
        "axis": "wh", "min": 1000, "max": 2000,
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
        "axis": "wh", "min": 2000, "max": 99999,
        "intro": "停電時に家電をひととおり動かす、あるいは電源のない現場で一日作業する"
                 "ための容量です。20kgを超えるものが多く、据え置いて使う前提になります。"
                "価格も20万円前後からで、発電機と比較検討する領域です。",
        "pick": "この価格帯なら保証期間を見てください。3年と5年では、"
                "実質的な年あたりの負担がかなり変わります。",
    },
    {
        "id": "box-under10k",
        "label": "宅配ボックス",
        "title": "1万円未満の宅配ボックスを比較",
        "axis": "price", "min": 0, "max": 10000,
        "intro": "いちばん安い帯です。折りたたみ式や簡易なものが中心で、"
                 "常設というより「まず試す」ための価格です。"
                 "軽いものが多いので、風の通る場所では固定が要ります。",
        "pick": "この帯は本体重量を見てください。10kgを切るものは、"
                "荷物が入っていない状態だと強風で動きます。",
    },
    {
        "id": "box-10to20k",
        "label": "宅配ボックス",
        "title": "1万円〜2万円の宅配ボックスを比較",
        "axis": "price", "min": 10000, "max": 20000,
        "intro": "置き型の主力価格帯です。スチール製で容量もそれなりにあり、"
                 "日用品のまとめ買いが入ります。ポストは別という製品が多い帯です。",
        "pick": "アンカー固定に対応しているかを先に確認してください。"
                "後から固定したくなっても、底に穴が無いと打てません。",
    },
    {
        "id": "box-20to30k",
        "label": "宅配ボックス",
        "title": "2万円〜3万円の宅配ボックスを比較",
        "axis": "price", "min": 20000, "max": 30000,
        "intro": "いちばん選ばれている帯です。ポストと宅配ボックスが一体になった"
                 "製品が多く、玄関まわりを1台で片づけられます。"
                 "重量も15kg前後あり、置くだけでもそれなりに安定します。",
        "pick": "一体型は幅を取ります。先に設置場所の幅と、扉の開く向きを"
                "測っておいてください。玄関ドアと干渉する例をよく見ます。",
    },
    {
        "id": "box-30to50k",
        "label": "宅配ボックス",
        "title": "3万円〜5万円の宅配ボックスを比較",
        "axis": "price", "min": 30000, "max": 50000,
        "intro": "大型化と作りの良さで値が上がる帯です。ステンレス製や、"
                 "複数の荷物を受けられる構造のものが入ってきます。"
                 "重量が20kgを超えるものが増え、置くだけでも動きません。",
        "pick": "この帯からは、据え付けを前提にした製品が混じります。"
                "土間があるか、基礎を打つ必要があるかで総額が変わります。",
    },
    {
        "id": "box-over50k",
        "label": "宅配ボックス",
        "title": "5万円以上の宅配ボックスを比較",
        "axis": "price", "min": 50000, "max": 10 ** 9,
        "intro": "据え付けを前提にした製品や、門柱と一体になったものが中心です。"
                 "本体価格のほかに設置費用がかかることが多く、"
                 "外構工事と一緒に考える領域になります。",
        "pick": "本体価格だけで比べないでください。基礎や配管の手間が乗ると、"
                "総額は本体の1.5倍前後になることがあります。",
    },
]


# ------------------------------------------------------------------ 用途から探す
# 条件はすべて取得済みの数値から機械的に判定する。該当するかどうかは
# ページ上に「判定の条件」として明示し、推測で分類しない。
USES = [
    {
        "id": "genba",
        "label": "ポータブル電源",
        "title": "現場で電動工具を使いたい",
        "rule": "定格出力 1,500W 以上",
        "lead": "丸ノコやインパクトは、起動する瞬間に定格を超える電流が流れます。"
                "容量が足りていても定格出力が低いと動きません。"
                "まず定格で足切りしてから、容量を見てください。",
        "match": lambda s, p: bool(s["w"]) and s["w"] >= 1500,
        "related": ["power-1000to2000", "power-over2000"],
    },
    {
        "id": "diy",
        "label": "ポータブル電源",
        "title": "DIY・日曜大工で使いたい",
        "rule": "定格出力 1,000W 以上",
        "lead": "ドリルやサンダー、小型の電動工具であれば1,000Wで足ります。"
                "屋外のコンセントが無い場所での作業や、庭仕事が中心ならこの帯です。",
        "match": lambda s, p: bool(s["w"]) and s["w"] >= 1000,
        "related": ["power-500to1000", "power-1000to2000"],
    },
    {
        "id": "bosai",
        "label": "ポータブル電源",
        "title": "停電や災害に備えたい",
        "rule": "容量 1,000Wh 以上／電池がリン酸鉄リチウム",
        "lead": "備えとして置くものは、使わない期間が長くなります。"
                "リン酸鉄リチウムは充放電できる回数が三元系より多く、"
                "長く置いておく用途に向きます。冷蔵庫を一晩動かすには1,000Whが目安です。",
        "match": lambda s, p: bool(s["wh"]) and s["wh"] >= 1000 and s["battery"] == "リン酸鉄",
        "related": ["power-1000to2000", "power-over2000"],
    },
    {
        "id": "shachuhaku",
        "label": "ポータブル電源",
        "title": "車中泊で使いたい",
        "rule": "容量 500〜1,500Wh／重量 15kg 以下",
        "lead": "車に積んで出し入れする前提なので、重量が効きます。"
                "15kgを超えると片手では持てません。容量は一泊なら500Whから、"
                "電気毛布や小型冷蔵庫を使うなら1,000Wh前後が目安です。",
        "match": lambda s, p: (bool(s["wh"]) and 500 <= s["wh"] <= 1500
                               and bool(s["kg"]) and s["kg"] <= 15),
        "related": ["power-500to1000", "power-1000to2000"],
    },
    {
        "id": "kateiyo",
        "label": "ポータブル電源",
        "title": "家に据えて使いたい",
        "rule": "容量 2,000Wh 以上",
        "lead": "持ち運ばずに家へ置く前提なら、重量を気にせず容量で選べます。"
                "この帯は20kgを超えるものが多く、置き場所を決めてから買うものです。",
        "match": lambda s, p: bool(s["wh"]) and s["wh"] >= 2000,
        "related": ["power-over2000"],
    },
    {
        "id": "cospa",
        "label": "ポータブル電源",
        "title": "1Whあたり価格の安い順で選びたい",
        "rule": "価格 ÷ 容量(Wh) が安い順",
        "lead": "1Whあたり価格とは、本体価格を容量(Wh)で割った数字です。"
                "100,000円で1,000Whなら100円/Wh。この数字が小さいほど、"
                "同じ金額で多くの電気を蓄えられます。"
                "容量の違う機種を同じものさしで比べるための指標で、"
                "重さや出力の良し悪しは含んでいません。軽さが要るなら重量欄も見てください。",
        "match": lambda s, p: bool(s["wh"]) and bool(p.get("price")),
        "sort": lambda s, p: p["price"] / s["wh"],
        "related": ["power-500to1000", "power-1000to2000"],
    },
    {
        "id": "box-post",
        "label": "宅配ボックス",
        "title": "ポストも一緒にしたい",
        "rule": "ポスト一体型",
        "lead": "郵便受けと宅配ボックスを1台にまとめた製品です。"
                "玄関まわりがすっきりしますが、そのぶん幅を取ります。"
                "設置場所の幅と、扉の開く向きを先に測ってください。",
        "match": lambda s, p: s["post"],
        "related": ["box-20to30k", "box-30to50k"],
    },
    {
        "id": "box-anchor",
        "label": "宅配ボックス",
        "title": "固定して使いたい",
        "rule": "アンカー固定に対応",
        "lead": "空の宅配ボックスは思っているより軽く、強風で動きます。"
                "底にアンカー用の穴があるかどうかで、後から固定できるかが決まります。"
                "吹きさらしの場所に置くなら、ここを外さないでください。",
        "match": lambda s, p: s["anchor"],
        "related": ["box-10to20k", "box-20to30k"],
    },
    {
        "id": "box-multi",
        "label": "宅配ボックス",
        "title": "荷物を複数受け取りたい",
        "rule": "商品説明に複数投函・複数受け取りの記載",
        "lead": "一度受け取ると次が入らない製品が多いなか、"
                "連続して投函できると書かれているものを集めました。"
                "通販の利用が多い家庭では、ここが効いてきます。",
        "match": lambda s, p: "複数荷物対応" in s["tags"],
        "related": ["box-20to30k", "box-30to50k"],
    },
    {
        "id": "box-heavy",
        "label": "宅配ボックス",
        "title": "動かない重さがほしい",
        "rule": "本体重量 20kg 以上",
        "lead": "固定せずに置くなら、本体の重さがそのまま安定性になります。"
                "20kgを超えると、荷物が空でも風では動きません。"
                "ただし搬入と設置はひとりでは厳しくなります。",
        "match": lambda s, p: bool(s["kg"]) and s["kg"] >= 20,
        "related": ["box-30to50k", "box-over50k"],
    },
]

USE_SEO = {
    "genba": [
        "現場向けポータブル電源の選び方｜電動工具に必要な定格出力で比較",
        "丸ノコやインパクトを動かすには容量より定格出力が効きます。定格1,500W以上の機種を、容量・重量・1Whあたり価格で比較しました。"
    ],
    "diy": [
        "DIY向けポータブル電源の選び方｜ドリル・サンダーが動く出力で比較",
        "ドリルやサンダーなら定格1,000Wで足ります。屋外作業や庭仕事で使える機種を、容量と価格で並べました。"
    ],
    "bosai": [
        "防災用ポータブル電源の選び方｜停電時に必要な容量とリン酸鉄で比較",
        "冷蔵庫を一晩動かす目安は1,000Wh。長く置いておく備えに向くリン酸鉄リチウムの機種を、容量・出力・価格で比較しました。"
    ],
    "shachuhaku": [
        "車中泊向けポータブル電源の選び方｜積める重さと必要容量で比較",
        "車に積んで出し入れするなら15kgが上限の目安です。500〜1,500Whで持てる重さの機種を、容量・出力・価格で並べました。"
    ],
    "kateiyo": [
        "家庭備蓄向けポータブル電源の選び方｜2000Wh以上を容量と価格で比較",
        "持ち運ばず家に据える前提なら重量を気にせず容量で選べます。2,000Wh以上の機種を、出力・1Whあたり価格で比較しました。"
    ],
    "cospa": [
        "ポータブル電源の1Whあたり価格を比較｜容量と価格のバランスで選ぶ",
        "本体価格を容量で割った1Whあたり価格で並べました。容量の違う機種を同じものさしで比べられます。"
    ],
    "box-post": [
        "ポスト一体型宅配ボックスの選び方｜サイズ・設置方法・価格で比較",
        "郵便受けと宅配ボックスを1台にまとめた製品を、幅と奥行き・重量・設置方法・価格で比較しました。"
    ],
    "box-anchor": [
        "アンカー固定できる宅配ボックスの選び方｜風対策と設置方法で比較",
        "空の宅配ボックスは風で動きます。底にアンカー用の穴がある製品を、サイズ・重量・価格で比較しました。"
    ],
    "box-multi": [
        "複数の荷物を受け取れる宅配ボックス｜連続投函できる製品を比較",
        "商品説明に複数投函や連続受け取りの記載がある製品だけを集め、サイズ・重量・設置方法・価格で比較しました。"
    ],
    "box-heavy": [
        "重くて動かない宅配ボックスの選び方｜本体20kg以上を比較",
        "固定せずに置くなら本体の重さが安定性になります。20kg以上の製品を、サイズ・設置方法・価格で比較しました。"
    ]
}

ARTICLE_SEO = {
    "power-under500": [
        "500Wh以下のポータブル電源を比較｜軽さ重視で選ぶ小容量モデル",
        "スマホやノートPCの充電が主な用途になる帯です。5〜7kg台の機種を、定格出力・重量・1Whあたり価格で比較しました。"
    ],
    "power-500to1000": [
        "500〜1000Whポータブル電源を比較｜車中泊・停電対策の定番容量",
        "一泊の車中泊や停電の一晩をしのげる容量帯です。電池の種類と重量、1Whあたり価格を並べて比較しました。"
    ],
    "power-1000to2000": [
        "1000〜2000Whポータブル電源を比較｜電動工具と電子レンジが動く容量",
        "定格1,500W以上なら電動工具や電子レンジも動きます。容量・出力・重量・1Whあたり価格を並べて比較しました。"
    ],
    "power-over2000": [
        "2000Wh以上の大容量ポータブル電源を比較｜家庭備蓄向けの据え置き型",
        "停電時に家電をひととおり動かす容量帯です。20kg超が中心のため、据え置いて使う前提で出力と1Whあたり価格を比較しました。"
    ],
    "box-under10k": [
        "1万円未満の宅配ボックスを比較｜まず試したい人向けの低価格モデル",
        "折りたたみ式や簡易な製品が中心の価格帯です。サイズ・重量・設置方法を並べ、風対策の要否が分かるようにしました。"
    ],
    "box-10to20k": [
        "1万円〜2万円の宅配ボックスを比較｜置き型の主力価格帯",
        "スチール製で容量もある置き型の主力帯です。サイズ・重量・アンカー固定の可否・価格を比較しました。"
    ],
    "box-20to30k": [
        "2万円〜3万円の宅配ボックスを比較｜ポスト一体型が中心の価格帯",
        "ポストと宅配ボックスが一体の製品が多い帯です。幅と奥行き・重量・設置方法を並べ、玄関に収まるか分かるようにしました。"
    ],
    "box-30to50k": [
        "3万円〜5万円の宅配ボックスを比較｜大型・複数荷物対応モデル",
        "ステンレス製や複数荷物を受けられる製品が入る帯です。サイズ・重量・設置方法・価格を比較しました。"
    ],
    "box-over50k": [
        "5万円以上の宅配ボックスを比較｜据付前提の門柱一体型",
        "据え付けを前提とした製品や門柱と一体のものが中心です。本体のサイズ・重量・設置方法を比較しました。"
    ]
}

ARTICLE_META = {
    "power-under500": [
        "この帯で何が動くか、本体の重さはどれくらいか、1Whあたりの価格はいくらか。",
        "スマホやノートPCの充電が主な目的で、できるだけ軽いものを探している人。"
    ],
    "power-500to1000": [
        "一泊の車中泊や停電の一晩をしのげる容量かどうか、電池の種類と重さ、1Whあたりの価格。",
        "車中泊や停電への備えとして、持ち運べる上限の重さまでを許せる人。"
    ],
    "power-1000to2000": [
        "電動工具や電子レンジが動く定格出力かどうか、重量が持ち運べる範囲か、1Whあたりの価格。",
        "現場や家で使う前提で、容量と出力の両方を確保したい人。"
    ],
    "power-over2000": [
        "据え置いて使う前提の容量と重量、1Whあたりの価格が下の帯と比べて得かどうか。",
        "停電時に家電をひととおり動かしたい人。持ち運びは考えていない人。"
    ],
    "box-under10k": [
        "この価格で買える本体の大きさと重さ、固定できるかどうか。",
        "まず試してみたい人。設置場所が風の当たらない所にある人。"
    ],
    "box-10to20k": [
        "置き型の主力価格帯で、サイズ・重量・固定方法がどう違うか。",
        "ポストは別で用意済みで、宅配ボックスだけ足したい人。"
    ],
    "box-20to30k": [
        "ポスト一体型が中心のこの帯で、サイズと設置方法がどう違うか。",
        "玄関まわりをポストごと1台にまとめたい人。"
    ],
    "box-30to50k": [
        "大型・高耐久の製品で、重量と設置方法がどう違うか。",
        "通販の利用が多く、複数の荷物を受けたい人。"
    ],
    "box-over50k": [
        "据付を前提とした製品の大きさ・重さ・設置方法。",
        "外構工事とあわせて設置を考えている人。"
    ]
}

PAGES = [
    ("about.html", "このサイトについて", """
<p>369は、石材と土木の仕事をしている運営者が、現場で実際に使う道具を
値段と仕様で並べて見比べるために作ったサイトです。</p>
<h2>掲載しているデータについて</h2>
<p>商品情報は楽天ウェブサービスが公開している公式APIから取得しています。
容量や重量といった仕様は、各ショップの商品説明文から自動的に抜き出したものです。
転記の誤りがあり得ますので、購入前には必ず商品ページでご確認ください。</p>
<h2>「おすすめ」の根拠について</h2>
<p>比較記事に付けている「最軽量」「最安」「レビュー最多」といった印は、
すべて取得したデータから機械的に判定したものです。
運営者の主観で順位を付けてはいません。</p>
<h2>使った商品と、使っていない商品</h2>
<p>運営者が実際に使った商品には「使ってみて」という欄を付けています。
ここだけは実体験です。付いていない商品は使っていません。
使ってもいない道具の使用感を書くつもりはないので、そこは正直に分けています。</p>
<p>「レビューまとめ」の欄は、楽天に投稿されたレビューを運営者が読んで
要約したものです。こちらも書いていない商品には表示されません。</p>
"""),
    ("privacy.html", "プライバシーポリシー", """
<h2>アクセス情報について</h2>
<p>当サイトは静的なページのみで構成されており、運営者が閲覧者の個人情報を
直接取得することはありません。</p>
<h2>外部サービスについて</h2>
<p>当サイトは楽天アフィリエイトを利用しています。商品リンクをクリックした際、
楽天グループが提供するプログラムによってCookieが利用され、
どのサイト経由で訪問したかが記録される場合があります。
これは購入の成果を判定するためのもので、氏名や住所などの個人情報を
運営者が知ることはありません。</p>
<p>Cookieの利用はブラウザの設定で拒否できます。方法はお使いのブラウザの
説明をご確認ください。</p>
"""),
    ("disclaimer.html", "免責事項", """
<h2>アフィリエイトについて</h2>
<p>当サイトは楽天アフィリエイトによる広告を掲載しています。
リンクから商品を購入された場合、運営者に紹介料が支払われます。</p>
<h2>掲載情報について</h2>
<p>価格、在庫、レビュー件数、商品仕様は、データを取得した時点のものです。
実際の販売条件と異なる場合がありますので、最新の情報は各商品ページで
必ずご確認ください。</p>
<h2>損害について</h2>
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
h1.pagetitle{font-size:23px;line-height:1.5;margin:0 0 10px;letter-spacing:.01em}
h2.head{font-size:22px;margin:0 0 8px;line-height:1.5}
.crumb{border-bottom:1px solid var(--rule);background:var(--bg);font-size:12px}
.crumb .wrap{padding:9px 22px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;
 color:var(--soft)}
.crumb a{color:var(--link);text-decoration:none}
.crumb a:hover{text-decoration:underline}
.crumb .sep{color:var(--rule)}
.crumb [aria-current]{color:var(--ink)}
.tagline{font-size:23px;font-weight:700;line-height:1.45;margin:0 0 12px}
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
.usedbadge{display:inline-block;background:var(--mark);color:var(--ink);
 font-size:11.5px;font-weight:700;padding:3px 10px;margin:0 0 7px;text-decoration:none;
 border:1px solid var(--ink)}
.usedbadge:hover{background:var(--ink);color:#fff}
.usedbadge:before{content:"\2713\0020"}
.card h3{font-size:16px;line-height:1.6;margin:0 0 7px;font-weight:600}
.card h3 a{color:var(--ink);text-decoration:none}
.card h3 a:hover{text-decoration:underline}
.blurb{margin:0 0 9px;font-size:13.5px;line-height:1.75;color:var(--soft)}
.note{margin:0 0 9px;padding:10px 12px;background:var(--tint);border-left:4px solid var(--mark);
 font-size:13.5px;line-height:1.75}
.note b{display:block;font-size:11px;color:var(--soft);margin-bottom:3px;font-weight:600}
.price{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;margin:0 0 8px}
.price .perwh{font-size:12px;font-weight:400;color:var(--soft);margin-left:9px;
 font-variant-numeric:tabular-nums}
.fit{margin:0 0 8px;font-size:12.5px;line-height:2}
.fit b{display:block;font-size:11px;color:var(--soft);font-weight:600;margin-bottom:3px}
.fit span{display:inline-block;border:1px solid var(--rule);background:var(--tint);
 padding:2px 9px;margin:0 5px 4px 0;font-size:12px;line-height:1.7}
.caution{margin:0 0 8px;padding:0 0 0 2px;list-style:none;font-size:12.5px;line-height:1.75}
.caution li{position:relative;padding-left:15px;color:var(--soft);margin-bottom:2px}
.caution li:before{content:"・";position:absolute;left:2px}
.caution li.h{padding-left:0;font-size:11px;font-weight:600;color:var(--soft);
 margin-bottom:3px}
.caution li.h:before{content:""}
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
table.cmp{border-collapse:collapse;width:100%;font-size:13.5px;min-width:900px;
 background:var(--bg);table-layout:auto}
table.cmp th:first-child,table.cmp td:first-child{min-width:210px;max-width:260px}
table.cmp th,table.cmp td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--rule);
 vertical-align:top}
table.cmp thead th{background:var(--tint);font-size:12.5px;font-weight:600;white-space:nowrap;
 border-bottom:2px solid var(--ink)}
table.cmp td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.cmp tbody tr:last-child td{border-bottom:0}
table.cmp a{text-decoration:none;font-weight:600}
table.cmp a:hover{text-decoration:underline}
.tablebadge{display:inline-block;background:var(--mark);color:var(--ink);
 font-size:10.5px;font-weight:700;padding:1px 6px;margin-right:5px;
 text-decoration:none;border:1px solid var(--ink);vertical-align:1px}
.tablebadge:hover{background:var(--ink);color:#fff}
.tag{display:inline-block;background:var(--mark);color:var(--ink);font-size:10.5px;
 font-weight:700;padding:2px 7px;margin-right:5px;white-space:nowrap}

.awards{list-style:none;margin:0 0 30px;padding:0;display:grid;
 grid-template-columns:repeat(3,1fr);gap:16px}
.awards li{border:1px solid var(--rule);border-top:4px solid var(--mark);padding:16px 18px}
.awards h3{margin:0 0 4px;font-size:12px;color:var(--soft);font-weight:600}
.awards .nm{font-size:14px;font-weight:600;line-height:1.55;margin:0 0 6px}
.awards .nm a{color:var(--ink);text-decoration:none}
.awards .nm a:hover{text-decoration:underline}
.awards .why{margin:0;font-size:12.5px;color:var(--soft);line-height:1.7}

.arts{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:16px}
.arts li{border:1px solid var(--rule);padding:18px 20px}
.arts h2,.arts h3{margin:0 0 5px;font-size:15.5px;line-height:1.55;font-weight:600}
.arts h2 a,.arts h3 a{color:var(--ink);text-decoration:none}
.arts h2 a:hover,.arts h3 a:hover{text-decoration:underline}
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

/* ---- ヒーロー（スマホ基準で組み、広い画面で広がる）---- */
.hero-lead{border-bottom:1px solid var(--rule);padding:26px 0 24px;margin-bottom:28px}
.hero-lead .tagline .accent{
  background:linear-gradient(transparent 62%,var(--mark) 62%);padding:0 2px}
.hero-lead p{margin:0 0 10px;font-size:15px;line-height:1.9;max-width:60ch}
.hero-lead p.sub{color:var(--soft);font-size:13.5px}
.cta{display:flex;flex-direction:column;gap:10px;margin:20px 0 0}
.cta a{
  display:block;text-align:center;padding:14px 18px;text-decoration:none;
  font-size:15px;font-weight:600;border:1px solid var(--ink)}
.cta a.primary{background:var(--ink);color:#fff}
.cta a.primary:hover{background:var(--link);border-color:var(--link)}
.cta a.ghost{background:var(--bg);color:var(--ink)}
.cta a.ghost:hover{background:var(--tint)}
.cta a:focus-visible{outline:2px solid var(--link);outline-offset:2px}
.facts{display:flex;flex-wrap:wrap;gap:14px;margin:18px 0 0;font-size:12px;
 color:var(--soft);font-variant-numeric:tabular-nums}
.facts b{color:var(--ink);font-size:14px;font-weight:700;margin-right:3px}

/* ---- 用途から探す ---- */
.uses{list-style:none;margin:0;padding:0;display:grid;gap:14px}
.uses li{border:1px solid var(--rule);border-left:5px solid var(--mark);padding:16px 18px}
.uses h3{margin:0 0 5px;font-size:16px;line-height:1.5}
.uses h3 a{color:var(--ink);text-decoration:none}
.uses h3 a:hover{text-decoration:underline}
.uses .rule{margin:0 0 7px;font-size:12px;color:var(--soft);font-variant-numeric:tabular-nums}
.uses .rule b{color:var(--ink);font-weight:600}
.uses p.t{margin:0;font-size:13.5px;line-height:1.8;color:var(--soft)}
h2.usegroup{margin:34px 0 14px;font-size:14px;font-weight:700;
 padding-bottom:6px;border-bottom:2px solid var(--ink)}

.criteria{background:var(--tint);border-left:4px solid var(--mark);
 padding:14px 16px;margin:0 0 24px}
.criteria p{margin:0 0 6px;font-size:13.5px;line-height:1.8}
.criteria p:last-child{margin:0}
.criteria b{font-size:13px}

.morelink{margin:26px 0 0;padding:16px 18px;background:var(--tint);
 border-left:4px solid var(--mark)}
.morelink p{margin:0 0 10px;font-size:13.5px;line-height:1.85}
.morelink p:last-child{margin:0}
.morelink .links{display:flex;flex-direction:column;gap:8px}
.morelink .links a{font-size:14px;font-weight:600;text-decoration:none}
.morelink .links button{font:inherit;font-size:14px;font-weight:600;padding:12px 20px;
 border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer;width:100%}
.morelink .links button:hover{background:var(--link);border-color:var(--link)}
.morelink .links button:focus-visible{outline:2px solid var(--link);outline-offset:2px}
@media (min-width:620px){.morelink .links button{width:auto}}
.morelink .links a:hover{text-decoration:underline}
@media (min-width:620px){.morelink .links{flex-direction:row;gap:22px}}

.related{list-style:none;margin:28px 0 0;padding:16px 0 0;border-top:1px solid var(--rule)}
.related strong{display:block;font-size:13px;margin-bottom:8px}
.related li{margin:0 0 6px;font-size:14px}

@media (min-width:620px){
  .shots{grid-template-columns:1fr 1fr}
  h1.pagetitle{font-size:27px}
  .cta{flex-direction:row}
  .cta a{flex:0 0 auto;min-width:200px}
  .hero-lead .tagline{font-size:27px}
  .uses{grid-template-columns:1fr 1fr}
}

.tiles{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:0;padding:0;list-style:none}
.tile{border:1px solid var(--rule);border-top:5px solid var(--mark);padding:22px}
.tile h3{margin:0 0 8px;font-size:18px}
.tile p{margin:0 0 12px;font-size:14px}
.tile .nums{color:var(--soft);font-size:13px;font-variant-numeric:tabular-nums}
.tile a.enter{display:inline-block;margin-top:12px;font-weight:600;text-decoration:none}

.art{max-width:74ch}
.art h2{font-size:17px;margin:34px 0 8px;padding-bottom:5px;border-bottom:2px solid var(--ink)}
.art p{margin:0 0 16px}
/* 実使用レビュー */
.trust{border:1px solid var(--mark);border-left:5px solid var(--mark);
 background:var(--tint);padding:15px 18px;margin:0 0 22px}
.trust p{margin:0 0 7px;font-size:13.5px;line-height:1.85}
.trust p:last-child{margin:0;color:var(--soft);font-size:12.5px}
.trust b{font-size:14.5px}
.ownrating{margin:0 0 20px;font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.ownrating .s{color:var(--mark);letter-spacing:2px}
.ownrating small{font-size:12px;font-weight:400;color:var(--soft)}
dl.kv{display:grid;grid-template-columns:auto 1fr;gap:0;margin:0 0 24px;
 border-top:1px solid var(--rule);font-size:14px}
dl.kv dt{padding:10px 16px 10px 0;border-bottom:1px solid var(--rule);
 color:var(--soft);font-size:13px;white-space:nowrap}
dl.kv dd{padding:10px 0;margin:0;border-bottom:1px solid var(--rule);
 font-variant-numeric:tabular-nums}
ul.rvlist{margin:0 0 22px;padding-left:22px}
ul.rvlist li{margin:0 0 7px;font-size:15px;line-height:1.85}
.shots{display:grid;gap:16px;margin:0 0 24px}
.shots figure{margin:0}
.shots img{width:100%;height:auto;border:1px solid var(--rule);display:block}
.shots figcaption{margin-top:6px;font-size:12.5px;color:var(--soft);line-height:1.7}
p.src{margin:0 0 14px;font-size:12.5px;color:var(--soft);line-height:1.8}
p.buy{margin:26px 0 0}
p.buy .go{display:block;text-align:center;padding:14px;font-size:15px}
.doc{max-width:68ch}
.doc h2{font-size:16px;margin:28px 0 6px}
.doc p{margin:0 0 14px}

footer{border-top:1px solid var(--rule);background:var(--tint);margin-top:20px}
footer .wrap{padding:26px 22px 40px;font-size:12.5px;color:var(--soft)}
footer .flinks{margin:0 0 14px;display:flex;flex-wrap:wrap;gap:16px}
footer .flinks a{text-decoration:none}
footer p{margin:0 0 7px;max-width:70ch}

/* スマホではナビを折り返さず、横に流せる帯にする */
@media (max-width:700px){
  nav.tabs .wrap{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;
   scrollbar-width:none}
  nav.tabs .wrap::-webkit-scrollbar{display:none}
  nav.tabs a{white-space:nowrap;padding:12px 13px;font-size:14px}
  .sect-title{flex-wrap:wrap;gap:4px 12px}
  .sect-title h2{flex:1 1 100%}
  .sect-title a{font-size:13px}
}

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
  if (p.depth === undefined) p.depth = window.CARD_DEPTH || 0;
  var full = Math.round(p.review_average);
  var stars = '';
  for (var i = 0; i < 5; i++) stars += (i < full ? '\\u2605' : '\\u2606');
  var yen = p.price.toLocaleString('ja-JP');
  var rev = p.review_count.toLocaleString('ja-JP');
  var link = 'href="' + p.url + '" target="_blank" rel="nofollow sponsored noopener"';
  var badge = p.reviewed
    ? '<a class="usedbadge" href="' + (p.depth ? '../' : '') + p.reviewurl
      + '">実際に使ってみた</a>'
    : '';
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
    +   badge
    +   '<h3><a ' + link + '>' + p.name + '</a></h3>'
    +   '<p class="price">' + yen + '<small>円</small>'
    +     (p.perwh ? '<span class="perwh">' + p.perwh + '円/Wh</span>' : '')
    +   '</p>'
    +   (p.note ? '<p class="note"><b>使ってみて</b>' + p.note + '</p>' : '')
    +   (p.blurb ? '<p class="blurb">' + p.blurb + '</p>' : '')
    +   (p.fit && p.fit.length
          ? '<p class="fit"><b>向いている用途</b>'
            + p.fit.map(function (t) { return '<span>' + t + '</span>'; }).join('')
            + '</p>'
          : '')
    +   (p.cautions && p.cautions.length
          ? '<ul class="caution"><li class="h">注意点</li>'
            + p.cautions.map(function (t) { return '<li>' + t + '</li>'; }).join('')
            + '</ul>'
          : '')
    + '</div>'
    + side
    + '</li>';
};
"""


# ------------------------------------------------------------------ 仕様の抽出
def extract(product):
    """仕様の抽出は specs.py に任せる。食い違う値は None（＝不明）で返ってくる。"""
    return specs.extract(product)


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
        "reviewed": bool(p.get("_review")),
        "reviewurl": (f"review/{fieldreview.slug_of(p['code'])}.html"
                      if p.get("_review") else ""),
        "summary": esc(p["_summary"]),
        "fit": [esc(t) for t in p["_spec"].get("tags", [])],
        "cautions": [esc(c) for c in p["_spec"].get("cautions", [])],
        "perwh": (f"{yen_per_wh(p):.1f}" if yen_per_wh(p) else ""),
    } for p in items]
    rows.sort(key=lambda x: (0 if (x["note"] or x["summary"]) else 1, -x["review_count"]))
    return rows


def link_attrs(product):
    return (f'href="{esc(product["url"])}" target="_blank" '
            f'rel="nofollow sponsored noopener"')


def breadcrumb_html(trail, root):
    """画面に出すパンくず。最後の1つは現在地なのでリンクにしない。"""
    if not trail:
        return ""
    parts = []
    for i, (label, url) in enumerate(trail):
        last = i == len(trail) - 1
        if last or not url:
            parts.append(f'<span aria-current="page">{esc(label)}</span>')
        else:
            parts.append(f'<a href="{root}{esc(url)}">{esc(label)}</a>')
    return ('<nav class="crumb" aria-label="パンくず"><div class="wrap">'
            + '<span class="sep">＞</span>'.join(parts) + "</div></nav>")


def breadcrumb_jsonld(trail):
    """BreadcrumbList。画面に出しているパンくずと同じ内容だけを入れる。"""
    if not trail:
        return ""
    items = []
    for i, (label, url) in enumerate(trail, 1):
        entry = {"@type": "ListItem", "position": i, "name": label}
        if url:
            entry["item"] = f"{BASE_URL}/{url}"
        items.append(entry)
    data = {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": items}
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False) + "</script>")


def itemlist_jsonld(products, name, page_url):
    """
    ItemList。ページに実際に出ている商品の名前・価格・リンクだけを入れる。
    レビューや評価は運営者のものではないので構造化データには入れない。
    """
    if not products:
        return ""
    items = []
    for i, p in enumerate(products, 1):
        items.append({
            "@type": "ListItem",
            "position": i,
            "name": shorten(p["name"], 70),
            "url": p["url"],
        })
    data = {"@context": "https://schema.org", "@type": "ItemList",
            "name": name, "url": f"{BASE_URL}/{page_url}",
            "numberOfItems": len(items), "itemListElement": items}
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False) + "</script>")


def page(title, body, active, depth=0, extra_js="", *,
         description=None, canonical=None, heading=None, trail=None,
         jsonld="", og_type="website"):
    """
    1ページ分のHTML。
      description … このページ固有の説明文
      canonical   … index.html からの相対パス（例 "use/genba.html"）
      heading     … H1 の文字列。指定がなければ title の「｜」より前
      trail       … パンくず [(表示名, URL or None), ...]
      jsonld      … 構造化データのscriptタグ
    """
    root = "../" if depth else ""
    desc = description or SITE_DESC
    canon = f"{BASE_URL}/{canonical}" if canonical else f"{BASE_URL}/index.html"
    h1 = heading or title.split("｜")[0]

    banner, bh, bw = (("banner.jpg", 418, 2172) if active == "index"
                      else ("banner-slim.jpg", 372, 2400))
    tabs = [("トップ", root + "index.html", active == "index")]
    for s in SECTIONS:
        tabs.append((s["label"], f"{root}{s['slug']}/index.html", active == s["slug"]))
    tabs.append(("実際に使ってみた", root + "reviews.html", active in ("reviews", "review")))
    tabs.append(("用途から探す", root + "use.html", active in ("uses", "use")))
    tabs.append(("比較記事", root + "articles.html", active in ("articles", "article")))
    tabs.append(("このサイトについて", root + "about.html", active == "about.html"))

    nav = "".join(
        f'<a href="{esc(url)}"{" class=\'on\'" if on else ""}>{esc(label)}</a>'
        for label, url, on in tabs
    )
    flinks = "".join(f'<a href="{root}{fn}">{esc(t)}</a>' for fn, t, _ in PAGES)
    crumb = breadcrumb_html(trail, root)
    crumb_ld = breadcrumb_jsonld(trail)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="google-site-verification" content="{GOOGLE_VERIFY}">
<link rel="canonical" href="{esc(canon)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{esc(canon)}">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:image" content="{BASE_URL}/banner.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="{root}style.css">
{crumb_ld}
{jsonld}
</head>
<body>
<header class="masthead">
  <a class="banner" href="{root}index.html">
    <img src="{root}{banner}" alt="369 SELECT　暮らしのそばに、いいモノを。"
         width="{bw}" height="{bh}">
  </a>
</header>
<nav class="tabs"><div class="wrap">{nav}</div></nav>
{crumb}
<main><div class="wrap">
<h1 class="pagetitle">{esc(h1)}</h1>
{body}
</div></main>
<footer><div class="wrap">
  <p class="flinks"><a href="{root}index.html">トップ</a>{flinks}</p>
  <p>当サイトは楽天アフィリエイトを利用しています。掲載リンクから商品を購入すると、運営者に紹介料が入ります。</p>
  <p>商品情報は楽天ウェブサービスの公式APIから取得しています。星印は運営者の評価ではなく、楽天レビューの平均値です。</p>
  <p>Supported by <a href="https://webservice.rakuten.co.jp/" target="_blank" rel="noopener">楽天ウェブサービス</a>　&copy; {esc(SITE_NAME)}</p>
</div></footer>
<script>window.CARD_DEPTH = {depth};</script>
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


def review_mark(product, root="../"):
    """比較表に出す小さな印。実使用レビューがある商品だけ。"""
    if not product.get("_review"):
        return ""
    url = f"{root}review/{fieldreview.slug_of(product['code'])}.html"
    return (f'<a class="tablebadge" href="{url}" '
            f'title="運営者が実際に使ってレビューしています">使用済</a> ')


def yen_per_wh(product):
    """1Whあたりの価格。容量が不明なら None。"""
    wh = product["_spec"].get("wh")
    if not wh or not product.get("price"):
        return None
    return product["price"] / wh


def comparison_table(group, label):
    """
    比較表。読み取れなかった項目は「不明」と書き、推測した値は入れない。
    """
    if label == "ポータブル電源":
        heads = ["商品", "価格", "容量", "定格出力", "重量",
                 "1Whあたり価格", "評価", "レビュー件数"]

        def row(p):
            s = p["_spec"]
            per = yen_per_wh(p)
            return [
                (review_mark(p) + f'<a {link_attrs(p)}>{esc(shorten(p["name"], 44))}</a>'),
                f'{p["price"]:,}円',
                f'{s["wh"]:,}Wh' if s["wh"] else "不明",
                f'{s["w"]:,}W' if s["w"] else "不明",
                f'{s["kg"]:g}kg' if s["kg"] else "不明",
                f"{per:.1f}円/Wh" if per else "不明",
                f'{p["review_average"]:.2f}',
                f'{p["review_count"]:,}件',
            ]
    else:
        heads = ["商品", "価格", "サイズ", "重量", "設置方法",
                 "ポスト一体型", "複数荷物", "評価", "レビュー件数"]

        def row(p):
            s = p["_spec"]
            return [
                (review_mark(p) + f'<a {link_attrs(p)}>{esc(shorten(p["name"], 44))}</a>'),
                f'{p["price"]:,}円',
                specs.size_text(s["size"]) or "不明",
                f'{s["kg"]:g}kg' if s["kg"] else "不明",
                s["install"] or "不明",
                "一体型" if s["post"] else "なし",
                specs.feature_text(s, "multi"),
                f'{p["review_average"]:.2f}',
                f'{p["review_count"]:,}件',
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


def axis_value(product, article):
    """記事の軸にあたる値。価格軸なら価格、容量軸なら仕様の値。"""
    axis = article.get("axis", article.get("key"))
    if axis == "price":
        return product.get("price")
    return product["_spec"].get(axis)


def axis_unit(article):
    axis = article.get("axis", article.get("key"))
    return {"wh": "Wh", "liters": "L", "price": "円"}.get(axis, "")


def dedupe(group, article):
    """同じ商品の重複出品をまとめる。仕様と価格が一致するものは1つにする。"""
    best = {}
    for p in sorted(group, key=lambda x: -x["review_count"]):
        sig = (p["price"], axis_value(p, article), p["_spec"]["kg"])
        if sig not in best:
            best[sig] = p
    return list(best.values())


def neighbour_links(article, built_ids):
    """同じ分類の記事のうち、ひとつ下とひとつ上の帯へのリンク。"""
    same = [a for a in ARTICLES
            if a["label"] == article["label"] and a["id"] in built_ids]
    same.sort(key=lambda a: a["min"])
    idx = next((i for i, a in enumerate(same) if a["id"] == article["id"]), None)
    out = []
    if idx is None:
        return out
    if idx > 0:
        prev = same[idx - 1]
        out.append((f"ひとつ下の帯：{prev['title']}", f"articles/{prev['id']}.html"))
    if idx < len(same) - 1:
        nxt = same[idx + 1]
        out.append((f"ひとつ上の帯：{nxt['title']}", f"articles/{nxt['id']}.html"))
    return out


def related_uses(article):
    """この記事から行ける用途ページ。related に記事IDを持つ用途を逆引きする。"""
    return [(f"{u['title']}（{u['rule']}）", f"use/{u['id']}.html")
            for u in USES if article["id"] in u.get("related", [])]


def article_page(article, group):
    group = dedupe(group, article)
    group = sorted(group, key=lambda p: -p["review_count"])[:10]
    label = article["label"]
    awards = pick_awards(group, label)

    award_html = "".join(f"""<li>
  <h3>{esc(tag)}</h3>
  <p class="nm"><a {link_attrs(p)}>{esc(shorten(p["name"], 40))}</a></p>
  <p class="why">{esc(why)}</p>
</li>""" for tag, p, why in awards)

    values = [v for v in (axis_value(p, article) for p in group) if v]
    unit = axis_unit(article)
    span = (f"この記事で扱っているのは{min(values):,}{unit}から{max(values):,}{unit}まで、"
            f"{len(group)}機種です。") if values else ""

    know, who = ARTICLE_META.get(article["id"], ("", ""))
    box_note = ("" if label == "ポータブル電源" else
                "<p>「複数荷物」は、商品説明に複数投函や連続受け取りの記載があるものだけを"
                "「対応」としています。「不明」は対応していないという意味ではなく、"
                "記載からは確認できなかったという意味です。</p>")
    meta_html = ""
    if know or who:
        meta_html = f"""<div class="criteria">
  <p><b>この比較で分かること</b><br>{esc(know)}</p>
  <p><b>こんな人向け</b><br>{esc(who)}</p>
</div>"""

    rows = []
    for _label, _url in neighbour_links(article, BUILT_IDS) + related_uses(article):
        rows.append(f'<li><a href="../{_url}">{esc(_label)}</a></li>')
    links_html = (f'<ul class="related"><strong>関連するページ</strong>{"".join(rows)}</ul>'
                  if rows else "")

    body = f"""<div class="lead">
  <p class="stamp">{esc(TODAY)}時点のデータ／掲載{len(group)}件</p>
  <p>{esc(article['intro'])}</p>
</div>
{meta_html}

<div class="art">
  <h2>まずは一覧で見る</h2>
  <p>{esc(span)}楽天のレビュー件数が多い順に並べています。表は横にスクロールできます。</p>
</div>
{comparison_table(group, label)}

<div class="art">
  <h2>データから見た選択肢</h2>
  <p>下の3つは、取得したデータから機械的に選んだものです。
     運営者の好みで順位を付けてはいません。</p>
</div>
<ul class="awards">{award_html}</ul>

<div class="art">
  <h2>選ぶときの目安</h2>
  <p>{esc(article['pick'])}</p>
  <p>仕様の数値は各ショップの商品説明から読み取ったものです。
     表に「不明」とあるものは、商品情報から確かな値を読み取れなかったものです。推測した値は載せていません。
     購入前には商品ページで確認してください。</p>
  {box_note}
</div>

<div class="sect-title"><h2>この帯の商品を詳しく見る</h2></div>
<ul class="grid" id="picks"></ul>
{links_html}
"""
    js = f"""<script>
window.PICKS = {json.dumps(payload_of(group), ensure_ascii=False)};
document.getElementById('picks').innerHTML = window.PICKS.map(window.cardHTML).join('');
</script>"""
    seo_title, seo_desc = ARTICLE_SEO.get(
        article["id"], (article["title"], article["intro"][:110]))
    sec = next(x for x in SECTIONS if x["label"] == article["label"])
    canonical = f"articles/{article['id']}.html"
    trail = [("369", "index.html"), (article["label"], f"{sec['slug']}/index.html"),
             ("比較記事", "articles.html"), (article["title"], None)]
    return page(f"{seo_title}｜{SITE_NAME}", body, "article", 1, js,
                description=seo_desc, canonical=canonical,
                heading=article["title"], trail=trail, og_type="article",
                jsonld=itemlist_jsonld(group, article["title"], canonical))


def articles_index(built):
    cards = "".join(f"""<li>
  <h2><a href="articles/{a['id']}.html">{esc(a['title'])}</a></h2>
  <p>{n}件を比較／{esc(a['label'])}</p>
</li>""" for a, n in built)
    body = f"""<div class="lead">
  <p>容量帯ごとに、仕様と価格を表にして並べています。
     数値はすべて楽天の公式APIから取得したものです。</p>
</div>
<ul class="arts">{cards}</ul>
"""
    return page(f"ポータブル電源・宅配ボックスの比較記事一覧｜容量帯・価格帯で選ぶ｜{SITE_NAME}",
                body, "articles", 0,
                description="ポータブル電源は容量帯、宅配ボックスは価格帯ごとに、"
                            "仕様と価格を表にして並べています。数値はすべて楽天の公式APIから取得したものです。",
                canonical="articles.html", heading="比較記事",
                trail=[("369", "index.html"), ("比較記事", None)])


# ------------------------------------------------------------------ 一覧ページ
def section_page(section, products):
    items = [p for p in products if p["label"] == section["label"]]
    payload = payload_of(items)
    prices = sorted(p["price"] for p in items)
    low, high = prices[len(prices) // 3], prices[len(prices) * 2 // 3]

    body = f"""<div class="lead">
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
    seo = {
        "ポータブル電源": (
            f"ポータブル電源{len(items)}機種の一覧｜容量・出力・価格で絞り込み",
            "楽天で売れているポータブル電源を集め、容量・定格出力・重量・1Whあたり価格を"
            "並べました。価格帯と並び順を変えながら比べられます。"),
        "宅配ボックス": (
            f"宅配ボックス{len(items)}製品の一覧｜価格・サイズ・設置方法で絞り込み",
            "楽天で売れている宅配ボックスを集め、価格・サイズ・重量・設置方法を並べました。"
            "価格帯と並び順を変えながら比べられます。"),
    }
    seo_title, seo_desc = seo.get(
        section["label"], (f"{section['label']}の一覧", section["lead"][:110]))
    return page(f"{seo_title}｜{SITE_NAME}", body, section["slug"], 1, js,
                description=seo_desc,
                canonical=f"{section['slug']}/index.html",
                heading=f"{section['label']}の一覧",
                trail=[("369", "index.html"), (section["label"], None)])


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


def index_page(products, built, uses_count):
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

    hero = f"""<div class="hero-lead">
  <p>仕事・DIY・防災・車中泊。実際に使う場面から考えて、
     価格と性能とレビューを並べています。</p>
  <p class="sub">石材と土木の現場で道具を使っている運営者が、
     楽天の商品データと現場で分かったことを突き合わせて、
     「この商品は何に向いているのか」が分かるようにしたサイトです。</p>
  <div class="cta">
    <a class="primary" href="use.html">用途から探す</a>
    <a class="ghost" href="articles.html">比較記事を見る</a>
  </div>
  <p class="facts">
    <span><b>{len(products)}</b>件 掲載</span>
    <span><b>{len(built)}</b>本 比較記事</span>
    <span><b>{uses_count}</b>通り 用途から絞り込み</span>
    <span>最終更新 {esc(TODAY)}</span>
  </p>
</div>

"""

    use_cards = "".join(f"""<li>
  <h3><a href="use/{u['id']}.html">{esc(u['title'])}</a></h3>
  <p class="rule">条件：{esc(u['rule'])}</p>
</li>""" for u in USES[:4])

    body = hero + f"""<div class="sect-title">
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
  <h2>用途から探す</h2>
  <a href="use.html">すべて見る</a>
</div>
<ul class="uses">{use_cards}</ul>

<div class="sect-title">
  <h2>価格帯・容量帯ごとの比較記事</h2>
  <a href="articles.html">すべて見る</a>
</div>
<ul class="arts">{arts}</ul>
"""
    return page("369｜現場目線でポータブル電源と宅配ボックスを比較",
                body, "index", 0,
                description="石材と土木の現場で道具を使う運営者が、楽天の商品データをもとに"
                            "ポータブル電源と宅配ボックスを比較しています。用途から探せて、"
                            "仕様が読み取れない項目は「不明」と明記しています。",
                canonical="index.html",
                heading="現場目線で選ぶ、ポータブル電源と宅配ボックス")


REVIEW_LOG = "review_needed.csv"


def write_review_log(products):
    """要確認の商品を一覧にして残す。毎回上書きする。"""
    rows = []
    for p in products:
        spec = p["_spec"]
        for issue in spec.get("issues", []):
            rows.append({
                "区分": issue["level"],
                "商品コード": p["code"],
                "分類": p["label"],
                "項目": specs.FIELD_LABEL.get(issue["field"], issue["field"]),
                "内容": issue["message"],
                "採用値": spec.get(issue["field"]) if issue["field"] != "price"
                          else p.get("price"),
                "掲載": "停止" if spec.get("block") else "掲載する",
                "価格": p["price"],
                "商品名": p["name"][:80],
                "URL": p["url"],
            })
    rows.sort(key=lambda r: (r["区分"] != specs.BLOCK, r["項目"]))

    fields = ["区分", "商品コード", "分類", "項目", "内容", "採用値", "掲載",
              "価格", "商品名", "URL"]
    with open(REVIEW_LOG, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return rows


def spec_coverage(products):
    """項目ごとに、確かな値が取れている割合を数える。"""
    out = {}
    for label, keys in (("ポータブル電源", ("wh", "w", "kg")),
                        ("宅配ボックス", ("liters", "kg"))):
        items = [p for p in products if p["label"] == label]
        if not items:
            continue
        out[label] = {
            k: (sum(1 for p in items if p["_spec"][k] is not None), len(items))
            for k in keys
        }
    return out


def use_members(use, products):
    """その用途に当てはまる商品を返す。条件に合うものだけで、推測はしない。"""
    hits = [p for p in products
            if p["label"] == use["label"] and use["match"](p["_spec"], p)]
    if use.get("sort"):
        hits.sort(key=lambda p: use["sort"](p["_spec"], p))
    else:
        hits.sort(key=lambda p: -p["review_count"])
    return hits


def use_page(use, products, by_id):
    members = use_members(use, products)
    first = 12
    shown = members[:first]

    rel = "".join(
        f'<li><a href="../articles/{rid}.html">{esc(by_id[rid]["title"])}</a></li>'
        for rid in use.get("related", []) if rid in by_id)
    rel_html = (f'<ul class="related"><strong>あわせて読む</strong>{rel}</ul>'
                if rel else "")

    slug = next(x["slug"] for x in SECTIONS if x["label"] == use["label"])
    total_label = f'{sum(1 for p in products if p["label"] == use["label"]):,}'

    order = ("1Whあたり価格（価格÷容量）の安い順" if use.get("sort")
             else "楽天のレビュー件数が多い順")

    body = f"""<div class="lead">
  <p class="stamp">{esc(TODAY)}時点のデータ／条件に合う {len(members)}件のうち {len(shown)}件を表示</p>
  <p>{esc(use['lead'])}</p>
</div>

<div class="criteria">
  <p><b>判定の条件：{esc(use['rule'])}</b></p>
  <p>楽天の商品情報から読み取れた数値だけで機械的に絞り込んでいます。
     数値が読み取れなかった商品は、条件に合っていても出てきません。
     並び順は{esc(order)}です。</p>
</div>

<ul class="grid" id="list-use"></ul>

<div class="morelink" id="morebox">
  <p><b>この条件に合う商品は全部で{len(members)}件あります。</b>
     最初は{first}件だけ出しています。この条件のまま、残りも続けて見られます。</p>
  <p class="links">
    <button type="button" id="more">この条件のまま、残り{len(members) - first}件を表示</button>
  </p>
</div>

<div class="morelink" id="donebox" hidden>
  <p><b>{len(members)}件すべてを表示しました。</b>
     価格帯や容量帯で絞って見たい場合は、比較記事のほうが選びやすくなっています。</p>
  <p class="links">
    <a href="../articles.html">価格帯・容量帯ごとの比較記事</a>
    <a href="../{slug}/index.html">{esc(use['label'])}の一覧 {total_label}件</a>
  </p>
</div>
{rel_html}
"""
    js = f"""<script>
window.USE_ITEMS = {json.dumps(payload_of(members), ensure_ascii=False)};
(function () {{
  var all = window.USE_ITEMS, step = {first};
  var list = document.getElementById('list-use');
  var box = document.getElementById('morebox'), done = document.getElementById('donebox');
  var btn = document.getElementById('more'), shown = 0;

  function draw(n) {{
    shown = Math.min(n, all.length);
    list.innerHTML = all.slice(0, shown).map(window.cardHTML).join('');
    if (shown >= all.length) {{
      if (box) box.hidden = true;
      if (done) done.hidden = false;
    }}
  }}
  if (btn) btn.addEventListener('click', function () {{ draw(all.length); }});
  draw(step);
}})();
</script>"""
    seo_title, seo_desc = USE_SEO.get(use["id"], (use["title"], use["lead"][:110]))
    canonical = f"use/{use['id']}.html"
    trail = [("369", "index.html"), (use["label"], f"{slug}/index.html"),
             ("用途から探す", "use.html"), (use["title"], None)]
    return page(f"{seo_title}｜{SITE_NAME}", body, "use", 1, js,
                description=seo_desc, canonical=canonical,
                heading=use["title"], trail=trail, og_type="article",
                jsonld=itemlist_jsonld(shown, use["title"], canonical))


def uses_index(products):
    groups = {}
    for u in USES:
        groups.setdefault(u["label"], []).append(u)

    blocks = []
    for label, items in groups.items():
        cards = "".join(f"""<li>
  <h3><a href="use/{u['id']}.html">{esc(u['title'])}</a></h3>
  <p class="rule">条件：{esc(u['rule'])}　／　<b>{len(use_members(u, products))}件</b></p>
  <p class="t">{esc(u['lead'][:62])}…</p>
</li>""" for u in items)
        blocks.append(f'<h2 class="usegroup">{esc(label)}</h2>'
                      f'<ul class="uses">{cards}</ul>')

    body = f"""<div class="lead">
  <p>「何に使うか」から入れるようにしました。容量の数字ではなく、
     やりたいことで絞り込めます。条件はすべて商品データから機械的に判定していて、
     各ページに判定の条件を書いてあります。</p>
</div>
{"".join(blocks)}
"""
    return page("用途から探すポータブル電源・宅配ボックス｜現場・防災・車中泊など"
                f"10通りの条件で絞り込み｜{SITE_NAME}", body, "uses", 0,
                description="現場仕事・DIY・防災・車中泊など、使う場面から商品を絞り込めます。"
                            "条件はすべて商品データの数値で判定しており、各ページに判定基準を明記しています。",
                canonical="use.html", heading="用途から探す",
                trail=[("369", "index.html"), ("用途から探す", None)])


DOC_SEO = {
    "about.html": ("369について｜商品データの集め方と「使ってみた」の扱い",
                   "掲載データの出どころ、おすすめの判定基準、"
                   "実際に使った商品と使っていない商品の分け方を書いています。"),
    "privacy.html": ("プライバシーポリシー",
                     "当サイトのアクセス情報の扱いと、楽天アフィリエイトで利用される"
                     "Cookieについて説明しています。"),
    "disclaimer.html": ("免責事項",
                        "アフィリエイトの利用、掲載情報の正確性、"
                        "損害についての考え方を記載しています。"),
}


def review_page(product, review):
    """
    実使用レビューの記事。
    使用感は reviews.json、仕様と価格は楽天APIと、情報源を分けて表示する。
    書かれていない項目は出さない。文章を補わない。
    """
    spec = product["_spec"]
    sec = next(x for x in SECTIONS if x["label"] == product["label"])
    slug = fieldreview.slug_of(product["code"])
    canonical = f"review/{slug}.html"
    title = shorten(product["name"], 40)

    # --- 使った条件。書かれているものだけ ---
    facts = [(label, value) for label, value in (
        ("使用場所", review["place"]),
        ("使用期間", review["duration"]),
        ("使用用途", review["purpose"]),
        ("レビュー日", review["date"]),
    ) if value]
    facts_html = "".join(
        f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in facts)

    def bullet_block(heading, items):
        if not items:
            return ""
        lis = "".join(f"<li>{esc(t)}</li>" for t in items)
        return f'<h3>{esc(heading)}</h3><ul class="rvlist">{lis}</ul>'

    good_html = bullet_block("良かった点", review["good"])
    bad_html = bullet_block("気になった点", review["bad"])
    for_html = (f'<h3>どんな人に向いているか</h3><p>{esc(review["recommend_for"])}</p>'
                if review["recommend_for"] else "")

    # --- 写真。実在するものだけが review["photos"] に入っている ---
    photos_html = ""
    if review["photos"]:
        shots = "".join(
            f'<figure><img src="../photos/{esc(ph["file"])}" '
            f'alt="{esc(ph["alt"])}" loading="lazy">'
            + (f"<figcaption>{esc(ph['alt'])}</figcaption>" if ph["alt"] else "")
            + "</figure>"
            for ph in review["photos"])
        photos_html = f'<h3>撮影した写真</h3><div class="shots">{shots}</div>'

    # --- 仕様。楽天APIから取れたものだけ ---
    if product["label"] == "ポータブル電源":
        rows = [("容量", f'{spec["wh"]:,}Wh' if spec["wh"] else "不明"),
                ("定格出力", f'{spec["w"]:,}W' if spec["w"] else "不明"),
                ("重量", f'{spec["kg"]:g}kg' if spec["kg"] else "不明"),
                ("電池", spec["battery"] or "不明")]
        per = yen_per_wh(product)
        if per:
            rows.append(("1Whあたり価格", f"{per:.1f}円/Wh"))
    else:
        rows = [("サイズ", specs.size_text(spec["size"]) or "不明"),
                ("重量", f'{spec["kg"]:g}kg' if spec["kg"] else "不明"),
                ("設置方法", spec["install"] or "不明"),
                ("ポスト一体型", "一体型" if spec["post"] else "なし"),
                ("複数荷物", specs.feature_text(spec, "multi"))]
    rows.append(("価格", f'{product["price"]:,}円'))
    spec_html = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows)

    rating_html = ""
    if review["rating"]:
        full = round(review["rating"])
        stars = "★" * full + "☆" * (5 - full)
        rating_html = (f'<p class="ownrating"><span class="s">{stars}</span> '
                       f'{review["rating"]:.1f}　<small>運営者の評価</small></p>')

    body = f"""<div class="trust">
  <p><b>この商品は運営者が実際に使用してレビューしています。</b></p>
  <p>使用感の記述は運営者が書いたものです。仕様と価格は楽天ウェブサービスの公式APIから
     取得した値で、下の「楽天レビュー」は楽天の利用者による評価です。運営者の評価とは別物です。</p>
</div>

{rating_html}

<h2>使った条件</h2>
<dl class="kv">{facts_html}</dl>

{good_html}
{bad_html}
{for_html}
{photos_html}

<h2>この商品の仕様と価格</h2>
<p class="src">以下は楽天ウェブサービスの公式APIから取得した値です（{esc(TODAY)}時点）。
   読み取れなかった項目は「不明」と表示しています。</p>
<dl class="kv spec">{spec_html}</dl>
<p class="src">楽天レビュー {product["review_count"]:,}件の平均 {product["review_average"]:.2f}。
   これは楽天の利用者による評価で、運営者の評価ではありません。</p>

<p class="buy"><a class="go" {link_attrs(product)}>楽天で{esc(title)}を見る</a></p>

<ul class="related"><strong>関連するページ</strong>
  <li><a href="../{sec['slug']}/index.html">{esc(product['label'])}の一覧から他の商品を見る</a></li>
  <li><a href="../articles.html">価格帯・容量帯ごとの比較記事</a></li>
  <li><a href="../use.html">用途から探す</a></li>
</ul>
"""

    first_good = review["good"][0] if review["good"] else ""
    desc = (f"{title}を運営者が実際に使ったレビューです。"
            + (f"{review['place']}で{review['duration']}使用。" if review["place"] and review["duration"] else "")
            + (f"{first_good[:40]}" if first_good else ""))[:118]

    jsonld = review_jsonld(product, review, canonical)
    trail = [("369", "index.html"), (product["label"], f"{sec['slug']}/index.html"),
             ("実際に使ってみた", "reviews.html"), (title, None)]

    return page(f"{title}を実際に使ってみた｜{SITE_NAME}", body, "review", 1,
                description=desc, canonical=canonical,
                heading=f"{title}を実際に使ってみた",
                trail=trail, og_type="article", jsonld=jsonld)


def review_jsonld(product, review, canonical):
    """
    ページに出ている内容だけを構造化データにする。
    運営者が点数を入れていなければ評価は入れない。
    楽天の評価は運営者のものではないので入れない。
    """
    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": f"{shorten(product['name'], 40)}を実際に使ってみた",
        "url": f"{BASE_URL}/{canonical}",
        "author": {"@type": "Person", "name": SITE_NAME},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
    }
    if review["date"]:
        data["datePublished"] = review["date"]
    if review["photos"]:
        data["image"] = [f"{BASE_URL}/photos/{ph['file']}" for ph in review["photos"]]
    if review["rating"]:
        data["review"] = {
            "@type": "Review",
            "author": {"@type": "Person", "name": SITE_NAME},
            "reviewRating": {"@type": "Rating", "ratingValue": review["rating"],
                             "bestRating": 5, "worstRating": 1},
        }
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False) + "</script>")


def reviews_index(items):
    """実使用レビューの一覧。0件のときは正直に0件と書く。"""
    if items:
        cards = "".join(f"""<li>
  <h2><a href="review/{fieldreview.slug_of(p['code'])}.html">{esc(shorten(p['name'], 44))}</a></h2>
  <p>{esc(p['_review']['place'] or '')}{'／' if p['_review']['place'] and p['_review']['duration'] else ''}{esc(p['_review']['duration'] or '')}　{p['price']:,}円</p>
</li>""" for p in items)
        body = f"""<div class="lead">
  <p>運営者が実際に使った商品だけを載せています。{len(items)}件あります。
     使っていない商品には「実際に使ってみた」の表示は付きません。</p>
</div>
<ul class="arts">{cards}</ul>
"""
    else:
        body = """<div class="lead">
  <p>運営者が実際に使った商品のレビューを載せる場所です。現在は0件です。</p>
</div>
<div class="criteria">
  <p><b>使っていない商品のレビューは書きません。</b></p>
  <p>このサイトに並んでいる商品の大半は、運営者が買って使ったものではありません。
     使っていないものについて使用感を書くことはしないので、ここに出るのは
     実際に手元で使った商品だけになります。
     商品の仕様と価格は楽天の公式データから取得して一覧や比較記事に載せています。</p>
</div>
<ul class="related"><strong>データで比べるページ</strong>
  <li><a href="articles.html">価格帯・容量帯ごとの比較記事</a></li>
  <li><a href="use.html">用途から探す</a></li>
</ul>
"""
    return page(f"実際に使ってみた商品のレビュー一覧｜{SITE_NAME}", body, "reviews", 0,
                description="運営者が実際に使った商品だけのレビュー一覧です。"
                            "使っていない商品の使用感は書いていません。",
                canonical="reviews.html", heading="実際に使ってみた",
                trail=[("369", "index.html"), ("実際に使ってみた", None)])


def doc_page(filename, title, body_html):
    body = f'<div class="doc">{body_html}</div>'
    seo_title, seo_desc = DOC_SEO.get(filename, (title, SITE_DESC))
    return page(f"{seo_title}｜{SITE_NAME}", body, filename, 0,
                description=seo_desc, canonical=filename, heading=title,
                trail=[("369", "index.html"), (title, None)])


def main():
    if not os.path.exists(STORE):
        sys.exit(f"{STORE} がありません。先に rakuten_collect.py を実行してください。")
    with open(STORE, encoding="utf-8") as f:
        products = [p for p in json.load(f) if p.get("url") and p.get("price")]
    if not products:
        sys.exit("商品データが空です。")

    notes = load_map(NOTES, "ひと言")
    summaries = fieldreview.load_summaries(".")
    field_reviews, review_issues = fieldreview.load_reviews(".")
    if review_issues:
        print("\n== 実使用レビューの確認 ==")
        for msg in review_issues:
            print(f"  {msg}")

    for p in products:
        p["_spec"] = extract(p)
        p["_blurb"] = blurb_from(p["_spec"], p["label"])
        p["_note"] = notes.get(p["code"], "")
        p["_summary"] = summaries.get(p["code"], "")
        p["_review"] = field_reviews.get(p["code"])

    rows = write_review_log(products)

    # 中心となる仕様が確定できなかった商品は掲載しない
    blocked = [p for p in products if p["_spec"].get("block")]
    products = [p for p in products if not p["_spec"].get("block")]

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

    # 比較記事（先にIDを確定させてから本文を作る。内部リンクで前後の帯を参照するため）
    groups = {}
    for a in ARTICLES:
        group = [p for p in products
                 if p["label"] == a["label"]
                 and axis_value(p, a)
                 and a["min"] <= axis_value(p, a) < a["max"]]
        group = dedupe(group, a)
        if len(group) < 4:
            print(f"  記事を作りませんでした（対象{len(group)}件）: {a['title']}")
            continue
        groups[a["id"]] = (a, group)

    BUILT_IDS.clear()
    BUILT_IDS.update(groups)

    built = []
    for a, group in groups.values():
        with open(os.path.join(OUT, "articles", f"{a['id']}.html"), "w",
                  encoding="utf-8") as f:
            f.write(article_page(a, group))
        built.append((a, min(len(group), 10)))

    # 実使用レビュー（運営者が書いたものだけ。0件なら記事は作らない）
    reviewed = [p for p in products if p.get("_review")]
    if reviewed:
        os.makedirs(os.path.join(OUT, "review"), exist_ok=True)
        for p in reviewed:
            slug = fieldreview.slug_of(p["code"])
            with open(os.path.join(OUT, "review", f"{slug}.html"), "w",
                      encoding="utf-8") as f:
                f.write(review_page(p, p["_review"]))
        n_photos = fieldreview.copy_photos(
            {p["code"]: p["_review"] for p in reviewed}, OUT)
    else:
        n_photos = 0
    with open(os.path.join(OUT, "reviews.html"), "w", encoding="utf-8") as f:
        f.write(reviews_index(reviewed))

    # 用途から探す
    by_id = {a["id"]: a for a, _ in built}
    os.makedirs(os.path.join(OUT, "use"), exist_ok=True)
    for u in USES:
        with open(os.path.join(OUT, "use", f"{u['id']}.html"), "w", encoding="utf-8") as f:
            f.write(use_page(u, products, by_id))
    with open(os.path.join(OUT, "use.html"), "w", encoding="utf-8") as f:
        f.write(uses_index(products))

    with open(os.path.join(OUT, "articles.html"), "w", encoding="utf-8") as f:
        f.write(articles_index(built))
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_page(products, built, len(USES)))
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
    urls = ["index.html", "articles.html", "use.html"]
    urls += [f"{s['slug']}/index.html" for s in SECTIONS]
    urls += [f"articles/{a['id']}.html" for a, _ in built]
    urls += [f"use/{u['id']}.html" for u in USES]
    urls += ["reviews.html"]
    urls += [f"review/{fieldreview.slug_of(p['code'])}.html" for p in reviewed]
    urls += [fn for fn, _, _ in PAGES]
    # 重複を除き、実際に書き出したファイルだけを載せる（404を入れない）
    seen = set()
    unique = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        if os.path.exists(os.path.join(OUT, u)):
            unique.append(u)
    urls = unique
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
    print(f"\n== 仕様の取得状況（確かな値が取れた件数）==")
    names = {"wh": "容量(Wh)", "w": "定格出力(W)", "kg": "重量(kg)", "liters": "容量(L)"}
    for label, cov in spec_coverage(products).items():
        parts = [f"{names[k]} {n}/{t}" for k, (n, t) in cov.items()]
        print(f"  {label}: " + "／".join(parts))
    block_codes = {r["商品コード"] for r in rows if r["区分"] == specs.BLOCK}
    warn_codes = {r["商品コード"] for r in rows
                  if r["区分"] == specs.WARNING} - block_codes
    warn, block = len(warn_codes), len(block_codes)
    print(f"\n== 検証結果 ==")
    print(f"  正常     {len(products) - warn:>4}件")
    print(f"  WARNING  {warn:>4}件（確認推奨。掲載はしている）")
    print(f"  BLOCK    {block:>4}件（仕様が確定できず掲載を止めた）")
    print(f"  → {REVIEW_LOG} に {len(rows)}行を書き出しました。")
    print("  ※ 確定できなかった値は「不明」と表示し、推測値は使っていません。")
    print(f"  比較記事 {len(built)}本:")
    for a, n in built:
        print(f"    articles/{a['id']}.html  {a['title']}（{n}件）")
    print(f"  用途ページ {len(USES)}本: use.html + use/*.html")
    print(f"  実使用レビュー {len(reviewed)}件"
          + (f"（写真 {n_photos}枚）" if n_photos else "（写真なし）"))
    print("  index.html / articles.html / about.html / privacy.html / disclaimer.html")
    for s in SECTIONS:
        print(f"  {s['slug']}/index.html")
    print("  style.css / app.js / card.js / sitemap.xml / robots.txt")


if __name__ == "__main__":
    main()
