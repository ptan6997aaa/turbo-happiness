# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 1. DATA LOADING & PREPROCESSING: 支持真实数据 + 模拟数据兜底                  │
# │                                                                              │
# │ ★ 设计原则：                                                                 │
# │   - 优先读取真实 Excel 文件                                                  │
# │   - 若文件缺失，自动生成结构一致的模拟数据（便于演示/测试）                  │
# │   - 所有衍生字段（等级、通过标志等）在加载阶段完成                           │
# └──────────────────────────────────────────────────────────────────────────────┘

import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── 尝试加载真实数据，失败则生成模拟数据 ───────────────────────────────────────
try:
    df_fact = pd.read_excel("FactPerformance.xlsx", sheet_name="Sheet1")       # 考试事实表
    df_dimStu = pd.read_excel("DimStudents.xlsx", sheet_name="Sheet1")         # 学生维度
    df_dimCal = pd.read_excel("DimCalendar.xlsx", sheet_name="Date")           # 日期维度
    df_dimSub = pd.read_excel("DimSubjects.xlsx", sheet_name="DimSubjects")    # 学科维度（NEW）
except FileNotFoundError:
    print("Data files not found. Using Dummy Data.")
    import numpy as np
    
    n_rows = 1000
    # 模拟事实表：StudentID (1-19), DateKey (~90天), SubjectID (1-4), Score (50-99)
    df_fact = pd.DataFrame({
        'StudentID': np.random.randint(1, 20, n_rows),
        'DateKey': np.random.choice(range(20220101, 20220330), n_rows),
        'SubjectID': np.random.randint(1, 5, n_rows),
        'Score': np.random.randint(50, 100, n_rows)
    })
    
    df_dimStu = pd.DataFrame({
        'StudentID': range(1, 21), 
        'GradeLevel': np.random.choice([9, 10, 11, 12], 20)  # 4个年级
    })
    
    dates = pd.date_range(start='2022-01-01', periods=90)
    df_dimCal = pd.DataFrame({
        'DateKey': [int(d.strftime('%Y%m%d')) for d in dates],
        'Year': dates.year,
        'QuarterNumber': dates.quarter,
        'Month': dates.month
    })
    
    df_dimSub = pd.DataFrame({
        'SubjectID': [1, 2, 3, 4],
        'SubjectName': ['Math', 'Science', 'English', 'History']
    })

# ── 构建分析宽表：星型模型展开 ─────────────────────────────────────────────────
df = pd.merge(df_fact, df_dimStu[["StudentID", "GradeLevel"]], on="StudentID", how="left")
df = pd.merge(df, df_dimSub[["SubjectID", "SubjectName"]], on="SubjectID", how="left")

# 构造时间标签（用于前端展示）
df_dimCal["YearQuarterConcat"] = df_dimCal["Year"].astype(str) + " Q" + df_dimCal["QuarterNumber"].astype(str)
df_dimCal["YearMonthConcat"]   = df_dimCal["Year"].astype(str) + "-" + df_dimCal["Month"].apply(lambda x: f"{x:02d}")
df = pd.merge(df, df_dimCal[["DateKey", "YearQuarterConcat", "YearMonthConcat", "QuarterNumber", "Year"]], on="DateKey", how="left")

# ── 衍生字段 ───────────────────────────────────────────────────────────────────
if "Weight" not in df.columns: 
    df["Weight"] = 1
if "WeightedScore" not in df.columns: 
    df["WeightedScore"] = df["Score"] * df["Weight"]
df["PassedScore"] = df["Score"].apply(lambda x: "Pass" if x >= 55 else "Fail")

def get_grade(score):
    if score > 84: return "A"
    if score > 74: return "B"
    if score > 64: return "C"
    if score > 54: return "D"
    return "F"

df["Assessment_Grade"] = df["Score"].apply(get_grade)
grade_order = ['A', 'B', 'C', 'D', 'F']
df['Assessment_Grade'] = pd.Categorical(df['Assessment_Grade'], categories=grade_order, ordered=True)

