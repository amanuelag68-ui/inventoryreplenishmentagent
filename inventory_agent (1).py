from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Dict, List, Tuple

import pandas as pd


DATA_DIR = Path(__file__).resolve().parent
SALES_CSV = DATA_DIR / "sales.csv"
INVENTORY_CSV = DATA_DIR / "inventory.csv"
PARAMS_CSV = DATA_DIR / "params.csv"
ALPHA = 0.35
REVIEW_PERIOD_DAYS = 1
ORDER_COST = 0.0
MAX_COVER_DAYS = 21  # keeps the agent from ordering way too much


@dataclass
class PendingOrder:
    sku: str
    qty: int
    arrival_date: pd.Timestamp


@dataclass
class SkuState:
    on_hand: int
    filled_units: int = 0
    demand_units: int = 0
    stockout_units: int = 0
    holding_cost_total: float = 0.0
    stockout_cost_total: float = 0.0
    order_cost_total: float = 0.0
    units_ordered: int = 0
    orders_placed: int = 0


def load_inputs() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Load the input files and make sure the needed columns exist.
    sales = pd.read_csv(SALES_CSV, parse_dates=["date"])
    inventory = pd.read_csv(INVENTORY_CSV)
    params = pd.read_csv(PARAMS_CSV)

    required_sales = {"date", "sku", "qty_sold"}
    required_inventory = {"sku", "opening_stock"}
    required_params = {
        "sku",
        "unit_cost",
        "holding_cost_per_day",
        "stockout_cost",
        "lead_time_days",
        "min_order_qty",
        "service_level",
    }

    for name, df, cols in [
        ("sales.csv", sales, required_sales),
        ("inventory.csv", inventory, required_inventory),
        ("params.csv", params, required_params),
    ]:
        missing = cols.difference(df.columns)
        if missing:
            raise ValueError(f"{name} is missing columns: {sorted(missing)}")

    sales = sales.groupby(["date", "sku"], as_index=False)["qty_sold"].sum().sort_values(["sku", "date"])
    return sales, inventory, params


def ewma_forecast(history: List[int], alpha: float = ALPHA) -> float:
    # Simple EWMA forecast based on past demand.
    if not history:
        return 0.0
    forecast = float(history[0])
    for actual in history[1:]:
        forecast = alpha * actual + (1 - alpha) * forecast
    return max(forecast, 0.0)


def mae(history: List[int], alpha: float = ALPHA) -> float:
    # Mean absolute error is used as a simple forecast error measure.
    if len(history) < 2:
        return 1.0
    forecast = float(history[0])
    errors = []
    for actual in history[1:]:
        errors.append(abs(actual - forecast))
        forecast = alpha * actual + (1 - alpha) * forecast
    return max(sum(errors) / len(errors), 1.0)


def safety_stock(history: List[int], service_level: float, lead_time_days: int) -> int:
    # Safety stock grows when uncertainty or service target is higher.
    z = NormalDist().inv_cdf(service_level)
    err = mae(history)
    value = z * err * math.sqrt(max(lead_time_days + REVIEW_PERIOD_DAYS, 1))
    return max(math.ceil(value), 0)


def baseline_reorder_qty(avg_daily_demand: float, lead_time_days: int, min_order_qty: int, on_hand: int) -> int:
    # This is a simpler reorder rule used only for comparison.
    target = math.ceil(avg_daily_demand * (lead_time_days + REVIEW_PERIOD_DAYS + 2))
    needed = max(target - on_hand, 0)
    if needed == 0:
        return 0
    return max(min_order_qty, math.ceil(needed / min_order_qty) * min_order_qty)


