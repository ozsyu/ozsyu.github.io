#!/usr/bin/env python3
"""
SNS投稿案の生成（369）

サイトに載っている内容だけを材料にして、SNS用の投稿案を書き出す。
自動投稿はしない。人が読んで直してから投稿する前提の下書きを作るだけ。

守っていること:
  - 数値はすべて products.json から計算した実際の値を使う
  - 使っていない商品の使用感は書かない
  - 楽天のデータと運営者の実体験を文面の中で分けて書く
  - 既に approved / posted にしたものは上書きしない

使い方:
    python make_sns.py              投稿案を作る（既存の下書きは作り直す）
    python make_sns.py --list       いまある投稿案とステータスを一覧する
    python make_sns.py --keep       既存ファイルを一切書き換えずに不足分だけ作る

出力:
    sns/posts.json          全投稿案の管理ファイル（ステータスはここで持つ）
    sns/instagram/*.md
    sns/x/*.md
    sns/youtube/*.md
    sns/tiktok/*.md
"""

import importlib.util
import json
import os
import sys
import urllib.parse
from datetime import date

import fieldreview
import specs

OUT = "sns"
INDEX = os.path.join(OUT, "posts.json")
STORE = "products.json"
TODAY = date.today().isoformat()

# SNSごとの出力先と utm_source
CHANNELS = {
    "instagram": {"dir": "instagram", "source": "instagram", "label": "Instagram"},
    "x":         {"dir": "x",         "source": "x",         "label": "X"},
    "youtube":   {"dir": "youtube",   "source": "youtube",   "label": "YouTube Shorts"},
    "tiktok":    {"dir": "tiktok",    "source": "tiktok",    "label": "TikTok / Reels"},
}

STATUSES = ("draft", "approved", "posted")


# ------------------------------------------------------------------ 読み込み
def load_site_module():
    """build_site.py から記事と用途の定義を借りる。"""
    spec = importlib.util.spec_from_file_location("build_site", "build_site.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_site"] = mod
    spec.loader.exec_module(mod)
    return mod


def load_products():
    with open(STORE, encoding="utf-8") as f:
        products = json.load(f)
    for p in products:
        p["_spec"] = specs.extract(p)
    return [p for p in products if not p["_spec"]["block"]]


# ------------------------------------------------------------------ 事実の集計
def fmt_yen(n):
    return f"{int(n):,}円"


def stats_of(group, label, shown=None):
    """
    その集まりから、投稿に書ける数字だけを取り出す。
    読み取れた件数が全体の半分に満たない項目は、範囲を出さない。
    （一部の商品でしか読み取れていない値を、全体の傾向のように見せないため）
    """
    total = len(group)
    out = {"count": total, "shown": shown if shown is not None else total}

    def span(values, key, half=True):
        vals = sorted(v for v in values if v)
        if not vals:
            return
        if half and len(vals) * 2 < total:
            return                      # 半数未満しか読み取れていない
        out[key + "_min"], out[key + "_max"] = vals[0], vals[-1]
        out[key + "_n"] = len(vals)

    span([p["price"] for p in group], "price", half=False)

    if label == "ポータブル電源":
        span([p["_spec"]["wh"] for p in group], "wh")
        span([p["_spec"]["w"] for p in group], "w")
        span([p["_spec"]["kg"] for p in group], "kg")
        per = sorted(p["price"] / p["_spec"]["wh"]
                     for p in group if p["_spec"]["wh"] and p.get("price"))
        if per and len(per) * 2 >= total:
            out["per_min"], out["per_max"] = per[0], per[-1]
    else:
        span([p["_spec"]["liters"] for p in group], "l")
        span([p["_spec"]["kg"] for p in group], "kg")
        out["post_n"] = sum(1 for p in group if p["_spec"]["post"])
        out["anchor_n"] = sum(1 for p in group if p["_spec"]["anchor"])

    reviews = sorted(group, key=lambda p: -p["review_count"])
    if reviews:
        out["top_reviews"] = reviews[0]["review_count"]
    return out


def count_line(st):
    """件数の言い方。記事に出している件数と、条件に合う総数を分けて書く。"""
    if st["shown"] < st["count"]:
        return f"条件に合うのは{st['count']}件、記事で比べているのは{st['shown']}件。"
    return f"掲載は{st['count']}件。"


def _note_line(src):
    """出どころの注記。レビューは体験と楽天データを分けて書く。"""
    if src.get("_is_review"):
        return ("使用感は運営者が書いたものです。"
                "仕様と価格は楽天の商品情報から取得した値です。")
    return ("数値は楽天の商品情報から読み取ったものです。"
            "読み取れなかった項目はサイト上で「不明」と表示しています。")


