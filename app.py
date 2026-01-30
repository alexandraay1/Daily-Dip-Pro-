import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 專業操盤系統", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 會員專區")
        password = st.text_input("請輸入本月通行密碼", type="password")
        if st.button("登入"):
            if password == "VIP888":
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
        st.stop()

check_password()

# --- 側邊欄 ---
st.sidebar.title("💎 VIP 操盤室")
symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()
timeframe = st.sidebar.selectbox("選擇時間範圍", ["3mo", "6mo", "1y", "2y"], index=2)

# --- 3. 核心分析邏輯 (修復版) ---
def get_data_and_analyze(ticker, period):
    try:
        # 下載數據
        df = yf.download(ticker, period=period, progress=False)
        
        # --- 數據清洗 (修復 KeyError 的關鍵) ---
        if df.empty: return None, "找不到數據"
        
        # 處理 Yahoo Finance 的多層索引 (MultiIndex)
        # 如果欄位是 ('Close', 'NVDA') 這種格式，我們只要保留 'Close'
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 確保必要的欄位存在
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in required_cols):
            return None, f"數據格式錯誤，缺少必要欄位。偵測到的欄位: {df.columns.tolist()}"

        # --- 計算技術指標 ---
        # 1. 移動平均線
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        
        # 2. 布林通道 (Bollinger Bands)
        bbands = ta.bbands(df['Close'], length=20, std=2)
        if bbands is not None:
            df = pd.concat([df, bbands], axis=1)
            # 重新命名布林通道欄位，避免名稱變動導致錯誤
            # 假設 bbands 回傳三欄，分別命名為 BBL, BBM, BBU
            bb_cols = [c for c in df.columns if c.startswith('BBL_')]
            if bb_cols: df['BBL'] = df[bb_cols[0]]
            
            bb_cols_u = [c for c in df.columns if c.startswith('BBU_')]
            if bb_cols_u: df['BBU'] = df[bb_cols_u[0]]

        # 3. RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)

        # 4. MACD (最容易出錯的地方，我們手動命名)
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        if macd is not None:
            # 強制重新命名，不管它原本叫什麼
            macd.columns = ['MACD_Line', 'MACD_Hist', 'MACD_Signal']
            df = pd.concat([df, macd], axis=1)
        
        # 5. ATR
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        # 移除 NaN (剛開始幾天沒數據的行)
        df.dropna(inplace=True)

        return df, None
    except Exception as e:
        import traceback
        return None, f"發生錯誤: {str(e)}"

# --- 生成 AI 分析建議 ---
def generate_insight(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    insight = []
    score = 0 
    
    # 1. 趨勢判斷
    if last['Close'] > last['EMA_50']:
        insight.append(f"✅ **趨勢向上**：股價位於 50 日均線 (${last['EMA_50']:.2f}) 之上。")
        score += 2
    else:
        insight.append(f"⚠️ **趨勢向下**：股價跌破 50 日均線，注意風險。")
        score -= 2

    # 2. RSI
    if last['RSI'] > 70:
        insight.append(f"🔴 **RSI 過熱 ({last['RSI']:.1f})**：短線超買。")
        score -= 1
    elif last['RSI'] < 30:
        insight.append(f"🟢 **RSI 超賣 ({last['RSI']:.1f})**：反彈機會。")
        score += 2
    else:
        insight.append(f"⚪ **RSI 中性 ({last['RSI']:.1f})**：動能正常。")

    # 3. MACD (使用新命名的欄位)
    if 'MACD_Hist' in df.columns:
        if last['MACD_Hist'] > 0 and prev['MACD_Hist'] < 0:
            insight.append("🚀 **MACD 黃金交叉**：買入訊號確認！")
            score += 2
        elif last['MACD_Hist'] < 0 and prev['MACD_Hist'] > 0:
            insight.append("🔻 **MACD 死亡交叉**：動能轉弱。")
            score -= 2

    # 4. 布林通道
    if 'BBU' in df.columns and last['Close'] > last['BBU']:
        insight.append("🔥 **突破布林上軌**：強勢但需防回調。")
    elif 'BBL' in df.columns and last['Close'] < last['BBL']:
        insight.append("💧 **跌破布林下軌**：關注支撐。")

    if score >= 3: final_call = "🟢 強力買入"
    elif score <= -3: final_call = "🔴 強力賣出"
    elif score > 0: final_call = "🔵 謹慎看多"
    else: final_call = "🟠 觀望 / 減倉"

    return insight, final_call, score

# --- 主畫面 ---
st.title(f"📈 {symbol} 專業技術分析")
st.caption("含 MACD, RSI, Bollinger Bands, Volume 綜合指標")

df, err = get_data_and_analyze(symbol, timeframe)

if df is not None:
    last_price = df['Close'].iloc[-1]
    change = last_price - df['Close'].iloc[-2]
    pct_change = (change / df['Close'].iloc[-2]) * 100
    
    c1, c2, c3 = st.columns(3)
    c1.metric("現價", f"${last_price:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
    
    insights, call, score = generate_insight(df)
    c2.metric("AI 綜合評級", call)
    c3.metric("多空分數", f"{score} / 5")

    st.markdown("### 🤖 AI 技術解讀")
    with st.container():
        for line in insights:
            st.write(line)
            
    st.divider()

    st.subheader("📊 綜合走勢圖")
    
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, 
                        row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=("K線 & 布林通道", "成交量", "MACD", "RSI"))

    # K線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
    if 'BBU' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['BBU'], line=dict(color='gray', width=1, dash='dot'), name='布林上軌'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BBL'], line=dict(color='gray', width=1, dash='dot'), name='布林下軌'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=2), name='EMA 50'), row=1, col=1)

    # 成交量
    colors = ['green' if c >= o else 'red' for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)

    # MACD
    if 'MACD_Line' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Line'], line=dict(color='blue', width=1), name='MACD'), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], line=dict(color='orange', width=1), name='Signal'), row=3, col=1)
        colors_macd = ['green' if v >= 0 else 'red' for v in df['MACD_Hist']]
        fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=colors_macd, name='Hist'), row=3, col=1)

    # RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=2), name='RSI'), row=4, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)

    fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error(err)
