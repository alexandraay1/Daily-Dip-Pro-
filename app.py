import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 狙擊手操盤系統", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 狙擊手操盤系統")
        st.caption("專注於價格行為 (Price Action) 與 精準點位 (Key Levels)")
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
st.sidebar.title("💎 狙擊手控制台")
symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()
st.sidebar.markdown("---")
st.sidebar.info("圖表標記說明：\n\n🔥 **VH** = 爆量異動\n🐂 **Engulf** = 看漲吞沒\n🔨 **Hammer** = 錘頭線\n⭐ **Star** = 晨星/流星")

# --- 3. 核心數據處理 ---
def get_data(ticker):
    try:
        # 下載數據 (取最近 1 年即可，專注近期)
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- 指標計算 ---
        # 均線
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        
        # 波動率 (ATR) 用於計算止損止盈
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        # RSI
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # 成交量異動 (Volume High)
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']

        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 訊號與形態偵測 (返回給圖表標註用) ---
def detect_signals(df):
    signals = [] # 儲存所有要標記在圖上的訊號
    
    # 遍歷最後 60 天的數據來標記 (不要標記太久以前的，會亂)
    start_idx = max(0, len(df) - 60)
    
    for i in range(start_idx, len(df)):
        date = df.index[i]
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        # 1. 偵測 VH (爆量)
        if row['Vol_Ratio'] >= 2.0:
            signals.append({
                "date": date,
                "type": "VH",
                "price": row['High'], # 標記在最高價上方
                "desc": f"🔥 VH (量比 {row['Vol_Ratio']:.1f}x)"
            })
            
        # 2. 偵測 K線形態
        body = abs(row['Close'] - row['Open'])
        lower_shadow = min(row['Close'], row['Open']) - row['Low']
        
        # 看漲吞沒
        if row['Close'] > row['Open'] and prev['Close'] < prev['Open']:
            if row['Close'] > prev['Open'] and row['Open'] < prev['Close']:
                signals.append({
                    "date": date,
                    "type": "Bull",
                    "price": row['Low'], # 標記在最低價下方
                    "desc": "🐂 吞沒"
                })
        
        # 錘頭線 (Hammer) - 下影線長
        if lower_shadow > 2 * body and row['RSI'] < 45:
             signals.append({
                    "date": date,
                    "type": "Hammer",
                    "price": row['Low'],
                    "desc": "🔨 錘頭"
                })
                
    return signals

