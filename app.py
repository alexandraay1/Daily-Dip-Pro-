import streamlit as st
import yfinance as yf
import pandas as pd
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

# --- 3. 手工指標計算引擎 (No-Lib 核心) ---
# 這些函數替代了 pandas_ta，保證不會崩潰

def calc_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

def calc_sma(series, length):
    return series.rolling(window=length).mean()

def calc_atr(df, length=14):
    high, low, close = df['High'], df['Low'], df['Close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, adjust=False).mean()

def calc_adx(df, length=14):
    high, low, close = df['High'], df['Low'], df['Close']
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    tr = calc_atr(df, length)
    plus_di = 100 * (plus_dm.ewm(alpha=1/length, adjust=False).mean() / tr)
    minus_di = 100 * (minus_dm.abs().ewm(alpha=1/length, adjust=False).mean() / tr)
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    return dx.ewm(alpha=1/length, adjust=False).mean()

def calc_supertrend(df, period=10, multiplier=3):
    atr = calc_atr(df, period)
    hl2 = (df['High'] + df['Low']) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    # 初始化
    final_upper = [basic_upper.iloc[0]]
    final_lower = [basic_lower.iloc[0]]
    trend = [1] # 1: Up, -1: Down
    
    close = df['Close'].values
    bu = basic_upper.values
    bl = basic_lower.values
    
    for i in range(1, len(df)):
        # 計算 Upper
        if bu[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]:
            final_upper.append(bu[i])
        else:
            final_upper.append(final_upper[i-1])
        
        # 計算 Lower
        if bl[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]:
            final_lower.append(bl[i])
        else:
            final_lower.append(final_lower[i-1])
            
        # 決定趨勢
        prev_trend = trend[i-1]
        if prev_trend == 1:
            if close[i] < final_lower[i]:
                trend.append(-1)
            else:
                trend.append(1)
        else:
            if close[i] > final_upper[i]:
                trend.append(1)
            else:
                trend.append(-1)

    # 組合 SuperTrend 線
    st_line = np.where(np.array(trend)==1, final_lower, final_upper)
    return pd.Series(st_line, index=df.index), pd.Series(trend, index=df.index)

def calc_wavetrend(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    esa = calc_ema(tp, 10)
    d = calc_ema((tp - esa).abs(), 10)
    ci = (tp - esa) / (0.015 * d)
    wt1 = calc_ema(ci, 21)
    wt2 = calc_sma(wt1, 4)
    return wt1, wt2

# --- 4. 數據下載與處理 ---
@st.cache_data(ttl=1800)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=False)
        
        # 格式清洗
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [c.capitalize() for c in df.columns] # 確保 Close, Open 等大寫
        
        # 移除時區
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)

        # --- 計算指標 (使用上方的手工函數) ---
        
        # 1. 均線
        df['EMA_50'] = calc_ema(df['Close'], 50)
        df['EMA_200'] = calc_ema(df['Close'], 200)
        
        # 2. SuperTrend
        st_line, st_dir = calc_supertrend(df, 10, 3)
        df['SuperTrend'] = st_line
        df['Trend_Dir'] = st_dir
        
        # 3. ADX
        df['ADX'] = calc_adx(df)
        
        # 4. Squeeze (BB & KC)
        bb_mid = calc_sma(df['Close'], 20)
        bb_std = df['Close'].rolling(20).std()
        df['BB_Upper'] = bb_mid + 2 * bb_std
        df['BB_Lower'] = bb_mid - 2 * bb_std
        
        atr_20 = calc_atr(df, 20)
        df['KC_Upper'] = calc_ema(df['Close'], 20) + 1.5 * atr_20
        df['KC_Lower'] = calc_ema(df['Close'], 20) - 1.5 * atr_20
        
        df['Squeeze_On'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])
        
        # 5. WaveTrend
        df['WT1'], df['WT2'] = calc_wavetrend(df)
        
        # 6. Volume
        df['Vol_SMA'] = calc_sma(df['Volume'], 20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']
        
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"Error: {e}") # 僅供後台除錯
        return None

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

