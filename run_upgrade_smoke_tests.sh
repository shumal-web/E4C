#!/usr/bin/env bash
set -euo pipefail

DB="${1:-${ODOO_DB:-e4c}}"
ODOO_PYTHON="${ODOO_PYTHON:-/opt/odoo19/venv/bin/python}"
ODOO_BIN="${ODOO_BIN:-/opt/odoo19/odoo/odoo-bin}"
ODOO_CONFIG="${ODOO_CONFIG:-/etc/odoo19.conf}"
MODULES="${MODULES:-tf_container_tracking,tf_container_tracking_extends}"
TEST_TAGS="${TEST_TAGS:-tf_upgrade_smoke}"

printf 'Running E4C upgrade smoke tests\n'
printf 'Database: %s\n' "$DB"
printf 'Modules:  %s\n' "$MODULES"
printf 'Tags:     %s\n' "$TEST_TAGS"

"$ODOO_PYTHON" "$ODOO_BIN" \
  -c "$ODOO_CONFIG" \
  -d "$DB" \
  -u "$MODULES" \
  --test-enable \
  --test-tags "$TEST_TAGS" \
  --stop-after-init \
  --no-http

printf 'Smoke tests passed for database: %s\n' "$DB"
