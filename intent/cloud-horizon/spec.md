# Spec: no whirl in the clouds

## Concerns

- **This is a change of look**, so it waits for Evan (`intent.md`: a look test before a look change
  is installed).
- **Less true to the real sky.** A cloud is no longer drawn where a flat layer over Budapest would
  put it on a panorama. The sun, moon and stars keep their true places; only the cloud layers are
  laid out as for an ordinary view. A shadow on the sea can lie up to about 20 degrees of azimuth
  from the cloud that casts it, at the frame's edges. Nothing in the picture lets a viewer check.
- **Cirrus streaks are not always along the wind.** A wind blowing toward or away from the viewer
  would point the streaks at a vanishing point inside the frame, which is the fan the change removes.
  They are held at least 60 degrees off the view's axis.
- **Every cloudy frame changes**, including which minutes a cloud covers the sun.

## Requirements

1. The three noise layers (`sky.CLOUD_LAYERS`) are sampled through one function, `cloud_plane`: a
   flat layer as a rectilinear lens sees it, the lens looking south along the horizon and reaching
   45 degrees (`LENS_TOP`) at the frame's top edge. Straight lines on the layer are straight on
   screen; a round cloudlet is round at the top edge, twice as wide as tall at half height.
2. `sun_visibility` and `water.sea_shadow` use the same function (they already go through
   `_layer_field`), so the cloud drawn over the sun is the cloud that dims it.
3. Cirrus streaks lie along `streak_bearing(wind)`: the wind's axis, held at least `STREAK_MIN` (60)
   degrees off the view's axis; within `STREAK_SWING` (6) degrees of it they turn through it, so the
   bearing is continuous in the wind direction.
4. Cloud noise is sampled with a cubic B-spline (`core.sample_smooth`).
5. Frames without cloud are byte-identical to `main`; the reference set r3 keeps its digest.
6. The heaps (`cumulus.py`, parked behind `HEAPS = False`) are left as they are.

## Proof

- `./venv/bin/python -m unittest tests.test_clouds`: straight lines stay straight; the cloudlet's
  shape at the top and at half height; the streak rule; a clear frame equals `main`'s (by the
  reference test below).
- `./venv/bin/python -m unittest discover -s tests`; `tests/test_shore_reference.py` (digest of r3).
- Determinism: the look test's frames rendered twice, no byte differs.
- Cost: CPU seconds for the same 20 minutes of a cloudy day, before and after.
- The look test: `out/look/cloud-horizon/` (`render.sh`, `pairs.py`, `README.md`).
