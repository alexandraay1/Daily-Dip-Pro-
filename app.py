import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go

# 網頁標題
st.set_page_config(page_title="AI 智能選股大師", layout="wide")

# 側邊欄
st.sidebar.title("💎 VIP 專用通道")
st.sidebar.info("這是您的專屬 AI 投資顧問")
symbol = st.sidebar.text_input("輸入美股代號 (如 NVDA, TSLA)", value="NVDA").upper()

# 核心分析功能
def analyze(ticker):
    try:
        # 抓取資料
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty: return None, "找不到股票數據"
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # 計算技術指標
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        # 取得最新數據
        last_close = df['Close'].iloc[-1]
        last_rsi = df['RSI'].iloc[-1]
        last_atr = df['ATR'].iloc[-1]
        
        # 交易訊號邏輯
        signal = "⚪ 觀望"
        color = "gray"
        note = "市場方向未明，建議空倉觀望。"

        if last_close > df['EMA_50'].iloc[-1] and last_rsi < 45:
            signal = "🟢 強力買入 (Buy Dip)"
            color = "green"
            note = "上升趨勢回調，低吸良機！"
        elif last_rsi > 75:
            signal = "🔴 建議賣出 (Sell)"
            color = "red"
            note = "嚴重超買，隨時崩盤，建議獲利。"
        elif last_close < df['EMA_50'].iloc[-1]:
            signal = "⚠️ 空頭走勢 (Bearish)"
            color = "orange"
            note = "趨勢向下，切勿接刀。"

        # 計算止蝕止盈
        stop_loss = last_close - (2 * last_atr)
        target = last_close + (3 * last_atr)

        return df, {"price": last_close, "signal": signal, "color": color, "note": note, "stop": stop_loss, "target": target}
    except:
        return None, "數據錯誤"

# 顯示介面
st.title(f"📈 {symbol} 趨勢狙擊系統")
st.write("---")
data, res = analyze(symbol)

if res and isinstance(res, dict):
    # 顯示三個核心指標
    c1, c2, c3 = st.columns(3)
    c1.metric("現價", f"${res['price']:.2f}")
    c2.metric("AI 訊號", res['signal'])
    c3.metric("止蝕位", f"${res['stop']:.2f}")

    if res['color'] == 'green': st.success(f"💡 AI 建議：{res['note']}")
    elif res['color'] == 'red': st.error(f"💡 AI 建議：{res['note']}")
    else: st.info(f"💡 AI 建議：{res['note']}")

    # 畫圖
    st.subheader("技術走勢")
    fig = go.Figure(data=[go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'])])
    fig.add_trace(go.Scatter(x=data.index, y=data['EMA_50'], line=dict(color='orange'), name='趨勢線'))
    fig.update_layout(xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
elif res:
    st.error(res)
