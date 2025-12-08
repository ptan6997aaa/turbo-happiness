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



# ==================== 5. 启动应用 ====================
if __name__ == "__main__":
    app.run(debug=True, port=8050)  # 启用调试模式，端口 8050