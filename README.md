# Punctum

A non-destructive photo editor for RAW (RW2, CR2/CR3, NEF, ARW, DNG) and JPEG,
with a preview computed on the graphics card and geotagging on a map.

> Wersja polska: [README.pl.md](README.pl.md). The program runs in English and
> Polish; the language is chosen in the settings.

## Running

Double-click `Punctum.bat` (you can drag it to the desktop or drop a photo
folder onto it), or from the command line:

```powershell
python -m punctum "C:\Photos\Trip"
```

First installation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## What works

**Browsing** — a thumbnail strip loaded from the previews embedded in RAW
files (about 100 ms per photo), a panel with camera, focal length, shutter
speed, aperture, ISO, date and location. Damaged files are marked instead of
crashing the program. Above the strip sits a format switch (all / RAW only /
JPEG only) — in a folder with thousands of JPEGs and a handful of RAWs you
cannot work without it. The choice is remembered.

**Adjustments** — white balance in kelvins (sliders with a color gradient),
exposure, contrast, highlights, shadows, whites, blacks, vibrance, saturation.
Double-clicking a slider restores its default.

**Auto correction** — the *Auto* button picks tonal settings from a histogram
analysis. The results match the *Auto* button of the commercial program used
as a reference to within a few points (see below).

**Crop** — the button with the crop icon (shortcut `R`). Dragging the edges
and corners changes the crop, `Shift` keeps the ratio, dragging outside the
crop rotates the photo. At rest you see the rule of thirds, while dragging an
8×8 grid. Separate buttons rotate by 90° and 180°. `Enter` confirms.

**Preview** — zoom with the wheel, the slider (logarithmic, from "fit" to
1600 %) or the *Fit* / *100 %* buttons; double-click toggles fit ↔ 100 %.
A navigator with a frame showing the zoomed part (clickable), holding
*Before / after* shows the photo without edits, a live histogram.

**Sharpening** — amount, radius, detail, masking; RAW defaults to 40,
JPEG to 0 (the camera has already sharpened it).

**Noise reduction** — luminance noise and color noise separately, with the
strength matched to the noise measured in the photo.

**Export** — `Ctrl+E` opens a window with the full set of options: destination
folder, optional subfolder, what to do with existing files, a name with a
sequence number, format, quality, a limit on the long edge and noise reduction
precision. At the bottom you see the full path of the first file, so the
effect of all settings together is visible before you click.

Export runs in the background — a progress bar with a counter sits in the
status bar and can be stopped. An error in one file does not stop the rest;
the list of problems appears at the end.

Selecting several photos in the strip (`Ctrl`, `Shift`) exports them together.
The program remembers the settings **separately for each photo**, so returning
to a photo edited earlier restores its sliders. Photos that were never opened
are exported unchanged — the export window says so plainly before you start.

## The program window

The window has two tabs laid out like the workflow: **Edit** and **Map**.
Further modules (library, albums, slideshow) may be added later as more tabs.
The *Export…* button sits in the right corner of the tab bar, so it is at hand
in both views.

The Edit tab:

