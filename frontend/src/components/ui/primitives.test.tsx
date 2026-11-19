import fs from "node:fs";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { t } from "@/i18n";
import { DURATIONS, SNAPPY_SPRING, useMotionKit } from "@/lib/motion";
import { renderHook } from "@testing-library/react";
import { Button } from "./button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./sheet";
import { Switch } from "./switch";

describe("Wave 1 UI primitives & design tokens", () => {
  it("defines surface, border, danger, scrim, and motion tokens in both theme stylesheets", () => {
    const themesDir = path.resolve(process.cwd(), "src/styles/themes");
    const oled = fs.readFileSync(path.join(themesDir, "oled-neon.css"), "utf-8");
    const eink = fs.readFileSync(path.join(themesDir, "e-ink.css"), "utf-8");

    for (const token of ["--surface-3", "--field-bg", "--danger-fg", "--scrim", "--dur-press"]) {
      expect(oled).toContain(token);
      expect(eink).toContain(token);
    }
    expect(eink).toContain('[data-variant="danger"]');
  });

  it("supports danger data-variant and loading spinner without breaking asChild", () => {
    const { rerender } = render(<Button variant="danger">Xoá</Button>);
    const btn = screen.getByRole("button", { name: "Xoá" });
    expect(btn).toHaveAttribute("data-variant", "danger");

    rerender(
      <Button variant="secondary" loading>
        Đang lưu
      </Button>,
    );
    const loadingBtn = screen.getByRole("button", { name: "Đang lưu" });
    expect(loadingBtn).toBeDisabled();
    expect(loadingBtn).toHaveAttribute("aria-busy", "true");
  });

  it("gives Dialog and Sheet accessible close buttons and SheetHeader in-flow close", () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Tiêu đề</DialogTitle>
          <DialogDescription>Mô tả</DialogDescription>
        </DialogContent>
      </Dialog>,
    );
    const dialogClose = screen.getByRole("button", { name: t("common.close") });
    expect(dialogClose.className).toContain("size-10");

    render(
      <Sheet open>
        <SheetContent hideDefaultClose>
          <SheetTitle className="sr-only">Bảng</SheetTitle>
          <SheetDescription className="sr-only">Chi tiết</SheetDescription>
          <SheetHeader title="Bảng bên" closeLabel="Đóng bảng" showHandle />
        </SheetContent>
      </Sheet>,
    );
    expect(screen.getByText("Bảng bên")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đóng bảng" }).className).toContain("size-10");
  });

  it("includes motion-reduce:transition-none on Switch and exposes snappy non-overshoot motion presets", () => {
    render(<Switch aria-label="Bật" />);
    const thumb = screen.getByRole("switch", { name: "Bật" }).querySelector("span");
    expect(thumb?.className).toContain("motion-reduce:transition-none");

    const { result } = renderHook(() => useMotionKit());
    expect(DURATIONS.press).toBe(0.09);
    expect(SNAPPY_SPRING).toMatchObject({ type: "spring", damping: 38 });
    expect(result.current.panel).toHaveProperty("animate");
    expect(result.current.crossfade).toHaveProperty("exit");
  });
});
