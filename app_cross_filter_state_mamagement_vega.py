# 导入必要的 Dash 和可视化组件
import dash
from dash import dcc, html, Input, Output, State, callback_context  # Dash 核心组件和回调机制
import dash_bootstrap_components as dbc  # Bootstrap 风格的 UI 组件
import dash_vega_components as dvc       # 用于在 Dash 中渲染 Altair/Vega 图表
import altair as alt                     # 声明式可视化库
import pandas as pd                      # 数据处理

# ==================== 1. 数据加载与预处理 ====================
# 一次性读取所有数据表，避免重复 I/O（符合性能优化最佳实践）
df_fact = pd.read_excel("FactPerformance.xlsx", sheet_name="Sheet1")      # 事实表：包含成绩、日期、科目等
df_dimStu = pd.read_excel("DimStudents.xlsx", sheet_name="Sheet1")       # 学生维度表：学生 ID 与年级
df_dimCal = pd.read_excel("DimCalendar.xlsx", sheet_name="Date")          # 日期维度表：包含 Year、QuarterNumber 等
df_dimSub = pd.read_excel("DimSubjects.xlsx", sheet_name="DimSubjects")   # 科目维度表：SubjectID 与 SubjectName

# 将维度表与事实表进行左连接（left join），丰富事实数据
df = pd.merge(df_fact, df_dimStu[["StudentID", "GradeLevel"]], on="StudentID", how="left")
df = pd.merge(df, df_dimSub[["SubjectID", "SubjectName"]], on="SubjectID", how="left")

# 构造“年份+季度”字段，用于时间维度展示（例如：2024 Q1）
df_dimCal["YearQuarterConcat"] = df_dimCal["Year"].astype(str) + " Q" + df_dimCal["QuarterNumber"].astype(str)
# 将 YearQuarterConcat 字段通过 DateKey 与事实表关联
df = pd.merge(df, df_dimCal[["DateKey", "YearQuarterConcat"]], left_on="DateKey", right_on="DateKey", how="left") 

# 新增“是否通过”字段：分数 >=55 为 Pass，否则为 Fail
df["PassedScore"] = df["Score"].apply(lambda x: "Pass" if x >= 55 else "Fail")

# 定义成绩等级函数（A: >84, B: >74, ..., F: ≤54）
def get_grade(s):
    if s > 84: return "A"
    if s > 74: return "B"
    if s > 64: return "C"
    if s > 54: return "D"
    return "F"

# 应用函数生成 Assessment_Grade 列，并设置为有序分类（便于排序和可视化）
df["Assessment_Grade"] = df["Score"].apply(get_grade)
df['Assessment_Grade'] = pd.Categorical(df['Assessment_Grade'], categories=['A','B','C','D','F'], ordered=True)

# 定义“满分”目标值（用于 Perfect Rate 计算）
perfect_target = 100

# ==================== 2. App Layout（UI 布局） ====================
# 初始化 Dash 应用，使用 Bootstrap 主题提升 UI 美观度
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server  # 用于部署（如 gunicorn）

# 定义 KPI 卡片的统一样式：渐变背景、白色文字、圆角、阴影
KPI_STYLE = {
    "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    "color": "white",
    "border": "none",
    "border-radius": "10px",
    "box-shadow": "0 4px 6px rgba(0,0,0,0.1)"
}

