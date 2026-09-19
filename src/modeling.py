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
    td_calibration_base_rate: float
    td_calibration_slope: float
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


def _baseline_predictions(test: pd.DataFrame, target: str) -> dict[str, np.ndarray]:
    if target == "rushing_yards":
        workload = (
            pd.to_numeric(test["carries_avg_3"], errors="coerce").fillna(0.0)
            * pd.to_numeric(test["yards_per_carry_avg_5"], errors="coerce").fillna(0.0)
        )
    else:
        workload = (
            pd.to_numeric(test["targets_avg_3"], errors="coerce").fillna(0.0)
            * pd.to_numeric(test["yards_per_target_avg_5"], errors="coerce").fillna(0.0)
        )

    return {
        "last_3": np.clip(
            pd.to_numeric(test[f"{target}_avg_3"], errors="coerce").fillna(0.0).to_numpy(),
            0,
            None,
        ),
        "last_5": np.clip(
            pd.to_numeric(test[f"{target}_avg_5"], errors="coerce").fillna(0.0).to_numpy(),
            0,
            None,
        ),
        "season_average": np.clip(
            pd.to_numeric(test[f"{target}_season_avg"], errors="coerce").fillna(0.0).to_numpy(),
            0,
            None,
        ),
        "workload": np.clip(workload.to_numpy(), 0, None),
    }


def benchmark_regression(df: pd.DataFrame, target: str, model_name: str) -> dict:
    frame = _role_frame(df, target)
    seasons = sorted(int(s) for s in frame["season"].dropna().unique())
    test_seasons = seasons[-3:] if len(seasons) >= 4 else seasons[-1:]
    model_scores = []
    baseline_scores = {k: [] for k in ("last_3", "last_5", "season_average", "workload")}
    diagnostic_rows = []
    sample_count = 0

    for test_season in test_seasons:
        train = frame[frame["season"] < test_season]
        test = frame[frame["season"] == test_season]
        if len(train) < 400 or len(test) < 40:
            continue

        Xtr, ytr = _clean_xy(train, target)
        Xte, yte = _clean_xy(test, target)
        model = _regression_candidates()[model_name]
        model.fit(Xtr, ytr)
        model_pred = np.clip(model.predict(Xte), 0, None)
        abs_err = np.abs(yte.to_numpy() - model_pred)
        model_scores.extend(abs_err.tolist())
        sample_count += len(test)

        workload_col = "carries_avg_3" if target == "rushing_yards" else "targets_avg_3"
        diag = test[["position", workload_col]].copy()
        diag["abs_error"] = abs_err
        diag["workload"] = pd.to_numeric(diag[workload_col], errors="coerce").fillna(0.0)
        diagnostic_rows.append(diag[["position", "workload", "abs_error"]])

        for name, pred in _baseline_predictions(test, target).items():
            baseline_scores[name].extend(np.abs(yte.to_numpy() - pred).tolist())

    model_mae = float(np.mean(model_scores)) if model_scores else None
    baselines = {
        name: round(float(np.mean(values)), 3) if values else None
        for name, values in baseline_scores.items()
    }
    valid = {k: v for k, v in baselines.items() if v is not None}
    best_baseline_name = min(valid, key=valid.get) if valid else None
    best_baseline_mae = valid.get(best_baseline_name) if best_baseline_name else None

    error_breakdown = {"by_position": {}, "by_workload": {}}
    if diagnostic_rows:
        diagnostics = pd.concat(diagnostic_rows, ignore_index=True)
        for pos, grp in diagnostics.groupby("position"):
            if len(grp) >= 30:
                error_breakdown["by_position"][str(pos)] = {
                    "samples": int(len(grp)),
                    "mae": round(float(grp["abs_error"].mean()), 3),
                }

        bins = [-0.001, 4, 8, 14, float("inf")]
        labels = ["low", "medium", "high", "elite"]
        diagnostics["workload_bucket"] = pd.cut(
            diagnostics["workload"], bins=bins, labels=labels
        )
        for bucket, grp in diagnostics.groupby("workload_bucket", observed=True):
            if len(grp) >= 30:
                error_breakdown["by_workload"][str(bucket)] = {
                    "samples": int(len(grp)),
                    "mae": round(float(grp["abs_error"].mean()), 3),
                    "avg_workload": round(float(grp["workload"].mean()), 2),
                }

    return {
        "samples": int(sample_count),
        "model_mae": round(model_mae, 3) if model_mae is not None else None,
        "baselines": baselines,
        "best_baseline": best_baseline_name,
        "best_baseline_mae": best_baseline_mae,
        "model_improvement_yards": round(best_baseline_mae - model_mae, 3)
        if model_mae is not None and best_baseline_mae is not None
        else None,
        "model_improvement_pct": round(
            100.0 * (best_baseline_mae - model_mae) / best_baseline_mae, 2
        )
        if model_mae is not None and best_baseline_mae not in (None, 0)
        else None,
        "beats_best_baseline": bool(
            model_mae is not None
            and best_baseline_mae is not None
            and model_mae < best_baseline_mae
        ),
        "error_breakdown": error_breakdown,
    }


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


