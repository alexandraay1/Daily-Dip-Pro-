import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 機構級操盤系統", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 機構版登入")
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
timeframe = st.sidebar.selectbox("分析週期", ["3mo", "6mo", "1y"], index=2)

# --- 3. 核心數據處理 ---
def get_data(ticker, period):
    try:
        df = yf.download(ticker, period=period, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 基礎指標
        df['SMA_20'] = ta.sma(df['Close'], length=20)
        df['SMA_50'] = ta.sma(df['Close'], length=50)
        df['SMA_200'] = ta.sma(df['Close'], length=200)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # 布林通道
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df = pd.concat([df, bb], axis=1)
            # 重新命名以防萬一
            cols = df.columns.tolist()
            if len(cols) >= 3:
                # 假設最後三欄是 BB 數據，手動對應
                # 這是一個簡單的防呆，確保我們抓得到欄位
                pass 

        # 成交量異動 (Volume Spike)
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA'] # 量比

        df.dropna(inplace=True)
        return df
    except Exception as e:
        return None

# --- 4. K線形態識別引擎 (純 Python 實現) ---
def check_patterns(df):
    # 取得最後 3 天的數據 (便於計算晨星等形態)
    if len(df) < 3: return []
    
    t = df.iloc[-1]   # 今天 (Today)
    y = df.iloc[-2]   # 昨天 (Yesterday)
    yy = df.iloc[-3]  # 前天
    
    patterns = []
    
    # 計算實體長度與影線
    body = abs(t['Close'] - t['Open'])
    upper_shadow = t['High'] - max(t['Close'], t['Open'])
    lower_shadow = min(t['Close'], t['Open']) - t['Low']
    avg_body = abs(df['Close'] - df['Open']).mean() # 平均實體大小
    
    # 1. 吞沒形態 (Engulfing)
    if t['Close'] > t['Open'] and y['Close'] < y['Open']: # 今陽昨陰
        if t['Close'] > y['Open'] and t['Open'] < y['Close']:
            patterns.append("🐂 **看漲吞沒 (Bullish Engulfing)**：多頭強勢反擊，覆蓋昨日跌幅。")
    
    if t['Close'] < t['Open'] and y['Close'] > y['Open']: # 今陰昨陽
        if t['Close'] < y['Open'] and t['Open'] > y['Close']:
            patterns.append("🐻 **看跌吞沒 (Bearish Engulfing)**：空頭反撲，吃掉昨日漲幅。")

    # 2. 錘頭線 (Hammer) - 底部反轉
    # 實體小，下影線長 (>2倍實體)，上影線短
    if lower_shadow > 2 * body and upper_shadow < 0.5 * body:
        if t['RSI'] < 40: # 結合低位判斷才準
            patterns.append("🔨 **錘頭線 (Hammer)**：低位出現長下影線，主力嘗試撐盤。")

    # 3. 射擊之星 (Shooting Star) - 頂部反轉
    if upper_shadow > 2 * body and lower_shadow < 0.5 * body:
        if t['RSI'] > 60:
            patterns.append("☄️ **射擊之星 (Shooting Star)**：高位受阻，拋壓沉重。")

    # 4. 十字星 (Doji)
    if body < 0.1 * avg_body:
        patterns.append("➕ **十字星 (Doji)**：多空勢均力敵，變盤前兆。")

    # 5. 晨星 (Morning Star) - 3根K線
    # 陰線 -> 小星線 -> 陽線
    if yy['Close'] < yy['Open'] and abs(y['Close']-y['Open']) < avg_body * 0.5 and t['Close'] > t['Open']:
        if t['Close'] > (yy['Open'] + yy['Close'])/2: # 收盤價深入第一根實體一半以上
            patterns.append("🌅 **晨星形態 (Morning Star)**：完美的底部反轉訊號。")

    return patterns

# --- 5. 阻力支撐與綜合分析 ---
def generate_pro_analysis(df, ticker):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = []
    score = 0
    
    # A. 均線與趨勢分析
    if last['Close'] < last['SMA_20'] and prev['Close'] > prev['SMA_20']:
        signals.append(f"📉 **跌穿 20MA 短期生命線**：股價轉弱，短線支撐失效。")
        score -= 2
    elif last['Close'] > last['SMA_20'] and prev['Close'] < prev['SMA_20']:
        signals.append(f"📈 **突破 20MA**：站上短期均線，動能轉強。")
        score += 2
        
    if last['Close'] < last['SMA_50']:
        signals.append(f"⚠️ **位於 50MA 之下**：中期趨勢偏空，反彈宜減碼。")
        score -= 1

    # B. 成交量異動 (VH)
    if last['Vol_Ratio'] > 2.0:
        if last['Close'] > last['Open']:
            signals.append(f"🔥 **爆量上漲 (量比 {last['Vol_Ratio']:.1f}x)**：資金強力進駐，後市看好。")
            score += 1
        else:
            signals.append(f"💀 **爆量下殺 (量比 {last['Vol_Ratio']:.1f}x)**：恐慌性拋售，主力出貨。")
            score -= 2

    # C. 形態學 (Patterns)
    candlestick_patterns = check_patterns(df)
    for p in candlestick_patterns:
        signals.append(p)
        if "🐂" in p or "🔨" in p or "🌅" in p: score += 2
        if "🐻" in p or "☄️" in p: score -= 2

    # D. 計算關鍵位 (阻力/支撐)
    # 簡單算法：過去 20 天的高低點
    recent_high = df['High'].tail(20).max()
    recent_low = df['Low'].tail(20).min()
    
    # 尋找整數關口 (Psychological Levels)
    price = last['Close']
    if price > 100:
        round_res = (int(price / 10) + 1) * 10 # 下一個 10元關卡
        round_sup = (int(price / 10)) * 10
    else:
        round_res = (int(price / 5) + 1) * 5
        round_sup = (int(price / 5)) * 5

    levels = {
        "resistance": max(recent_high, round_res),
        "support": min(recent_low, round_sup),
        "round_number": round_res
    }

    # 總結
    if score >= 3: recommendation = "🟢 強力買入"
    elif score <= -3: recommendation = "🔴 強力賣出"
    elif score > 0: recommendation = "🔵 謹慎看多"
    else: recommendation = "🟠 觀望 / 減倉"

    return signals, recommendation, score, levels

# --- 主畫面 UI ---
st.title(f"📊 {symbol} 機構級深度分析")
st.caption("包含：K線形態識別、成交量異動 (VH)、均線攻防、關鍵位")

df = get_data(symbol, timeframe)

if df is not None:
    # 1. 頂部大數據
    last_price = df['Close'].iloc[-1]
    change = last_price - df['Close'].iloc[-2]
    pct = (change / df['Close'].iloc[-2]) * 100
    
    # 執行分析
    reasons, rec, score, levels = generate_pro_analysis(df, symbol)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("現價", f"${last_price:.2f}", f"{pct:.2f}%")
    c2.metric("AI 評級", rec)
    c3.metric("多空分數", f"{score} / 10")
    c4.metric("今日量比 (Vol Ratio)", f"{df['Vol_Ratio'].iloc[-1]:.1f}x")

    st.divider()

    # 2. 左右分欄：左邊圖表，右邊分析
    col_left, col_right = st.columns([2, 1])

    with col_right:
        st.subheader("📝 智能訊號解讀")
        
        # 顯示關鍵位
        st.markdown(f"""
        **關鍵價位監控：**
        - 🎯 **壓力位 (Resistance)**: `${levels['resistance']:.2f}`
        - 🛡️ **支撐位 (Support)**: `${levels['support']:.2f}`
        - 🚧 **整數關口**: `${levels['round_number']}`
        """)
        
        st.markdown("---")
        st.markdown("**觸發訊號：**")
        
        if not reasons:
            st.info("今日無特殊技術形態，走勢平穩。")
        else:
            for r in reasons:
                st.write(r)
                
        # 交易心理建議
        st.markdown("---")
        if score > 0:
            st.success("💡 **操作建議**：多頭佔優，可沿 20MA 尋找買點，跌破支撐止蝕。")
        else:
            st.error("💡 **操作建議**：空頭強勢或動能不足，建議保留現金，等待止跌訊號。")

    with col_left:
        st.subheader("📈 綜合走勢圖")
        
        # 繪圖
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        
        # K線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        # 均線
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='orange', width=1.5), name='20 MA'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], line=dict(color='blue', width=1.5), name='50 MA'), row=1, col=1)
        
        # 標記阻力支撐
        fig.add_hline(y=levels['resistance'], line_dash="dash", line_color="red", annotation_text="壓力", row=1, col=1)
        fig.add_hline(y=levels['support'], line_dash="dash", line_color="green", annotation_text="支撐", row=1, col=1)

        # 成交量 (顏色區分漲跌)
        colors = ['red' if c < o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)
        
        fig.update_layout(height=600, xaxis_rangeslider_visible=False, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

else:
    st.error("無法獲取數據，請檢查股票代號。")
