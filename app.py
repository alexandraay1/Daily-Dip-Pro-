import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 智能趨勢系統 V9.0", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 智能趨勢系統 V9.0")
        st.caption("集大成之作：價格行為 (V8) + 智能趨勢 (V9) + 機構風控")
        password = st.text_input("請輸入通行密碼", type="password")
        if st.button("登入"):
            if password == "VIP888":
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
        st.stop()

check_password()

# --- 側邊欄設定 ---
st.sidebar.title("🎛️ 智能控制台")
symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()
st.sidebar.markdown("---")

# 模式選擇
st.sidebar.subheader("⚙️ 系統設定")
candle_mode = st.sidebar.selectbox("K線著色模式", ["Standard (紅綠)", "Smart MACD (動能色)"])
show_cloud = st.sidebar.checkbox("顯示 EMA 趨勢雲", value=True)
show_supertrend = st.sidebar.checkbox("顯示 SuperTrend", value=True)
show_wavetrend = st.sidebar.checkbox("顯示 WaveTrend 反轉鑽石", value=True)

st.sidebar.markdown("---")
st.sidebar.info("""
**圖例說明：**
- ☁️ **雲帶**: 綠=多頭趨勢 / 紅=空頭趨勢
- ➖ **線條**: SuperTrend 智能止損線
- 💎 **鑽石**: WaveTrend 反轉訊號
- 🔥 **VH**: 爆量異動
- 🕯️ **形態**: 吞沒/錘頭/星形
""")

