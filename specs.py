#!/usr/bin/env python3
"""
商品仕様の抽出と検証（369）

楽天APIが返す「商品名」「キャッチコピー」「商品説明」の3つから仕様の候補を集め、
突き合わせて1つの値に決める。決められない場合は推測せず「不明」とする。

方針:
  - 推測しない。読み取れないものは None（＝不明）。
  - 商品名を最優先する。ショップが最も正確に書く場所であるため。
  - 意味の違う数値は矛盾として扱わない。
      定格出力と最大出力、本体容量と拡張容量は別物として分けて読む。
  - 価格は楽天APIの現在価格を基準とする。
      商品名に書かれた割引後価格との差は記録するが、掲載は止めない。

要確認の区分:
  WARNING … 確認したほうがよいが、掲載はできる
  BLOCK   … 中心となる仕様が特定できず、掲載を止める

build_site.py と validate.py の両方から読み込まれる。
"""

import re
from collections import Counter

WARNING = "WARNING"
BLOCK = "BLOCK"

FIELD_LABEL = {"wh": "容量(Wh)", "w": "定格出力(W)", "kg": "重量(kg)",
               "liters": "容量(L)", "price": "価格"}

# その分類で「これが無いと比較にならない」中心の項目
CORE_FIELD = {"ポータブル電源": "wh", "宅配ボックス": None}


# ------------------------------------------------------------------ 取り出し
def _find(patterns, text):
    """該当する数値を (値, 位置) で拾う。"""
    found = []
    if not text:
        return found
    for pat, mul in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                found.append((round(float(m.group(1)) * mul, 1), m.start()))
            except (TypeError, ValueError):
                continue
    return found


def _near(text, pos, words, span=18):
    """数値の直前に特定の語があるか。"""
    before = text[max(0, pos - span):pos]
    return any(w in before for w in words)


def _near_after(text, pos, words, span=16):
    """数値の直後に特定の語があるか。「16660Wh容量拡張」のような書き方を拾う。"""
    after = text[pos:pos + span]
    return any(w in after for w in words)


WH_PATTERNS = [
    (r"(\d{1,2}(?:\.\d+)?)\s*kWh", 1000),
    (r"(\d{3,5})\s*Wh", 1),
]
# 拡張バッテリーを足したときの容量。本体容量ではない。
# 「最大16660Wh容量拡張」のように数値の後ろに書かれることが多いので前後とも見る。
WH_EXPAND_BEFORE = ("拡張", "増設", "追加", "エクストラ", "最大容量", "合計",
                    "最大", "総容量", "まで")
WH_EXPAND_AFTER = ("容量拡張", "まで拡張", "へ拡張", "に拡張", "まで容量", "拡張",
                   "倍増", "増設", "合計")

W_RATED_PATTERNS = [
    (r"(?:定格出力|定格|AC出力|連続出力|出力)[^\d]{0,12}?(\d{3,4})\s*W(?!h)", 1),
]
W_BARE_PATTERNS = [
    (r"(\d{3,4})\s*W(?!h)", 1),
]
# 瞬間的にしか出ない値。定格出力と混ぜない
W_PEAK_WORDS = ("瞬間最大", "最大出力", "サージ", "ピーク", "X-Boost", "瞬間", "起動時",
                "最大", "ブースト")
# 出力ではなく入力・充電の話
W_INPUT_WORDS = ("ソーラー", "入力", "充電", "パネル", "ソーラーパネル", "急速充電")

KG_PATTERNS = [
    (r"(?:本体重量|重[さ量])[^\d]{0,10}?(\d{1,3}(?:\.\d+)?)\s*kg", 1),
    (r"約\s*(\d{1,3}(?:\.\d+)?)\s*kg", 1),
]
KG_BARE_PATTERNS = [
    (r"(\d{1,3}(?:\.\d+)?)\s*kg", 1),
]
# 重量ではない「kg」
KG_EXCLUDE_WORDS = ("耐荷重", "積載", "耐重", "荷重", "対応重量", "まで", "最大")