# --- 5. 交易計劃生成 (計算點位與原因) ---
def generate_trade_plan(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    atr = last['ATR']
    close = last['Close']
    
    plan = {}
    reasons = []
    
    # --- 阻力位 (Resistance) ---
    # 找過去 20 天最高點 + 整數關口
    recent_high = df['High'].tail(20).max()
    if recent_high > close:
        res_price = recent_high
        res_reason = "前波高點壓力"
    else:
        # 如果創新高，用整數關口
        res_price = (int(close / 10) + 1) * 10
        res_reason = "整數心理關口"
    
    plan['resistance'] = res_price
    plan['res_reason'] = res_reason

    # --- 止損位 (Stop Loss) ---
    # 策略：如果跌破 20MA 或 2倍 ATR
    if close > last['EMA_20']:
        stop_price = last['EMA_20']
        stop_reason = "跌穿 20MA (趨勢轉弱)"
    else:
        stop_price = close - (1.5 * atr)
        stop_reason = f"1.5倍 ATR 波動防守 (${1.5*atr:.2f})"
        
    plan['stop'] = stop_price
    plan['stop_reason'] = stop_reason
    
    # --- 目標價 (Target) ---
    # 盈虧比 1.5 : 1
    risk = close - stop_price
    if risk > 0:
        target_price = close + (risk * 2) # 賺賠比 2:1
        target_reason = "風險回報比 2:1 推算"
    else:
        # 如果現在是空頭趨勢 (Close < Stop?? 邏輯上 Stop 應該在上方，這裡簡化做多邏輯)
        # 假設做多邏輯
        target_price = close + (2 * atr)
        target_reason = "2倍 ATR 波段獲利"

    plan['target'] = target_price
    plan['target_reason'] = target_reason
    
    # --- 趨勢訊號原因 ---
    if close > last['EMA_20']:
        reasons.append("✅ **趨勢**：價格位於 20MA 之上，短線偏多。")
    else:
        reasons.append("⚠️ **趨勢**：價格跌破 20MA，注意回調。")
        
    if last['Vol_Ratio'] > 1.5:
        reasons.append(f"🔥 **量能**：今日成交量放大 {last['Vol_Ratio']:.1f}倍，方向明確。")
        
    patterns = detect_signals(df[-2:]) # 只看最後兩天有沒有形態
    for p in patterns:
        reasons.append(f"🕯️ **形態**：出現 {p['desc']}")

    return plan, reasons

# --- 主畫面 ---
st.title(f"🎯 {symbol} 精準戰術分析")
st.caption("智能標註：VH (爆量) / K線形態 / 關鍵點位")

df = get_data(symbol)

if df is not None:
    # 1. 取得數據與計算
    plan, reasons = generate_trade_plan(df)
    chart_signals = detect_signals(df)
    last_price = df['Close'].iloc[-1]
    
    # 2. 顯示關鍵點位 (戰術面板)
    st.subheader("📋 交易作戰計劃 (Trade Setup)")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("現價", f"${last_price:.2f}")
    c2.metric("🎯 目標獲利 (Target)", f"${plan['target']:.2f}")
    c3.metric("🛡️ 止損防守 (Stop)", f"${plan['stop']:.2f}")
    c4.metric("🚧 關鍵壓力 (Res)", f"${plan['resistance']:.2f}")
    
    # 3. 顯示原因 (Reasoning)
    st.info(f"""
    **點位設定邏輯：**
    * **目標價**：{plan['target_reason']}
    * **止損位**：{plan['stop_reason']}
    * **壓力位**：{plan['res_reason']}
    """)

    # 4. 訊號提示
    with st.expander("🔍 查看今日技術訊號分析", expanded=True):
        for r in reasons:
            st.write(r)
        if not reasons:
            st.write("今日走勢平穩，無特殊訊號，建議觀望。")

    st.divider()

    # 5. 繪製專業圖表 (含標註)
    st.subheader("📊 戰術圖表 (Tactical Chart)")
    
    fig = go.Figure()

    # K線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"))
    
    # 均線
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], line=dict(color='orange', width=1.5), name='20 EMA'))
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='blue', width=1.5), name='50 EMA'))
    
    # --- 關鍵：在圖表上畫線 ---
    # 1. 目標線 (綠色虛線)
    fig.add_hline(y=plan['target'], line_dash="dash", line_color="green", annotation_text="目標 Target", annotation_position="top right")
    # 2. 止損線 (紅色虛線)
    fig.add_hline(y=plan['stop'], line_dash="dash", line_color="red", annotation_text="止損 Stop", annotation_position="bottom right")
    # 3. 壓力線 (灰色點線)
    fig.add_hline(y=plan['resistance'], line_dash="dot", line_color="gray", annotation_text="壓力 Resistance")

    # --- 關鍵：圖表標註 (Annotations) ---
    # 我們把 detect_signals 算出來的點標上去
    annotations = []
    for sig in chart_signals:
        # 設定顏色
        color = "red" if "VH" in sig['type'] else "black"
        if "Bull" in sig['type']: color = "green"
        
        # 決定箭頭方向 (VH 在上方，Bull 在下方)
        ay = -40 if sig['type'] == 'VH' else 40 
        
        annotations.append(dict(
            x=sig['date'],
            y=sig['price'],
            xref="x",
            yref="y",
            text=sig['desc'], # 顯示 "🔥VH" 或 "🐂吞沒"
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=ay,
            font=dict(color=color, size=10)
        ))
    
    fig.update_layout(
        height=700, 
        xaxis_rangeslider_visible=False,
        annotations=annotations, # 加入標註
        title=f"{symbol} 價格行為標註圖"
    )
    
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("無法獲取數據")
