import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { PageHeader } from "@/components/PageHeader";
import { FilterButton, FilterChips } from "@/components/FilterToolbar";

describe("PageHeader", () => {
  it("has the serif title, a one-line description, the actions on the right and the chips underneath", () => {
    render(
      <PageHeader title={<>Candidate <span className="accent-word">opportunities</span></>} description="One line." actions={<button>Do it</button>}>
        <p>chips go here</p>
      </PageHeader>,
    );
    const title = screen.getByRole("heading", { level: 2, name: "Candidate opportunities" });
    expect(title).toHaveClass("display-heading");
    expect(title.querySelector(".accent-word")).toHaveTextContent("opportunities");
    const header = title.closest("header")!;
    expect(within(header).getByText("One line.")).toBeInTheDocument();
    const actions = within(header).getByTestId("page-actions");
    expect(within(actions).getByRole("button", { name: "Do it" })).toBeInTheDocument();
    // order in the document: title row (title, then actions), then the chips
    expect(title.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(actions.compareDocumentPosition(screen.getByText("chips go here")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows no actions row when there are no actions", () => {
    render(<PageHeader title="Landscape" description="d" />);
    expect(screen.queryByTestId("page-actions")).not.toBeInTheDocument();
  });
});

describe("FilterButton and FilterChips", () => {
  it("the button shows the number of active filters in its name, and nothing extra when there are none", () => {
    const { rerender } = render(<FilterButton count={0} onOpen={() => {}} />);
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
    expect(screen.queryByTestId("filter-count")).not.toBeInTheDocument();
    rerender(<FilterButton count={3} onOpen={() => {}} />);
    expect(screen.getByRole("button", { name: "Filters, 3 active" })).toBeInTheDocument();
    expect(screen.getByTestId("filter-count")).toHaveTextContent("3");
  });

  it("the chips render nothing when no filter is active (no orphaned line)", () => {
    const { container } = render(<FilterChips chips={[]} count={0} onRemove={() => {}} onClearAll={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