if "GradeLevel" in df.columns:
    df = df.sort_values(['GradeLevel', 'Assessment_Grade'])


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 2. DASH APP SETUP: UI 布局                                                   │
# │                                                                              │
# │ ★ 设计说明：                                                                 │
# │   - 使用 dcc.Store 存储四个筛选维度的当前状态                                │
# │   - 所有图表使用 dcc.Graph（Plotly 原生组件）                                │
# │   - 隐藏 Plotly 模式栏（config={'displayModeBar': False}）提升整洁度          │
# └──────────────────────────────────────────────────────────────────────────────┘

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

card_style_purple = {
    "background": "linear-gradient(45deg, #6a11cb 0%, #2575fc 100%)",
    "color": "white",
}

app.layout = dbc.Container([
    # 状态存储（相当于前端的 state）
    dcc.Store(id='store-grade', data='All'),
    dcc.Store(id='store-level', data='All'),
    dcc.Store(id='store-time', data='All'),
    dcc.Store(id='store-subject', data='All'),  # ← 新增学科筛选状态

    html.H2("Education Performance Analysis", className="my-3"),

    # 顶部：筛选状态 + 重置按钮
    dbc.Row([
        dbc.Col([html.H5(id='filter-status-text', className="text-primary")], width=8),
        dbc.Col([dbc.Button("Reset All Filters", id="reset-btn", color="secondary", size="sm", className="w-100")], width=4)
    ], className="mb-4"),

    # KPI 指标行
    dbc.Row([
        dbc.Col(dbc.Card([dbc.CardBody([html.H6("Average Score"), html.H3(id="kpi-avg")])], style=card_style_purple), width=3),
        dbc.Col(dbc.Card([dbc.CardBody([html.H6("Weighted Avg"), html.H3(id="kpi-weighted")])], style=card_style_purple), width=3),
        dbc.Col(dbc.Card([dbc.CardBody([html.H6("Pass Rate"), html.H3(id="kpi-pass", className="text-success")])]), width=3),
        dbc.Col(dbc.Card([dbc.CardBody([html.H6("Perfect Scores"), html.H3(id="kpi-perfect", className="text-primary")])]), width=3),
    ], className="mb-4"),

    # 环形图行（使用 Plotly 的 pie + hole=0.6 实现环形）
    dbc.Row([
        dbc.Col(dbc.Card([dbc.CardHeader("Grade Distribution"), dbc.CardBody([dcc.Graph(id="chart-grade", config={'displayModeBar': False}, style={'height': '250px'})])]), width=6),
        dbc.Col(dbc.Card([dbc.CardHeader("Grade Level Distribution"), dbc.CardBody([dcc.Graph(id="chart-level", config={'displayModeBar': False}, style={'height': '250px'})])]), width=6),
    ], className="mb-4"),

    # 趋势图 + 学科图
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader([
                dbc.Row([
                    dbc.Col(html.Span(id="time-chart-title", children="Performance Over Time"), width=7, className="align-self-center"),
                    dbc.Col(
                        dbc.RadioItems(
                            id="time-view-toggle",
                            options=[{"label": "Quarter", "value": "Quarter"}, {"label": "Month", "value": "Month"}],
                            value="Quarter",
                            inline=True,
                            inputClassName="btn-check",
                            labelClassName="btn btn-outline-primary btn-sm",
                            labelCheckedClassName="active"
                        ), width=5, className="d-flex justify-content-end"
                    ),
                ])
            ]),
            dbc.CardBody([dcc.Graph(id="chart-time-trend", config={'displayModeBar': False}, style={'height': '300px'})])
        ]), width=6),
        
        # ← 新增：学科柱状图
        dbc.Col(dbc.Card([
            dbc.CardHeader("Average Score by Subject (Click to Filter)"),
            dbc.CardBody([dcc.Graph(id="chart-subject", config={'displayModeBar': False}, style={'height': '300px'})])
        ]), width=6),
    ])
], fluid=True)


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 3. CALLBACKS: 交互逻辑核心                                                   │
# │                                                                              │
# │ ★ 交互机制说明：                                                             │
# │   - Plotly 的 clickData 返回点击点的详细信息（如 label, x, y）               │
# │   - 点击逻辑：若点击已选中项 → 取消筛选（"All"）；否则 → 应用新筛选           │
# │   - 时间下钻：点击季度 → 切换到月视图，并锁定该季度                          │
# └──────────────────────────────────────────────────────────────────────────────┘

