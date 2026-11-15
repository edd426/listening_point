# Spec: render tomorrow once

## Concerns

- **A missed evening.** If the Mac is asleep or on battery from 18:00 to midnight, tomorrow is not
  ready at 00:00. Before this change it usually was (rendered that morning with the morning's
  forecast). What happens instead: the helper shows the same minute of the newest earlier day and
  kicks the job; on power the job renders "the rest of today" from the current minute and catches up
  inside a minute or two; on battery it renders three hours at a time, as now. In the log the Mac was
  awake on power after 18:00 on all 14 days checked, so this should be rare.
- **The forecast used.** `weather.day_weather` fetches a fresh forecast on every render start, so a
  render begun at 18:00 uses the 18:00 forecast. No change test is needed any more.

## Requirements

1. On power, a run renders the rest of today, then the hourly wallpaper, then, only if the local
   clock reads 18:00 or later on the same date the run started, all of tomorrow.
2. The clock is read again after today's frames are done: a run that starts at 17:50 and finishes
   today at 18:20 goes on to tomorrow; a run that crosses midnight does not (the next run sees a new
   today).
3. Before 18:00 nothing of tomorrow is rendered, with `--force` too. `--date` still renders any date.
4. On battery nothing changes.
5. Frames of tomorrow are never deleted for a forecast change. `refresh_tomorrow` and the `evening`
   flag go; `weather.json` stays as a record of the forecast a day was made with.
6. The shore and lamp rule (`refresh_shore`) still runs for today and tomorrow on every run.

## Design

- `TOMORROW_FROM = 18` and `tomorrow_due(t, today)` in `tools/nightly.py`.
- `main(argv=None, clock=dt.datetime.now)` so tests can set the time.

## Proof

- `./venv/bin/python -m unittest tests.test_nightly`: the calls to `render` at 10:00, 18:00, a run
  that crosses 18:00, a run that crosses midnight, on battery, and with `--force`.
- `/usr/bin/python3 -m unittest tests.test_shore_sync` still passes (it reads `main`'s source).
- After install: the log shows one `(tomorrow)` render a day, after 18:00, and no
  `(evening forecast)` line.
