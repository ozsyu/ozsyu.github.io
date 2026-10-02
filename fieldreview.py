#!/usr/bin/env python3
"""
実使用レビューの読み込みと検証（369）

運営者が実際に使った商品についてのみ、使用感を記録する。
文章は人が書いたものだけを読み込み、このファイルは一切の文章生成をしない。

扱うファイル:
    reviews.json            実使用レビュー（運営者が書く）
    rakuten_summaries.json  楽天レビューを読んでまとめた文章（運営者が書く）
    photos/                 運営者が撮影した写真

掲載の条件:
    used が true で、使用場所・使用期間・良かった点・気になった点のうち
    ひとつでも書かれていること。何も書かれていないものは出さない。
"""

import json
import os

REVIEWS = "reviews.json"
SUMMARIES = "rakuten_summaries.json"
PHOTO_DIR = "photos"

# reviews.json に書ける項目。ここに無いキーは無視する。
FIELDS = {
    "code": "商品コード",
    "name": "商品名（確認用。表示には楽天の商品名を使う）",
    "used": "実際に使ったか true/false",
    "place": "使用場所",
    "duration": "使用期間",
    "purpose": "使用用途",
    "good": "良かった点（文字列または配列）",
    "bad": "気になった点（文字列または配列）",
    "recommend_for": "どんな人に向いているか",
    "photos": "写真 [{file, alt}]",
    "date": "レビュー日 YYYY-MM-DD",
    "rating": "運営者の5段階評価（任意。書かなければ星は出ない）",
}

# これらのどれかが書かれていれば、記事として成立しているとみなす
SUBSTANCE_FIELDS = ("place", "duration", "purpose", "good", "bad", "recommend_for")


def _as_list(value):
    """文字列でも配列でも配列に揃える。空のものは落とす。"""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value if str(v).strip()]


def _clean_photos(entry, base_dir):
    """
    実在する写真だけを返す。
    ファイルが無いものは黙って捨てる（存在しない画像URLを出さないため）。
    """
    out = []
    for photo in entry.get("photos") or []:
        if isinstance(photo, str):
            photo = {"file": photo}
        name = (photo.get("file") or "").strip()
        if not name:
            continue
        path = os.path.join(base_dir, PHOTO_DIR, name)
        if not os.path.exists(path):
            continue
        alt = (photo.get("alt") or "").strip()
        out.append({"file": name, "alt": alt, "path": path})
    return out


def load_reviews(base_dir=".", quiet=False):
    """
    実使用レビューを読む。
    返り値: ({商品コード: レビュー}, [問題の説明])
    """
    path = os.path.join(base_dir, REVIEWS)
    if not os.path.exists(path):
        return {}, []

    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return {}, [f"{REVIEWS} が読めません: {e}"]

    # 配列でも辞書でも受ける
    entries = raw if isinstance(raw, list) else [
        dict(v, code=k) for k, v in raw.items() if isinstance(v, dict)
    ]

    out, issues = {}, []
    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            issues.append(f"{i}件目: 形式が違います")
            continue

        code = (entry.get("code") or "").strip()
        if not code:
            issues.append(f"{i}件目: 商品コードがありません")
            continue
        if entry.get("used") is not True:
            # used が true でないものは、存在しないものとして扱う
            continue

        review = {
            "code": code,
            "name": (entry.get("name") or "").strip(),
            "place": (entry.get("place") or "").strip(),
            "duration": (entry.get("duration") or "").strip(),
            "purpose": (entry.get("purpose") or "").strip(),
            "good": _as_list(entry.get("good")),
            "bad": _as_list(entry.get("bad")),
            "recommend_for": (entry.get("recommend_for") or "").strip(),
            "date": (entry.get("date") or "").strip(),
            "photos": _clean_photos(entry, base_dir),
            "rating": None,
        }

        # 評価は運営者が書いた場合だけ。書いていなければ星を出さない
        rating = entry.get("rating")
        if isinstance(rating, (int, float)) and 1 <= rating <= 5:
            review["rating"] = float(rating)

        filled = [k for k in SUBSTANCE_FIELDS
                  if (review[k] if isinstance(review[k], list) else review[k].strip())]
        if not filled:
            issues.append(f"{code}: used=true ですが中身が空です。掲載しません")
            continue

        missing = [k for k in SUBSTANCE_FIELDS
                   if not (review[k] if isinstance(review[k], list) else review[k].strip())]
        if missing and not quiet:
            labels = "／".join(FIELDS[k].split("（")[0] for k in missing)
            issues.append(f"{code}: 未記入あり（{labels}）。その欄は表示しません")

        # 写真があるのに alt が無い場合は知らせる
        for photo in review["photos"]:
            if not photo["alt"]:
                issues.append(f"{code}: 写真 {photo['file']} に alt がありません")

        out[code] = review

    return out, issues


def load_summaries(base_dir="."):
    """楽天レビューを読んでまとめた文章。運営者の体験とは別物。"""
    path = os.path.join(base_dir, SUMMARIES)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if ":" in k and isinstance(v, str) and v.strip()}
    except Exception:
        return {}


def slug_of(code):
    """商品コードからファイル名を作る。"""
    return code.replace(":", "-").replace("/", "-")


def has_review(reviews, code):
    return code in reviews


def copy_photos(reviews, out_dir):
    """掲載する写真だけを出力先にコピーする。"""
    import shutil
    if not reviews:
        return 0
    dest = os.path.join(out_dir, PHOTO_DIR)
    os.makedirs(dest, exist_ok=True)
    n = 0
    for review in reviews.values():
        for photo in review["photos"]:
            shutil.copy(photo["path"], os.path.join(dest, photo["file"]))
            n += 1
    return n