# --- 5. 智能分析模組 ---
def analyze_market_regime(df):
    last = df.iloc[-1]
    
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
    if not can_trade: return signals
    
    start = max(0, len(df)-60)
    for i in range(start, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
        
        # 趨勢回調
        if curr['Trend_Dir'] == 1 and curr['WT1'] < -40 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
             signals.append({"date": date, "price": curr['Low'], "text": "💎趨勢回調買點", "color": "#00ff00", "ay": 30})

        # 關鍵突破
        if curr['Close'] > curr['EMA_50'] and prev['Close'] <= prev['EMA_50'] and curr['ADX'] > 20:
             signals.append({"date": date, "price": curr['Low'], "text": "🚀站上生命線", "color": "white", "ay": 40})
             
    return signals

def get_whale_zones(df):
    # 鯨魚偵測
    recent = df.tail(40).copy()
    recent['Body_Size'] = (recent['Close'] - recent['Open']).abs()
    recent['Total_Size'] = recent['High'] - recent['Low']
    
    mask = (recent['Volume'] > recent['Vol_SMA'] * 1.5) & \
           (recent['Body_Size'] > recent['Total_Size'] * 0.6) & \
           (recent['Close'] > recent['Open'])
           
    whales = recent[mask]
    zones = []
    if not whales.empty:
        last_whale = whales.iloc[-1]
        zones.append({
            "price": last_whale['Low'],
            "top": last_whale['High'],
            "date": last_whale.name,
            "vol_ratio": last_whale['Vol_Ratio']
        })
    return zones

def get_smc_structure(df):
    last_fvg = None
    start = max(0, len(df)-40)
    for i in range(start, len(df)):
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            last_fvg = {"top": df['Low'].iloc[i], "bottom": df['High'].iloc[i-2], "date": df.index[i-1]}
    
    swing_high = df['High'].tail(60).max()
    swing_low = df['Low'].tail(60).min()
    fib = swing_low + 0.618 * (swing_high - swing_low)
    return last_fvg, fib

# --- 主程式 UI ---
st.title(f"🦈 {symbol} 量化戰術終端 V14")

# 下載數據
df = get_data(symbol)

if df is not None:
    regime, color, can_trade, advice = analyze_market_regime(df)
    
    with st.container():
        st.markdown("### 📡 Market Regime (市場狀態)")
        c1, c2, c3 = st.columns([1, 2, 1])
        c1.metric("當前狀態", regime, delta="可交易" if can_trade else "觀望", delta_color="normal" if can_trade else "off")
        c2.info(f"💡 **AI 戰術顧問**：{advice}")
        c3.metric("趨勢強度 (ADX)", f"{df['ADX'].iloc[-1]:.1f}")
        
    st.divider()

    tab1, tab2 = st.tabs(["🚀 戰術圖表 (Tactical)", "🏛️ 機構數據 (Institutional)"])
    
    with tab1:
        signals = get_valid_signals(df, can_trade)
        whale_zones = get_whale_zones(df)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
        
        # 價格與指標
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=2), name="EMA 50"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(color='blue', width=2), name="EMA 200"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], line=dict(color='gray', dash='dot', width=1), name="SuperTrend"), row=1, col=1)
        
        # 鯨魚帶
        if whale_zones:
            w = whale_zones[-1]
            fig.add_shape(type="rect", x0=w['date'], y0=w['price'], x1=df.index[-1], y1=w['top'], 
                         line=dict(width=0), fillcolor="rgba(128,0,128,0.2)", layer="below", row=1, col=1)

        # 信號
        annotations = []
        for s in signals:
            annotations.append(dict(x=s['date'], y=s['price'], text=s['text'], showarrow=True, arrowhead=2, ay=s['ay'], font=dict(color=s['color'])))
        
        # 副圖
        colors = ['red' if s else 'gray' for s in df['Squeeze_On']]
        fig.add_trace(go.Bar(x=df.index, y=df['ADX'], marker_color=colors, name="ADX / Squeeze"), row=2, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="white", row=2, col=1)
        
        fig.update_layout(height=700, xaxis_rangeslider_visible=False, template="plotly_dark", annotations=annotations)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        fvg, fib = get_smc_structure(df)
        last_close = df['Close'].iloc[-1]
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🧱 訂單流")
            if fvg:
                st.metric("FVG 買入區", f"${fvg['top']:.2f}")
            else:
                st.info("無明顯 FVG")
        with c2:
            st.subheader("📐 Fibonacci")
            st.metric("0.618 回調", f"${fib:.2f}")

else:
    st.error("無法取得數據，請確認代號正確")
