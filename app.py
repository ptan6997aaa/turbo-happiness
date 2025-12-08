import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import dash_vega_components as dvc
import altair as alt
import pandas as pd

# ==================== 1. 数据加载与预处理 ====================
try:
    df_fact = pd.read_excel("FactPerformance.xlsx", sheet_name="Sheet1")
    df_dimStu = pd.read_excel("DimStudents.xlsx", sheet_name="Sheet1")
    df_dimCal = pd.read_excel("DimCalendar.xlsx", sheet_name="Date")
    df_dimSub = pd.read_excel("DimSubjects.xlsx", sheet_name="DimSubjects")
except Exception as e:
    print(f"Loading mock data due to error: {e}")
    import numpy as np
    np.random.seed(42)
    n = 500
    df_fact = pd.DataFrame({
        "StudentID": np.random.choice(range(1000, 2000), n),
        "SubjectID": np.random.choice([1, 2, 3, 4], n),
        "DateKey": pd.date_range("2023-01-01", periods=4, freq='Q')[np.random.choice(4, n)],
        "Score": np.clip(np.random.normal(75, 15, n), 0, 100),
    })
    df_dimStu = pd.DataFrame({
        "StudentID": range(1000, 2000),
        "GradeLevel": np.random.choice(["Grade 9", "Grade 10", "Grade 11", "Grade 12"], 1000)
    })
    df_dimSub = pd.DataFrame({
        "SubjectID": [1, 2, 3, 4],
        "SubjectName": ["Math", "Science", "English", "History"]
    })
    df_dimCal = pd.DataFrame({
        "DateKey": pd.date_range("2023-01-01", periods=4, freq='Q'),
        "Year": [2023, 2023, 2023, 2023],
        "QuarterNumber": [1, 2, 3, 4]
    })

df = pd.merge(df_fact, df_dimStu[["StudentID", "GradeLevel"]], on="StudentID", how="left")
df = pd.merge(df, df_dimSub[["SubjectID", "SubjectName"]], on="SubjectID", how="left")
df_dimCal["YearQuarterConcat"] = df_dimCal["Year"].astype(str) + " Q" + df_dimCal["QuarterNumber"].astype(str)
df = pd.merge(df, df_dimCal[["DateKey", "YearQuarterConcat"]], left_on="DateKey", right_on="DateKey", how="left") 

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

# ==================== 2. App Layout ====================
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

KPI_STYLE = {
    "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    "color": "white",
    "border": "none",
    "border-radius": "10px",
    "box-shadow": "0 4px 6px rgba(0,0,0,0.1)"
}

app.layout = dbc.Container([
    dcc.Store(id='store-grade', data='All'),
    dcc.Store(id='store-subject', data='All'),
    dcc.Store(id='store-assess-grade', data='All'),

    dbc.Row([
        dbc.Col(html.H2("🎓 Student Performance Dashboard", className="fw-bold my-3"), width=9),
        dbc.Col(
            dbc.Button("↺ Reset All Filters", id="btn-reset", color="danger", outline=True, className="mt-4 w-100 shadow-sm"),
            width=3
        )
    ], className="mb-4 border-bottom pb-3"),

    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Average Score"), html.H3(id="kpi-avg", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Weighted Avg"), html.H3(id="kpi-wavg", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Pass Rate"), html.H3(id="kpi-pass", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Perfect Rate"), html.H3(id="kpi-perfect", className="fw-bold")]), style=KPI_STYLE), width=3),
    ], className="mb-4"),

    # 第二排：两个 Donut 图
    dbc.Row([
        # 左：Student Count by Grade Level (唯一学生数)
        dbc.Col(dbc.Card([
            dbc.CardHeader("Student Count by Grade Level", className="fw-bold text-center"),
            dbc.CardBody(dvc.Vega(id="chart-grade", signalsToObserve=["sel_grade"], style={"height": "380px"}))
        ], className="shadow"), width=6),

        # 右：Exam Count by Assessment Grade (A-F) —— 使用 Assessment_Grade 分组，计数记录
        dbc.Col(dbc.Card([
            dbc.CardHeader("Exam Count by Assessment Grade", className="fw-bold text-center"),
            dbc.CardBody(dvc.Vega(id="chart-assess", signalsToObserve=["sel_assess"], style={"height": "380px"}))
        ], className="shadow"), width=6),
    ], className="mb-4"),

    # 第三排：Subject 条形图
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("Avg Score by Subject", className="bg-white fw-bold border-0"),
            dbc.CardBody(dvc.Vega(id="chart-subject", signalsToObserve=["sel_subject"], style={'width': '100%', 'height': '300px'}))
        ], style={"box-shadow": "0 2px 4px rgba(0,0,0,0.05)", "border-radius": "8px"}), width=12),
    ], className="mb-4"),

    dbc.Row(dbc.Col(html.Div(id="filter-status", className="text-muted small mt-4 text-end fst-italic")))
], fluid=True, className="bg-light vh-100 p-4")


