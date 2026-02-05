import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 雙核戰略系統 V13.1", layout="wide")

# --- 2. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 雙核戰略系統 V13.1 (增強版)")
        st.caption("新增：均線突破信號 (MA Breakout) | 關鍵阻力位標示")
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
**V13.1 更新日誌：**
1. **🚀 智能戰術**：
   - 新增 EMA 20/50/100 突破提示。
   - 自動標示近期關鍵阻力位。
   
2. **🏛️ 機構透視** (保持 V13)：
   - 繼續提供 FVG、Order Block、鯨魚單。
""")

# --- 3. 核心數據引擎 ---
@st.cache_data(ttl=3600)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # --- 技術指標 ---
        # 均線組
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['EMA_100'] = ta.ema(df['Close'], length=100)
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
        
        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 戰術信號 (增強版：加入 MA 突破) ---
def detect_enhanced_signals(df):
    signals = []
    # 只分析最近 100 天
    start = max(0, len(df)-100)
    
    # 計算近 30 天的高點作為阻力
    recent_high = df['High'].tail(30).max()
    
    for i in range(start, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
        
        # A. 原有信號
        # 1. VH 爆量
        if curr['Vol_Ratio'] >= 2.0:
            signals.append({"date": date, "price": curr['High'], "text": "🔥VH", "color": "red", "ay": -45})
        # 2. 吞沒
        if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
            if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']:
                signals.append({"date": date, "price": curr['Low'], "text": "🐂吞沒", "color": "green", "ay": 45})
        # 3. WT 鑽石
        if curr['WT1'] < -50 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
            signals.append({"date": date, "price": curr['Low'] - curr['ATR'], "text": "💎", "color": "cyan", "ay": 30})

        # B. 新增：均線突破信號 (MA Crossover)
        # 突破 EMA 20
        if curr['Close'] > curr['EMA_20'] and prev['Close'] <= prev['EMA_20']:
             signals.append({"date": date, "price": curr['EMA_20'], "text": "🚀破20線", "color": "yellow", "ay": 20})
        elif curr['Close'] < curr['EMA_20'] and prev['Close'] >= prev['EMA_20']:
             signals.append({"date": date, "price": curr['EMA_20'], "text": "⚠️失20線", "color": "orange", "ay": -20})
             
        # 突破 EMA 50 (重要強弱分界)
        if curr['Close'] > curr['EMA_50'] and prev['Close'] <= prev['EMA_50']:
             signals.append({"date": date, "price": curr['EMA_50'], "text": "⚡站上50線", "color": "white", "ay": 25})
             
        # 突破 EMA 100 (長期趨勢)
        if curr['Close'] > curr['EMA_100'] and prev['Close'] <= prev['EMA_100']:
             signals.append({"date": date, "price": curr['EMA_100'], "text": "🦅牛市啟動(破100)", "color": "magenta", "ay": 30})

    return signals, recent_high

# --- 5. 機構計算模組 (保持 V13) ---
def calculate_smc_advanced(df):
    fvgs = []
    obs = []
    start = max(0, len(df)-60)
    for i in range(start, len(df)):
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            fvgs.append({"type": "Bull FVG", "top": df['Low'].iloc[i], "bottom": df['High'].iloc[i-2], "date": df.index[i-1]})
        if df['High'].iloc[i] < df['Low'].iloc[i-2] and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
            fvgs.append({"type": "Bear FVG", "top": df['Low'].iloc[i-2], "bottom": df['High'].iloc[i], "date": df.index[i-1]})
            
    for i in range(start, len(df)-2):
        if df['Low'].iloc[i] < df['Low'].iloc[i-1] and df['Low'].iloc[i] < df['Low'].iloc[i+1]:
            if df['Close'].iloc[i] < df['Open'].iloc[i]: 
                if df['Close'].iloc[i+1] > df['High'].iloc[i] or df['Close'].iloc[i+2] > df['High'].iloc[i]:
                    obs.append({"type": "Bull OB", "top": df['High'].iloc[i], "bottom": df['Low'].iloc[i], "date": df.index[i]})

    recent_df = df.tail(30)
    max_vol_idx = recent_df['Volume'].idxmax()
    whale_candle = {"price": recent_df.loc[max_vol_idx, 'Close'], "date": max_vol_idx}

    swing_high = df['High'].tail(50).max()
    swing_low = df['Low'].tail(50).min()
    current_price = df['Close'].iloc[-1]
    mid_point = (swing_high + swing_low) / 2
    market_structure = {
        "range_high": swing_high, "range_low": swing_low,
        "fib_618": swing_low + 0.618 * (swing_high - swing_low),
        "zone": "🔴 溢價區 (Premium)" if current_price > mid_point else "🟢 折價區 (Discount)"
    }
    return fvgs, obs, whale_candle, market_structure

# --- 主程式 UI ---
st.title(f"📊 {symbol} 雙核戰略系統 V13.1")
df = get_data(symbol)

if df is not None:
    
    tab_retail, tab_inst = st.tabs(["🚀 智能戰術 (技術增強版)", "🏛️ 機構透視 (深度數據)"])
    
    # ==========================================
    # Tab 1: 智能戰術 (增強版)
    # ==========================================
    with tab_retail:
        # 計算戰術數據
        last_close = df['Close'].iloc[-1]
        ema20 = df['EMA_20'].iloc[-1]
        ema50 = df['EMA_50'].iloc[-1]
        ema100 = df['EMA_100'].iloc[-1]
        stop_loss = df['SuperTrend'].iloc[-1]
        
        # 1. 頂部狀態列
        st.subheader("📡 技術指標雷達 (Technical Radar)")
        c1, c2, c3, c4 = st.columns(4)
        
        # 判斷均線狀態
        ma_status = "多頭排列 🚀" if last_close > ema20 > ema50 else "震盪整理 ⚖️"
        if last_close < ema20 and last_close < ema50: ma_status = "空頭壓制 🔴"
        
        c1.metric("市場趨勢", ma_status)
        c2.metric("趨勢強度 (ADX)", f"{df['ADX'].iloc[-1]:.1f}")
        c3.metric("WaveTrend 動能", f"{df['WT1'].iloc[-1]:.1f}")
        c4.metric("智能止損 (SuperTrend)", f"${stop_loss:.2f}")

        # 2. 均線檢核表 (Checklist)
        st.markdown(f"""
        **均線攻防戰：**
        * 短線 (EMA 20): **${ema20:.2f}** ({'✅ 站上' if last_close > ema20 else '❌ 跌破'})
        * 中線 (EMA 50): **${ema50:.2f}** ({'✅ 站上' if last_close > ema50 else '❌ 跌破'}) - *生命線*
        * 長線 (EMA 100): **${ema100:.2f}** ({'✅ 站上' if last_close > ema100 else '❌ 跌破'}) - *牛熊分界*
        """)

        # 3. 繪圖
        fig_v9 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        
        # K線
        fig_v9.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"), row=1, col=1)
        
        # 均線組 (視覺化)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], line=dict(color='yellow', width=1), name="EMA 20"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=1.5), name="EMA 50"), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_100'], line=dict(color='blue', width=1.5), name="EMA 100"), row=1, col=1)
        
        # 雲帶 (保留背景)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_150'], line=dict(width=0, color='rgba(0,128,0,0)'), showlegend=False), row=1, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(width=0, color='rgba(128,0,0,0)'), fill='tonexty', fillcolor='rgba(128,128,128,0.1)', name="長線雲帶"), row=1, col=1)
        
        # SuperTrend (虛線)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], mode='lines', line=dict(color='gray', width=1, dash='dash'), name="SuperTrend止損"), row=1, col=1)

        # 取得信號與阻力位
        signals, res_price = detect_enhanced_signals(df)
        
        # 畫阻力線
        fig_v9.add_hline(y=res_price, line_dash="solid", line_color="red", line_width=1, annotation_text=f"近期關鍵阻力 ${res_price:.2f}", annotation_position="top right", row=1, col=1)

        # 標註信號
        annotations = []
        for s in signals:
            annotations.append(dict(
                x=s['date'], y=s['price'], xref="x", yref="y",
                text=s['text'], showarrow=True, arrowhead=2, ax=0, ay=s['ay'],
                font=dict(color=s['color'], size=10, family="Arial Black")
            ))
        
        # 副圖 (WaveTrend)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT1'], line=dict(color='cyan'), name="WT 快線"), row=2, col=1)
        fig_v9.add_trace(go.Scatter(x=df.index, y=df['WT2'], line=dict(color='red', dash='dot'), name="WT 慢線"), row=2, col=1)
        fig_v9.add_hline(y=60, line_dash="dot", row=2, col=1); fig_v9.add_hline(y=-60, line_dash="dot", row=2, col=1)

        fig_v9.update_layout(height=700, xaxis_rangeslider_visible=False, title=f"{symbol} 智能戰術圖表 (含均線信號)", annotations=annotations, template="plotly_dark")
        st.plotly_chart(fig_v9, use_container_width=True)
        
        st.info("💡 **操作指引**：當 K 線出現「🚀 破20線」且下方有「💎」符號時，為強烈短線買入信號。若跌破紅色的「關鍵阻力線」後回測不過，則視為賣出信號。")

    # ==========================================
    # Tab 2: 機構透視 (保留原汁原味 V13)
    # ==========================================
    with tab_inst:
        fvgs, obs, whale, struct = calculate_smc_advanced(df)
        
        st.subheader("🏛️ 機構戰情數據中心 (SMC Dashboard)")
        c1, c2, c3 = st.columns(3)
        c1.info(f"**市場位置**\n\n### {struct['zone']}")
        c2.warning(f"**🐳 鯨魚入場價**\n\n### ${whale['price']:.2f}")
        c3.success(f"**黃金回調 (0.618)**\n\n### ${struct['fib_618']:.2f}")
        
        st.markdown("---")
        st.write("#### 🧱 機構關鍵價位清單")
        table_data = []
        for ob in obs[-3:]: table_data.append({"類型": "🟦 Order Block", "方向": "看漲支撐", "頂部": f"${ob['top']:.2f}", "底部": f"${ob['bottom']:.2f}", "日期": ob['date'].strftime('%Y-%m-%d')})
        for fvg in fvgs[-3:]: table_data.append({"類型": f"Other ({fvg['type']})", "方向": "支撐/壓力", "頂部": f"${fvg['top']:.2f}", "底部": f"${fvg['bottom']:.2f}", "日期": fvg['date'].strftime('%Y-%m-%d')})
        st.dataframe(pd.DataFrame(table_data), use_container_width=True)
        
        fig_v10 = go.Figure()
        fig_v10.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"))
        for box in fvgs:
            color = "rgba(0, 255, 0, 0.2)" if "Bull" in box['type'] else "rgba(255, 0, 0, 0.2)"
            fig_v10.add_shape(type="rect", x0=box['date'], y0=box['bottom'], x1=df.index[-1], y1=box['top'], line=dict(width=0), fillcolor=color, layer="below")
        for ob in obs:
            fig_v10.add_shape(type="rect", x0=ob['date'], y0=ob['bottom'], x1=df.index[-1], y1=ob['top'], line=dict(color="blue", width=1, dash="dot"), fillcolor="rgba(0, 0, 255, 0.15)", layer="below")
        fig_v10.add_hline(y=whale['price'], line_color="purple", annotation_text="🐳 Whale Entry")
        fig_v10.add_hline(y=struct['fib_618'], line_dash="dash", line_color="gold", annotation_text="Fib 0.618")
        fig_v10.update_layout(height=750, xaxis_rangeslider_visible=False, title=f"{symbol} 機構透視圖", template="plotly_dark")
        st.plotly_chart(fig_v10, use_container_width=True)

else:
    st.error("無法獲取數據")
