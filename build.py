#!/usr/bin/env python3
"""会社経営オンライン 攻略ガイドの静的サイト生成。

- content/*.md (本文・運営だけが書く) を HTML にする
- config.json の approved_csv_url (スプレッドシートの「公開」タブ=承認済みだけ) を読み、
  各ページの末尾に「プレイヤーからの情報」として載せる
- 出力は public/

外部ライブラリなし(Python 3.9+ 標準のみ)。
"""
import csv
import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
OUT = ROOT / "public"


# ---------------------------------------------------------------- 設定 / 投稿

def load_config():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def fetch_approved(url):
    """承認済みタブの CSV を読む。列= タイムスタンプ, ページ, 内容, 名前(任意)。
    失敗しても本文だけでサイトは出す(投稿欄が空になるだけ)。"""
    if not url:
        return []
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            text = r.read().decode("utf-8-sig")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 承認済み投稿を読めませんでした: {e}", file=sys.stderr)
        return []
    rows = list(csv.reader(io.StringIO(text)))
    posts = []
    for row in rows[1:]:  # 1 行目は見出し
        row = (row + ["", "", "", ""])[:4]
        ts, page, body, name = (c.strip() for c in row)
        if not page or not body:
            continue
        posts.append({"ts": ts, "page": page, "body": body, "name": name})
    return posts


# ---------------------------------------------------------------- 最小 Markdown

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    # [文字](相対リンク.html or https://)
    s = re.sub(r"\[([^\]]+)\]\(((?:https?://|[\w\-]+\.html)[^)\s]*)\)",
               lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', s)
    return s


def md_to_html(md):
    out, para, lst, table = [], [], None, []

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para.clear()

    def flush_list():
        nonlocal lst
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None

    def flush_table():
        if not table:
            return
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table]
        head, body = rows[0], [r for r in rows[1:] if not re.fullmatch(r"[\s:\-|]*", "|".join(r))]
        h = "".join(f"<th>{inline(c)}</th>" for c in head)
        b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
        out.append(f'<div class="tbl"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>')
        table.clear()

    def flush_all():
        flush_para(); flush_list(); flush_table()

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_all(); continue
        if line.lstrip().startswith("|"):
            flush_para(); flush_list(); table.append(line); continue
        flush_table()
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_all()
            n = max(2, len(m.group(1)))  # ## → h2・### → h3(h1 はページ名)
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); continue
        m = re.match(r"^\s*[-・]\s+(.*)$", line)
        if m:
            flush_para()
            if not lst or lst[0] != "ul":
                flush_list(); lst = ("ul", [])
            lst[1].append(m.group(1)); continue
        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            flush_para()
            if not lst or lst[0] != "ol":
                flush_list(); lst = ("ol", [])
            lst[1].append(m.group(1)); continue
        if line.startswith("> "):
            flush_all(); out.append(f'<p class="note">{inline(line[2:])}</p>'); continue
        flush_list(); para.append(line)
    flush_all()
    return "\n".join(out)


def parse_page(path):
    text = path.read_text(encoding="utf-8")
    meta = {"slug": path.stem, "title": path.stem, "order": "99", "status": ""}
    if text.startswith("---"):
        _, fm, text = text.split("---", 2)
        for l in fm.strip().splitlines():
            if ":" in l:
                k, v = l.split(":", 1)
                meta[k.strip()] = v.strip()
    meta["body"] = text.strip()
    return meta


# ---------------------------------------------------------------- HTML

CSS = """
:root{--ink:#222;--muted:#666;--line:#cfcfcf;--head:#f2f2f2;--link:#1a55a8;--key:#2f7d4f;--soft:#f7f9f6}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font:15px/1.75 -apple-system,"Hiragino Kaku Gothic ProN","Hiragino Sans",Meiryo,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--link)}a:hover{text-decoration:none}
.bar{border-bottom:3px solid var(--key)}
.bar .in{max-width:1080px;margin:0 auto;padding:10px 16px;display:flex;align-items:center;gap:10px}
.bar a.site{color:var(--ink);text-decoration:none;font-weight:700;font-size:18px}
.bar a.site img{width:34px;height:34px;vertical-align:middle;margin-right:8px;border-radius:8px}
.bar small{color:var(--muted);font-size:12px}
.layout{max-width:1080px;margin:0 auto;padding:0 16px;display:grid;grid-template-columns:minmax(0,1fr) 220px;gap:32px}
.side{padding:16px 0}
.side h4{margin:0 0 4px;font-size:13px;background:var(--key);color:#fff;padding:4px 8px}
.side ul{list-style:none;margin:0 0 16px;padding:0;border:1px solid var(--line);border-top:0}
.side li a{display:block;padding:6px 10px;border-top:1px solid #eee;text-decoration:none;font-size:14px}
.side li a:hover{background:var(--soft)}
.side li a.cur{font-weight:700;color:var(--ink);background:var(--soft)}
main{padding:12px 0 48px;min-width:0}
.crumb{font-size:12px;color:var(--muted);margin:4px 0 0}
h1{font-size:24px;margin:6px 0 14px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h1 img{width:44px;height:44px;vertical-align:-10px;margin-right:6px}
.st{font-size:12px;font-weight:400;color:#a05a00;border:1px solid #e0b070;background:#fff8ec;padding:1px 6px;margin-left:8px;vertical-align:4px}
h2{font-size:18px;margin:30px 0 10px;padding:5px 10px;background:var(--head);border-left:6px solid var(--key)}
h3{font-size:16px;margin:22px 0 6px;padding-bottom:2px;border-bottom:1px dotted #aaa}
.tbl{overflow-x:auto}
table{border-collapse:collapse;font-size:14px;margin:6px 0}
th,td{border:1px solid var(--line);padding:5px 10px;text-align:left;vertical-align:top}
th{background:var(--head);white-space:nowrap}
.note{border:1px solid #d8d8d8;background:#fafafa;padding:8px 12px;font-size:14px}
.shot{display:block;width:100%;height:auto;border:1px solid var(--line);margin:4px 0 12px}
ul.list{list-style:none;padding:0;margin:8px 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:0 20px}
ul.list li{border-bottom:1px solid #eee;padding:8px 0}
ul.list a{display:flex;gap:10px;align-items:center;text-decoration:none}
ul.list img{width:44px;height:44px;flex:none}
ul.list b{display:block}
ul.list span{display:block;color:var(--muted);font-size:12px;line-height:1.5}
table.idx{width:100%}table.idx td:first-child{white-space:nowrap;font-weight:700;width:1%}
.posts{margin-top:36px}
.post{border:1px solid var(--line);padding:8px 12px;margin:8px 0}
.post .meta{font-size:12px;color:var(--muted)}
.send{display:inline-block;margin-top:6px;padding:7px 14px;border:1px solid var(--link);color:var(--link);text-decoration:none;font-size:14px}
.send:hover{background:#eef3fb}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:12px}
footer .in{max-width:1080px;margin:0 auto;padding:14px 16px 28px}
@media (max-width:760px){
 .layout{grid-template-columns:1fr;gap:0}
 .side{order:2;padding-top:0}
 main{order:1}
}
"""


