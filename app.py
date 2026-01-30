import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 量化回測系統", layout="wide")

# --- 2. 密碼鎖 (維持不變) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 量化系統")
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
st.sidebar.title("💎 機構操盤室")
symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()
# 回測週期強制設為 2年，這樣數據才夠
period = "2y" 

# --- 3. 核心數據處理 ---
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 基礎指標
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_50'] = ta.sma(df['Close'], length=50)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # 成交量
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']

        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 回測引擎 (Backtest Engine) ---
# 這是這次更新的核心：它會真的去模擬買賣
def run_backtest(df):
    balance = 10000  # 初始資金 10,000 美元
    initial_balance = balance
    position = 0     # 目前持倉數量
    
    trades = []      # 記錄每一筆交易
    equity_curve = [] # 資產曲線

    for i in range(1, len(df)):
        date = df.index[i]
        price = df['Close'].iloc[i]
        prev_price = df['Close'].iloc[i-1]
        
        # 取得指標
        sma_20 = df['SMA_20'].iloc[i]
        rsi = df['RSI'].iloc[i]
        
        # --- 策略邏輯 (Strategy Logic) ---
        # 買入條件: 站上 20MA (趨勢轉強) 且 RSI 不算太高 (不是最高點追高)
        buy_signal = (price > sma_20) and (rsi < 65) and (position == 0)
        
        # 賣出條件: 跌破 20MA (趨勢轉弱) 或 RSI 過熱 (獲利了結)
        sell_signal = ((price < sma_20) or (rsi > 80)) and (position > 0)
        
        # --- 執行交易 ---
        if buy_signal:
            position = balance / price # 全倉買入
            buy_price = price
            balance = 0
            trades.append({"type": "buy", "date": date, "price": price})
            
        elif sell_signal:
            balance = position * price # 全倉賣出
            profit = (price - buy_price) / buy_price
            trades.append({"type": "sell", "date": date, "price": price, "pct": profit})
            position = 0
            
        # 記錄每日資產淨值
        current_equity = balance + (position * price)
        equity_curve.append(current_equity)

    # 轉為 DataFrame
    df_trades = pd.DataFrame(trades)
    
    # 計算績效指標
    total_return = ((current_equity - initial_balance) / initial_balance) * 100
    
    # 計算勝率
    if not df_trades.empty:
        sells = df_trades[df_trades['type'] == 'sell']
        if not sells.empty:
            wins = len(sells[sells['pct'] > 0])
            total_trades = len(sells)
            win_rate = (wins / total_trades) * 100
        else:
            win_rate = 0
            total_trades = 0
    else:
        win_rate = 0
        total_trades = 0

    return total_return, win_rate, total_trades, equity_curve, df_trades

# --- 5. 顯示邏輯 ---
st.title(f"📊 {symbol} 實戰回測驗證")
st.caption("這不是預測，這是真實的歷史戰績。數據不說謊。")

df = get_data(symbol)

if df is not None:
    # 執行回測
    ret, win, count, curve, trade_log = run_backtest(df)
    
    # --- A. 績效儀表板 ---
    st.subheader("🏆 過去 2 年 AI 策略表現")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總回報率 (Total Return)", f"{ret:.2f}%", help="起始資金 $10,000 變成了多少")
    col2.metric("交易勝率 (Win Rate)", f"{win:.1f}%", help="賺錢的交易次數 / 總交易次數")
    col3.metric("總交易次數", f"{count} 次", help="太少代表樣本不足，太多代表手續費會很貴")
    
    # 買入持有對比 (Benchmark)
    buy_hold_ret = ((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]) * 100
    col4.metric("同期買入持有 (Buy & Hold)", f"{buy_hold_ret:.2f}%", delta=f"{ret - buy_hold_ret:.2f}%")

    st.divider()

    # --- B. 資金曲線圖 ---
    st.subheader("📈 資產增長曲線")
    st.info("藍線：使用我們的 AI 策略 | 橘線：傻傻買入持有")
    
    # 為了畫圖，我們要把 equity_curve 對齊 index
    curve_df = pd.DataFrame({'Strategy': curve}, index=df.index[1:])
    # 歸一化買入持有的曲線 (從 10000 開始)
    base_price = df['Close'].iloc[0]
    curve_df['Buy_Hold'] = (df['Close'][1:] / base_price) * 10000
    
    fig_curve = go.Figure()
    fig_curve.add_trace(go.Scatter(x=curve_df.index, y=curve_df['Strategy'], mode='lines', name='AI 策略資金', line=dict(color='green', width=2)))
    fig_curve.add_trace(go.Scatter(x=curve_df.index, y=curve_df['Buy_Hold'], mode='lines', name='買入持有 (基準)', line=dict(color='gray', dash='dot')))
    fig_curve.update_layout(height=400, yaxis_title="資產淨值 ($)")
    st.plotly_chart(fig_curve, use_container_width=True)

    # --- C. 今日分析 (保留之前的分析功能) ---
    st.divider()
    st.subheader("📝 今日技術分析")
    
    last = df.iloc[-1]
    
    # 簡單訊號顯示
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**當前價格**: ${last['Close']:.2f}")
        if last['Close'] > last['SMA_20']:
            st.success("✅ 目前處於 **20日均線之上** (趨勢偏多)")
        else:
            st.error("⚠️ 目前處於 **20日均線之下** (趨勢偏空)")
            
    with c2:
        st.write(f"**RSI 強度**: {last['RSI']:.1f}")
        if last['RSI'] > 70:
            st.warning("🔥 市場過熱，注意回調風險")
        elif last['RSI'] < 30:
            st.success("🧊 市場超賣，留意反彈機會")
        else:
            st.info("⚪ 市場情緒中性")

    # K線圖
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線")])
    fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='orange'), name='20 MA'))
    fig.update_layout(height=500, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("無法獲取數據")
