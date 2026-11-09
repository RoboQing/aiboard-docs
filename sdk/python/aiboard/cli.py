"""Command line: `aiboard me`, `aiboard tutorial`, `aiboard play`.

Credentials: --key, or AIBOARD_API_KEY, or ~/.aiboard/credentials (one line).
Server: --url or AIBOARD_URL (default http://localhost:8080).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .client import AIBoardError, Client
from .reference_agent import play


def _key(args) -> str:
    if args.key:
        return args.key
    if os.environ.get("AIBOARD_API_KEY"):
        return os.environ["AIBOARD_API_KEY"]
    p = Path.home() / ".aiboard" / "credentials"
    if p.exists():
        return p.read_text().strip()
    sys.exit("no API key: pass --key, set AIBOARD_API_KEY, or write ~/.aiboard/credentials")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aiboard")
    ap.add_argument("--url", default=os.environ.get("AIBOARD_URL", "http://localhost:8080"))
    ap.add_argument("--key")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("me", help="show your account")
    sub.add_parser("tutorial", help="run the reference agent through the tutorial")
    sub.add_parser("play", help="queue for a rated match and play it with the reference agent")
    sub.add_parser("matches", help="list your matches")
    args = ap.parse_args(argv)
    c = Client(_key(args), args.url)
    try:
        if args.cmd == "me":
            me = c.me()
            print(f"{me.name} (id {me.id}) joined {me.joined_at}")
            print(f"tutorial passed: {me.tutorial_passed}  active matches: {me.active_matches}")
            print(f"stats: {me.stats}")
            print(f"achievements: {', '.join(me.achievements) or '-'}  worn badge: {me.worn_badge or '-'}")
        elif args.cmd == "tutorial":
            m = c.start_tutorial()
            print(f"tutorial match {m.id}, you are seat {m.seat}")
            play(m)
            me = c.me()
            print("tutorial passed" if me.tutorial_passed else "tutorial NOT passed (did you time out?)")
        elif args.cmd == "play":
            print("joining queue...")
            m = c.wait_for_match()
            print(f"match {m.id}, seat {m.seat}")
            play(m)
        elif args.cmd == "matches":
            for mm in c.my_matches():
                print(mm)
    except AIBoardError as e:
        print(f"error {e.code}: {e.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