def apply_td_calibration(
    probabilities: np.ndarray,
    base_rate: float,
    slope: float,
) -> np.ndarray:
    """Shrink or expand raw TD probabilities around the historical base rate."""
    probabilities = np.asarray(probabilities, dtype=float)
    calibrated = float(base_rate) + float(slope) * (
        probabilities - float(base_rate)
    )
    return np.clip(calibrated, 0.001, 0.999)


def fit_td_calibration(df: pd.DataFrame, model_name: str) -> tuple[float, float, dict]:
    """Fit and honestly evaluate a lightweight time-aware TD calibrator.

    Every probability is generated out of sample by a model trained only on
    earlier seasons. Calibration parameters are selected on the older 80% of
    those predictions and evaluated on the newest 20%. Deployment parameters
    are then refit on all out-of-sample predictions for the next future slate.
    """
    frame = _role_frame(df, "touchdown").copy()
    seasons = sorted(int(s) for s in frame["season"].dropna().unique())
    test_seasons = seasons[-3:] if len(seasons) >= 4 else seasons[-1:]
    rows = []

    for test_season in test_seasons:
        train = frame[frame["season"] < test_season]
        test = frame[frame["season"] == test_season]
        if len(train) < 400 or len(test) < 40 or train["touchdown"].nunique() < 2:
            continue
        Xtr, ytr = _clean_xy(train, "touchdown")
        Xte, yte = _clean_xy(test, "touchdown")
        model = _classification_candidates()[model_name]
        model.fit(Xtr, ytr)
        prob = np.clip(model.predict_proba(Xte)[:, 1], 0.001, 0.999)
        for season, week, actual, raw_prob in zip(
            test["season"], test["week"], yte.to_numpy(), prob
        ):
            rows.append(
                {
                    "season": int(season),
                    "week": int(week),
                    "actual": int(actual),
                    "raw_probability": float(raw_prob),
                }
            )

    if len(rows) < 100:
        return 0.20, 1.0, {
            "method": "time-aware linear probability scaling",
            "samples": len(rows),
            "available": False,
        }

    oof = pd.DataFrame(rows).sort_values(["season", "week"]).reset_index(drop=True)
    split = max(50, int(len(oof) * 0.80))
    split = min(split, len(oof) - 30)
    older, newest = oof.iloc[:split], oof.iloc[split:]
    candidate_slopes = np.linspace(0.0, 1.5, 61)

    def best_parameters(part: pd.DataFrame) -> tuple[float, float]:
        actual = part["actual"].to_numpy(dtype=float)
        raw = part["raw_probability"].to_numpy(dtype=float)
        base = float(actual.mean())
        slope = min(
            candidate_slopes,
            key=lambda value: brier_score_loss(
                actual, apply_td_calibration(raw, base, float(value))
            ),
        )
        return base, float(slope)

    eval_base, eval_slope = best_parameters(older)
    eval_actual = newest["actual"].to_numpy(dtype=float)
    eval_raw = newest["raw_probability"].to_numpy(dtype=float)
    eval_calibrated = apply_td_calibration(eval_raw, eval_base, eval_slope)
    raw_brier = float(brier_score_loss(eval_actual, eval_raw))
    calibrated_brier = float(brier_score_loss(eval_actual, eval_calibrated))

    deploy_base, deploy_slope = best_parameters(oof)
    improvement = raw_brier - calibrated_brier
    return deploy_base, deploy_slope, {
        "method": "time-aware linear probability scaling",
        "available": True,
        "leakage_safe": True,
        "samples": int(len(oof)),
        "evaluation_samples": int(len(newest)),
        "base_rate": round(float(deploy_base), 4),
        "slope": round(float(deploy_slope), 3),
        "raw_brier": round(raw_brier, 4),
        "calibrated_brier": round(calibrated_brier, 4),
        "improvement": round(improvement, 4),
        "improvement_pct": round(100.0 * improvement / raw_brier, 2)
        if raw_brier > 0
        else 0.0,
        "improves_brier": bool(calibrated_brier < raw_brier),
    }


