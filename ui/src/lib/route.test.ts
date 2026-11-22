import { describe, expect, it } from "vitest";
import { DEFAULT_ROUTE, formatRoute, parseRoute, sameRoute, type Route } from "./route";

describe("route <-> hash", () => {
  it("round-trips every combination of the four fields", () => {
    const routes: Route[] = [
      DEFAULT_ROUTE,
      { view: "story", opp: null, paper: null, graph: "" },
      { view: "candidates", opp: null, paper: null, graph: "" },
      { view: "candidates", opp: 14, paper: null, graph: "" },
      { view: "papers", opp: null, paper: "W3028876793", graph: "" },
      { view: "graph", opp: null, paper: null, graph: "W2626778328" },
      { view: "landscape", opp: null, paper: null, graph: "" },
      { view: "graph", opp: 7, paper: "W1", graph: "W2" },
    ];
    for (const r of routes) expect(parseRoute(formatRoute(r))).toEqual(r);
  });

  it("the default route is the story, written as the empty hash; an empty or unknown hash is the default route", () => {
    expect(DEFAULT_ROUTE.view).toBe("story");
    expect(formatRoute(DEFAULT_ROUTE)).toBe("");
    for (const h of ["", "#", "#/", "#/nonsense", "#/story", "#/STORY", "#/CANDIDATES", "#/?opp=abc"]) {
      expect(parseRoute(h).view).toBe("story");
    }
    expect(parseRoute("")).toEqual(DEFAULT_ROUTE);
  });

  it("the explorer is a route of its own: #/candidates is Candidates, not the default", () => {
    expect(formatRoute({ ...DEFAULT_ROUTE, view: "candidates" })).toBe("#/candidates");
    expect(parseRoute("#/candidates").view).toBe("candidates");
  });

  it("links to an opportunity and a paper", () => {
    expect(formatRoute({ ...DEFAULT_ROUTE, view: "candidates", opp: 14 })).toBe("#/candidates?opp=14");
    expect(parseRoute("#/candidates?opp=14")).toMatchObject({ view: "candidates", opp: 14 });
    expect(parseRoute("#/papers?paper=W3028876793")).toMatchObject({ view: "papers", paper: "W3028876793" });
  });

  it("ignores values that are not valid instead of failing", () => {
    for (const bad of ["abc", "-3", "0", "1.5", "1e3", "99999999999", "", " 7"]) expect(parseRoute(`#/candidates?opp=${bad}`).opp).toBeNull();
    expect(parseRoute("#/candidates?opp=14&opp=15").opp).toBe(14);
  });

  it("reduces pasted graph-style ids and openalex links to plain ids", () => {
    expect(parseRoute("#/graph?graph=Paper:W3028876793").graph).toBe("W3028876793");
    expect(parseRoute("#/graph?graph=" + encodeURIComponent("https://openalex.org/W3028876793")).graph).toBe("W3028876793");
  });

  it("encodes odd characters so a hash cannot inject extra parameters", () => {
    const h = formatRoute({ ...DEFAULT_ROUTE, view: "papers", paper: "W1&opp=9" });
    expect(parseRoute(h)).toMatchObject({ paper: "W1&opp=9", opp: null });
  });

  it("sameRoute compares by hash", () => {
    expect(sameRoute(DEFAULT_ROUTE, parseRoute(""))).toBe(true);
    expect(sameRoute(DEFAULT_ROUTE, { ...DEFAULT_ROUTE, opp: 1 })).toBe(false);
  });
});
