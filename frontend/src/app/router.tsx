import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { t } from "@/i18n";
import { AppLayout } from "./AppLayout";

const GalleryPage = lazy(() => import("@/pages/GalleryPage"));
const ChatsHubPage = lazy(() => import("@/pages/ChatsHubPage"));
const ChatPage = lazy(() => import("@/pages/ChatPage"));
const NewChatPage = lazy(() => import("@/features/chat/newChat/NewChatPage"));
const CreatePage = lazy(() => import("@/pages/CreatePage"));
const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));
const LibraryCharactersPage = lazy(() =>
  import("@/pages/LibraryPages").then((m) => ({ default: m.LibraryCharactersPage })),
);
const LibraryWorldsPage = lazy(() =>
  import("@/pages/LibraryPages").then((m) => ({ default: m.LibraryWorldsPage })),
);
const LibraryLorebooksPage = lazy(() =>
  import("@/pages/LibraryPages").then((m) => ({ default: m.LibraryLorebooksPage })),
);
const LibraryPersonasPage = lazy(() =>
  import("@/pages/LibraryPages").then((m) => ({ default: m.LibraryPersonasPage })),
);
const CharacterDetailPage = lazy(() =>
  import("@/pages/DetailPages").then((m) => ({ default: m.CharacterDetailPage })),
);
const WorldDetailPage = lazy(() =>
  import("@/pages/DetailPages").then((m) => ({ default: m.WorldDetailPage })),
);
const PersonaDetailPage = lazy(() =>
  import("@/pages/DetailPages").then((m) => ({ default: m.PersonaDetailPage })),
);
const LorebookDetailPage = lazy(() =>
  import("@/pages/DetailPages").then((m) => ({ default: m.LorebookDetailPage })),
);

function PageFallback() {
  return (
    <p role="status" className="p-8 text-sm text-muted">
      {t("pages.loading")}
    </p>
  );
}

function Lazy({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>;
}

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: (
          <Lazy>
            <GalleryPage />
          </Lazy>
        ),
      },
      {
        path: "chats",
        element: (
          <Lazy>
            <ChatsHubPage />
          </Lazy>
        ),
      },
      {
        path: "chats/new",
        element: (
          <Lazy>
            <NewChatPage />
          </Lazy>
        ),
      },
      {
        path: "chat/:chatId",
        element: (
          <Lazy>
            <ChatPage />
          </Lazy>
        ),
      },
      {
        path: "library",
        element: <Navigate to="/library/characters" replace />,
      },
      {
        path: "library/characters",
        element: (
          <Lazy>
            <LibraryCharactersPage />
          </Lazy>
        ),
      },
      {
        path: "library/worlds",
        element: (
          <Lazy>
            <LibraryWorldsPage />
          </Lazy>
        ),
      },
      {
        path: "library/lorebooks",
        element: (
          <Lazy>
            <LibraryLorebooksPage />
          </Lazy>
        ),
      },
      {
        path: "library/personas",
        element: (
          <Lazy>
            <LibraryPersonasPage />
          </Lazy>
        ),
      },
      {
        path: "library/personas/:id",
        element: (
          <Lazy>
            <PersonaDetailPage />
          </Lazy>
        ),
      },
      {
        path: "library/lorebooks/:id",
        element: (
          <Lazy>
            <LorebookDetailPage />
          </Lazy>
        ),
      },
      {
        path: "characters/:id",
        element: (
          <Lazy>
            <CharacterDetailPage />
          </Lazy>
        ),
      },
      {
        path: "worlds/:id",
        element: (
          <Lazy>
            <WorldDetailPage />
          </Lazy>
        ),
      },
      {
        path: "create/chat",
        element: (
          <Lazy>
            <NewChatPage />
          </Lazy>
        ),
      },
      {
        path: "create",
        element: (
          <Lazy>
            <CreatePage />
          </Lazy>
        ),
      },
      {
        path: "settings",
        element: (
          <Lazy>
            <SettingsPage />
          </Lazy>
        ),
      },
      {
        path: "*",
        element: (
          <Lazy>
            <NotFoundPage />
          </Lazy>
        ),
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
