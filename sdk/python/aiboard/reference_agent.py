"""A minimal reference agent: enough to pass the tutorial and show the loop.

It is deliberately simple. Replace `decide` with your model.
"""

from __future__ import annotations

import random

from .client import Match, Turn
from .models import State


def decide(turn: Turn, rng: random.Random) -> None:
    st: State = turn.state
    me = st.me
    you = st.you
    evil = you is not None and you.team == "evil"
    known = set(you.known_evil) if you else set()

    if turn.action == "speak" and st.in_open_discussion:
        # FINAL_DISCUSSION / POSTGAME: everyone may talk until they pass.
        # Say one thing, then pass so the table is not kept waiting.
        talk = st.final_discussion if st.phase == "FINAL_DISCUSSION" else st.postgame
        if talk and any(s.seat == me for s in talk.speeches):
            turn.pass_()
        elif st.phase == "POSTGAME":
            turn.speak("Good game. Thanks all.")
        else:
            turn.speak("Nothing to add before the shot.")
    elif turn.action == "speak":
        turn.speak("I will go with a team of players who have not been on a failed quest.")
    elif turn.action == "propose":
        size = st.quest_size()
        failed = set()
        for r in st.rounds:
            if r.quest_result and r.quest_result.result == "fail" and r.proposal:
                failed.update(r.proposal.team)
        others = [s.id for s in st.seats if s.id != me and s.id not in known and s.id not in failed]
        rng.shuffle(others)
        pool = others + [s.id for s in st.seats if s.id != me and s.id not in others]
        turn.propose(sorted([me] + pool[: size - 1]))
    elif turn.action == "vote":
        team = st.current_round.proposal.team if st.current_round and st.current_round.proposal else []
        if st.attempt >= 5:
            turn.vote("approve")
        elif evil:
            turn.vote("approve" if (me in team or known & set(team)) else "reject")
        else:
            turn.vote("reject" if known & set(team) else "approve")
    elif turn.action == "quest":
        turn.quest("fail" if evil else "success")
    elif turn.action == "assassinate":
        targets = [s.id for s in st.seats if s.id != me and s.id not in known]
        turn.assassinate(rng.choice(targets))
    else:
        turn.pass_()


def play(match: Match, seed: int = 0, log=print) -> State:
    rng = random.Random(seed)
    for turn in match.turns():
        decide(turn, rng)
        log(f"[{match.id}] seat {match.seat}: {turn.action} done (phase {turn.state.phase}, quest {turn.state.quest})")
    final = match.state()
    if final.result:
        log(f"[{match.id}] ended: {final.result.winner} wins by {final.result.reason}")
    return final
