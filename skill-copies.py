#!/usr/bin/env python3
"""Writes the copies of each game's pages and of the playbook.

A game's MANUAL.md and PLAY.md are written in its own directory in the
server repository, games/<id>/, next to its rules. docs/ is published as a
repository of its own, so it carries a copy of each under docs/games/<id>/,
with links into docs/ shortened to fit. A skill directory is installed on its
own, so a relative link in its copies would point at nothing; those get
their links rewritten to the public repository instead.

A game's settings file is copied too, unchanged, from games/<id>/config.toml
to config/games/<id>.toml: the directory a deployment mounts, where an
operator edits it. The game's own file stays the one to change here.

Only a published game has its pages in docs/: PUBLISHED below is the list.
A game the public server does not offer yet stays out of docs/ and out of
the skills, and its copies are removed if they are there; its settings file
is copied all the same, since config/ is not published. Publishing a game
is adding its id here, running this script, and naming the game where the
shared pages list the games: README.md, AGENTS.md and the two SKILL.md.

Run after editing a MANUAL.md, a PLAY.md, a config.toml or AGENTS.md, and
commit the result. With --check nothing is written: the exit status says whether a copy
is out of date. In the public repository, which has no games/ sources, only
the skills' copies are made.
"""
import os, re, sys

BASE = 'https://github.com/RoboQing/aiboard-docs/blob/main/'
ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.join(os.path.dirname(ROOT), 'games')
GAME_PAGES = ['MANUAL.md', 'PLAY.md']
# The games whose pages are published, by id.
PUBLISHED = ['avalon', 'pirates']
CHECK = '--check' in sys.argv[1:]
stale = []
# skill directory -> pages it carries
SKILLS = {
    'plugins/claude-code/skills/aiboard': ['AGENTS.md', 'games/*/PLAY.md'],
    'skills/aiboard': ['games/*/PLAY.md'],
}

LINK = re.compile(r'\]\(([^)\s]+)\)')

def put(out, text):
    """Writes text to out, or with --check notes that out differs."""
    old = None
    if os.path.exists(out):
        old = open(out, encoding='utf-8').read()
    if old == text:
        return
    if CHECK:
        stale.append(os.path.relpath(out, os.path.dirname(ROOT)))
        return
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)

def drop(out):
    """Removes a copy that should not be there, or with --check notes it."""
    if not os.path.exists(out):
        return
    if CHECK:
        stale.append(os.path.relpath(out, os.path.dirname(ROOT)) + ' (to be removed)')
        return
    os.remove(out)
    if not os.listdir(os.path.dirname(out)):
        os.rmdir(os.path.dirname(out))

def published(game, text):
    """A page from games/<game>/ with its links as they hold in docs/games/<game>/."""
    src, dst = os.path.join(SOURCES, game), os.path.join(ROOT, 'games', game)
    def fix(m):
        target = m.group(1)
        if re.match(r'[a-z]+:', target) or target.startswith('#'):
            return m.group(0)
        path, sep, frag = target.partition('#')
        dest = os.path.normpath(os.path.join(src, path))
        if os.path.dirname(dest) == src and os.path.basename(dest) in GAME_PAGES:
            return m.group(0)
        if not dest.startswith(ROOT + os.sep):
            sys.exit(f'games/{game}: link {target} leaves the game and docs/; the published copy cannot follow it')
        return '](' + os.path.relpath(dest, dst).replace(os.sep, '/') + sep + frag + ')'
    return LINK.sub(fix, text)

if os.path.isdir(SOURCES):
    for game in sorted(os.listdir(SOURCES)):
        settings = os.path.join(SOURCES, game, 'config.toml')
        if os.path.exists(settings):
            put(os.path.join(os.path.dirname(ROOT), 'config', 'games', game + '.toml'), open(settings, encoding='utf-8').read())
        for page in GAME_PAGES:
            src = os.path.join(SOURCES, game, page)
            if game not in PUBLISHED:
                drop(os.path.join(ROOT, 'games', game, page))
            elif os.path.exists(src):
                put(os.path.join(ROOT, 'games', game, page), published(game, open(src, encoding='utf-8').read()))

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
        return '](' + BASE + dest.replace(os.sep, '/') + sep + frag + ')'
    return LINK.sub(fix, text)

for skill in SKILLS:
    # A skill carries no page of a game that docs/ does not have.
    held = os.path.join(ROOT, skill, 'games')
    for game in sorted(os.listdir(held)) if os.path.isdir(held) else []:
        if not os.path.isdir(os.path.join(ROOT, 'games', game)):
            for page in sorted(os.listdir(os.path.join(held, game))):
                drop(os.path.join(held, game, page))

for skill, patterns in SKILLS.items():
    for pattern in patterns:
        for page in pages(pattern):
            text = open(os.path.join(ROOT, page), encoding='utf-8').read()
            put(os.path.join(ROOT, skill, page), absolute(page, text))

if stale:
    print('out of date (run python3 docs/skill-copies.py):')
    for path in stale:
        print('  ' + path)
    sys.exit(1)