def first_line(md):
    for l in md.splitlines():
        l = l.strip()
        if l and not l.startswith(("#", "|", ">", "-")):
            l = re.sub(r"\*\*", "", l)
            return l.split("。")[0] + "。" if "。" in l else l
    return ""


def form_link(cfg, slug, title):
    base = cfg.get("form_url", "")
    if not base:
        return ""
    entry = cfg.get("form_page_entry", "")
    if entry:
        sep = "&" if "?" in base else "?"
        base = f"{base}{sep}usp=pp_url&{entry}={urllib.parse.quote(title)}"
    return base


def render(cfg, page, pages, posts):
    site = html.escape(cfg["site_title"])
    menu = "".join(
        f'<li><a href="{p["slug"]}.html"{" class=cur" if p["slug"] == page["slug"] else ""}>{html.escape(p["title"])}</a></li>'
        for p in pages)
    st = f'<span class="st">{html.escape(page["status"])}</span>' if page["status"] else ""
    body = md_to_html(page["body"])
    icon = page.get("icon", "")
    if page["slug"] == "index":
        items = "".join(
            f'<tr><td><a href="{p["slug"]}.html">{html.escape(p["title"])}</a></td><td>{html.escape(first_line(p["body"]))}</td></tr>'
            for p in pages if p["slug"] != "index")
        top = f'<h1>{site}</h1><img class="shot" src="assets/hero.jpg" alt="ゲーム画面">'
        body += f'<h2>ページ一覧</h2><div class="tbl"><table class="idx"><tbody>{items}</tbody></table></div>'
        crumb = ""
    else:
        top = f'<h1>{html.escape(page["title"])}{st}</h1>'
        crumb = f'<p class="crumb"><a href="index.html">トップ</a> &gt; {html.escape(page["title"])}</p>'
    mine = [x for x in posts if x["page"] in (page["title"], page["slug"])]
    post_html = ""
    if page["slug"] != "index":
        items = "".join(
            '<div class="post"><div class="meta">'
            + html.escape(x["ts"]) + (f' ・ 情報提供：{html.escape(x["name"])}さん' if x["name"] and cfg.get("show_names") else "")
            + '</div><div>' + html.escape(x["body"]).replace("\n", "<br>") + "</div></div>"
            for x in mine)
        link = form_link(cfg, page["slug"], page["title"])
        btn = f'<a class="send" href="{html.escape(link)}" target="_blank" rel="noopener">このページへの情報を送る</a>' if link else ""
        post_html = (f'<section class="posts"><h2>プレイヤーからの情報</h2>'
                     f'{items or "<p>まだありません。</p>"}'
                     f'<p class="note">送っていただいた情報は、運営が確認してから掲載します。</p>{btn}</section>')
    page_title = site if page["slug"] == "index" else f'{html.escape(page["title"])} - {site}'
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{page_title}</title>
<meta name="description" content="{html.escape(cfg.get("description", ""))}">
<link rel="icon" href="assets/app_icon.png">
<style>{CSS}</style></head>
<body><div class="bar"><div class="in"><a class="site" href="index.html"><img src="assets/app_icon.png" alt="">{site}</a></div></div>
<div class="layout">
<main>{crumb}{top}
{body}
{post_html}
</main>
<aside class="side"><h4>メニュー</h4><ul>{menu}</ul></aside>
</div>
<footer><div class="in">{html.escape(cfg.get("footer", ""))}</div></footer></body></html>"""


def main():
    cfg = load_config()
    pages = sorted((parse_page(p) for p in CONTENT.glob("*.md")), key=lambda p: (int(p["order"]), p["slug"]))
    posts = fetch_approved(cfg.get("approved_csv_url", ""))
    OUT.mkdir(exist_ok=True)
    for page in pages:
        (OUT / f'{page["slug"]}.html').write_text(render(cfg, page, pages, posts), encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    import shutil
    if (ROOT / "assets").exists():
        shutil.copytree(ROOT / "assets", OUT / "assets", dirs_exist_ok=True)
    print(f"built {len(pages)} pages, {len(posts)} approved posts -> {OUT}")


if __name__ == "__main__":
    main()