# ==================== 3. 筛选状态管理 ====================
@app.callback(
    [Output('store-grade', 'data'),
     Output('store-subject', 'data'),
     Output('store-assess-grade', 'data')],
    [Input('btn-reset', 'n_clicks'),
     Input('chart-grade', 'signalData'),
     Input('chart-subject', 'signalData'),
     Input('chart-assess', 'signalData')],
    [State('store-grade', 'data'),
     State('store-subject', 'data'),
     State('store-assess-grade', 'data')]
)
def manage_filters(n_clicks, sig_grade, sig_subj, sig_assess, curr_grade, curr_subj, curr_assess):
    ctx = callback_context
    if not ctx.triggered:
        return "All", "All", "All"
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'btn-reset':
        return "All", "All", "All"

    def process_signal(signal_data, signal_name, key_name, current_filter):
        if not signal_data or signal_name not in signal_data:
            return current_filter
        sel = signal_data[signal_name]
        if not sel:
            return "All"
        if key_name in sel and len(sel[key_name]) > 0:
            clicked = sel[key_name][0]
            if str(current_filter) != "All" and str(clicked) == str(current_filter):
                return "All"
            return clicked
        return current_filter

    if trigger_id == 'chart-grade':
        new_grade = process_signal(sig_grade, 'sel_grade', 'GradeLevel', curr_grade)
        return new_grade, curr_subj, curr_assess
    if trigger_id == 'chart-subject':
        new_subj = process_signal(sig_subj, 'sel_subject', 'SubjectName', curr_subj)
        return curr_grade, new_subj, curr_assess
    if trigger_id == 'chart-assess':
        new_assess = process_signal(sig_assess, 'sel_assess', 'Assessment_Grade', curr_assess)
        return curr_grade, curr_subj, new_assess

    return curr_grade, curr_subj, curr_assess


