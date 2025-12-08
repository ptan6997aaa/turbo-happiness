import dash
from dash import html, dcc, Input, Output
import dash_bootstrap_components as dbc
import dash_vega_components as dvc
import pandas as pd
import altair as alt
from dash.exceptions import PreventUpdate

# ==================== 1. 数据加载 ====================
df_fact = pd.read_excel("FactPerformance.xlsx", sheet_name="Sheet1")
df_dimStu = pd.read_excel("DimStudents.xlsx", sheet_name="Sheet1")
df_dimCal = pd.read_excel("DimCalendar.xlsx", sheet_name="Date")
df_dimSub = pd.read_excel("DimSubjects.xlsx", sheet_name="DimSubjects")

df = pd.merge(df_fact, df_dimStu[["StudentID", "GradeLevel"]], on="StudentID", how="left")
df = pd.merge(df, df_dimSub[["SubjectID", "SubjectName"]], on="SubjectID", how="left")
df_dimCal["YearQuarterConcat"] = df_dimCal["Year"].astype(str) + " Q" + df_dimCal["QuarterNumber"].astype(str)
df = pd.merge(df, df_dimCal[["DateKey", "YearQuarterConcat"]], on="DateKey", how="left")

# 衍生字段
df["PassedScore"] = df["Score"].apply(lambda x: "Pass" if x >= 55 else "Fail")
def get_grade(s):
    if s > 84: return "A"
    if s > 74: return "B"
    if s > 64: return "C"
    if s > 54: return "D"
    return "F"
df["Assessment_Grade"] = df["Score"].apply(get_grade)
df['Assessment_Grade'] = pd.Categorical(df['Assessment_Grade'], categories=['A','B','C','D','F'], ordered=True)

perfect_target = 100

# ==================== 2. Dash App ====================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

app.layout = dbc.Container([
    html.H1("Student Performance Dashboard", className="text-center my-4 text-primary fw-bold"),

    # 筛选区（可扩展）
    dbc.Row([
        dbc.Col([
            html.Label("Grade Level"),
            dcc.Dropdown(id="filter-grade", options=[{"label": "All", "value": "All"}] +
                         [{"label": g, "value": g} for g in sorted(df["GradeLevel"].unique())],
                         value="All", clearable=False)
        ], md=3),
        dbc.Col([
            html.Label("Subject"),
            dcc.Dropdown(id="filter-subject", options=[{"label": "All", "value": "All"}] +
                         [{"label": s, "value": s} for s in sorted(df["SubjectName"].unique())],
                         value="All", clearable=False)
        ], md=3),
        dbc.Col([
            html.Label("Quarter"),
            dcc.Dropdown(id="filter-quarter", options=[{"label": "All", "value": "All"}] +
                         [{"label": q, "value": q} for q in sorted(df["YearQuarterConcat"].unique())],
                         value="All", clearable=False)
        ], md=3),
        dbc.Col([
            html.Label("Pass Status"),
            dcc.Dropdown(id="filter-pass", options=[{"label": "All", "value": "All"}, {"label": "Pass", "value": "Pass"}, {"label": "Fail", "value": "Fail"}],
                         value="All", clearable=False)
        ], md=3),
    ], className="mb-4 bg-light p-3 rounded"),

    # 第一排：4 个 KPI
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Average Score", className="text-white text-center text-opacity-75"),
            html.H2(id="kpi-avg", className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #667eea, #764ba2)"}), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Weighted Average", className="text-white text-center text-opacity-75"),
            html.H2(id="kpi-weighted", className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #11998e, #38ef7d)"}), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Pass Rate", className="text-white text-center text-opacity-75"),
            html.H2(id="kpi-pass", className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #4facfe, #00f2fe)"}), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Perfect Score Rate", className="text-white text-center text-opacity-75"),
            html.H2(id="kpi-perfect", className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #ff9a00, #ffd200)"}), width=3),
    ], className="mb-4 g-4"),

    # 第二排：2 个 Vega Donut Chart
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("Grade Distribution (Count of Exams)", className="fw-bold text-center"),
            dbc.CardBody(dvc.Vega(id="vega-grade-donut", spec={}, style={"height": "380px"}))
        ], className="shadow"), width=6),
        dbc.Col(dbc.Card([
            dbc.CardHeader("Student Coverage by Grade Level", className="fw-bold text-center"),
            dbc.CardBody(dvc.Vega(id="vega-level-donut", spec={}, style={"height": "380px"}))
        ], className="shadow"), width=6),
    ], className="mb-5"),

    html.Div(id="debug", style={"display": "none"})
], fluid=True, className="bg-light")

# ==================== 3. 核心回调 ====================
@app.callback(
    Output("kpi-avg", "children"),
    Output("kpi-weighted", "children"),
    Output("kpi-pass", "children"),
    Output("kpi-perfect", "children"),
    Output("vega-grade-donut", "spec"),
    Output("vega-level-donut", "spec"),
    Input("filter-grade", "value"),
    Input("filter-subject", "value"),
    Input("filter-quarter", "value"),
    Input("filter-pass", "value")
)
def update_dashboard(grade, subject, quarter, pass_status):
    # 过滤数据
    d = df.copy()
    if grade != "All":      d = d[d["GradeLevel"] == grade]
    if subject != "All":    d = d[d["SubjectName"] == subject]
    if quarter != "All":    d = d[d["YearQuarterConcat"] == quarter]
    if pass_status != "All": d = d[d["PassedScore"] == pass_status]

    # KPI
    if d.empty:
        k_avg = k_w = k_pass = k_perf = "N/A"
    else:
        k_avg = f"{d['Score'].mean():.2f}"
        w_sum = d["Weight"].sum() if "Weight" in d.columns else 1
        k_w = f"{(d['WeightedScore'].sum() / w_sum):.2f}" if "WeightedScore" in d.columns and w_sum > 0 else k_avg
        k_pass = f"{(d['PassedScore'] == 'Pass').mean()*100:.1f}%"
        k_perf = f"{(d['Score'] == perfect_target).mean()*100:.1f}%"

    # Donut 1: Assessment_Grade → Count of RecordID
    grade_counts = d["Assessment_Grade"].value_counts().reset_index()
    grade_counts.columns = ["grade", "count"]
    donut_grade = alt.Chart(grade_counts).mark_arc(innerRadius=90, outerRadius=140).encode(
        theta=alt.Theta("count:Q", stack=True),
        color=alt.Color("grade:N", scale=alt.Scale(domain=['A','B','C','D','F'],
                     range=['#2ecc71', '#3498db', '#f1c40f', '#e67e22', '#e74c3c'])),
        tooltip=["grade", "count"]
    ).properties(width=300, height=300, title="Exam Count by Grade")
    spec_grade = donut_grade.to_dict()

    # Donut 2: GradeLevel → distinct count of StudentID
    level_students = d.groupby("GradeLevel")["StudentID"].nunique().reset_index()
    level_students.columns = ["level", "students"]
    donut_level = alt.Chart(level_students).mark_arc(innerRadius=90, outerRadius=140).encode(
        theta=alt.Theta("students:Q", stack=True),
        color=alt.Color("level:N", scale=alt.Scale(scheme="category10")),
        tooltip=["level", "students"]
    ).properties(width=300, height=300, title="Unique Students by Grade Level")
    spec_level = donut_level.to_dict()

    return k_avg, k_w, k_pass, k_perf, spec_grade, spec_level

# ==================== 4. 运行 ====================
if __name__ == "__main__":
    app.run(debug=True, port=8050)