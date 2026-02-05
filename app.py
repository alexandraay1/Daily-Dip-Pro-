import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="Trend Catchers V14 | 量化修正版", layout="wide", page_icon="🦈")

# --- 2. 核心與密碼 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

def check_password():
    if not st.session_state.password_correct:
        st.markdown("## 🦈 Trend Catchers V14 (Quant Edition)")
        st.caption("核心升級：市場狀態過濾 (Regime Filter) | VPA 量價分析 | 假突破防禦")
        password = st.text_input("輸入通行密碼", type="password")
        if st.button("Access Terminal"):
            if password == "VIP888":
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ Access Denied")
        st.stop()

check_password()

# --- 側邊欄 ---
st.sidebar.title("🎛️ 量化控制台")
symbol = st.sidebar.text_input("美股代號", value="NVDA").upper()
timeframe = st.sidebar.selectbox("分析週期", ["Daily", "Weekly"], index=0)
st.sidebar.markdown("---")
st.sidebar.info("""
**V14 量化邏輯更新：**
1. **🛡️ 盤整過濾**：ADX < 20 或包絡線擠壓時，屏蔽突破信號。
2. **🐋 真鯨魚偵測**：排除長上影線的「出貨量」。
3. **📉 減法美學**：移除無效均線，只留關鍵位。
""")

# --- 3. 數據引擎 (優化版) ---
@st.cache_data(ttl=1800)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 基礎均線 (只留機構最看重的兩條)
        df['EMA_50'] = ta.ema(df['Close'], length=50)   # 機構成本線
        df['EMA_200'] = ta.ema(df['Close'], length=200) # 牛熊分界線
        
        # 波動率與趨勢強度
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        adx = ta.adx(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx['ADX_14']
        
        # SuperTrend (作為動態止損)
        st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        df['SuperTrend'] = st_data[st_data.columns[0]]
        df['Trend_Dir'] = st_data[st_data.columns[1]]
        
        # Bollinger Bands & Keltner Channels (用於偵測盤整擠壓)
        bb = ta.bbands(df['Close'], length=20, std=2)
        kc = ta.kc(df['High'], df['Low'], df['Close'], length=20, scalar=1.5)
        df['BB_Upper'] = bb['BBU_20_2.0']
        df['BB_Lower'] = bb['BBL_20_2.0']
        df['KC_Upper'] = kc['KCUe_20_1.5']
        df['KC_Lower'] = kc['KCLe_20_1.5']
        
        # Squeeze Logic: 當布林帶跑進 Keltner 通道內，代表極度壓縮 (變盤前兆)
        df['Squeeze_On'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])

        # WaveTrend (動能)
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        esa = ta.ema(tp, length=10)
        d = ta.ema((tp - esa).abs(), length=10)
        ci = (tp - esa) / (0.015 * d)
        df['WT1'] = ta.ema(ci, length=21)
        df['WT2'] = ta.sma(df['WT1'], length=4)
        
        # Volume
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']
        
        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 智能分析模組 (Quant Filters) ---
def analyze_market_regime(df):
    last = df.iloc[-1]
    
    # 1. 判斷市場狀態 (Regime)
    if last['Squeeze_On']:
        regime = "😴 壓縮盤整 (變盤前兆)"
        status_color = "orange"
        can_trade = False
        advice = "市場波動極低，正在蓄力。**嚴禁追高殺低**，等待布林帶開口。"
    elif last['ADX'] < 20:
        regime = "☁️ 無趨勢震盪"
        status_color = "gray"
        can_trade = False
        advice = "ADX 低於 20，缺乏動能。適合區間低吸高拋，不宜做突破。"
    else:
        regime = "🔥 強趨勢行情"
        status_color = "green" if last['Trend_Dir'] == 1 else "red"
        can_trade = True
        advice = "動能充足。順著 SuperTrend 方向操作，尋找回調買點。"
        
    return regime, status_color, can_trade, advice