# ==================== 4. 可视化更新逻辑 ====================
@app.callback(
    [Output('kpi-avg', 'children'),
     Output('kpi-wavg', 'children'),
     Output('kpi-pass', 'children'),
     Output('kpi-perfect', 'children'),
     Output('chart-grade', 'spec'),
     Output('chart-assess', 'spec'),
     Output('chart-subject', 'spec'),
     Output('filter-status', 'children')],
    [Input('store-grade', 'data'),
     Input('store-subject', 'data'),
     Input('store-assess-grade', 'data')]
)
def update_visuals(sel_grade, sel_subj, sel_assess):
    def filter_df(ignore_grade=False, ignore_subj=False, ignore_assess=False):
        d = df.copy()
        if not ignore_grade and sel_grade != "All":
            d = d[d["GradeLevel"] == sel_grade]
        if not ignore_subj and sel_subj != "All":
            d = d[d["SubjectName"] == sel_subj]
        if not ignore_assess and sel_assess != "All":
            d = d[d["Assessment_Grade"] == sel_assess]
        return d

    df_kpi = filter_df()
    if df_kpi.empty:
        k_avg = k_w = k_pass = k_perf = "N/A"
    else:
        k_avg = f"{df_kpi['Score'].mean():.2f}"
        if "WeightedScore" in df_kpi.columns and "Weight" in df_kpi.columns:
            total_w = df_kpi["Weight"].sum()
            k_w = f"{df_kpi['WeightedScore'].sum() / total_w:.2f}" if total_w > 0 else k_avg
        else:
            k_w = k_avg
        k_pass = f"{(df_kpi['PassedScore'] == 'Pass').mean() * 100:.1f}%"
        k_perf = f"{(df_kpi['Score'] == perfect_target).mean() * 100:.1f}%"

    # ── Donut: Student Count by Grade Level (unique StudentID count) ──
    def build_donut_grade(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        
        agg = df_in.groupby('GradeLevel')['StudentID'].nunique().reset_index()
        agg.columns = ['GradeLevel', 'UniqueStudents']
        
        init_value = [{'GradeLevel': selected_val}] if selected_val != "All" else None
        sel_param = alt.selection_point(name="sel_grade", fields=["GradeLevel"], value=init_value)
        
        # 高亮逻辑：选中项保持原色，未选中变灰
        color_condition = alt.condition(
            sel_param,
            alt.Color("GradeLevel:N", scale=alt.Scale(scheme="category10")),
            alt.value('#eee')
        )
        
        donut = alt.Chart(agg).mark_arc(innerRadius=90, outerRadius=140).encode(
            theta=alt.Theta("UniqueStudents:Q", stack=True),
            color=color_condition,
            tooltip=["GradeLevel", alt.Tooltip("UniqueStudents", title="Students")]
        ).add_params(sel_param).properties(width=300, height=300)
        
        return donut.to_dict()

    # ── Donut: Exam Count by Assessment Grade (count of records) ──
    def build_donut_assess(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        
        counts = df_in["Assessment_Grade"].value_counts().reindex(['A','B','C','D','F'], fill_value=0).reset_index()
        counts.columns = ["Assessment_Grade", "ExamCount"]
        
        color_map = {'A':'#2ecc71','B':'#3498db','C':'#f1c40f','D':'#e67e22','F':'#e74c3c'}
        
        init_value = [{"Assessment_Grade": selected_val}] if selected_val != "All" else None
        sel_param = alt.selection_point(name="sel_assess", fields=["Assessment_Grade"], value=init_value)
        
        # 自定义颜色 + 高亮逻辑
        color_condition = alt.condition(
            sel_param,
            alt.Color(
                "Assessment_Grade:N",
                scale=alt.Scale(domain=['A','B','C','D','F'], range=list(color_map.values()))
            ),
            alt.value('#eee')
        )
        
        donut = alt.Chart(counts).mark_arc(innerRadius=90, outerRadius=140).encode(
            theta=alt.Theta("ExamCount:Q", stack=True),
            color=color_condition,
            tooltip=["Assessment_Grade", "ExamCount"]
        ).add_params(sel_param).properties(width=300, height=300)
        
        return donut.to_dict()

    # ── Bar: Avg Score by Subject ──
    def build_bar_subject(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        agg = df_in.groupby("SubjectName")["Score"].mean().reset_index()
        agg = agg.sort_values("Score", ascending=False)
        init_value = [{"SubjectName": selected_val}] if selected_val != "All" else None
        sel_param = alt.selection_point(name="sel_subject", fields=["SubjectName"], value=init_value)
        color_condition = alt.condition(
            alt.datum["SubjectName"] == selected_val,
            alt.value('#11998e'),
            alt.value('#ccc')
        ) if selected_val != "All" else alt.value('#11998e')
        bar = alt.Chart(agg).mark_bar().encode(
            x=alt.X("SubjectName", sort='-y', axis=alt.Axis(title=None)),
            y=alt.Y("Score", axis=alt.Axis(title=None)),
            color=color_condition,
            tooltip=["SubjectName", alt.Tooltip("Score", format=".2f")]
        ).add_params(sel_param).properties(height=280, width='container')
        return bar.to_dict()

    # 获取忽略自身筛选的数据
    df_grade = filter_df(ignore_grade=True)
    df_assess = filter_df(ignore_assess=True)
    df_subject = filter_df(ignore_subj=True)

    spec_grade = build_donut_grade(df_grade, sel_grade)
    spec_assess = build_donut_assess(df_assess, sel_assess)
    spec_subject = build_bar_subject(df_subject, sel_subj)

    status_text = f"Filters: GradeLevel='{sel_grade}' | Subject='{sel_subj}' | Assessment Grade='{sel_assess}'"

    return k_avg, k_w, k_pass, k_perf, spec_grade, spec_assess, spec_subject, status_text


# ==================== 5. Run ====================
if __name__ == "__main__":
    app.run(debug=True, port=8050)