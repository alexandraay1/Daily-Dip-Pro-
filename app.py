import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP SMC 機構透視系統 V10.0", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP SMC 機構透視系統 V10.0")
        st.caption("核心技術：Smart Money Concepts (SMC) + Fair Value Gaps (FVG)")
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
st.sidebar.title("🏛️ 機構操盤室")
symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()
st.sidebar.markdown("---")
st.sidebar.success("""
**SMC 機構指標說明：**
1. 🔲 **FVG (失衡區)**：
   價格劇烈波動留下的缺口，
   價格常會回測此區(磁鐵效應)。
   
2. 🧱 **Order Block (訂單塊)**：
   機構大舉進場的足跡，
   這是最強的支撐/壓力區。

3. 🌊 **Liquidity (流動性)**：
   標記前高/前低，
   是假突破的高發區。
""")
show_fvg = st.sidebar.checkbox("顯示 FVG 失衡區", value=True)
show_ob = st.sidebar.checkbox("顯示 Order Blocks 訂單塊", value=True)

# --- 3. 核心數據處理 ---
def get_data(ticker):
    try:
        # 下載 1 年數據
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 基礎指標
        df['EMA_50'] = ta.ema(df['Close'], length=50) # 趨勢基準
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # SuperTrend (用於過濾大方向)
        st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        st_col = [c for c in st_data.columns if "SUPERT_" in c][0]
        st_dir = [c for c in st_data.columns if "SUPERTd_" in c][0]
        df['SuperTrend'] = st_data[st_col]
        df['Trend_Dir'] = st_data[st_dir] # 1=Buy, -1=Sell

        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. SMC 機構指標算法 (V10 核心) ---

def calculate_smc(df):
    # FVG (Fair Value Gaps) 識別
    # 邏輯：第1根K線的高/低點 與 第3根K線的低/高點 之間沒有重疊
    
    fvg_zones = []
    
    for i in range(2, len(df)):
        # 1. 看漲 FVG (Bullish FVG)
        # 條件：K線1的高點 < K線3的低點 (中間K線2是大陽線)
        h1 = df['High'].iloc[i-2]
        l3 = df['Low'].iloc[i]
        
        if l3 > h1 and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            # 記錄這個區域 (只記錄最近 30 天的，保持圖表乾淨)
            if i > len(df) - 60: 
                fvg_zones.append({
                    "type": "Bull_FVG",
                    "top": l3,
                    "bottom": h1,
                    "start_date": df.index[i-1],
                    "end_date": df.index[-1] # 延伸到今天
                })
        
        # 2. 看跌 FVG (Bearish FVG)
        # 條件：K線1的低點 > K線3的高點 (中間K線2是大陰線)
        l1 = df['Low'].iloc[i-2]
        h3 = df['High'].iloc[i]
        
        if h3 < l1 and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
            if i > len(df) - 60:
                fvg_zones.append({
                    "type": "Bear_FVG",
                    "top": l1,
                    "bottom": h3,
                    "start_date": df.index[i-1],
                    "end_date": df.index[-1]
                })

    return fvg_zones

def detect_order_blocks(df):
    # 簡易 Order Block 識別：
    # 看漲 OB：一段下跌趨勢後的最後一根陰線，隨後被強勢陽線吞沒
    obs = []
    for i in range(5, len(df)-2):
        # 簡單邏輯：如果是波段低點，且後面緊跟大陽線
        # 為了代碼效率，我們找 Pivot Low
        curr_low = df['Low'].iloc[i]
        if curr_low < df['Low'].iloc[i-1] and curr_low < df['Low'].iloc[i+1]:
            # 這是個轉折底，檢查這根是否是陰線，且後面是否大漲
            if df['Close'].iloc[i] < df['Open'].iloc[i]: # 陰線
                # 檢查後兩天是否有大漲吞沒
                if df['Close'].iloc[i+1] > df['High'].iloc[i] or df['Close'].iloc[i+2] > df['High'].iloc[i]:
                     # 這根陰線就是 Order Block
                     if i > len(df) - 60:
                        obs.append({
                            "type": "Bull_OB",
                            "top": df['High'].iloc[i],
                            "bottom": df['Low'].iloc[i],
                            "date": df.index[i]
                        })
    return obs

