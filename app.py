import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 (必須在第一行) ---
st.set_page_config(page_title="VIP 雙核戰略系統 V11.0", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 雙核戰略系統 V11.0")
        st.caption("雙視角切換：🚀 智能戰術 (V9)  |  🏛️ 機構透視 (V10)")
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
**系統導航：**
點擊主畫面在上方的標籤頁 (Tabs) 切換視角。

1. **🚀 智能戰術**：
   適合短線進出，看 K 線形態與指標。
   
2. **🏛️ 機構透視**：
   適合尋找大支撐，看 FVG 缺口與訂單塊。
""")

# --- 3. 核心數據引擎 (一次計算所有指標) ---
@st.cache_data(ttl=3600) # 快取數據避免重複加載
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- V9 指標 (趨勢與動能) ---
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
        
        # WaveTrend (反轉)
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        esa = ta.ema(tp, length=10)
        d = ta.ema((tp - esa).abs(), length=10)
        ci = (tp - esa) / (0.015 * d)
        df['WT1'] = ta.ema(ci, length=21)
        df['WT2'] = ta.sma(df['WT1'], length=4)
        
        # ADX (強度)
        adx = ta.adx(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx['ADX_14']
        
        # Volume Ratio
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']

        # K線實體計算
        df['Body'] = abs(df['Close'] - df['Open'])
        
        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 功能模組：V9 戰術信號 (V8+V9 邏輯) ---
def detect_retail_signals(df):
    signals = []
    # 取最近 100 天
    start = max(0, len(df)-100)
    avg_body = df['Body'].rolling(20).mean()
    
    for i in range(start, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
        
        # 1. 爆量
        if curr['Vol_Ratio'] >= 2.0:
            signals.append({"date": date, "price": curr['High'], "text": "🔥VH", "color": "red", "ay": -40})
            
        # 2. 吞沒
        if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
            if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']:
                signals.append({"date": date, "price": curr['Low'], "text": "🐂吞沒", "color": "green", "ay": 40})
                
        # 3. WaveTrend 鑽石
        if curr['WT1'] < -50 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
            signals.append({"date": date, "price": curr['Low'] - curr['ATR'], "text": "💎", "color": "cyan", "ay": 25})
            
    return signals

def generate_v9_panel(df):
    last = df.iloc[-1]
    trend = "🟢 多頭趨勢" if last['Trend_Dir'] == 1 else "🔴 空頭趨勢"
    strength = "🔥 強勢" if last['ADX'] > 25 else "☁️ 震盪"
    stop = last['SuperTrend']
    return trend, strength, stop

# --- 5. 功能模組：V10 機構邏輯 (SMC) ---
def calculate_smc_zones(df):
    fvgs = []
    obs = []
    
    # 計算 FVG (只取最近 60 天)
    start = max(0, len(df)-60)
    for i in range(start, len(df)):
        # Bullish FVG
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            fvgs.append({
                "type": "Bull", "top": df['Low'].iloc[i], "bottom": df['High'].iloc[i-2],
                "x0": df.index[i-1], "x1": df.index[-1]
            })
        # Bearish FVG
        if df['High'].iloc[i] < df['Low'].iloc[i-2] and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
            fvgs.append({
                "type": "Bear", "top": df['Low'].iloc[i-2], "bottom": df['High'].iloc[i],
                "x0": df.index[i-1], "x1": df.index[-1]
            })
            
    # 計算簡易 Order Blocks (最近 90 天)
    # 邏輯：波段低點前的陰線
    for i in range(start, len(df)-2):
        if df['Low'].iloc[i] < df['Low'].iloc[i-1] and df['Low'].iloc[i] < df['Low'].iloc[i+1]: # 轉折底
            if df['Close'].iloc[i] < df['Open'].iloc[i]: # 陰線
                # 確認後續上漲
                if df['Close'].iloc[i+1] > df['High'].iloc[i] or df['Close'].iloc[i+2] > df['High'].iloc[i]:
                    obs.append({
                        "type": "OB", "top": df['High'].iloc[i], "bottom": df['Low'].iloc[i],
                        "x0": df.index[i], "x1": df.index[-1]
                    })
    return fvgs, obs

# --- 主程式 ---
st.title(f"📊 {symbol} 雙核戰略分析系統")
df = get_data(symbol)

if df is not None:
    
    # 建立兩個分頁 (Tabs)
    tab_retail, tab_inst = st.tabs(["🚀 智能戰術 (V9.0)", "🏛️ 機構透視 (V10.0)"])
    
    # ==========================================
    # 分頁 1: V9.0 智能戰術 (適合散戶/短線)
    # ==========================================
    with tab_retail:
        st.subheader("🚀 趨勢跟蹤與形態識別")
        
        # 1. 戰術面板
        trend, strength, stop_v9 = generate_v9_panel(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("市場趨勢", trend)
        c2.metric("趨勢強度 (ADX)", f"{df['ADX'].iloc[-1]:.1f}", strength)
        c3.metric("WaveTrend 動能", f"{df['WT1'].iloc[-1]:.1f}")
        c4.metric("智能止損 (SuperTrend)", f"${stop_v9:.2f}")
        
        # 2. V9 圖表 (包含雲帶、SuperTrend、形態)
        fig_v9 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        
        # K線
        fig_v9.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        
        # 趨勢雲 (150/200 EMA)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_150'], line=dict(width=1, color='rgba(0,128,0,0.5)'), name="EMA 150"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(width=1, color='rgba(128,0,0,0.5)'), fill='tonexty', fillcolor='rgba(128,128,128,0.1)', name="EMA 200 (雲)"), row=1, col=1)
        
        # SuperTrend
        st_color = ['green' if x == 1 else 'red' for x in df['Trend_Dir']]
        # 為了畫線連續，這裡簡化處理，直接畫出整條線，顏色分段較複雜，用點表示或單色
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], mode='lines', line=dict(color='orange', width=2, dash='dash'), name="SuperTrend止損"), row=1, col=1)

        # 標註 (VH, 吞沒, 鑽石)
        signals = detect_retail_signals(df)
        annotations_v9 = []
        for s in signals:
            annotations_v9.append(dict(
                x=s['date'], y=s['price'], xref="x", yref="y",
                text=s['text'], showarrow=True, arrowhead=2, ax=0, ay=s['ay'],
                font=dict(color=s['color'], size=10, family="Arial Black")
            ))
        
        # WaveTrend 副圖
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT1'], line=dict(color='cyan'), name="WT 快線"), row=2, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT2'], line=dict(color='red', dash='dot'), name="WT 慢線"), row=2, col=1)
        fig_v9.add_hline(y=60, line_dash="dot", row=2, col=1); fig_v9.add_hline(y=-60, line_dash="dot", row=2, col=1)

        fig_v9.update_layout(height=700, xaxis_rangeslider_visible=False, title=f"{symbol} 智能戰術圖表 (V9)", annotations=annotations_v9, template="plotly_dark")
        st.plotly_chart(fig_v9, use_container_width=True)
        
        st.info("💡 **V9 戰術提示**：尋找「WaveTrend 鑽石信號」與「SuperTrend 趨勢線」同向的時刻。背景雲帶為綠色時，只做多。")

    # ==========================================
    # 分頁 2: V10.0 機構透視 (適合大戶/波段)
    # ==========================================
    with tab_inst:
        st.subheader("🏛️ 機構訂單流與結構")
        
        # 1. 機構面板
        fvgs, obs = calculate_smc_zones(df)
        last_close = df['Close'].iloc[-1]
        
        # 判斷價格與 FVG 的關係
        fvg_status = "價格處於平衡區"
        for box in fvgs:
            if box['type'] == 'Bull' and box['bottom'] <= last_close <= box['top']:
                fvg_status = "⚠️ 價格進入看漲 FVG (潛在支撐)"
            elif box['type'] == 'Bear' and box['bottom'] <= last_close <= box['top']:
                fvg_status = "⚠️ 價格進入看跌 FVG (潛在壓力)"

        ic1, ic2 = st.columns(2)
        ic1.metric("機構狀態監測", fvg_status)
        ic2.metric("下方最近訂單塊", f"{len(obs)} 個潛在支撐區")
        
        # 2. V10 圖表 (乾淨版，只有 FVG 和 OB)
        fig_v10 = go.Figure()
        
        # K線 (單純化)
        fig_v10.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"))
        
        # 繪製 FVG (矩形)
        for box in fvgs:
            color = "rgba(0, 255, 0, 0.2)" if box['type'] == 'Bull' else "rgba(255, 0, 0, 0.2)"
            fig_v10.add_shape(type="rect", x0=box['x0'], y0=box['bottom'], x1=box['x1'], y1=box['top'],
                             line=dict(width=0), fillcolor=color, layer="below")
                             
        # 繪製 Order Blocks (藍色矩形)
        for ob in obs:
            fig_v10.add_shape(type="rect", x0=ob['x0'], y0=ob['bottom'], x1=ob['x1'], y1=ob['top'],
                             line=dict(color="blue", width=1, dash="dot"), fillcolor="rgba(0, 0, 255, 0.15)", layer="below")
            
        fig_v10.update_layout(height=700, xaxis_rangeslider_visible=False, title=f"{symbol} SMC 機構透視圖 (V10)", template="plotly_dark")
        
        # 添加標註解釋
        fig_v10.add_annotation(text="綠色區塊 = FVG (缺口回補支撐)", xref="paper", yref="paper", x=0, y=1, showarrow=False, font=dict(color="green"))
        fig_v10.add_annotation(text="藍色區塊 = Order Block (大戶成本)", xref="paper", yref="paper", x=0, y=0.95, showarrow=False, font=dict(color="blue"))
        
        st.plotly_chart(fig_v10, use_container_width=True)
        
        st.success("""
        **🏛️ 機構劇本解讀：**
        1. **FVG (綠色/紅色塊)**：這是價格的「磁鐵」。如果價格急速回調並停留在綠色區塊內，這是機構在二次上車。
        2. **Order Block (藍色塊)**：這是最後的防線。價格碰到這裡通常會有強烈反彈。
        **操作建議**：不要在 FVG 中間追單，等待價格觸碰這些色塊邊緣並出現反轉 K 線（如 V9 的錘頭）時進場。
        """)

else:
    st.error("無法獲取數據，請檢查代號。")
