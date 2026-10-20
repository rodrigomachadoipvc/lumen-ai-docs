import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import Home from "./page";

it("renders the product name and pitch", () => {
  render(<Home />);

  expect(screen.getByRole("heading", { level: 1, name: "Lumen" })).toBeInTheDocument();
  expect(screen.getByText(/cites the exact passages/i)).toBeInTheDocument();
});
