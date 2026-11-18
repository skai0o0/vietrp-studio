"""Structural and security checks for Debian 12 systemd, backup, and Cloudflare Tunnel deploy files."""

from __future__ import annotations

import re
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parents[2] / "deploy"


def _read_deploy(rel_path: str) -> str:
    path = DEPLOY_DIR / rel_path
    assert path.is_file(), f"Missing deploy artifact: {path}"
    return path.read_text(encoding="utf-8")


def test_api_systemd_unit_enforces_single_worker_loopback_and_hardening() -> None:
    unit = _read_deploy("systemd/vietrp-api.service")
    assert "WorkingDirectory=/opt/vietrp/backend" in unit
    assert "EnvironmentFile=/etc/vietrp/vietrp.env" in unit
    assert "ExecStartPre=/opt/vietrp/backend/.venv/bin/alembic" in unit
    assert "upgrade head" in unit
    assert "--host 127.0.0.1" in unit
    assert "--port 7880" in unit
    assert "--workers 1" in unit
    assert "--forwarded-allow-ips=127.0.0.1" in unit
    assert "NoNewPrivileges=yes" in unit
    assert "ProtectSystem=strict" in unit


def test_backup_systemd_service_and_timer_configuration() -> None:
    service = _read_deploy("systemd/vietrp-backup.service")
    timer = _read_deploy("systemd/vietrp-backup.timer")

    assert "Type=oneshot" in service
    assert "EnvironmentFile=/etc/vietrp/vietrp.env" in service
    assert "ExecStart=/bin/bash /opt/vietrp/deploy/scripts/backup.sh" in service
    assert "ReadWritePaths=/var/backups/vietrp" in service

    assert "OnCalendar=" in timer
    assert "Persistent=true" in timer


def test_backup_and_restore_scripts_verify_archives_and_confirm_destructive_restore() -> None:
    backup = _read_deploy("scripts/backup.sh")
    restore = _read_deploy("scripts/restore.sh")
    pg_env = _read_deploy("scripts/pg_env.sh")

    assert "--format=custom" in backup
    assert "--list" in backup
    assert "VIETRP_BACKUP_KEEP" in backup

    assert "VIETRP_CONFIRM_RESTORE" in restore
    assert "--single-transaction" in restore
    assert "vietrp-api.service" in restore

    assert "PGPASSWORD" in pg_env
    assert "DATABASE_URL" in pg_env


def test_deploy_docs_and_env_example_contain_no_secrets_or_quick_tunnels() -> None:
    env_example = _read_deploy("scripts/env.example")
    readme = _read_deploy("README.md")

    assert "VIETRP_ENV=prod" in env_example
    assert "DATABASE_URL=postgresql+asyncpg://vietrp:" in env_example
    assert "VIETRP_SERVER_PEPPER=" in env_example
    assert "VIETRP_SESSION_SECRET=" in env_example
    assert "sk-or-v1-" not in env_example
    assert "trycloudflare.com" not in readme
    assert "sudo git clone" in readme
    assert "/opt/vietrp/src/frontend" in readme
    assert not re.search(r"sk-or-v1-[A-Za-z0-9]{20,}", readme + env_example)
