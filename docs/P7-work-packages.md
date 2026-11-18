# P7 — Deploy, Mobile & E-ink Verification, and Live OpenRouter E2E: work packages

Phase goal (`KIEN-TRUC-VIETRP.md` §13, `AGENTS.md` §6–§7):
- Verify Debian 12 + systemd + PostgreSQL 17 + Cloudflare Tunnel deployment artifacts in `deploy/` (`vietrp-api.service`, `vietrp-backup.service`, `vietrp-backup.timer`, `backup.sh`, `restore.sh`, `pg_env.sh`, `env.example`, `deploy/README.md`) and SPA static serving in `backend/app/main.py`.
- Add automated verification tests for deployment configuration invariants (`backend/tests/test_deploy_artifacts.py`) and mobile (`375px`) + E-ink / OLED Neon theme invariants (`frontend/src/styles/themeEinkMobile.test.tsx`).
- Build the frontend bundle (`frontend/dist`) and execute end-to-end live verification against OpenRouter (`scripts/dev/smoke_live_openrouter.py`, `smoke_single_chat.py`, `smoke_world_chat.py`) covering P2 through P7 including reasoning streaming and per-chat lorebook configuration.
- Run final full backend and frontend quality gates, rule greps, and read-only checks on reference folders.

## Work Packages

| WP | Owner role | Scope |
|---|---|---|
| **WP-D7** | lead / ops | Review `deploy/` units, timer, backup/restore scripts, sync `deploy/README.md` paths to the git repo root, and add `backend/tests/test_deploy_artifacts.py`. |
| **WP-UI7** | lead / frontend | Verify E-ink (`--glow: none`, serif `--font-content`, `--motion: 0`), OLED Neon (`--bg: 0 0 0`), `useReducedMotion`, and mobile (`375px`) vs desktop (`1440px`) responsive layout & chat components in `frontend/src/styles/themeEinkMobile.test.tsx`. |
| **WP-QA7** | lead / qa-runner | Build `frontend/dist`, run live OpenRouter E2E smoke test (`P2-P7`), run full BE/FE quality gates + rule greps, and update `docs/PROGRESS.md`. |
