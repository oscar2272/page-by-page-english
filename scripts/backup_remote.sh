#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_dir="${PBP_BACKUP_DIR:-$project_dir/backups}"
server_host="${PBP_HOST:-161.33.169.174}"
ssh_key="${PBP_KEY:-$HOME/.ssh/page-by-page-oci}"
timestamp="$(date +%Y%m%d-%H%M%S)"
destination="$backup_dir/page-by-page-$timestamp.tar.gz"

umask 077
mkdir -p "$backup_dir"
temporary="$(mktemp "$backup_dir/.page-by-page-XXXXXXXX.tar.gz")"
trap 'rm -f "$temporary"' EXIT

ssh -i "$ssh_key" "ubuntu@$server_host" \
  'sudo python3 /home/ubuntu/page-by-page/scripts/remote_backup.py' \
  > "$temporary"
tar -tzf "$temporary" > /dev/null
mv "$temporary" "$destination"
trap - EXIT
printf '%s\n' "$destination"