L_PATTERNS = [
    (r"(?:有効内寸容量|収納容量|容量)[^\d]{0,10}?(\d{2,3})\s*(?:L|ℓ|リットル)", 1),
    (r"(\d{2,3})\s*(?:L|ℓ|リットル)(?:の大容量|サイズ|タイプ|以上|対応)", 1),
]
L_BARE_PATTERNS = [
    (r"(\d{2,3})\s*L(?![a-zA-Z])", 1),
]


def _collect(product, field):
    """出典ごとに候補値を集める。意味の違う数値はここで切り分ける。"""
    texts = {
        "name": product.get("name") or "",
        "catch": product.get("catch") or "",
        "caption": product.get("caption") or "",
    }
    out = {}

    for src, text in texts.items():
        if field == "wh":
            hits = _find(WH_PATTERNS, text)
            # 拡張時の容量は本体容量ではないので、別物として外す
            hits = [(v, p) for v, p in hits
                    if not _near(text, p, WH_EXPAND_BEFORE, span=12)
                    and not _near_after(text, p, WH_EXPAND_AFTER, span=18)]

        elif field == "w":
            hits = _find(W_RATED_PATTERNS, text)
            # 「最大出力1500W」のような書き方を定格と取り違えない
            hits = [(v, p) for v, p in hits if not _near(text, p, W_PEAK_WORDS)]
            hits = [(v, p) for v, p in hits if not _near(text, p, W_INPUT_WORDS)]
            if src == "name" and not hits:
                bare = _find(W_BARE_PATTERNS, text)
                bare = [(v, p) for v, p in bare
                        if not _near(text, p, W_PEAK_WORDS + W_INPUT_WORDS)]
                if len({v for v, _ in bare}) == 1:
                    hits = bare

        elif field == "kg":
            hits = _find(KG_PATTERNS, text)
            hits = [(v, p) for v, p in hits if not _near(text, p, KG_EXCLUDE_WORDS)]
            if src == "name" and not hits:
                bare = _find(KG_BARE_PATTERNS, text)
                bare = [(v, p) for v, p in bare
                        if not _near(text, p, KG_EXCLUDE_WORDS)]
                if len({v for v, _ in bare}) == 1:
                    hits = bare

        elif field == "liters":
            hits = _find(L_PATTERNS, text)
            if src == "name" and not hits:
                bare = _find(L_BARE_PATTERNS, text)
                if len({v for v, _ in bare}) == 1:
                    hits = bare
        else:
            hits = []

        out[src] = [v for v, _ in hits]
    return out


# ------------------------------------------------------------------ もっともらしさ
def _plausible(field, value, label, known):
    wh = known.get("wh")
    if field == "wh":
        return 100 <= value <= 30000
    if field == "liters":
        return 20 <= value <= 300
    if field == "w":
        if not 100 <= value <= 8000:
            return False
        if wh and not (wh * 0.25 <= value <= wh * 3.0):
            return False
        return True
    if field == "kg":
        if label == "ポータブル電源":
            if not 1 <= value <= 80:
                return False
            if wh and not (wh / 200 <= value <= wh / 20):
                return False
            return True
        return 3 <= value <= 150
    return True


def _close(a, b, tol=0.03):
    if a == 0 or b == 0:
        return a == b
    return abs(a - b) / max(a, b) <= tol


def _fmt(v):
    return f"{v:g}"


def _fmt_list(vals):
    return "/".join(f"{v:g}" for v in vals)


