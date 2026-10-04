# Changelog

Notable changes to Punctum, newest first. Version numbers follow
MAJOR.MINOR.PATCH: fixes bump the last number, new features the middle one.
Wersja polska: [CHANGELOG.pl.md](CHANGELOG.pl.md).

## 0.10.0 — 2026-10-04

### Added

- Help ▸ "What's new" — the program's change history. After an update the
  window opens by itself, once.
- Settings ▸ About ▸ "Third-party licenses" — the libraries by other authors
  included with the program and the full texts of their licenses; the
  installer lists them too.
- The installer can be downloaded from the GitHub releases page, with
  a SHA-256 checksum.

### Fixed

- Smoother preview while dragging sliders: the photo no longer flickers with
  the previous setting or a blurry image, also when zoomed in, and colours no
  longer shift a moment after the slider stops — colour noise reduction now
  runs on the graphics card with every move.
- The luminance noise and sharpening sliders show their effect while
  dragging, not only after the slider is released.

## 0.9.0 — 2026-09-29

First release.

### Added

- Editing of RAW (RW2, CR2, CR3, NEF, ARW, DNG) and JPEG photos in a single
  pipeline, with the preview rendered on the graphics card.
- Light and colour adjustments, white balance, automatic tone correction.
- Cropping and rotation, including by any angle.
- Noise reduction matched to the measured noise of the photo, with
  a preview; sharpening.
- Monochrome with colour mixing, and adjustment presets.
- Before / after comparison: side by side (Y) or with a split line
  (Shift+Y).
- Undo / redo in editing and on the map.
- Non-destructive editing: adjustments are stored next to the photo in an
  XMP file, the original stays untouched.
- Background export with an options window: author, copyright, tags, camera
  data and watermark.
- Map and geotagging: GPX track, photos grouped by day, coordinate
  clipboard, place names.
- Metadata panel and status markers in the photo list.
- Panels made of sections: collapse, reorder, pin and hide; scaling of the
  whole interface.
- Polish and English interface, a tooltip on every button, slider and field.
- Control by AI agents (MCP server).
- Windows installer: RAW file associations and opening a photo straight
  from Explorer.
