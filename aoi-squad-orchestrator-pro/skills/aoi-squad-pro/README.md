# AOI Squad Pro (private)

This is the paid/private evolution of AOI Squad Orchestrator Lite.

## v0.1 (M1 focus)
- Two 5-role presets (A + B)
- Stable pseudonym team names per preset
- Preset clone/edit/save (stored locally)

## Non-negotiables
- Never output AOI internal nicknames.
- Any side-effect actions require explicit approval (diff-first); not implemented in M1.

## CLI
```bash
aoi-squad-pro preset list
aoi-squad-pro team show --preset pro-a
aoi-squad-pro preset clone --from pro-a --to my-team
aoi-squad-pro preset show --name my-team

aoi-squad-pro run --preset pro-a --task "Draft a launch checklist"
```

## Local data
- Names: `~/.openclaw/aoi/squad_names.json`
- Pro presets: `~/.openclaw/aoi/presets.json`