# 构建主页面布局（使用 dbc.Container 实现响应式设计）
app.layout = dbc.Container([
    # 使用 dcc.Store 保存当前筛选状态（GradeLevel, Subject, Assessment_Grade）
    # 初始值均为 "All"，表示无筛选
    dcc.Store(id='store-grade', data='All'),
    dcc.Store(id='store-subject', data='All'),
    dcc.Store(id='store-assess-grade', data='All'),

    # 第一行：标题 + 重置按钮
    dbc.Row([
        # 左侧：主标题
        dbc.Col(html.H2("🎓 Student Performance Dashboard", className="fw-bold my-3"), width=9),
        # 右侧：“重置所有筛选”按钮（危险色 outline 风格）
        dbc.Col(
            dbc.Button("↺ Reset All Filters", id="btn-reset", color="danger", outline=True, className="mt-4 w-100 shadow-sm"),
            width=3
        )
    ], className="mb-4 border-bottom pb-3"),

    # 第二行：4 个 KPI 指标卡片（平均分、加权平均、通过率、满分率）
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Average Score"), html.H3(id="kpi-avg", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Weighted Avg"), html.H3(id="kpi-wavg", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Pass Rate"), html.H3(id="kpi-pass", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Perfect Rate"), html.H3(id="kpi-perfect", className="fw-bold")]), style=KPI_STYLE), width=3),
    ], className="mb-4"),

    # 第三行：两个 Donut 图（左：按年级的学生人数；右：按成绩等级的考试次数）
    dbc.Row([
        # 左：Student Count by Grade Level（使用唯一 StudentID 计数）
        dbc.Col(dbc.Card([
            dbc.CardHeader("Student Count by Grade Level", className="fw-bold text-center"),
            # 使用 dvc.Vega 渲染 Altair 图表，并监听 sel_grade 信号（用于交互）
            dbc.CardBody(dvc.Vega(id="chart-grade", signalsToObserve=["sel_grade"], style={"height": "380px"}))
        ], className="shadow"), width=6),

        # 右：Exam Count by Assessment Grade（A-F 的考试记录数）
        dbc.Col(dbc.Card([
            dbc.CardHeader("Exam Count by Assessment Grade", className="fw-bold text-center"),
            dbc.CardBody(dvc.Vega(id="chart-assess", signalsToObserve=["sel_assess"], style={"height": "380px"}))
        ], className="shadow"), width=6),
    ], className="mb-4"),

    # 第四行：Subject 条形图（各科目的平均分）
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("Avg Score by Subject", className="bg-white fw-bold border-0"),
            dbc.CardBody(dvc.Vega(id="chart-subject", signalsToObserve=["sel_subject"], style={'width': '100%', 'height': '300px'}))
        ], style={"box-shadow": "0 2px 4px rgba(0,0,0,0.05)", "border-radius": "8px"}), width=12),
    ], className="mb-4"),

    # 底部：实时显示当前筛选状态（用于调试和用户体验）
    dbc.Row(dbc.Col(html.Div(id="filter-status", className="text-muted small mt-4 text-end fst-italic")))
], fluid=True, className="bg-light vh-100 p-4")  # fluid=True：全宽容器；vh-100：占满视口高度

# ==================== 3. 筛选状态管理（核心交互逻辑） ====================
# 此回调负责更新三个 dcc.Store 的值，反映用户点击图表或点击重置按钮后的筛选状态
@app.callback(
    # 输出：三个 store 的 data 属性
    [Output('store-grade', 'data'),
     Output('store-subject', 'data'),
     Output('store-assess-grade', 'data')],
    # 输入：重置按钮点击 + 三个图表的信号数据（用户点击图表时触发）
    [Input('btn-reset', 'n_clicks'),
     Input('chart-grade', 'signalData'),      # 来自年级 Donut 图的 sel_grade 信号
     Input('chart-subject', 'signalData'),    # 来自科目条形图的 sel_subject 信号
     Input('chart-assess', 'signalData')],    # 来自成绩 Donut 图的 sel_assess 信号
    # 状态：当前 store 中的筛选值（用于“切换”逻辑：点击已选中项则取消筛选）
    [State('store-grade', 'data'),
     State('store-subject', 'data'),
     State('store-assess-grade', 'data')]
)
def manage_filters(n_clicks, sig_grade, sig_subj, sig_assess, curr_grade, curr_subj, curr_assess):
    # 获取触发回调的组件 ID
    ctx = callback_context
    if not ctx.triggered:
        # 首次加载时返回默认值
        return "All", "All", "All"
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # 如果点击了“重置”按钮，清空所有筛选
    if trigger_id == 'btn-reset':
        return "All", "All", "All"

    # 通用信号处理函数：解析 Altair 信号数据，提取用户点击的值
    def process_signal(signal_data, signal_name, key_name, current_filter):
        # 若无信号数据，保留当前筛选
        if not signal_data or signal_name not in signal_data:
            return current_filter
        sel = signal_data[signal_name]
        # 若信号为空（如用户点击空白区域），则取消筛选
        if not sel:
            return "All"
        # 若信号包含有效字段值
        if key_name in sel and len(sel[key_name]) > 0:
            clicked = sel[key_name][0]  # Altair 返回的是列表，取第一个
            # 实现“点击已选中项则取消筛选”的切换逻辑
            if str(current_filter) != "All" and str(clicked) == str(current_filter):
                return "All"
            return clicked
        return current_filter

    # 根据触发源更新对应的筛选状态
    if trigger_id == 'chart-grade':
        new_grade = process_signal(sig_grade, 'sel_grade', 'GradeLevel', curr_grade)
        return new_grade, curr_subj, curr_assess
    if trigger_id == 'chart-subject':
        new_subj = process_signal(sig_subj, 'sel_subject', 'SubjectName', curr_subj)
        return curr_grade, new_subj, curr_assess
    if trigger_id == 'chart-assess':
        new_assess = process_signal(sig_assess, 'sel_assess', 'Assessment_Grade', curr_assess)
        return curr_grade, curr_subj, new_assess

    # 默认返回当前状态（理论上不会触发）
    return curr_grade, curr_subj, curr_assess

