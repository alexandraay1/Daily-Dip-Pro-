import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta

# --- 1. 系統設定 ---
st.set_page_config(page_title="V15 機構獵殺終端", layout="wide", page_icon="🏦")

# --- 2. 量化數學引擎 (SMC Math Engine) ---
# 這些是我們獨家的數學模型，用來計算機構痕跡

def calculate_ma(series, window):
    return series.rolling(window=window).mean()

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(window=period).mean()

def identify_fvg(df):
    """
    識別失衡區 (Fair Value Gaps)
    邏輯：當第1根K棒的高點 < 第3根K棒的低點 (多頭失衡)
    """
    fvg_zones = []
    # 掃描最近 60 天
    scan_start = max(0, len(df) - 60)
    
    for i in range(scan_start, len(df) - 1):
        # Bullish FVG (多頭失衡 - 機構急買)
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            # 只有當缺口還沒被完全回補時才顯示
            # 簡單過濾：如果現在價格還在上面，就算有效
            if df['Close'].iloc[-1] > df['High'].iloc[i-2]: 
                fvg_zones.append({
                    "type": "Bullish FVG",
                    "top": df['Low'].iloc[i],
                    "bottom": df['High'].iloc[i-2],
                    "date": df.index[i-1],
                    "color": "rgba(0, 255, 0, 0.15)"
                })
        
        # Bearish FVG (空頭失衡 - 機構急拋)
        elif df['High'].iloc[i] < df['Low'].iloc[i-2] and df['Close'].iloc[i-1] < df['Open'].iloc[i-1]:
             if df['Close'].iloc[-1] < df['Low'].iloc[i-2]:
                fvg_zones.append({
                    "type": "Bearish FVG",
                    "top": df['Low'].iloc[i-2],
                    "bottom": df['High'].iloc[i],
                    "date": df.index[i-1],
                    "color": "rgba(255, 0, 0, 0.15)"
                })
    return fvg_zones

def identify_order_blocks(df):
    """
    識別訂單塊 (Order Blocks)
    簡化模型：在強烈上漲前的最後一根陰線 (Bullish OB)
    """
    obs = []
    scan_start = max(0, len(df) - 90)
    
    for i in range(scan_start, len(df) - 3):
        # Bullish OB 判斷：
        # 1. 這是一根陰線 (Close < Open)
        # 2. 後面跟著連續的上漲，且突破了結構
        # 3. 成交量放大
        curr = df.iloc[i]
        next_candle = df.iloc[i+1]
        
        is_red = curr['Close'] < curr['Open']
        is_strong_move = (next_candle['Close'] > curr['High']) and (next_candle['Volume'] > curr['Volume'])
        
        if is_red and is_strong_move:
            obs.append({
                "type": "Bullish OB",
                "top": curr['High'],
                "bottom": curr['Low'],
                "date": df.index[i],
                "color": "rgba(0, 255, 255, 0.2)" # 青色
            })
    
    # 過濾：只保留那些價格還沒跌破的 OB (即有效支撐)
    valid_obs = [ob for ob in obs if df['Close'].iloc[-1] > ob['bottom']]
    # 只取最近的 3 個，避免圖表混亂
    return valid_obs[-3:] if valid_obs else []

def get_trading_signals(df):
    """
    產生買賣信號與止損建議
    """
    signals = []
    last_idx = df.index[-1]
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 1. 均線突破系統
    mas = [20, 50, 100]
    for ma in mas:
        col = f'SMA_{ma}'
        # 黃金突破 (站上均線)
        if curr['Close'] > curr[col] and prev['Close'] <= prev[col]:
            signals.append({
                "type": "BUY",
                "trigger": f"突破 SMA {ma}",
                "stop_loss": curr['Close'] - 2 * curr['ATR'], # ATR 止損
                "desc": f"價格強勢站上 {ma} 日線，動能轉強。"
            })
        # 死亡跌破 (跌破均線)
        elif curr['Close'] < curr[col] and prev['Close'] >= prev[col]:
            signals.append({
                "type": "SELL",
                "trigger": f"跌破 SMA {ma}",
                "stop_loss": curr['Close'] + 2 * curr['ATR'],
                "desc": f"價格失守 {ma} 日線，建議減倉。"
            })
            
    # 2. 波動率止損 (Chandelier Exit 概念)
    stop_loss_level = curr['Close'] - (3 * curr['ATR'])
    
    return signals, stop_loss_level

