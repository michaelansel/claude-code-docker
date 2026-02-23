#!/usr/bin/env bash
set -euo pipefail

# --- Init commands (if any) ---
if [[ -n "${AGENT_INIT:-}" ]]; then
    echo "Running init commands..." >&2
    # AGENT_INIT is base64-encoded JSON array of commands
    DECODED=$(printf '%s' "$AGENT_INIT" | base64 -d)
    # Parse JSON array and execute each command
    while IFS= read -r cmd || [[ -n "$cmd" ]]; do
        [[ -z "$cmd" ]] && continue
        echo "  $cmd" >&2
        eval "$cmd" || {
            echo "Error: Init command failed: $cmd" >&2
            exit 1
        }
    done < <(printf '%s' "$DECODED" | jq -r '.[]' 2>/dev/null)
    echo "Init commands completed." >&2
fi

# --- Plugin updates (all modes) ---
PLUGIN_DIR="$HOME/.claude/plugins"

if [[ -d "$PLUGIN_DIR" ]] && ls "$PLUGIN_DIR"/ >/dev/null 2>&1; then
    echo "Updating plugins..." >&2

    # Discover unique marketplace names from plugin dirs (<name>@<marketplace>)
    marketplaces=()
    for dir in "$PLUGIN_DIR"/*/; do
        name=$(basename "$dir")
        if [[ "$name" == *@* ]]; then
            mp="${name##*@}"
            if [[ ! " ${marketplaces[*]:-} " =~ " ${mp} " ]]; then
                marketplaces+=("$mp")
            fi
        fi
    done

    for mp in ${marketplaces[@]+"${marketplaces[@]}"}; do
        claude plugin marketplace update "$mp" 2>/dev/null || true
    done

    for dir in "$PLUGIN_DIR"/*/; do
        plugin=$(basename "$dir")
        if [[ "$plugin" == *@* ]]; then
            claude plugin update "$plugin" 2>/dev/null || true
        fi
    done
fi

# --- C3PO credential check (agent mode only) ---
if [[ "${CLAUDE_AGENT_MODE:-}" == "1" ]]; then
    CREDS_FILE="$HOME/.claude/c3po-credentials.json"
    if [[ -f "$CREDS_FILE" ]]; then
        coordinator_url=$(jq -r '.coordinator_url' "$CREDS_FILE")
        api_token=$(jq -r '.api_token' "$CREDS_FILE")
        machine_name=$(jq -r '.machine_name // "docker"' "$CREDS_FILE")
        if [[ -n "$coordinator_url" && "$coordinator_url" != "null" &&
              -n "$api_token" && "$api_token" != "null" ]]; then
            echo "Checking c3po credentials..." >&2
            status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
                -H "Authorization: Bearer $api_token" \
                "$coordinator_url/agent/api/validate?machine_name=$machine_name" 2>/dev/null) || true
            if [[ "$status" == "000" ]]; then
                echo "ERROR: could not reach c3po coordinator at $coordinator_url" >&2
                exit 1
            elif [[ "$status" == "403" ]]; then
                echo "ERROR: c3po token does not authorize $machine_name agents. Re-run setup-c3po with a $machine_name/* scoped key." >&2
                exit 1
            elif [[ ! "$status" =~ ^2 ]]; then
                echo "ERROR: c3po coordinator returned HTTP $status. Re-run setup-c3po or check coordinator health." >&2
                exit 1
            fi
        else
            echo "ERROR: c3po credentials file is incomplete. Re-run setup-c3po." >&2
            exit 1
        fi
    else
        echo "ERROR: c3po credentials not found. Run setup-c3po first." >&2
        exit 1
    fi
fi

echo "Launching claude..." >&2
claude --dangerously-skip-permissions "$@"
_claude_exit=$?
exit $_claude_exit
