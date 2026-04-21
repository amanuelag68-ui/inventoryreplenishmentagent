# Inventory Replenishment Agent

This project is a simple inventory replenishment simulation for 3 SKUs over 90 days. I used an EWMA forecast to estimate demand, then built an agent that decides each day if it should place an order or wait.

## Files in this project
- `inventory_agent.py` - main Python script
- `sales.csv` - daily sales data
- `inventory.csv` - starting inventory for each SKU
- `params.csv` - lead time, service level, min order quantity, and costs
- `design_doc.md` - short design summary
- `scaling_note.md` - short note on how this could scale in real life
- `run_output.txt` - successful code output
- `daily_agent_log.csv` - daily decisions made by the agent
- `agent_metrics.csv` - final results for the agent
- `baseline_metrics.csv` - final results for the baseline
- `comparison_vs_baseline.csv` - comparison between both approaches

## How to run
```bash
python inventory_agent.py
```

## What the code does
1. Loads the 3 CSV files
2. Groups daily demand by SKU
3. Uses EWMA to forecast demand
4. Calculates safety stock from forecast error and service level
5. Checks whether inventory is enough for the lead time + review period
6. Places an order if needed and follows the minimum order quantity rule
7. Simulates demand, arrivals, stockouts, and cost day by day
8. Compares the agent against a simple baseline rule

## Baseline
For the baseline, I used a simpler average-demand reorder rule.

## Results summary
The EWMA agent performed better than the baseline for all 3 SKUs.
- `PASTA`: fill rate improved from 0.9765 to 0.9962 and total cost dropped from 422.27 to 139.73
- `RICE`: fill rate improved from 0.9675 to 0.9943 and total cost dropped from 298.82 to 101.22
- `BEANS`: fill rate improved from 0.9828 to 0.9889 and total cost dropped from 127.56 to 97.08

## Trade-off
Keeping more inventory can improve service level, but it also increases holding cost. The goal is to keep enough stock to avoid too many stockouts without ordering way too much.