@app.callback(
    [
        Output('store-grade', 'data'),
        Output('store-level', 'data'),
        Output('store-time', 'data'),
        Output('store-subject', 'data'),
        Output('time-view-toggle', 'value')
    ],
    [
        Input('reset-btn', 'n_clicks'),
        Input('chart-grade', 'clickData'),
        Input('chart-level', 'clickData'),
        Input('chart-time-trend', 'clickData'),
        Input('chart-subject', 'clickData'),  # ← 监听学科图点击
        Input('time-view-toggle', 'value')
    ],
    [
        State('store-grade', 'data'),
        State('store-level', 'data'),
        State('store-time', 'data'),
        State('store-subject', 'data')
    ]
)
def update_filters(n_reset, click_grade, click_level, click_time, click_subject, view_mode, 
                   current_grade, current_level, current_time, current_subject):
    """
    核心：响应用户点击，更新全局筛选状态。
    
    交互规则：
    - 重置按钮：清空所有筛选
    - 切换时间粒度：自动清除时间筛选（避免跨粒度状态冲突）
    - 图表点击：
        * 成绩/年级/学科图：点击选中，再点取消（toggle）
        * 时间图（季度）：点击后下钻到月度，并锁定该季度
    """
    ctx = callback_context
    if not ctx.triggered:
        return "All", "All", "All", "All", "Quarter"

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # 1. 重置逻辑
    if trigger_id == 'reset-btn':
        return "All", "All", "All", "All", "Quarter"

    # 2. 切换时间粒度：清除时间筛选，防止粒度混乱
    if trigger_id == 'time-view-toggle':
        return current_grade, current_level, "All", current_subject, view_mode

    # 3. 处理各图表点击事件
    # 成绩等级图（环形图）
    if trigger_id == 'chart-grade' and click_grade:
        clicked_val = click_grade['points'][0]['label']  # 获取点击的等级标签
        new_grade = "All" if clicked_val == current_grade else clicked_val
        return new_grade, current_level, current_time, current_subject, view_mode

    # 年级图（环形图）
    if trigger_id == 'chart-level' and click_level:
        clicked_val = click_level['points'][0]['label']
        new_level = "All" if clicked_val == current_level else clicked_val
        return current_grade, new_level, current_time, current_subject, view_mode

    # 时间趋势图（柱状图）
    if trigger_id == 'chart-time-trend' and click_time:
        clicked_val = click_time['points'][0]['x']  # 获取点击的 x 轴值（如 "2022 Q1"）
        if view_mode == "Quarter":
            # 下钻逻辑：季度 → 月度，并筛选该季度
            return current_grade, current_level, clicked_val, current_subject, "Month"
        else:
            # 月度视图：toggle 选中状态
            new_time = "All" if clicked_val == current_time else clicked_val
            return current_grade, current_level, new_time, current_subject, view_mode

    # 学科柱状图（NEW）
    if trigger_id == 'chart-subject' and click_subject:
        clicked_val = click_subject['points'][0]['x']  # 学科名称
        new_subject = "All" if clicked_val == current_subject else clicked_val
        return current_grade, current_level, current_time, new_subject, view_mode

    return current_grade, current_level, current_time, current_subject, view_mode


