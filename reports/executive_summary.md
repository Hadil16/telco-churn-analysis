# Executive summary: customer churn at a telecom operator

**Prepared for:** Retention and marketing management  **Scope:** 7,043 customers, $456K of monthly revenue

## Bottom line

**26.5% of customers have left, taking $139K of monthly revenue (30.5% of the total).** The risk is concentrated: month-to-month customers in their first year, on fiber optic, paying by electronic check. A model can find them: **calling the riskiest 20% of customers reaches half of all churners.**

## What we found

1. **Contract type is the strongest signal.** Churn is 43% on month-to-month contracts, 11% on one-year and 3% on two-year contracts.
2. **The first year is the danger zone.** Churn is 47% in the first 12 months and 10% after four years.
3. **Fiber optic customers churn the most** (42%, against 19% for DSL), even after accounting for contract and services: their odds of leaving are 2.5 times higher.
4. **Tech support and online security protect.** Among internet customers, churn is 15% with tech support and 42% without.
5. **Electronic check payers churn at 45%**, against 15% to 19% for other payment methods.
6. **Gender has no effect.**
7. **Churn is predictable** (AUC 0.845 on customers the model had not seen). The 1,408 riskiest customers (top 20%) contain 51% of all churners, with a 67.5% churn rate.

## What we recommend

| Priority | Action | How we will know it works |
|---|---|---|
| 1 | Move month-to-month customers, especially new ones, to one- or two-year contracts with an incentive | Share of month-to-month customers, churn in the first year |
| 2 | Offer tech support and online security to fiber customers who lack them | Churn rate of fiber customers |
| 3 | Encourage automatic payment for electronic check customers | Churn of electronic check customers |
| 4 | Contact the riskiest 20% first, as an A/B test | Customers saved in the test group against a control group |

## The money at stake (scenario)

The churners among the top 20% pay $78K a month. **If an offer saved 25% of them, the company would keep about $19.5K a month, around $234K a year.** The 25% is an assumption to verify with the A/B test, not a forecast.

## Caveats

These are associations, not proven causes. The data is a one-month snapshot of a fictional operator (IBM sample data), so the figures illustrate a method.

*Method, code and dashboard: see the project README.*
