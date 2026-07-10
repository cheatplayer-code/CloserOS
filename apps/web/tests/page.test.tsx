import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import Home from "../app/page";

describe("web scaffold", () => {
  it("renders the repository-foundation placeholder", () => {
    const markup = renderToStaticMarkup(<Home />);

    expect(markup).toContain("CloserOS AI");
    expect(markup).toContain("Product features begin in later tasks.");
  });
});