def run_policy(use_forecast: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # Runs the full day-by-day simulation.
    sales, inventory, params = load_inputs()
    merged = sales.merge(params, on="sku", how="left").merge(inventory, on="sku", how="left")
    if merged[["opening_stock"]].isna().any().any():
        raise ValueError("Every SKU in sales.csv must exist in inventory.csv")

    dates = sorted(merged["date"].unique())
    skus = sorted(merged["sku"].unique())
    opening_stock = inventory.set_index("sku")["opening_stock"].to_dict()
    params_by_sku = params.set_index("sku").to_dict(orient="index")
    sales_pivot = sales.pivot(index="date", columns="sku", values="qty_sold").fillna(0).reindex(dates, fill_value=0)

    states: Dict[str, SkuState] = {sku: SkuState(on_hand=int(opening_stock[sku])) for sku in skus}
    history: Dict[str, List[int]] = {sku: [] for sku in skus}
    pending_orders: List[PendingOrder] = []
    logs: List[dict] = []

    for date in dates:
        date = pd.Timestamp(date)
        arrivals_today = [po for po in pending_orders if po.arrival_date == date]
        pending_orders = [po for po in pending_orders if po.arrival_date != date]
        arrivals_by_sku: Dict[str, int] = {}
        for po in arrivals_today:
            states[po.sku].on_hand += po.qty
            arrivals_by_sku[po.sku] = arrivals_by_sku.get(po.sku, 0) + po.qty

        for sku in skus:
            p = params_by_sku[sku]
            state = states[sku]
            demand = int(sales_pivot.loc[date, sku])
            history_before = history[sku][:]

            if use_forecast:
                forecast = ewma_forecast(history_before)
                avg_daily = forecast if history_before else demand
                ss = safety_stock(history_before, p["service_level"], int(p["lead_time_days"]))
                policy_name = "agent_ewma"
            else:
                avg_daily = sum(history_before) / len(history_before) if history_before else demand
                forecast = avg_daily
                ss = 0
                policy_name = "baseline_avg"

            lead = int(p["lead_time_days"])
            pipeline_qty = sum(po.qty for po in pending_orders if po.sku == sku)
            horizon = lead + REVIEW_PERIOD_DAYS
            reorder_point = math.ceil(avg_daily * horizon + ss)
            target_stock = math.ceil(avg_daily * horizon + ss)
            cap_stock = math.ceil(avg_daily * MAX_COVER_DAYS + ss)
            inventory_position = state.on_hand + pipeline_qty
            projected_inventory = inventory_position - math.ceil(avg_daily * horizon)

            action = "WAIT"
            order_qty = 0
            reason = "Projected inventory is sufficient through review horizon."

            if inventory_position <= reorder_point:
                raw_needed = max(target_stock - inventory_position, 0)
                if raw_needed > 0:
                    order_qty = max(int(p["min_order_qty"]), math.ceil(raw_needed / int(p["min_order_qty"])) * int(p["min_order_qty"]))
                    max_additional = max(cap_stock - inventory_position, 0)
                    if max_additional > 0:
                        order_qty = min(order_qty, math.ceil(max_additional / int(p["min_order_qty"])) * int(p["min_order_qty"]))
                    if order_qty > 0:
                        arrival_date = date + pd.Timedelta(days=lead)
                        pending_orders.append(PendingOrder(sku=sku, qty=int(order_qty), arrival_date=arrival_date))
                        state.units_ordered += int(order_qty)
                        state.orders_placed += 1
                        state.order_cost_total += ORDER_COST
                        action = "ORDER"
                        reason = (
                            f"Inventory position {inventory_position} is at/below reorder point {reorder_point}; "
                            f"ordered {order_qty} units to cover {horizon} days plus safety stock {ss}."
                        )
                else:
                    reason = "At reorder threshold, but no net replenishment needed after cap guardrail."

            filled = min(state.on_hand, demand)
            lost = demand - filled
            state.on_hand -= filled
            state.filled_units += filled
            state.demand_units += demand
            state.stockout_units += lost
            state.stockout_cost_total += lost * float(p["stockout_cost"])
            state.holding_cost_total += state.on_hand * float(p["holding_cost_per_day"])
            history[sku].append(demand)

            logs.append(
                {
                    "date": date.date().isoformat(),
                    "policy": policy_name,
                    "sku": sku,
                    "arrivals_today": arrivals_by_sku.get(sku, 0),
                    "demand": demand,
                    "forecast": round(forecast, 2),
                    "safety_stock": ss,
                    "on_hand_end": state.on_hand,
                    "pipeline_qty": pipeline_qty,
                    "inventory_position": inventory_position,
                    "projected_inventory_after_horizon": projected_inventory,
                    "action": action,
                    "order_qty": order_qty,
                    "reason": reason,
                }
            )

    metrics = []
    for sku, state in states.items():
        p = params_by_sku[sku]
        total_cost = state.holding_cost_total + state.stockout_cost_total + state.order_cost_total
        fill_rate = state.filled_units / state.demand_units if state.demand_units else 1.0
        metrics.append(
            {
                "policy": "agent_ewma" if use_forecast else "baseline_avg",
                "sku": sku,
                "demand_units": state.demand_units,
                "filled_units": state.filled_units,
                "stockout_units": state.stockout_units,
                "fill_rate": round(fill_rate, 4),
                "orders_placed": state.orders_placed,
                "units_ordered": state.units_ordered,
                "holding_cost": round(state.holding_cost_total, 2),
                "stockout_cost": round(state.stockout_cost_total, 2),
                "order_cost": round(state.order_cost_total, 2),
                "total_cost": round(total_cost, 2),
                "service_level_target": p["service_level"],
            }
        )

    return pd.DataFrame(logs), pd.DataFrame(metrics)


def main() -> None:
    # Run both the agent and the baseline, then save the results.
    agent_log, agent_metrics = run_policy(use_forecast=True)
    baseline_log, baseline_metrics = run_policy(use_forecast=False)

    comparison = agent_metrics.merge(
        baseline_metrics,
        on="sku",
        suffixes=("_agent", "_baseline"),
    )
    comparison["fill_rate_change"] = comparison["fill_rate_agent"] - comparison["fill_rate_baseline"]
    comparison["total_cost_change"] = comparison["total_cost_agent"] - comparison["total_cost_baseline"]

    print("=== DAILY AGENT LOG (first 20 rows) ===")
    print(agent_log.head(20).to_string(index=False))
    print("\n=== AGENT METRICS ===")
    print(agent_metrics.to_string(index=False))
    print("\n=== BASELINE METRICS ===")
    print(baseline_metrics.to_string(index=False))
    print("\n=== COMPARISON VS BASELINE ===")
    print(comparison[["sku", "fill_rate_agent", "fill_rate_baseline", "fill_rate_change", "total_cost_agent", "total_cost_baseline", "total_cost_change"]].to_string(index=False))

    agent_log.to_csv(DATA_DIR / "daily_agent_log.csv", index=False)
    agent_metrics.to_csv(DATA_DIR / "agent_metrics.csv", index=False)
    baseline_metrics.to_csv(DATA_DIR / "baseline_metrics.csv", index=False)
    comparison.to_csv(DATA_DIR / "comparison_vs_baseline.csv", index=False)


if __name__ == "__main__":
    main()