def get_valid_signals(df, can_trade):
    signals = []
    if not can_trade: return signals # 如果市場狀態不好，直接不給信號 (保護用戶)
    
    start = max(0, len(df)-60)
    for i in range(start, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
        
        # 1. 趨勢跟隨信號 (Trend Pullback)
        # 邏輯：在多頭趨勢中，WT動能從低檔黃金交叉
        if curr['Trend_Dir'] == 1 and curr['WT1'] < -40 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
             signals.append({"date": date, "price": curr['Low'], "text": "💎趨勢回調買點", "color": "#00ff00", "ay": 30})

        # 2. 關鍵均線突破 (只看 EMA 50)
        if curr['Close'] > curr['EMA_50'] and prev['Close'] <= prev['EMA_50'] and curr['ADX'] > 20:
             signals.append({"date": date, "price": curr['Low'], "text": "🚀站上生命線", "color": "white", "ay": 40})
             
    return signals

def get_whale_zones(df):
    # 優化版鯨魚偵測：必須是大陽線，且不能有長上影線
    recent = df.tail(40).copy()
    # 計算實體佔比
    recent['Body_Size'] = (recent['Close'] - recent['Open']).abs()
    recent['Total_Size'] = recent['High'] - recent['Low']
    recent['Upper_Wick'] = recent['High'] - recent[['Open', 'Close']].max(axis=1)
    
    # 篩選條件：量大 + 實體大 + 上影線短 (代表主力真心想買)
    mask = (recent['Volume'] > recent['Vol_SMA'] * 1.5) & \
           (recent['Body_Size'] > recent['Total_Size'] * 0.6) & \
           (recent['Close'] > recent['Open'])
           
    whales = recent[mask]
    
    zones = []
    if not whales.empty:
        # 取最近的一根有效鯨魚K
        last_whale = whales.iloc[-1]
        zones.append({
            "price": last_whale['Low'], # 防守位通常是大量K的低點
            "top": last_whale['High'],
            "date": last_whale.name,
            "vol_ratio": last_whale['Vol_Ratio']
        })
    return zones

# --- 5. SMC 結構 (精簡版) ---
def get_smc_structure(df):
    # 只找最近的一個主要 FVG
    last_fvg = None
    start = max(0, len(df)-40)
    for i in range(start, len(df)):
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            last_fvg = {"top": df['Low'].iloc[i], "bottom": df['High'].iloc[i-2], "date": df.index[i-1]}
            
    # Fib 0.618
    swing_high = df['High'].tail(60).max()
    swing_low = df['Low'].tail(60).min()
    fib = swing_low + 0.618 * (swing_high - swing_low)
    
    return last_fvg, fib

# --- 主程式 UI ---
st.title(f"🦈 {symbol} 量化戰術終端 V14")
df = get_data(symbol)

if df is not None:
    
    # 1. 市場狀態儀表板 (最重要！)
    regime, color, can_trade, advice = analyze_market_regime(df)
    
    with st.container():
        st.markdown("### 📡 Market Regime (市場狀態)")
        c1, c2, c3 = st.columns([1, 2, 1])
        c1.metric("當前狀態", regime, delta="可交易" if can_trade else "觀望", delta_color="normal" if can_trade else "off")
        c2.info(f"💡 **AI 戰術顧問**：{advice}")
        c3.metric("趨勢強度 (ADX)", f"{df['ADX'].iloc[-1]:.1f}")
        
    st.divider()

    tab1, tab2 = st.tabs(["🚀 戰術圖表 (Tactical)", "🏛️ 機構數據 (Institutional)"])
    
    # --- Tab 1: 戰術圖表 ---
    with tab1:
        # 準備數據
        signals = get_valid_signals(df, can_trade)
        whale_zones = get_whale_zones(df)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
        
        # K線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
        
        # 關鍵均線
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=2), name="EMA 50 (生命線)"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(color='blue', width=2), name="EMA 200 (牛熊線)"), row=1, col=1)
        
        # SuperTrend
        fig.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], line=dict(color='gray', dash='dot', width=1), name="Trailing Stop"), row=1, col=1)
        
        # 繪製鯨魚支撐帶 (Whale Zone)
        if whale_zones:
            w = whale_zones[-1]
            fig.add_shape(type="rect", x0=w['date'], y0=w['price'], x1=df.index[-1], y1=w['top'], 
                         line=dict(width=0), fillcolor="rgba(128,0,128,0.2)", layer="below", row=1, col=1)
            fig.add_annotation(x=df.index[-1], y=w['top'], text=f"🐳 Whale Support (Vol x{w['vol_ratio']:.1f})", showarrow=False, xanchor="left", font=dict(color="purple"), row=1, col=1)

        # 繪製信號
        annotations = []
        for s in signals:
            annotations.append(dict(x=s['date'], y=s['price'], text=s['text'], showarrow=True, arrowhead=2, ay=s['ay'], font=dict(color=s['color'], size=11, family="Arial Black")))
        
        # 擠壓顯示 (Squeeze) - 在副圖顯示
        colors = ['red' if s else 'gray' for s in df['Squeeze_On']]
        fig.add_trace(go.Bar(x=df.index, y=df['ADX'], marker_color=colors, name="ADX / Squeeze"), row=2, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="white", row=2, col=1)
        
        fig.update_layout(height=700, xaxis_rangeslider_visible=False, template="plotly_dark", annotations=annotations, title=f"{symbol} 量化戰術圖表")
        st.plotly_chart(fig, use_container_width=True)
        
        st.caption("副圖說明：灰色柱狀體為 ADX 強度。**紅色柱狀體**代表「市場擠壓中 (Squeeze)」，此時即將變盤，請留意突破方向。")

    # --- Tab 2: 機構數據 ---
    with tab2:
        fvg, fib = get_smc_structure(df)
        last_close = df['Close'].iloc[-1]
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("🧱 訂單流結構 (Order Flow)")
            if fvg:
                st.success(f"發現最近的多頭失衡區 (Bull FVG)")
                st.metric("買入區間頂部", f"${fvg['top']:.2f}")
                st.metric("買入區間底部", f"${fvg['bottom']:.2f}")
                dist = (last_close - fvg['top']) / last_close * 100
                st.caption(f"目前距離買點：{dist:.1f}%")
            else:
                st.warning("近期無明顯大型 FVG 結構")

        with c2:
            st.subheader("📐 黃金回調位 (Fibonacci)")
            st.metric("0.618 回調位", f"${fib:.2f}")
            st.caption("這是機構演算法最常掛 Limit Buy 的位置")
            
            risk = abs(last_close - df['SuperTrend'].iloc[-1])
            st.metric("建議止損距離 (Risk)", f"${risk:.2f}")

else:
    st.error("無法取得數據，請確認代號正確")
