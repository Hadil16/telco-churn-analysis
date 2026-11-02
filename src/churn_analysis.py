"""
Telco customer churn analysis.

Questions:
  Q1. What is the churn rate, and in which customer groups is it highest?
  Q2. Which factors drive churn once the others are held constant? (logistic regression)
  Q3. Can churn be predicted, and how reliably? (AUC on customers the model has not seen)
  Q4. Which customers should be contacted first? (gains curve)
  Q5. How much monthly revenue is at stake, and what could a retention offer save?

Reads  : data/WA_Fn-UseC_-Telco-Customer-Churn.csv   (Kaggle: blastchar/telco-customer-churn)
Writes : data/processed/customers_clean.csv, reports/tables/*.csv, reports/figures/*.png,
         reports/analysis_results.json

Run from the project root:  python src/churn_analysis.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "WA_Fn-UseC_-Telco-Customer-Churn.csv"
PROC = ROOT / "data" / "processed"
TAB = ROOT / "reports" / "tables"
FIG = ROOT / "reports" / "figures"
for d in (PROC, TAB, FIG):
    d.mkdir(parents=True, exist_ok=True)

INK, BLUE, CHURN, GREY = "#26264F", "#5B6FD6", "#E4572E", "#9AA5B1"
plt.rcParams.update({
    "figure.figsize": (10, 5.2), "figure.dpi": 150, "savefig.bbox": "tight",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left", "font.size": 10.5,
})
res = {}

# ------------------------------------------------------------------ audit and cleaning
df = pd.read_csv(RAW)
res["customers"] = int(len(df))
res["duplicate_ids"] = int(df.customerID.duplicated().sum())

# Trap 1: TotalCharges is text because 11 new customers (tenure 0) have a blank value.
blank = df.TotalCharges.str.strip() == ""
res["blank_total_charges"] = int(blank.sum())
res["blank_total_charges_tenures"] = sorted(int(t) for t in df.loc[blank, "tenure"].unique())
res["blank_total_charges_churned"] = int((df.loc[blank, "Churn"] == "Yes").sum())
df["TotalCharges"] = pd.to_numeric(df.TotalCharges.str.strip().replace("", "0"))

# Trap 2: "No internet service" / "No phone service" repeat what InternetService / PhoneService already say.
service_cols = ["MultipleLines", "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport",
                "StreamingTV", "StreamingMovies"]
for c in service_cols:
    df[c] = df[c].replace({"No internet service": "No", "No phone service": "No"})

df["churned"] = (df.Churn == "Yes").astype(int)
df["SeniorCitizen"] = df.SeniorCitizen.map({0: "No", 1: "Yes"})
df["tenure_group"] = pd.cut(df.tenure, [-1, 12, 24, 48, 72], labels=["0-12 months", "13-24", "25-48", "49-72"])
df.to_csv(PROC / "customers_clean.csv", index=False)

# ------------------------------------------------------------------ Q1 who churns
overall = df.churned.mean()
res["churn_rate"] = float(overall)
res["churners"] = int(df.churned.sum())
rows = []
for col in ["Contract", "tenure_group", "InternetService", "PaymentMethod",
            "PaperlessBilling", "SeniorCitizen", "Partner", "Dependents", "gender"]:
    g = df.groupby(col, observed=True).churned.agg(["mean", "size"]).reset_index()
    g.columns = ["value", "churn_rate", "customers"]
    g.insert(0, "factor", col)
    rows.append(g)
# Tech support and online security only make sense for customers who have internet.
# Comparing "No" over everyone would mix in the 1,526 customers without internet (very low churn).
inet = df[df.InternetService != "No"]
for col in ["TechSupport", "OnlineSecurity"]:
    g = inet.groupby(col).churned.agg(["mean", "size"]).reset_index()
    g.columns = ["value", "churn_rate", "customers"]
    g.insert(0, "factor", f"{col} (internet customers)")
    rows.append(g)
seg = pd.concat(rows)
seg.to_csv(TAB / "churn_by_segment.csv", index=False)
res["by_contract"] = {r.value: float(r.churn_rate) for r in seg[seg.factor == "Contract"].itertuples()}
res["by_tenure"] = {r.value: float(r.churn_rate) for r in seg[seg.factor == "tenure_group"].itertuples()}
res["by_internet"] = {r.value: float(r.churn_rate) for r in seg[seg.factor == "InternetService"].itertuples()}
res["by_payment"] = {r.value: float(r.churn_rate) for r in seg[seg.factor == "PaymentMethod"].itertuples()}
res["by_techsupport"] = {r.value: float(r.churn_rate) for r in seg[seg.factor == "TechSupport (internet customers)"].itertuples()}
res["by_onlinesecurity"] = {r.value: float(r.churn_rate) for r in seg[seg.factor == "OnlineSecurity (internet customers)"].itertuples()}
res["by_gender"] = {r.value: float(r.churn_rate) for r in seg[seg.factor == "gender"].itertuples()}


def bars(ax, sub, title, order=None):
    sub = sub.set_index("value")
    if order:
        sub = sub.loc[order]
    ax.bar(sub.index.astype(str), sub.churn_rate, color=[CHURN if v > overall else BLUE for v in sub.churn_rate], width=.6)
    ax.axhline(overall, color="#333", ls="--", lw=1)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
    ax.set_title(title)
    for i, (v, n) in enumerate(zip(sub.churn_rate, sub.customers)):
        ax.text(i, v + .01, f"{v:.0%}", ha="center", fontweight="bold", fontsize=10)
        ax.text(i, 0.01, f"n={n:,}", ha="center", color="white", fontsize=8)
    ax.set_ylim(0, max(sub.churn_rate) * 1.2)


fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
bars(axes[0], seg[seg.factor == "Contract"], "Churn by contract", ["Month-to-month", "One year", "Two year"])
bars(axes[1], seg[seg.factor == "tenure_group"], "Churn by time as a customer")
axes[0].text(2.45, overall + .005, f"average {overall:.1%}", ha="right", fontsize=8.5)
fig.savefig(FIG / "01_churn_by_contract_tenure.png"); plt.close(fig)

fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
bars(axes[0], seg[seg.factor == "InternetService"], "Churn by internet service")
bars(axes[1], seg[seg.factor == "PaymentMethod"], "Churn by payment method")
axes[1].tick_params(axis="x", labelsize=8)
axes[1].set_xticks(range(4))
axes[1].set_xticklabels([t.replace(" (automatic)", "\n(automatic)") for t in
                         seg[seg.factor == "PaymentMethod"].value], fontsize=8)
bars(axes[2], seg[seg.factor == "TechSupport (internet customers)"], "Churn by tech support (internet customers)")
fig.savefig(FIG / "02_churn_by_service_payment.png"); plt.close(fig)

# ------------------------------------------------------------------ Q2 drivers (logistic regression)
# MonthlyCharges is left out of this inference model: the bill is almost fully determined by the
# services a customer subscribes to (VIF = 863 when included, see below), which makes the
# odds ratios of the services unreliable. It stays in the prediction models, where it does no harm.
formula = ("churned ~ C(Contract, Treatment('Month-to-month')) + tenure"
           " + C(InternetService, Treatment('DSL')) + C(PaymentMethod, Treatment('Credit card (automatic)'))"
           " + C(TechSupport) + C(OnlineSecurity) + C(OnlineBackup) + C(DeviceProtection)"
           " + C(StreamingTV) + C(StreamingMovies) + C(MultipleLines) + C(PaperlessBilling)"
           " + C(SeniorCitizen) + C(Partner) + C(Dependents) + C(gender) + C(PhoneService)")
import patsy
from statsmodels.stats.outliers_influence import variance_inflation_factor


def max_vif(f):
    _, Xd = patsy.dmatrices(f, df, return_type="dataframe")
    v = pd.Series([variance_inflation_factor(Xd.values, i) for i in range(Xd.shape[1])],
                  index=Xd.columns).drop("Intercept")
    return float(v.max()), v.idxmax()


vif_with, vif_with_name = max_vif(formula + " + MonthlyCharges")
vif_without, _ = max_vif(formula)
res["vif_with_monthly_charges"] = vif_with
res["vif_without_monthly_charges"] = vif_without
logit = smf.logit(formula, data=df).fit(disp=False)
ci = logit.conf_int()
odds = pd.DataFrame({"odds_ratio": np.exp(logit.params), "ci_low": np.exp(ci[0]), "ci_high": np.exp(ci[1]),
                     "p_value": logit.pvalues}).drop(index="Intercept")


def pretty(name):
    name = name.replace("C(Contract, Treatment('Month-to-month'))[T.", "Contract: ")
    name = name.replace("C(InternetService, Treatment('DSL'))[T.", "Internet: ")
    name = name.replace("C(PaymentMethod, Treatment('Credit card (automatic)'))[T.", "Payment: ")
    for var, lab in [("TechSupport", "Tech support"), ("OnlineSecurity", "Online security"),
                     ("OnlineBackup", "Online backup"), ("DeviceProtection", "Device protection"),
                     ("StreamingTV", "Streaming TV"), ("StreamingMovies", "Streaming movies"),
                     ("MultipleLines", "Multiple lines"), ("PaperlessBilling", "Paperless billing"),
                     ("SeniorCitizen", "Senior citizen"), ("Partner", "Has partner"), ("Dependents", "Has dependents"),
                     ("gender", "Gender"), ("PhoneService", "Phone service")]:
        name = name.replace(f"C({var})[T.", f"{lab}: ")
    return name.rstrip("]")


odds.index = [pretty(i) for i in odds.index]
odds = odds.sort_values("odds_ratio")
odds.to_csv(TAB / "odds_ratios.csv", index_label="factor")
sig = odds[odds.p_value < 0.05]
# drivers used by the Power BI dashboard: significant factors, expressed as % change in the odds of churn
drivers = sig.drop(index="tenure", errors="ignore").copy()
drivers["pct_change_in_odds"] = drivers.odds_ratio - 1
drivers = drivers.sort_values("pct_change_in_odds", ascending=False)
drivers["sort_order"] = np.arange(1, len(drivers) + 1)  # lets Power BI keep this order in the chart
drivers.to_csv(TAB / "drivers.csv", index_label="factor")
res["pseudo_r2"] = float(logit.prsquared)
res["n_significant_drivers"] = int(len(sig))
for key in ["Contract: Two year", "Contract: One year", "Internet: Fiber optic", "Payment: Electronic check",
            "Tech support: Yes", "Online security: Yes", "Paperless billing: Yes", "Streaming TV: Yes",
            "Gender: Male", "Senior citizen: Yes"]:
    if key in odds.index:
        r = odds.loc[key]
        res[f"or::{key}"] = {"odds_ratio": float(r.odds_ratio), "ci": [float(r.ci_low), float(r.ci_high)],
                             "p": float(r.p_value)}
res["tenure_or_per_12_months"] = float(np.exp(logit.params["tenure"] * 12))

show = sig.copy()
show = show.loc[[i for i in show.index if i not in ("tenure", "MonthlyCharges")]]
fig, ax = plt.subplots(figsize=(9, 6.5))
y = np.arange(len(show))
ax.hlines(y, show.ci_low, show.ci_high, color=GREY, lw=2)
ax.scatter(show.odds_ratio, y, color=[CHURN if v > 1 else BLUE for v in show.odds_ratio], zorder=3, s=45)
ax.axvline(1, color="#333", lw=1)
ax.set_xscale("log")
ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 4])
ax.get_xaxis().set_major_formatter(mtick.ScalarFormatter())
ax.get_xaxis().set_minor_formatter(mtick.NullFormatter())
ax.set_yticks(y)
ax.set_yticklabels(show.index, fontsize=9)
ax.set_xlabel("Odds ratio (above 1: more likely to churn, below 1: less likely), with 95% interval")
ax.set_title("What changes the risk of churn, all else equal")
fig.savefig(FIG / "03_odds_ratios.png"); plt.close(fig)

# ------------------------------------------------------------------ Q3 prediction
features = ["Contract", "tenure", "MonthlyCharges", "InternetService", "PaymentMethod", "TechSupport",
            "OnlineSecurity", "OnlineBackup", "DeviceProtection", "StreamingTV", "StreamingMovies", "MultipleLines",
            "PaperlessBilling", "SeniorCitizen", "Partner", "Dependents", "gender", "PhoneService"]
X, y_all = df[features], df.churned
cat = [c for c in features if df[c].dtype == object or str(df[c].dtype) == "str"]
num = [c for c in features if c not in cat]
pre = ColumnTransformer([("cat", OneHotEncoder(drop="first"), cat), ("num", StandardScaler(), num)])
Xtr, Xte, ytr, yte = train_test_split(X, y_all, test_size=0.25, stratify=y_all, random_state=42)
models = {
    "Logistic regression": make_pipeline(pre, LogisticRegression(max_iter=2000)),
    "Gradient boosting": make_pipeline(pre, GradientBoostingClassifier(random_state=42)),
}
auc = {}
for name, m in models.items():
    m.fit(Xtr, ytr)
    auc[name] = float(roc_auc_score(yte, m.predict_proba(Xte)[:, 1]))
res["auc_test"] = auc
res["test_customers"] = int(len(yte))
pd.DataFrame({"model": list(auc), "auc_on_unseen_customers": list(auc.values())}).to_csv(TAB / "model_auc.csv", index=False)

# ------------------------------------------------------------------ Q4 targeting (cross-validated risk for every customer)
cv = StratifiedKFold(5, shuffle=True, random_state=42)
risk = cross_val_predict(models["Logistic regression"], X, y_all, cv=cv, method="predict_proba")[:, 1]
df["churn_risk"] = risk
order = df.sort_values("churn_risk", ascending=False).reset_index(drop=True)
order["cum_churners"] = order.churned.cumsum() / order.churned.sum()
order["share_of_customers"] = (np.arange(len(order)) + 1) / len(order)
gains = order[["share_of_customers", "cum_churners"]]
gains.iloc[::20].to_csv(TAB / "gains_curve.csv", index=False)
for pct in (0.10, 0.20, 0.30):
    top = order.head(int(len(order) * pct))
    res[f"top_{int(pct*100)}pct"] = {"churn_rate": float(top.churned.mean()), "share_of_churners": float(top.churned.sum() / order.churned.sum()),
                                     "lift": float(top.churned.mean() / overall)}
res["cv_auc"] = float(roc_auc_score(y_all, risk))
df[["customerID", "churn_risk"]].to_csv(PROC / "churn_risk_scores.csv", index=False)

# Priority groups by predicted risk (riskiest first). "A" + "B" = the 20% to contact first.
n_cust = len(order)
cuts = [("A. Top 10%", int(n_cust * 0.10)), ("B. 10-20%", int(n_cust * 0.20)),
        ("C. 20-50%", int(n_cust * 0.50)), ("D. Bottom 50%", n_cust)]
labels, start = np.empty(n_cust, dtype=object), 0
for name, end in cuts:
    labels[start:end] = name
    start = end
order["risk_group"] = labels
scored = df.merge(order[["customerID", "risk_group"]], on="customerID")
scored.to_csv(PROC / "customers_scored.csv", index=False)
res["risk_group_sizes"] = {k: int(v) for k, v in scored.risk_group.value_counts().sort_index().items()}
fig, ax = plt.subplots(figsize=(7.5, 6))
ax.plot(gains.share_of_customers, gains.cum_churners, color=CHURN, lw=2.5, label="Model ranking")
ax.plot([0, 1], [0, 1], color=GREY, ls="--", label="Random contact")
for pct in (0.2,):
    v = res[f"top_{int(pct*100)}pct"]["share_of_churners"]
    ax.scatter([pct], [v], color=INK, zorder=3)
    ax.annotate(f"Contacting the riskiest {pct:.0%}\nreaches {v:.0%} of churners", (pct, v), xytext=(0.28, v - 0.18),
                arrowprops=dict(arrowstyle="->", color="#555"), fontsize=10)
ax.xaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
ax.yaxis.set_major_formatter(mtick.PercentFormatter(1, decimals=0))
ax.set_xlabel("Share of customers contacted (riskiest first)")
ax.set_ylabel("Share of all churners reached")
ax.set_title("Who to call first")
ax.legend(frameon=False, loc="lower right")
fig.savefig(FIG / "04_gains_curve.png"); plt.close(fig)

# ------------------------------------------------------------------ Q5 money at stake
total_monthly = df.MonthlyCharges.sum()
churn_monthly = df.loc[df.churned == 1, "MonthlyCharges"].sum()
res["monthly_revenue_total"] = float(total_monthly)
res["monthly_revenue_of_churners"] = float(churn_monthly)
res["share_of_revenue_churners"] = float(churn_monthly / total_monthly)
res["avg_monthly_charge_churners"] = float(df.loc[df.churned == 1, "MonthlyCharges"].mean())
res["avg_monthly_charge_stayers"] = float(df.loc[df.churned == 0, "MonthlyCharges"].mean())
res["avg_tenure_churners"] = float(df.loc[df.churned == 1, "tenure"].mean())
res["avg_tenure_stayers"] = float(df.loc[df.churned == 0, "tenure"].mean())
top20 = order.head(int(len(order) * 0.20))
top20_churn_rev = top20.loc[top20.churned == 1, "MonthlyCharges"].sum()
SAVE_RATE = 0.25  # scenario assumption, not a prediction
res["scenario_save_rate"] = SAVE_RATE
res["top20_churners_monthly_revenue"] = float(top20_churn_rev)
res["scenario_monthly_revenue_saved"] = float(top20_churn_rev * SAVE_RATE)
res["scenario_annual_revenue_saved"] = float(top20_churn_rev * SAVE_RATE * 12)
res["top20_customers_contacted"] = int(len(top20))

(ROOT / "reports" / "analysis_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps(res, indent=2))
print(odds.round(3).to_string())
