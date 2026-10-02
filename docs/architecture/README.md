# Architecture Diagram

The diagram in the [main README](../../README.md#high-level-architecture-diagram) is generated from code, not drawn by hand, so it can be updated in the same commit as the case it describes.

| File | What it is |
| :--- | :--- |
| `build_platform_diagram.py` | The generator: layout, components and labels |
| `platform-dark.svg`, `platform-light.svg` | Generated vector sources |
| `platform-dark.png`, `platform-light.png` | The images the README shows (GitHub picks one by the viewer's theme) |

## Regenerate

```bash
python3 build_platform_diagram.py dark && python3 build_platform_diagram.py light
```
```bash
for t in dark light; do google-chrome --headless=new --hide-scrollbars --force-device-scale-factor=1.25 --window-size=1920,1350 --screenshot="platform-$t.png" "file://$PWD/platform-$t.svg"; done
```

The README uses the PNGs, not the SVGs: GitHub renders an SVG with the viewer's fonts, so text widths can shift on other systems.

## Rules for what goes in the diagram

- Only controls documented in a published case.
- Every component carries a tag with the case that built it (`01`–`04`).
- Work in progress is drawn dashed and labeled, and becomes solid only when its case is complete. Case 04 stays dashed until its drills are recorded.