# ------------------------------------------------------------------ 決定
def decide(product, field, label, known):
    """
    候補を突き合わせて値を1つ決める。
    返り値: (値 or None, {"level":…, "field":…, "message":…} or None)
    """
    raw = _collect(product, field)
    cand = {src: [v for v in vals if _plausible(field, v, label, known)]
            for src, vals in raw.items()}

    name_vals = sorted(set(cand["name"]))
    other_all = cand["catch"] + cand["caption"]
    other_vals = sorted(set(other_all))

    def issue(level, msg):
        return {"level": level, "field": field, "message": msg}

    # --- 商品名に候補がある場合 ---
    if name_vals:
        if len(name_vals) == 1:
            value = name_vals[0]
            if other_vals and not any(_close(value, o) for o in other_vals):
                return value, issue(
                    WARNING,
                    f"商品名は{_fmt(value)}、説明文は{_fmt_list(other_vals)}。商品名を採用")
            return value, None

        backed = [v for v in name_vals if any(_close(v, o) for o in other_vals)]
        if len(set(backed)) == 1:
            return backed[0], None
        if _close(min(name_vals), max(name_vals), tol=0.08):
            return max(name_vals), None
        return None, issue(
            BLOCK, f"商品名に複数の値 {_fmt_list(name_vals)}。判別できないため不明")

    # --- 商品名に無い場合 ---
    if not other_vals:
        return None, None                       # 記載なし。矛盾ではない

    if len(other_vals) == 1:
        return other_vals[0], None

    if _close(min(other_vals), max(other_vals), tol=0.05):
        return max(other_vals), None

    counts = Counter(other_all).most_common()
    if len(counts) >= 2 and counts[0][1] > counts[1][1]:
        return counts[0][0], None

    return None, issue(
        BLOCK, f"説明文に離れた値 {_fmt_list(other_vals)}。他機種の併記の可能性があるため不明")


# ------------------------------------------------------------------ 価格
def check_price(product):
    """
    表示価格は楽天APIの現在価格を基準とする。
    商品名に書かれた割引後価格との差は記録するだけで、掲載は止めない。
    """
    price = product.get("price") or 0
    if price <= 0:
        return {"level": BLOCK, "field": "price", "message": "価格が取得できていない"}

    name = product.get("name") or ""
    shown = [int(m.group(1).replace(",", ""))
             for m in re.finditer(r"([\d,]{4,9})\s*円", name)]
    shown = [v for v in shown if 1000 <= v <= 2000000]
    if not shown:
        return None
    if all(abs(v - price) / max(v, price) > 0.30 for v in shown):
        return {"level": WARNING, "field": "price",
                "message": (f"商品名の金額 {_fmt_list(shown)}円 と "
                            f"取得価格 {price:,}円 が離れている。"
                            f"クーポン適用前の価格を表示している可能性")}
    return None



# ------------------------------------------------------------------ 機能の有無
# 商品説明に明確な記載があるものだけ「対応」と判定する。
# 記載が無い＝非対応ではないので、その場合は None（＝不明）を返す。
#
# 判定材料を増やすときは、ここに行を足すか sources を増やすだけで済むようにしてある。
#   key      … spec["features"] のキー
#   label    … 画面に出す名前
#   patterns … これに当たれば「対応」。正規表現
#   sources  … 見る場所。将来メーカー情報を足すならここに増やす
FEATURE_RULES = [
    {
        "key": "multi",
        "label": "複数荷物",
        "patterns": [
            r"複数(?:個)?(?:の)?(?:荷物|投函|受取|受け取り|配達)",
            r"連続(?:投函|受取|受け取り)",
            r"[2２]個(?:口|まで)?(?:の)?(?:荷物|受取|受け取り|投函)",
            r"再投函",
            r"複数回(?:の)?(?:投函|受取)",
        ],
        "sources": ("name", "catch", "caption"),
    },
    {
        "key": "waterproof",
        "label": "防水",
        "patterns": [r"防水", r"IPX\s*[4-8]", r"完全防水"],
        "sources": ("name", "catch", "caption"),
    },
    {
        "key": "lock",
        "label": "施錠",
        "patterns": [r"施錠", r"鍵付き", r"ダイヤルロック", r"南京錠", r"オートロック"],
        "sources": ("name", "catch", "caption"),
    },
]

# 「対応」でも「不明」でもなく、はっきり無いと書かれている場合に使う。
# いまのところ確実に読み取れる書き方が無いので、どのルールにも設定していない。
NOT_SUPPORTED = "非対応"
SUPPORTED = "対応"
UNKNOWN = None


def find_features(product):
    """
    機能ごとに「対応」か「不明」を返す。
    記載が無いことを根拠に「非対応」とは判定しない。
    """
    out = {}
    for rule in FEATURE_RULES:
        text = " ".join(product.get(src) or "" for src in rule["sources"])
        hit = any(re.search(pat, text) for pat in rule["patterns"])
        out[rule["key"]] = SUPPORTED if hit else UNKNOWN
    return out


def feature_text(spec, key):
    """画面に出す文字。対応が確認できないものは「不明」。"""
    return spec.get("features", {}).get(key) or "不明"

