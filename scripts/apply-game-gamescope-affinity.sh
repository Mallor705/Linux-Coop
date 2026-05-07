#!/usr/bin/env bash

# Usage:
#   ./apply-game-gamescope-affinity.sh 'game_name.exe'
#
# The argument (exact process name) is mandatory.

if [ -z "$1" ]; then
  echo "Error: you must provide the exact process name."
  echo "Usage: $0 <process>"
  echo "Example: $0 'enshrouded.exe'"
  exit 1
fi

PATTERN="$1"

# Processes that should be ignored in the listing.
# Always use lowercase here.
BLACKLIST=(
  "xalia"
)

GAME_PIDS=()
GAME_CMDS=()
GAMESCOPE_PIDS=()

is_blacklisted() {
  local cmd_lower
  cmd_lower=$(echo "$1" | tr '[:upper:]' '[:lower:]')

  for item in "${BLACKLIST[@]}"; do
    if [[ "$cmd_lower" == *"$item"* ]]; then
      return 0
    fi
  done

  return 1
}

find_gamescope_parent() {
  local p="$1"

  while [ "$p" != "1" ] && [ -n "$p" ]; do
    local comm
    comm=$(ps -p "$p" -o comm= 2>/dev/null)

    if [ "$comm" = "gamescope" ] || [ "$comm" = "gamescope-wl" ]; then
      echo "$p"
      return
    fi

    p=$(ps -p "$p" -o ppid= 2>/dev/null | tr -d ' ')
  done
}

collect_children_recursive() {
  local parent="$1"
  echo "$parent"

  for child in $(pgrep -P "$parent"); do
    collect_children_recursive "$child"
  done
}

short_name() {
  local cmd="$1"

  local exe
  exe=$(echo "$cmd" | grep -oE '[^ /\\]+\.exe' | tail -n 1)

  if [ -n "$exe" ]; then
    echo "$exe"
  else
    echo "$cmd" | cut -c1-80
  fi
}

echo "Searching for games with exact process name:"
echo "  $PATTERN"
echo

# Exact search by process name
while read -r pid cmd; do
  [ -z "$pid" ] && continue

  if is_blacklisted "$cmd"; then
    continue
  fi

  gs=$(find_gamescope_parent "$pid")

  GAME_PIDS+=("$pid")
  GAME_CMDS+=("$cmd")
  GAMESCOPE_PIDS+=("$gs")
done < <(
  for pid in $(pgrep -x "$PATTERN"); do
    cmd=$(ps -p "$pid" -o args= 2>/dev/null)
    echo "$pid $cmd"
  done
)

if [ "${#GAME_PIDS[@]}" -eq 0 ]; then
  echo "No games found with exact name: $PATTERN"
  echo
  echo "Try passing a process name, for example:"
  echo "  $0 'enshrouded.exe'"
  exit 1
fi

echo "Games found:"
echo

for i in "${!GAME_PIDS[@]}"; do
  num=$((i + 1))
  game_pid="${GAME_PIDS[$i]}"
  game_cmd="${GAME_CMDS[$i]}"
  gs_pid="${GAMESCOPE_PIDS[$i]}"
  name=$(short_name "$game_cmd")

  echo "[$num] $name"
  echo "    Game PID:      $game_pid"
  echo "    Gamescope PID: ${gs_pid:-not found}"
  echo
done

echo "[a] Apply to all"
echo "[q] Quit"
echo

read -rp "Choose which game will have its affinity modified: " choice

if [ "$choice" = "q" ]; then
  echo "Exiting."
  exit 0
fi

read -rp "Enter CPU affinity, e.g.: 0-11, 12-23, 0,2,4,6: " AFF

if [ -z "$AFF" ]; then
  echo "Empty affinity. Exiting."
  exit 1
fi

apply_affinity() {
  local index="$1"

  local game_pid="${GAME_PIDS[$index]}"
  local gs_pid="${GAMESCOPE_PIDS[$index]}"
  local game_cmd="${GAME_CMDS[$index]}"
  local name
  name=$(short_name "$game_cmd")

  echo
  echo "Applying affinity:"
  echo "  Game:       $name"
  echo "  Game PID:   $game_pid"
  echo "  Gamescope:  ${gs_pid:-not found}"
  echo "  CPUs:       $AFF"
  echo

  if [ -n "$gs_pid" ]; then
    echo "Applying to the gamescope tree..."
    for proc in $(collect_children_recursive "$gs_pid"); do
      taskset -acp "$AFF" "$proc" >/dev/null 2>&1
    done
  else
    echo "Gamescope not found for this game. Applying only to the game process."
  fi

  echo "Applying directly to the game..."
  taskset -acp "$AFF" "$game_pid" >/dev/null 2>&1

  echo "Done for: $name"
}

if [ "$choice" = "a" ]; then
  for i in "${!GAME_PIDS[@]}"; do
    apply_affinity "$i"
  done

  echo
  echo "Affinity applied to all found games."
  exit 0
fi

if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
  echo "Invalid choice."
  exit 1
fi

index=$((choice - 1))

if [ "$index" -lt 0 ] || [ "$index" -ge "${#GAME_PIDS[@]}" ]; then
  echo "Number out of range."
  exit 1
fi

apply_affinity "$index"