def fit_models(df: pd.DataFrame) -> ModelBundle:
    rush_df = _role_frame(df, "rushing_yards")
    rec_df = _role_frame(df, "receiving_yards")
    td_df = _role_frame(df, "touchdown")

    rush_name, rush_cv = walk_forward_regression(df, "rushing_yards")
    rec_name, rec_cv = walk_forward_regression(df, "receiving_yards")
    td_name, td_cv = walk_forward_td(df)
    td_base_rate, td_calibration_slope, td_calibration = fit_td_calibration(
        df, td_name
    )

    rush_benchmark = benchmark_regression(df, "rushing_yards", rush_name)
    rec_benchmark = benchmark_regression(df, "receiving_yards", rec_name)

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
            "benchmark": rush_benchmark,
        },
        "receiving": {
            "model": rec_name,
            "role_filtered": True,
            "training_samples": int(len(rec_df)),
            "walk_forward": rec_cv.get(rec_name, []),
            "cv_mae": avg_cv(rec_cv.get(rec_name, []), "mae"),
            "train_mae": round(float(rec_train_mae), 3),
            "benchmark": rec_benchmark,
        },
        "touchdown": {
            "model": td_name,
            "role_filtered": True,
            "training_samples": int(len(td_df)),
            "walk_forward": td_cv.get(td_name, []),
            "raw_cv_brier": avg_cv(td_cv.get(td_name, []), "brier"),
            "cv_brier": td_calibration.get("calibrated_brier")
            if td_calibration.get("available")
            else avg_cv(td_cv.get(td_name, []), "brier"),
            "calibration": td_calibration,
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

    return ModelBundle(
        rush_model,
        rec_model,
        td_model,
        td_base_rate,
        td_calibration_slope,
        metrics,
    )


def predict(bundle: ModelBundle, features: pd.DataFrame) -> pd.DataFrame:
    out = features.copy()
    X = out[feature_columns()].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    rush = np.clip(bundle.rushing_model.predict(X), 0, None)
    rec = np.clip(bundle.receiving_model.predict(X), 0, None)
    td_raw = np.clip(bundle.td_model.predict_proba(X)[:, 1], 0.001, 0.999)
    td = apply_td_calibration(
        td_raw,
        bundle.td_calibration_base_rate,
        bundle.td_calibration_slope,
    )

    # Do not extrapolate market-specific models far outside their trained roles.
    rush = np.where(out["carries_avg_3"].fillna(0) >= 1.0, rush, 0.0)
    rec = np.where(out["targets_avg_3"].fillna(0) >= 0.75, rec, 0.0)
    td = np.where(out["opportunities_avg_3"].fillna(0) >= 2.0, td, 0.01)

    out["projected_rushing_yards"] = rush
    out["projected_receiving_yards"] = rec
    out["touchdown_probability"] = td
    return out
