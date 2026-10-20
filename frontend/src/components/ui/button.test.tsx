import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./button";

describe("Button", () => {
  it("calls onClick when pressed", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Ask</Button>);

    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(onClick).toHaveBeenCalledOnce();
  });

  it("does not call onClick when disabled", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Ask
      </Button>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(onClick).not.toHaveBeenCalled();
  });
});
