#!/usr/bin/env python3
"""Reports relative Markdown links that point at a missing file or heading.

Run from either repository: in the server repo it checks docs/, in the public
repo (whose root is a copy of docs/) the root. The two trees have the same
layout, so a link that passes here passes there.
"""
import os, re, sys

LINK = re.compile(r'\]\(([^)\s]+)\)')

def anchors(path):
    out = set()
    for line in open(path, encoding='utf-8'):
        m = re.match(r'#+\s+(.*)', line)
        if m:
            h = re.sub(r'[^\w\s-]', '', m.group(1).strip().lower())
            out.add(re.sub(r'\s', '-', h))
    return out

def main(root):
    bad = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
        for f in files:
            if not f.endswith('.md'):
                continue
            src = os.path.join(dirpath, f)
            for n, line in enumerate(open(src, encoding='utf-8'), 1):
                for target in LINK.findall(line):
                    if re.match(r'[a-z]+:', target) or target.startswith('#'):
                        continue
                    path, _, frag = target.partition('#')
                    dest = os.path.normpath(os.path.join(dirpath, path))
                    if not os.path.exists(dest):
                        print(f'{src}:{n}: missing {target}'); bad += 1
                    elif frag and dest.endswith('.md') and frag not in anchors(dest):
                        print(f'{src}:{n}: no heading #{frag} in {path}'); bad += 1
    return 1 if bad else 0

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else here))
