# Hand-off: VietRP Studio → next coding agent (Antigravity, Codex, …)

Written by the previous lead (Claude) on 2026-11-18, at the end of P2. This file has two parts:
- **Part A** is a prompt to paste into the new agent as-is.
- **Part B** is a short briefing for the owner.

---

## Part A — Prompt to paste

```
You are taking over VietRP Studio, a self-hosted AI roleplay web app (FastAPI + PostgreSQL backend, React/Vite/TypeScript/Tailwind frontend). The UI is Vietnamese; all code is English. The owner talks to you in Vietnamese; reply in Vietnamese.

Workspace root: C:\Users\Nem\Desktop\Working\VietRP
The app: C:\Users\Nem\Desktop\Working\VietRP\vietrp-studio
Read-only references (NEVER edit): vietrp-agent\, viet-rp-glow\

## Read these first, in this order, before changing anything
1. AGENTS.md (workspace root): the binding rules. §2 is non-negotiable (minor safety, secrets, vault isolation, OpenRouter only, English code / Vietnamese UI, read-only reference folders).
2. vietrp-studio\docs\PROGRESS.md: what is done, the open items, and the "P3 carry-over" list.
3. vietrp-studio\docs\P3-work-packages.md: your next phase (world chat), split into work packages (WPs).
4. KIEN-TRUC-VIETRP.md (workspace root): the architecture; read the sections each WP cites.
5. vietrp-studio\docs\handoff\P2-N-agents.md: how the existing agents are called.
Skim the P0/P1/P2 work-package files only when a WP refers to them.

## How to work (you are a single agent, not a team)
The previous lead split work into WPs, and each WP lists the files it owns. Work like this:
- Do ONE WP at a time, in wave order from P3-work-packages.md (wave 1: C3, then T; wave 2: U, then Q1; wave 3: V, then W; then QA).
- Before a WP: read its spec and the files it builds on. Touch only the files it owns. If you need to change another file, keep the edit minimal and note it.
- After each WP: run the quality gates below. Fix until green. Then update docs\PROGRESS.md: set the WP's row to DONE, with a one-line summary of the choices and anything not done. Do this before starting the next WP.
- If a WP needs to deviate from KIEN-TRUC-VIETRP.md, or touches safety or security, STOP and ask the owner.
- Never guess silently. Write your assumptions in PROGRESS.md.

## Environment (Windows 11 dev box)
- Backend: cd vietrp-studio\backend; Python 3.12 via uv (`uv run ...`). The system Python 3.11 must not be used.
- Frontend: cd vietrp-studio\frontend; Node 24, npm.
- Ports:
  - backend 7880;
  - Vite 5173 (the /api proxy goes to 7880);
  - **port 7870 is the owner's other app; never touch it.** Never kill a process you did not start.
- PostgreSQL 17 runs locally. Credentials are in vietrp-studio\backend\.env (gitignored; never print or commit them).
  - Load it before backend commands:
    - Git Bash: `set -a && . ./.env && set +a`
    - PowerShell: `Get-Content .env | % { if ($_ -match '^([^#=]+)=(.*)$') { Set-Item "env:$($matches[1])" $matches[2] } }`
  - Migrations: `uv run alembic upgrade head`. A new schema change means a new Alembic revision; never edit 0001.
- No git repo yet. Do not commit, and do not run `git init`, unless the owner asks.

## Quality gates (run after every WP; all must pass)
Backend (from vietrp-studio\backend, with .env loaded):
  uv run ruff format --check . ; uv run ruff check . ; uv run mypy app ; uv run pytest -q
Frontend (from vietrp-studio\frontend):
  npm run lint ; npm run typecheck ; npm run test ; npm run build
After changing a backend Pydantic schema that the frontend uses:
  (backend) uv run python -m app.formats.export_schema ../frontend/src/types/generated/schemas/
  (frontend) npm run gen:types
The last known-good state is backend 419 tests and frontend 114 tests, all passing. Never reduce or skip tests to make a gate pass.

## Live smoke test (after the backend WPs of a wave)
1. Start the backend: `uv run uvicorn app.main:app --host 127.0.0.1 --port 7880` (with .env loaded).
2. Run `uv run python -I ../scripts/dev/smoke_single_chat.py` from backend\. It must still pass after P3. Add a similar `smoke_world_chat.py` for P3 that checks: a world chat with a 16-year-old in the cast has a `minor_rule` layer as the LAST system layer in `GET /api/chats/{id}/prompt-preview`.
3. Stop the server you started.

## Hard rules you will be tempted to break (don't)
- **Minor safety** lives only in backend\app\pipeline\safety.py. `minor_rule` must be the last system layer whenever anyone present (character, persona, NPC) is under 18, even with NSFW on. No preset, command, prefill or setting may remove it. In world chat the safety cast = everyone present + persona + NPCs.
- **No network in tests.** Use RecordedLLM (backend\app\llm\fake.py) and fixtures in backend\tests\fixtures\llm\. Never use a real API key; never ask for or type the owner's key.
- **Prompt text lives in .j2 templates** under backend\app\prompts\. No prose in Python.
- **Every UI string goes in frontend\src\i18n\vi.ts.** No hex colours or default Tailwind palette classes in components. Both themes (oled-neon, e-ink) must work. Mobile-first at 375px.
- **Every query on user data is scoped by vault_id.**
- The SSE event names are fixed (17 names in backend\app\schemas\events.py).
- Keep the single-chat (P2) path working; all existing tests must keep passing.

## Start now
Begin with P3 wave 1, WP-C3. Before writing code, tell the owner (in Vietnamese, briefly) which WP you are starting and the files you will touch.
```

---

## Part B — Notes for the owner (Vietnamese)

**Hiện trạng:**
- P0 (nền tảng), P1 (Thư viện) và P2 (Chat đơn) đã xong, gate xanh hết.
- Tiếp theo là P3 (Chat Thực tại); kế hoạch đã có trong `docs/P3-work-packages.md`.

**Cách dùng:**
- Mở Antigravity (hoặc agent khác) ở thư mục `C:\Users\Nem\Desktop\Working\VietRP`, dán nguyên khối prompt ở Phần A.
- Agent khác không có "đội" như mình, nên prompt bắt nó làm **từng gói một**, chạy gate sau mỗi gói và cập nhật `PROGRESS.md`. Nhờ vậy, khi bạn đổi agent giữa chừng, agent sau vẫn biết đang ở đâu.

**Nên tự kiểm sau mỗi wave** (vì agent yếu hơn dễ bỏ qua):
- Nó có chạy đủ gate và báo con số test không? Số test chỉ được tăng, không được giảm.
- Nó có sửa vào `vietrp-agent/` hoặc `viet-rp-glow/` không? Không được sửa.
- Có chuỗi tiếng Việt viết thẳng trong component, hay tên biến tiếng Việt trong code không?
- Có đụng vào `safety.py`, hoặc làm luật dưới 18 tuổi yếu đi không? Nếu có, bắt nó giải thích.
- Có test nào gọi mạng thật, hay dùng key thật không?

**Khi muốn mình review lại:** mở lại phiên Claude, nhờ "review P3 theo PROGRESS.md". Mình sẽ chạy gate, đọc code và smoke test như các phase trước.

**Việc chỉ bạn làm được:** thêm OpenRouter API key trong trang Cài đặt rồi chat thử thật. Tới giờ mọi thứ mới chạy với LLM giả lập.
