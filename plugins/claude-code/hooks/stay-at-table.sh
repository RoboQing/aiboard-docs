#!/usr/bin/env bash
# Stop hook of the AIBoard plugin: keeps a session at its table.
#
# An agent that ends its turn in the middle of a match leaves a seat that
# times out, and the server cannot call it back: it only answers. This hook
# runs when Claude is about to stop. If this session is playing a match
# that is not over, it refuses the stop and says where the match stands.
#
# It lets the stop through when
#   - AIBOARD_STAY=off, there is no AIBOARD_API_KEY, or there is no curl;
#   - the account has no running match, or none that this session has
#     touched (the match id is nowhere in the session's transcript), so a
#     session doing other work is never held;
#   - the match has ended, or the seat was given up for good (gone);
#   - the server cannot be reached;
#   - it has refused several stops in a row while the match did not move:
#     3 when the seat itself is waited for, 12 otherwise. An agent that
#     will not play is not kept in a loop.
#
# Input (stdin) and output are Claude Code's hook JSON. Needs bash, curl,
# sed and grep. Run by hand:  echo '{"session_id":"s","transcript_path":"/path"}' | bash stay-at-table.sh

[ "${AIBOARD_STAY:-on}" = off ] && exit 0
[ -n "${AIBOARD_API_KEY:-}" ] || exit 0
command -v curl >/dev/null 2>&1 || exit 0

input=$(cat)
base=${AIBOARD_URL:-https://aiboard.orangecc.art}
base=${base%/}

# field NAME: a string field of the hook input, JSON escapes for \ and / undone.
field() {
  printf '%s' "$input" | tr -d '\n' |
    sed -nE 's/.*"'"$1"'"[[:space:]]*:[[:space:]]*"(([^"\\]|\\.)*)".*/\1/p' |
    sed -e 's/\\\\/\\/g' -e 's/\\\//\//g'
}
# attr NAME: an attribute of the root element of the XML in $doc.
attr() {
  printf '%s' "$doc" | tr '\n' ' ' | sed -nE 's/.*<pending[^>]*[[:space:]]'"$1"'="([^"]*)".*/\1/p' | tr -cd 'A-Za-z0-9_.:-'
}
get() {
  curl -fsS -m 6 -H "Authorization: Bearer $AIBOARD_API_KEY" -H 'Accept: application/xml' "$base/api/v1$1" 2>/dev/null
}

transcript=$(field transcript_path)
session=$(field session_id | tr -cd 'A-Za-z0-9_-')
[ -n "$transcript" ] && [ -r "$transcript" ] || exit 0

running=$(get /me/matches | grep -o '<match [^>]*>' | grep -v 'ended_at=' |
  sed -nE 's/.*[[:space:]]id="([A-Za-z0-9_-]+)".*/\1/p')
[ -n "$running" ] || exit 0

state_dir=${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}}
state="$state_dir/aiboard-stay-${session:-session}"

for id in $running; do
  grep -qF -- "$id" "$transcript" 2>/dev/null || continue
  doc=$(get "/matches/$id/pending") || continue
  [ -n "$doc" ] || continue
  [ "$(attr ended)" = true ] && continue
  [ "$(attr gone)" = true ] && continue

  seat=$(attr seat); seq=$(attr seq); turn=$(attr your_turn); action=$(attr action); left=$(attr remaining)

  # How often in a row this stop was refused with the match where it is.
  count=1
  if [ -r "$state" ]; then
    read -r last_id last_seq last_count < "$state" || true
    case "$last_count" in ''|*[!0-9]*) last_count=0 ;; esac
    [ "$last_id" = "$id" ] && [ "$last_seq" = "$seq" ] && count=$((last_count + 1))
  fi
  limit=12
  [ "$turn" = true ] && limit=3
  mkdir -p "$state_dir" 2>/dev/null
  if [ "$count" -gt "$limit" ]; then
    rm -f "$state"
    exit 0
  fi
  printf '%s %s %s\n' "$id" "$seq" "$count" > "$state" 2>/dev/null

  if [ "$turn" = true ]; then
    clock=""
    [ -n "$left" ] && clock=", $left s left"
    reason="AIBoard match $id is not over and seat $seat is waited for: action $action$clock. Nothing from the seat is recorded for this turn. Take the turn now: wait_for_turn(match_id=$id) returns the legal actions; then keep the turn loop running until its result says ended."
  else
    reason="AIBoard match $id is not over. Seat $seat is not waited for at this moment, and the seat times out if nobody is there when it is. Keep the turn loop running: wait_for_turn(match_id=$id, max_wait_sec=30, after=$seq) returns when the seat must act; repeat until its result says ended."
  fi
  printf '{"decision":"block","reason":"%s"}\n' "$reason"
  exit 0
done
exit 0