def _facts_line(src, st, line):
    """数字の行。レビューは商品1件なので件数を言わない。"""
    if src.get("_is_review"):
        return f"この商品の仕様は {src['facts_short']}。" if src.get("facts_short") else ""
    return count_line(st) + (f"{line}。" if line else "")


def _short(text, limit=20):
    """画面テロップ用に短くする。"""
    if len(text) <= limit:
        return text
    return text.split("／")[0][:limit]


def spec_one(product, label):
    """商品1件ぶんの仕様。範囲ではなく実際の値を書く。"""
    sp = product["_spec"]
    parts = []
    if label == "ポータブル電源":
        if sp["wh"]:
            parts.append(f"{sp['wh']:,}Wh")
        if sp["w"]:
            parts.append(f"定格{sp['w']:,}W")
        if sp["kg"]:
            parts.append(f"{sp['kg']:g}kg")
        if sp["battery"]:
            parts.append(f"{sp['battery']}リチウム")
    else:
        size = specs.size_text(sp["size"])
        if size:
            parts.append(size)
        if sp["kg"]:
            parts.append(f"{sp['kg']:g}kg")
        if sp["install"]:
            parts.append(sp["install"])
    parts.append(f"{product['price']:,}円")
    return "／".join(parts)


def spec_line(st, label):
    """集計した数字を1行にする。取れなかった項目は書かない。"""
    parts = []
    if label == "ポータブル電源":
        if "wh_min" in st:
            parts.append(f"容量 {st['wh_min']:,}〜{st['wh_max']:,}Wh")
        if "w_min" in st:
            parts.append(f"定格 {st['w_min']:,}〜{st['w_max']:,}W")
        if "kg_min" in st:
            parts.append(f"重量 {st['kg_min']:g}〜{st['kg_max']:g}kg")
    else:
        if "l_min" in st:
            parts.append(f"容量 {st['l_min']}〜{st['l_max']}L")
        if "kg_min" in st:
            parts.append(f"重量 {st['kg_min']:g}〜{st['kg_max']:g}kg")
        if st.get("post_n"):
            parts.append(f"ポスト一体型 {st['post_n']}件")
    if "price_min" in st:
        parts.append(f"価格 {fmt_yen(st['price_min'])}〜{fmt_yen(st['price_max'])}")
    return "／".join(parts)


# ------------------------------------------------------------------ URL
def build_url(base_url, path, channel, campaign):
    """UTMパラメータを付けた記事URL。"""
    params = {
        "utm_source": CHANNELS[channel]["source"],
        "utm_medium": "social",
        "utm_campaign": campaign,
    }
    return f"{base_url}/{path}?" + urllib.parse.urlencode(params)


# ------------------------------------------------------------------ 文案
def hashtags(label, extra):
    """ハッシュタグ。元ページに根拠のある語だけを使う。"""
    base = {
        "ポータブル電源": ["#ポータブル電源", "#蓄電池"],
        "宅配ボックス": ["#宅配ボックス", "#置き配"],
    }.get(label, [])
    return base + [t for t in extra if t] + ["#369"]


def make_instagram(src, st, url):
    """Instagram。本文は事実の列挙と、サイトに載っている運営者の文章だけ。"""
    line = spec_line(st, src["label"])
    body = [
        src["lead"],
        "",
        _facts_line(src, st, line),
        "",
        src["pick"],
        "",
        _note_line(src),
    ]
    return {
        "title": src["sns_title"],
        "body": "\n".join(body),
        "cta": f"くわしい比較表はプロフィールのリンクから。\n{url}",
        "hashtags": hashtags(src["label"], src["tags"]),
    }


def make_x(src, st, url):
    """X。140字前後に収める。"""
    line = spec_line(st, src["label"])
    text = f"{src['sns_title']}\n\n{_facts_line(src, st, line)}\n\n{src['pick_short']}"
    return {"text": text, "url": url}


def _script(src, st, seconds):
    """
    動画の台本。最初の3秒で何の話か分かるようにする。
    数字はすべて集計した実データ。
    """
    line = spec_line(st, src["label"])
    hook = src["hook"]

    if seconds == 15:
        return [
            ("0:00-0:03", hook, _short(src["telop_hook"], 22)),
            ("0:03-0:08", src["lead_short"], src["telop_mid"]),
            ("0:08-0:12", _facts_line(src, st, line), _short(src["facts_short"] or line)),
            ("0:12-0:15", "くわしい比較は369で。", "369｜比較表はこちら"),
        ]
    return [
        ("0:00-0:03", hook, _short(src["telop_hook"], 22)),
        ("0:03-0:09", src["lead_short"], src["telop_mid"]),
        ("0:09-0:16", _facts_line(src, st, line), _short(src["facts_short"] or line)),
        ("0:16-0:24", src["pick"], src["telop_pick"]),
        ("0:24-0:28",
         "数値は楽天の商品情報から読み取ったものです。読み取れない項目は「不明」と表示しています。",
         "読み取れない項目は「不明」"),
        ("0:28-0:30", "くわしい比較は369で。", "369｜比較表はこちら"),
    ]


