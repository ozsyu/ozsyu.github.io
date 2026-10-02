#!/usr/bin/env python3
"""
SEOの安全確認（369）

site/ を生成したあとに実行して、重複やリンク切れを機械的に調べる。
サイトは生成しない。

使い方:
    python build_site.py && python seocheck.py
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict

OUT = "site"
BASE_URL = "https://ozsyu.github.io"

NG_WORDS = ["おすすめNo.1", "おすすめNO.1", "No.1", "絶対", "最強", "業界一",
            "日本一", "完全無欠", "100%満足"]


def load_pages():
    pages = {}
    for root, _, files in os.walk(OUT):
        for f in files:
            if not f.endswith(".html"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, OUT).replace(os.sep, "/")
            pages[rel] = open(path, encoding="utf-8").read()
    return pages


def tag(html, pattern, group=1):
    m = re.search(pattern, html, re.S)
    return m.group(group).strip() if m else None


def main():
    if not os.path.isdir(OUT):
        sys.exit(f"{OUT}/ がありません。先に build_site.py を実行してください。")

    pages = load_pages()
    info = {}
    for rel, html in pages.items():
        info[rel] = {
            "title": tag(html, r"<title>(.*?)</title>"),
            "desc": tag(html, r'<meta name="description" content="(.*?)"'),
            "canonical": tag(html, r'<link rel="canonical" href="(.*?)"'),
            "h1": re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S),
            "og": {k: tag(html, rf'<meta property="og:{k}" content="(.*?)"')
                   for k in ("title", "description", "url", "type", "image")},
            "jsonld": re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                 html, re.S),
            "html": html,
        }

    results = []

    def add(name, bad, detail=""):
        results.append((name, len(bad), bad[:6], detail))

    # 1. 重複title
    c = Counter(v["title"] for v in info.values() if v["title"])
    add("重複title", [f"{t}（{n}ページ）" for t, n in c.items() if n > 1])

    # 2. 重複meta description
    c = Counter(v["desc"] for v in info.values() if v["desc"])
    add("重複meta description", [f"{d[:40]}…（{n}ページ）" for d, n in c.items() if n > 1])

    # 3. meta description 欠落・長さ
    add("description欠落", [k for k, v in info.items() if not v["desc"]])
    add("descriptionが長い(120字超)",
        [f"{k} {len(v['desc'])}字" for k, v in info.items()
         if v["desc"] and len(v["desc"]) > 120])

    # 4. H1
    add("H1欠落", [k for k, v in info.items() if len(v["h1"]) == 0])
    add("複数H1", [f"{k} {len(v['h1'])}個" for k, v in info.items() if len(v["h1"]) > 1])

    # 5. canonical
    add("canonical欠落", [k for k, v in info.items() if not v["canonical"]])
    mismatch = []
    for k, v in info.items():
        if not v["canonical"]:
            continue
        want = f"{BASE_URL}/{k}"
        if v["canonical"] != want:
            mismatch.append(f"{k} → {v['canonical']}")
    add("canonical不整合", mismatch)

    # 6. 見出しの順序
    disorder = []
    for k, v in info.items():
        levels = [int(x) for x in re.findall(r"<h([1-4])[^>]*>", v["html"])]
        prev = 0
        for lv in levels:
            if prev and lv > prev + 1:
                disorder.append(f"{k} h{prev}→h{lv}")
                break
            prev = lv
    add("見出しの飛び越し", disorder)

    # 7. 404の内部リンク
    broken = []
    for k, v in info.items():
        base = os.path.dirname(os.path.join(OUT, k))
        for href in re.findall(r'href="([^"]+)"', v["html"]):
            if href.startswith(("http", "#", "mailto")):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, href))):
                broken.append(f"{k} → {href}")
    add("404の内部リンク", broken)

    # 8. 孤立ページ（どこからもリンクされていない）
    linked = set()
    for k, v in info.items():
        base = os.path.dirname(k)
        for href in re.findall(r'href="([^"]+)"', v["html"]):
            if href.startswith(("http", "#", "mailto")):
                continue
            target = os.path.normpath(os.path.join(base, href)).replace(os.sep, "/")
            linked.add(target)
    orphan = [k for k in info if k != "index.html" and k not in linked]
    add("孤立ページ", orphan)

    # 9. sitemapとの一致
    sm = open(os.path.join(OUT, "sitemap.xml"), encoding="utf-8").read()
    sm_urls = [u.replace(BASE_URL + "/", "")
               for u in re.findall(r"<loc>(.*?)</loc>", sm)]
    add("sitemapの重複", [u for u, n in Counter(sm_urls).items() if n > 1])
    add("sitemapにあるが実在しない",
        [u for u in sm_urls if not os.path.exists(os.path.join(OUT, u))])
    add("HTMLにあるがsitemapに無い",
        [k for k in info if k not in sm_urls])

    # 10. robots.txt
    robots = open(os.path.join(OUT, "robots.txt"), encoding="utf-8").read()
    blocked = [line for line in robots.splitlines()
               if line.lower().startswith("disallow:") and line.split(":", 1)[1].strip()]
    add("robots.txtで遮断中のパス", blocked)

    # 11. OGP
    for key in ("title", "description", "url", "type"):
        add(f"og:{key} 欠落", [k for k, v in info.items() if not v["og"][key]])
    add("og:url 不整合",
        [f"{k} → {v['og']['url']}" for k, v in info.items()
         if v["og"]["url"] and v["og"]["url"] != f"{BASE_URL}/{k}"])

    # 12. 構造化データが壊れていないか
    broken_ld = []
    for k, v in info.items():
        for raw in v["jsonld"]:
            try:
                json.loads(raw)
            except Exception as e:
                broken_ld.append(f"{k}: {e}")
    add("JSON-LDの構文エラー", broken_ld)

    # 13. 誇張表現
    hits = []
    for k, v in info.items():
        text = re.sub(r"<[^>]+>", " ", v["html"])
        for w in NG_WORDS:
            # 商品名そのものに含まれる場合は除く（楽天の商品名は変更できない）
            if w in (v["title"] or "") or w in (v["desc"] or ""):
                hits.append(f"{k}: {w}")
    add("title/descの誇張表現", hits)

    # ---- 出力 ----
    print(f"ページ数: {len(info)}\n")
    print("=" * 64)
    print(f" {'項目':<28}{'件数':>6}  判定")
    print("=" * 64)
    ng = 0
    for name, n, sample, _ in results:
        mark = "OK" if n == 0 else "要確認"
        if n:
            ng += 1
        print(f" {name:<28}{n:>6}  {mark}")
        for sitem in sample:
            print(f"     - {sitem}")
    print("=" * 64)
    print(f"\n問題なし {len(results) - ng}項目 ／ 要確認 {ng}項目")

    # title一覧
    print("\n--- title 一覧 ---")
    for k in sorted(info):
        print(f"  {k:<32} {info[k]['title']}")


if __name__ == "__main__":
    main()
