import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 專業操盤系統", layout="wide")

# --- 2. 密碼鎖 (保留你的賺錢功能) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 會員專區")
        password = st.text_input("請輸入本月通行密碼", type="password")
        if st.button("登入"):
            if password == "VIP888":  # 密碼
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

# --- 3. 核心分析邏輯 (升級版) ---
def get_data_and_analyze(ticker, period):
    try:
        # 下載數據
        df = yf.download(ticker, period=period, progress=False)
        if df.empty: return None, "找不到數據"
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # --- 計算技術指標 ---
        # 1. 移動平均線
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        
        # 2. 布林通道 (Bollinger Bands)
        bbands = ta.bbands(df['Close'], length=20, std=2)
        df = pd.concat([df, bbands], axis=1) # 合併數據
        # (bbands columns: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0)

        # 3. RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)

        # 4. MACD
        macd = ta.macd(df['Close'], fast=12, slow=26, signal=9)
        df = pd.concat([df, macd], axis=1)
        # (macd columns: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9)
        
        # 5. ATR (用於止蝕)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        return df, None
    except Exception as e:
        return None, str(e)

# --- 生成 AI 分析建議文字 ---
def generate_insight(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    insight = []
    score = 0 # 簡單評分 -5 到 +5
    
    # 1. 趨勢判斷 (EMA 50)
    if last['Close'] > last['EMA_50']:
        insight.append(f"✅ **趨勢向上**：股價位於 50 日均線之上 (${last['EMA_50']:.2f})，多頭格局。")
        score += 2
    else:
        insight.append(f"⚠️ **趨勢向下**：股價跌破 50 日均線，空頭佔優。")
        score -= 2

    # 2. RSI 判斷
    if last['RSI'] > 70:
        insight.append(f"🔴 **RSI 過熱 ({last['RSI']:.1f})**：進入超買區，短線可能回調。")
        score -= 1
    elif last['RSI'] < 30:
        insight.append(f"🟢 **RSI 超賣 ({last['RSI']:.1f})**：進入超賣區，隨時可能反彈。")
        score += 2
    else:
        insight.append(f"⚪ **RSI 中性 ({last['RSI']:.1f})**：動能正常。")

    # 3. MACD 判斷
    if last['MACDh_12_26_9'] > 0 and prev['MACDh_12_26_9'] < 0:
        insight.append("🚀 **MACD 黃金交叉**：動能翻正，強烈買入訊號！")
        score += 2
    elif last['MACDh_12_26_9'] < 0 and prev['MACDh_12_26_9'] > 0:
        insight.append("🔻 **MACD 死亡交叉**：動能轉弱，建議減倉。")
        score -= 2

    # 4. 布林通道
    if last['Close'] > last['BBU_20_2.0']:
        insight.append("🔥 **突破布林上軌**：強勢突破，注意乖離過大。")
    elif last['Close'] < last['BBL_20_2.0']:
        insight.append("💧 **跌破布林下軌**：股價被低估，關注支撐。")

    # 總結建議
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
    # 取得最新數據
    last_price = df['Close'].iloc[-1]
    change = last_price - df['Close'].iloc[-2]
    pct_change = (change / df['Close'].iloc[-2]) * 100
    
    # 顯示頂部大字
    c1, c2, c3 = st.columns(3)
    c1.metric("現價", f"${last_price:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
    
    # 生成分析
    insights, call, score = generate_insight(df)
    c2.metric("AI 綜合評級", call)
    c3.metric("多空分數", f"{score} / 5")

    # 顯示文字分析報告
    st.markdown("### 🤖 AI 技術解讀")
    with st.container():
        for line in insights:
            st.write(line)
            
    st.divider()

    # --- 繪製專業圖表 (4合1) ---
    st.subheader("📊 綜合走勢圖")
    
    # 建立子圖表 (4 Rows)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, 
                        row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=("K線 & 布林通道", "成交量 (Volume)", "MACD", "RSI"))

    # 1. 主圖 (K線 + MA + BB)
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BBU_20_2.0'], line=dict(color='gray', width=1, dash='dot'), name='布林上軌'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BBL_20_2.0'], line=dict(color='gray', width=1, dash='dot'), name='布林下軌'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=2), name='EMA 50'), row=1, col=1)

    # 2. 成交量
    colors = ['green' if c >= o else 'red' for c, o in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)

    # 3. MACD
    # MACD 線
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_12_26_9'], line=dict(color='blue', width=1), name='MACD'), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACDs_12_26_9'], line=dict(color='orange', width=1), name='Signal'), row=3, col=1)
    # Histogram (柱狀圖)
    colors_macd = ['green' if v >= 0 else 'red' for v in df['MACDh_12_26_9']]
    fig.add_trace(go.Bar(x=df.index, y=df['MACDh_12_26_9'], marker_color=colors_macd, name='Hist'), row=3, col=1)

    # 4. RSI
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=2), name='RSI'), row=4, col=1)
    # 畫出 70/30 參考線
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)

    # 設定圖表樣式
    fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error(err)
