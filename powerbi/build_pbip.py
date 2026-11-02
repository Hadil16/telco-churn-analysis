"""
Generate the Power BI project (PBIP format) for the Telco churn dashboard.

Writes powerbi/telco_dashboard.pbip + .SemanticModel/ + .Report/
Open telco_dashboard.pbip in Power BI Desktop, click Refresh now (once per banner, and wait),
then File > Save as .pbix.

Data sources (parameters DataFolder and TablesFolder, edit them if you move the project):
  data/processed/customers_scored.csv   customers with churn risk and priority group (src/churn_analysis.py)
  reports/tables/drivers.csv            factors that change the odds of churn (src/churn_analysis.py)

Run from the project root:  python powerbi/build_pbip.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"
NAME = "telco_dashboard"
SM = PBI / f"{NAME}.SemanticModel"
RP = PBI / f"{NAME}.Report"
DATA_DIR = str(ROOT / "data" / "processed")
TABLES_DIR = str(ROOT / "reports" / "tables")

T = "\t"
# The telecom company is fictional (IBM sample data), so it has no brand colors.
# Identity: deep indigo header, blue for data, vermilion for churn, teal accent.
INK, BLUE, CHURN, TEAL, AMBER, GREY = "#26264F", "#5B6FD6", "#E4572E", "#2EC4B6", "#FFB703", "#9AA5B1"


def w(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def wj(path, obj):
    w(path, json.dumps(obj, indent=2))


# =====================================================================
# SEMANTIC MODEL (TMDL)
# =====================================================================
def col(name, dtype, fmt=None, sort_by=None):
    s = [f"{T}column {name}", f"{T}{T}dataType: {dtype}"]
    if fmt:
        s.append(f"{T}{T}formatString: {fmt}")
    s.append(f"{T}{T}summarizeBy: none")
    if sort_by:
        s.append(f"{T}{T}sortByColumn: {sort_by}")
    s.append(f"{T}{T}sourceColumn: {name}")
    return "\n".join(s) + "\n"


def measure(name, dax, fmt=None, folder=None):
    n = f"'{name}'" if " " in name or "(" in name or "%" in name else name
    lines = dax.strip().splitlines()
    if len(lines) == 1:
        s = f"{T}measure {n} = {lines[0]}\n"
    else:
        s = f"{T}measure {n} = ```\n" + "\n".join(f"{T}{T}{T}{l}" for l in lines) + f"\n{T}{T}{T}```\n"
    if fmt:
        s += f"{T}{T}formatString: {fmt}\n"
    if folder:
        s += f"{T}{T}displayFolder: {folder}\n"
    return s


def m_partition(table, m_code):
    lines = m_code.strip().splitlines()
    return (f"{T}partition {table} = m\n{T}{T}mode: import\n{T}{T}source = ```\n"
            + "\n".join(f"{T}{T}{T}{l}" for l in lines) + f"\n{T}{T}{T}```\n")


def csv_query(folder_param, file, cols):
    names = ", ".join(f'"{c[0]}"' for c in cols)
    types = ", ".join(f'{{"{c[0]}", {c[1]}}}' for c in cols)
    return f"""let
    Source = Csv.Document(File.Contents({folder_param} & "\\{file}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Kept = Table.SelectColumns(Promoted, {{{names}}}),
    Typed = Table.TransformColumnTypes(Kept, {{{types}}}, "en-US")
in
    Typed"""


CUST_COLS = [  # name, M type, TMDL type, format
    ("customerID", "type text", "string", None), ("SeniorCitizen", "type text", "string", None),
    ("Partner", "type text", "string", None), ("Dependents", "type text", "string", None),
    ("tenure", "Int64.Type", "int64", "0"), ("InternetService", "type text", "string", None),
    ("TechSupport", "type text", "string", None), ("OnlineSecurity", "type text", "string", None),
    ("StreamingTV", "type text", "string", None), ("Contract", "type text", "string", None),
    ("PaperlessBilling", "type text", "string", None), ("PaymentMethod", "type text", "string", None),
    ("MonthlyCharges", "type number", "double", "#,0.00"), ("churned", "Int64.Type", "int64", "0"),
    ("tenure_group", "type text", "string", None), ("churn_risk", "type number", "double", "0.0%"),
    ("risk_group", "type text", "string", None),
]
customers_tmdl = "table customers\n\n"
for name, _, dt, fmt in CUST_COLS:
    customers_tmdl += col(name, dt, fmt) + "\n"
customers_tmdl += m_partition("customers", csv_query("DataFolder", "customers_scored.csv", CUST_COLS))

DRV_COLS = [("factor", "type text", "string", None), ("odds_ratio", "type number", "double", "0.00"),
            ("ci_low", "type number", "double", "0.00"), ("ci_high", "type number", "double", "0.00"),
            ("p_value", "type number", "double", "0.0000"), ("pct_change_in_odds", "type number", "double", "+0%;-0%"),
            ("sort_order", "Int64.Type", "int64", "0")]
drivers_tmdl = "table drivers\n\n"
for name, _, dt, fmt in DRV_COLS:
    drivers_tmdl += col(name, dt, fmt, sort_by="sort_order" if name == "factor" else None) + "\n"
drivers_tmdl += m_partition("drivers", csv_query("TablesFolder", "drivers.csv", DRV_COLS))

TOP20 = '{ "A. Top 10%", "B. 10-20%" }'
M = []
M.append(measure("Customers", "DISTINCTCOUNT ( customers[customerID] )", "#,0", "Core KPIs"))
M.append(measure("Churned Customers", "CALCULATE ( COUNTROWS ( customers ), customers[churned] = 1 )", "#,0", "Core KPIs"))
M.append(measure("Churn Rate", "DIVIDE ( [Churned Customers], [Customers] )", "0.0%", "Core KPIs"))
M.append(measure("Overall Churn Rate", "CALCULATE ( [Churn Rate], ALL ( customers ) )", "0.0%", "Core KPIs"))
M.append(measure("Avg Tenure (months)", "AVERAGE ( customers[tenure] )", "0.0", "Core KPIs"))
M.append(measure("Monthly Revenue", "SUM ( customers[MonthlyCharges] )", "#,0", "Revenue"))
M.append(measure("Monthly Revenue Lost", "CALCULATE ( SUM ( customers[MonthlyCharges] ), customers[churned] = 1 )", "#,0", "Revenue"))
M.append(measure("Revenue Lost %", "DIVIDE ( [Monthly Revenue Lost], [Monthly Revenue] )", "0.0%", "Revenue"))
# two-series trick: bars above the average churn rate in vermilion, the others in blue
M.append(measure("Churn Rate Above Average", "VAR r = [Churn Rate] RETURN IF ( r > [Overall Churn Rate], r )", "0.0%", "Chart helpers"))
M.append(measure("Churn Rate Below Average", "VAR r = [Churn Rate] RETURN IF ( r <= [Overall Churn Rate], r )", "0.0%", "Chart helpers"))
M.append(measure("Churn Rate (internet customers)", 'CALCULATE ( [Churn Rate], customers[InternetService] <> "No" )', "0.0%", "Chart helpers"))
M.append(measure("Internet Churn Above Average", "VAR r = [Churn Rate (internet customers)] RETURN IF ( r > [Overall Churn Rate], r )", "0.0%", "Chart helpers"))
M.append(measure("Internet Churn Below Average", "VAR r = [Churn Rate (internet customers)] RETURN IF ( r <= [Overall Churn Rate], r )", "0.0%", "Chart helpers"))
M.append(measure("Share of All Churners", "DIVIDE ( [Churned Customers], CALCULATE ( [Churned Customers], ALL ( customers ) ) )", "0.0%", "Targeting"))
M.append(measure("Top 20% Customers", f"CALCULATE ( [Customers], customers[risk_group] IN {TOP20} )", "#,0", "Targeting"))
M.append(measure("Top 20% Churn Rate", f"CALCULATE ( [Churn Rate], customers[risk_group] IN {TOP20} )", "0.0%", "Targeting"))
M.append(measure("Top 20% Share of Churners", f"CALCULATE ( [Share of All Churners], customers[risk_group] IN {TOP20} )", "0.0%", "Targeting"))
M.append(measure("Top 20% Revenue Lost", f"CALCULATE ( [Monthly Revenue Lost], customers[risk_group] IN {TOP20} )", "#,0", "Targeting"))
M.append(measure("Scenario Saved per Month", "[Top 20% Revenue Lost] * 0.25", "#,0", "Targeting"))
M.append(measure("Scenario Saved per Year", "[Scenario Saved per Month] * 12", "#,0", "Targeting"))
M.append(measure("Odds Change Up", "VAR v = MAX ( drivers[pct_change_in_odds] ) RETURN IF ( v > 0, v )", "+0%;-0%", "Chart helpers"))
M.append(measure("Odds Change Down", "VAR v = MAX ( drivers[pct_change_in_odds] ) RETURN IF ( v <= 0, v )", "+0%;-0%", "Chart helpers"))

measures_tmdl = (f"table _Measures\n\n{T}column Dummy\n{T}{T}dataType: int64\n{T}{T}isHidden\n{T}{T}summarizeBy: none\n"
                 f"{T}{T}sourceColumn: [Dummy]\n\n" + "\n".join(M) +
                 f"\n{T}partition _Measures = calculated\n{T}{T}mode: import\n{T}{T}source = ROW ( \"Dummy\", 1 )\n")

expressions_tmdl = (
    f'expression DataFolder = "{DATA_DIR}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n\n'
    f'expression TablesFolder = "{TABLES_DIR}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n')

model_tmdl = """model Model
	culture: en-US
	defaultPowerBIDataSourceVersion: powerBI_V3
	discourageImplicitMeasures
	sourceQueryCulture: en-US

ref table customers
ref table drivers
ref table _Measures
"""

for p in (SM, RP):
    if p.exists():
        shutil.rmtree(p)
wj(SM / "definition.pbism", {"version": "4.0", "settings": {}})
w(SM / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
w(SM / "definition" / "model.tmdl", model_tmdl)
w(SM / "definition" / "expressions.tmdl", expressions_tmdl)
w(SM / "definition" / "tables" / "customers.tmdl", customers_tmdl)
w(SM / "definition" / "tables" / "drivers.tmdl", drivers_tmdl)
w(SM / "definition" / "tables" / "_Measures.tmdl", measures_tmdl)

# =====================================================================
# REPORT (PBIR)
# =====================================================================
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def solid(color):
    return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}}


def fld(table, prop, kind="Column"):
    return {kind: {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}


def proj(table, prop, kind="Column", active=None):
    d = {"field": fld(table, prop, kind), "queryRef": f"{table}.{prop}", "nativeQueryRef": prop}
    if active:
        d["active"] = True
    return d


def title(text):
    return {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{text}'"),
                                      "fontSize": lit("12D"), "bold": lit("true")}}]}


def visual(name, x, y, w_, h, vtype, query=None, objects=None, container=None, z=1000):
    v = {"visualType": vtype, "drillFilterOtherVisuals": True}
    if query:
        v["query"] = query
    if objects:
        v["objects"] = objects
    d = {"$schema": f"{SCHEMA}/visualContainer/2.0.0/schema.json", "name": name,
         "position": {"x": x, "y": y, "z": z, "height": h, "width": w_, "tabOrder": z}, "visual": v}
    if container:
        d["visual"]["visualContainerObjects"] = container
    return d


def card(name, x, measure_name, label, units=None, precision=None):
    props = {"fontSize": lit("24D")}
    if units is not None:
        props["labelDisplayUnits"] = lit(f"{units}D")
        if precision is not None:
            props["labelPrecision"] = lit(f"{precision}L")
    objects = {"labels": [{"properties": props}], "categoryLabels": [{"properties": {"show": lit("false")}}]}
    return visual(name, x, 70, 165, 80, "card",
                  {"queryState": {"Values": {"projections": [proj("_Measures", measure_name, "Measure")]}}},
                  objects=objects,
                  container={"title": [{"properties": {"show": lit("true"), "text": lit(f"'{label}'"),
                                                       "fontSize": lit("10D")}}]})


def chart(name, x, y, w_, h, vtype, cat, vals, ttl, labels=False, pct=False, dec=None):
    qs = {"Category": {"projections": [proj(*cat, active=True)]},
          "Y": {"projections": [proj(t, p, "Measure") for t, p in vals]}}
    no_title = {"properties": {"showAxisTitle": lit("false")}}
    objects = {"categoryAxis": [no_title], "valueAxis": [no_title]}
    if labels:
        precision = dec if dec is not None else (1 if pct else 0)
        objects["labels"] = [{"properties": {"show": lit("true"), "labelPrecision": lit(f"{precision}L")}}]
    return visual(name, x, y, w_, h, vtype, {"queryState": qs}, objects=objects, container=title(ttl))


def textbox(name, x, y, w_, h, paragraphs):
    paras = []
    for text, bold, size, *rest in paragraphs:
        run = {"value": text, "textStyle": {"fontSize": f"{size}pt"}}
        if rest:
            run["textStyle"]["color"] = rest[0]
        if bold:
            run["textStyle"]["fontWeight"] = "bold"
        paras.append({"textRuns": [run]})
    return visual(name, x, y, w_, h, "textbox", objects={"general": [{"properties": {"paragraphs": paras}}]})


def slicer(name, x, y, w_, h, table, prop, ttl):
    q = {"queryState": {"Values": {"projections": [proj(table, prop, active=True)]}}}
    return visual(name, x, y, w_, h, "slicer", q,
                  objects={"data": [{"properties": {"mode": lit("'Dropdown'")}}]}, container=title(ttl))


def table(name, x, y, w_, h, cols, ttl, sort=None):
    q = {"queryState": {"Values": {"projections": [proj(t, p, k) for t, p, k in cols]}}}
    if sort:
        t, p, k, direction = sort
        q["sortDefinition"] = {"sort": [{"field": fld(t, p, k), "direction": direction}]}
    return visual(name, x, y, w_, h, "tableEx", q, container=title(ttl),
                  objects={"total": [{"properties": {"totals": lit("false")}}]})


def nav(name):
    selected = {"properties": {"fillColor": solid(TEAL)}, "selector": {"id": "selected"}}
    selected_text = {"properties": {"fontColor": solid(INK)}, "selector": {"id": "selected"}}
    return visual(name, 500, 8, 450, 44, "pageNavigator", objects={"fill": [selected], "text": [selected_text]})


def shape(name, y, h, color, z):
    objs = {"shape": [{"properties": {"tileShape": lit("'rectangle'")}}],
            "fill": [{"properties": {"fillColor": solid(color)}, "selector": {"id": "default"}}],
            "outline": [{"properties": {"show": lit("false")}}]}
    return visual(name, 0, y, 1280, h, "shape", objects=objs, z=z)


def clear_button(name):
    objs = {"text": [{"properties": {"show": lit("true"), "text": lit("'Clear filters'"),
                                     "fontColor": solid("#FFFFFF")}, "selector": {"id": "default"}}],
            "icon": [{"properties": {"shapeType": lit("'blank'")}, "selector": {"id": "default"}}]}
    link = {"visualLink": [{"properties": {"show": lit("true"), "type": lit("'ClearAllSlicers'")}}]}
    return visual(name, 958, 8, 110, 44, "actionButton", objects=objs, container=link)


def cards(specs):
    return [card(n, 20 + i * 172, m, lab, **kw) for i, (n, m, lab, kw) in enumerate(specs)]


def TOP(t, n, slicer_spec=None):
    items = [textbox(f"title{n}", 20, 0, 470, 46, [(t, True, 18, "#FFFFFF")]),
             textbox(f"subtitle{n}", 20, 38, 470, 26,
                     [("Telecom customers (IBM sample data)  |  7,043 customers  |  churn analysis", False, 9, "#C9D3E6")]),
             shape(f"stripe{n}", 64, 4, TEAL, 1), nav(f"nav{n}"), clear_button(f"clear{n}")]
    if slicer_spec:
        items.append(slicer(f"slicer_top{n}", 1075, 8, 185, 50, *slicer_spec))
    return items


# ---------------- page 1: overview
page1 = TOP("Telco: who leaves?", 1, ("customers", "Contract", "Contract")) + cards([
    ("c_cust", "Customers", "Customers", dict(units=1)),
    ("c_churned", "Churned Customers", "Customers who left", dict(units=1)),
    ("c_rate", "Churn Rate", "Churn rate", {}),
    ("c_tenure", "Avg Tenure (months)", "Avg tenure (months)", {}),
    ("c_lost", "Monthly Revenue Lost", "Monthly revenue lost ($)", dict(units=1000, precision=0)),
    ("c_lostpct", "Revenue Lost %", "Share of revenue lost", {}),
]) + [
    slicer("slicer_internet1", 1055, 70, 205, 80, "customers", "InternetService", "Internet service"),
    chart("ch_contract", 20, 160, 620, 270, "columnChart", ("customers", "Contract", "Column"),
          [("_Measures", "Churn Rate Above Average"), ("_Measures", "Churn Rate Below Average")],
          "Churn rate by contract", labels=True, pct=True),
    chart("ch_tenure", 660, 160, 600, 270, "columnChart", ("customers", "tenure_group", "Column"),
          [("_Measures", "Churn Rate Above Average"), ("_Measures", "Churn Rate Below Average")],
          "Churn rate by time as a customer", labels=True, pct=True),
    chart("ch_payment", 20, 445, 620, 265, "barChart", ("customers", "PaymentMethod", "Column"),
          [("_Measures", "Churn Rate Above Average"), ("_Measures", "Churn Rate Below Average")],
          "Churn rate by payment method", labels=True, pct=True),
    textbox("findings1", 660, 445, 600, 265, [
        ("Key findings", True, 14),
        ("1. 26.5% of customers left (1,869 of 7,043), taking $139K of monthly revenue (30.5% of the total).", False, 11),
        ("2. Month-to-month contracts churn at 43%, two-year contracts at 3%.", False, 11),
        ("3. Customers in their first year churn at 47%, after four years only 10%.", False, 11),
        ("4. Electronic check payers churn at 45% (15% to 19% for the other methods).", False, 11),
    ]),
]

# ---------------- page 2: drivers
page2 = TOP("What drives churn?", 2) + [
    chart("ch_drivers", 20, 78, 620, 632, "barChart", ("drivers", "factor", "Column"),
          [("_Measures", "Odds Change Up"), ("_Measures", "Odds Change Down")],
          "Change in the odds of churn, all else equal (significant factors)", labels=True, pct=True, dec=0),
    chart("ch_internet", 660, 78, 600, 215, "columnChart", ("customers", "InternetService", "Column"),
          [("_Measures", "Churn Rate Above Average"), ("_Measures", "Churn Rate Below Average")],
          "Churn rate by internet service", labels=True, pct=True),
    chart("ch_tech", 660, 305, 600, 215, "columnChart", ("customers", "TechSupport", "Column"),
          [("_Measures", "Internet Churn Above Average"), ("_Measures", "Internet Churn Below Average")],
          "Churn rate by tech support (internet customers)", labels=True, pct=True),
    textbox("findings2", 660, 532, 600, 178, [
        ("How to read this", True, 14),
        ("+147% for fiber optic: the odds of churning are 2.5 times those of DSL customers with the same contract, tenure and other services.", False, 11),
        ("-74% for a two-year contract: four times lower odds than month-to-month. Gender has no effect (not shown).", False, 11),
    ]),
]

# ---------------- page 3: who to call
page3 = TOP("Who to call first?", 3) + cards([
    ("t_cust", "Top 20% Customers", "Customers to call first (top 20%)", dict(units=1)),
    ("t_rate", "Top 20% Churn Rate", "Churn rate in that group", {}),
    ("t_share", "Top 20% Share of Churners", "Share of all churners reached", {}),
    ("t_rev", "Top 20% Revenue Lost", "Monthly revenue at risk ($)", dict(units=1000, precision=0)),
    ("t_month", "Scenario Saved per Month", "Scenario: saved per month ($)", dict(units=1000, precision=1)),
    ("t_year", "Scenario Saved per Year", "Scenario: saved per year ($)", dict(units=1000, precision=0)),
]) + [
    chart("ch_group_rate", 20, 160, 620, 270, "columnChart", ("customers", "risk_group", "Column"),
          [("_Measures", "Churn Rate Above Average"), ("_Measures", "Churn Rate Below Average")],
          "Actual churn rate by predicted-risk group", labels=True, pct=True),
    chart("ch_group_share", 660, 160, 600, 270, "clusteredColumnChart", ("customers", "risk_group", "Column"),
          [("_Measures", "Share of All Churners")], "Share of all churners in each group", labels=True, pct=True),
    table("t_ranked", 20, 445, 1240, 265,
          [("customers", "customerID", "Column"), ("customers", "risk_group", "Column"),
           ("customers", "churn_risk", "Column"), ("customers", "Contract", "Column"),
           ("customers", "tenure", "Column"), ("customers", "InternetService", "Column"),
           ("customers", "MonthlyCharges", "Column"), ("customers", "churned", "Column")],
          "Customers ranked by predicted risk (cross-validated scores; 'churned' = 1 if the customer left)",
          sort=("customers", "churn_risk", "Column", "Descending")),
]


# ---------------- page 4: about
def info_box(name, x, y, w_, h, heading, lines):
    paras = [(heading, True, 17)]
    for t in lines:
        paras += [(" ", False, 4), (t, False, 12)]
    return textbox(name, x, y, w_, h, paras)


page4 = TOP("About the company and the data", 4) + [
    info_box("about_company", 20, 82, 620, 290, "The company", [
        "A fictional telecom operator from IBM's public sample data. It is not a real company, so it has no brand colors: the colors of this report are a design choice.",
        "Customers have a phone line and/or internet (DSL or fiber), optional add-ons such as tech support or streaming, and a monthly, one-year or two-year contract.",
        "Each row is one customer, with a flag showing whether they left in the last month.",
    ]),
    info_box("about_data", 660, 82, 600, 290, "The data in numbers", [
        "7,043 customers, 21 original columns, no duplicates",
        "26.5% churned (1,869 customers)",
        "Average tenure 32.4 months, average bill $64.76 a month",
        "Monthly revenue $456K, of which $139K (30.5%) belongs to customers who left",
    ]),
    info_box("about_defs", 20, 388, 620, 322, "Definitions", [
        "Churn = the customer left in the last month.",
        "Tenure = months as a customer.",
        "Change in odds = how much a factor multiplies the odds of churning, holding the others constant (+147% = 2.5 times).",
        "Risk group = customers ranked by predicted churn risk (A = riskiest 10%). The 'top 20%' is groups A and B.",
    ]),
    info_box("about_method", 660, 388, 600, 322, "Method and limits", [
        "Python cleaned the data, a logistic regression measured the drivers and predicted churn (AUC 0.845 on customers the model had not seen).",
        "The monthly bill was left out of the driver model because it is nearly determined by the services chosen (collinearity).",
        "The 25% 'saved' figure is a scenario to test with an A/B experiment, not a prediction.",
        "Association is not causation. Sample data.",
    ]),
]

BORDER = {"border": [{"properties": {"show": lit("true"), "color": lit("'#D9DCEB'"), "radius": lit("10D")}}],
          "background": [{"properties": {"show": lit("true"), "color": solid("#FFFFFF"), "transparency": lit("0D")}}]}
for pg, band_name in ((page1, "band1"), (page2, "band2"), (page3, "band3"), (page4, "band4")):
    pg.insert(0, shape(band_name, 0, 64, INK, 0))
    for v in pg:
        if v["name"].startswith(("title", "subtitle")):
            v["visual"].setdefault("visualContainerObjects", {})["background"] = [{"properties": {"show": lit("false")}}]
        elif v["visual"]["visualType"] not in ("pageNavigator", "actionButton", "shape"):
            v["visual"].setdefault("visualContainerObjects", {}).update(BORDER)

VERSION_AT_IMPORT = {"visual": "1.8.50", "report": "2.0.50", "page": "1.3.50"}
wj(PBI / f"{NAME}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                          "settings": {"enableAutoRecovery": True}})
wj(RP / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
wj(RP / "definition" / "version.json", {"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
wj(RP / "StaticResources" / "RegisteredResources" / "TelcoTheme.json", {
    "name": "TelcoTheme",
    # first color = series 1 of the two-series charts (above-average churn / factors that raise churn)
    "dataColors": [CHURN, BLUE, TEAL, AMBER, GREY, "#F2A38C", "#8E9AE6", "#7FDDD3"],
    "background": "#FFFFFF", "foreground": "#1C2733", "tableAccent": INK})
wj(RP / "definition" / "report.json", {
    "$schema": f"{SCHEMA}/report/3.0.0/schema.json",
    "themeCollection": {
        "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": VERSION_AT_IMPORT, "type": "SharedResources"},
        "customTheme": {"name": "TelcoTheme.json", "reportVersionAtImport": VERSION_AT_IMPORT, "type": "RegisteredResources"}},
    "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                          "items": [{"name": "TelcoTheme.json", "path": "TelcoTheme.json", "type": "CustomTheme"}]}],
    "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                 "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                 "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}})
wj(RP / "definition" / "pages" / "pages.json", {"$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
                                                "pageOrder": ["page_overview", "page_drivers", "page_call", "page_about"],
                                                "activePageName": "page_overview"})
for pname, disp, visuals in (("page_overview", "Overview", page1), ("page_drivers", "Drivers", page2),
                             ("page_call", "Who to call", page3), ("page_about", "About", page4)):
    wj(RP / "definition" / "pages" / pname / "page.json",
       {"$schema": f"{SCHEMA}/page/2.0.0/schema.json", "name": pname, "displayName": disp,
        "displayOption": "FitToPage", "height": 720, "width": 1280,
        "objects": {"background": [{"properties": {"color": solid("#F4F5FA"), "transparency": lit("0D")}}]}})
    for v in visuals:
        wj(RP / "definition" / "pages" / pname / "visuals" / v["name"] / "visual.json", v)

w(PBI / ".gitignore", ".pbi/\n*.pbix.bak\n")
print("Built", PBI / f"{NAME}.pbip")
