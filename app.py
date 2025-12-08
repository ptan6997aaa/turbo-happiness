import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import dash_vega_components as dvc
import altair as alt
import pandas as pd
import numpy as np
import os

# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 1. 数据准备 (Data Loading & Preprocessing)                                   │
# └──────────────────────────────────────────────────────────────────────────────┘
def load_data():
    # 为了保证代码可直接运行，这里保留了 Mock 数据生成逻辑
    # 如果你有真实文件，代码会优先读取文件
    try:
        if os.path.exists("FactPerformance.xlsx"):
            df_fact = pd.read_excel("FactPerformance.xlsx")
            df_dimStu = pd.read_excel("DimStudents.xlsx")
            df_dimSub = pd.read_excel("DimSubjects.xlsx")
        else:
            raise FileNotFoundError("Files not found")
    except Exception:
        # Mock Data
        np.random.seed(42)
        n = 1000
        df_fact = pd.DataFrame({
            "StudentID": np.random.randint(1, 201, n),
            "Score": np.random.randint(40, 100, n),
            "Weight": np.random.choice([1, 1.5, 2], n),
            "SubjectID": np.random.randint(101, 105, n)
        })
        df_dimStu = pd.DataFrame({
            "StudentID": range(1, 201),
            "GradeLevel": np.random.choice(["Grade 9", "Grade 10", "Grade 11", "Grade 12"], 200)
        })
        df_dimSub = pd.DataFrame({
            "SubjectID": [101, 102, 103, 104],
            "SubjectName": ["Math", "Science", "English", "History"]
        })

    # Merge
    df = pd.merge(df_fact, df_dimStu[["StudentID", "GradeLevel"]], on="StudentID", how="left")
    df = pd.merge(df, df_dimSub[["SubjectID", "SubjectName"]], on="SubjectID", how="left")

    # Metrics
    df["PassedScore"] = df["Score"].apply(lambda x: "Pass" if x >= 55 else "Fail")
    df["WeightedScore"] = df["Score"] * df["Weight"]
    
    # Grading
    def get_grade(s):
        if s >= 85: return "A"
        elif s >= 75: return "B"
        elif s >= 65: return "C"
        elif s >= 55: return "D"
        else: return "F"
    
    df["Assessment_Grade"] = df["Score"].apply(get_grade)
    # 模拟主键用于计数
    df["RecordID"] = df.index 
    
    return df

df = load_data()
perfect_target = 100

# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 2. UI 布局 (Layout)                                                          │
# └──────────────────────────────────────────────────────────────────────────────┘
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.LUMEN])

KPI_STYLE = {"box-shadow": "0 4px 6px rgba(0,0,0,0.1)", "border-radius": "8px", "border": "none"}

app.layout = dbc.Container([
    # ── State Stores (核心：用于存储当前的筛选状态) ──
    dcc.Store(id='store-grade', data=None),  # 存储选中的成绩 (A, B, C...)
    dcc.Store(id='store-level', data=None),  # 存储选中的年级 (Grade 9, 10...)

    # ── Header ──
    dbc.Row([
        dbc.Col(html.H2("📊 Study Performance (Cross-Filter)", className="fw-bold text-primary"), width=9),
        dbc.Col(
            dbc.Button("↺ Reset Filters", id="btn-reset", color="danger", outline=True, className="w-100"),
            width=3, className="d-flex align-items-center"
        )
    ], className="my-4 pb-3 border-bottom"),

    # ── Row 1: KPI Cards ──
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Avg Score"), html.H2(id="kpi-avg", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Weighted Avg"), html.H2(id="kpi-w", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Pass Rate"), html.H2(id="kpi-pass", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Perfect Score"), html.H2(id="kpi-perf", className="fw-bold")]), style=KPI_STYLE), width=3),
    ], className="mb-4"),

    # ── Row 2: Charts ──
    # 注意 signalsToObserve，这告诉 Dash 去监听 Vega 图表里的 selection 变化
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("By Result (Click to Filter)", className="fw-bold bg-white text-center"),
            dbc.CardBody(dvc.Vega(id="chart-result", signalsToObserve=["sel_grade"], style={'width': '100%'}))
        ], style=KPI_STYLE), width=6),

        dbc.Col(dbc.Card([
            dbc.CardHeader("By Grade Level (Click to Filter)", className="fw-bold bg-white text-center"),
            dbc.CardBody(dvc.Vega(id="chart-level", signalsToObserve=["sel_level"], style={'width': '100%'}))
        ], style=KPI_STYLE), width=6),
    ]),
    
    # 底部状态栏，显示当前筛选条件
    html.Div(id="filter-status", className="text-center text-muted mt-3 small")

], fluid=True, className="bg-light vh-100 p-4")

# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 3. 核心逻辑：状态管理 (State Management Callback)                            │
# └──────────────────────────────────────────────────────────────────────────────┘
@app.callback(
    [Output('store-grade', 'data'),
     Output('store-level', 'data')],
    [Input('chart-result', 'signalData'),  # 监听图表1点击
     Input('chart-level', 'signalData'),   # 监听图表2点击
     Input('btn-reset', 'n_clicks')],
    [State('store-grade', 'data'),
     State('store-level', 'data')]
)
def update_filters(sig_res, sig_lev, n_reset, curr_grade, curr_level):
    """
    负责解析 Vega 的点击信号，并更新 dcc.Store。
    实现“点击选中 -> 再次点击取消”的逻辑。
    """
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # 1. 重置按钮
    if trigger_id == 'btn-reset':
        return None, None

    # 2. 处理结果分布图点击 (左图)
    if trigger_id == 'chart-result' and sig_res and 'sel_grade' in sig_res:
        # Vega 返回格式通常是 {'sel_grade': {'Assessment_Grade': ['A']}}
        data = sig_res['sel_grade']
        if not data: return dash.no_update, dash.no_update # 点击空白处
        
        # 获取点击的值
        clicked_val = data['Assessment_Grade'][0] if 'Assessment_Grade' in data and data['Assessment_Grade'] else None
        
        if clicked_val:
            # Toggle 逻辑：如果点击的和当前存的一样，就清空（取消选择）；否则更新
            if curr_grade == clicked_val:
                return None, curr_level
            else:
                return clicked_val, curr_level

    # 3. 处理年级分布图点击 (右图)
    if trigger_id == 'chart-level' and sig_lev and 'sel_level' in sig_lev:
        data = sig_lev['sel_level']
        if not data: return dash.no_update, dash.no_update

        clicked_val = data['GradeLevel'][0] if 'GradeLevel' in data and data['GradeLevel'] else None
        
        if clicked_val:
            if curr_level == clicked_val:
                return curr_grade, None
            else:
                return curr_grade, clicked_val

    return dash.no_update, dash.no_update

# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 4. 渲染逻辑：图表和KPI更新 (Rendering Callback)                              │
# └──────────────────────────────────────────────────────────────────────────────┘
@app.callback(
    [Output("kpi-avg", "children"),
     Output("kpi-w", "children"),
     Output("kpi-pass", "children"),
     Output("kpi-perf", "children"),
     Output("chart-result", "spec"),
     Output("chart-level", "spec"),
     Output("filter-status", "children")],
    [Input('store-grade', 'data'),
     Input('store-level', 'data')]
)
def update_view(sel_grade, sel_level):
    # ── Step 1: 数据过滤 (Cross-Filtering Logic) ──
    # df_kpi: 受所有过滤器影响 (用于计算KPI)
    df_kpi = df.copy()
    if sel_grade: df_kpi = df_kpi[df_kpi["Assessment_Grade"] == sel_grade]
    if sel_level: df_kpi = df_kpi[df_kpi["GradeLevel"] == sel_level]

    # df_chart1 (左图数据): 只受右图筛选影响 (为了展示在该年级下的成绩分布)
    df_c1 = df.copy()
    if sel_level: df_c1 = df_c1[df_c1["GradeLevel"] == sel_level]

    # df_chart2 (右图数据): 只受左图筛选影响 (为了展示该成绩在各年级的分布)
    df_c2 = df.copy()
    if sel_grade: df_c2 = df_c2[df_c2["Assessment_Grade"] == sel_grade]

    # ── Step 2: 计算 KPIs ──
    if df_kpi.empty:
        k_avg, k_w, k_pass, k_perf = "-", "-", "-", "-"
    else:
        k_avg = f"{df_kpi['Score'].mean():.1f}"
        w_sum = df_kpi["Weight"].sum()
        k_w = f"{(df_kpi['WeightedScore'].sum()/w_sum):.1f}" if w_sum>0 else "0.0"
        k_pass = f"{(df_kpi['PassedScore']=='Pass').mean()*100:.1f}%"
        k_perf = f"{(df_kpi['Score']==perfect_target).mean()*100:.1f}%"

    # ── Step 3: 构建 Vega Charts (带高亮逻辑) ──
    
    # 通用函数：构建带交互的甜甜圈图
    def build_donut(dataframe, theta_field, color_field, agg_type, sel_name, current_selection, color_scale, title):
        # 如果被过滤空了
        if dataframe.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text().encode(text='text').to_dict()

        # 定义点击参数 (Signal)
        # 这里 value=init_val 并不是必须的，因为我们通过 Python 重绘控制颜色，但保留它有助于Vega初始化
        click = alt.selection_point(fields=[color_field], name=sel_name)

        # 颜色逻辑：如果当前有选中项，非选中项变灰
        if current_selection:
            color_condition = alt.condition(
                alt.datum[color_field] == current_selection,
                alt.Color(color_field, scale=color_scale),
                alt.value('#e0e0e0') # 灰色
            )
        else:
            color_condition = alt.Color(color_field, scale=color_scale)

        base = alt.Chart(dataframe).encode(
            theta=alt.Theta(theta_field, aggregate=agg_type, stack=True),
            color=color_condition,
            tooltip=[color_field, alt.Tooltip(theta_field, aggregate=agg_type, title="Count")]
        ).add_params(click) # 添加点击监听

        pie = base.mark_arc(innerRadius=70)
        text = base.mark_text(radius=120).encode(
            text=alt.Text(theta_field, aggregate=agg_type),
            order=alt.Order(color_field),
            color=alt.value("black")  # 始终显示黑色文字
        )
        return (pie + text).properties(title=title).to_dict()

    # 左图: Assessment Grade (Count of RecordID)
    scale_grade = alt.Scale(domain=['A','B','C','D','F'], range=['#2ecc71', '#3498db', '#f1c40f', '#e67e22', '#e74c3c'])
    spec1 = build_donut(df_c1, "RecordID", "Assessment_Grade", "count", "sel_grade", sel_grade, scale_grade, "Results")

    # 右图: Grade Level (Distinct Count of StudentID)
    scale_level = alt.Scale(scheme="category20")
    spec2 = build_donut(df_c2, "StudentID", "GradeLevel", "distinct", "sel_level", sel_level, scale_level, "Grade Levels")

    # 状态文字
    status = []
    if sel_grade: status.append(f"Result: {sel_grade}")
    if sel_level: status.append(f"Level: {sel_level}")
    status_text = " | ".join(status) if status else "Viewing All Data"

    return k_avg, k_w, k_pass, k_perf, spec1, spec2, status_text

if __name__ == "__main__":
    app.run(debug=True, port=8057)