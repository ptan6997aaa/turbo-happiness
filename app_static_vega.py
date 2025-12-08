import dash
from dash import html
import dash_bootstrap_components as dbc
import dash_vega_components as dvc
import pandas as pd
import altair as alt

# ==================== 1. 数据加载 ====================
df_fact = pd.read_excel("FactPerformance.xlsx", sheet_name="Sheet1")
df_dimStu = pd.read_excel("DimStudents.xlsx", sheet_name="Sheet1")
df_dimCal = pd.read_excel("DimCalendar.xlsx", sheet_name="Date")
df_dimSub = pd.read_excel("DimSubjects.xlsx", sheet_name="DimSubjects")

# 合并维度表
df = pd.merge(df_fact, df_dimStu[["StudentID", "GradeLevel"]], on="StudentID", how="left")
df = pd.merge(df, df_dimSub[["SubjectID", "SubjectName"]], on="SubjectID", how="left")
df_dimCal["YearQuarterConcat"] = df_dimCal["Year"].astype(str) + " Q" + df_dimCal["QuarterNumber"].astype(str)
df = pd.merge(df, df_dimCal[["DateKey", "YearQuarterConcat"]], on="DateKey", how="left")  # ✅ 已修正拼写

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

# ==================== 2. 预计算静态 KPI 与图表 ====================
if df.empty:
    k_avg = k_w = k_pass = k_perf = "N/A"
    spec_grade = spec_level = {}
else:
    # KPI: Average Score
    k_avg = f"{df['Score'].mean():.2f}"

    # KPI: Weighted Average (fallback to avg if WeightedScore missing)
    if "WeightedScore" in df.columns and "Weight" in df.columns:
        total_weight = df["Weight"].sum()
        if total_weight > 0:
            k_w = f"{df['WeightedScore'].sum() / total_weight:.2f}"
        else:
            k_w = k_avg
    else:
        k_w = k_avg

    # KPI: Pass Rate
    k_pass = f"{(df['PassedScore'] == 'Pass').mean() * 100:.1f}%"

    # KPI: Perfect Score Rate
    k_perf = f"{(df['Score'] == perfect_target).mean() * 100:.1f}%"

    # Donut 1: Grade Distribution (by Assessment_Grade)
    grade_counts = df["Assessment_Grade"].value_counts().reset_index()
    grade_counts.columns = ["grade", "count"]
    donut_grade = alt.Chart(grade_counts).mark_arc(innerRadius=90, outerRadius=140).encode(
        theta=alt.Theta("count:Q", stack=True),
        color=alt.Color(
            "grade:N",
            scale=alt.Scale(domain=['A','B','C','D','F'],
                            range=['#2ecc71', '#3498db', '#f1c40f', '#e67e22', '#e74c3c'])
        ),
        tooltip=["grade", "count"]
    ).properties(width=300, height=300, title="Exam Count by Grade")
    spec_grade = donut_grade.to_dict()

    # Donut 2: Student Coverage by Grade Level (distinct StudentID)
    level_students = df.groupby("GradeLevel")["StudentID"].nunique().reset_index()
    level_students.columns = ["level", "students"]
    donut_level = alt.Chart(level_students).mark_arc(innerRadius=90, outerRadius=140).encode(
        theta=alt.Theta("students:Q", stack=True),
        color=alt.Color("level:N", scale=alt.Scale(scheme="category10")),
        tooltip=["level", "students"]
    ).properties(width=300, height=300, title="Unique Students by Grade Level")
    spec_level = donut_level.to_dict()

# ==================== 3. 静态 Dash App Layout ====================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

app.layout = dbc.Container([
    html.H1("Student Performance Dashboard", className="text-center my-4 text-primary fw-bold"),

    # 第一排：4 个 KPI
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Average Score", className="text-white text-center text-opacity-75"),
            html.H2(k_avg, className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #667eea, #764ba2)"}), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Weighted Average", className="text-white text-center text-opacity-75"),
            html.H2(k_w, className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #11998e, #38ef7d)"}), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Pass Rate", className="text-white text-center text-opacity-75"),
            html.H2(k_pass, className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #4facfe, #00f2fe)"}), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Perfect Score Rate", className="text-white text-center text-opacity-75"),
            html.H2(k_perf, className="text-white text-center fw-bold")
        ]), className="shadow", style={"background": "linear-gradient(135deg, #ff9a00, #ffd200)"}), width=3),
    ], className="mb-4 g-4"),

    # 第二排：2 个 Donut 图表
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("Grade Distribution (Count of Exams)", className="fw-bold text-center"),
            dbc.CardBody(dvc.Vega(spec=spec_grade, style={"height": "380px"}))
        ], className="shadow"), width=6),
        dbc.Col(dbc.Card([
            dbc.CardHeader("Student Coverage by Grade Level", className="fw-bold text-center"),
            dbc.CardBody(dvc.Vega(spec=spec_level, style={"height": "380px"}))
        ], className="shadow"), width=6),
    ], className="mb-5"),

], fluid=True, className="bg-light")

# ==================== 4. 运行 ====================
if __name__ == "__main__":
    app.run(debug=True, port=8050)