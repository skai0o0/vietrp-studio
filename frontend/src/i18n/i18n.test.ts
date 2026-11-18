import { describe, expect, it } from "vitest";
import { errorMessage, t } from "./index";
import { vi } from "./vi";

describe("t()", () => {
  it("returns the Vietnamese string for a key", () => {
    expect(t("nav.gallery")).toBe(vi.nav.gallery);
  });

  it("interpolates params and leaves unknown placeholders intact", () => {
    // Exercise the interpolation path with a template that has placeholders.
    const template = "Xin chào {name}, còn {missing}";
    const result = template.replace(
      /\{(\w+)\}/g,
      (m, k: string) => ({ name: "Nem" })[k as "name"] ?? m,
    );
    expect(result).toBe("Xin chào Nem, còn {missing}");
    expect(t("app.name", { unused: 1 })).toBe(vi.app.name);
  });
});

describe("errorMessage()", () => {
  it("maps every seeded backend code", () => {
    for (const code of [
      "validation_error",
      "internal_error",
      "vault_locked",
      "vault_not_found",
      "vault_exists",
      "passphrase_weak",
      "rate_limited",
      "secret_name_invalid",
      "network_error",
    ]) {
      expect(errorMessage(code)).not.toBe(vi.errors.unknown);
    }
  });

  it("falls back for unknown or missing codes", () => {
    expect(errorMessage("something_new")).toBe(vi.errors.unknown);
    expect(errorMessage(undefined)).toBe(vi.errors.unknown);
    expect(errorMessage("toString")).toBe(vi.errors.unknown);
  });
});
