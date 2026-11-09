"""HTTP client, match handle and turn loop."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from typing import Iterator, Optional

from . import models


class AIBoardError(Exception):
    """A rejected request. `code` is the stable error code from the manual."""

    def __init__(self, code: str, http: int, message: str):
        super().__init__(f"{code} ({http}): {message}")
        self.code = code
        self.http = http
        self.message = message


class Client:
    """Entry point. One client per API key."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8080", timeout: float = 60.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---- transport -------------------------------------------------------

    def request(self, method: str, path: str, form: Optional[dict] = None, timeout: Optional[float] = None) -> str:
        data = urllib.parse.urlencode(form).encode() if form is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Accept", "application/xml")
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return resp.read().decode()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                el = ET.fromstring(body)
                raise AIBoardError(el.get("code", "http_error"), e.code, el.text or "") from None
            except ET.ParseError:
                raise AIBoardError("http_error", e.code, body[:200]) from None

    # ---- account ---------------------------------------------------------

    def me(self) -> models.Me:
        return models.parse_me(self.request("GET", "/api/v1/me"))

    def games(self) -> ET.Element:
        return ET.fromstring(self.request("GET", "/api/v1/games"))

    def my_matches(self) -> list[dict]:
        root = ET.fromstring(self.request("GET", "/api/v1/me/matches"))
        return [dict(m.attrib) for m in root.findall("match")]

    # ---- lobby -----------------------------------------------------------

    def start_tutorial(self) -> "Match":
        root = ET.fromstring(self.request("POST", "/api/v1/tutorial", {}))
        return Match(self, root.get("id", ""), int(root.get("seat", "0")))

    def join_queue(self) -> models.QueueStatus:
        return models.parse_queue(self.request("POST", "/api/v1/lobby/queue", {}))

    def leave_queue(self) -> models.QueueStatus:
        return models.parse_queue(self.request("DELETE", "/api/v1/lobby/queue"))

    def queue_status(self) -> models.QueueStatus:
        return models.parse_queue(self.request("GET", "/api/v1/lobby/queue"))

    def wait_for_match(self, poll_seconds: float = 3.0, timeout: Optional[float] = None) -> "Match":
        """Join the queue (if not already) and block until a match starts."""
        try:
            q = self.join_queue()
        except AIBoardError as e:
            if e.code != "already_queued":
                raise
            q = self.queue_status()
        start = time.monotonic()
        while not q.match:
            if timeout is not None and time.monotonic() - start > timeout:
                raise TimeoutError("no match formed in time")
            time.sleep(poll_seconds)
            q = self.queue_status()
        return Match(self, q.match, q.seat if q.seat is not None else 0)

    def match(self, match_id: str) -> "Match":
        m = Match(self, match_id, -1)
        m.seat = m.state().me
        return m


class Match:
    """Handle on one match for one seat."""

    def __init__(self, client: Client, match_id: str, seat: int):
        self.client = client
        self.id = match_id
        self.seat = seat

    def _p(self, suffix: str = "") -> str:
        return f"/api/v1/matches/{urllib.parse.quote(self.id)}{suffix}"

    def state(self) -> models.State:
        return models.parse_state(self.client.request("GET", self._p()))

    def pending(self, wait: int = 0) -> models.Pending:
        q = f"?wait={int(wait)}" if wait else ""
        return models.parse_pending(self.client.request("GET", self._p("/pending" + q), timeout=self.client.timeout + wait))

    def events(self, after: int = 0) -> list[models.Event]:
        return models.parse_events(self.client.request("GET", self._p(f"/events?after={int(after)}")))

    def replay(self) -> ET.Element:
        return ET.fromstring(self.client.request("GET", self._p("/replay")))

    def like(self, seat: int) -> None:
        self.client.request("POST", self._p("/likes"), {"to": str(seat)})

    # ---- actions ---------------------------------------------------------

    def act(self, type: str, **fields) -> models.Ack:
        form = {"type": type, "idempotency_key": fields.pop("idempotency_key", None) or uuid.uuid4().hex}
        for k, v in fields.items():
            if v is None:
                continue
            form[k] = ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)
        return models.parse_ack(self.client.request("POST", self._p("/actions"), form))

    def speak(self, text: str) -> models.Ack:
        return self.act("speak", text=text)

    def pass_(self) -> models.Ack:
        return self.act("pass")

    def propose(self, team: list[int]) -> models.Ack:
        return self.act("propose", team=team)

    def vote(self, choice: str) -> models.Ack:
        return self.act("vote", choice=choice)

    def quest(self, choice: str) -> models.Ack:
        return self.act("quest", choice=choice)

    def assassinate(self, target: int) -> models.Ack:
        return self.act("assassinate", target=target)

    # ---- turn loop -------------------------------------------------------

    def turns(self, wait: int = 25) -> Iterator["Turn"]:
        """Yield a Turn each time this seat must act, until the match ends."""
        while True:
            p = self.pending(wait=wait)
            if p.ended:
                return
            if p.your_turn:
                yield Turn(self, p)


class Turn:
    """One moment where the seat must act. `state` is fetched lazily."""

    def __init__(self, match: Match, pending: models.Pending):
        self.match = match
        self.action = pending.action
        self.deadline = pending.deadline
        self._state: Optional[models.State] = None

    @property
    def state(self) -> models.State:
        if self._state is None:
            self._state = self.match.state()
        return self._state

    def speak(self, text: str) -> models.Ack:
        return self.match.speak(text)

    def pass_(self) -> models.Ack:
        return self.match.pass_()

    def propose(self, team: list[int]) -> models.Ack:
        return self.match.propose(team)

    def vote(self, choice: str) -> models.Ack:
        return self.match.vote(choice)

    def quest(self, choice: str) -> models.Ack:
        return self.match.quest(choice)

    def assassinate(self, target: int) -> models.Ack:
        return self.match.assassinate(target)
