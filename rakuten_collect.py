#!/usr/bin/env python3
"""
楽天 商品収集スクリプト（フェーズ1）

決めたジャンル・キーワードの商品を楽天商品検索APIで集めて
products.json に貯める。実行するたびに追記され、同じ商品は
新しい情報で上書きされる。

使い方:
    python rakuten_collect.py            収集する
    python rakuten_collect.py --dump     楽天の生データを見る（不具合調査用）
    python rakuten_collect.py --list     いま貯まっている商品を一覧する

環境変数は rakuten_research.py と同じ4つ。
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

APP_ID = os.environ.get("RAKUTEN_APP_ID", "")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
ORIGIN = os.environ.get("RAKUTEN_ORIGIN", "")

BASE = "https://openapi.rakuten.co.jp"
SEARCH_API = f"{BASE}/ichibams/api/IchibaItem/Search/20260701"

STORE = "products.json"
INTERVAL = 1.5          # リクエストの間隔（秒）
PAGES_PER_TARGET = 5    # 1条件あたり何ページ取るか（1ページ30件）

# ------------------------------------------------------------------
# 集める対象。ここを増やせば守備範囲が広がる。
#   label   … サイト上の分類名
#   keyword … 検索語
#   genreId … ジャンルで絞る（0なら絞らない）
#   minPrice… この価格未満は無視する（安すぎる周辺小物を除くため）
# ------------------------------------------------------------------
TARGETS = [
    {"label": "ポータブル電源", "keyword": "ポータブル電源",
     "genreId": 100890, "minPrice": 30000},
    {"label": "ポータブル電源", "keyword": "ポータブル電源 ソーラーパネル",
     "genreId": 100890, "minPrice": 50000},
    {"label": "宅配ボックス", "keyword": "宅配ボックス",
     "genreId": 100880, "minPrice": 8000},
    {"label": "宅配ボックス", "keyword": "宅配ボックス ポスト 一体型",
     "genreId": 100880, "minPrice": 10000},
]


def call(params, retries=3):
    """APIを1回叩く。"""
    params = {k: v for k, v in params.items() if v is not None and v != ""}
    params.update({
        "format": "json",
        "formatVersion": 2,
        "applicationId": APP_ID,
        "accessKey": ACCESS_KEY,
    })
    if AFFILIATE_ID:
        params["affiliateId"] = AFFILIATE_ID

    url = SEARCH_API + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "rakuten-collect/1.0"}
    if ORIGIN:
        headers["Origin"] = ORIGIN
        headers["Referer"] = ORIGIN.rstrip("/") + "/"

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code == 429:
                print("    混雑中。10秒待ちます...", file=sys.stderr)
                time.sleep(10)
                continue
            if e.code in (400, 403, 404):
                print(f"\n    エラー {e.code}: {body}", file=sys.stderr)
                return None
            print(f"    再試行 {attempt + 1}/{retries} (HTTP {e.code})", file=sys.stderr)
        except Exception as e:
            print(f"    再試行 {attempt + 1}/{retries} ({e})", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    return None


def pick(item, *names, default=""):
    """キー名が変わっても拾えるように候補を順に試す。"""
    for n in names:
        if isinstance(item, dict) and item.get(n) not in (None, ""):
            return item[n]
    return default


def to_int(value, default=0):
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def normalize(raw, label):
    """楽天の1件を、こちらで使う形に整える。"""
    item = raw.get("Item", raw) if isinstance(raw, dict) else {}
    code = pick(item, "itemCode")
    name = pick(item, "itemName", "nameJa")
    if not code or not name:
        return None

    images = []
    for key in ("mediumImageUrls", "smallImageUrls", "imageUrls"):
        for entry in item.get(key) or []:
            url = entry if isinstance(entry, str) else entry.get("imageUrl", "")
            if url:
                images.append(url.split("?")[0])
        if images:
            break

    return {
        "label": label,
        "code": code,
        "name": name.strip(),
        "catch": pick(item, "catchcopy").strip(),
        "caption": pick(item, "itemCaption")[:2000],
        "price": to_int(pick(item, "itemPrice")),
        "shop": pick(item, "shopName"),
        "review_count": to_int(pick(item, "reviewCount")),
        "review_average": float(to_int(pick(item, "reviewAverage"), 0)) or
                          float(pick(item, "reviewAverage", default=0) or 0),
        "url": pick(item, "affiliateUrl", "itemUrl"),
        "images": images[:3],
        "fetched": time.strftime("%Y-%m-%d"),
    }


def load_store():
    if not os.path.exists(STORE):
        return {}
    try:
        with open(STORE, encoding="utf-8") as f:
            return {p["code"]: p for p in json.load(f)}
    except Exception:
        print("既存のproducts.jsonが読めませんでした。新規で作ります。", file=sys.stderr)
        return {}


def save_store(store):
    items = sorted(store.values(), key=lambda p: -p["review_count"])
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    return len(items)


def collect():
    store = load_store()
    before = len(store)

    for target in TARGETS:
        print(f"\n▼ {target['label']} / 「{target['keyword']}」")
        for page in range(1, PAGES_PER_TARGET + 1):
            data = call({
                "keyword": target["keyword"],
                "genreId": target["genreId"] or None,
                "minPrice": target["minPrice"],
                "hits": 30,
                "page": page,
                "sort": "-reviewCount",
            })
            if not data:
                break

            items = data.get("Items") or data.get("items") or []
            if not items:
                print(f"  {page}ページ目: 該当なし。ここで打ち切ります。")
                break

            added = 0
            for raw in items:
                product = normalize(raw, target["label"])
                if product:
                    if product["code"] not in store:
                        added += 1
                    store[product["code"]] = product
            print(f"  {page}ページ目: {len(items)}件取得（うち新規 {added}件）")
            time.sleep(INTERVAL)

    total = save_store(store)
    print(f"\n合計 {total}件を {STORE} に保存しました（新たに {total - before}件増えました）")

    by_label = {}
    for p in store.values():
        by_label[p["label"]] = by_label.get(p["label"], 0) + 1
    print("\n分類ごとの件数:")
    for label, n in sorted(by_label.items(), key=lambda x: -x[1]):
        print(f"  {label}: {n}件")


def show_list():
    store = load_store()
    if not store:
        sys.exit("まだ商品がありません。先に収集してください。")
    items = sorted(store.values(), key=lambda p: -p["review_count"])
    print(f"{len(items)}件。レビューの多い順に上位40件:\n")
    for p in items[:40]:
        print(f"  {p['price']:>8,}円  レビュー{p['review_count']:>6}  "
              f"[{p['label']}] {p['name'][:45]}")


def main():
    if not APP_ID or not ACCESS_KEY:
        sys.exit("RAKUTEN_APP_ID と RAKUTEN_ACCESS_KEY を設定してください。")

    if "--list" in sys.argv:
        return show_list()

    if "--dump" in sys.argv:
        data = call({"keyword": "ポータブル電源", "hits": 1})
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
        return

    if not ORIGIN:
        print("警告: RAKUTEN_ORIGIN が未設定です。403になる可能性があります。\n",
              file=sys.stderr)
    collect()


if __name__ == "__main__":
    main()
