import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sqlite3
from datetime import datetime

# ==========================================
# КОНФИГУРАЦИЯ СТРАНИЦЫ
# ==========================================
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

# ==========================================
# ИНИЦИАЛИЗАЦИЯ БД
# ==========================================
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

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def get_roi_warning(roi):
    if roi > 80:
        return "⚠️ ВНИМАНИЕ: Очень высокий ROI (>80%). Проверьте реалистичность допущений."
    elif roi < 0:
        return "🔴 КРИТИЧЕСКИ: Отрицательный ROI. Проект убыточен."
    return None

def get_risk_recommendation(risk_score, roi, bankruptcy_prob):
    if risk_score > 70:
        return "🔴 **КРИТИЧЕСКИЙ УРОВЕНЬ:** Риск превышает 70%. Необходима оптимизация издержек."
    elif risk_score > 50:
        return "🟡 **ВЫСОКИЙ РИСК:** Рекомендуется снизить фиксированные расходы."
    elif risk_score > 25:
        return "🟢 **УМЕРЕННЫЙ РИСК:** Модель устойчива. Требуется мониторинг."
    else:
        return "✅ **НИЗКИЙ РИСК:** Проект готов к масштабированию."

def calculate_risk_score(bankruptcy_prob, var_percent, margin_ratio, roi):
    # Нормализуем компоненты от 0 до 100
    risk_bankruptcy = min(100, bankruptcy_prob * 1.5)
    risk_var = min(100, var_percent * 1.2)
    risk_margin = max(0, 100 - margin_ratio)
    
    # ROI > 80% тоже считается риском (аномальная доходность)
    risk_roi = max(0, min(100, (roi - 80) * 2)) if roi > 80 else 0
    
    weighted_risk = (risk_bankruptcy * 0.4 + risk_var * 0.3 + risk_margin * 0.2 + risk_roi * 0.1)
    return min(100, weighted_risk)

# ==========================================
# РЕАЛИСТИЧНЫЕ ОГРАНИЧЕНИЯ РЫНКА
# ==========================================
def get_market_cap(industry):
    """Максимальный ежемесячный спрос по отраслям"""
    caps = {
        'Технологии': 500,
        'Ритейл': 2000,
        'Производство': 1000,
        'Услуги': 800
    }
    return caps.get(industry, 500)

def get_base_demand(industry, competition):
    """Базовый спрос с учётом конкуренции"""
    base = {
        'Технологии': 150,
        'Ритейл': 400,
        'Производство': 100,
        'Услуги': 250
    }
    demand = base.get(industry, 150)
    
    # Конкуренция снижает спрос
    competition_factors = {'Низкая': 1.0, 'Средняя': 0.7, 'Высокая': 0.4}
    return demand * competition_factors.get(competition, 0.7)

# ==========================================
# МОНТЕ-КАРЛО (ИСПРАВЛЕННЫЙ)
# ==========================================
@st.cache_data(ttl=3600)
def run_monte_carlo(data_dict, scenario, num_sims=1000, months=12):
    price = data_dict['price']
    var_cost = data_dict['variable_cost']
    fixed = data_dict['fixed_expenses']
    capital = data_dict['start_capital']
    industry = data_dict['industry']
    competition = data_dict['competition']
    
    margin = price - var_cost
    if margin <= 0:
        return {
            'paths': [[-capital] * months for _ in range(num_sims)],
            'final_balances': [-capital] * num_sims,
            'bankruptcy_prob': 100.0,
            'var_95': capital,
            'var_percent': 100,
            'expected_shortfall': capital
        }
    
    base_demand = get_base_demand(industry, competition)
    market_cap = get_market_cap(industry)
    
    # Волатильность по отраслям
    volatility = {
        'Технологии': 0.35,
        'Ритейл': 0.20,
        'Производство': 0.15,
        'Услуги': 0.18
    }
    vol = volatility.get(industry, 0.20)
    
    # Сценарии
    scenario_mult = 1.0
    if scenario == "Кризис 2026":
        scenario_mult = 0.6
        margin *= 0.85
    elif scenario == "Агрессивный рост":
        scenario_mult = 1.3
        margin *= 1.1
    
    all_paths = []
    final_balances = []
    bankruptcy_count = 0
    
    for _ in range(num_sims):
        balance = -capital
        path = []
        bankrupt = False
        
        current_demand = base_demand * scenario_mult
        
        for month in range(months):
            if bankrupt:
                path.append(np.nan)
                continue
            
            # Случайные колебания спроса
            shock = np.random.normal(0, vol)
            current_demand = current_demand * (1 + shock * 0.3)
            current_demand = max(5, min(market_cap, current_demand))
            
            # Случайные колебания маржи
            margin_shock = np.random.normal(0, 0.08)
            actual_margin = max(margin * 0.5, margin * (1 + margin_shock))
            
            revenue = current_demand * price
            costs = current_demand * var_cost + fixed
            monthly_profit = revenue - costs
            
            balance += monthly_profit
            path.append(balance)
            
            if balance <= 0 and not bankrupt:
                bankrupt = True
                bankruptcy_count += 1
        
        all_paths.append(path)
        final_balances.append(balance)
    
    final_balances_np = np.array(final_balances)
    losses = capital - final_balances_np
    
    var_95 = np.percentile(losses, 95) if len(losses) > 0 else capital
    var_95 = max(0, var_95)
    var_percent = (var_95 / capital * 100) if capital > 0 else 100
    
    tail_losses = losses[losses >= var_95]
    expected_shortfall = np.mean(tail_losses) if len(tail_losses) > 0 else var_95
    
    return {
        'paths': all_paths,
        'final_balances': final_balances,
        'bankruptcy_prob': (bankruptcy_count / num_sims) * 100,
        'var_95': var_95,
        'var_percent': var_percent,
        'expected_shortfall': expected_shortfall
    }

