import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sqlite3
from datetime import datetime

# ==========================================
# ГОТОВЫЕ ДЕМО-КЕЙСЫ ДЛЯ ЖЮРИ
# ==========================================
DEMO_CASES = {
    "1": {
        "name": "Tech Startup (Высокий риск)",
        "initial_capital": 100000,
        "mu": 0.25,
        "sigma": 0.45,
        "operating_cost": 15000
    },
    "2": {
        "name": "Retail Shop (Средний риск)",
        "initial_capital": 50000,
        "mu": 0.08,
        "sigma": 0.18,
        "operating_cost": 5000
    },
    "3": {
        "name": "Manufacturing Plant (Низкий риск)",
        "initial_capital": 500000,
        "mu": 0.04,
        "sigma": 0.09,
        "operating_cost": 40000
    }
}

# ==============================================================================
# 1. ИНИЦИАЛИЗАЦИЯ СИСТЕМЫ И БАЗЫ ДАННЫХ (SQLite)
# ==============================================================================
def init_db():
    conn = sqlite3.connect('projects_vault.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            industry TEXT NOT NULL,
            competition TEXT NOT NULL,
            price REAL NOT NULL,
            variable_cost REAL NOT NULL,
            fixed_expenses REAL NOT NULL,
            start_capital REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

st.set_page_config(
    page_title="RiskPulse Q-Engine 2026",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #e9ecef; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ И ВАЛИДАТОРЫ
# ==============================================================================
def get_roi_warning(roi):
    if roi > 300:
        return "⚠️ КРИТИЧЕСКАЯ АНОМАЛИЯ: ROI выше 300% выглядит нереалистично. Проверь завышение цен или недооценку постоянных издержек."
    elif roi > 150:
        return "⚠️ ВНИМАНИЕ: Очень высокий ROI (>150%). Модель может быть переоптимизирована. Проверь объемы спроса."
    return None

def get_risk_recommendation(risk_score, roi, bankruptcy_prob):
    if risk_score > 70:
        return "🔴 **КРИТИЧЕСКИЙ УРОВЕНЬ:** Риск превышает 70%. Необходима жесткая оптимизация издержек или докапитализация."
    elif risk_score > 50:
        return "🟡 **ВЫСОКИЙ РИСК:** Рекомендуется снизить фиксированные расходы на 15-20% и сформировать подушку ликвидности."
    elif risk_score > 25:
        return "🟢 **УМЕРЕННЫЙ РИСК:** Модель устойчива. Требуется плановый мониторинг оборотного капитала."
    else:
        return "✅ **НИЗКИЙ РИСК:** Отличные показатели безопасности. Проект готов к масштабированию."

def normalize_risk_roi(roi, target=25, max_sustainable=80):
    if roi < 0: return 100  
    if roi < target: return 5 + 95 * (1 - (roi / target))
    if target <= roi <= max_sustainable: return 5  
    excess = roi - max_sustainable
    return min(100, 5 + (excess ** 1.2))

def calculate_risk_score(bankruptcy_prob, var_percent, margin_ratio, roi):
    base_risk = (bankruptcy_prob * 0.35) + (var_percent * 0.35) + (max(0, 100 - margin_ratio) * 0.15)
    roi_risk = normalize_risk_roi(roi)
    return min(100, max(0, (base_risk * 0.85) + (roi_risk * 0.15)))

# ==============================================================================
# 3. ИСПРАВЛЕННОЕ ЯДРО МОНТЕ-КАРЛО (РЕАЛИСТИЧНЫЕ ROI)
# ==============================================================================
@st.cache_data(ttl=3600)
def run_monte_carlo_institutional(data_dict, scenario, num_simulations=1000, months=12, demand_multiplier=1.0):
    """
    ИСПРАВЛЕННАЯ версия Монте-Карло:
    - Реалистичный расчёт капитала (начальный баланс = капитал, НЕ -капитал)
    - Правильный ROI: (конечный_капитал - начальный) / начальный
    """
    price = data_dict['price']
    var_cost = data_dict['variable_cost']
    fixed = data_dict['fixed_expenses']
    capital = data_dict['start_capital']
    industry = data_dict['industry']
    
    margin_per_unit = price - var_cost
    
    # Защита от нереалистичной маржи (не более 70% от цены)
    max_reasonable_margin = price * 0.7
    if margin_per_unit > max_reasonable_margin:
        margin_per_unit = max_reasonable_margin
    
    INDUSTRY_VOLATILITY = {
        'Технологии': [0.35, 0.15, 0.10],   
        'Ритейл': [0.18, 0.10, 0.05],
        'Производство': [0.12, 0.25, 0.08], 
        'Услуги': [0.22, 0.08, 0.04]
    }
    vols = INDUSTRY_VOLATILITY.get(industry, [0.25, 0.15, 0.10])
    
    # Реалистичный базовый спрос (ограниченный)
    industry_base = {'Технологии': 150, 'Ритейл': 300, 'Производство': 100, 'Услуги': 200}
    start_sales = industry_base.get(industry, 200) * demand_multiplier
    # Ограничиваем максимальный спрос (реалистично)
    start_sales = min(start_sales, 1000)

    drift = 0.03  
    if scenario == "Кризис 2026":
        margin_per_unit *= 0.7
        start_sales *= 0.75
        drift = -0.02
    elif scenario == "Агрессивный рост":
        margin_per_unit *= 1.1  # Снижено с 1.15 для реалистичности
        start_sales *= 1.1     # Снижено с 1.2
        drift = 0.05           # Снижено с 0.06

    corr_matrix = np.array([
        [1.0, -0.4],
        [-0.4, 1.0]
    ])
    cov_matrix = np.diag([vols[1], vols[2]]) @ corr_matrix @ np.diag([vols[1], vols[2]])

    all_paths = []
    bankruptcy_count = 0
    final_balances = []
    monthly_balances = {m: [] for m in range(1, months + 1)}
    ruin_by_month = np.zeros(months)

    for _ in range(num_simulations):
        # ИСПРАВЛЕНО: Начальный баланс = capital (НЕ -capital)
        balance = capital
        path = []
        is_bankrupt = False
        
        shocks = np.random.multivariate_normal(mean=[0, 0], cov=cov_matrix, size=months)
        current_sales = start_sales
        
        for m in range(1, months + 1):
            if is_bankrupt:
                path.append(np.nan)
                monthly_balances[m].append(np.nan)
                continue
            
            vol_demand = vols[0]
            rand_normal = np.random.normal()
            current_sales *= np.exp((drift - 0.5 * vol_demand**2) + vol_demand * rand_normal)
            sim_sales = max(5, int(current_sales))
            # Ограничиваем продажи реалистичным потолком
            sim_sales = min(sim_sales, 2000)
            
            cost_shock = shocks[m-1, 0]
            price_shock = shocks[m-1, 1]
            
            sim_margin = margin_per_unit * (1 + price_shock - cost_shock)
            sim_margin = np.clip(sim_margin, margin_per_unit * 0.5, margin_per_unit * 1.5)
            
            monthly_cf = (sim_sales * sim_margin) - fixed
            balance += monthly_cf
            
            if balance <= 0 and not is_bankrupt:
                is_bankrupt = True
                bankruptcy_count += 1
                ruin_by_month[m-1] += 1
                path.append(np.nan)
                monthly_balances[m].append(np.nan)
            else:
                path.append(balance)
                monthly_balances[m].append(balance)
                
        all_paths.append(path)
        final_balances.append(balance)
    
    # ИСПРАВЛЕНО: Правильный расчёт убытков
    final_balances_np = np.array(final_balances)
    losses = capital - final_balances_np  
    
    worst_5_percent_loss = np.percentile(losses, 95)
    var_95 = max(0.0, worst_5_percent_loss)
    var_percent = (var_95 / capital * 100) if capital > 0 else 100
    
    tail_losses = losses[losses >= worst_5_percent_loss]
    expected_shortfall = max(0.0, np.mean(tail_losses)) if len(tail_losses) > 0 else var_95
    
    return {
        'paths': all_paths,
        'final_balances': final_balances,
        'bankruptcy_prob': (bankruptcy_count / num_simulations) * 100,
        'var_95': var_95,
        'var_percent': var_percent,
        'expected_shortfall': expected_shortfall,
        'monthly_balances': monthly_balances,
        'ruin_by_month_pct': (ruin_by_month / num_simulations) * 100
    }

def generate_forecast_metrics(data, scenario, demand_multiplier=1.0, fast_mode=False):
    margin_per_unit = data['price'] - data['variable_cost']
    margin_ratio = (margin_per_unit / data['price'] * 100) if data['price'] > 0 else 0
    
    data_dict = {k: v for k, v in data.items() if k != 'name'}
    sim_count = 200 if fast_mode else 1000
    
    mc_results = run_monte_carlo_institutional(
        data_dict, scenario, num_simulations=sim_count, demand_multiplier=demand_multiplier
    )
    
    # ИСПРАВЛЕНО: Правильный расчёт ROI
    capital = data['start_capital']
    avg_final_balance = np.mean(mc_results['final_balances'])
    net_profit = avg_final_balance - capital
    roi = (net_profit / capital) * 100 if capital > 0 else 0
    # Ограничиваем ROI реалистичным значением (макс 300%)
    roi = min(roi, 300)
    
    rf_rate = 6.0
    final_balances_np = np.array(mc_results['final_balances'])
    all_sim_rois = ((final_balances_np - capital) / capital) * 100
    all_sim_rois = np.clip(all_sim_rois, -100, 300)
    
    total_std = np.std(all_sim_rois)
    sharpe_ratio = (roi - rf_rate) / total_std if total_std > 0 else 0
    sharpe_ratio = max(-2, min(5, sharpe_ratio))
    
    downside_returns = all_sim_rois[all_sim_rois < rf_rate]
    if len(downside_returns) > 0:
        downside_deviation = np.sqrt(np.mean((downside_returns - rf_rate) ** 2))
        sortino_ratio = (roi - rf_rate) / downside_deviation if downside_deviation > 0 else 0
    else:
        sortino_ratio = 9.99
    
    sortino_ratio = max(-2, min(10, sortino_ratio))
    
    risk_score = calculate_risk_score(
        mc_results['bankruptcy_prob'], mc_results['var_percent'], margin_ratio, roi
    )
    
    return {
        'break_even_units': data['fixed_expenses'] / margin_per_unit if margin_per_unit > 0 else float('inf'),
        'margin_ratio': margin_ratio,
        'bankruptcy_prob': mc_results['bankruptcy_prob'],
        'roi': roi,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'avg_profit': avg_final_balance,
        'risk_score': risk_score,
        'var_95': mc_results['var_95'],
        'var_percent': mc_results['var_percent'],
        'expected_shortfall': mc_results['expected_shortfall'],
        'mc_results': mc_results
    }

def calculate_tornado_sensitivity(data, scenario):
    base_metrics = generate_forecast_metrics(data, scenario, fast_mode=True)
    base_roi = base_metrics['roi']
    
    factors = {
        'Цена (-10%)': ('price', 0.9),
        'Спрос (-10%)': ('demand_multiplier', 0.9),
        'Пост. расходы (+10%)': ('fixed_expenses', 1.1),
        'Перем. издержки (+10%)': ('variable_cost', 1.1)
    }
    
    sensitivity_data = []
    for label, (param, modifier) in factors.items():
        test_data = data.copy()
        d_mult = 1.0
        if param == 'demand_multiplier':
            d_mult = modifier
        else:
            test_data[param] *= modifier
            
        test_metrics = generate_forecast_metrics(test_data, scenario, demand_multiplier=d_mult, fast_mode=True)
        roi_delta = test_metrics['roi'] - base_roi
        
        sensitivity_data.append({'Фактор риска': label, 'Влияние на ROI (%)': roi_delta})
        
    return pd.DataFrame(sensitivity_data).sort_values(by='Влияние на ROI (%)', ascending=True)

# ==============================================================================
# 4. ПОЛЬЗОВАТЕЛЬСКИЙ ИНТЕРФЕЙС STREAMLIT
# ==============================================================================
st.title("⚡ RiskPulse Q-Engine (Institutional Build 2026)")
st.caption("Аналитическая система стресс-тестирования бизнес-моделей методом Монте-Карло")

def get_safe_index(val, options, default=0):
    return options.index(val) if val in options else default

st.sidebar.header("🛠️ Параметры бизнес-модели")
db_action = st.sidebar.selectbox("Управление базой данных", ["Новый проект", "Загрузить из БД"])

db_loaded_data = None
if db_action == "Загрузить из БД":
    conn = sqlite3.connect('projects_vault.db')
    try:
        df_projects = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
        conn.close()
    except:
        df_projects = pd.DataFrame()
        conn.close()
    
    if not df_projects.empty:
        project_options = {f"{row['name']} ({row['created_at']})": row['id'] for _, row in df_projects.iterrows()}
        selected_project = st.sidebar.selectbox("Выберите проект", list(project_options.keys()))
        p_id = project_options[selected_project]
        db_loaded_data = df_projects[df_projects['id'] == p_id].iloc[0].to_dict()
        st.sidebar.success(f"Загружен: {db_loaded_data['name']}")
    else:
        st.sidebar.warning("База данных пуста.")

p_name = st.sidebar.text_input("Название проекта", value=db_loaded_data['name'] if db_loaded_data else "Project Nexus")

industries = ["Технологии", "Ритейл", "Производство", "Услуги"]
p_industry = st.sidebar.selectbox("Отрасль", industries, 
                                  index=get_safe_index(db_loaded_data.get('industry') if db_loaded_data else None, industries))

comps = ["Низкая", "Средняя", "Высокая"]
p_competition = st.sidebar.selectbox("Уровень конкуренции", comps,
                                     index=get_safe_index(db_loaded_data.get('competition') if db_loaded_data else None, comps, default=1))

st.sidebar.markdown("---")
st.sidebar.subheader("Финансовые метрики (в сомони)")
p_price = st.sidebar.number_input("Цена за единицу продукции", min_value=1.0, value=float(db_loaded_data.get('price', 150.0)) if db_loaded_data else 150.0)
p_var_cost = st.sidebar.number_input("Переменные издержки", min_value=0.0, value=float(db_loaded_data.get('variable_cost', 60.0)) if db_loaded_data else 60.0)
p_fixed = st.sidebar.number_input("Постоянные расходы", min_value=0.0, value=float(db_loaded_data.get('fixed_expenses', 12000.0)) if db_loaded_data else 12000.0)
p_capital = st.sidebar.number_input("Стартовый капитал", min_value=1000.0, value=float(db_loaded_data.get('start_capital', 50000.0)) if db_loaded_data else 50000.0)

data = {
    'name': p_name, 'industry': p_industry, 'competition': p_competition,
    'price': p_price, 'variable_cost': p_var_cost, 'fixed_expenses': p_fixed, 'start_capital': p_capital
}

if st.sidebar.button("💾 Сохранить модель в БД"):
    conn = sqlite3.connect('projects_vault.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (name, industry, competition, price, variable_cost, fixed_expenses, start_capital, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data['name'], data['industry'], data['competition'], data['price'], data['variable_cost'], data['fixed_expenses'], data['start_capital'], datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    st.sidebar.success("Проект успешно записан в SQLite!")

st.sidebar.markdown("---")
market_scenario = st.sidebar.radio("Сценарий макросреды", ["Базовый план", "Кризис 2026", "Агрессивный рост"])

tab_dash, tab_monte = st.tabs(["📊 Аналитический дашборд", "🎲 Моделирование Монте-Карло (Bloomberg Cone)"])

metrics = generate_forecast_metrics(data, market_scenario)

with tab_dash:
    p_bank = metrics['bankruptcy_prob']
    sharpe = metrics['sharpe_ratio']
    
    if p_bank > 25.0 or sharpe < 0.4:
        verdict_text = "🚨 CRITICAL FAILURE RISK (Крайне опасно)"
        verdict_color = "red"
        verdict_desc = "Модель демонстрирует критическую нехватку ликвидности. Квантильные хвосты убытков (VaR) пробивают защитный капитал. Инвестиции не рекомендуются."
    elif p_bank > 5.0 or sharpe < 1.2:
        verdict_text = "🟡 MODERATE RISK (Требует оптимизации)"
        verdict_color = "orange"
        verdict_desc = "Бизнес имеет жизнеспособное математическое ожидание, но уязвим к макроэкономическим шокам спроса. Необходим резервный буфер."
    else:
        verdict_text = "🟢 SAFE TO SCALE (Инвестиционный класс)"
        verdict_color = "green"
        verdict_desc = "Высокая маржинальная прочность. Движок подтверждает устойчивость распределения к ковариационным шокам. Проект готов к масштабированию."

    st.markdown(f"""
        <div style="background-color: rgba(0,0,0,0.03); padding: 20px; border-left: 6px solid {verdict_color}; border-radius: 5px; margin-bottom: 25px;">
            <h3 style="margin: 0; color: {verdict_color}; font-size: 24px;">{verdict_text}</h3>
            <p style="margin: 10px 0 0 0; color: #555; font-size: 15px;"><b>АНАЛИЗ РИСК-СИСТЕМЫ:</b> {verdict_desc}</p>
        </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Интегральный Риск-Скоринг", f"{metrics['risk_score']:.1f} / 100", help="Общий индекс уязвимости системы")
    with c2:
        st.metric("Ожидаемый ROI", f"{metrics['roi']:.1f}%", help="Рентабельность капитала")
    with c3:
        st.metric("Коэффициент Шарпа", f"{sharpe:.2f}", help="Эффективность на единицу риска")
    with c4:
        st.metric("Коэффициент Сортино", f"{metrics['sortino_ratio']:.2f}", help="Защита от понижательного риска")
        
    st.markdown("### 🚨 Заключение системы комплаенса")
    roi_warn = get_roi_warning(metrics['roi'])
    if roi_warn:
        st.warning(roi_warn)
    st.info(get_risk_recommendation(metrics['risk_score'], metrics['roi'], metrics['bankruptcy_prob']))

    col_graph1, col_graph2 = st.columns(2)
    
    with col_graph1:
        st.subheader("🕸️ Профиль уязвимостей (Risk Radar)")
        categories = ['Риск Дефолта', 'Квантильный Риск (VaR)', 'Низкая Маржинальность', 'Аномальный ROI']
        
        r_bankruptcy = metrics['bankruptcy_prob']
        r_var = metrics['var_percent']
        r_margin = max(0, 100 - metrics['margin_ratio'])
        r_roi = normalize_risk_roi(metrics['roi'])
        
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=[r_bankruptcy, r_var, r_margin, r_roi],
            theta=categories,
            fill='toself',
            name=data['name'],
            line_color='#dc3545'
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=False, height=350, margin=dict(t=20, b=20, l=20, r=20)
        )
        st.plotly_chart(fig_radar, use_container_width=True)

    with col_graph2:
        st.subheader("🌪️ Чувствительность модели (Tornado Chart)")
        df_tornado = calculate_tornado_sensitivity(data, market_scenario)
        
        fig_tornado = px.bar(
            df_tornado, x='Влияние на ROI (%)', y='Фактор риска',
            orientation='h', text='Влияние на ROI (%)',
            color='Влияние на ROI (%)', color_continuous_scale='Reds_r'
        )
        fig_tornado.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_tornado.update_layout(
            height=320, xaxis_title="Сдвиг ROI (Процентные пункты)",
            yaxis_title="", template='plotly_white', showlegend=False
        )
        st.plotly_chart(fig_tornado, use_container_width=True)

with tab_monte:
    st.subheader("🏛️ Квантильный конус распределения капитала (Bloomberg Cone)")
    
    mc_res = metrics['mc_results']
    paths = np.array(mc_res['paths'])
    months_range = [f"Мес {i}" for i in range(1, 13)]
    
    p5 = np.nanpercentile(paths, 5, axis=0)
    p25 = np.nanpercentile(paths, 25, axis=0)
    p50 = np.nanpercentile(paths, 50, axis=0)
    p75 = np.nanpercentile(paths, 75, axis=0)
    p95 = np.nanpercentile(paths, 95, axis=0)

    fig_cone = go.Figure()
    fig_cone.add_trace(go.Scatter(x=months_range, y=p95, mode='lines', line=dict(color='rgba(40, 167, 69, 0.05)'), showlegend=False))
    fig_cone.add_trace(go.Scatter(x=months_range, y=p75, mode='lines', fill='tonexty', fillcolor='rgba(40, 167, 69, 0.12)', line=dict(width=0), name='Зона оптимистичного роста (75%-95%)'))
    fig_cone.add_trace(go.Scatter(x=months_range, y=p50, mode='lines', fill='tonexty', fillcolor='rgba(0, 123, 255, 0.15)', line=dict(width=0), name='Ожидаемый тренд роста (50%-75%)'))
    fig_cone.add_trace(go.Scatter(x=months_range, y=p25, mode='lines', fill='tonexty', fillcolor='rgba(255, 193, 7, 0.15)', line=dict(width=0), name='Зона умеренной стагнации (25%-50%)'))
    fig_cone.add_trace(go.Scatter(x=months_range, y=p5, mode='lines', fill='tonexty', fillcolor='rgba(220, 53, 69, 0.15)', line=dict(width=0), name='Зона высокого риска (5%-25%)'))

    fig_cone.add_trace(go.Scatter(
        x=months_range, y=p50, mode='lines+markers',
        line=dict(color='#007bff', width=3.5), name='Медианный сценарий'
    ))
    
    fig_cone.update_layout(
        template='plotly_white', height=480,
        xaxis_title="Горизонт планирования",
        yaxis_title="Свободный кэш на расчетном счету (сомони)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_cone, use_container_width=True)
    
    st.markdown("### 📊 Квантильные параметры устойчивости капитала")
    col_q1, col_q2, col_q3 = st.columns(3)
    
    with col_q1:
        st.metric(
            label="Вероятность дефолта (Def. Prob.)", 
            value=f"{mc_res['bankruptcy_prob']:.1f}%",
            delta="Критично!" if mc_res['bankruptcy_prob'] > 15 else "Безопасно",
            delta_color="inverse"
        )
    with col_q2:
        st.metric(
            label="95% Value at Risk (VaR)", 
            value=f"{mc_res['var_95']:.2f} сомони",
            delta=f"{mc_res['var_percent']:.1f}% капитала",
            delta_color="inverse"
        )
    with col_q3:
        st.metric(
            label="95% Expected Shortfall (ES / CVaR)", 
            value=f"{mc_res['expected_shortfall']:.2f} сомони"
        )


