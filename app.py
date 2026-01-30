import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 全能操盤系統 V5.0", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 全能操盤系統")
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
st.sidebar.markdown("---")
st.sidebar.info("系統整合：\n1. 歷史回測驗證\n2. K線形態識別\n3. 關鍵位自動劃線\n4. 智能買賣策略")

# --- 3. 核心數據處理 (整合所有指標) ---
def get_data(ticker):
    try:
        # 下載 2 年數據以供回測與分析
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        
        # 數據清洗 (處理 Yahoo MultiIndex)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # --- 計算指標 ---
        # 均線
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_50'] = ta.sma(df['Close'], length=50)
        df['SMA_200'] = ta.sma(df['Close'], length=200)
        
        # 動能
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # 波動率 (用於止蝕)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        # 成交量異動
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']

        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. K線形態識別引擎 (V3.0 功能回歸) ---
def check_patterns(df):
    if len(df) < 3: return []
    t = df.iloc[-1]; y = df.iloc[-2]; yy = df.iloc[-3]
    
    patterns = []
    body = abs(t['Close'] - t['Open'])
    upper_shadow = t['High'] - max(t['Close'], t['Open'])
    lower_shadow = min(t['Close'], t['Open']) - t['Low']
    avg_body = abs(df['Close'] - df['Open']).mean()

    # 吞沒
    if t['Close'] > t['Open'] and y['Close'] < y['Open']:
        if t['Close'] > y['Open'] and t['Open'] < y['Close']:
            patterns.append("🐂 **看漲吞沒 (Bullish Engulfing)**")
    elif t['Close'] < t['Open'] and y['Close'] > y['Open']:
        if t['Close'] < y['Open'] and t['Open'] > y['Close']:
            patterns.append("🐻 **看跌吞沒 (Bearish Engulfing)**")

    # 錘頭與射擊之星
    if lower_shadow > 2 * body and upper_shadow < 0.5 * body:
        if t['RSI'] < 40: patterns.append("🔨 **錘頭線 (Hammer)**")
    elif upper_shadow > 2 * body and lower_shadow < 0.5 * body:
        if t['RSI'] > 60: patterns.append("☄️ **射擊之星 (Shooting Star)**")

    # 十字星
    if body < 0.1 * avg_body: patterns.append("➕ **十字星 (Doji)**")
    
    return patterns

# --- 5. 回測引擎 (V4.0 功能保留) ---
def run_backtest(df):
    balance = 10000; initial_balance = balance; position = 0
    trades = []; equity_curve = []
    
    for i in range(1, len(df)):
        price = df['Close'].iloc[i]
        sma_20 = df['SMA_20'].iloc[i]
        rsi = df['RSI'].iloc[i]
        
        # 策略：站上 20MA 且 RSI 健康買入
        if price > sma_20 and rsi < 65 and position == 0:
            position = balance / price
            buy_price = price
            balance = 0
            trades.append({"type": "buy", "price": price})
        # 策略：跌破 20MA 或 RSI 過熱賣出
        elif ((price < sma_20) or (rsi > 80)) and position > 0:
            balance = position * price
            trades.append({"type": "sell", "price": price, "pct": (price-buy_price)/buy_price})
            position = 0
        
        equity_curve.append(balance + (position * price))
        
    # 計算回報
    total_return = ((equity_curve[-1] - initial_balance) / initial_balance) * 100
    # 計算勝率
    df_trades = pd.DataFrame(trades)
    win_rate = 0
    if not df_trades.empty:
        sells = df_trades[df_trades['type'] == 'sell']
        if not sells.empty:
            win_rate = (len(sells[sells['pct'] > 0]) / len(sells)) * 100

    return total_return, win_rate, equity_curve