def fmt_script(rows):
    out = []
    for t, say, telop in rows:
        out.append(f"| {t} | {say} | {telop} |")
    return "\n".join(out)


def make_youtube(src, st, url):
    return {
        "title": src["sns_title"],
        "script_15": _script(src, st, 15),
        "script_30": _script(src, st, 30),
        "telops": [r[2] for r in _script(src, st, 30)],
        "cta": f"概要欄のリンクから比較表を見られます。\n{url}",
    }


def make_tiktok(src, st, url):
    return {
        "hook": src["hook"],
        "script_15": _script(src, st, 15),
        "script_30": _script(src, st, 30),
        "telops": [r[2] for r in _script(src, st, 30)],
        "cta": f"プロフィールのリンクから比較表へ。\n{url}",
    }


# ------------------------------------------------------------------ 元ネタ
def source_from_article(article, meta, seo, group, bs):
    """比較記事から、投稿に使う素材をまとめる。"""
    know, who = meta
    seo_title, _ = seo
    label = article["label"]
    tags = []
    if label == "ポータブル電源":
        tags = ["#車中泊", "#防災"] if "防災" in article["intro"] or "停電" in article["intro"] else []
    return {
        "kind": "article",
        "id": article["id"],
        "label": label,
        "path": f"articles/{article['id']}.html",
        "campaign": ("portable_power" if label == "ポータブル電源" else "delivery_box"),
        "sns_title": seo_title.split("｜")[0],
        "hook": f"{article['title']}、どれを選ぶ？",
        "telop_hook": article["title"],
        "lead": article["intro"],
        "lead_short": _first_sentence(article["intro"]),
        "pick": article["pick"],
        "pick_short": _first_sentence(article["pick"]),
        "telop_mid": _telop(article["intro"]),
        "telop_pick": _telop(article["pick"]),
        "angle": know,
        "for_whom": who,
        "tags": tags,
        "facts_short": "",
    }


def source_from_use(use, seo, group):
    """用途ページから素材をまとめる。用途ごとに切り口が変わる。"""
    seo_title, _ = seo
    tag_map = {
        "genba": ["#現場仕事", "#電動工具"],
        "diy": ["#DIY"],
        "bosai": ["#防災", "#停電対策"],
        "shachuhaku": ["#車中泊"],
        "kateiyo": ["#家庭備蓄"],
        "cospa": ["#コスパ"],
        "box-post": ["#ポスト一体型"],
        "box-anchor": ["#戸建て"],
        "box-multi": ["#置き配"],
        "box-heavy": ["#戸建て"],
    }
    return {
        "kind": "use",
        "id": use["id"],
        "label": use["label"],
        "path": f"use/{use['id']}.html",
        "campaign": ("portable_power" if use["label"] == "ポータブル電源" else "delivery_box"),
        "sns_title": seo_title.split("｜")[0],
        "hook": f"{use['title']}なら、どれ？",
        "telop_hook": use["title"],
        "lead": use["lead"],
        "lead_short": _first_sentence(use["lead"]),
        "pick": f"判定の条件は「{use['rule']}」。この条件に合うものだけを集めています。",
        "pick_short": f"条件は{use['rule']}。",
        "telop_mid": _telop(use["lead"]),
        "telop_pick": use["rule"],
        "angle": f"{use['rule']} で絞り込んだ商品",
        "for_whom": use["title"],
        "tags": tag_map.get(use["id"], []),
        "facts_short": "",
    }


