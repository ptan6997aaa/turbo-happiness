import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import dash_vega_components as dvc
import altair as alt
import pandas as pd
import json

# ==================== 1. 数据加载与预处理 ====================
# 请确保 Excel 文件在当前目录下
df_fact = pd.read_excel("FactPerformance.xlsx", sheet_name="Sheet1")
df_dimStu = pd.read_excel("DimStudents.xlsx", sheet_name="Sheet1")
df_dimCal = pd.read_excel("DimCalendar.xlsx", sheet_name="Date")
df_dimSub = pd.read_excel("DimSubjects.xlsx", sheet_name="DimSubjects")

# 构建分析宽表 
df = pd.merge(df_fact, df_dimStu[["StudentID", "GradeLevel"]], on="StudentID", how="left")
df = pd.merge(df, df_dimSub[["SubjectID", "SubjectName"]], on="SubjectID", how="left")

# 构造时间标签（用于前端展示）
df_dimCal["YearQuarterConcat"] = df_dimCal["Year"].astype(str) + "-" + df_dimCal["QuarterNumber"].apply(lambda x: f"{x:02d}")
df_dimCal["YearMonthConcat"] = df_dimCal["Year"].astype(str) + "-" + df_dimCal["Month"].apply(lambda x: f"{x:02d}")
df = pd.merge(df, df_dimCal[["DateKey", "YearQuarterConcat", "YearMonthConcat"]], on="DateKey", how="left")

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

    # Title Row
    dbc.Row([
        dbc.Col(html.H2("🎓 Student Performance Dashboard", className="fw-bold my-3"), width=9),
        dbc.Col(
            dbc.Button("↺ Reset All Filters", id="btn-reset", color="danger", outline=True, className="mt-4 w-100 shadow-sm"),
            width=3
        )
    ], className="mb-4 border-bottom pb-3"),

    # KPI Row
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Average Score"), html.H3(id="kpi-avg", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Weighted Avg"), html.H3(id="kpi-wavg", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Pass Rate"), html.H3(id="kpi-pass", className="fw-bold")]), style=KPI_STYLE), width=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Perfect Rate"), html.H3(id="kpi-perfect", className="fw-bold")]), style=KPI_STYLE), width=3),
    ], className="mb-4"),

    # Three Charts in One Row
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Student Count by Grade Level", className="fw-bold text-center"),
                dbc.CardBody(dvc.Vega(id="chart-grade", signalsToObserve=["sel_grade"], style={"height": "380px"}))
            ], className="shadow"),
            width=3
        ),
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Exam Count by Assessment Grade", className="fw-bold text-center"),
                dbc.CardBody(dvc.Vega(id="chart-assess", signalsToObserve=["sel_assess"], style={"height": "380px"}))
            ], className="shadow"),
            width=3
        ),
        dbc.Col(
            dbc.Card([
                dbc.CardHeader("Future Bar Chart", className="fw-bold text-center text-muted"),
                dbc.CardBody([
                    html.Div(
                        "Placeholder reserved for additional bar chart.",
                        className="d-flex justify-content-center align-items-center h-100 fw-light",
                        style={"height": "380px", "color": "#6c757d"}
                    )
                ])
            ], className="shadow"),
            width=6
        ),
    ], className="mb-4"),

    # Subject Chart (full width)
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardBody(dvc.Vega(id="chart-subject", signalsToObserve=["sel_subject"], style={'width': '100%'}))
        ], style={"box-shadow": "0 2px 4px rgba(0,0,0,0.05)", "border-radius": "8px"}), width=12),
    ], className="mb-4"),

    # Filter Status
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
        # Vega Handle: 有时候 Vega 返回的是对象，有时候是直接的值，取决于 Signal 定义
        # 在我们的 Vega spec 中，sel_subject 直接返回 SubjectName 字符串
        if isinstance(sel, dict) and key_name in sel:
             # Altair selection output
            if len(sel[key_name]) > 0:
                clicked = sel[key_name][0]
                if str(current_filter) != "All" and str(clicked) == str(current_filter):
                    return "All"
                return clicked
        elif isinstance(sel, str) or isinstance(sel, int) or isinstance(sel, float):
             # Raw Vega signal output (direct value)
             clicked = sel
             if str(current_filter) != "All" and str(clicked) == str(current_filter):
                return "All"
             return clicked
             
        return current_filter

    if trigger_id == 'chart-grade':
        new_grade = process_signal(sig_grade, 'sel_grade', 'GradeLevel', curr_grade)
        return new_grade, curr_subj, curr_assess
    
    # === 注意：Raw Vega 的 Signal 处理逻辑
    if trigger_id == 'chart-subject':
        # 在 Raw Vega 中，sel_subject 直接就是字符串值（例如 "Math"），不是字典
        new_subj = process_signal(sig_subj, 'sel_subject', None, curr_subj)
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

    # --- Donut Charts (保持 Altair 不变) ---
    def build_donut_grade(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        agg = df_in.groupby('GradeLevel')['StudentID'].nunique().reset_index()
        agg.columns = ['GradeLevel', 'TotalPlayers']
        grand_total = agg['TotalPlayers'].sum()
        agg['Share'] = agg['TotalPlayers'] / grand_total if grand_total > 0 else 0
        init_value = [{'GradeLevel': selected_val}] if selected_val != "All" else None
        sel = alt.selection_point(name='sel_grade', fields=['GradeLevel'], value=init_value, on='click', empty='none')
        color = alt.condition(sel, alt.Color('GradeLevel:N', sort='-color', legend=None), alt.value('#dddddd'))
        opacity = alt.condition(sel, alt.value(0.4), alt.value(0.9))
        donut = (
            alt.Chart(agg)
            .mark_arc(innerRadius=70, outerRadius=110, cornerRadius=5, padAngle=0.04, stroke='black', strokeWidth=1)
            .encode(
                theta=alt.Theta('Share:Q', stack=True),
                color=color,
                order=alt.Order('TotalPlayers:Q', sort='descending'),
                opacity=opacity,
                tooltip=[alt.Tooltip('GradeLevel:N'), alt.Tooltip('TotalPlayers:Q'), alt.Tooltip('Share:Q', format='.1%')],
            ).add_params(sel).properties(width=300, height=300)
        )
        return donut.to_dict()

    def build_donut_assess(df_in, selected_val):
        if df_in.empty:
            return alt.Chart(pd.DataFrame({'text': ['No Data']})).mark_text(size=20).encode(text='text:N').to_dict()
        counts = df_in["Assessment_Grade"].value_counts().reindex(['A','B','C','D','F'], fill_value=0).reset_index()
        counts.columns = ["Assessment_Grade", "TotalPlayers"]
        grand_total = counts['TotalPlayers'].sum()
        counts['Share'] = counts['TotalPlayers'] / grand_total if grand_total > 0 else 0
        color_map = {'A':'#2ecc71','B':'#3498db','C':'#f1c40f','D':'#e67e22','F':'#e74c3c'}
        init_value = [{"Assessment_Grade": selected_val}] if selected_val != "All" else None
        sel = alt.selection_point(name="sel_assess", fields=["Assessment_Grade"], value=init_value, on='click', empty='none')
        color = alt.condition(sel, alt.Color("Assessment_Grade:N", scale=alt.Scale(domain=['A','B','C','D','F'], range=list(color_map.values())), legend=None), alt.value('#dddddd'))
        opacity = alt.condition(sel, alt.value(0.4), alt.value(0.9))
        donut = (
            alt.Chart(counts)
            .mark_arc(innerRadius=70, outerRadius=110, cornerRadius=5, padAngle=0.04, stroke='black', strokeWidth=1)
            .encode(
                theta=alt.Theta("Share:Q", stack=True),
                color=color,
                order=alt.Order('TotalPlayers:Q', sort='descending'),
                opacity=opacity,
                tooltip=[alt.Tooltip('Assessment_Grade:N'), alt.Tooltip('TotalPlayers:Q'), alt.Tooltip('Share:Q', format='.1%')],
            ).add_params(sel).properties(width=300, height=300)
        )
        return donut.to_dict()

    def build_bar_subject(df_in, selected_val):
        # 1. 预处理数据以匹配 Vega 规范要求的字段名
        if df_in.empty:
            return {"$schema": "https://vega.github.io/schema/vega/v5.json", "marks": [{"type": "text", "encode": {"update": {"text": {"value": "No Data"}, "x": {"value": 100}, "y": {"value": 100}}}}]}

        df_agg = df_in.groupby("SubjectName")["Score"].mean().reset_index()
        df_agg.rename(columns={"Score": "Average of Score"}, inplace=True)
        
        data_values = df_agg.to_dict(orient="records")
        current_selection = selected_val if selected_val != "All" else None

        # 3. 嵌入 Raw Vega JSON (注意：null -> None, true -> True, false -> False)
        vega_spec = {
          "$schema": "https://vega.github.io/schema/vega/v6.json",
          "description": "Bar chart with average line for Subject Scores",
          "background": "white",
          "padding": 10,
          "width": 650, 
          "height": 350, 
          "autosize": {"type": "fit", "contains": "padding"}, 
          "title": {
            "text": "Subject Performance",
            "subtitle": ["Comparison of Average Score per Subject against the Overall Mean"],
            "anchor": "start",
            "fontSize": 16,
            "subtitleFontSize": 12,
            "subtitleColor": "gray",
            "offset": 20
          },
          "style": "cell",
          "data": [
            {
              "name": "dataset",
              "values": data_values 
            },
            {
              "name": "data_0",
              "source": "dataset",
              "transform": [
                {
                  "type": "joinaggregate",
                  "as": ["MeanScore", "MinScore", "MaxScore"],
                  "ops": ["mean", "min", "max"],
                  "fields": ["Average of Score", "Average of Score", "Average of Score"]
                },
                {
                  "type": "formula",
                  "expr": "datum.MinScore - 5",
                  "as": "YAxisBaseline"
                }
              ]
            },
            {
              "name": "data_1",
              "source": "data_0",
              "transform": [
                {"type": "filter", "expr": "isValid(datum[\"Average of Score\"]) && isFinite(+datum[\"Average of Score\"])"}
              ]
            },
            {
              "name": "data_2",
              "source": "data_0",
              "transform": [
                {"type": "filter", "expr": "isValid(datum[\"Average of Score\"]) && isFinite(+datum[\"Average of Score\"])"}
              ]
            },
            {
              "name": "data_3",
              "source": "data_0",
              "transform": [
                {"type": "filter", "expr": "isValid(datum[\"MeanScore\"]) && isFinite(+datum[\"MeanScore\"])"}
              ]
            },
            {
              "name": "data_4",
              "source": "data_0",
              "transform": [
                {
                  "type": "window",
                  "params": [None],  # <--- 修正这里: null -> None
                  "as": ["rowNum"],
                  "ops": ["row_number"],
                  "fields": [None],  # <--- 修正这里: null -> None
                  "sort": {"field": [], "order": []}
                },
                {"type": "filter", "expr": "datum.rowNum === 1"},
                {"type": "filter", "expr": "isValid(datum[\"MeanScore\"]) && isFinite(+datum[\"MeanScore\"])"}
              ]
            }
          ],
          "signals": [
            {
              "name": "hovered_subject",
              "value": None, # <--- 修正这里: null -> None
              "on": [
                {"events": "@layer_0_marks:mouseover", "update": "datum.SubjectName"},
                {"events": "@layer_0_marks:mouseout", "update": "null"} # 注意：引号内的字符串 "null" 是 Vega 表达式，不需要改
              ]
            },
            {
              "name": "sel_subject",
              "value": current_selection, 
              "on": [
                {
                  "events": "@layer_0_marks:click",
                  "update": "datum.SubjectName === sel_subject ? null : datum.SubjectName"
                },
                {
                  "events": "dblclick",
                  "update": "null"
                }
              ]
            }
          ],
          "marks": [
            # 模糊阴影层
            {
              "name": "layer_0_blur_shadow",
              "type": "rect",
              "clip": True, # <--- 修正这里: true -> True
              "style": ["bar"],
              "from": {"data": "data_1"},
              "encode": {
                "update": {
                  "x": {"scale": "x", "field": "SubjectName", "band": 0.2, "offset": 3},
                  "width": {"signal": "max(0.25, 0.6 * bandwidth('x')) + 2"},
                  "y": {"scale": "y", "field": "Average of Score", "offset": 3},
                  "y2": {"scale": "y", "field": "YAxisBaseline", "offset": 3},
                  "fill": {"value": "rgba(0, 0, 0, 0.15)"},
                  "opacity": [
                    {"test": "hovered_subject === datum.SubjectName", "value": 1},
                    {"value": 0}
                  ],
                  "cornerRadiusTopLeft": {"value": 15},
                  "cornerRadiusTopRight": {"value": 15}
                }
              }
            },
            # 主要阴影层
            {
              "name": "layer_0_main_shadow",
              "type": "rect",
              "clip": True,
              "style": ["bar"],
              "from": {"data": "data_1"},
              "encode": {
                "update": {
                  "x": {"scale": "x", "field": "SubjectName", "band": 0.2, "offset": 1},
                  "width": {"signal": "max(0.25, 0.6 * bandwidth('x'))"},
                  "y": {"scale": "y", "field": "Average of Score", "offset": 1},
                  "y2": {"scale": "y", "field": "YAxisBaseline", "offset": 1},
                  "fill": {"value": "rgba(0, 0, 0, 0.25)"},
                  "opacity": [
                    {"test": "hovered_subject === datum.SubjectName", "value": 1},
                    {"value": 0}
                  ],
                  "cornerRadiusTopLeft": {"value": 15},
                  "cornerRadiusTopRight": {"value": 15}
                }
              }
            },
            # 柱状图层
            {
              "name": "layer_0_marks",
              "type": "rect",
              "clip": True,
              "style": ["bar"],
              "from": {"data": "data_1"},
              "encode": {
                "update": {
                  "cursor": {"value": "pointer"},
                  "cornerRadiusTopLeft": {"value": 10},
                  "cornerRadiusTopRight": {"value": 10},
                  "fill": [
                    {
                      "test": "datum['Average of Score'] < datum.MeanScore",
                      "value": "#EF8354"
                    },
                    {
                      "value": "#2D3142"
                    }
                  ],
                  "fillOpacity": [
                    {"test": "hovered_subject === datum.SubjectName", "value": 1},
                    {"test": "sel_subject && datum.SubjectName !== sel_subject", "value": 0.2},
                    {"value": 0.9}
                  ],
                  "tooltip": {
                    "signal": "{\"Subject\": datum[\"SubjectName\"], \"Avg Score\": format(datum[\"Average of Score\"], \".1f\"), \"Overall Mean\": format(datum[\"MeanScore\"], \".1f\")}"
                  },
                  "x": {"scale": "x", "field": "SubjectName", "band": 0.2},
                  "width": {"signal": "max(0.25, 0.6 * bandwidth('x'))"},
                  "y": {"scale": "y", "field": "Average of Score"},
                  "y2": {"scale": "y", "field": "YAxisBaseline"}
                }
              }
            },
            # 平均参考线
            {
              "name": "layer_2_marks",
              "type": "rule",
              "style": ["rule"],
              "from": {"data": "data_3"},
              "encode": {
                "update": {
                  "strokeDash": {"value": [6, 4]},
                  "stroke": {"value": "#444"},
                  "x": {"field": {"group": "width"}},
                  "x2": {"value": 0},
                  "y": {"scale": "y", "field": "MeanScore"},
                  "strokeWidth": {"value": 2}
                }
              }
            },
            # 平均值标签
            {
              "name": "layer_3_marks",
              "type": "text",
              "style": ["text"],
              "from": {"data": "data_4"},
              "encode": {
                "update": {
                  "text": {"signal": "'Overall Avg ' + format(datum[\"MeanScore\"], \".1f\")"},
                  "align": {"value": "right"},
                  "dx": {"value": 0},
                  "dy": {"value": -8},
                  "fontSize": {"value": 12},
                  "fontWeight": {"value": "bold"},
                  "fill": {"value": "#444"},
                  "x": {"field": {"group": "width"}}, 
                  "y": {"scale": "y", "field": "MeanScore"},
                  "baseline": {"value": "middle"}
                }
              }
            }
          ],
          "scales": [
            {
              "name": "x",
              "type": "band",
              "domain": {
                "data": "data_1",
                "field": "SubjectName",
                "sort": {"field": "Average of Score", "op": "max", "order": "descending"}
              },
              "range": [0, {"signal": "width"}],
              "paddingInner": 0.1,
              "paddingOuter": 0.05
            },
            {
              "name": "y",
              "type": "linear",
              "domain": {
                  "fields": [
                      {"data": "data_1", "field": "Average of Score"},
                      {"data": "data_1", "field": "YAxisBaseline"}, 
                      {"data": "data_3", "field": "MeanScore"}
                  ]
              },
              "range": [{"signal": "height"}, 0],
              "nice": True, # <--- 修正这里: true -> True
              "zero": False # <--- 修正这里: false -> False
            }
          ],
          "axes": [
            {
              "scale": "y",
              "orient": "left",
              "grid": True, # <--- 修正这里
              "gridColor": "#DAD8D7",
              "gridOpacity": 0.5,
              "tickCount": {"signal": "ceil(height/40)"},
              "title": "Avg Score",
              "zindex": 0
            },
            {
              "scale": "x",
              "orient": "bottom",
              "labelAngle": 325,
              "labelAlign": "right",
              "zindex": 0
            }
          ],
          "config": {
            "axis": {"labelFontSize": 12, "titleFontSize": 14, "titlePadding": 10},
            "style": {"cell": {"stroke": "transparent"}}
          }
        }
        return vega_spec

    df_grade = filter_df(ignore_grade=True)
    df_assess = filter_df(ignore_assess=True)
    df_subject = filter_df(ignore_subj=True)

    spec_grade = build_donut_grade(df_grade, sel_grade)
    spec_assess = build_donut_assess(df_assess, sel_assess)
    spec_subject = build_bar_subject(df_subject, sel_subj) # 调用新的 Vega 构建函数

    status_text = f"Filters: GradeLevel='{sel_grade}' | Subject='{sel_subj}' | Assessment Grade='{sel_assess}'"
    return k_avg, k_w, k_pass, k_perf, spec_grade, spec_assess, spec_subject, status_text  

# ==================== 5. 启动应用 ====================
if __name__ == "__main__":
    app.run(debug=True, port=8050)