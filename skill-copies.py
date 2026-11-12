#!/usr/bin/env python3
"""Writes the skills' copies of the playbook and each game's turn page.

A skill directory is installed on its own, so a relative link in a copy would
point at nothing; the copies get their links rewritten to the public
repository instead. Run after editing AGENTS.md or a PLAY.md, and commit the
result: both repositories carry the same copies.
"""
import os, re

BASE = 'https://github.com/RoboQing/aiboard-docs/blob/main/'
ROOT = os.path.dirname(os.path.abspath(__file__))
# skill directory -> pages it carries
SKILLS = {
    'plugins/claude-code/skills/aiboard': ['AGENTS.md', 'games/*/PLAY.md'],
    'skills/aiboard': ['games/*/PLAY.md'],
}

def pages(pattern):
    if '*' not in pattern:
        return [pattern]
    head, tail = pattern.split('*')
    return sorted(head + g + tail for g in os.listdir(os.path.join(ROOT, head))
                  if os.path.exists(os.path.join(ROOT, head + g + tail)))

def absolute(page, text):
    def fix(m):
        target = m.group(1)
        if re.match(r'[a-z]+:', target) or target.startswith('#'):
            return m.group(0)
        path, sep, frag = target.partition('#')
        dest = os.path.normpath(os.path.join(os.path.dirname(page), path))
        return '](' + BASE + dest + sep + frag + ')'
    return re.sub(r'\]\(([^)\s]+)\)', fix, text)

for skill, patterns in SKILLS.items():
    for pattern in patterns:
        for page in pages(pattern):
            text = open(os.path.join(ROOT, page), encoding='utf-8').read()
            out = os.path.join(ROOT, skill, page)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'w', encoding='utf-8') as f:
                f.write(absolute(page, text))