# ==========================================
# РАСЧЁТ МЕТРИК
# ==========================================
def calculate_metrics(data, scenario, fast_mode=False):
    margin = data['price'] - data['variable_cost']
    margin_ratio = (margin / data['price'] * 100) if data['price'] > 0 else 0
    
    sims = 200 if fast_mode else 1000
    mc = run_monte_carlo(data, scenario, num_sims=sims)
    
    capital = data['start_capital']
    avg_final = np.mean(mc['final_balances'])
    
    # ПРАВИЛЬНЫЙ ROI: (конечный_капитал - начальный_капитал) / начальный_капитал * 100
    # Баланс начинается с -capital, поэтому конечный баланс = -capital + прибыль
    # Значит реальная прибыль = avg_final + capital
    actual_profit = avg_final + capital
    roi = (actual_profit / capital * 100) if capital > 0 else 0
    roi = max(-100, min(200, roi))  # Ограничиваем ROI для адекватности
    
    # Коэффициенты
    all_profits = np.array(mc['final_balances']) + capital
    all_rois = (all_profits / capital * 100) if capital > 0 else np.zeros_like(all_profits)
    
    roi_std = np.std(all_rois)
    risk_free = 5.0
    sharpe = (roi - risk_free) / roi_std if roi_std > 0 else 0
    
    downside = all_rois[all_rois < risk_free]
    if len(downside) > 0:
        downside_std = np.std(downside - risk_free)
        sortino = (roi - risk_free) / downside_std if downside_std > 0 else 0
    else:
        sortino = 9.99
    
    risk_score = calculate_risk_score(
        mc['bankruptcy_prob'], 
        mc['var_percent'], 
        margin_ratio, 
        roi
    )
    
    return {
        'margin_ratio': margin_ratio,
        'break_even': data['fixed_expenses'] / margin if margin > 0 else float('inf'),
        'bankruptcy_prob': mc['bankruptcy_prob'],
        'roi': roi,
        'sharpe': sharpe,
        'sortino': sortino,
        'risk_score': risk_score,
        'var_95': mc['var_95'],
        'var_percent': mc['var_percent'],
        'expected_shortfall': mc['expected_shortfall'],
        'mc_results': mc,
        'avg_final_balance': avg_final
    }

