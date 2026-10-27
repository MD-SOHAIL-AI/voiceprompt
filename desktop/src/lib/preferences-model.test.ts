import { describe, expect, it } from "vitest";
import {
  defaultPreferences,
  parsePreferences,
  resolveAppearance,
} from "./preferences-model";

describe("saved desktop preferences", () => {
  it("preserves the existing dark forest appearance on upgrade", () => {
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
});