# ------------------------------------------------------------------ 分類タグ
def make_tags(product, spec):
    """
    記事の切り口に使うタグ。価格帯以外の軸を足すときはここを増やす。
    判定できないものは付けない（推測しない）。
    """
    name = product.get("name") or ""
    text = name + " " + (product.get("caption") or "") + " " + (product.get("catch") or "")
    tags = []

    if product.get("label") == "宅配ボックス":
        if spec.get("post"):
            tags.append("ポスト一体型")
        if spec.get("anchor"):
            tags.append("アンカー固定可")
        if re.search(r"戸建|一戸建", text):
            tags.append("戸建て向け")
        if spec.get("features", {}).get("multi") == SUPPORTED:
            tags.append("複数荷物対応")
        if (spec.get("liters") or 0) >= 100 or "大容量" in name:
            tags.append("大容量")
        if spec.get("kg") and spec["kg"] >= 20:
            tags.append("据え置き型")
        if re.search(r"埋め込み|据付|据え付け|基礎", text):
            tags.append("据付工事型")
    else:
        if spec.get("w") and spec["w"] >= 1500:
            tags.append("電動工具が動く")
        if spec.get("wh") and spec.get("kg") and 500 <= spec["wh"] <= 1500 and spec["kg"] <= 15:
            tags.append("持ち運べる")
        if spec.get("wh") and spec["wh"] >= 1000 and spec.get("battery") == "リン酸鉄":
            tags.append("長期保管向き")
        if spec.get("solar"):
            tags.append("ソーラー付き")

    return tags



# ------------------------------------------------------------------ 寸法
# 幅×奥行×高さ。書き方がショップごとに違うので代表的な3通りを見る。
SIZE_PATTERNS = [
    r"幅[約\s:：]*(\d{2,3}(?:\.\d)?)\s*(?:cm)?[^\d]{0,14}奥行[きさ]?[約\s:：]*(\d{2,3}(?:\.\d)?)\s*(?:cm)?[^\d]{0,14}高さ[約\s:：]*(\d{2,3}(?:\.\d)?)",
    r"W[約\s:：]*(\d{2,3}(?:\.\d)?)\s*(?:cm)?\s*[×xX]\s*D[約\s:：]*(\d{2,3}(?:\.\d)?)\s*(?:cm)?\s*[×xX]\s*H[約\s:：]*(\d{2,3}(?:\.\d)?)",
    r"(?:外寸|本体サイズ|サイズ)[^\d]{0,10}(\d{2,3}(?:\.\d)?)\s*[×xX]\s*(\d{2,3}(?:\.\d)?)\s*[×xX]\s*(\d{2,3}(?:\.\d)?)\s*cm",
]


def find_size(product):
    """幅・奥行・高さをcmで取り出す。読み取れなければ None。"""
    for text in (product.get("name") or "", product.get("catch") or "",
                 product.get("caption") or ""):
        for pat in SIZE_PATTERNS:
            m = re.search(pat, text)
            if not m:
                continue
            try:
                w, d, h = (float(m.group(i)) for i in (1, 2, 3))
            except (TypeError, ValueError):
                continue
            if all(15 <= v <= 200 for v in (w, d, h)):
                return {"w": w, "d": d, "h": h}
    return None


def size_text(size):
    if not size:
        return None
    return f"幅{size['w']:g}×奥行{size['d']:g}×高さ{size['h']:g}cm"


# ------------------------------------------------------------------ 設置方法
def find_install(product, spec):
    """設置のしかた。書かれていないものは推測しない。"""
    text = ((product.get("name") or "") + " " + (product.get("caption") or "")
            + " " + (product.get("catch") or ""))
    parts = []
    if re.search(r"据[え]?付|埋[めこ]込|基礎工事|アンカーボルト施工|ポール設置|門柱", text):
        parts.append("据付")
    if spec.get("anchor"):
        parts.append("アンカー固定可")
    if re.search(r"置き型|据え置き|置き配|スタンド|自立", text):
        parts.append("置き型")
    if not parts:
        return None
    # 置き型を先に見せたほうが分かりやすい
    parts.sort(key=lambda x: {"置き型": 0, "アンカー固定可": 1, "据付": 2}.get(x, 3))
    return "／".join(parts)