# --- 6. 綜合分析與訊號生成 (核心大腦) ---
def generate_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    reasons = []
    score = 0
    
    # A. 趨勢分析
    if last['Close'] > last['SMA_20']:
        reasons.append("📈 **趨勢**：股價位於 20MA 之上，短線強勢。")
        score += 2
    else:
        reasons.append("📉 **趨勢**：股價位於 20MA 之下，短線弱勢。")
        score -= 2
        
    # B. 形態與成交量
    patterns = check_patterns(df)
    for p in patterns:
        reasons.append(f"🕯️ **形態**：出現 {p}")
        if "🐂" in p or "🔨" in p: score += 2
        if "🐻" in p or "☄️" in p: score -= 2
        
    if last['Vol_Ratio'] > 2.0:
        if last['Close'] > last['Open']:
            reasons.append(f"🔥 **量能**：爆量上漲 ({last['Vol_Ratio']:.1f}倍)，資金流入。")
            score += 1
        else:
            reasons.append(f"💀 **量能**：爆量下跌 ({last['Vol_Ratio']:.1f}倍)，恐慌拋售。")
            score -= 2

    # C. 阻力與支撐
    price = last['Close']
    recent_high = df['High'].tail(20).max()
    recent_low = df['Low'].tail(20).min()
    # 止蝕位 (基於 ATR)
    stop_loss = price - (2 * last['ATR'])
    # 目標價 (盈虧比 1.5:1)
    target_price = price + (3 * last['ATR'])

    # D. 最終建議
    if score >= 3: signal = "STRONG_BUY"
    elif score <= -3: signal = "STRONG_SELL"
    elif score > 0: signal = "BUY"
    else: signal = "WAIT"
    
    levels = {"res": recent_high, "sup": recent_low, "stop": stop_loss, "target": target_price}
    return signal, score, reasons, levels

# --- 主畫面 UI ---
st.title(f"🚀 {symbol} 全能即時分析")
st.caption("結合：歷史回測 (Backtest) + 價格行為 (Price Action) + 智能訊號 (AI Signal)")

df = get_data(symbol)

if df is not None:
    # --- Part 1: 回測數據 (證明實力) ---
    ret, win, curve = run_backtest(df)
    
    with st.expander("📊 查看 AI 歷史戰績 (點擊展開)", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("過去2年回報", f"{ret:.2f}%", delta="策略績效")
        c2.metric("交易勝率", f"{win:.1f}%", help="獲利次數佔比")
        c3.metric("當前參考勝算", "高" if win > 50 else "中", help="基於歷史表現")
    
    st.divider()

    # --- Part 2: 今日智能訊號 (核心操作區) ---
    signal, score, reasons, levels = generate_signal(df)
    
    # 顯示超大訊號區
    st.subheader("🤖 今日操作建議")
    
    col_sig, col_data = st.columns([1, 2])
    
    with col_sig:
        if signal == "STRONG_BUY":
            st.success("🟢 強力買入")
        elif signal == "BUY":
            st.info("🔵 謹慎買入")
        elif signal == "STRONG_SELL":
            st.error("🔴 強力賣出")
        else:
            st.warning("🟠 觀望 / 持幣")
            
        st.metric("多空評分", f"{score}/10")
        
    with col_data:
        k1, k2, k3 = st.columns(3)
        k1.metric("🎯 目標獲利", f"${levels['target']:.2f}")
        k2.metric("🛡️ 建議止蝕", f"${levels['stop']:.2f}")
        k3.metric("🚧 重點阻力", f"${levels['res']:.2f}")

    # --- Part 3: 詳細原因與圖表 ---
    tab1, tab2 = st.tabs(["📈 技術分析詳解", "💰 資金增長曲線"])
    
    with tab1:
        st.markdown("### 📝 進場/出場理由分析")
        if not reasons:
            st.write("今日走勢平穩，無特殊形態訊號。")
        else:
            for r in reasons:
                st.write(r)
        
        st.markdown("---")
        
        # 繪圖
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        # K線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        # 均線
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='orange'), name='20 MA'), row=1, col=1)
        # 支撐阻力線
        fig.add_hline(y=levels['res'], line_dash="dash", line_color="red", row=1, col=1)
        fig.add_hline(y=levels['sup'], line_dash="dash", line_color="green", row=1, col=1)
        # 止蝕線
        if signal in ["BUY", "STRONG_BUY"]:
            fig.add_hline(y=levels['stop'], line_dash="dot", line_color="yellow", row=1, col=1, annotation_text="止蝕")

        # 成交量
        colors = ['red' if c < o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)
        
        fig.update_layout(height=600, xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("資產增長模擬")
        st.line_chart(curve)

else:
    st.error("無法獲取數據")
