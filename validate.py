#!/usr/bin/env python3
"""
商品データ検証（369）

products.json の仕様抽出がどれくらい確かかを調べ、要確認の商品を一覧にする。
サイトは生成しない。確認だけしたいときに使う。

区分:
    WARNING … 確認したほうがよいが、掲載はできる
    BLOCK   … 中心となる仕様が確定できず、掲載を止める

使い方:
    python validate.py              要約を表示する
    python validate.py --all        要確認の商品をすべて表示する
    python validate.py --warn       WARNING も個別に表示する
    python validate.py --csv        review_needed.csv に書き出す
"""

import csv
import json
import os
import re
import sys
from collections import Counter

import specs

STORE = "products.json"
OUT_CSV = "review_needed.csv"
KEYS = {"ポータブル電源": ("wh", "w", "kg"), "宅配ボックス": ("liters", "kg")}


def load():
    if not os.path.exists(STORE):
        sys.exit(f"{STORE} が見つかりません。rakuten_collect.py を先に実行してください。")
    with open(STORE, encoding="utf-8") as f:
        return json.load(f)


def bar(n, total, width=26):
    return "█" * (round(n / total * width) if total else 0) + "·" * (
        width - (round(n / total * width) if total else 0))


def cross_check(products):
    """商品名に書かれた容量と、採用した値が食い違っていないか。"""
    ok, bad = 0, []
    for p in products:
        if p["label"] != "ポータブル電源":
            continue
        shown = [int(m.group(1)) for m in re.finditer(r"(\d{3,5})\s*Wh", p["name"], re.I)]
        got = p["_spec"]["wh"]
        if not shown or not got:
            continue
        if any(abs(got - v) / max(got, v) <= 0.03 for v in shown):
            ok += 1
        else:
            bad.append((p, shown, got))
    return ok, bad


def main():
    products = load()
    for p in products:
        p["_spec"] = specs.extract(p)

    blocked = [p for p in products if p["_spec"]["block"]]
    warned = [p for p in products
              if not p["_spec"]["block"]
              and any(i["level"] == specs.WARNING for i in p["_spec"]["issues"])]
    clean = [p for p in products
             if not p["_spec"]["block"] and p not in warned]

    print(f"商品 {len(products)}件を調べました。\n")
    print("=" * 60)
    print(" 検証結果")
    print("=" * 60)
    print(f"  正常      {len(clean):>4}件  問題なし")
    print(f"  WARNING   {len(warned):>4}件  確認推奨だが掲載する")
    print(f"  BLOCK     {len(blocked):>4}件  仕様が確定できず掲載停止")
    print(f"  掲載される商品 {len(products) - len(blocked)}件")

    print("\n" + "=" * 60)
    print(" 確かな値が取れている割合（掲載する商品のうち）")
    print("=" * 60)
    live = [p for p in products if not p["_spec"]["block"]]
    for label, keys in KEYS.items():
        items = [p for p in live if p["label"] == label]
        if not items:
            continue
        print(f"\n【{label}】{len(items)}件")
        for k in keys:
            n = sum(1 for p in items if p["_spec"][k] is not None)
            print(f"  {specs.FIELD_LABEL[k]:<10} {bar(n, len(items))} "
                  f"{n:>3}/{len(items)} ({n * 100 // len(items)}%)")

    ok, bad = cross_check(products)
    print("\n" + "=" * 60)
    print(" 商品名の容量と、採用した値の突き合わせ")
    print("=" * 60)
    print(f"  一致 {ok}件 ／ 不一致 {len(bad)}件")
    for p, shown, got in bad[:10]:
        print(f"   × 採用{got}Wh / 商品名{shown}  {p['name'][:44]}")

    print("\n" + "=" * 60)
    print(f" BLOCK（掲載停止）{len(blocked)}件")
    print("=" * 60)
    if not blocked:
        print("  ありません。")
    for p in blocked:
        print(f"\n  {p['code']}  {p['price']:,}円")
        print(f"  {p['name'][:60]}")
        for i in p["_spec"]["issues"]:
            if i["level"] == specs.BLOCK:
                print(f"    → {specs.issue_text(i)}")

    reasons = Counter(specs.FIELD_LABEL.get(i["field"], i["field"])
                      for p in warned for i in p["_spec"]["issues"]
                      if i["level"] == specs.WARNING)
    print("\n" + "=" * 60)
    print(f" WARNING（掲載する）{len(warned)}件の内訳")
    print("=" * 60)
    for k, v in reasons.most_common():
        print(f"  {k:<12} {v}件")

    if "--warn" in sys.argv or "--all" in sys.argv:
        show = warned if "--all" in sys.argv else warned[:15]
        print(f"\n--- WARNING の内訳（{len(show)}件）---")
        for p in show:
            print(f"\n  {p['code']}  {p['price']:,}円")
            print(f"  {p['name'][:60]}")
            for i in p["_spec"]["issues"]:
                if i["level"] == specs.WARNING:
                    print(f"    → {specs.issue_text(i)}")
        if len(show) < len(warned):
            print(f"\n  （残り {len(warned) - len(show)}件。--all ですべて表示）")

    if "--csv" in sys.argv:
        rows = []
        for p in products:
            for i in p["_spec"]["issues"]:
                rows.append({
                    "区分": i["level"], "商品コード": p["code"], "分類": p["label"],
                    "項目": specs.FIELD_LABEL.get(i["field"], i["field"]),
                    "内容": i["message"],
                    "掲載": "停止" if p["_spec"]["block"] else "掲載する",
                    "価格": p["price"], "商品名": p["name"][:80], "URL": p["url"],
                })
        rows.sort(key=lambda r: (r["区分"] != specs.BLOCK, r["項目"]))
        with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["区分", "商品コード", "分類", "項目",
                                              "内容", "掲載", "価格", "商品名", "URL"])
            w.writeheader()
            w.writerows(rows)
        print(f"\n{OUT_CSV} に {len(rows)}行を書き出しました。")

    print("\n表示価格は楽天APIの現在価格です。"
          "商品名の割引価格との差は記録するだけで、掲載は止めていません。")


if __name__ == "__main__":
    main()
