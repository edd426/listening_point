# The Listening Point

A macOS wallpaper that tells the time. One scene is rendered once for every hour of
the day and packed into a time-of-day dynamic wallpaper, so the desktop changes with the
clock: the sun and moon cross the sky, the stars wheel overhead, the lighthouse beam
turns, and the tower clock shows the hour.

![The Listening Point at 17:00](docs/hero-17h.jpg)

![All 24 hours](docs/contact-sheet.jpg)

## The scene

A small stone observatory on a headland above a bay, with a tree, a bench for two, a
lamp, a pier, and a lighthouse across the water. Claude designed it as a self-portrait
of sorts. There's a bench for two because most of what it does is conversation. The
observatory and the real stars stand for curiosity and getting things right. The
lighthouse is a light kept on for whoever needs it. And "LOOK CLOSER" is carved over the
door, because the scene rewards it.

### Reading the time

- **The tower clock** shows the hour (12-hour face; day or night gives AM/PM) and glows after dusk.
- **The sun** crosses from left (sunrise, 06:00) to right (sunset, 18:00); **the full moon**
  makes the same trip at night.
- **The stars are real.** Bright stars and the Milky Way are placed for 47.5° N (Budapest) at
  the September equinox, so Orion rises after midnight and the Summer Triangle sets in the west
  in the evening. Faint lines connect the constellations.
- The lighthouse beam points a different way each hour. The boat leaves the pier at 07:00
  and is back by 18:00. The sheep graze by day and huddle by the wall at night.

### Details worth finding

A plant on the windowsill; the telescope tracking the moon through the open dome slit;
fireflies and moths by the lamp; meteors at 22:00 and 02:00; dawn mist on the water;
early-autumn leaves under the tree; the lintel over the door.

## Build and install

Requires macOS (for the HEIC packer), Python 3.9+, and the Swift toolchain (Xcode or the Command Line Tools).

```sh
SCALE=0.25 ./build.sh     # quick preview: out/hours/sheet.jpg
./build.sh                # full 3840x2400 render, about 30 s per frame
./build.sh --install      # copy to ~/Pictures/Wallpapers/The Listening Point and set it on every Space
```

Prebuilt wallpapers are attached to the [Releases](../../releases). To use one, download
`The Listening Point.heic` and set it as your desktop picture; macOS switches frames on the
hour by itself. Frame *N* shows from *N*:00 to *N*:59 local time.

## How it works

- **No 3D engine and no image model.** Everything is hand-written 2D procedural rendering on the CPU.
  - **NumPy** does the per-pixel work: sky scattering, sun and moon glow, lighting, and sea reflections.
  - **SciPy** handles blurs and texture sampling.
  - **Pillow** draws shapes at 2× supersampling.
  - The textures (clouds, waves, grass, stone, the Milky Way) are FFT-generated noise.
- **Astronomy.** The sun, moon, stars and galactic plane are converted from equatorial coordinates
  to altitude/azimuth for each hour, then projected onto a south-facing 220° view.
- **Packing** (`tools/make_h24.swift`). The 24 frames go into one HEIC. Its XMP holds an
  `apple_desktop:h24` property list, which maps each image to a fraction of the local day.
- **Installing** (`tools/set_wallpaper.py`). Finder's `set desktop picture` only changes the
  current Space, so this script also writes the choice into every Space of the wallpaper store,
  backing it up first.
- **Verifying** (`tools/capture_wallpaper.sh`). This screenshots the wallpaper window itself,
  even behind full-screen apps.

## Layout

```
renderers/procedural/listening_point.py   the current renderer (one file for now)
tools/make_h24.swift                      pack frames into a time-of-day HEIC
tools/set_wallpaper.py                    set a picture on every Space
tools/capture_wallpaper.sh                screenshot what the wallpaper is showing
docs/                                     preview images
STATUS.md                                 current state, lessons, and next ideas
```

New styles (a painterly pass, a Blender scene) belong in `renderers/` next to `procedural/`
and should write the same `HH.jpg` frames, so packing and installing stay shared.