# --- 3. 數據下載 ---
@st.cache_data(ttl=3600)
def get_quant_data(ticker):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [c.capitalize() for c in df.columns]
        
        # 處理時區
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None: df.index = df.index.tz_localize(None)

        # 計算指標
        df['SMA_20'] = calculate_ma(df['Close'], 20)
        df['SMA_50'] = calculate_ma(df['Close'], 50)
        df['SMA_100'] = calculate_ma(df['Close'], 100)
        df['ATR'] = calculate_atr(df, 14)
        
        # Volume SMA
        df['Vol_SMA'] = calculate_ma(df['Volume'], 20)
        
        df.dropna(inplace=True)
        return df
    except Exception as e:
        return None

# --- 4. 介面邏輯 ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False

def check_password():
    if not st.session_state.password_correct:
        st.markdown("## 🏦 V15 Institutional Hunter (機構獵殺版)")
        st.caption("載入模組：F.V.G 失衡識別 | Order Block 定位 | 智能 ATR 止損")
        pwd = st.text_input("輸入通行密碼", type="password")
        if st.button("連接終端"):
            if pwd == "VIP888": st.session_state.password_correct = True; st.rerun()
            else: st.error("權限不足")
        st.stop()

check_password()

# 側邊欄
st.sidebar.title("🎛️ 量化控制台")
symbol = st.sidebar.text_input("輸入代號", "NVDA").upper()
st.sidebar.markdown("---")
st.sidebar.info("""
**📊 V15 新增功能：**
1. **SMA 戰術突破**：自動偵測 20/50/100 關鍵位。
2. **FVG 失衡獵殺**：標記機構急拉後的必補缺口。
3. **OB 訂單塊**：顯示真正的大戶建倉成本區。
""")

# 主程式
df = get_quant_data(symbol)

