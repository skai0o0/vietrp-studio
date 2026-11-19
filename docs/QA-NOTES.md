# Ghi chú QA — VietRP Studio

Tài liệu gom các lỗi và thiếu sót phát hiện trong quá trình QA thực tế để sửa tập trung theo đợt.

---

## Đã sửa (Đợt 1 · Điều hướng & UI Persona)

- **Lối vào Persona & các mục Thư viện bị ẩn:**
  - `frontend/src/features/library/list/LibraryListLayout.tsx`: thêm thanh tab chuyển giữa `Nhân vật` (`/library/characters`), `Thực tại` (`/library/worlds`), `Lorebook` (`/library/lorebooks`) và `Persona` (`/library/personas`).
  - `frontend/src/features/chat/newChat/PersonaPicker.tsx`: thêm link `+ Tạo persona mới` (`/library/personas/new`) ngay ở bước chọn Persona khi tạo chat đơn / chat Thực tại.
  - `frontend/src/features/chat/settings/ChatSettingsPanel.tsx`: thêm mục chọn/đổi `Persona` ngay trong Cài đặt chat + link tạo Persona mới.

---

## Đã sửa (Đợt 2 · Backend Chat Pipeline & UI/UX Waves 1–3)

Xem lộ trình chi tiết 5 đợt tại `docs/UI-REFACTOR-PLAN.md`. Toàn bộ 6 mục QA dưới đây đã được xử lý:

1. **Thay thế biến `{{user}}` và `{{char}}` đầy đủ trong chat (Fixed):**
   - `backend/app/prompts/_shared/card.j2`: truyền `user_name` thay vì nhãn cứng `"người chơi"`.
   - `backend/app/pipeline/prompt_assembler.py` & `backend/app/pipeline/world_assembly.py`: áp dụng `substitute_placeholders` cho card fields, lorebook, world rules/locations/`player_role`, persona, bonds, memory, prefill và `HistoryMessage` (giữ nguyên `minor_rule` không bị sửa và luôn ở cuối system layers).
   - `backend/app/pipeline/single_turn.py` & `backend/app/pipeline/world_turn.py`: thay `{{user}}` / `{{char}}` trong `parsed.message` trước khi lưu DB.
   - Đã bổ sung unit test tại `backend/tests/pipeline/test_assembler.py` và `backend/tests/pipeline/test_world_assembly.py`.
2. **Backend cho phép gỡ `persona_id` về `null` (Fixed):**
   - `backend/app/services/chat_service.py` (`ChatService.update`): kiểm tra `"persona_id" in body.model_fields_set` để hỗ trợ gửi `{"persona_id": null}` gỡ Persona khỏi chat.
3. **Đồng bộ nhãn Bond `*:user` khi đổi hoặc gỡ Persona (Fixed):**
   - `backend/app/services/chat_service.py` (`ChatService.update`): tự động cập nhật `state["bonds"][pid]["label"]` của mọi cặp `*:user` theo tên Persona mới hoặc `"người chơi"`.
   - Đã kiểm chứng qua test trong `backend/tests/chat/test_chats_api.py`.
4. **Mục điều hướng chủ động vào Chat (Fixed):**
   - `frontend/src/app/navItems.ts`, `IconRail.tsx`, `BottomNav.tsx`, `router.tsx`, `frontend/src/pages/ChatsHubPage.tsx`: thêm mục `Chat` (`/chats`) vào thanh điều hướng chính 5 mục cùng hub `/chats` và `/chats/new`.
5. **Cập nhật giao diện tức thì khi đổi cài đặt / trạng thái ở sidebar (Fixed):**
   - `frontend/src/features/chat/hooks.ts`, `components/usePromptPreview.ts`, `useTurnStream.ts`, `store.ts`: thêm `chatKeys.promptPreview` (`staleTime: 0`, debounce `400ms`), optimistic + rollback `useUpdateChat`, invalidate derived queries ở mọi mutation/SSE done, merge SSE `scene` vào cache, `clearLiveFields` theo từng section, xoá overlay store khi Undo/Delete và gắn `key={chatId}` ở `ChatChrome`.
   - `frontend/src/features/chat/settings/ChatSettingsPanel.tsx`: serialize `patch()` theo cache settings mới nhất để các toggle nhanh không ghi đè lẫn nhau.
6. **Refactor UI/UX Sidebar & Chat Workspace đồng bộ OLED Neon + E-ink + Mobile 375px (Fixed):**
   - Xây dựng `SidebarAccordion.tsx`, gom `LiveStateEditor` / `ChatSettingsPanel` theo accordion phẳng, thêm 2 tab `Phiên | Cài đặt` cho chat đơn (`ChatChrome.tsx`), thu gọn `SceneSection`/`BondsSection`/`MemorySection`, lọc lệnh world-only khi chat đơn (`commands.ts`), làm mới `RecentChats.tsx` (bộ lọc mode, nhóm thu gọn, đổi tên / xoá chat) và hoàn thiện `ChatHeader.tsx`, `MessageList.tsx`, `MessageBubble.tsx`, `StreamingBubble.tsx`, `ReasoningBlock.tsx`, `RpText.tsx`, `TokenBar.tsx`, `CommandPopup.tsx`, `ChatInput.tsx`, `NoticeList.tsx`, `PromptInspector.tsx`, `WorldPromptInspector.tsx`.

