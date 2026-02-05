import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 基礎設定 ---
st.set_page_config(page_title="Trend Catchers V14 (No-Lib)", layout="wide", page_icon="🦈")

# --- 2. 手工計算指標函數 (替代 pandas_ta) ---
# 這些函數用純數學計算，保證不會崩潰
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

def calc_supertrend(df, period=10, multiplier=3):
    atr = calc_atr(df, period)
    hl2 = (df['High'] + df['Low']) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    final_upper = [basic_upper.iloc[0]]
    final_lower = [basic_lower.iloc[0]]
    trend = [1] # 1: Up, -1: Down
    
    close = df['Close'].values
    bu = basic_upper.values
    bl = basic_lower.values
    
    for i in range(1, len(df)):
        # 計算上軌
        if bu[i] < final_upper[i-1] or close[i-1] > final_upper[i-1]:
            final_upper.append(bu[i])
        else:
            final_upper.append(final_upper[i-1])
            
        # 計算下軌
        if bl[i] > final_lower[i-1] or close[i-1] < final_lower[i-1]:
            final_lower.append(bl[i])
        else:
            final_lower.append(final_lower[i-1])
            
        # 判斷趨勢
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
                
    st_line = np.where(np.array(trend)==1, final_lower, final_upper)
    return pd.Series(st_line, index=df.index), pd.Series(trend, index=df.index)

def calc_adx(df, length=14):
    high, low = df['High'], df['Low']
    close = df['Close']
    
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    
    tr = calc_atr(df, length) # 用 ATR 近似 TR Smooth
    plus_di = 100 * (plus_dm.ewm(alpha=1/length, adjust=False).mean() / tr)
    minus_di = 100 * (minus_dm.abs().ewm(alpha=1/length, adjust=False).mean() / tr)
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    return dx.ewm(alpha=1/length, adjust=False).mean()

def calc_wavetrend(df):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    esa = calc_ema(tp, 10)
    d = calc_ema((tp - esa).abs(), 10)
    ci = (tp - esa) / (0.015 * d)
    wt1 = calc_ema(ci, 21)
    wt2 = calc_sma(wt1, 4)
    return wt1, wt2

# --- 3. 數據下載引擎 ---
@st.cache_data(ttl=1800)
def get_data(ticker):
    try:
        # 下載數據
        df = yf.download(ticker, period="3y", progress=False, auto_adjust=False)
        
        # 格式修復
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.capitalize() for c in df.columns]
        
        # 移除時區
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
            
        if df.empty: return None

        # --- 套用手工指標 ---
        df['EMA_50'] = calc_ema(df['Close'], 50)
        df['EMA_200'] = calc_ema(df['Close'], 200)
        
        st_line, st_dir = calc_supertrend(df)
        df['SuperTrend'] = st_line
        df['Trend_Dir'] = st_dir
        
        df['ADX'] = calc_adx(df)
        df['WT1'], df['WT2'] = calc_wavetrend(df)
        
        # 擠壓 (簡單版)
        bb_mid = calc_sma(df['Close'], 20)
        bb_std = df['Close'].rolling(20).std()
        df['BB_Upper'] = bb_mid + 2 * bb_std
        df['BB_Lower'] = bb_mid - 2 * bb_std
        
        atr = calc_atr(df, 20)
        df['KC_Upper'] = bb_mid + 1.5 * atr
        df['KC_Lower'] = bb_mid - 1.5 * atr
        
        df['Squeeze_On'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])
        
        df.dropna(inplace=True)
        return df
        
    except Exception as e:
        st.error(f"數據處理錯誤: {e}")
        return None

# --- 4. 回測引擎 (V14) ---
def run_backtest(df):
    st.markdown("## 💰 V14 模擬回測報告")
    
    capital = 100000.0
    position = 0
    entry_price = 0
    log = []
    equity_curve = []
    
    # 預先計算可交易狀態
    # 條件：ADX > 20 且 沒有擠壓
    trade_mask = (df['ADX'] > 20) & (~df['Squeeze_On'])
    
    for i in range(1, len(df)-1):
        curr = df.iloc[i]
        nxt = df.iloc[i+1] # 成交價 (隔日開盤)
        prev = df.iloc[i-1]
        date = df.index[i]
        
        current_val = capital if position == 0 else position * curr['Close']
        equity_curve.append({"Date": date, "Equity": current_val})
        
        # --- 賣出邏輯 ---
        if position > 0:
            # 跌破 SuperTrend 或 跌破 EMA 50
            if curr['Close'] < curr['SuperTrend'] or curr['Close'] < curr['EMA_50']:
                sell_price = nxt['Open']
                profit_pct = (sell_price - entry_price) / entry_price * 100
                capital = position * sell_price
                position = 0
                log.append({"Date": nxt.name, "Type": "SELL", "Price": sell_price, "Return(%)": profit_pct})
                
        # --- 買入邏輯 ---
        elif position == 0 and trade_mask.iloc[i]:
            # 1. WT 黃金交叉 (且在超賣區)
            wt_signal = (curr['WT1'] < -40) and (curr['WT1'] > curr['WT2']) and (prev['WT1'] <= prev['WT2'])
            # 2. 突破 EMA 50
            ema_signal = (curr['Close'] > curr['EMA_50']) and (prev['Close'] <= prev['EMA_50'])
            
            if (wt_signal or ema_signal) and curr['Trend_Dir'] == 1:
                buy_price = nxt['Open']
                position = capital / buy_price
                entry_price = buy_price
                capital = 0
                log.append({"Date": nxt.name, "Type": "BUY", "Price": buy_price, "Return(%)": 0})

    # 最終結算
    final_val = capital if position == 0 else position * df.iloc[-1]['Close']
    ret = (final_val - 100000) / 100000 * 100
    
    c1, c2 = st.columns(2)
    c1.metric("最終獲利", f"${final_val:,.0f}", f"{ret:.1f}%")
    c2.metric("交易次數", len(log)//2)
    
    if len(equity_curve) > 0:
        st.line_chart(pd.DataFrame(equity_curve).set_index("Date"))
    else:
        st.warning("回測期間無交易")

# --- 主程式 ---
# 密碼鎖
if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    pwd = st.text_input("輸入密碼 (VIP888)", type="password")
    if st.button("登入"):
        if pwd == "VIP888": st.session_state.auth = True; st.rerun()
    st.stop()

# 介面
symbol = st.sidebar.text_input("股票代號", "TSLA").upper()
if st.button("重整數據"): st.cache_data.clear()

df = get_data(symbol)

if df is not None:
    tab1, tab2 = st.tabs(["📊 戰術圖表", "💰 回測結果"])
    
    with tab1:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange'), name="EMA 50"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], line=dict(color='blue', dash='dot'), name="SuperTrend"), row=1, col=1)
        
        # 標記買點
        buys = df[(df['Trend_Dir'] == 1) & (df['Close'] > df['EMA_50']) & (df['Close'].shift(1) <= df['EMA_50'].shift(1))]
        fig.add_trace(go.Scatter(x=buys.index, y=buys['Low']*0.98, mode='markers', marker=dict(symbol='triangle-up', size=10, color='yellow'), name="Potential Buy"), row=1, col=1)

        fig.add_trace(go.Bar(x=df.index, y=df['ADX'], name="ADX"), row=2, col=1)
        fig.add_hline(y=20, line_dash="dot", row=2, col=1)
        
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        if st.button("🚀 開始 V14 回測 ($100k)"):
            run_backtest(df)
else:
    st.error("無法下載數據，請稍後再試。")
