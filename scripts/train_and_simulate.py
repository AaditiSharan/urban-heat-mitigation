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
from sklearn.metrics import mean_absolute_error, r2_score
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
    return (
        df["air_temp"].values
        + 35 * (1 - df["albedo"].values)
        - 18 * df["ndvi"].values
        + 8 * df["impervious"].values
        - 0.8 * df["wind"].values
    )


def train_model(df: pd.DataFrame) -> tuple[XGBRegressor, dict]:
    X = df[FEATURE_COLUMNS]
    y = df["lst"]

    # Spatial hold-out: north vs south Delhi
    train_mask = df["lat"] <= df["lat"].median()
    X_train, X_test = X[train_mask], X[~train_mask]
    y_train, y_test = y[train_mask], y[~train_mask]

    model = XGBRegressor(
        n_estimators=350,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
    )
    model.fit(X_train, y_train)

    pred = model.predict(X_test)
    metrics = {
        "r2": round(float(r2_score(y_test, pred)), 3),
        "rmse_c": round(float(np.sqrt(np.mean((y_test - pred) ** 2))), 2),
        "mae_c": round(float(mean_absolute_error(y_test, pred)), 2),
        "validation": "Spatial hold-out (north vs south Delhi)",
    }

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
        zone_drivers[zone["id"]] = {
            "name": zone["name"],
            "low_albedo": round(float(mean_abs[3] / total), 2),
            "low_vegetation": round(float(mean_abs[0] / total), 2),
            "high_impervious": round(float(mean_abs[2] / total), 2),
            "built_up_intensity": round(float(mean_abs[1] / total), 2),
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

    print("Model metrics:", metrics)
    print("Top scenario:", scenarios[0])
    print("Top priority zone:", priority[0]["neighborhood"])


if __name__ == "__main__":
    main()
