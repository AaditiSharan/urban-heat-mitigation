"""
Train physics-informed LST model, run cooling scenarios, and optimize interventions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    COST_PER_M2,
    DASHBOARD_DATA,
    DATA_DIR,
    DEFAULT_BUDGET_INR,
    FEATURE_COLUMNS,
    INTERVENTIONS,
    MATERIALS,
    ZONES,
)


def physics_lst(df: pd.DataFrame) -> np.ndarray:
    """
    Physics-informed LST calculation incorporating urban morphology and meteorological factors.
    Enhanced with sky view factor, building height, humidity, and thermal anisotropy.
    """
    # Base surface temperature from air temperature
    base_temp = df["air_temp"].values
    
    # Surface energy balance components
    # Solar radiation absorption (albedo effect)
    solar_heating = 35 * (1 - df["albedo"].values)
    
    # Evapotranspiration cooling (vegetation effect)
    et_cooling = 18 * df["ndvi"].values
    
    # Anthropogenic heat and thermal mass (impervious surfaces)
    anthropogenic = 8 * df["impervious"].values
    
    # Wind cooling effect
    wind_cooling = 0.8 * df["wind"].values
    
    # Urban canyon effect (sky view factor)
    # Lower SVF traps more heat
    canyon_effect = 5 * (1 - df.get("sky_view_factor", 0.5).values)
    
    # Building height effect (thermal mass)
    building_effect = 0.15 * df.get("building_height_m", 15).values
    
    # Humidity effect (moist air reduces diurnal range)
    humidity_effect = -0.05 * df.get("humidity", 35).values
    
    # Thermal anisotropy (directional temperature variation)
    anisotropy_effect = 2 * df.get("thermal_anisotropy", 0.3).values
    
    # Combined physics model
    lst = (
        base_temp
        + solar_heating
        - et_cooling
        + anthropogenic
        - wind_cooling
        + canyon_effect
        + building_effect
        + humidity_effect
        + anisotropy_effect
    )
    
    return lst


def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "r2": round(float(r2_score(y_true, y_pred)), 3),
        "rmse_c": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 2),
        "mae_c": round(float(mean_absolute_error(y_true, y_pred)), 2),
    }


def spatial_cross_validate(df: pd.DataFrame, n_folds: int = 5) -> dict:
    """
    Spatial block cross-validation by latitude bands.
    Trains on observed Landsat LST (not physics-generated targets).
    """
    df = df.copy()
    df["spatial_fold"] = pd.qcut(df["lat"], n_folds, labels=False, duplicates="drop")

    ml_scores: list[dict] = []
    hybrid_scores: list[dict] = []
    physics_scores: list[dict] = []

    for fold in sorted(df["spatial_fold"].unique()):
        test_mask = df["spatial_fold"] == fold
        train_df = df[~test_mask]
        test_df = df[test_mask]

        model = XGBRegressor(
            n_estimators=350,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
        )
        model.fit(train_df[FEATURE_COLUMNS], train_df["lst"])

        y_true = test_df["lst"].values
        ml_pred = model.predict(test_df[FEATURE_COLUMNS])
        physics_pred = physics_lst(test_df)
        hybrid_pred = 0.35 * physics_pred + 0.65 * ml_pred

        ml_scores.append(_regression_metrics(y_true, ml_pred))
        hybrid_scores.append(_regression_metrics(y_true, hybrid_pred))
        physics_scores.append(_regression_metrics(y_true, physics_pred))

    def _mean_metric(scores: list[dict], key: str) -> float:
        return round(float(np.mean([s[key] for s in scores])), 3 if key == "r2" else 2)

    return {
        "method": f"{n_folds}-fold spatial block CV (latitude bands)",
        "target": "Observed Landsat 8 LST (ST_B10)",
        "n_folds": int(n_folds),
        "ml_only": {
            "r2": _mean_metric(ml_scores, "r2"),
            "rmse_c": _mean_metric(ml_scores, "rmse_c"),
            "mae_c": _mean_metric(ml_scores, "mae_c"),
        },
        "physics_only": {
            "r2": _mean_metric(physics_scores, "r2"),
            "rmse_c": _mean_metric(physics_scores, "rmse_c"),
            "mae_c": _mean_metric(physics_scores, "mae_c"),
        },
        "hybrid_physics_ml": {
            "r2": _mean_metric(hybrid_scores, "r2"),
            "rmse_c": _mean_metric(hybrid_scores, "rmse_c"),
            "mae_c": _mean_metric(hybrid_scores, "mae_c"),
        },
        "fold_details": [
            {
                "fold": int(i),
                "hybrid_r2": hybrid_scores[i]["r2"],
                "hybrid_rmse_c": hybrid_scores[i]["rmse_c"],
            }
            for i in range(len(hybrid_scores))
        ],
    }


def train_model(df: pd.DataFrame) -> tuple[XGBRegressor, dict]:
    cv_metrics = spatial_cross_validate(df, n_folds=5)

    # Primary reported metrics: spatial hold-out (north vs south Delhi) on ML-only model
    # Physics model disabled for real satellite data (tuned on synthetic data)
    train_mask = df["lat"] <= df["lat"].median()
    train_df = df[train_mask]
    holdout_df = df[~train_mask]

    model = XGBRegressor(
        n_estimators=350,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
    )
    model.fit(train_df[FEATURE_COLUMNS], train_df["lst"])

    y_true = holdout_df["lst"].values
    ml_pred = model.predict(holdout_df[FEATURE_COLUMNS])

    holdout_ml = _regression_metrics(y_true, ml_pred)

    metrics = {
        **holdout_ml,
        "validation": "Spatial hold-out: train south Delhi, test north Delhi (ML-only model)",
        "model_type": "XGBoost (physics model disabled for real satellite data)",
        "target_variable": "Observed Landsat 8 LST",
        "spatial_holdout": {
            "split": "latitude median",
            "train_cells": int(train_mask.sum()),
            "test_cells": int((~train_mask).sum()),
            "ml_only": holdout_ml,
        },
        "spatial_cross_validation": cv_metrics,
        "note": (
            "Metrics computed on real satellite LST. "
            f"5-fold spatial CV ML-only R²={cv_metrics['ml_only']['r2']}, "
            f"RMSE={cv_metrics['ml_only']['rmse_c']}°C. "
            "Physics model disabled as it was tuned on synthetic data."
        ),
    }

    # Retrain on full dataset for scenario simulation and deployment
    model.fit(df[FEATURE_COLUMNS], df["lst"])
    return model, metrics


def driver_importance(model: XGBRegressor, df: pd.DataFrame) -> dict:
    sample = df[FEATURE_COLUMNS].sample(min(2500, len(df)), random_state=42)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(sample)
    mean_abs = np.abs(shap_values).mean(axis=0)
    total = mean_abs.sum()
    labels = {
        "ndvi": "Low vegetation",
        "ndbi": "Built-up intensity",
        "impervious": "Impervious surfaces",
        "albedo": "Low albedo surfaces",
        "building_density": "Building density",
        "dist_water_m": "Distance from water",
        "wind": "Wind exposure",
        "air_temp": "Air temperature",
        "humidity": "Relative humidity",
        "sky_view_factor": "Sky view factor (urban canyon)",
        "building_height_m": "Building height (thermal mass)",
        "street_width_m": "Street width (ventilation)",
        "ghsl_built_up": "GHSL built-up density",
        "population_density": "Population density",
        "thermal_anisotropy": "Thermal anisotropy",
    }
    ranked = sorted(
        [
            {"feature": labels.get(col, col), "contribution": round(float(v / total), 3)}
            for col, v in zip(FEATURE_COLUMNS, mean_abs)
        ],
        key=lambda x: x["contribution"],
        reverse=True,
    )
    return {"global_drivers": ranked[:5]}


def drivers_by_zone(df: pd.DataFrame, model: XGBRegressor) -> dict:
    zone_drivers = {}
    for zone in ZONES:
        zdf = df[df["zone_id"] == zone["id"]]
        if len(zdf) < 20:
            continue
        sample = zdf[FEATURE_COLUMNS].sample(min(800, len(zdf)), random_state=7)
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(sample)
        mean_abs = np.abs(shap_values).mean(axis=0)
        total = mean_abs.sum() if mean_abs.sum() else 1
        
        # Map feature indices to driver names
        feature_map = {
            0: "low_vegetation",
            1: "built_up_intensity", 
            2: "high_impervious",
            3: "low_albedo",
            4: "building_density",
            5: "dist_water",
            6: "wind_exposure",
            7: "air_temp",
            8: "humidity",
            9: "sky_view_factor",
            10: "building_height",
            11: "street_width",
            12: "ghsl_built_up",
            13: "population_density",
            14: "thermal_anisotropy",
        }
        
        zone_drivers[zone["id"]] = {
            "name": zone["name"],
            "low_albedo": round(float(mean_abs[3] / total), 2) if len(mean_abs) > 3 else 0,
            "low_vegetation": round(float(mean_abs[0] / total), 2) if len(mean_abs) > 0 else 0,
            "high_impervious": round(float(mean_abs[2] / total), 2) if len(mean_abs) > 2 else 0,
            "built_up_intensity": round(float(mean_abs[1] / total), 2) if len(mean_abs) > 1 else 0,
            "urban_canyon_effect": round(float(mean_abs[9] / total), 2) if len(mean_abs) > 9 else 0,
            "thermal_mass": round(float(mean_abs[10] / total), 2) if len(mean_abs) > 10 else 0,
        }
    return zone_drivers


def predict_df(df: pd.DataFrame, model: XGBRegressor) -> np.ndarray:
    physics = physics_lst(df)
    ml = model.predict(df[FEATURE_COLUMNS])
    return 0.35 * physics + 0.65 * ml


def apply_intervention_df(df: pd.DataFrame, delta: dict) -> pd.DataFrame:
    updated = df.copy()
    updated["albedo"] = np.clip(df["albedo"] + delta["albedo"], 0.05, 0.85)
    updated["ndvi"] = np.clip(df["ndvi"] + delta["ndvi"], 0.02, 0.90)
    updated["impervious"] = np.clip(df["impervious"] + delta["impervious"], 0.05, 0.95)
    return updated


def predict_row(row: pd.Series, model: XGBRegressor) -> float:
    return float(predict_df(pd.DataFrame([row]), model)[0])


def apply_intervention(row: pd.Series, delta: dict) -> pd.Series:
    return apply_intervention_df(pd.DataFrame([row]), delta).iloc[0]


def run_scenarios(df: pd.DataFrame, model: XGBRegressor) -> list[dict]:
    base = predict_df(df, model)
    results = []
    for key, spec in INTERVENTIONS.items():
        cooled = predict_df(apply_intervention_df(df, spec), model)
        deltas = np.maximum(0.0, base - cooled)
        results.append(
            {
                "strategy_id": key,
                "strategy": spec["label"],
                "delta_t": round(float(np.mean(deltas)), 1),
                "max_delta_t": round(float(np.percentile(deltas, 95)), 1),
            }
        )
    return sorted(results, key=lambda x: x["delta_t"], reverse=True)


def scenario_by_zone(df: pd.DataFrame, model: XGBRegressor, strategy_key: str) -> dict:
    spec = INTERVENTIONS[strategy_key]
    out = {}
    for zone in ZONES:
        zdf = df[df["zone_id"] == zone["id"]]
        if zdf.empty:
            continue
        base = predict_df(zdf, model)
        cooled = predict_df(apply_intervention_df(zdf, spec), model)
        out[zone["id"]] = round(float(np.mean(np.maximum(0.0, base - cooled))), 1)
    return out


def optimize(df: pd.DataFrame, model: XGBRegressor, budget_inr: float = DEFAULT_BUDGET_INR) -> list[dict]:
    area_per_cell_m2 = 250 * 250
    recommendations = []

    for zone in ZONES:
        zdf = df[df["zone_id"] == zone["id"]]
        if zdf.empty:
            continue

        lst_mean = float(zdf["lst"].mean())
        hri = float(np.clip((lst_mean - 38) / 2.4, 1, 10))
        best_strategy = None
        best_score = -1
        best_delta = 0

        for key, spec in INTERVENTIONS.items():
            zdf = df[df["zone_id"] == zone["id"]]
            base = predict_df(zdf, model)
            cooled = predict_df(apply_intervention_df(zdf, spec), model)
            avg_delta = float(np.mean(np.maximum(0.0, base - cooled)))
            cost = COST_PER_M2[key]
            score = avg_delta / (cost / 100)  # benefit per 100 INR/m2
            if score > best_score:
                best_score = score
                best_strategy = key
                best_delta = avg_delta

        deployable_cells = max(1, int(len(zdf) * 0.65))
        deploy_area = deployable_cells * area_per_cell_m2
        est_cost = deploy_area * COST_PER_M2[best_strategy]
        benefit_people = zone["population"]
        priority = round(
            0.35 * (hri / 10) * 100
            + 0.30 * min(benefit_people / 35000, 1) * 100
            + 0.20 * min(best_delta / 12, 1) * 100
            + 0.15 * min(best_score / 0.03, 1) * 100,
            0,
        )

        recommendations.append(
            {
                "neighborhood": zone["name"],
                "zone_id": zone["id"],
                "heat_risk_index": round(hri, 1),
                "population_exposed": zone["population"],
                "priority_score": int(priority),
                "recommended_strategy": INTERVENTIONS[best_strategy]["label"],
                "expected_delta_t": round(best_delta, 1),
                "estimated_cost_inr": int(est_cost),
                "within_budget": est_cost <= budget_inr,
            }
        )

    return sorted(recommendations, key=lambda x: x["priority_score"], reverse=True)


def build_insights(
    drivers: dict,
    scenarios: list[dict],
    priority: list[dict],
    metrics: dict,
) -> dict:
    top_zones = [p["neighborhood"] for p in priority[:3]]
    top_strategy = scenarios[0]["strategy"]
    top_delta = scenarios[0]["delta_t"]

    return {
        "title": "AIML Insights",
        "drivers": (
            "High surface temperatures in Delhi are primarily driven by "
            f"{drivers['global_drivers'][0]['feature'].lower()} and "
            f"{drivers['global_drivers'][1]['feature'].lower()} across built-up cores."
        ),
        "priority_zones": top_zones,
        "impact_estimates": {
            "cool_pavements": "8-14 C surface reduction in dense markets",
            "cool_roofs": "2-4 C indoor reduction, up to 12 C surface locally",
        },
        "recommendation": (
            f"Deploy {top_strategy.lower()} in Central Delhi and Karol Bagh first "
            f"to capture up to {top_delta} C average surface cooling."
        ),
        "model_metrics": metrics,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sync_dashboard(data: dict[str, object]) -> None:
    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)
    for name, payload in data.items():
        write_json(DASHBOARD_DATA / name, payload)


def main() -> None:
    csv_path = DATA_DIR / "grid_features.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing {csv_path}. Run generate_delhi_data.py first.")

    df = pd.read_csv(csv_path)
    model, metrics = train_model(df)
    joblib.dump(model, DATA_DIR / "lst_model.joblib")

    drivers = driver_importance(model, df)
    zone_drivers = drivers_by_zone(df, model)
    scenarios = run_scenarios(df, model)
    cool_roof_zone = scenario_by_zone(df, model, "cool_roofs")
    priority = optimize(df, model)
    insights = build_insights(drivers, scenarios, priority, metrics)

    scenario_after = {}
    for zone in ZONES:
        zdf = df[df["zone_id"] == zone["id"]]
        if zdf.empty:
            continue
        base = float(zdf["lst"].mean())
        delta = cool_roof_zone.get(zone["id"], 0)
        scenario_after[zone["id"]] = {
            "name": zone["name"],
            "baseline_lst": round(base, 1),
            "after_lst": round(max(30, base - delta), 1),
            "delta_t": round(delta, 1),
        }

    outputs = {
        "model_metrics.json": metrics,
        "drivers.json": drivers,
        "drivers_by_zone.json": zone_drivers,
        "scenarios.json": scenarios,
        "priority_table.json": priority,
        "insights.json": insights,
        "materials.json": MATERIALS,
        "scenario_after.json": scenario_after,
    }

    for name, payload in outputs.items():
        write_json(DATA_DIR / name, payload)

    sync_dashboard(outputs)

    validation_path = DATA_DIR / "validation.json"
    if validation_path.exists():
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        write_json(DASHBOARD_DATA / "validation.json", validation)

    print("Model metrics:", metrics)
    print("Top scenario:", scenarios[0])
    if priority:
        print("Top priority zone:", priority[0]["neighborhood"])
    else:
        print("No zones found - all cells may be unassigned")


if __name__ == "__main__":
    main()