def source_from_review(product, review):
    """実使用レビューから素材をまとめる。運営者が書いたことだけを使う。"""
    slug = fieldreview.slug_of(product["code"])
    name = product["name"][:30]
    good = review["good"][0] if review["good"] else ""
    bad = review["bad"][0] if review["bad"] else ""
    used = "・".join(x for x in (review["place"], review["duration"]) if x)
    return {
        "kind": "review",
        "id": f"review-{slug}",
        "label": product["label"],
        "path": f"review/{slug}.html",
        "campaign": "field_review",
        "sns_title": f"{name}を実際に使ってみた",
        "hook": f"{name}、実際に使ってみました",
        "telop_hook": "実際に使ってみた",
        "lead": f"{used}使った記録です。" if used else "実際に使った記録です。",
        "lead_short": f"{used}使いました。" if used else "実際に使いました。",
        "pick": (f"良かった点：{good}" if good else "") +
                (f"／気になった点：{bad}" if bad else ""),
        "pick_short": good or bad or "",
        "telop_mid": used or "実際に使用",
        "telop_pick": good[:18] if good else "",
        "angle": "運営者が実際に使った記録",
        "for_whom": review["recommend_for"],
        "tags": ["#実際に使ってみた"],
        "facts_short": spec_one(product, product["label"]),
        "_is_review": True,
    }


def _first_sentence(text):
    for sep in ("。", "．"):
        if sep in text:
            return text.split(sep)[0] + sep
    return text[:40]


def _telop(text):
    """画面に出す短い文字。20字くらいまで。"""
    s = _first_sentence(text).rstrip("。")
    return s[:20]


# ------------------------------------------------------------------ 書き出し
def md_instagram(post, src, status):
    c = post["content"]
    return f"""# Instagram投稿案

- 元ページ: [{src['sns_title']}]({post['url_plain']})
- 切り口: {src['angle']}
- ステータス: **{status}**
- PR表示: {post['pr']}
- 生成日: {post['generated']}

## タイトル
{c['title']}

## 本文
{c['body']}

## CTA
{c['cta']}

## ハッシュタグ候補
{' '.join(c['hashtags'])}

---
投稿前に確認すること

- [ ] PR表示を入れたか（楽天アフィリエイトのリンクに飛ばすため必要）
- [ ] 文中の数字が元ページと合っているか
- [ ] 使っていない商品の使用感を書いていないか
"""


def md_x(post, src, status):
    c = post["content"]
    return f"""# X投稿案

- 元ページ: [{src['sns_title']}]({post['url_plain']})
- 切り口: {src['angle']}
- ステータス: **{status}**
- PR表示: {post['pr']}
- 生成日: {post['generated']}

## 投稿文
```
{c['text']}
```

## 記事URL
{c['url']}

文字数の目安: 本文 {len(c['text'])}字（URLは別枠で約23字）

---
投稿前に確認すること

- [ ] PR表示を入れたか
- [ ] 文中の数字が元ページと合っているか
"""


def md_video(post, src, status, kind):
    c = post["content"]
    head = "YouTube Shorts" if kind == "youtube" else "TikTok / Reels"
    hook = c.get("hook") or c.get("title")
    return f"""# {head} 投稿案

- 元ページ: [{src['sns_title']}]({post['url_plain']})
- 切り口: {src['angle']}
- ステータス: **{status}**
- PR表示: {post['pr']}
- 生成日: {post['generated']}

## {'タイトル' if kind == 'youtube' else '冒頭3秒のフック'}
{hook}

## 15秒版

| 時間 | 読み上げ | 画面テロップ |
|---|---|---|
{fmt_script(c['script_15'])}

## 30秒版

| 時間 | 読み上げ | 画面テロップ |
|---|---|---|
{fmt_script(c['script_30'])}

## 画面テロップ一覧
{chr(10).join('- ' + t for t in c['telops'])}

## CTA
{c['cta']}

---
投稿前に確認すること

- [ ] PR表示を入れたか
- [ ] 読み上げの数字が元ページと合っているか
- [ ] 撮影した映像が、話している商品のものか
- [ ] 使っていない商品を使ったように見せていないか
"""


