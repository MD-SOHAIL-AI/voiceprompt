export const palettes = [
  { id: "black", name: "Black", swatch: "#262626" },
  { id: "forest", name: "Forest", swatch: "#8bd0af" },
  { id: "graphite", name: "Graphite", swatch: "#b5c2d0" },
  { id: "ocean", name: "Ocean", swatch: "#89bde9" },
  { id: "lavender", name: "Lavender", swatch: "#c4ade8" },
  { id: "sand", name: "Sand", swatch: "#dfbc85" },
] as const;
export type Palette = (typeof palettes)[number]["id"];
export type Appearance = "system" | "light" | "dark";
export interface Preferences {
  version: 1;
  appearance: Appearance;
  palette: Palette;
  islandEnabled: boolean;
  islandPinned: boolean;
  islandTransparency: number;
}
export const defaultPreferences: Preferences = {
  version: 1,
  appearance: "dark",
  palette: "black",
  islandEnabled: true,
  islandPinned: false,
  islandTransparency: 0,
};
export function parsePreferences(value: unknown): Preferences {
  if (!value || typeof value !== "object") return { ...defaultPreferences };
  const p = value as Record<string, unknown>;
  if (p.version !== 1) return { ...defaultPreferences };
  return {
    version: 1,
    appearance: ["system", "light", "dark"].includes(String(p.appearance))
      ? (p.appearance as Appearance)
      : defaultPreferences.appearance,
    palette: palettes.some((palette) => palette.id === p.palette)
      ? (p.palette as Palette)
      : defaultPreferences.palette,
    islandEnabled:
      typeof p.islandEnabled === "boolean" ? p.islandEnabled : true,
    islandPinned: typeof p.islandPinned === "boolean" ? p.islandPinned : false,
    islandTransparency:
      typeof p.islandTransparency === "number" &&
      Number.isFinite(p.islandTransparency)
        ? Math.max(0, Math.min(25, Math.round(p.islandTransparency)))
        : 0,
  };
}
export function resolveAppearance(appearance: Appearance, systemDark: boolean) {
  return appearance === "system" ? (systemDark ? "dark" : "light") : appearance;
}