```
┌──────────────┬──────────────────────────────────┬─────────────────────┐
│ navigator    │                                  │ histogram           │
│              │                                  ├─────────────────────┤
│ ─●────────── │                                  │ CROP AND ROTATE     │
│ Fit    100 % │             preview              │ [crop] ↺90 180 90↻  │
│ [Before/after]                                  │ Angle ─────●──────  │
│              │                                  │ [    Reset crop   ] │
│ photo info   │                                  │ [  Auto  ][ Reset ] │
│   ▾ EXIF     │                                  ├─────────────────────┤
│              │                                  │ sliders — only this │
│              │                                  │ part scrolls        │
├──────────────┴──────────────────────────────────┴─────────────────────┤
│ Show: [All ▾]   1 RAW • 2 JPEG                                        │
│ ▢ ▢ ▢ ▢ ▢ ▢ ▢   thumbnail strip                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**The left panel** answers "where am I in the photo" and "what photo is this":

- **navigator** — the whole photo with a frame around the visible part;
  clicking or dragging moves the preview there. It grows with the panel width
  and can be hidden in the settings,
- **zoom slider** — logarithmic, from "fit to window" to 1600 %. Logarithmic,
  because between fit (e.g. 12 %) and the maximum there is more than a factor
  of a hundred: on a linear scale the whole range below 100 % would fit into
  a few pixels. The slider, the mouse wheel and the *Fit* / *100 %* buttons
  move together; below them the state of the sharp detail is shown
  ("sharpening…", "full sharpness"),
- **Before / after** — holding it shows the photo without edits. The row has
  room for a second button: a split before/after view is planned,
- **photo info** — camera, focal length, shutter speed, aperture, ISO, date
  and location. The arrow in the corner expands the full metadata (see below);
  then only this section scrolls, while the navigator and zoom stay in place.
  The *All tags*, *Discard changes* and *Write to original* buttons are pinned
  to the bottom of the section.

**The right panel** collects what changes the photo. At the top, always
visible: the histogram, crop and rotate (crop button, 90° and 180° rotations,
angle slider, *Reset crop*) and the *Auto* / *Reset* row. Below them the list
of sliders — white balance, tone, presence, noise reduction — scrolling in its
own area.

**Sizes.** The width of both panels and the height of the thumbnail strip are
changed by dragging the edges (the handle lights up under the cursor):

| Element | Range | Default |
|---|---|---|
| left panel | 220–420 px | 260 px |
| right panel | 290–480 px | 340 px |
| thumbnail strip | 90–260 px | 150 px |

When the window is resized, the free space goes to the preview and the panels
keep their width. Thumbnails grow with the strip (always a single row) and are
stored at 300×208 so that they are not blurry in a tall strip. The program
remembers all three sizes between runs. Expanding the metadata does not change
the width of any panel or of the preview.

### Menus and shortcuts

| Menu | Command | Shortcut |
|---|---|---|
| File | Open folder… | `Ctrl+O` |
| | Export… | `Ctrl+E` |
| | Recent folders | |
| | Settings… | `Ctrl+,` |
| | Quit | `Alt+F4` |
| Edit | Auto correction | `Ctrl+U` |
| | Crop (on / off) | `R` |
| View | Fit to window | `Ctrl+0` |
| | Zoom 100 % | `Ctrl+1` |
| Help | About | |

In crop mode `Enter` or `Esc` ends cropping. Double-clicking the preview
toggles fit ↔ 100 %, double-clicking a slider restores its default.
*Help ▸ About* opens the settings window directly on the "About" page.

## Map and geotagging

The **Map** tab has the list of photos with thumbnails and status markers on
the left, an OpenStreetMap map with place search and four layers (map, dark,
satellite, hybrid) in the middle, and the metadata panel on the right.

Assigning a location: select photos in the list, turn on *Assign to selected*
and click a place on the map — all selected photos get that point. Pins show
both locations assigned in the program and those the photos already had from
a camera or phone. Double-clicking the list returns to editing that photo.

**Coordinates do not go into the source file.** They land in the XMP sidecar,
like the edits, and are written into the metadata only in the output file on
export — you can change your mind until the last moment, and the original
stays untouched. The sidecar holds both forms: ours (a signed number) and
`exif:GPS*` for other programs.

The map is a Leaflet page in the browser engine, moved over from a separate
GeoTagger application written earlier in PyQt6. Two Qt bindings cannot live
in one process — each loads its own copy of the Qt libraries — so the page was
moved rather than run alongside. The content itself (HTML and JavaScript)
moved unchanged; what changed is how it talks to Python: **QWebChannel**
instead of a message queue polled by a timer every 100 ms. The old
application imported QWebChannel but did not use it.

The map is created at program start, before the window appears on screen —
and this is a decision about **flicker**, not performance. The browser engine
needs a native window capable of OpenGL composition; added to a window that is
already on screen, it makes Qt rebuild the whole top-level window. It looks as
if the program vanished for a split second and came back. You can see it
directly in the window handle: with lazy creation it changed on the first
visit to the tab, with creation before showing the window it stays the same
(`tools/diag_zakladki.py`). This costs about 260 ms of startup (2080 → 2340 ms),
but it happens before the user sees anything. A bare OpenGL widget instead of
the map is not enough — tested, the window is rebuilt anyway.

Without internet the tab says plainly what is missing instead of showing a grey
rectangle; the photo list and removing locations keep working.

## Keeping your work

Closing the program does not lose edits. The settings of each photo land in a
separate XMP file next to the original and return to the sliders the next time
the folder is opened. This way editing two thousand photos can be spread over
several days, with the whole set exported only at the end.

The non-destructive rule applies to saving too: **the photo file is never
touched**.

Saving happens on every move to another photo and when the window closes, not
only at the end of the session — a program hang after three hours of work
should cost one photo, not three hours. It takes 2 ms, so it cannot be
noticed.

Both photo lists — the thumbnail strip in Edit and the column in Map — speak
the same language. A photo gets two independent markers:

| Marker | Meaning |
|---|---|
| dot | the photo has saved work (settings in the sidecar) |
| pin | the photo has coordinates — assigned in the program or from the camera |

The markers are **drawn**, not added to the file name: a character in the text
would shift names differently in each row and the list would stop reading
as one column. In the strip they sit in the corners of the tile, in the Map
column in a fixed place before the name — there the thumbnails also stand at
the right edge, so all names start at the same place.

The status bar says how many photos have the first marker. Without it,
splitting the editing into stages would make no sense, because after opening
a folder you would not know where you had stopped — and when geotagging you
would not see which shots are still waiting for a pin.

The XMP file holds two sets of values. The `crs:` fields use the same names
as Camera Raw — another program will read something from them. The match is
only partial, though, because our sliders do not correspond one-to-one to
theirs, so we treat them as a courtesy, not as the source of truth. The
`punctum:` fields are our exact values and are what we read.

Two decisions worth noting:

- **We never overwrite other programs' files.** If an XMP written by another
  program lies next to the photo, our settings go into `<name>.punctum.xmp`.
  An extra file is a lesser evil than someone else's work deleted.
- **We never load other programs' settings into the sliders.** Loading a
  sidecar from another program would look like carrying the edit over, but it
  would quietly change the photo — the same numbers mean something else here.

The feature can be turned off in `File ▸ Settings… ▸ General`. The
`File` menu also remembers recently opened folders.

## Metadata (EXIF)

The metadata panel is present in both tabs. In Edit it is the collapsible
bottom of the photo info section in the left panel — the arrow in its corner
expands it, so collapsed it takes no space at all, and expanded it fills the
rest of the panel height and scrolls by itself, without moving the navigator
and the zoom slider. In Map it is a column on the right side of the window.
Both copies show the same state.

There are nineteen editable fields in six groups: authorship (author,
copyright), description (title, comment, keywords, subject), time (three
dates), equipment (make, model, lens, serial number, software), exposure (ISO,
aperture, shutter speed, focal length) and orientation. The *All tags* button
additionally shows the full content of the file, read-only — read only after
the click, because with two thousand photos there is no reason to read
everything from every file.

Changes follow the same path as edits and coordinates: **into the sidecar**,
and into the file's metadata only on export. The *Write to original* button is
an exception on request — it writes them straight into the photo file:

- **JPEG only.** RW2 is Panasonic's closed format and tinkering with its header
  would end with a damaged file. The program says so plainly instead of
  silently skipping such photos.
- **lossless** — only the EXIF header is rewritten, the pixels stay untouched,
  and the file date is put back after writing.
- **existing metadata stays.** Only the fields changed in the panel are
  written; the rest of the header, including the GPS block, passes unchanged.

An empty field means "do not change", not "delete the tag" — deleting metadata
is irreversible, so it must not happen by accident.

## JPEG files

A JPEG goes through exactly the same pipeline as a RAW — with auto correction,
cropping, noise reduction and the GPU preview. There is one difference, in
loading: we remove the sRGB curve from the JPEG to enter the linear pipeline.
`tools/test_jpeg.py` checks this step — a file passed through the whole
pipeline without edits comes out **pixel for pixel identical**.

What cannot be recovered from a JPEG:

- **no headroom in the highlights** — in a RAW there is still material above
  a white wall to pull back, in a JPEG everything above the white point was
  clipped when saving,
- **8 bits in the shadows instead of twelve** — strong lifting shows banding
  where a RAW would give a smooth transition,
- **no camera multipliers or color matrix**, so the "as shot" temperature
  cannot be reconstructed.

That is why white balance works differently for a JPEG, and the program says
so: the slider is then called *Temperature (rel.)* and the status bar says
"relative white balance". We assume the file is sRGB with a D65 white point
(6500 K) and that this is its starting state; the slider shifts the color
**relative to what the camera recorded**, not relative to the scene light.
The kelvins are nominal here.

Export guards one more thing than for RAW: the source file is never the
target. For RAW this was impossible (the output has a different extension);
for a JPEG, exporting into the same folder would hit exactly the original —
so it gets a new name regardless of the chosen overwrite policy.

## Settings

`File ▸ Settings…` (`Ctrl+,`). A narrow list of categories on the left, the
chosen page on the right. The window opens on General; during one run it
returns to the last page viewed.

**General** — the program language, reopening the last folder at startup,
keeping edits in XMP files.

**Performance** — detected hardware (CPU with core count and memory, graphics
card with memory and OpenGL version) and the choice of preview engine:

| Setting | Behavior |
|---|---|
| Auto | The graphics card when available; falls back to the CPU on problems |
| Graphics card | Always computes on the GPU |
| CPU | Always computes on the CPU, the texture is released from GPU memory |

This is also where the preview size lives (the long edge of the image computed
for the fit-to-window view) and the number of threads loading thumbnails.

**Preview** — the delay of the sharp detail and of noise reduction, preview
noise reduction quality, and the zoom above which the image is scaled with
nearest neighbour.

**Interface** — navigator visibility, tooltips and their delay (see below),
and the behavior of the mouse wheel over sliders.

### Mouse wheel over sliders

Qt sends the wheel event to the widget under the cursor, so while scrolling a
long list, sliders slide under a still cursor and catch the event on the way —
the user wanted to scroll the panel and changed the exposure instead.

A slider accepts the wheel only when two independent conditions are met:

- **the list has not been scrolled** for the last 400 ms (the *Lock after
  scrolling* setting) — so continuous scrolling never catches a slider,
- **the cursor has rested over the slider** for at least 220 ms (the
  *Required hover* setting) — this catches a slider that has just slid under
  the cursor.

Deliberate use — hover and turn — works as before. Zero in *Lock after
scrolling* turns the guard off and restores Qt's behavior.

When the conditions are not met, the slider calls `event.ignore()` and Qt
passes the event up to the scroll area — the panel scrolls normally.

**Export** — format, JPEG quality, long edge, noise reduction quality, default
destination folder, default author and copyright.

**About** — version, full hardware and driver details, the settings file path,
library versions.

Settings are stored in `%APPDATA%\Punctum\settings.json` (on Linux
`~/.config/Punctum/`). Saving goes through a temporary file, so an interruption
does not leave a damaged file. Reading is lenient: unknown keys are skipped,
missing ones filled with defaults, out-of-range values clamped — a damaged file
will not block the program from starting.

The same file holds things that are not set in the settings window but in the
course of work: the format filter of the thumbnail strip, folder history, the
last export options and the sizes of the panels and the strip
(`left_panel_width`, `right_panel_width`, `filmstrip_height`). Sizes outside
the allowed ranges are clamped on reading, so a hand-broken file will not leave
a panel in which no button fits.

## Tooltips

Every button, slider and field in the program has a tooltip: a bold title,
a description with practical advice, and a grey line with the keyboard
shortcut, gesture (double-click resets a slider) or field format. Tooltips are
turned off in `Settings ▸ Interface ▸ Show tooltips` — immediately, without
restarting (it is an event filter on the whole application, not deleting the
texts).

The code knows only keys (`suwak.shadows`, `eksport.podfolder`…). The texts
live in `punctum/lang/podpowiedzi.<code>.json`; Polish is the base and
complete. A missing entry or field is taken from Polish, so an incomplete
translation breaks nothing.

## Languages

The program is in English and Polish. The language is chosen in
`Settings ▸ General ▸ Language`; the change takes effect after a
restart, because labels are computed when the windows are built. On first
start the program uses the system language, and English when it does not
know it.

The code writes labels in Polish and passes them through `t()`: `t("Zapisz")`.
The Polish text is the key as well, so the code reads as before and Polish
needs no file of its own. Translations live in
`punctum/lang/interfejs.<code>.json` (Polish → translation pairs), tooltips in
`podpowiedzi.<code>.json`. Another language is two files, with no code changes
— the list in the settings comes from the files on disk.

- **Values in a sentence go by name**, not by gluing pieces together:
  `t("Wczytywanie {plik}…", plik=name)`. In another language the file name or
  the number often stands elsewhere in the sentence.
- **Plurals** have their own function:
  `mnoga(n, "{n} zdjęcie|{n} zdjęcia|{n} zdjęć")`. Polish has three forms,
  English two; a translation gives as many as its language has.
- **Numbers** use the language's decimal separator — "2.50" in English,
  "2,50" in Polish, in number fields too.
- **Qt's own labels** (the folder picker, the text field menu) use the
  standard translation shipped with Qt.

`tools/test_przeklad.py` scans the sources and catches a label shown on screen
that bypassed `t()`, a sentence glued from pieces, a missing translation, an
entry nobody uses, and mismatched `{...}` fields.

## Architecture

### Non-destructive editing

The RAW file is never modified. The full set of settings is described by the
`EditParams` class; the output image is produced only on export.

### Decode once, edit many times

`load_raw()` decodes the file **once** into linear float32 in the camera color
space and keeps it in memory. Every slider move works only on this array —
without it every change would cost ~0.9 s of decoding again.

Demosaicing and highlight reconstruction are left to LibRaw. We take over from
the moment we have linear RGB.

### Order of operations

```
decoding → demosaicing → camera WB            (LibRaw)
─────────────────────────────────────────────────────────
geometry (90° rotation, angle, crop)
white balance correction       ┐
camera space → sRGB            │
exposure                       │ all on LINEAR data
highlights / shadows           │
whites / blacks                │
contrast                       ┘
sRGB transfer curve            ← gamma only here
saturation / vibrance          ← after the curve, not on linear data
noise reduction
```

Tonal operations **must** work on linear data. Applying gamma before exposure
gives plastic, "digital" colors — the most common mistake in amateur RAW
processing programs.

### Two preview layers

The bottom layer is the proxy image (1600 px) stretched over the whole photo —
it appears at once, but is soft when zoomed in. The top layer is the visible
part computed from the **full resolution, directly at screen resolution**; it
is added after ~160 ms and is what gives the sharpness.

The key trick: rotation, crop offset and zoom are combined into one
transformation matrix and `warpAffine` computes only the visible rectangle.
The cost therefore depends on the window size, not on the zoom level or the
file size. Measured sharpness gain over the stretched proxy: **18×** (variance
of the Laplacian 47.4 against 2.6).

### White balance in kelvins

The camera records only channel multipliers, not a color temperature. To show
"7110 K", `estimate_temp_tint()` searches the Planckian locus for the
temperature giving the closest multipliers. The reference program shows
7100 K for the same file.

`tools/verify_color.py` confirms the matrices — multipliers computed for D65
must agree with `daylight_whitebalance` from the file. Difference: 0.006 %.

### Sharpening

An unsharp mask on luminance only (`core/sharpen.py`) — sharpening the color
channels would give colored fringes. *Detail* softly limits the mask amplitude
(`tanh`): a strong edge that would produce a halo is clipped, while fine
texture passes. *Masking* limits sharpening to edges, leaving smooth surfaces
alone. The RAW defaults 40 / 1.0 / 25 / 0 were chosen by measurement against a
Lightroom export at its default sharpening (band energy ratio 0.7–1.5 px and
1.5–4 px, `tools/ostrosc_lab.py`): our 40 gives 106 % of the reference —
deliberately a little more detail.

The shader does not sharpen: like noise reduction, it is computed on the CPU in
a pass after the preview and in the sharp detail when zoomed in. The radius is
given in photo pixels; on a preview downsized so much that the radius drops
below 0.5 px, sharpening is skipped.

### Noise reduction

The *Luminance noise* and *Color noise* sliders do not set an absolute filter
strength, but a strength **relative to the noise measured in the photo itself**
(`core/denoise.py`). This way "50" behaves similarly at ISO 400 and ISO 6400,
in shadows and highlights, for RAW and JPEG.

1. **Measurement.** The Immerkaer filter (zero response to flat backgrounds and
   gradients) gives the noise sigma in brightness bins of 8 levels.
2. **Variance stabilization (VST).** The table `f(v) = ∫ 1/σ(v)` brings the
   noise to the same size in every tone. Without it a filter tuned to the
   shadows blurred the highlights, and one tuned to the highlights left noise
   in the shadows.
3. **Luminance.** Non-local means on the VST data with `h` expressed in
   multiples of the measured sigma (50 → 2σ). Noise is **suppressed, not
   smoothed**: part of the original returns as fine grain (30 → about 30 %,
   50 → 15 %). Lightroom at 30–40 leaves visible grain and that looks better
   than a smooth "wax"; sharpening recovers the contour.
4. **Color.** À trous wavelets on five scales, at half resolution (as JPEG 4:2:0
   stores chrominance). Color noise sits both in fine sparks and in larger
   blotches, so all scales are suppressed.

Calibration on an ISO 6400 photo against Lightroom exports: luminance 50 gives
residual noise close to its 50, color 25 removes colored sparks much like its
default 25. The old pipeline (NLM on the image after the tone curve, fixed `h`)
removed about 20 % of the noise at 50, while Lightroom removed about 85 % at 30.

Cost when exporting a 20 MP photo: 3.6 s at 50/25 (formerly 5.1 s), 0.8 s for
color alone. Fit-to-window preview: 0.2 s.

A known limit: noise depends not only on brightness but also on hue — in
strongly saturated blue (the blue channel has the largest gain) more grain
remains than in greys, because the measurement groups pixels by brightness
only.

**Noise reduction must work on native pixels, before zooming.** Earlier the
pipeline computed it after scaling, so at 400 % the grain was four times larger
than the filter's reach and the slider did nothing visible. The correct order
is also cheaper — the larger the zoom, the fewer native pixels need computing.
On a downsized image the measurement itself detects less noise and the filter
weakens.

Tools: `tools/szum_lab.py` (noise curves on two scales, timings and a mosaic of
1:1 crops against references from another program), `tools/szum_demozaik.py`
(influence of the LibRaw demosaicing algorithm — none of the seven variants
reduced noise, we stay with AHD).

### Auto correction

The auto correction does not guess WHAT is in the photo — it relies on rules
that hold in photography regardless of the subject. Decisions are made in the
perceptual L\* space, where "five units brighter" means the same in shadows and
highlights, so thresholds are set once and work on every frame.

The starting point: **there is no single good histogram**. A correctly exposed
night shot is packed against the left edge, and that is right. An automat that
turns every histogram into a bell in the middle repeats the mistake of a light
meter that turns snow grey.

Exposure has two conditions and the more cautious one decides:

- **content** — the median brightness should land in the zone appropriate for
  the key of the scene,
- **highlights** — diffuse white must not leave the range; a specular highlight
  may burn out, textured white may not, because it cannot be recovered.

The target for the median is shifted by the **scene key** (the share of the
frame lying more than 2.5 stops below the photo's *own* white — a measure of
the scene layout, not of an exposure error) and by the **range** (the longer
the scale, the lower the middle has to sit so the highlights fit under the
shoulder of the curve). A scene without range — a grey card, a plain wall, fog
— has no key, so both shifts fade in proportion to the confidence of the
estimate.

Diffuse white is determined ignoring specular highlights: when the histogram
peak stands more than 1.5 stops away from the 99th percentile, the white point
is taken lower. Otherwise one street lamp in the frame would darken the whole
photo.

The check is `tools/test_auto_zasady.py` — 21 cases on images with known
properties: a grey card and its over- and underexposed versions, an 8 EV and a
2 EV step wedge, a synthetic night and snow, robustness to a specular
highlight. The most important is the last: a night scene set against an
ordinary photo underexposed by 4 EV. The medians differ by less than one L\*
unit and the corrections by two stops — because the decision is made by the
scene layout, not the median brightness.

Comparison with the commercial reference on the reference file (a calibration
of the method, not a goal to imitate):

| parameter | Punctum | reference |
|---|---:|---:|
| exposure | +1.22 | +1.00 |
| contrast | +7 | +6 |
| highlights | −48 | −47 |
| shadows | +57 | +57 |
| whites | 0 | +9 |
| blacks | −3 | −8 |

The auto correction deliberately leaves white balance alone — the camera knows
the lighting conditions better than the histogram, and a "corrected" sunset
loses its point.

This work exposed a flaw in the **whites** slider: it was a plain multiplier of
the whole image, i.e. a second exposure under another name, and could not do
what it exists for — set the white point without brightening everything. It
now acts from about 1.4 stops above middle grey, higher than the highlights
mask, so the two sliders do not duplicate each other.

### Tonal pipeline on the graphics card

The preview is computed by a GLSL fragment shader in an offscreen OpenGL 3.3
context. The full-resolution RAW data go to the GPU memory **once**, when the
photo is opened (244 MB, ~20 ms). Every slider move is then a swap of a dozen
uniforms and a redraw of a rectangle.

One texture yields both the fit-to-window preview and the sharp detail when
zoomed in — mipmaps take care of correct downscaling. Geometry (90° rotation,
angle, crop, zoom) sits in one matrix transforming the texture coordinates, so
cropping and rotating are as cheap as the sliders.

The matrix comes from `core/geometry.py`, which the numpy pipeline also uses —
so the two implementations cannot drift apart. `tools/test_gpu.py` checks
agreement: on eight parameter sets (geometry included) the mean difference is
**0.04 brightness levels**, the maximum 1.

Noise reduction stays on the CPU — non-local means has no sensible shader
counterpart. It is a separate, delayed step: the preview appears at once and
the noise disappears a moment later, when the slider stops.

### Window layout

A few decisions that do not follow from appearance alone:

- **Panels sit on splitters with explicit width limits.** Explicit minimum and
  maximum take precedence in Qt over what the content asks for. Without them,
  expanding the metadata widened the column, because the form wanted more room
  than the sliders, and the photo preview jumped along with it.
- **Remembered sizes are applied only after the window is shown.** Before
  being shown the splitter does not know its real width and would split the
  difference its own way on the first layout; a window opened maximized gets
  its final size a moment after `showEvent`.
- **The zoom slider computes nothing by itself.** The view reports every change
  (wheel, button, fit after a window resize) and the panel only displays it —
  one synchronization path instead of three. A slider move scales the image
  relative to the current state, so the center of the view stays in place.
- **Thumbnail tiles are computed from the height of the whole strip**, not the
  viewport. The viewport changes when a horizontal scrollbar appears, and
  a tile change can hide that scrollbar — and round it goes.
- **The map is still created before the window is shown** (see above) — the
  Edit layout rework does not change that.

## Measured performance

Panasonic DC-G91, 20 Mpix (5200 × 3904), NVIDIA GTX 1660.

Delay from a slider move to a refreshed preview (`tools/test_lag.py`), measured
along the full event path — the threshold of perception is about 16 ms:

| Operation | Median | Worst |
|---|---:|---:|
| Exposure slider | 11.5 ms | 18.9 ms |
| Shadows slider (EV masks) | 12.4 ms | — |
| Color temperature slider | 12.5 ms | 19.6 ms |
| Rotation angle slider | 11.4 ms | 17.6 ms |
| Dragging a crop corner | 3.2 ms | 6.1 ms |
| Rotating by dragging outside the crop | 12.7 ms | 16.3 ms |
| Adding the sharp detail | 16.3 ms | 21.2 ms |

The shader alone computes the preview in **5.9 ms** (169 frames per second);
the rest is image conversion and widget refresh.

Other operations:

| Operation | Time |
|---|---|
| Thumbnail from a RAW file | 102 ms |
| Full decoding | 894 ms |
| Texture upload to the GPU | 20 ms |
| Analysis for auto correction | 90 ms |
| Full processing on the CPU (export) | 4562 ms |

The numpy pipeline remains as the reference and export path and as a safety
net: when the OpenGL context does not come up, the application falls back to
the CPU and says so in the status bar.

## Structure

```
punctum/core/
    params.py        full set of edit settings (EditParams)
    whitebalance.py  Planckian locus, kelvins ↔ multipliers, color matrices
    raw_loader.py    RAW decoding, proxy, thumbnails, orientation
    jpeg_loader.py   JPEG decoding, removing the sRGB curve
    loader.py        common entry for both formats, format filter
    pipeline.py      tonal pipeline, geometry
    denoise.py       noise reduction matched to the measured noise
    sharpen.py       sharpening (unsharp mask on luminance)
    auto.py          automatic choice of settings
    metadata.py      EXIF reading (with Panasonic's own fields)
    exif_edit.py     view of all tags and writing of editable fields
    sidecar.py       saving and loading edits next to the photo (XMP)
    export.py        JPEG / PNG / TIFF output
    settings.py      program settings: reading, saving, validation
    hardware.py      CPU and graphics card detection
punctum/app/
    main_window.py   putting it all together
    image_view.py    canvas, zoom, detail layer, cropping
    edit_panel.py    histogram, photo info, cropping, sliders
    sliders.py       sliders, including those with a color gradient
    navigator.py     thumbnail with the zoom frame
    zoom_panel.py    zoom slider and buttons in the left panel
    filmstrip.py     thumbnail strip
    markers.py       markers next to photo names, shared by both lists
    exif_panel.py    metadata panel: form, tag view, writing
    map_view.py      map tab: photo list, bridge to the page, assigning
    map_page.py      the map page (Leaflet) as HTML and JavaScript
    workers.py       background tasks
    podpowiedzi.py   tooltips: keys, text assembly, languages, switch
    jezyk.py         switching the language for the whole application at start
punctum/przeklad.py  t(), mnoga(), liczba(), list of languages
punctum/lang/        interface translations and tooltip texts, one file per language
tools/               diagnostic tools, tests and CLI
```

Module names, comments and developer notes are in Polish; the interface and
this README are available in English.

## Tests

```powershell
tools\testy.bat --szybkie                 # tests without the UI only, ~5 s
tools\testy.bat "C:\Photos\Trip"          # the whole series, ~300 checks, ~60 s
tools\testy.bat "C:\Photos\Trip" --pelny  # with full result tables
```

By default each test prints only what failed and one summary line — the exit
code equals the number of errors, so the series stops at the first failed test
instead of grinding through the rest.

Tests without the UI (tonal pipeline, auto correction, JPEG, sidecars,
metadata, translations) always run and need nothing beyond the repository.
Tests with the UI open a real window, so they need a folder with photos — one
RAW file and two JPEGs are enough, and the program picks which ones by itself.
The folder can be set once and for all with the `PUNCTUM_TESTY` variable;
without it the series simply skips that part.

| Test | What it guards |
|---|---|
| `test_geo.py` | coordinates in the sidecar without loss of precision, GPS in the export |
| `test_sidecar.py` | the full set of sliders saved and loaded gives exactly the same values |
| `test_auto_zasady.py` | the auto correction on scenes with known properties |
| `test_jpeg.py` | a JPEG passed through the linear pipeline without edits comes out the same |
| `test_exif.py` | writing to the original does not damage the image, the rest of the metadata or the file date |
| `test_przeklad.py` | every on-screen label goes through translation, complete English interface and tooltips, matching `{...}` fields, plurals, decimal separator |
| `test_podpowiedzi.py` | every key in the code has a text, no unused texts, a language with an incomplete translation falls back to Polish, preview noise reduction quality from the settings |
| `test_trwalosc_gui.py` | edits survive moving on and restarting |
| `test_mapa_gui.py` | assigning a point on the map and keeping it |
| `test_jpeg_gui.py` | a mixed folder: format filter, white balance description |
| `test_znaczniki_gui.py` | markers on the lists and the metadata panel in both tabs |
| `test_uklad_gui.py` | window layout: element visibility when maximized, widths when the metadata expands, the zoom slider, dragging and remembering sizes |
| `test_podpowiedzi_gui.py` | no button, slider or field in the main window, Settings and export without a tooltip; the tooltip switch |

The layout test also saves a screenshot of the window (`punctum-uklad.png` in
the temporary folder) — this is how we check the appearance after changes
without asking for screenshots.

Tests with the UI wait for a **condition**, not a fixed time — a loaded machine
once failed to load a photo within the set seconds and the series fell over on
correct code. For the same reason the test stages run in a chain: the next one
starts when the previous one returns, not at a set second. This change alone
cut the series from 105 to 37 seconds.

## Not there yet

- Matching locations to a GPS track (GPX files) and grouping by day — for now
  coordinates are assigned to a selection of photos.
- Presets and copying settings between photos.
- Fast batch export — it works, but computes sequentially on the CPU.
- Google Photos integration.
- A split before/after view (a dividing line or two views side by side) — for
  now *Before / after* works by holding the button.
- Tool icons in one style — the rotate buttons are characters for now; only
  cropping has an icon.
