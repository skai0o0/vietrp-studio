# Kế hoạch Refactor UI/UX Toàn diện — VietRP Studio

Tài liệu lộ trình 5 đợt nâng cấp giao diện, hệ thống thiết kế và trải nghiệm người dùng dựa trên bộ tiêu chuẩn `ui-ux-pro-max` và `design-taste-frontend`, áp dụng song song trên cả **OLED Neon**, **E-ink** và **Mobile 375px**.

---

## Wave 1 — Hệ thống Thiết kế & Primitives (`DONE`)

- **Token màu & tương phản WCAG AA / 1.4.11 (`frontend/src/styles/themes/oled-neon.css`, `e-ink.css`, `frontend/tailwind.config.ts`):**
  - Bổ sung surface hierarchy (`--surface-3`, `--field-bg`, `--hover`), border tokens (`--border-subtle`, `--border-strong`), semantic text tokens (`--accent-text`, `--danger-text`, `--danger-fg`, `--success`, `--warning`), `--scrim`, `--shadow-{sm,popover,dialog}`, `--font-mono`, `--dur-*`, `--ease-*`.
  - Nâng tương phản viền tối thiểu `3:1+`, chỉnh `--accent`/`--danger` đạt chuẩn AA trên nền đen OLED mà vẫn giữ nguyên `--bg: 0 0 0` và `--motion: 1`.
  - E-ink parity 100%: `--glow: none`, `--motion: 0`, `box-shadow: none !important`, `animation: none !important`, `[data-variant="danger"]` viền nét đứt, `[data-eink-active="true"]` / `[role="tab"][data-state="active"]` đảo nền đen chữ trắng thay vì phụ thuộc màu sắc.
- **Typography, Focus & Motion (`globals.css`, `index.html`, `theme.ts`, `motion.ts`, `providers.tsx`):**
  - Bổ sung `@fontsource/noto-serif` `400-italic` và `600` (`vietnamese`, `latin`, `latin-ext`), `touch-action: manipulation`, `<meta name="theme-color">` đồng bộ theo theme.
  - Chuẩn hoá `SNAPPY_SPRING`, `EASE_UI` / `EASE_ENTER` / `EASE_EXIT`, `DURATIONS`, `panel` / `crossfade` / `activeIndicator` và `<MotionConfig reducedMotion={reduced ? "always" : "user"}>`.
- **14 UI Primitives (`frontend/src/components/ui/`):**
  - Thêm `Textarea`, `Select`; nâng cấp `Button` (`secondary`, `loading`, `size="icon-sm"`, tactile press), `Input`, `Tabs`, `Switch`, `Dialog`, `Sheet` (`SheetHeader`, `hideDefaultClose`), `DropdownMenu` (`bg-surface-3`, `z-popover`, `destructive`), `Tooltip`, `ScrollArea`, `Label`, `Separator`, `Sonner`.

---

## Wave 2 — Kiến trúc Thông tin (IA) & Shell (`DONE`)

- **Điều hướng chính 5 mục (`frontend/src/app/navItems.ts`, `IconRail.tsx`, `BottomNav.tsx`):**
  - Mở rộng `NAV_ITEMS` lên 5 mục chuẩn: `Gallery` (`/`), `Chat` (`/chats`), `Thư viện` (`/library/characters`), `Tạo mới` (`/create`), `Cài đặt` (`/settings`).
  - Tablet/Desktop `IconRail` có indicator `layoutId="rail-active"`, micro-label ở breakpoint `md–lg`, logo `V` dẫn về `/`; `BottomNav` chuẩn `text-xs` và `data-eink-active`.
- **Chat Hub (`/chats`) & Routes (`ChatsHubPage.tsx`, `router.tsx`, `AppLayout.tsx`, `pageChrome.ts`):**
  - Thêm trang `/chats` tổng hợp lối vào chat gần đây, tạo chat đơn / chat Thực tại (`/chats/new` giữ tương thích `/create/chat`) và `/library` redirect về `/library/characters`.
  - `AppLayout.tsx` dùng `SheetHeader` không đè nút đóng lên tiêu đề sidebar, tự động đóng drawer & reset scroll `<main>` khi chuyển route, ẩn `BottomNav` và toggle bar trên màn hình chat.

---

## Wave 3 — Workspace Chat, Sidebar & Đồng bộ Backend/State (`DONE`)

- **Wave 3.1 — Đồng bộ Cache & Stream Store (`hooks.ts`, `usePromptPreview.ts`, `store.ts`, `useTurnStream.ts`):**
  - Thêm `chatKeys.promptPreview(id)`, `chatKeys.usage(id)` và `invalidateChatDerived`; nâng cấp `useUpdateChat` với optimistic update + rollback khi lỗi.
  - Mọi thao tác đổi state/bonds/summary/variant/edit/undo/delete/SSE done đều invalidate `prompt-preview` ngay (`staleTime: 0`, debounce `400ms`).
  - `useUndoChat` / `useDeleteMessage` xoá sạch SSE overlay cũ; thêm `clearLiveFields` theo từng phần, `optimisticUserMessage`, bộ đếm `errorNonce` đơn điệu và merge SSE `scene` vào cache.