# ==================== 4. 可视化更新逻辑（数据过滤 + 图表生成） ====================
# 此回调根据筛选状态更新 KPI 和所有图表
@app.callback(
    # 输出：4 个 KPI 文本 + 3 个图表 spec + 筛选状态文本
    [Output('kpi-avg', 'children'),
     Output('kpi-wavg', 'children'),
     Output('kpi-pass', 'children'),
     Output('kpi-perfect', 'children'),
     Output('chart-grade', 'spec'),
     Output('chart-assess', 'spec'),
     Output('chart-subject', 'spec'),
     Output('filter-status', 'children')],
    # 输入：三个 store 的当前筛选值
    [Input('store-grade', 'data'),
     Input('store-subject', 'data'),
     Input('store-assess-grade', 'data')]
)
def update_visuals(sel_grade, sel_subj, sel_assess):
    # 定义通用数据过滤函数，支持“忽略某字段”（用于交叉高亮）
    def filter_df(ignore_grade=False, ignore_subj=False, ignore_assess=False):
        d = df.copy()
        # 如果不忽略年级筛选且当前筛选不是 "All"，则应用筛选
        if not ignore_grade and sel_grade != "All":
            d = d[d["GradeLevel"] == sel_grade]
        if not ignore_subj and sel_subj != "All":
            d = d[d["SubjectName"] == sel_subj]
        if not ignore_assess and sel_assess != "All":
            d = d[d["Assessment_Grade"] == sel_assess]
        return d

    # 获取用于 KPI 计算的完整筛选数据
    df_kpi = filter_df()
    if df_kpi.empty:
        # 若无数据，KPI 显示 N/A
        k_avg = k_w = k_pass = k_perf = "N/A"
    else:
        # 计算平均分
        k_avg = f"{df_kpi['Score'].mean():.2f}"
        # 尝试计算加权平均（若数据中包含 WeightedScore 和 Weight 字段）
        if "WeightedScore" in df_kpi.columns and "Weight" in df_kpi.columns:
            total_w = df_kpi["Weight"].sum()
            k_w = f"{df_kpi['WeightedScore'].sum() / total_w:.2f}" if total_w > 0 else k_avg
        else:
            k_w = k_avg  # 若无权重字段，用普通平均分代替
        # 通过率：PassedScore == 'Pass' 的比例
        k_pass = f"{(df_kpi['PassedScore'] == 'Pass').mean() * 100:.1f}%"
        # 满分率：Score == 100 的比例
        k_perf = f"{(df_kpi['Score'] == perfect_target).mean() * 100:.1f}%"

    # ── 构建年级 Donut 图 ──
    def build_donut_grade(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        # 按年级统计唯一学生数（避免重复计数）
        agg = df_in.groupby('GradeLevel')['StudentID'].nunique().reset_index()
        agg.columns = ['GradeLevel', 'UniqueStudents']
        # 初始化选择状态（用于图表加载时高亮已选项）
        init_value = [{'GradeLevel': selected_val}] if selected_val != "All" else None
        sel_param = alt.selection_point(name="sel_grade", fields=["GradeLevel"], value=init_value)
        # 高亮逻辑：选中项使用彩色，未选中项变灰
        color_condition = alt.condition(
            sel_param,
            alt.Color("GradeLevel:N", scale=alt.Scale(scheme="category10")),  # 默认配色
            alt.value('#eee')  # 未选中灰色
        )
        donut = alt.Chart(agg).mark_arc(innerRadius=90, outerRadius=140).encode(
            theta=alt.Theta("UniqueStudents:Q", stack=True),  # 弧长 = 学生数
            color=color_condition,
            tooltip=["GradeLevel", alt.Tooltip("UniqueStudents", title="Students")]
        ).add_params(sel_param).properties(width=300, height=300)
        return donut.to_dict()

    # ── 构建成绩等级 Donut 图 ──
    def build_donut_assess(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        # 统计每个成绩等级的考试记录数（注意：是记录数，不是学生数）
        counts = df_in["Assessment_Grade"].value_counts().reindex(['A','B','C','D','F'], fill_value=0).reset_index()
        counts.columns = ["Assessment_Grade", "ExamCount"]
        # 自定义颜色映射（A绿色 → F红色）
        color_map = {'A':'#2ecc71','B':'#3498db','C':'#f1c40f','D':'#e67e22','F':'#e74c3c'}
        init_value = [{"Assessment_Grade": selected_val}] if selected_val != "All" else None
        sel_param = alt.selection_point(name="sel_assess", fields=["Assessment_Grade"], value=init_value)
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

    # ── 构建科目平均分条形图 ──
    def build_bar_subject(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        # 按科目计算平均分
        agg = df_in.groupby("SubjectName")["Score"].mean().reset_index()
        agg = agg.sort_values("Score", ascending=False)  # 降序排列
        init_value = [{"SubjectName": selected_val}] if selected_val != "All" else None
        sel_param = alt.selection_point(name="sel_subject", fields=["SubjectName"], value=init_value)
        # 条形图高亮逻辑：仅高亮当前选中科目，其余灰色
        color_condition = alt.condition(
            alt.datum["SubjectName"] == selected_val,  # 注意：这里用 datum 直接比较（因 selection_point 在 bar 图中行为不同）
            alt.value('#11998e'),
            alt.value('#ccc')
        ) if selected_val != "All" else alt.value('#11998e')  # 无筛选时全彩色
        bar = alt.Chart(agg).mark_bar().encode(
            x=alt.X("SubjectName", sort='-y', axis=alt.Axis(title=None)),  # 按 y 值（平均分）排序
            y=alt.Y("Score", axis=alt.Axis(title=None)),
            color=color_condition,
            tooltip=["SubjectName", alt.Tooltip("Score", format=".2f")]
        ).add_params(sel_param).properties(height=280, width='container')  # width='container' 适配父容器
        return bar.to_dict()

    # 关键：为每个图表提供“忽略自身筛选”的数据，以实现交叉高亮（cross-filtering）
    # 例如：点击年级时，科目图应显示该年级下各科平均分，但高亮逻辑基于全局筛选
    df_grade = filter_df(ignore_grade=True)      # 用于年级图：忽略年级筛选（显示全量年级分布）
    df_assess = filter_df(ignore_assess=True)    # 用于成绩图：忽略成绩筛选
    df_subject = filter_df(ignore_subj=True)     # 用于科目图：忽略科目筛选

    # 生成三个图表的 Vega 规范（spec）
    spec_grade = build_donut_grade(df_grade, sel_grade)
    spec_assess = build_donut_assess(df_assess, sel_assess)
    spec_subject = build_bar_subject(df_subject, sel_subj)

    # 构建筛选状态提示文本
    status_text = f"Filters: GradeLevel='{sel_grade}' | Subject='{sel_subj}' | Assessment Grade='{sel_assess}'"

    # 返回所有输出
    return k_avg, k_w, k_pass, k_perf, spec_grade, spec_assess, spec_subject, status_text

# ==================== 5. 启动应用 ====================
if __name__ == "__main__":
    app.run(debug=True, port=8050)  # 启用调试模式，端口 8050