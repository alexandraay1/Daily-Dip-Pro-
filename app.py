import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 雙核戰略執行系統 V12.0", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 雙核戰略執行系統 V12.0")
        st.caption("含：戰術執行點位 (Entry/Target/Stop) + 機構透視 (FVG/OB)")
        password = st.text_input("請輸入通行密碼", type="password")
        if st.button("登入"):
            if password == "VIP888":
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
        st.stop()

check_password()

# --- 側邊欄 ---
st.sidebar.title("🎛️ 雙核控制台")
symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()
st.sidebar.markdown("---")
st.sidebar.info("""
**V12.0 新增功能：**
在「智能戰術」頁面新增自動交易計劃：
- 🎯 **Entry**: 建議入場價
- 💰 **Target**: 建議獲利價 (2R)
- 🚧 **Res**: 近期關鍵阻力
""")

# --- 3. 核心數據引擎 ---
@st.cache_data(ttl=3600)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- V9 指標 ---
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['EMA_150'] = ta.ema(df['Close'], length=150)
        df['EMA_200'] = ta.ema(df['Close'], length=200)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # SuperTrend
        st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        st_col = [c for c in st_data.columns if "SUPERT_" in c][0]
        st_dir = [c for c in st_data.columns if "SUPERTd_" in c][0]
        df['SuperTrend'] = st_data[st_col]
        df['Trend_Dir'] = st_data[st_dir]
        
        # WaveTrend
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        esa = ta.ema(tp, length=10)
        d = ta.ema((tp - esa).abs(), length=10)
        ci = (tp - esa) / (0.015 * d)
        df['WT1'] = ta.ema(ci, length=21)
        df['WT2'] = ta.sma(df['WT1'], length=4)
        
        # ADX
        adx = ta.adx(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx['ADX_14']
        
        # Volume
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']

        df['Body'] = abs(df['Close'] - df['Open'])
        
        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 戰術計算模組 (V12 新增：點位計算) ---
def generate_execution_plan(df):
    last = df.iloc[-1]
    close = last['Close']
    trend_dir = last['Trend_Dir']
    stop = last['SuperTrend']
    
    # 計算阻力位 (取過去 20 天最高價，如果是新高則用 1.05 倍)
    recent_high = df['High'].tail(20).max()
    if close >= recent_high:
        resistance = close * 1.05 # 突破新高，看高 5%
        res_desc = "新高突破預測"
    else:
        resistance = recent_high
        res_desc = "前波高點壓力"
        
    # 計算盈虧比 (Risk Reward Ratio)
    risk = abs(close - stop)
    
    if trend_dir == 1: # 多頭
        action = "🟢 做多 (BUY)"
        entry = close
        target = close + (risk * 2) # 目標設定為 2倍風險
        trend_status = "多頭趨勢"
    else: # 空頭
        action = "🔴 做空 (SELL)"
        entry = close
        target = close - (risk * 2)
        trend_status = "空頭趨勢"
        
    strength = "🔥 強勢" if last['ADX'] > 25 else "☁️ 震盪"
    
    return {
        "trend": trend_status,
        "strength": strength,
        "wt": last['WT1'],
        "action": action,
        "entry": entry,
        "target": target,
        "stop": stop,
        "resistance": resistance,
        "res_desc": res_desc
    }

def detect_retail_signals(df):
    signals = []
    start = max(0, len(df)-100)
    
    for i in range(start, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
        
        # VH 爆量
        if curr['Vol_Ratio'] >= 2.0:
            signals.append({"date": date, "price": curr['High'], "text": "🔥VH", "color": "red", "ay": -40})
        # 吞沒
        if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
            if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']:
                signals.append({"date": date, "price": curr['Low'], "text": "🐂吞沒", "color": "green", "ay": 40})
        # WT 鑽石
        if curr['WT1'] < -50 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
            signals.append({"date": date, "price": curr['Low'] - curr['ATR'], "text": "💎", "color": "cyan", "ay": 25})
            
    return signals

# --- 5. 機構計算模組 (SMC) ---
def calculate_smc_zones(df):
    fvgs = []
    obs = []
    start = max(0, len(df)-60)
    for i in range(start, len(df)):
        # FVG
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            fvgs.append({"type": "Bull", "top": df['Low'].iloc[i], "bottom": df['High'].iloc[i-2], "x0": df.index[i-1], "x1": df.index[-1]})
        if df['High'].iloc[i] < df['Low'].iloc[i-2] and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
            fvgs.append({"type": "Bear", "top": df['Low'].iloc[i-2], "bottom": df['High'].iloc[i], "x0": df.index[i-1], "x1": df.index[-1]})
            
    # OB
    for i in range(start, len(df)-2):
        if df['Low'].iloc[i] < df['Low'].iloc[i-1] and df['Low'].iloc[i] < df['Low'].iloc[i+1]:
            if df['Close'].iloc[i] < df['Open'].iloc[i]:
                if df['Close'].iloc[i+1] > df['High'].iloc[i] or df['Close'].iloc[i+2] > df['High'].iloc[i]:
                    obs.append({"type": "OB", "top": df['High'].iloc[i], "bottom": df['Low'].iloc[i], "x0": df.index[i], "x1": df.index[-1]})
    return fvgs, obs

# --- 主程式 UI ---
st.title(f"📊 {symbol} 雙核戰略執行系統 V12.0")
df = get_data(symbol)

if df is not None:
    
    tab_retail, tab_inst = st.tabs(["🚀 智能戰術 (執行點位)", "🏛️ 機構透視 (結構分析)"])
    
    # ==========================================
    # Tab 1: 智能戰術 (V12 升級版)
    # ==========================================
    with tab_retail:
        plan = generate_execution_plan(df)
        
        # --- 第一層：環境分析 ---
        st.caption("📡 戰場環境數據")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("市場趨勢", plan['trend'])
        e2.metric("趨勢強度 (ADX)", f"{df['ADX'].iloc[-1]:.1f}", plan['strength'])
        e3.metric("WaveTrend 動能", f"{plan['wt']:.1f}")
        e4.metric("操作方向建議", plan['action'], delta_color="off")
        
        st.divider()
        
        # --- 第二層：執行計劃 (新功能) ---
        st.subheader("📋 交易執行計劃 (Trade Execution)")
        p1, p2, p3, p4 = st.columns(4)
        
        p1.metric("🎯 參與買入價 (Entry)", f"${plan['entry']:.2f}", help="建議現價或回調時入場")
        p2.metric("💰 賣出獲利價 (Target)", f"${plan['target']:.2f}", help="基於 1:2 風險回報比推算")
        p3.metric("🚧 關鍵阻力位 (Res)", f"${plan['resistance']:.2f}", help=plan['res_desc'])
        p4.metric("🛡️ 智能止損 (Stop)", f"${plan['stop']:.2f}", delta_color="inverse", help="SuperTrend 動態止損")
        
        st.info(f"💡 **戰術邏輯**：當價格突破 **${plan['entry']:.2f}**，首要目標看 **${plan['target']:.2f}**。若跌破 **${plan['stop']:.2f}** 則止損離場。上方最大壓力在 **${plan['resistance']:.2f}**。")

        # --- 圖表 ---
        fig_v9 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        fig_v9.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_150'], line=dict(width=1, color='rgba(0,128,0,0.5)'), name="EMA 150"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(width=1, color='rgba(128,0,0,0.5)'), fill='tonexty', fillcolor='rgba(128,128,128,0.1)', name="EMA 雲"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], mode='lines', line=dict(color='orange', width=2, dash='dash'), name="SuperTrend"), row=1, col=1)

        # 畫出阻力線和目標線
        fig_v9.add_hline(y=plan['resistance'], line_dash="dot", line_color="red", annotation_text="Res", row=1, col=1)
        fig_v9.add_hline(y=plan['target'], line_dash="dot", line_color="green", annotation_text="Target", row=1, col=1)

        signals = detect_retail_signals(df)
        annotations_v9 = []
        for s in signals:
            annotations_v9.append(dict(x=s['date'], y=s['price'], xref="x", yref="y", text=s['text'], showarrow=True, arrowhead=2, ax=0, ay=s['ay'], font=dict(color=s['color'], size=10, family="Arial Black")))
        
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT1'], line=dict(color='cyan'), name="WT 快線"), row=2, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT2'], line=dict(color='red', dash='dot'), name="WT 慢線"), row=2, col=1)
        fig_v9.add_hline(y=60, line_dash="dot", row=2, col=1); fig_v9.add_hline(y=-60, line_dash="dot", row=2, col=1)

        fig_v9.update_layout(height=700, xaxis_rangeslider_visible=False, title=f"{symbol} 智能戰術圖表", annotations=annotations_v9, template="plotly_dark")
        st.plotly_chart(fig_v9, use_container_width=True)

    # ==========================================
    # Tab 2: 機構透視 (維持 V10/V11)
    # ==========================================
    with tab_inst:
        st.subheader("🏛️ 機構訂單流與結構")
        fvgs, obs = calculate_smc_zones(df)
        
        fig_v10 = go.Figure()
        fig_v10.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"))
        
        for box in fvgs:
            color = "rgba(0, 255, 0, 0.2)" if box['type'] == 'Bull' else "rgba(255, 0, 0, 0.2)"
            fig_v10.add_shape(type="rect", x0=box['x0'], y0=box['bottom'], x1=box['x1'], y1=box['top'], line=dict(width=0), fillcolor=color, layer="below")
        for ob in obs:
            fig_v10.add_shape(type="rect", x0=ob['x0'], y0=ob['bottom'], x1=ob['x1'], y1=ob['top'], line=dict(color="blue", width=1, dash="dot"), fillcolor="rgba(0, 0, 255, 0.15)", layer="below")
            
        fig_v10.update_layout(height=700, xaxis_rangeslider_visible=False, title=f"{symbol} SMC 機構透視圖", template="plotly_dark")
        fig_v10.add_annotation(text="🟩 FVG 失衡區 (支撐)", xref="paper", yref="paper", x=0, y=1, showarrow=False, font=dict(color="green"))
        fig_v10.add_annotation(text="🟦 Order Block (機構單)", xref="paper", yref="paper", x=0, y=0.95, showarrow=False, font=dict(color="blue"))
        st.plotly_chart(fig_v10, use_container_width=True)

else:
    st.error("無法獲取數據")
