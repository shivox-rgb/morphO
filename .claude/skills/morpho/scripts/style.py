#!/usr/bin/env python3
"""Style presets: list them, show one, and apply one to a book.

  style.py list [--tier lesson|picture|documentary|shorts] [--mode light|dark]
  style.py show <id>
  style.py apply site/<book> <id> [--style-json books/<book>/style.json]
  style.py remove site/<book> [--style-json books/<book>/style.json]

The presets are assets/styles/<id>.css, described in assets/styles/styles.json (mood, the tiers each suits, the
character look to draw the cast in) and shown in assets/styles/samples/index.html, a gallery of every preset with a
sample scene. `apply` puts the preset at the top of the book's lib/book.css, after any @import lines, between two
marker comments, so applying another preset replaces it and `remove` takes it out. Whatever the book's lib/book.css
says below the block still wins: a film kit's own palette, for example, keeps its colours, and the preset then
restyles only the shapes (cards, buttons, bar). The tool names every such setting it leaves to the book.
With --style-json it also records the choice as the "preset" block of the book's style.json.
"""
import argparse
import json
import re
import sys
from pathlib import Path

STYLES = Path(__file__).resolve().parent.parent / 'assets' / 'styles'
START, END = '/* morpho-style: ', '/* end morpho-style */'
PALETTE = ['--page', '--board', '--panel', '--edge', '--chalk', '--dim', '--faint', '--task', '--quiz', '--good', '--bad']


def catalog():
    data = json.loads((STYLES / 'styles.json').read_text(encoding='utf-8'))
    styles = {s['id']: s for s in data['styles']}
    for s in styles.values():
        for need in (STYLES / f"{s['id']}.css", STYLES / s['sample']):
            if not need.exists():
                print(f"warning: {s['id']}: {need.relative_to(STYLES.parent.parent)} is missing", file=sys.stderr)
    return styles


def get(styles, sid):
    if sid not in styles:
        sys.exit(f"no style '{sid}'; the styles are: {', '.join(styles)}")
    return styles[sid]


def book_css(book):
    css = Path(book) / 'lib' / 'book.css'
    if not css.exists():
        sys.exit(f"{css} does not exist: start the book with new_book.py (or engine.py {book}) first")
    return css


def read(css):
    """The file's text with \\n line ends, and the line end it uses, so a write gives it back unchanged."""
    raw = css.read_bytes().decode('utf-8')
    return raw.replace('\r\n', '\n'), '\r\n' if '\r\n' in raw else '\n'


def write(css, text, eol):
    css.write_bytes(text.replace('\n', eol).encode('utf-8'))


def strip_block(text):
    """Remove an applied preset block; return the text and the id it held (or None)."""
    # the block with the blank line apply put before it (after @import lines) and the one after it
    m = re.search(r'\n?' + re.escape(START) + r'([\w-]+).*?' + re.escape(END) + r'\n\n?', text, flags=re.S)
    return (text[:m.start()] + text[m.end():], m.group(1)) if m else (text, None)


def record(path, value):
    p = Path(path)
    if not p.exists():
        print(f"{p} does not exist, so the choice was not recorded there", file=sys.stderr)
        return
    data = json.loads(p.read_text(encoding='utf-8'))
    if value is None:
        data.pop('preset', None)
    else:
        data['preset'] = value
    p.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8'))
    print(f"recorded in {p}: preset = {value['id'] if value else 'none'}")


def cmd_list(a):
    styles = catalog()
    rows = [s for s in styles.values() if (not a.tier or a.tier in s['tiers']) and (not a.mode or s['mode'] == a.mode)]
    if not rows:
        sys.exit(f"no style suits tier={a.tier} mode={a.mode}")
    for s in rows:
        pair = f"  (twin: {s['pair']})" if s.get('pair') else ''
        print(f"{s['id']:<12} {s['name']} [{s['mode']}]{pair}\n             {s['mood']}\n             suits {s['suits']}; best for {', '.join(s['tiers'])}")
    print(f"\ngallery: {STYLES / 'samples' / 'index.html'}")


def cmd_show(a):
    s = get(catalog(), a.id)
    for k in ('name', 'mode', 'mood', 'suits', 'characters'):
        print(f"{k:<11} {s[k]}")
    print(f"{'tiers':<11} {', '.join(s['tiers'])}")
    if s.get('pair'):
        print(f"{'twin':<11} {s['pair']}")
    print(f"{'file':<11} {STYLES / (s['id'] + '.css')}\n{'sample':<11} {STYLES / s['sample']}")


def cmd_apply(a):
    s = get(catalog(), a.id)
    css = book_css(a.book)
    text, eol = read(css)
    text, old = strip_block(text)
    preset = read(STYLES / f"{s['id']}.css")[0].rstrip() + '\n'
    block = (f"{START}{s['id']} ({s['name']}), from assets/styles/{s['id']}.css. style.py apply replaces this block and "
             f"style.py remove deletes it; the book's own settings go below it and win. */\n{preset}{END}\n")
    lines = text.splitlines(keepends=True)
    imports = [i for i, ln in enumerate(lines) if ln.lstrip().startswith('@import')]
    at = imports[-1] + 1 if imports else 0
    if at and not lines[at - 1].endswith('\n'):
        lines[at - 1] += '\n'
    write(css, ''.join(lines[:at]) + ('\n' if at else '') + block + ('\n' if lines[at:] else '') + ''.join(lines[at:]), eol)
    n = len(imports)
    where = f"after its {n} @import line{'s' if n != 1 else ''}" if n else 'at the top'
    print(f"applied {s['id']} to {css} ({where})" + (f", replacing {old}" if old else ''))
    rest = ''.join(lines[at:])
    rest_rules = re.sub(r'/\*.*?\*/', '', rest, flags=re.S)
    kept = [v for v in PALETTE if re.search(re.escape(v) + r'\s*:', rest_rules)]
    if kept:
        print(f"note: the book's own settings below the block set {', '.join(kept)}, so those keep the book's values; "
              f"remove them from {css.name} to take the preset's")
    if a.style_json:
        record(a.style_json, {'id': s['id'], 'name': s['name'], 'file': f"assets/styles/{s['id']}.css",
                              'characters': s['characters'], 'sample': f"assets/styles/{s['sample']}"})


def cmd_remove(a):
    css = book_css(a.book)
    text, eol = read(css)
    text, old = strip_block(text)
    if not old:
        print(f"{css} has no preset block; nothing removed")
    else:
        write(css, text, eol)
        print(f"removed {old} from {css}")
    if a.style_json:
        record(a.style_json, None)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('list', help='list the presets')
    s.add_argument('--tier', choices=['lesson', 'picture', 'documentary', 'shorts'])
    s.add_argument('--mode', choices=['light', 'dark'])
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser('show', help="one preset's details")
    s.add_argument('id')
    s.set_defaults(fn=cmd_show)
    s = sub.add_parser('apply', help="put a preset at the top of a book's lib/book.css")
    s.add_argument('book', help='the book folder, site/<book>')
    s.add_argument('id')
    s.add_argument('--style-json', help='also record the choice in this style.json')
    s.set_defaults(fn=cmd_apply)
    s = sub.add_parser('remove', help="take the preset out of a book's lib/book.css")
    s.add_argument('book')
    s.add_argument('--style-json')
    s.set_defaults(fn=cmd_remove)
    a = p.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
