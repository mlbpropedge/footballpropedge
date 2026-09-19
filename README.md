# Football Prop Edge

Zero-cost NFL player projection site for rushing yards, receiving yards, and anytime-touchdown probability.

## Architecture
- **Data:** nflverse weekly player stats + schedules (free/open tooling)
- **Models:** candidate gradient-boosting / tree regressors and classifiers, chosen by walk-forward validation
- **Leakage control:** rolling player features are shifted so the game being predicted never appears in its own features
- **Overfitting checks:** train-vs-walk-forward error ratio is recorded with each build
- **Automation:** GitHub Actions refreshes projections and commits JSON outputs
- **Hosting:** static GitHub Pages site; no paid server/database/API required

## Local run
```bash
pip install -r requirements.txt
python scripts/build_predictions.py
python -m http.server 8000 -d site
```

Then open `http://localhost:8000`.

## Important
Predictions are statistical estimates, not guarantees. Underlying NFL data remains subject to the terms of its respective owners.
