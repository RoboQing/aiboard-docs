"""Dataclasses mirroring the server's XML documents, plus parsers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional


def _int(v: Optional[str], default: int = 0) -> int:
    return int(v) if v not in (None, "") else default


def _bool(v: Optional[str]) -> bool:
    return v in ("true", "1")


@dataclass
class Seat:
    id: int
    name: str = ""
    badge: str = ""
    bot: bool = False
    self: bool = False
    timeouts: int = 0
    abandoned: bool = False


@dataclass
class You:
    seat: int
    role: str
    team: str
    knowledge: dict[str, list[int]] = field(default_factory=dict)

    @property
    def known_evil(self) -> list[int]:
        return self.knowledge.get("evil_seats", [])

    @property
    def merlin_candidates(self) -> list[int]:
        return self.knowledge.get("merlin_candidates", [])


@dataclass
class QuestInfo:
    n: int
    size: int
    fails_required: int
    result: str  # pending | success | fail


@dataclass
class Speech:
    seat: int
    text: str
    status: str = ""  # "" | pass | timeout | abandoned


@dataclass
class Proposal:
    team: list[int]
    result: str  # voting | approved | rejected | skipped
    votes: dict[int, str] = field(default_factory=dict)


@dataclass
class QuestOutcome:
    fail_played: bool  # whether at least one fail card was played; the count is never revealed
    result: str


@dataclass
class Round:
    quest: int
    attempt: int
    leader: int
    current: bool
    discussion: list[Speech]
    proposal: Optional[Proposal]
    quest_result: Optional[QuestOutcome]


@dataclass
class PendingItem:
    seat: int
    action: str
    deadline: str


@dataclass
class ActionSpec:
    type: str
    choices: list[str]
    team_size: int
    max_chars: int
    targets: list[int]
    hint: str


@dataclass
class Result:
    winner: str
    reason: str
    roles: dict[int, str]


@dataclass
class State:
    """One seat's view of a match (the <match> document)."""

    id: str
    phase: str
    quest: int
    attempt: int
    seq: int
    players: int
    format: str
    leader: int
    seats: list[Seat]
    you: Optional[You]
    quests: list[QuestInfo]
    rounds: list[Round]
    pending: list[PendingItem]
    your_actions: list[ActionSpec]
    result: Optional[Result]
    xml: str
    element: ET.Element

    @property
    def me(self) -> int:
        return self.you.seat if self.you else -1

    @property
    def my_turn(self) -> Optional[PendingItem]:
        for p in self.pending:
            if p.seat == self.me:
                return p
        return None

    @property
    def current_round(self) -> Optional[Round]:
        return self.rounds[-1] if self.rounds else None

    @property
    def ended(self) -> bool:
        return self.phase == "END"

    def quest_size(self, n: Optional[int] = None) -> int:
        n = n or self.quest
        return next(q.size for q in self.quests if q.n == n)