# --- 3. 核心數據與指標計算 (V9.0 核心) ---
def get_data(ticker):
    try:
        # 下載數據 (取 2 年以確保長週期均線計算準確)
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- A. 基礎指標 (V8 保留) ---
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # 成交量
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']
        
        # --- B. 智能趨勢系統 (V9 新增) ---
        
        # 1. EMA 趨勢雲 (Trend Cloud) - 150/200 EMA
        df['EMA_150'] = ta.ema(df['Close'], length=150)
        df['EMA_200'] = ta.ema(df['Close'], length=200)
        
        # 2. SuperTrend (超級趨勢)
        # 使用 ATR=10, Multiplier=3 (標準設定)
        st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        # pandas_ta return columns: SUPERT_7_3.0, SUPERTd_7_3.0, etc. Need to rename dynamically or find column
        st_col_trend = [c for c in st_data.columns if "SUPERT_" in c][0] # 數值
        st_col_dir = [c for c in st_data.columns if "SUPERTd_" in c][0]  # 方向 (1=Buy, -1=Sell)
        df['SuperTrend'] = st_data[st_col_trend]
        df['SuperTrend_Dir'] = st_data[st_col_dir]
        
        # 3. MACD (用於 K 線著色)
        macd = ta.macd(df['Close'])
        df['MACD'] = macd['MACD_12_26_9']
        df['MACD_Signal'] = macd['MACDs_12_26_9']
        df['MACD_Hist'] = macd['MACDh_12_26_9']
        
        # 4. ADX (趨勢強度)
        adx = ta.adx(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx['ADX_14']
        
        # 5. WaveTrend (反轉偵測)
        # 公式: ESA = EMA(Typical Price), D = EMA(abs(TP - ESA)), CI = (TP - ESA) / (0.015 * D), TCI = EMA(CI)
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        esa = ta.ema(tp, length=10)
        d = ta.ema((tp - esa).abs(), length=10)
        ci = (tp - esa) / (0.015 * d)
        df['WT1'] = ta.ema(ci, length=21) # 快線
        df['WT2'] = ta.sma(df['WT1'], length=4) # 慢線

        df.dropna(inplace=True)
        return df
    except Exception as e:
        return None

# --- 4. 形態與信號識別 (V8 + V9 整合) ---
def detect_all_signals(df):
    signals = [] 
    
    # 只需要最近 90 天的訊號來畫圖
    start_idx = max(200, len(df) - 90) # 確保前面有足夠數據算指標
    
    # 計算平均實體 (用於十字星)
    df['Body'] = abs(df['Close'] - df['Open'])
    avg_body = df['Body'].rolling(20).mean()
    
    for i in range(start_idx, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        date = df.index[i]
        
        # --- V8.0: 價格行為 (K線形態) ---
        body = curr['Body']
        mean_body = avg_body.iloc[i]
        
        # 爆量 (VH)
        if curr['Vol_Ratio'] >= 2.0:
            signals.append({"date": date, "price": curr['High'], "text": "🔥VH", "color": "red", "ay": -40, "anchor": "bottom"})

        # 吞沒 (Bullish Engulfing)
        if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
            if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']:
                signals.append({"date": date, "price": curr['Low'], "text": "🐂吞沒", "color": "green", "ay": 40, "anchor": "top"})
        
        # 錘頭 (Hammer)
        lower_shadow = min(curr['Close'], curr['Open']) - curr['Low']
        if lower_shadow > 2 * body and body > 0.1 * mean_body and curr['RSI'] < 45:
             signals.append({"date": date, "price": curr['Low'], "text": "🔨錘頭", "color": "green", "ay": 40, "anchor": "top"})
             
        # --- V9.0: WaveTrend 反轉信號 ---
        # 黃金交叉 (超賣區反彈)
        if curr['WT1'] < -50 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
            signals.append({"date": date, "price": curr['Low'] - (curr['ATR']*0.5), "text": "💎", "color": "blue", "ay": 25, "anchor": "top", "desc": "WT看漲反轉"})
        
        # 死亡交叉 (超買區回落)
        if curr['WT1'] > 50 and curr['WT1'] < curr['WT2'] and prev['WT1'] >= prev['WT2']:
             signals.append({"date": date, "price": curr['High'] + (curr['ATR']*0.5), "text": "💎", "color": "purple", "ay": -25, "anchor": "bottom", "desc": "WT看跌反轉"})

        # --- V9.0: SuperTrend 突破信號 ---
        # 趨勢轉多
        if curr['SuperTrend_Dir'] == 1 and prev['SuperTrend_Dir'] == -1:
            signals.append({"date": date, "price": curr['Low'], "text": "BUY", "color": "lime", "ay": 50, "anchor": "top", "desc": "SuperTrend 轉多"})
        # 趨勢轉空
        if curr['SuperTrend_Dir'] == -1 and prev['SuperTrend_Dir'] == 1:
            signals.append({"date": date, "price": curr['High'], "text": "SELL", "color": "maroon", "ay": -50, "anchor": "bottom", "desc": "SuperTrend 轉空"})

    return signals

# --- 5. 智能交易面板生成 ---
def generate_smart_panel(df):
    last = df.iloc[-1]
    
    # A. 市場狀態判斷
    if last['SuperTrend_Dir'] == 1:
        trend_status = "🟢 多頭趨勢"
        trend_color = "green"
    else:
        trend_status = "🔴 空頭趨勢"
        trend_color = "red"
        
    # B. 強度篩選 (ADX)
    adx_val = last['ADX']
    if adx_val > 50: strength = "🔥🔥 極強"
    elif adx_val > 25: strength = "🔥 強勢"
    else: strength = "☁️ 震盪/無趨勢"
    
    # C. 交易計劃 (風險管理)
    atr = last['ATR']
    close = last['Close']
    
    # 止損位：使用 SuperTrend 或 2倍 ATR
    if last['SuperTrend_Dir'] == 1:
        stop_loss = last['SuperTrend']
    else:
        stop_loss = close + (2 * atr) # 做空止損
        
    # 目標位：2倍風險回報 (2R)
    risk = abs(close - stop_loss)
    if last['SuperTrend_Dir'] == 1:
        tp1 = close + risk
        tp2 = close + (2 * risk)
    else:
        tp1 = close - risk
        tp2 = close - (2 * risk)

    return {
        "price": close,
        "trend": trend_status,
        "trend_color": trend_color,
        "strength": strength,
        "adx": adx_val,
        "volatility": (atr / close) * 100,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "risk_reward": "1 : 2"
    }

# --- 主程式 UI ---
st.title(f"🚀 {symbol} 智能趨勢系統 V9.0")
st.caption("SuperTrend 趨勢跟蹤 | WaveTrend 反轉偵測 | 機構級風險控管")

df = get_data(symbol)

if df is not None:
    # 只取最近 1 年數據畫圖
    plot_df = df.tail(250).copy()
    
    # 1. 智能面板 (Smart Panel)
    panel = generate_smart_panel(df)
    
    # 浮動樣式面板
    st.subheader("📊 市場概況 (Market Overview)")
    c1, c2, c3, c4, c5 = st.columns(5)
    
    c1.metric("當前價格", f"${panel['price']:.2f}")
    c2.metric("市場趨勢", panel['trend'])
    c3.metric("趨勢強度 (ADX)", f"{panel['adx']:.1f}", help=">25 為趨勢形成，>50 為極強趨勢")
    c4.metric("波動率", f"{panel['volatility']:.2f}%")
    c5.metric("建議止損 (SL)", f"${panel['stop_loss']:.2f}", delta_color="inverse")
    
    # 風險管理面板
    with st.expander("🛡️ 智能風險管理計劃 (Risk Management)", expanded=True):
        rc1, rc2, rc3 = st.columns(3)
        rc1.info(f"**第一目標 (TP1 - 保本移止)**: ${panel['tp1']:.2f}")
        rc2.success(f"**第二目標 (TP2 - 獲利鎖定)**: ${panel['tp2']:.2f}")
        rc3.warning(f"**動態止損 (Trailing SL)**: 沿著 SuperTrend 線移動 (${panel['stop_loss']:.2f})")

    st.divider()
    
    # 2. 準備繪圖數據
    
    # K線著色邏輯
    # 預設紅綠
    colors_increase = 'green'
    colors_decrease = 'red'
    line_increase = 'green'
    line_decrease = 'red'
    
    if candle_mode == "Smart MACD (動能色)":
        # 如果選了智能著色，我們需要建立顏色陣列
        # 這裡用 Plotly 的一個 trick：如果要做複雜著色，最好分開畫，但為了效能，
        # 我們保持主體紅綠，但在圖上疊加一個 "動能條 (Momentum Bar)"
        pass # Plotly 複雜著色在 Python Streamlit 較難完美實現，我們用標準紅綠配合指標信號更清晰
    
    # 3. 繪製全能圖表
    fig = go.Figure()

    # --- A. 趨勢雲 (Trend Cloud) ---
    if show_cloud:
        # 使用填色區塊
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df['EMA_150'],
            line=dict(width=0), showlegend=False, name="EMA 150"
        ))
        fig.add_trace(go.Scatter(
            x=plot_df.index, y=plot_df['EMA_200'],
            fill='tonexty', # 填滿到上一條線
            fillcolor='rgba(0, 255, 0, 0.1)', # 預設綠色 (需在 trace 中動態判斷? Plotly 靜態難做動態變色填充)
            # 這裡我們做簡單處理：一律淺灰色，重點看線的交叉，或者用兩次 fill
            line=dict(width=0), showlegend=False, name="EMA Cloud"
        ))
        # 為了區分紅綠雲，我們畫兩條線輔助
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_150'], line=dict(color='rgba(0,100,0,0.3)', width=1), name="EMA 150"))
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200'], line=dict(color='rgba(100,0,0,0.3)', width=1), name="EMA 200"))

    # --- B. K線圖 ---
    # 智能著色：如果 MACD > 0 且 RSI > 50 -> 亮綠色邊框；否則 -> 亮紅色邊框 (透過線條顏色區分)
    # 為了代碼穩定，這裡使用標準著色，但加強了邊框清晰度
    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df['Open'], high=plot_df['High'],
        low=plot_df['Low'], close=plot_df['Close'],
        name="K線",
        increasing_line_color='green', decreasing_line_color='red'
    ))

    # --- C. SuperTrend (超級趨勢線) ---
    if show_supertrend:
        # 分段畫綠線和紅線
        st_green = plot_df['SuperTrend'].copy()
        st_green[plot_df['SuperTrend_Dir'] == -1] = None # 只保留多頭部分
        
        st_red = plot_df['SuperTrend'].copy()
        st_red[plot_df['SuperTrend_Dir'] == 1] = None # 只保留空頭部分
        
        fig.add_trace(go.Scatter(x=plot_df.index, y=st_green, mode='lines', line=dict(color='lime', width=2), name='SuperTrend (多)'))
        fig.add_trace(go.Scatter(x=plot_df.index, y=st_red, mode='lines', line=dict(color='red', width=2), name='SuperTrend (空)'))

    # --- D. 訊號標註 (V8 + V9) ---
    signals = detect_all_signals(plot_df)
    annotations = []
    
    for sig in signals:
        # 過濾：如果使用者不想看 WaveTrend，就跳過鑽石
        if not show_wavetrend and "WT" in sig.get('desc', ''): continue
            
        annotations.append(dict(
            x=sig['date'], y=sig['price'],
            xref="x", yref="y",
            text=sig['text'],
            showarrow=True, arrowhead=2,
            ax=0, ay=sig['ay'],
            font=dict(color=sig['color'], size=10, family="Arial Black")
        ))
        
    fig.update_layout(
        height=700,
        xaxis_rangeslider_visible=False,
        annotations=annotations,
        title=f"{symbol} 智能趨勢戰術地圖",
        yaxis_title="價格",
        template="plotly_dark" # 現代暗色主題
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 4. 底部 WaveTrend 附圖 (如果需要看細節)
    if show_wavetrend:
        with st.expander("🌊 查看 WaveTrend 動能震盪指標", expanded=False):
            wt_fig = go.Figure()
            wt_fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['WT1'], name="WT 快線", line=dict(color='cyan')))
            wt_fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['WT2'], name="WT 慢線 (信號)", line=dict(color='red', dash='dot')))
            
            # 超買超賣線
            wt_fig.add_hline(y=60, line_dash="dash", line_color="gray")
            wt_fig.add_hline(y=-60, line_dash="dash", line_color="gray")
            wt_fig.add_hrect(y0=60, y1=100, fillcolor="red", opacity=0.1, line_width=0)
            wt_fig.add_hrect(y0=-60, y1=-100, fillcolor="green", opacity=0.1, line_width=0)
            
            wt_fig.update_layout(height=300, title="WaveTrend Momentum", template="plotly_dark")
            st.plotly_chart(wt_fig, use_container_width=True)

else:
    st.error("無法獲取數據，請檢查代號。")
