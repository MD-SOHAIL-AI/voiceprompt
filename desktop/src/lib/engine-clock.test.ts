import { describe, expect, it } from "vitest";
import { EngineClock } from "./engine-clock";

describe("engine restarts and hydration", () => {
  it("rejects old engine events and disconnects after a replacement starts", () => {
    const clock = new EngineClock();
    expect(clock.accept(1, 98, "runtime")).toBe(true);
    expect(clock.accept(2, 1, "runtime")).toBe(true);
    expect(clock.accept(1, 99, "runtime")).toBe(false);
    expect(clock.accept(1)).toBe(false);
    expect(clock.accept(2, 1, "runtime")).toBe(false);
  });
  it("preserves newer runtime events without discarding an unrelated planner snapshot", () => {
    const clock = new EngineClock();
    clock.accept(2, 4, "runtime");
    expect(clock.newerThan("runtime", 3)).toBe(true);
    expect(clock.newerThan("planner", 3)).toBe(false);
    clock.accept(3);
    expect(clock.newerThan("runtime", 0)).toBe(false);
  });
});