# ------------------------------------------------------------------ 本体
def generate(sources, products_by_source, base_url, keep=False):
    old = {}
    if os.path.exists(INDEX):
        try:
            with open(INDEX, encoding="utf-8") as f:
                old = {p["id"]: p for p in json.load(f).get("posts", [])}
        except Exception:
            print(f"{INDEX} が読めませんでした。新しく作ります。", file=sys.stderr)

    os.makedirs(OUT, exist_ok=True)
    for ch in CHANNELS.values():
        os.makedirs(os.path.join(OUT, ch["dir"]), exist_ok=True)

    posts, skipped, written = [], 0, 0

    for src in sources:
        group = products_by_source.get(src["id"], [])
        shown = min(len(group), 10) if src["kind"] == "article" else len(group)
        st = (stats_of(group, src["label"], shown) if group
              else {"count": 0, "shown": 0})
        if not group and src["kind"] != "review":
            continue

        for ch_key, ch in CHANNELS.items():
            post_id = f"{src['id']}--{ch_key}"
            before = old.get(post_id)
            status = before["status"] if before else "draft"

            # 人が承認したものは触らない
            if before and status in ("approved", "posted"):
                posts.append(before)
                skipped += 1
                continue
            if keep and before:
                posts.append(before)
                skipped += 1
                continue

            url = build_url(base_url, src["path"], ch_key, src["campaign"])
            maker = {"instagram": make_instagram, "x": make_x,
                     "youtube": make_youtube, "tiktok": make_tiktok}[ch_key]
            content = maker(src, st, url)

            post = {
                "id": post_id,
                "channel": ch_key,
                "channel_label": ch["label"],
                "status": status,
                "pr": "要PR表示（楽天アフィリエイトの記事へ誘導するため）",
                "source_kind": src["kind"],
                "source_id": src["id"],
                "source_title": src["sns_title"],
                "source_path": src["path"],
                "angle": src["angle"],
                "url": url,
                "url_plain": f"{base_url}/{src['path']}",
                "file": f"{ch['dir']}/{src['id']}.md",
                "generated": TODAY,
                "content": content,
            }
            posts.append(post)

            md = {"instagram": md_instagram, "x": md_x}.get(ch_key)
            text = (md(post, src, status) if md
                    else md_video(post, src, status, ch_key))
            with open(os.path.join(OUT, post["file"]), "w", encoding="utf-8") as f:
                f.write(text)
            written += 1

    posts.sort(key=lambda p: (p["source_kind"], p["source_id"], p["channel"]))
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump({"generated": TODAY, "base_url": base_url,
                   "note": "ステータスは draft / approved / posted。"
                           "approved と posted のものは作り直しません。"
                           "自動投稿はしません。",
                   "posts": posts}, f, ensure_ascii=False, indent=1)
    return posts, written, skipped


def show_list():
    if not os.path.exists(INDEX):
        sys.exit(f"{INDEX} がありません。先に python make_sns.py を実行してください。")
    with open(INDEX, encoding="utf-8") as f:
        data = json.load(f)
    posts = data["posts"]
    from collections import Counter
    c = Counter(p["status"] for p in posts)
    print(f"投稿案 {len(posts)}件（生成日 {data['generated']}）\n")
    for s in STATUSES:
        print(f"  {s:<9} {c.get(s, 0):>3}件")
    print("\n--- 一覧 ---")
    for p in posts:
        print(f"  [{p['status']:<8}] {p['channel_label']:<16} {p['source_title'][:34]}")


def main():
    if "--list" in sys.argv:
        return show_list()

    bs = load_site_module()
    products = load_products()
    reviews, _ = fieldreview.load_reviews(".")
    base_url = bs.BASE_URL

    sources, by_source = [], {}

    # 比較記事
    for a in bs.ARTICLES:
        group = [p for p in products
                 if p["label"] == a["label"]
                 and bs.axis_value(p, a)
                 and a["min"] <= bs.axis_value(p, a) < a["max"]]
        group = bs.dedupe(group, a)
        if len(group) < 4:
            continue
        src = source_from_article(a, bs.ARTICLE_META.get(a["id"], ("", "")),
                                  bs.ARTICLE_SEO.get(a["id"], (a["title"], "")),
                                  group, bs)
        sources.append(src)
        by_source[src["id"]] = group

    # 用途ページ
    for u in bs.USES:
        group = [p for p in products
                 if p["label"] == u["label"] and u["match"](p["_spec"], p)]
        if not group:
            continue
        src = source_from_use(u, bs.USE_SEO.get(u["id"], (u["title"], "")), group)
        sources.append(src)
        by_source[src["id"]] = group

    # 実使用レビュー（書かれているものだけ）
    for p in products:
        review = reviews.get(p["code"])
        if not review:
            continue
        src = source_from_review(p, review)
        sources.append(src)
        by_source[src["id"]] = [p]

    posts, written, skipped = generate(sources, by_source, base_url,
                                       keep="--keep" in sys.argv)

    print(f"元ページ {len(sources)}件から、投稿案 {len(posts)}件を管理しています。")
    print(f"  今回書き出した: {written}件")
    if skipped:
        print(f"  触らなかった  : {skipped}件（approved / posted、または --keep 指定）")
    print(f"\n{OUT}/ に保存しました。")
    for ch in CHANNELS.values():
        n = len([p for p in posts if p["channel_label"] == ch["label"]])
        print(f"  {ch['dir']}/  {n}件")
    print(f"  posts.json  管理ファイル（ステータスはここで変更する）")
    print("\nすべて draft です。自動投稿はしません。"
          "内容を読んで直してから、手で投稿してください。")


if __name__ == "__main__":
    main()
