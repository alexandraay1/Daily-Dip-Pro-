import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 機構狙擊系統 V13.0", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 機構狙擊系統 V13.0")
        st.caption("新增：SMC 數據列表 | 斐波那契回調預測 | 鯨魚成交量偵測")
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
**V13.0 機構數據升級：**
在「機構透視」頁面新增：
1. **Premium/Discount**: 判斷價格貴賤。
2. **Key Level Table**: FVG/OB 精確報價表。
3. **Whale Level**: 最大量 K 線價格。
""")

# --- 3. 核心數據引擎 ---
@st.cache_data(ttl=3600)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- V9 指標 ---
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
        
        # WaveTrend
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        esa = ta.ema(tp, length=10)
        d = ta.ema((tp - esa).abs(), length=10)
        ci = (tp - esa) / (0.015 * d)
        df['WT1'] = ta.ema(ci, length=21)
        df['WT2'] = ta.sma(df['WT1'], length=4)
        
        # ADX & Volume
        adx = ta.adx(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx['ADX_14']
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']
        df['Body'] = abs(df['Close'] - df['Open'])
        
        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 戰術計算 (Retail) ---
def generate_execution_plan(df):
    last = df.iloc[-1]
    close = last['Close']
    trend_dir = last['Trend_Dir']
    stop = last['SuperTrend']
    
    recent_high = df['High'].tail(20).max()
    resistance = close * 1.05 if close >= recent_high else recent_high
    res_desc = "新高突破預測" if close >= recent_high else "前波高點壓力"
        
    risk = abs(close - stop)
    if trend_dir == 1:
        action = "🟢 做多 (BUY)"
        entry = close
        target = close + (risk * 2)
        trend_status = "多頭趨勢"
    else:
        action = "🔴 做空 (SELL)"
        entry = close
        target = close - (risk * 2)
        trend_status = "空頭趨勢"
        
    strength = "🔥 強勢" if last['ADX'] > 25 else "☁️ 震盪"
    return {"trend": trend_status, "strength": strength, "wt": last['WT1'], "action": action, "entry": entry, "target": target, "stop": stop, "resistance": resistance, "res_desc": res_desc}

def detect_retail_signals(df):
    signals = []
    start = max(0, len(df)-100)
    for i in range(start, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
        if curr['Vol_Ratio'] >= 2.0: signals.append({"date": date, "price": curr['High'], "text": "🔥VH", "color": "red", "ay": -40})
        if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
            if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']: signals.append({"date": date, "price": curr['Low'], "text": "🐂吞沒", "color": "green", "ay": 40})
        if curr['WT1'] < -50 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']: signals.append({"date": date, "price": curr['Low'] - curr['ATR'], "text": "💎", "color": "cyan", "ay": 25})
    return signals

# --- 5. 機構計算模組 (SMC V13 Advanced) ---
def calculate_smc_advanced(df):
    fvgs = []
    obs = []
    
    # A. 尋找 FVG 和 OB (邏輯同 V12)
    start = max(0, len(df)-60)
    for i in range(start, len(df)):
        # Bull FVG
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            fvgs.append({"type": "Bull FVG", "top": df['Low'].iloc[i], "bottom": df['High'].iloc[i-2], "date": df.index[i-1], "status": "Active"})
        # Bear FVG
        if df['High'].iloc[i] < df['Low'].iloc[i-2] and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
            fvgs.append({"type": "Bear FVG", "top": df['Low'].iloc[i-2], "bottom": df['High'].iloc[i], "date": df.index[i-1], "status": "Active"})
            
    for i in range(start, len(df)-2):
        # Bull OB
        if df['Low'].iloc[i] < df['Low'].iloc[i-1] and df['Low'].iloc[i] < df['Low'].iloc[i+1]:
            if df['Close'].iloc[i] < df['Open'].iloc[i]: # 陰線
                if df['Close'].iloc[i+1] > df['High'].iloc[i] or df['Close'].iloc[i+2] > df['High'].iloc[i]:
                    obs.append({"type": "Bull OB", "top": df['High'].iloc[i], "bottom": df['Low'].iloc[i], "date": df.index[i], "status": "Active"})

    # B. 鯨魚偵測 (Whale Detection) - 過去 30 天最大量
    recent_df = df.tail(30)
    max_vol_idx = recent_df['Volume'].idxmax()
    whale_candle = {
        "price": recent_df.loc[max_vol_idx, 'Close'],
        "volume": recent_df.loc[max_vol_idx, 'Volume'],
        "date": max_vol_idx,
        "type": "Whale"
    }

    # C. 市場結構 (Premium vs Discount)
    # 取過去 50 天的高低點作為 Range
    swing_high = df['High'].tail(50).max()
    swing_low = df['Low'].tail(50).min()
    current_price = df['Close'].iloc[-1]
    mid_point = (swing_high + swing_low) / 2
    
    # 斐波那契回調位 (Fibonacci Retracement)
    fib_618 = swing_low + 0.618 * (swing_high - swing_low) # 黃金回調位 (若是多頭)
    
    market_structure = {
        "range_high": swing_high,
        "range_low": swing_low,
        "mid_point": mid_point,
        "fib_618": fib_618,
        "zone": "🔴 溢價區 (Premium - 找賣點)" if current_price > mid_point else "🟢 折價區 (Discount - 找買點)"
    }

    return fvgs, obs, whale_candle, market_structure

# --- 主程式 UI ---
st.title(f"📊 {symbol} 雙核戰略系統 V13.0 (狙擊版)")
df = get_data(symbol)

if df is not None:
    
    tab_retail, tab_inst = st.tabs(["🚀 智能戰術 (執行點位)", "🏛️ 機構透視 (深度數據)"])
    
    # ==========================================
    # Tab 1: 智能戰術 (保持 V12)
    # ==========================================
    with tab_retail:
        plan = generate_execution_plan(df)
        st.caption("📡 戰場環境數據")
        e1, e2, e3, e4 = st.columns(4)
        e1.metric("市場趨勢", plan['trend'])
        e2.metric("趨勢強度", f"{df['ADX'].iloc[-1]:.1f}", plan['strength'])
        e3.metric("WaveTrend", f"{plan['wt']:.1f}")
        e4.metric("操作建議", plan['action'], delta_color="off")
        
        st.divider()
        st.subheader("📋 交易執行計劃")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("🎯 參與買入價", f"${plan['entry']:.2f}")
        p2.metric("💰 賣出獲利價", f"${plan['target']:.2f}")
        p3.metric("🚧 關鍵阻力位", f"${plan['resistance']:.2f}")
        p4.metric("🛡️ 智能止損", f"${plan['stop']:.2f}", delta_color="inverse")
        
        fig_v9 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        fig_v9.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_150'], line=dict(width=1, color='rgba(0,128,0,0.5)'), name="EMA 150"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(width=1, color='rgba(128,0,0,0.5)'), fill='tonexty', fillcolor='rgba(128,128,128,0.1)', name="EMA 雲"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], mode='lines', line=dict(color='orange', width=2, dash='dash'), name="SuperTrend"), row=1, col=1)
        fig_v9.add_hline(y=plan['resistance'], line_dash="dot", line_color="red", row=1, col=1)
        fig_v9.add_hline(y=plan['target'], line_dash="dot", line_color="green", row=1, col=1)
        
        signals = detect_retail_signals(df)
        annotations = [dict(x=s['date'], y=s['price'], text=s['text'], showarrow=True, ax=0, ay=s['ay'], font=dict(color=s['color'])) for s in signals]
        fig_v9.update_layout(height=700, xaxis_rangeslider_visible=False, annotations=annotations, template="plotly_dark", title="智能戰術圖表")
        
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT1'], line=dict(color='cyan'), name="WT 快線"), row=2, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT2'], line=dict(color='red', dash='dot'), name="WT 慢線"), row=2, col=1)
        fig_v9.add_hline(y=60, line_dash="dot", row=2, col=1); fig_v9.add_hline(y=-60, line_dash="dot", row=2, col=1)
        st.plotly_chart(fig_v9, use_container_width=True)

    # ==========================================
    # Tab 2: 機構透視 (V13 重磅升級)
    # ==========================================
    with tab_inst:
        fvgs, obs, whale, struct = calculate_smc_advanced(df)
        last_price = df['Close'].iloc[-1]

        # 1. 機構戰情面板
        st.subheader("🏛️ 機構戰情數據中心 (SMC Dashboard)")
        
        col_main1, col_main2, col_main3 = st.columns(3)
        
        # A. 價格位置 (Premium/Discount)
        col_main1.info(f"**目前市場位置**\n\n### {struct['zone']}")
        col_main1.caption(f"區間高點: ${struct['range_high']:.2f} | 低點: ${struct['range_low']:.2f}")

        # B. 鯨魚活動
        col_main2.warning(f"**🐳 鯨魚(最大量)入場價**\n\n### ${whale['price']:.2f}")
        col_main2.caption(f"發生日期: {whale['date'].strftime('%Y-%m-%d')} (近30日最大量)")
        
        # C. 最佳回調預測 (Fibonacci)
        col_main3.success(f"**黃金回調預測位 (0.618)**\n\n### ${struct['fib_618']:.2f}")
        col_main3.caption("機構最常掛單的「搭車點」")

        st.markdown("---")
        
        # 2. 關鍵價位清單 (Table)
        st.write("#### 🧱 機構關鍵價位清單 (Key Levels Cheat Sheet)")
        
        # 整理數據為 DataFrame
        table_data = []
        # 加入 OB
        for ob in obs[-3:]: # 只列出最近 3 個
            table_data.append({"類型": "🟦 Order Block (機構建倉)", "方向": "看漲支撐", "頂部價格": f"${ob['top']:.2f}", "底部價格": f"${ob['bottom']:.2f}", "日期": ob['date'].strftime('%Y-%m-%d')})
        # 加入 FVG
        for fvg in fvgs[-3:]:
            direction = "🟢 看漲支撐" if "Bull" in fvg['type'] else "🔴 看跌壓力"
            color = "Bull" if "Bull" in fvg['type'] else "Bear"
            table_data.append({"類型": f"Other ({fvg['type']})", "方向": direction, "頂部價格": f"${fvg['top']:.2f}", "底部價格": f"${fvg['bottom']:.2f}", "日期": fvg['date'].strftime('%Y-%m-%d')})
            
        st.dataframe(pd.DataFrame(table_data), use_container_width=True)
        st.caption("💡 **操作指引**：請將上述價格設為您的券商「到價提醒」。當價格回落至 **Order Block** 或 **Bull FVG** 時，是高勝率買點。")

        # 3. 機構圖表 (升級版)
        fig_v10 = go.Figure()
        fig_v10.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"))
        
        # 畫 FVG
        for box in fvgs:
            color = "rgba(0, 255, 0, 0.2)" if "Bull" in box['type'] else "rgba(255, 0, 0, 0.2)"
            fig_v10.add_shape(type="rect", x0=box['date'], y0=box['bottom'], x1=df.index[-1], y1=box['top'], line=dict(width=0), fillcolor=color, layer="below")
            
        # 畫 Order Blocks
        for ob in obs:
            fig_v10.add_shape(type="rect", x0=ob['date'], y0=ob['bottom'], x1=df.index[-1], y1=ob['top'], line=dict(color="blue", width=1, dash="dot"), fillcolor="rgba(0, 0, 255, 0.15)", layer="below")
            
        # 畫 鯨魚線
        fig_v10.add_hline(y=whale['price'], line_dash="solid", line_color="purple", line_width=2, annotation_text="🐳 Whale Entry", annotation_position="top right")

        # 畫 Fibonacci 0.618
        fig_v10.add_hline(y=struct['fib_618'], line_dash="dash", line_color="gold", line_width=2, annotation_text="Fib 0.618 (Golden Pocket)", annotation_position="bottom right")

        fig_v10.update_layout(height=750, xaxis_rangeslider_visible=False, title=f"{symbol} 機構深度透視圖 (FVG + OB + Whale)", template="plotly_dark")
        st.plotly_chart(fig_v10, use_container_width=True)

else:
    st.error("無法獲取數據")