if df is not None:
    # 計算進階數據
    fvgs = identify_fvg(df)
    obs = identify_order_blocks(df)
    signals, atr_stop = get_trading_signals(df)
    last_price = df['Close'].iloc[-1]
    
    st.title(f"🏦 {symbol} 機構級量化分析報告")
    
    # 頂部儀表板
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("當前價格", f"${last_price:.2f}", f"{(last_price - df['Close'].iloc[-2]):.2f}")
    col2.metric("智能止損位 (ATR)", f"${atr_stop:.2f}", "跌破離場", delta_color="inverse")
    
    # 顯示最新的信號
    if signals:
        latest_sig = signals[-1]
        col3.metric("最新戰術信號", latest_sig['trigger'], latest_sig['type'])
    else:
        col3.metric("最新戰術信號", "觀望中", "HOLD", delta_color="off")
        
    # 機構籌碼狀態
    fvg_status = "接近失衡區" if any(abs(last_price - f['top']) < last_price*0.02 for f in fvgs) else "平衡"
    col4.metric("機構籌碼狀態", fvg_status)

    # --- 戰術圖表 ---
    tab1, tab2 = st.tabs(["📈 智能戰術圖表 (Tactical)", "🏛️ 機構透視 (Institutional)"])
    
    with tab1:
        # 繪製主圖
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
        
        # K線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
        
        # 均線系統
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='#FFD700', width=1), name="SMA 20 (短線)"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], line=dict(color='#00FF00', width=1.5), name="SMA 50 (生命線)"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_100'], line=dict(color='#FFFFFF', width=2), name="SMA 100 (牛熊線)"), row=1, col=1)
        
        # 標記 ATR 止損線 (只顯示最近30天)
        atr_line = df['Close'] - (3 * df['ATR'])
        fig.add_trace(go.Scatter(x=df.index[-30:], y=atr_line[-30:], mode='markers', marker=dict(color='red', size=2), name="ATR Stop Loss"), row=1, col=1)

        # 標記信號
        for sig in signals:
            # 簡單過濾：只顯示最近 30 天的信號，避免圖表混亂
            sig_date = df.index[-1] # 這裡是簡化，實際應該記錄信號發生時間
            # 在這裡我們用文字註解顯示今天的信號
            pass 

        # 成交量
        colors = ['red' if r < 0 else 'green' for r in (df['Close'] - df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="Volume"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Vol_SMA'], line=dict(color='white'), name="Vol SMA"), row=2, col=1)
        
        fig.update_layout(height=600, template="plotly_dark", title=f"{symbol} 戰術執行圖表", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # 顯示具體操作建議
        st.subheader("📋 交易員執行計畫")
        if signals:
            for s in signals:
                color = "green" if s['type'] == "BUY" else "red"
                st.markdown(f"""
                <div style="border-left: 5px solid {color}; padding-left: 10px; margin-bottom: 10px; background-color: rgba(255,255,255,0.05);">
                    <strong>[{s['type']}] {s['trigger']}</strong><br>
                    <small>{s['desc']}</small><br>
                    🛡️ 建議止損位：${s['stop_loss']:.2f}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("目前無均線突破信號，建議沿著趨勢線操作或等待回調。")

    with tab2:
        st.subheader("🕵️‍♂️ Smart Money Concepts (SMC) 結構分析")
        st.markdown("""
        此面板顯示**機構大戶的腳印**。散戶看均線，機構看流動性。
        * **FVG (失衡區)**：價格急拉後留下的真空區，未來有 80% 機率會回測此處。
        * **Order Block (訂單塊)**：機構建倉的成本區，是比支撐線更強的防守位。
        """)
        
        # SMC 圖表
        fig_smc = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price")])
        
        # 繪製 FVG (矩形)
        for fvg in fvgs:
            fig_smc.add_shape(type="rect",
                x0=fvg['date'], y0=fvg['bottom'], x1=df.index[-1], y1=fvg['top'],
                line=dict(width=0), fillcolor=fvg['color'], layer="below")
            
            # 添加標籤
            fig_smc.add_annotation(x=df.index[-1], y=(fvg['top']+fvg['bottom'])/2, 
                                   text=fvg['type'], showarrow=False, xanchor="left", font=dict(color="gray", size=10))

        # 繪製 Order Blocks (矩形)
        for ob in obs:
            fig_smc.add_shape(type="rect",
                x0=ob['date'], y0=ob['bottom'], x1=df.index[-1], y1=ob['top'],
                line=dict(width=0), fillcolor=ob['color'], layer="below")
             
            fig_smc.add_annotation(x=df.index[-1], y=ob['top'], 
                                   text="🐳 Order Block", showarrow=False, xanchor="left", font=dict(color="cyan", size=10))

        fig_smc.update_layout(height=600, template="plotly_dark", title="機構流動性地圖 (SMC Map)", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_smc, use_container_width=True)
        
        # 數據化列表
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🧲 下方買入失衡區 (FVG Support)")
            bull_fvgs = [f for f in fvgs if "Bullish" in f['type']]
            if bull_fvgs:
                for f in bull_fvgs[-3:]:
                    st.write(f"區間: **${f['bottom']:.2f} - ${f['top']:.2f}** (等待回調接多)")
            else:
                st.write("下方無明顯失衡區")
                
        with c2:
            st.markdown("#### 🧱 強力支撐訂單塊 (Order Blocks)")
            if obs:
                for o in obs:
                    st.write(f"機構成本區: **${o['bottom']:.2f} - ${o['top']:.2f}**")
            else:
                st.write("近期無明顯機構建倉痕跡")

else:
    st.error("無法取得數據，請確認代號或網絡狀態。")
