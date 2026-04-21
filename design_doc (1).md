# Inventory Replenishment Agent - Design Doc

## Agent goal
The goal of this agent is to help decide when to reorder products so the store can reduce stockouts and also keep total inventory cost lower. The agent looks at demand history, current stock, lead time, service level, and cost settings. Based on that, it chooses either to place an order or wait.

## Inputs
- `sales.csv`: daily demand by SKU
- `inventory.csv`: opening stock for each SKU
- `params.csv`: unit cost, holding cost per day, stockout cost, lead time, minimum order quantity, and service level

## Outputs
- A daily log that shows the forecast, safety stock, inventory position, action, order quantity, and reason
- Final metrics such as stockouts, fill rate, holding cost, stockout cost, and total cost
- A comparison between the agent and a simple baseline strategy

## Forecasting and reorder logic
I used an EWMA forecast that updates every day. Then I estimate safety stock using forecast error and the service level. The agent checks if inventory position is enough to cover the lead time plus one review day. If not, it places an order while following the minimum order quantity rule.

## Guardrails and business rules
- The order must respect `min_order_qty`
- The agent accounts for lead time before inventory arrives
- The service level is used to calculate safety stock
- The model avoids over-ordering by using a max coverage cap
- The agent tries to balance holding cost and stockout cost

## Metrics, ethics, and trust
The main metrics are stockouts, fill rate, and total cost. This matters because too many stockouts can hurt customer trust, while ordering too much can waste money and tie up working capital. The daily log also makes the decisions easy to review.