# --- 5. 訊號整合 ---
def generate_institutional_signal(df):
    last = df.iloc[-1]
    
    # 結合 趨勢 (SuperTrend) + 價格行為
    trend = "🟢 多頭機構控盤" if last['Trend_Dir'] == 1 else "🔴 空頭機構控盤"
    
    score = 0
    reasons = []
    
    # 1. 趨勢分
    if last['Trend_Dir'] == 1: 
        score += 2
        reasons.append("✅ **趨勢**：SuperTrend 顯示機構資金流向為多頭。")
    else: 
        score -= 2
        reasons.append("⚠️ **趨勢**：SuperTrend 顯示空頭佔優。")
        
    # 2. RSI 狀態
    if last['RSI'] > 70: reasons.append("⚠️ **RSI**：超買，小心機構倒貨。")
    if last['RSI'] < 30: reasons.append("✅ **RSI**：超賣，機構可能正在吸籌。")

    # 3. 建議操作
    atr = last['ATR']
    stop_loss = last['SuperTrend']
    
    # 計算盈虧比
    dist_to_sl = abs(last['Close'] - stop_loss)
    tp1 = last['Close'] + (1.5 * dist_to_sl) if last['Trend_Dir'] == 1 else last['Close'] - (1.5 * dist_to_sl)
    
    return trend, score, reasons, stop_loss, tp1

# --- 主 UI ---
st.title(f"🏛️ {symbol} SMC 機構透視系統 V10.0")
st.caption("Smart Money Concepts: 追蹤大戶足跡，尋找 FVG 缺口與訂單塊")

df = get_data(symbol)

if df is not None:
    # 計算 SMC 數據
    fvgs = calculate_smc(df)
    obs = detect_order_blocks(df)
    trend, score, reasons, sl, tp = generate_institutional_signal(df)
    last_price = df['Close'].iloc[-1]
    
    # --- 1. 機構儀表板 ---
    st.subheader("📊 機構資金流向 (Institutional Flow)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("當前趨勢", trend)
    c2.metric("最新報價", f"${last_price:.2f}")
    c3.metric("止損位 (SL)", f"${sl:.2f}")
    c4.metric("第一目標 (TP)", f"${tp:.2f}")
    
    with st.expander("📝 查看詳細分析報告", expanded=True):
        for r in reasons:
            st.write(r)
        st.info("💡 **交易提示**：重點關注圖表中的 **矩形色塊 (FVG)**。當價格回調進入綠色 FVG 區域且不跌破時，是勝率最高的「機構搭車點」。")

    st.divider()

    # --- 2. SMC 專業圖表 ---
    st.subheader(f"🏛️ {symbol} 機構訂單分佈圖")
    
    fig = go.Figure()

    # K線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"))
    
    # SuperTrend 線
    st_color = 'green' if df['Trend_Dir'].iloc[-1] == 1 else 'red'
    fig.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], line=dict(color=st_color, width=2), name="SuperTrend (止損)"))

    # --- 繪製 FVG (失衡區) ---
    if show_fvg:
        for box in fvgs:
            # 限制只畫尚未被填補太遠的，或者最近的
            color = "rgba(0, 255, 0, 0.2)" if box['type'] == "Bull_FVG" else "rgba(255, 0, 0, 0.2)"
            # 使用 Shape 畫矩形
            fig.add_shape(type="rect",
                x0=box['start_date'], y0=box['bottom'],
                x1=box['end_date'], y1=box['top'],
                line=dict(width=0),
                fillcolor=color,
                layer="below"
            )
            # 標註
            if box == fvgs[-1]: # 只標最後一個，避免亂
                fig.add_annotation(x=box['start_date'], y=box['top'], text="FVG", showarrow=False, font=dict(color=color, size=8))

    # --- 繪製 Order Blocks (訂單塊) ---
    if show_ob:
        for ob in obs:
            # OB 通常是一根 K 線的範圍，延伸到未來
            fig.add_shape(type="rect",
                x0=ob['date'], y0=ob['bottom'],
                x1=df.index[-1], y1=ob['top'],
                line=dict(color="blue", width=1, dash="dot"),
                fillcolor="rgba(0, 0, 255, 0.1)",
                layer="below"
            )

    fig.update_layout(
        height=750,
        xaxis_rangeslider_visible=False,
        title=f"{symbol} Smart Money Structure (FVG & Order Blocks)",
        template="plotly_dark",
        yaxis_title="Price"
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.warning("**免責聲明**：SMC (聰明錢概念) 是進階交易技術，FVG 區域是潛在支撐/壓力，並非絕對轉折點，請務必配合止損使用。")

else:
    st.error("無法獲取數據")
