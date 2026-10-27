import { describe, expect, it } from "vitest";
import {
  defaultPreferences,
  parsePreferences,
  resolveAppearance,
} from "./preferences-model";

describe("saved desktop preferences", () => {
  it("uses neutral Black unless a saved preference is available", () => {
    expect(parsePreferences(null)).toEqual(defaultPreferences);
    expect(parsePreferences({ version: 99, palette: "ocean" })).toEqual(
      defaultPreferences,
    );
  });
  it("retains valid choices and rejects malformed preferences independently", () => {
    expect(
      parsePreferences({
        version: 1,
        appearance: "light",
        palette: "ocean",
        islandPinned: true,
        islandEnabled: "false",
      }),
    ).toEqual({
      version: 1,
      appearance: "light",
      palette: "ocean",
      islandPinned: true,
      islandEnabled: true,
      islandTransparency: 0,
    });
    expect(
      parsePreferences({
        version: 1,
        appearance: "neon",
        palette: {},
        islandPinned: 1,
      }),
    ).toEqual(defaultPreferences);
  });
  it("follows system changes only when System is selected", () => {
    expect(resolveAppearance("system", true)).toBe("dark");
    expect(resolveAppearance("system", false)).toBe("light");
    expect(resolveAppearance("light", true)).toBe("light");
    expect(resolveAppearance("dark", false)).toBe("dark");
  });
  it("bounds transparency and upgrades preferences without the new field", () => {
    for (const [input, expected] of [
      [-20, 0],
      [15, 15],
      [90, 25],
      [NaN, 0],
      [Infinity, 0],
    ]) {
      expect(
        parsePreferences({ ...defaultPreferences, islandTransparency: input })
          .islandTransparency,
      ).toBe(expected);
    }
    expect(parsePreferences({ version: 1, palette: "forest" }).palette).toBe(
      "forest",
    );
    expect(
      parsePreferences({ version: 1, palette: "forest" }).islandTransparency,
    ).toBe(0);
  });
});
