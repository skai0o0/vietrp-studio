import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePageChromeStore } from "@/app/pageChrome";
import { TooltipProvider } from "@/components/ui/tooltip";
import SettingsPage from "@/features/settings/SettingsPage";
import { t } from "@/i18n";
import { createQueryClient } from "@/lib/queryClient";
import { VaultGate } from "./VaultGate";
import { isPassphraseStrong } from "./passphrase";

interface Call {
  method: string;
  path: string;
  body: unknown;
}

type Handler = (call: Call) => Response;

const VAULT = {
  id: "11111111-1111-4111-8111-111111111111",
  display_name: "Mèo",
  created_at: "2026-01-01T00:00:00Z",
};
const STRONG = "mot cau passphrase rat dai";

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

const locked = () => json(401, { error: { code: "vault_locked", message: "locked" } });

let calls: Call[] = [];

function mockApi(handler: Handler): void {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const call: Call = {
        method: init?.method ?? "GET",
        path,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      };
      calls.push(call);
      return handler(call);
    }),
  );
}

/** Stands in for the IconRail, which renders the footer slot in the real layout. */
function RailFooterProbe() {
  return <>{usePageChromeStore((state) => state.railFooter)}</>;
}

function renderGate(children: React.ReactNode = <p>nội dung app</p>): void {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <VaultGate>
            <RailFooterProbe />
            {children}
          </VaultGate>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

async function typePassphrase(value: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(t("vault.unlock.passphrase")), `${value}{Enter}`);
}

describe("passphrase strength", () => {
  it("mirrors the server rule", () => {
    expect(isPassphraseStrong("a".repeat(16))).toBe(true);
    expect(isPassphraseStrong("mot hai ba bon")).toBe(true);
    expect(isPassphraseStrong("mot hai ba")).toBe(false);
    expect(isPassphraseStrong("a b c d")).toBe(false);
    expect(isPassphraseStrong("short")).toBe(false);
  });
});

describe("VaultGate", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it("shows the app when the vault is already unlocked", async () => {
    mockApi(() => json(200, { vault: VAULT }));
    renderGate();
    expect(await screen.findByText("nội dung app")).toBeInTheDocument();
  });

  it("unlocks an existing vault with Enter", async () => {
    let unlocked = false;
    mockApi(({ path }) => {
      if (path === "/api/vault/unlock") {
        unlocked = true;
        return json(200, { exists: true, vault: VAULT });
      }
      return unlocked ? json(200, { vault: VAULT }) : locked();
    });
    renderGate();
    await typePassphrase(STRONG);
    expect(await screen.findByText("nội dung app")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/vault/unlock")?.body).toEqual({ passphrase: STRONG });
    expect(screen.getByRole("button", { name: t("vault.lock") })).toBeInTheDocument();
  });

  it("asks for confirmation before creating a vault for an unknown passphrase", async () => {
    mockApi(({ path }) => {
      if (path === "/api/vault/unlock") return json(200, { exists: false });
      if (path === "/api/vault/create") return json(201, { vault: VAULT });
      return locked();
    });
    renderGate();
    await typePassphrase(STRONG);
    expect(await screen.findByText(t("vault.create.title"))).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/vault/create")).toBe(false);

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(t("vault.create.displayName")), "Mèo");
    await user.click(screen.getByRole("button", { name: t("vault.create.confirm") }));

    expect(await screen.findByText("nội dung app")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/vault/create")?.body).toEqual({
      passphrase: STRONG,
      display_name: "Mèo",
    });
  });

  it("maps passphrase_weak from the server to Vietnamese", async () => {
    mockApi(({ path }) => {
      if (path === "/api/vault/unlock") return json(200, { exists: false });
      if (path === "/api/vault/create") {
        return json(422, { error: { code: "passphrase_weak", message: "weak" } });
      }
      return locked();
    });
    renderGate();
    await typePassphrase("yeu");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(t("vault.create.displayName")), "Mèo");
    await user.click(screen.getByRole("button", { name: t("vault.create.confirm") }));
    expect(await screen.findByRole("alert")).toHaveTextContent(t("errors.passphrase_weak"));
  });

  it("shows the Retry-After seconds on a 429", async () => {
    mockApi(({ path }) =>
      path === "/api/vault/unlock"
        ? json(429, { error: { code: "rate_limited", message: "slow" } }, { "Retry-After": "42" })
        : locked(),
    );
    renderGate();
    await typePassphrase(STRONG);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(t("vault.unlock.retryAfter", { seconds: 42 }));
  });

  it("returns to the unlock screen after locking", async () => {
    let lockedNow = false;
    mockApi(({ path }) => {
      if (path === "/api/vault/lock") {
        lockedNow = true;
        return new Response(null, { status: 204 });
      }
      return lockedNow ? locked() : json(200, { vault: VAULT });
    });
    renderGate();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: t("vault.lock") }));
    expect(await screen.findByLabelText(t("vault.unlock.passphrase"))).toBeInTheDocument();
    expect(screen.queryByText("nội dung app")).not.toBeInTheDocument();
  });
});

describe("SettingsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  const SECRET_VALUE = "sk-or-v1-SUPERSECRETVALUE1234";

  it("lists keys with a hint only, saves a new key and never shows the value", async () => {
    let isSet = true;
    mockApi(({ method, path }) => {
      if (path === "/api/vault/me") return json(200, { vault: VAULT });
      if (path === "/api/secrets" && method === "GET") {
        return json(200, {
          secrets: [
            {
              name: "OPENROUTER_API_KEY",
              is_set: isSet,
              hint: isSet ? "1234" : null,
              updated_at: null,
            },
          ],
        });
      }
      if (method === "PUT") {
        return json(200, {
          secret: { name: "OPENROUTER_API_KEY", is_set: true, hint: "1234", updated_at: null },
        });
      }
      if (method === "DELETE") {
        isSet = false;
        return new Response(null, { status: 204 });
      }
      return json(404, { error: { code: "unknown", message: "?" } });
    });
    renderGate(<SettingsPage />);
    expect(await screen.findByText("••••1234")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(SECRET_VALUE);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: t("settings.apiKey.replace") }));
    await user.type(await screen.findByLabelText(t("settings.apiKey.value")), SECRET_VALUE);
    await user.click(screen.getByRole("button", { name: t("settings.apiKey.save") }));

    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ value: SECRET_VALUE });
    await waitFor(() =>
      expect(screen.queryByLabelText(t("settings.apiKey.value"))).not.toBeInTheDocument(),
    );
    expect(document.body.textContent).not.toContain(SECRET_VALUE);

    await user.click(
      screen.getByRole("button", {
        name: `${t("settings.apiKey.remove")}: ${t("settings.apiKey.names.OPENROUTER_API_KEY")}`,
      }),
    );
    await user.click(
      await screen.findByRole("button", { name: t("settings.apiKey.deleteConfirm") }),
    );
    expect(await screen.findByText(t("settings.apiKey.notSet"))).toBeInTheDocument();
  });
});