- **Wave 3.2 — Backend Placeholder `{{user}}` / `{{char}}` & Persona (`prompt_assembler.py`, `world_assembly.py`, `single_turn.py`, `world_turn.py`, `card.j2`, `chat_service.py`):**
  - Truyền `user_name` vào `_shared/card.j2`; chạy `substitute_placeholders` nhất quán cho toàn bộ card fields, lorebook, world rules/locations/`player_role`, persona, bonds, memory, prefill, lịch sử hội thoại và `user_text` lưu DB (giữ nguyên `minor_rule` ở cuối hệ thống).
  - `ChatService.update` kiểm tra `"persona_id" in body.model_fields_set` để cho phép gỡ Persona về `null`, đồng thời đồng bộ lại `label` cho các bond `*:user`.
- **Wave 3.3 — Refactor Sidebar & Chat Workspace:**
  - `SidebarAccordion.tsx`: accordion phẳng `divide-y` có summary, dirty badge, E-ink focus ring và chuyển động khớp giảm chuyển động.
  - Right sidebar (`ChatChrome.tsx`, `LiveStateEditor.tsx`, `ChatSettingsPanel.tsx`, `StructuredStateSection.tsx`, `SceneSection.tsx`, `BondsSection.tsx`, `MemorySection.tsx`, `AgentModelSelects.tsx`):
    - Chat đơn dùng 2 tab `Phiên | Cài đặt`; chat Thực tại dùng 2 tab `Trạng thái | Cài đặt`.
    - Sửa từng nhân vật đang có mặt bằng pill selector, accordion cho từng cặp Bond, thu gọn sự kiện & toggle `+ Thêm sự kiện`, ẩn `state_keeper` ở chat đơn, serialize `patch()` tránh mất field khi bấm liên tiếp.
  - Left sidebar (`RecentChats.tsx`): header sticky với `+ Mới` (`/chats/new`), bộ lọc chế độ (`Tất cả | Đơn | Thực tại`), nhóm thu gọn không lặp tên, timestamp tương đối, thụt lề fork tối đa 3 cấp, menu `⋯` Đổi tên / Xoá chat.
  - Workspace (`ChatHeader.tsx`, `MessageList.tsx`, `MessageBubble.tsx`, `StreamingBubble.tsx`, `ReasoningBlock.tsx`, `RpText.tsx`, `TokenBar.tsx`, `CommandPopup.tsx`, `ChatInput.tsx`, `NoticeList.tsx`, `PromptInspector.tsx`, `WorldPromptInspector.tsx`, `ChatView.tsx`):
    - Sticky `ChatHeader` có Avatar, Persona pill, World scene strip, drawer triggers và overflow actions.
    - Smart scroll + nút `"↓ Tin nhắn mới"`, vạch phân cách Archivist `summary_upto`, bong bóng gửi lạc quan, nút Sao chép + `Ctrl/Cmd+Enter` lưu sửa, skeleton trước khi speaker bắt đầu nói, kéo lại contrast bản nháp và `*action*`/`**bold**`, composer 2 hàng auto-grow + unified slash menu lọc lệnh world-only khi chat đơn, `NoticeList` ghim cố định trên composer, Prompt Inspector thu gọn từng lớp theo %.

---

## Wave 4 — Editors, Creator Studio, Library & Gallery (`PENDING`)

- Thống nhất lưới card, empty/error states và filter bar giữa Gallery, Library (`Character`/`World`/`Lorebook`/`Persona`) và `NewChat`/`NewWorldChat`.
- Làm gọn form `CharacterEditor`, `WorldEditor` (cây địa điểm & Opening), `LorebookEditor` và `CreatorStudio` theo cùng hệ token surface/border và primitives Wave 1 (`Select`, `Textarea`, `Button` loading/variant).
- Cải thiện `Prompt` / `Usage` / `Settings` (`/settings`) với feedback trạng thái lưu và kiểm tra E-ink ở độ rộng `375px`.

---

## Wave 5 — Micro-interactions, Phím tắt & QA Thị giác (`PENDING`)

- Bổ sung phím tắt workspace (`Ctrl/Cmd+K` chuyển nhanh chat, phím tắt mở Prompt Inspector / chuyển sidebar) kèm tooltip hỗ trợ.
- Rà soát visual QA trên trình duyệt thật (Playwright / Chrome DevTools) ở cả 2 theme `oled-neon` & `e-ink`, breakpoint `375px`, `768px`, `1280px` và kiểm tra độ tương phản chữ + hành vi reduced-motion.
