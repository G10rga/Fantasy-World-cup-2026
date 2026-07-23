#!/usr/bin/env bash
# Render Release Command (optional): flask db upgrade
# Or rely on AUTO_MIGRATE=1 at app boot (default in production).
set -e
flask db upgrade
