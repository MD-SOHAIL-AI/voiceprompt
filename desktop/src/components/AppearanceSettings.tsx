import { Monitor, Moon, Sun } from "lucide-react";
import { palettes, type Appearance } from "../lib/preferences-model";
import { updatePreferences, usePreferences } from "../lib/preferences";
import { Toggle } from "./ui";

const modes = [
  { id: "light", name: "Light", Icon: Sun },
  { id: "dark", name: "Dark", Icon: Moon },
  { id: "system", name: "System", Icon: Monitor },
] as const;
export function AppearanceSettings() {
  const appearance = usePreferences((p) => p.appearance);
  const palette = usePreferences((p) => p.palette);
  const enabled = usePreferences((p) => p.islandEnabled);
  const pinned = usePreferences((p) => p.islandPinned);
  return (
    <section className="settings-section appearance-settings">
      <h2>Appearance</h2>
      <p className="muted">
        Make it yours. Changes apply instantly to both windows and save
        automatically.
      </p>
      <fieldset className="appearance-fieldset">
        <legend>Brightness</legend>
        <div className="appearance-modes">
          {modes.map(({ id, name, Icon }) => (
            <label className="appearance-option" key={id}>
              <input
                type="radio"
                name="appearance"
                value={id}
                checked={appearance === id}
                onChange={() =>
                  updatePreferences({ appearance: id as Appearance })
                }
              />
              <span>
                <Icon size={18} />
                {name}
              </span>
            </label>
          ))}
        </div>
        <small>System follows your Windows light or dark setting.</small>
      </fieldset>
      <fieldset className="appearance-fieldset">
        <legend>Color theme</legend>
        <div className="theme-options">
          {palettes.map((p) => (
            <label className="appearance-option theme-option" key={p.id}>
              <input
                type="radio"
                name="palette"
                value={p.id}
                checked={palette === p.id}
                onChange={() => updatePreferences({ palette: p.id })}
              />
              <span>
                <i
                  className="theme-swatch"
                  style={{ backgroundColor: p.swatch }}
                  aria-hidden="true"
                />
                {p.name}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <h3>Floating island</h3>
      <Toggle
        label="Show floating island"
        checked={enabled}
        onChange={(islandEnabled) => updatePreferences({ islandEnabled })}
      />
      <Toggle
        label="Keep island visible"
        checked={pinned}
        disabled={!enabled}
        onChange={(islandPinned) => updatePreferences({ islandPinned })}
      />
      <p className="muted">
        Keep it visible for quick access, even when idle. Turn this off to hide
        it automatically when nothing is active.
      </p>
    </section>
  );
}