# ==========================================
# TORNADO АНАЛИЗ
# ==========================================
def tornado_sensitivity(data, scenario):
    base = calculate_metrics(data, scenario, fast_mode=True)
    base_roi = base['roi']
    
    factors = {
        'Цена (-10%)': ('price', 0.9),
        'Спрос (-10%)': ('demand', 0.9),
        'Пост. расходы (+10%)': ('fixed', 1.1),
        'Перем. издержки (+10%)': ('var', 1.1)
    }
    
    results = []
    for label, (param, mod) in factors.items():
        test_data = data.copy()
        if param == 'price':
            test_data['price'] *= mod
        elif param == 'var':
            test_data['variable_cost'] *= mod
        elif param == 'fixed':
            test_data['fixed_expenses'] *= mod
        elif param == 'demand':
            # Спрос моделируется через конкуренцию
            comp_mult = {'Низкая': 1.0, 'Средняя': 0.7, 'Высокая': 0.4}
            current = comp_mult[data['competition']]
            new_comp = [k for k, v in comp_mult.items() if abs(v - current * mod) < 0.01]
            if new_comp:
                test_data['competition'] = new_comp[0]
        
        test_metrics = calculate_metrics(test_data, scenario, fast_mode=True)
        delta = test_metrics['roi'] - base_roi
        results.append({'Фактор': label, 'Влияние (%)': delta})
    
    return pd.DataFrame(results).sort_values('Влияние (%)', ascending=True)

# ==========================================
# UI
# ==========================================
st.title("⚡ RiskPulse Q-Engine 2026")
st.caption("Реалистичное стресс-тестирование бизнес-моделей методом Монте-Карло")

# Sidebar
st.sidebar.header("🛠️ Параметры проекта")

def safe_index(val, options, default=0):
    return options.index(val) if val in options else default

p_name = st.sidebar.text_input("Название", value="Мой проект")

industries = ["Технологии", "Ритейл", "Производство", "Услуги"]
p_industry = st.sidebar.selectbox("Отрасль", industries)

competitions = ["Низкая", "Средняя", "Высокая"]
p_competition = st.sidebar.selectbox("Конкуренция", competitions, 
                                      help="Низкая = больше клиентов, Высокая = меньше клиентов")

st.sidebar.markdown("---")
st.sidebar.subheader("💰 Финансы (сомони)")

p_price = st.sidebar.number_input("Цена за единицу", min_value=10.0, value=200.0)
p_var = st.sidebar.number_input("Переменные издержки", min_value=0.0, value=100.0)
p_fixed = st.sidebar.number_input("Постоянные расходы/мес", min_value=0.0, value=20000.0)
p_capital = st.sidebar.number_input("Стартовый капитал", min_value=5000.0, value=100000.0)

# Валидация маржи
if p_price - p_var <= 0:
    st.sidebar.error("❌ Цена должна быть выше переменных издержек!")

data = {
    'name': p_name,
    'industry': p_industry,
    'competition': p_competition,
    'price': p_price,
    'variable_cost': p_var,
    'fixed_expenses': p_fixed,
    'start_capital': p_capital
}