# ------------------------------------------------------------------ 注意点
def cautions(product, spec):
    """
    データから言える注意点だけを返す。
    使った感想は書かない。読み取れない項目は「読み取れない」と書く。
    """
    out = []
    label = product.get("label")
    price_warn = any(i["field"] == "price" and i["level"] == WARNING
                     for i in spec.get("issues", []))

    if label == "ポータブル電源":
        if spec["w"] is None:
            out.append("定格出力が読み取れません。電動工具に使うなら商品ページで確認を")
        elif spec["w"] < 1000:
            out.append(f"定格{spec['w']:,}W。電子レンジや大きめの電動工具は動きません")
        if spec["kg"] is None:
            out.append("本体重量が読み取れません")
        elif spec["kg"] > 20:
            out.append(f"{spec['kg']:g}kg。持ち運ぶ使い方には向きません")
        if spec["battery"] == "三元系":
            out.append("三元系リチウム。リン酸鉄より充放電できる回数は少なめです")
        elif spec["battery"] is None:
            out.append("電池の種類が読み取れません")
    else:
        if spec["kg"] is None:
            out.append("本体重量が読み取れません")
        elif spec["kg"] < 10:
            out.append(f"本体{spec['kg']:g}kg。空のときは風で動くことがあります")
        if not spec.get("anchor"):
            out.append("アンカー固定の記載がありません")
        if not spec.get("size"):
            out.append("寸法が読み取れません。設置場所に入るか商品ページで確認を")

    if price_warn:
        out.append("商品名の割引価格と表示価格が違います。表示は楽天の現在価格です")
    return out

# ------------------------------------------------------------------ 本体
def extract(product):
    """
    商品1件から仕様を取り出す。
    spec["issues"] は dict のリスト。spec["block"] が True なら掲載しない。
    """
    label = product.get("label") or ""
    name = product.get("name") or ""
    text = (product.get("caption") or "") + " " + (product.get("catch") or "")
    both = name + " " + text

    spec = {"wh": None, "w": None, "kg": None, "battery": None, "solar": False,
            "liters": None, "material": None, "post": False, "anchor": False,
            "size": None, "install": None, "cautions": [], "features": {},
            "issues": [], "block": False, "tags": []}

    order = ("wh", "w", "kg") if label == "ポータブル電源" else ("liters", "kg")
    known = {}
    for field in order:
        value, issue = decide(product, field, label, known)
        if value is not None:
            value = int(value) if field in ("wh", "w", "liters") else round(value, 1)
        spec[field] = value
        known[field] = value
        if issue:
            spec["issues"].append(issue)

    issue = check_price(product)
    if issue:
        spec["issues"].append(issue)

    if "リン酸鉄" in both:
        spec["battery"] = "リン酸鉄"
    elif "三元系" in both:
        spec["battery"] = "三元系"
    if re.search(r"ソーラーパネル.{0,8}(セット|付)|Solar Generator", name):
        spec["solar"] = True
    for material in ("ステンレス", "スチール", "アルミ", "木製", "樹脂"):
        if material in both:
            spec["material"] = material
            break
    if "一体型" in name or "ポスト付" in name:
        spec["post"] = True
    if "アンカー" in both:
        spec["anchor"] = True

    spec["size"] = find_size(product)
    spec["install"] = find_install(product, spec)
    spec["features"] = find_features(product)
    spec["tags"] = make_tags(product, spec)
    spec["cautions"] = cautions(product, spec)

    # 掲載を止めるのは、中心となる項目が矛盾で確定できなかった場合だけ。
    # 記載が無いだけ、価格表示が食い違うだけでは止めない。
    core = CORE_FIELD.get(label)
    for i in spec["issues"]:
        if i["level"] != BLOCK:
            continue
        if i["field"] == "price" or (core and i["field"] == core):
            spec["block"] = True
        else:
            # 中心でない項目の矛盾は、その値を不明にするだけで掲載は続ける
            i["level"] = WARNING

    return spec


def issue_text(issue):
    return f"{FIELD_LABEL.get(issue['field'], issue['field'])}: {issue['message']}"