@app.callback(
    [
        Output('filter-status-text', 'children'),
        Output('time-chart-title', 'children'),
        Output('kpi-avg', 'children'),
        Output('kpi-weighted', 'children'),
        Output('kpi-pass', 'children'),
        Output('kpi-perfect', 'children'),
        Output('chart-grade', 'figure'),
        Output('chart-level', 'figure'),
        Output('chart-time-trend', 'figure'),
        Output('chart-subject', 'figure')
    ],
    [
        Input('store-grade', 'data'),
        Input('store-level', 'data'),
        Input('store-time', 'data'),
        Input('store-subject', 'data'),
        Input('time-view-toggle', 'value')
    ]
)
def update_ui(selected_grade, selected_level, selected_time, selected_subject, view_mode):
    """
    核心：根据当前筛选状态，重新计算 KPI 并生成所有图表。
    
    关键机制：Cross-filtering
      - 渲染某图表时，忽略该图表对应维度的筛选条件
      - 例如：渲染成绩等级环形图时，不应用 Grade 筛选，才能看到完整分布
    
    步骤：
    1. 构建筛选状态文本
    2. 计算 KPI（使用全筛选数据）
    3. 为每个图表生成“上下文数据”（忽略自身维度）
    4. 特殊处理时间图表标题（体现下钻上下文）
    """
    status_text = f"Filters | Grade: {selected_grade} | Level: {selected_level} | Time: {selected_time} | Sub: {selected_subject}"
    chart_title = "Performance Over Time"

    # ── 辅助函数：支持选择性忽略筛选维度（Cross-filtering 核心）────────────────
    def get_context_data(ignore_grade=False, ignore_level=False, ignore_time=False, ignore_subject=False):
        d = df.copy()
        if not ignore_grade and selected_grade != "All": 
            d = d[d["Assessment_Grade"] == selected_grade]
        if not ignore_level and selected_level != "All": 
            d = d[d["GradeLevel"] == selected_level]
        if not ignore_subject and selected_subject != "All": 
            d = d[d["SubjectName"] == selected_subject]
        if not ignore_time and selected_time != "All":
            if 'Q' in selected_time: 
                d = d[d["YearQuarterConcat"] == selected_time]
            else: 
                d = d[d["YearMonthConcat"] == selected_time]
        return d

    # ── 计算 KPI（应用全部筛选条件）──────────────────────────────────────────
    fully_filtered = get_context_data()
    if fully_filtered.empty:
        kpi_avg, kpi_weighted, kpi_pass, kpi_perfect = "0.00", "0.00", "0.00%", "0.0%"
        global_avg_line = 0
    else:
        kpi_avg = f"{fully_filtered['Score'].mean():.2f}"
        w_sum = fully_filtered["Weight"].sum()
        kpi_weighted = f"{(fully_filtered['WeightedScore'].sum() / w_sum):.2f}" if w_sum > 0 else "0.00"
        kpi_pass = f"{(fully_filtered['PassedScore'] == 'Pass').mean() * 100:.2f}%"
        perfect_target = 100 if df["Score"].max() > 1 else 1.0
        kpi_perfect = f"{(fully_filtered['Score'] == perfect_target).mean() * 100:.1f}%"
        global_avg_line = fully_filtered["Score"].mean()

    # ── 1. 成绩等级环形图（忽略 Grade 筛选）───────────────────────────────────
    df_grade_ctx = get_context_data(ignore_grade=True)
    if df_grade_ctx.empty:
        fig_grade = go.Figure().add_annotation(text="No Data", showarrow=False)
    else:
        df_agg_grade = df_grade_ctx.groupby('Assessment_Grade', observed=False)['Score'].count().reset_index()
        fig_grade = px.pie(
            df_agg_grade, values='Score', names='Assessment_Grade', hole=0.6,
            color='Assessment_Grade', 
            color_discrete_map={'A': '#2ca02c', 'B': '#1f77b4', 'C': '#ff7f0e', 'D': '#d62728', 'F': '#7f7f7f'}
        )
        # 高亮选中项（通过 pull 参数突出显示）
        if selected_grade != "All":
            fig_grade.update_traces(pull=[0.1 if x == selected_grade else 0 for x in df_agg_grade['Assessment_Grade']])
        fig_grade.add_annotation(text=f"{len(fully_filtered):,}<br>Assessments", x=0.5, y=0.5, showarrow=False, font_size=16)
        fig_grade.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)

    # ── 2. 年级环形图（忽略 Level 筛选）──────────────────────────────────────
    df_level_ctx = get_context_data(ignore_level=True)
    if df_level_ctx.empty:
        fig_level = go.Figure().add_annotation(text="No Data", showarrow=False)
    else:
        df_agg_level = df_level_ctx.groupby('GradeLevel', observed=False)['StudentID'].nunique().reset_index()
        fig_level = px.pie(df_agg_level, values='StudentID', names='GradeLevel', hole=0.6)
        if selected_level != "All":
            fig_level.update_traces(pull=[0.1 if x == selected_level else 0 for x in df_agg_level['GradeLevel']])
        fig_level.add_annotation(text=f"{fully_filtered['StudentID'].nunique():,}<br>Students", x=0.5, y=0.5, showarrow=False, font_size=16)
        fig_level.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)

    # ── 3. 时间趋势图（特殊处理时间上下文）────────────────────────────────────
    # 手动应用除时间外的筛选（因时间逻辑依赖 view_mode）
    d_time = df.copy()
    if selected_grade != "All": d_time = d_time[d_time["Assessment_Grade"] == selected_grade]
    if selected_level != "All": d_time = d_time[d_time["GradeLevel"] == selected_level]
    if selected_subject != "All": d_time = d_time[d_time["SubjectName"] == selected_subject]
    
    # 下钻逻辑：月视图下，若筛选了季度，则只显示该季度的月份
    if view_mode == "Month":
        if selected_time != "All" and 'Q' in selected_time:
            d_time = d_time[d_time["YearQuarterConcat"] == selected_time]
        elif selected_time != "All" and '-' in selected_time:
            parent_q = df[df["YearMonthConcat"] == selected_time]["YearQuarterConcat"].iloc[0]
            d_time = d_time[d_time["YearQuarterConcat"] == parent_q]

    if d_time.empty:
        fig_time = go.Figure().add_annotation(text="No Data", showarrow=False)
    else:
        time_col = "YearQuarterConcat" if view_mode == "Quarter" else "YearMonthConcat"
        df_bar_time = d_time.groupby(time_col)["Score"].mean().reset_index().sort_values(time_col)
        
        # 智能标题
        if view_mode == "Month" and 'Q' in selected_time:
            chart_title = f"Monthly Breakdown for {selected_time}"
        elif view_mode == "Month" and '-' in selected_time:
            parent_q = df[df["YearMonthConcat"] == selected_time]["YearQuarterConcat"].iloc[0]
            chart_title = f"Monthly Context ({parent_q})"
        else:
            chart_title = "Performance Over Time (Quarters)"

        fig_time = px.bar(df_bar_time, x=time_col, y="Score", text_auto='.1f')
        fig_time.update_xaxes(type='category')  # 确保 x 轴为离散类别

        # 高亮选中项（通过 opacity 控制）
        opacities = [1.0 if (selected_time == "All") or (x == selected_time) else 0.3 for x in df_bar_time[time_col]]
        fig_time.update_traces(marker=dict(opacity=opacities))
        fig_time.add_hline(y=global_avg_line, line_dash="dash", line_color="red", annotation_text=f"Avg: {global_avg_line:.1f}")
        fig_time.update_layout(margin=dict(t=20, b=20, l=20, r=20), xaxis_title=None, yaxis_title="Avg Score")

    # ── 4. 学科柱状图（忽略 Subject 筛选）────────────────────────────────────
    df_sub_ctx = get_context_data(ignore_subject=True)
    if df_sub_ctx.empty:
        fig_subject = go.Figure().add_annotation(text="No Data", showarrow=False)
    else:
        df_bar_sub = df_sub_ctx.groupby("SubjectName")["Score"].mean().reset_index().sort_values("Score", ascending=False)
        fig_subject = px.bar(df_bar_sub, x="SubjectName", y="Score", text_auto='.1f')
        sub_opacities = [1.0 if (selected_subject == "All") or (x == selected_subject) else 0.3 for x in df_bar_sub["SubjectName"]]
        fig_subject.update_traces(marker=dict(opacity=sub_opacities))
        fig_subject.add_hline(y=global_avg_line, line_dash="dash", line_color="red", annotation_text=f"Avg: {global_avg_line:.1f}")
        fig_subject.update_layout(margin=dict(t=20, b=20, l=20, r=20), xaxis_title=None, yaxis_title="Avg Score")

    return status_text, chart_title, kpi_avg, kpi_weighted, kpi_pass, kpi_perfect, fig_grade, fig_level, fig_time, fig_subject


# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ 4. ENTRY POINT                                                               │
# └──────────────────────────────────────────────────────────────────────────────┘
if __name__ == "__main__":
    app.run(debug=True)