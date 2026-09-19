from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import RANDOM_STATE
from .features import feature_columns


@dataclass
class ModelBundle:
    rushing_model: object
    receiving_model: object
    td_model: object
    metrics: dict


def _regression_candidates():
    return {
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            loss="absolute_error",
            learning_rate=0.05,
            max_iter=350,
            max_leaf_nodes=24,
            l2_regularization=2.0,
            random_state=RANDOM_STATE,
        ),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=350,
            min_samples_leaf=6,
            max_features=0.75,
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
    }


def _classification_candidates():
    return {
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            learning_rate=0.04,
            max_iter=300,
            max_leaf_nodes=20,
            l2_regularization=2.0,
            random_state=RANDOM_STATE,
        ),
        "logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(
                max_iter=1500,
                C=0.35,
                class_weight="balanced",
                random_state=RANDOM_STATE,
            ),
        ),
    }


def _clean_xy(df: pd.DataFrame, target: str):
    X = df[feature_columns()].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = pd.to_numeric(df[target], errors="coerce").fillna(0.0)
    return X, y


def _role_frame(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """Evaluate/train each market on players with a real pre-game role.

    This avoids deceptively low errors caused by scoring hundreds of near-zero
    outcomes that would never be useful projections on the site.
    """
    if target == "rushing_yards":
        mask = (df["carries_avg_3"] >= 2.0) | (df["carries_avg_5"] >= 2.5)
        return df[mask].copy()
    if target == "receiving_yards":
        mask = (df["targets_avg_3"] >= 1.5) | (df["targets_avg_5"] >= 2.0)
        return df[mask].copy()
    if target == "touchdown":
        mask = (df["opportunities_avg_3"] >= 3.0) | (df["opportunities_avg_5"] >= 4.0)
        return df[mask].copy()
    return df.copy()


def walk_forward_regression(df: pd.DataFrame, target: str) -> tuple[str, dict]:
    df = _role_frame(df, target)
    seasons = sorted(int(s) for s in df["season"].dropna().unique())
    test_seasons = seasons[-3:] if len(seasons) >= 4 else seasons[-1:]
    scores = {name: [] for name in _regression_candidates()}
    details = {}

    for test_season in test_seasons:
        train = df[df["season"] < test_season]
        test = df[df["season"] == test_season]
        if len(train) < 400 or len(test) < 40:
            continue
        Xtr, ytr = _clean_xy(train, target)
        Xte, yte = _clean_xy(test, target)
        for name, model in _regression_candidates().items():
            model.fit(Xtr, ytr)
            pred = np.clip(model.predict(Xte), 0, None)
            mae = mean_absolute_error(yte, pred)
            rmse = mean_squared_error(yte, pred) ** 0.5
            scores[name].append(mae)
            details.setdefault(name, []).append(
                {
                    "season": test_season,
                    "samples": int(len(test)),
                    "mae": round(float(mae), 3),
                    "rmse": round(float(rmse), 3),
                }
            )

    viable = {k: v for k, v in scores.items() if v}
    if not viable:
        return "hist_gradient_boosting", details
    winner = min(viable, key=lambda k: float(np.mean(viable[k])))
    return winner, details


def walk_forward_td(df: pd.DataFrame) -> tuple[str, dict]:
    df = _role_frame(df, "touchdown")
    seasons = sorted(int(s) for s in df["season"].dropna().unique())
    test_seasons = seasons[-3:] if len(seasons) >= 4 else seasons[-1:]
    scores = {name: [] for name in _classification_candidates()}
    details = {}

    for test_season in test_seasons:
        train = df[df["season"] < test_season]
        test = df[df["season"] == test_season]
        if len(train) < 400 or len(test) < 40 or train["touchdown"].nunique() < 2:
            continue
        Xtr, ytr = _clean_xy(train, "touchdown")
        Xte, yte = _clean_xy(test, "touchdown")
        for name, model in _classification_candidates().items():
            model.fit(Xtr, ytr)
            prob = np.clip(model.predict_proba(Xte)[:, 1], 0.001, 0.999)
            brier = brier_score_loss(yte, prob)
            scores[name].append(brier)
            details.setdefault(name, []).append(
                {
                    "season": test_season,
                    "samples": int(len(test)),
                    "brier": round(float(brier), 4),
                }
            )

    viable = {k: v for k, v in scores.items() if v}
    if not viable:
        return "hist_gradient_boosting", details
    winner = min(viable, key=lambda k: float(np.mean(viable[k])))
    return winner, details


def fit_models(df: pd.DataFrame) -> ModelBundle:
    rush_df = _role_frame(df, "rushing_yards")
    rec_df = _role_frame(df, "receiving_yards")
    td_df = _role_frame(df, "touchdown")

    rush_name, rush_cv = walk_forward_regression(df, "rushing_yards")
    rec_name, rec_cv = walk_forward_regression(df, "receiving_yards")
    td_name, td_cv = walk_forward_td(df)

    X_rush, y_rush = _clean_xy(rush_df, "rushing_yards")
    rush_model = _regression_candidates()[rush_name]
    rush_model.fit(X_rush, y_rush)

    X_rec, y_rec = _clean_xy(rec_df, "receiving_yards")
    rec_model = _regression_candidates()[rec_name]
    rec_model.fit(X_rec, y_rec)

    X_td, y_td = _clean_xy(td_df, "touchdown")
    td_model = _classification_candidates()[td_name]
    td_model.fit(X_td, y_td)

    rush_train_mae = mean_absolute_error(
        y_rush, np.clip(rush_model.predict(X_rush), 0, None)
    )
    rec_train_mae = mean_absolute_error(
        y_rec, np.clip(rec_model.predict(X_rec), 0, None)
    )

    def avg_cv(rows, key):
        vals = [x[key] for x in rows]
        return round(float(np.mean(vals)), 3) if vals else None

    metrics = {
        "rushing": {
            "model": rush_name,
            "role_filtered": True,
            "training_samples": int(len(rush_df)),
            "walk_forward": rush_cv.get(rush_name, []),
            "cv_mae": avg_cv(rush_cv.get(rush_name, []), "mae"),
            "train_mae": round(float(rush_train_mae), 3),
        },
        "receiving": {
            "model": rec_name,
            "role_filtered": True,
            "training_samples": int(len(rec_df)),
            "walk_forward": rec_cv.get(rec_name, []),
            "cv_mae": avg_cv(rec_cv.get(rec_name, []), "mae"),
            "train_mae": round(float(rec_train_mae), 3),
        },
        "touchdown": {
            "model": td_name,
            "role_filtered": True,
            "training_samples": int(len(td_df)),
            "walk_forward": td_cv.get(td_name, []),
            "cv_brier": avg_cv(td_cv.get(td_name, []), "brier"),
        },
    }

    for key in ("rushing", "receiving"):
        cv = metrics[key]["cv_mae"]
        tr = metrics[key]["train_mae"]
        metrics[key]["overfit_ratio"] = (
            round(float(cv / max(tr, 0.01)), 2) if cv else None
        )
        metrics[key]["overfit_flag"] = bool(
            cv and cv / max(tr, 0.01) > 1.8
        )

    return ModelBundle(rush_model, rec_model, td_model, metrics)


def predict(bundle: ModelBundle, features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    X = out[feature_columns()].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    rush = np.clip(bundle.rushing_model.predict(X), 0, None)
    rec = np.clip(bundle.receiving_model.predict(X), 0, None)
    td = np.clip(bundle.td_model.predict_proba(X)[:, 1], 0.001, 0.999)

    # Do not extrapolate market-specific models far outside their trained roles.
    rush = np.where(out["carries_avg_3"].fillna(0) >= 1.0, rush, 0.0)
    rec = np.where(out["targets_avg_3"].fillna(0) >= 0.75, rec, 0.0)
    td = np.where(out["opportunities_avg_3"].fillna(0) >= 2.0, td, 0.01)

    out["projected_rushing_yards"] = rush
    out["projected_receiving_yards"] = rec
    out["touchdown_probability"] = td
    return out
