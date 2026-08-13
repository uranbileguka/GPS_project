"""agent_method_talk.md  ->  agent_method_talk.html

Standalone, no dependencies, no external assets — the page has to open from a file share
with nothing installed. Kept in the repo for the same reason as make_method_figs.py: the
previous generator lived in a scratch directory and was gone when the numbers changed.

    python analysis/make_talk_html.py
"""
import html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'agent_method_talk.md')
OUT = os.path.join(HERE, 'agent_method_talk.html')

CSS = """
:root{--ink:#1d2125;--grey:#6b7076;--teal:#1b9e8a;--line:#e6e9ea}
*{box-sizing:border-box}
body{max-width:860px;margin:0 auto;padding:44px 32px 100px;background:#fff;color:var(--ink);
 font:17px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",Arial,sans-serif}
h1{font-size:28px;margin:0 0 10px;padding-bottom:12px;border-bottom:3px solid var(--teal)}
h2{font-size:21px;margin:48px 0 18px;padding:10px 0 10px 15px;border-left:5px solid var(--teal);
 background:#f4faf8;line-height:1.35}
p{margin:14px 0}
strong{font-weight:650}
hr{border:0;border-top:1px solid var(--line);margin:0}
em{color:var(--grey)}
code{background:#f0f2f3;padding:2px 6px;border-radius:4px;font-size:.9em}
@media print{body{max-width:none;padding:0;font-size:12.5px}
 h2{page-break-after:avoid;font-size:17px}p{page-break-inside:avoid}}
"""


def inline(text):
    """Markdown inline -> HTML. Escape first so the source cannot inject markup."""
    t = html.escape(text, quote=False)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', t)
    return t


def convert(md):
    out, para = [], []

    def flush():
        if para:
            out.append('<p>' + '<br />\n'.join(inline(l) for l in para) + '</p>')
            para.clear()

    title = 'Talking script'
    for raw in md.split('\n'):
        line = raw.rstrip()
        if line.startswith('# '):
            flush(); title = line[2:].strip()
        elif line.startswith('## '):
            flush(); out.append(f'<h2>{inline(line[3:].strip())}</h2>')
        elif line.strip() == '---':
            flush(); out.append('<hr />')
        elif not line.strip():
            flush()
        else:
            para.append(line)
    flush()
    return title, '\n'.join(out)


def main():
    with open(SRC) as fh:
        md = fh.read()
    title, body = convert(md)
    page = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>讲稿 · Talking script</title><style>{CSS}</style></head><body>'
            f'<h1>{inline(title)}</h1>\n{body}\n</body></html>\n')
    with open(OUT, 'w') as fh:
        fh.write(page)
    print(f'wrote {os.path.basename(OUT)}  ({len(page):,} bytes)')


if __name__ == '__main__':
    main()
