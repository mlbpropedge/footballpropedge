# Football Prop Edge

Zero-cost NFL player projection site for rushing yards, receiving yards, and anytime-touchdown probability.

## Architecture
- **Data:** nflverse weekly player stats + schedules (free/open tooling)
- **Availability:** nflverse injury reports and weekly rosters. Players listed Out, on a reserve list, released or inactive are removed from the slate and shown in a "Ruled out" list; Questionable/Doubtful players are tagged. Traded players use their current roster team. Every availability feed is optional, so an outage never blocks a refresh.
- **Usage context:** nflverse snap counts (offensive snap share, last 3 games) and games-missed streaks (bye weeks excluded)
- **Change tags:** each refresh compares against the previous run of the same slate and tags moves of 5+ yards or 5+ TD points
- **Results:** graded weekly with 80%-range hit rates, TD calibration buckets, and a simple TD baseline (last-8 TD rate blended with league rate); the full graded list is in `data/results_detail.json`
- **Models:** candidate gradient-boosting / tree regressors and classifiers, chosen by walk-forward validation
- **Leakage control:** rolling player features are shifted so the game being predicted never appears in its own features
- **Overfitting checks:** train-vs-walk-forward error ratio is recorded with each build
- **Automation:** GitHub Actions refreshes every day in season, with a second Sunday pregame refresh; a publication check prevents malformed slates from being committed
- **Hosting:** static GitHub Pages site; no paid server/database/API required
- **Results:** the first game's date freezes the archived pregame snapshot; later refreshes preserve projections for games already played

## Local run
```bash
pip install -r requirements.txt
python scripts/build_predictions.py
python scripts/add_prediction_ranges.py
python scripts/check_publication.py
python -m http.server 8000 -d .
```

Then open `http://localhost:8000`.

GitHub Pages serves the repository root. The `site/` folder was an obsolete copy and has been removed.

## Important
Predictions are statistical estimates, not guarantees. Underlying NFL data remains subject to the terms of its respective owners.
