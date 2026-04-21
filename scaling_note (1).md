# Scaling Note

If I had to scale this project in real life, I would run it as a scheduled cloud job once per day after new sales and inventory data are available. This could be done with something simple like a container and a scheduler such as GitHub Actions, cron, or a cloud job runner.

For monitoring, I would track fill rate, stockouts, forecast error, and unusual order sizes. If one of those metrics gets worse, the team should get an alert. I would also save the daily agent log so someone can review what the system decided and why.

For reliability, I would add checks for missing columns, empty files, bad dates, duplicate rows, and missing inventory values before the script runs. I would also add retry logic in case the data source fails for a short time. If fresh data is missing, the system could use the most recent valid snapshot and flag the issue.

For cost control, I would add order caps, approval thresholds for very large orders, and working-capital limits. That would help prevent the agent from ordering too much during demand spikes. Over time, I would also tune values like alpha, service level, and max cover days based on actual results.