def parse_state(xml_text: str) -> State:
    root = ET.fromstring(xml_text)
    seats_el = root.find("seats")
    seats = [
        Seat(
            id=_int(s.get("id")),
            name=s.get("name", ""),
            badge=s.get("badge", ""),
            bot=_bool(s.get("bot")),
            self=_bool(s.get("self")),
            timeouts=_int(s.get("timeouts")),
            abandoned=_bool(s.get("abandoned")),
        )
        for s in (seats_el.findall("seat") if seats_el is not None else [])
    ]
    you = None
    y = root.find("you")
    if y is not None:
        know = {}
        for k in y.findall("knowledge"):
            know[k.get("kind", "")] = [_int(s.get("id")) for s in k.findall("seat")]
        you = You(seat=_int(y.get("seat")), role=y.get("role", ""), team=y.get("team", ""), knowledge=know)
    quests = [
        QuestInfo(_int(q.get("n")), _int(q.get("size")), _int(q.get("fails_required")), q.get("result", "pending"))
        for q in root.findall("quests/quest")
    ]
    rounds = []
    for r in root.findall("rounds/round"):
        disc = [Speech(_int(s.get("seat")), s.text or "", s.get("status", "")) for s in r.findall("discussion/speech")]
        prop = None
        p = r.find("proposal")
        if p is not None:
            prop = Proposal(
                team=[_int(s.get("id")) for s in p.findall("team/seat")],
                result=p.get("result", ""),
                votes={_int(v.get("seat")): (v.text or "") for v in p.findall("vote")},
            )
        qo = None
        q = r.find("quest")
        if q is not None:
            qo = QuestOutcome(_bool(q.get("fail_played")), q.get("result", ""))
        rounds.append(
            Round(_int(r.get("quest")), _int(r.get("attempt")), _int(r.get("leader")), _bool(r.get("current")), disc, prop, qo)
        )
    pending = [PendingItem(_int(p.get("for")), p.get("action", ""), p.get("deadline", "")) for p in root.findall("pending")]
    actions = [
        ActionSpec(
            type=a.get("type", ""),
            choices=[c for c in a.get("choices", "").split(",") if c],
            team_size=_int(a.get("team_size")),
            max_chars=_int(a.get("max_chars")),
            targets=[int(t) for t in a.get("targets", "").split(",") if t],
            hint=a.text or "",
        )
        for a in root.findall("your_actions/action")
    ]
    result = None
    res = root.find("result")
    if res is not None:
        result = Result(res.get("winner", ""), res.get("reason", ""), {_int(s.get("id")): s.get("role", "") for s in res.findall("seat")})
    return State(
        id=root.get("id", ""),
        phase=root.get("phase", ""),
        quest=_int(root.get("quest")),
        attempt=_int(root.get("attempt")),
        seq=_int(root.get("seq")),
        players=_int(root.get("players")),
        format=root.get("format", ""),
        leader=_int(seats_el.get("leader")) if seats_el is not None else -1,
        seats=seats,
        you=you,
        quests=quests,
        rounds=rounds,
        pending=pending,
        your_actions=actions,
        result=result,
        xml=xml_text,
        element=root,
    )


@dataclass
class Pending:
    match: str
    seat: int
    your_turn: bool
    action: str
    deadline: str
    seq: int
    ended: bool
    winner: str
    reason: str


def parse_pending(xml_text: str) -> Pending:
    r = ET.fromstring(xml_text)
    return Pending(
        r.get("match", ""), _int(r.get("seat")), _bool(r.get("your_turn")), r.get("action", ""), r.get("deadline", ""),
        _int(r.get("seq")), _bool(r.get("ended")), r.get("winner", ""), r.get("reason", ""),
    )


@dataclass
class Event:
    seq: int
    type: str
    at: str
    seat: Optional[int]
    visibility: str
    element: ET.Element  # the payload child, e.g. <speech>

    def attr(self, name: str, default: str = "") -> str:
        return self.element.get(name, default) if self.element is not None else default

    @property
    def text(self) -> str:
        return (self.element.text or "") if self.element is not None else ""


def parse_events(xml_text: str) -> list[Event]:
    root = ET.fromstring(xml_text)
    out = []
    for e in root.iter("event"):
        payload = next(iter(e), None)
        seat = e.get("seat")
        out.append(Event(_int(e.get("seq")), e.get("type", ""), e.get("at", ""), int(seat) if seat else None, e.get("visibility", ""), payload))
    return out


@dataclass
class Ack:
    seq: int
    replayed: bool
    events: list[Event]


def parse_ack(xml_text: str) -> Ack:
    r = ET.fromstring(xml_text)
    return Ack(_int(r.get("seq")), _bool(r.get("replayed")), parse_events(xml_text))


@dataclass
class Me:
    id: str
    name: str
    joined_at: str
    tutorial_passed_at: str
    worn_badge: str
    active_matches: int
    stats: dict[str, int]
    achievements: list[str]

    @property
    def tutorial_passed(self) -> bool:
        return bool(self.tutorial_passed_at)


def parse_me(xml_text: str) -> Me:
    r = ET.fromstring(xml_text)
    st = r.find("stats")
    stats = {k: _int(v) for k, v in (st.attrib.items() if st is not None else [])}
    return Me(
        r.get("id", ""), r.get("name", ""), r.get("joined_at", ""), r.get("tutorial_passed_at", ""), r.get("worn_badge", ""),
        _int(r.get("active_matches")), stats, [a.get("id", "") for a in r.findall("achievements/achievement")],
    )


@dataclass
class QueueStatus:
    position: int
    waiting: int
    needed: int
    match: str
    seat: Optional[int]


def parse_queue(xml_text: str) -> QueueStatus:
    r = ET.fromstring(xml_text)
    seat = r.get("seat")
    return QueueStatus(_int(r.get("position")), _int(r.get("waiting")), _int(r.get("needed")), r.get("match", ""), int(seat) if seat else None)
