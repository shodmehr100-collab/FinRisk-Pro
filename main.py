import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import sqlite3
from datetime import datetime

# Фиксация случайных чисел для стабильности интерфейса
np.random.seed(42)

# -------------------------- НАСТРОЙКА СТРАНИЦЫ --------------------------
st.set_page_config(
    page_title="ФинРиск Аналитика PRO+",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------- UI/UX СТИЛЬ (CSS) --------------------------
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    h1, h2, h3 { color: #0f172a !important; font-family: 'Inter', sans-serif !important; font-weight: 700 !important; }
    .metric-card {
        background-color: #ffffff; padding: 20px; border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;
        text-align: center; transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); }
    .metric-label { font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 6px; }
    .metric-value { font-size: 24px; color: #0f172a; font-weight: 700; }
    .metric-status { font-size: 11px; margin-top: 4px; font-weight: 500; }
    .stSidebar { background-color: #0f172a !important; }
    .stSidebar .css-17eq0hr, .stSidebar .stHeading, .stSidebar p, .stSidebar label { color: #f1f5f9 !important; }
    .custom-divider { height: 2px; background: linear-gradient(90deg, #3b82f6 0%, #e2e8f0 100%); margin: 20px 0; }
    </style>
""", unsafe_allow_html=True)

# -------------------------- БАЗА ДАННЫХ (SQLite) --------------------------
def init_db():
    conn = sqlite3.connect('startups_pro.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, industry TEXT,
            start_capital REAL, fixed_expenses REAL, variable_cost REAL,
            price REAL, competition TEXT, scenario TEXT, date_created TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_project_to_db(data, scenario):
    conn = sqlite3.connect('startups_pro.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (name, industry, start_capital, fixed_expenses, variable_cost, price, competition, scenario, date_created)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data['name'], data['industry'], data['start_capital'], data['fixed_expenses'], data['variable_cost'], data['price'], data['competition'], scenario, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def load_projects_from_db():
    conn = sqlite3.connect('startups_pro.db')
    df = pd.read_sql_query("SELECT * FROM projects ORDER BY id DESC", conn)
    conn.close()
    return df

init_db()

# -------------------------- ИНИЦИАЛИЗАЦИЯ SESSION_STATE --------------------------
if 'company_data' not in st.session_state:
    st.session_state.company_data = {
        'name': 'КиберТех Инкопорейтед', 'industry': 'Технологии',
        'start_capital': 2000000, 'fixed_expenses': 150000,
        'variable_cost': 300, 'price': 1200, 'competition': 'Средняя'
    }
if 'page' not in st.session_state:
    st.session_state.page = "Проектирование"

# -------------------------- МАТЕМАТИЧЕСКИЙ АППАРАТ --------------------------
def calculate_base_metrics(data, scenario):
    price = data['price']
    var_cost = data['variable_cost']
    fixed = data['fixed_expenses']
    
    comp_map = {'Низкая': 1.0, 'Средняя': 0.85, 'Высокая': 0.65}
    comp_factor = comp_map[data['competition']]
    
    margin_per_unit = price - var_cost
    
    # Модификация маржи по сценариям
    if scenario == "Кризис 2026":
        margin_per_unit *= 0.7
    elif scenario == "Агрессивный рост":
        margin_per_unit *= 1.15
        
    margin_ratio = (margin_per_unit / price * 100) if price > 0 else 0
    break_even_units = (fixed / margin_per_unit) if margin_per_unit > 0 else float('inf')
    
    return margin_per_unit, margin_ratio, break_even_units, comp_factor

def run_monte_carlo(data, scenario, num_simulations=1000, months=12):
    """Симуляция Монте-Карло для анализа рисков банкротства"""
    margin_per_unit, _, fixed, comp_factor = calculate_base_metrics(data, scenario)
    capital = data['start_capital']
    
    industry_base = {'Технологии': 200, 'Ритейл': 500, 'Производство': 120, 'Услуги': 300}
    base_sales = industry_base.get(data['industry'], 200) * comp_factor
    
    if scenario == "Кризис 2026":
        base_sales *= 0.75
    elif scenario == "Агрессивный рост":
        base_sales *= 1.3

    all_simulation_paths = []
    bankruptcy_count = 0
    final_balances = []

    for _ in range(num_simulations):
        balance = -capital
        path = []
        is_bankrupt = False
        
        for m in range(1, months + 1):
            growth_factor = 1 / (1 + np.exp(-0.6 * (m - 3)))
            # Внедрение стохастического шума (Монте-Карло)
            simulated_sales = int(base_sales * growth_factor + np.random.normal(0, base_sales * 0.25))
            simulated_sales = max(simulated_sales, 5)
            
            monthly_profit = (simulated_sales * margin_per_unit) - fixed
            balance += monthly_profit
            path.append(balance)
            
            # Если накопленный убыток превысил стартовый капитал в процессе (баланс стал критическим)
            if balance < -capital * 2: 
                is_bankrupt = True
                
        if is_bankrupt:
            bankruptcy_count += 1
            
        all_simulation_paths.append(path)
        final_balances.append(balance)
        
    bankruptcy_prob = (bankruptcy_count / num_simulations) * 100
    return all_simulation_paths, final_balances, bankruptcy_prob

def generate_forecast_metrics(data, scenario):
    margin_per_unit, margin_ratio, break_even_units, _ = calculate_base_metrics(data, scenario)
    _, final_balances, bankruptcy_prob = run_monte_carlo(data, scenario)
    
    avg_final_profit = np.mean(final_balances)
    capital = data['start_capital']
    
    # Расчет ROI
    roi = (avg_final_profit / capital) * 100 if capital > 0 else 0
    
    # Расчет Cash Burn Rate и Runway (на основе первого месяца)
    expected_first_month_sales = 30 
    expected_revenue = expected_first_month_sales * margin_per_unit
    burn_rate = data['fixed_expenses'] - expected_revenue
    
    if burn_rate > 0:
        runway = capital / burn_rate
    else:
        runway = float('inf') # Компания сразу генерирует кэш
        
    return {
        'break_even_units': break_even_units,
        'margin_ratio': margin_ratio,
        'bankruptcy_prob': bankruptcy_prob,
        'roi': roi,
        'burn_rate': max(0, burn_rate),
        'runway': runway,
        'avg_profit': avg_final_profit
    }

# -------------------------- СИСТЕМНАЯ НАВИГАЦИЯ --------------------------
st.sidebar.markdown("<h2 style='text-align: center; color: white;'>🔥 FINRISK ENGINE</h2>", unsafe_allow_html=True)
st.sidebar.markdown("<div style='height:1px; background-color:#334155; margin-bottom:20px;'></div>", unsafe_allow_html=True)

st.session_state.page = st.sidebar.radio("НАВИГАЦИЯ СИСТЕМЫ:", ["Профиль компании", "Симуляция Монте-Карло", "Архив СУБД SQLite"])

st.sidebar.markdown("<div style='height:1px; background-color:#334155; margin-top:20px; margin-bottom:20px;'></div>", unsafe_allow_html=True)
st.sidebar.subheader("🌍 МАКРО-СЦЕНАРИЙ")
market_scenario = st.sidebar.selectbox("Выберите режим рынка:", ["Базовый сценарий", "Кризис 2026", "Агрессивный рост"])

# --- СТРАНИЦА 1: ВВОД ДАННЫХ ---
if st.session_state.page == "Профиль компании":
    st.title("🏢 Моделирование параметров предприятия")
    st.markdown("<div class='custom-divider'></div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2, gap="large")
    with col1:
        with st.container(border=True):
            st.markdown("<h3 style='margin-top:0;'>📋 Идентификация</h3>", unsafe_allow_html=True)
            name = st.text_input("Название стартапа", value=st.session_state.company_data['name'])
            industry = st.selectbox("Сектор рынка", ["Технологии", "Ритейл", "Производство", "Услуги"], index=["Технологии", "Ритейл", "Производство", "Услуги"].index(st.session_state.company_data['industry']))
            competition = st.radio("Уровень конкуренции", ["Низкая", "Средняя", "Высокая"], index=["Низкая", "Средняя", "Высокая"].index(st.session_state.company_data['competition']))

    with col2:
        with st.container(border=True):
            st.markdown("<h3 style='margin-top:0;'>💰 Финансовый каркас</h3>", unsafe_allow_html=True)
            start_capital = st.slider("Стартовый капитал (₽)", 100000, 10000000, int(st.session_state.company_data['start_capital']), step=50000)
            fixed_expenses = st.number_input("Постоянные расходы / мес (₽)", 10000, 2000000, int(st.session_state.company_data['fixed_expenses']), step=5000)
            variable_cost = st.number_input("Переменные издержки на ед. (₽)", 10, 10000, int(st.session_state.company_data['variable_cost']), step=10)
            price = st.number_input("Цена реализации единицы (₽)", 20, 50000, int(st.session_state.company_data['price']), step=10)

    st.session_state.company_data.update({
        'name': name, 'industry': industry, 'competition': competition,
        'start_capital': start_capital, 'fixed_expenses': fixed_expenses,
        'variable_cost': variable_cost, 'price': price
    })

    if st.button("💾 Записать текущую итерацию в репозиторий SQLite", use_container_width=True):
        if not name.strip():
            st.warning("Критично: Введите имя проекта.")
        else:
            save_project_to_db(st.session_state.company_data, market_scenario)
            st.success(f"Запись успешно добавлена в СУБД. Режим макросреды: {market_scenario}")

# --- СТРАНИЦА 2: МОНТЕ-КАРЛО И АНАЛИТИКА ---
elif st.session_state.page == "Симуляция Монте-Карло":
    st.title("🎲 Стохастический анализ рисков по методу Монте-Карло")
    st.markdown("<div class='custom-divider'></div>", unsafe_allow_html=True)
    
    data = st.session_state.company_data
    st.info(f"📊 Текущий режим симуляции: **{market_scenario}**")
    
    # Расчет расширенных метрик
    res = generate_forecast_metrics(data, market_scenario)
    paths, final_balances, prob_bankrupt = run_monte_carlo(data, market_scenario)
    
    # KPI Панель уровня МВА
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>Вероятность Дефолта</div>
            <div class='metric-value' style='color:{"#ef4444" if prob_bankrupt > 20 else "#10b981"};'>{prob_bankrupt:.1f}%</div>
            <div class='metric-status'>Риск банкротства</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        runway_text = f"{res['runway']:.1f} мес." if res['runway'] != float('inf') else "∞ (Кэш-позитив)"
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>Financial Runway</div>
            <div class='metric-value'>{runway_text}</div>
            <div class='metric-status' style='color:#3b82f6;'>Запас прочности кэша</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>Ожидаемый ROI</div>
            <div class='metric-value'>{res['roi']:.1f}%</div>
            <div class='metric-status' style='color:#10b981;'>Рентабельность инвест.</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class='metric-card'>
            <div class='metric-label'>Порог безубыточности</div>
            <div class='metric-value'>{res['break_even_units']:.0f} ед.</div>
            <div class='metric-status'>План продаж в месяц</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Визуализация 1000 траекторий Монте-Карло
    st.subheader("📉 Распределение 1000 случайных траекторий развития капитала")
    
    # Ограничим отрисовку до 50 линий для экономии памяти браузера, но на основе полной симуляции
    months_range = list(range(1, 13))
    plot_df = pd.DataFrame()
    for idx, path in enumerate(paths[:60]):
        df_path = pd.DataFrame({'Месяц': months_range, 'Капитал': path, 'Симуляция': f'Поток {idx}'})
        plot_df = pd.concat([plot_df, df_path])
        
    line_chart = alt.Chart(plot_df).mark_line(opacity=0.3, strokeWidth=1.5).encode(
        x='Месяц:O', y='Капитал:Q', color=alt.Color('Симуляция:N', legend=None)
    ).properties(height=400)
    
    zero_line = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='#ef4444', strokeWidth=2, strokeDash=[5,5]).encode(y='y')
    st.altair_chart(line_chart + zero_line, use_container_width=True)

    # 🤖 ЭКСПЕРТНАЯ СИСТЕМА (AI RECOMMENDATIONS)
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🤖 Автоматизированное заключение экспертной системы рисков")
    
    recs = []
    if prob_bankrupt > 25:
        recs.append("🔴 **КРИТИЧЕСКИЙ УРОВЕНЬ РИСКА:** Вероятность банкротства превышает критический порог в 25%. Требуется срочное увеличение стартового капитала либо сокращение постоянных костов (`fixed expenses`) минимум на 20%.")
    else:
        recs.append("🟢 **СТАБИЛЬНЫЙ ЗАПАС ПРОЧНОСТИ:** Модель устойчива к рыночным флуктуациям в рамках выбранного сценария.")
        
    if res['margin_ratio'] < 25:
        recs.append("⚠️ **НИЗКАЯ МАРЖИНАЛЬНОСТЬ:** Рентабельность единицы продукции критически мала. Система чувствительна к демпингу конкурентов. Рекомендуется пересмотреть ценообразование.")
        
    if res['runway'] != float('inf') and res['runway'] < 6:
        recs.append(f"❗ **ОПАСНОСТЬ CASH BURN:** Финансовый Runway составляет всего {res['runway']:.1f} мес. Стартап рискует умереть в кассовом разрыве на этапе выхода на рынок.")
        
    with st.container(border=True):
        for rec in recs:
            st.markdown(rec)
            
# --- СТРАНИЦА 3: БД ---
else:
    st.title("🗄️ Исторический лог моделей в СУБД")
    st.markdown("<div class='custom-divider'></div>", unsafe_allow_html=True)
    
    df_db = load_projects_from_db()
    if df_db.empty:
        st.info("Хранилище пусто.")
    else:
        st.dataframe(df_db, use_container_width=True)