# Сохранение
if st.sidebar.button("💾 Сохранить в БД"):
    conn = sqlite3.connect('projects_vault.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (name, industry, competition, price, variable_cost, fixed_expenses, start_capital, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (p_name, p_industry, p_competition, p_price, p_var, p_fixed, p_capital, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    st.sidebar.success("✅ Сохранено!")

# Загрузка
if st.sidebar.button("📂 Загрузить последний"):
    conn = sqlite3.connect('projects_vault.db')
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    if not df.empty:
        row = df.iloc[0]
        p_name = row['name']
        p_industry = row['industry']
        p_competition = row['competition']
        p_price = row['price']
        p_var = row['variable_cost']
        p_fixed = row['fixed_expenses']
        p_capital = row['start_capital']
        st.rerun()

st.sidebar.markdown("---")
scenario = st.sidebar.radio("Макросценарий", ["Базовый", "Кризис 2026", "Агрессивный рост"])

# Расчёт
if p_price - p_var <= 0:
    st.error("❌ Исправьте ценообразование: цена должна быть выше переменных издержек")
    st.stop()

metrics = calculate_metrics(data, scenario)

# ==========================================
# ДАШБОРД
# ==========================================
tab1, tab2 = st.tabs(["📊 Дашборд", "🎲 Monte-Carlo"])

with tab1:
    # Вердикт
    if metrics['bankruptcy_prob'] > 25 or metrics['roi'] < 0:
        verdict = "🚨 HIGH RISK"
        color = "red"
        desc = "Высокий риск банкротства или отрицательная доходность. Требуется реструктуризация."
    elif metrics['bankruptcy_prob'] > 10 or metrics['sharpe'] < 0.8:
        verdict = "🟡 MODERATE RISK"
        color = "orange"
        desc = "Умеренный риск. Рекомендуется создать резервный фонд."
    else:
        verdict = "🟢 INVESTMENT GRADE"
        color = "green"
        desc = "Низкий риск, положительная доходность. Проект готов к инвестициям."
    
    st.markdown(f"""
        <div style="background:#f8f9fa; padding:20px; border-left:6px solid {color}; border-radius:8px; margin-bottom:20px">
            <h3 style="margin:0; color:{color}">{verdict}</h3>
            <p style="margin:10px 0 0 0">{desc}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Метрики
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Риск-скоринг", f"{metrics['risk_score']:.0f} / 100")
    with c2:
        st.metric("ROI", f"{metrics['roi']:.1f}%")
    with c3:
        st.metric("Sharpe", f"{metrics['sharpe']:.2f}")
    with c4:
        st.metric("Sortino", f"{metrics['sortino']:.2f}")
    
    # Предупреждения
    warn = get_roi_warning(metrics['roi'])
    if warn:
        st.warning(warn)
    
    st.info(get_risk_recommendation(metrics['risk_score'], metrics['roi'], metrics['bankruptcy_prob']))
    
    # Графики
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        st.subheader("🎯 Чувствительность")
        df_tornado = tornado_sensitivity(data, scenario)
        fig = px.bar(df_tornado, x='Влияние (%)', y='Фактор', orientation='h', text='Влияние (%)')
        fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with col_g2:
        st.subheader("📈 Безубыточность")
        margin = p_price - p_var
        if margin > 0:
            be = p_fixed / margin
            st.metric("Точка безубыточности (ед/мес)", f"{be:.0f}")
            
            # График безубыточности
            units = np.linspace(0, be * 2, 50)
            revenue = units * p_price
            costs = p_fixed + units * p_var
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=units, y=revenue, name="Выручка", line=dict(color='green')))
            fig.add_trace(go.Scatter(x=units, y=costs, name="Затраты", line=dict(color='red')))
            fig.add_vline(x=be, line_dash="dash", line_color="blue")
            fig.update_layout(height=300, xaxis_title="Единиц", yaxis_title="Сомони")
            st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("🏛️ Конус распределения капитала")
    
    mc = metrics['mc_results']
    paths = np.array(mc['paths'])
    months = [f"Мес {i+1}" for i in range(12)]
    
    # Квантили
    p5 = np.nanpercentile(paths, 5, axis=0)
    p25 = np.nanpercentile(paths, 25, axis=0)
    p50 = np.nanpercentile(paths, 50, axis=0)
    p75 = np.nanpercentile(paths, 75, axis=0)
    p95 = np.nanpercentile(paths, 95, axis=0)
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=months, y=p95, fill=None, line=dict(color='rgba(0,0,0,0)')))
    fig.add_trace(go.Scatter(x=months, y=p75, fill='tonexty', fillcolor='rgba(0,200,0,0.1)', line=dict(width=0), name='Оптимистичный'))
    fig.add_trace(go.Scatter(x=months, y=p50, fill='tonexty', fillcolor='rgba(0,100,255,0.15)', line=dict(width=2, color='blue'), name='Медиана'))
    fig.add_trace(go.Scatter(x=months, y=p25, fill='tonexty', fillcolor='rgba(255,150,0,0.15)', line=dict(width=0), name='Пессимистичный'))
    fig.add_trace(go.Scatter(x=months, y=p5, fill='tonexty', fillcolor='rgba(255,0,0,0.15)', line=dict(width=0), name='Критический'))
    
    fig.update_layout(
        height=450,
        xaxis_title="Месяц",
        yaxis_title="Баланс (сомони)",
        template='plotly_white'
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Риск-метрики
    st.markdown("### 📊 Квантильные риски")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Вероятность дефолта", f"{metrics['bankruptcy_prob']:.1f}%")
    with c2:
        st.metric("95% VaR", f"{metrics['var_95']:.0f} сомони")
    with c3:
        st.metric("95% CVaR (ES)", f"{metrics['expected_shortfall']:.0f} сомони")
    
    # Дополнительно: распределение ROI
    st.subheader("📊 Распределение ROI (1000 симуляций)")
    final_balances = np.array(mc['final_balances'])
    rois = ((final_balances + p_capital) / p_capital) * 100
    rois = np.clip(rois, -100, 200)
    
    fig = px.histogram(rois, nbins=30, title="Распределение доходности")
    fig.add_vline(x=metrics['roi'], line_dash="dash", line_color="red", annotation_text="Средний ROI")
    fig.update_layout(xaxis_title="ROI (%)", yaxis_title="Частота", height=350)
    st.plotly_chart(fig, use_container_width=True)
