# Football Prop Edge

Zero-cost NFL player projection site for rushing yards, receiving yards, and anytime-touchdown probability.

## Architecture
- **Data:** nflverse weekly player stats + schedules (free/open tooling)
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
