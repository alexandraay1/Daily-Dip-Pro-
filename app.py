import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 網頁設定 ---
st.set_page_config(page_title="Trend Catchers V14 | 量化修正版", layout="wide", page_icon="🦈")

# --- 2. 核心與密碼 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

def check_password():
    if not st.session_state.password_correct:
        st.markdown("## 🦈 Trend Catchers V14 (Quant Edition)")
        st.caption("核心升級：市場狀態過濾 (Regime Filter) | VPA 量價分析 | 回測引擎")
        password = st.text_input("輸入通行密碼", type="password")
        if st.button("Access Terminal"):
            if password == "VIP888":
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("❌ Access Denied")
        st.stop()

check_password()

# --- 側邊欄 ---
st.sidebar.title("🎛️ 量化控制台")
symbol = st.sidebar.text_input("美股代號", value="TSLA").upper() # 預設改為 TSLA 方便測試
timeframe = st.sidebar.selectbox("分析週期", ["Daily", "Weekly"], index=0)
st.sidebar.markdown("---")
st.sidebar.info("""
**V14 量化邏輯更新：**
1. **🛡️ 盤整過濾**：ADX < 20 或包絡線擠壓時，屏蔽突破信號。
2. **🐋 真鯨魚偵測**：排除長上影線的「出貨量」。
3. **💰 回測引擎**：驗證策略真實回報。
""")

# --- 3. 數據引擎 (優化版) ---
@st.cache_data(ttl=1800)
def get_data(ticker):
    try:
        # 下載更多數據以供回測
        df = yf.download(ticker, period="5y", progress=False) 
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 基礎均線 (只留機構最看重的兩條)
        df['EMA_50'] = ta.ema(df['Close'], length=50)   # 機構成本線
        df['EMA_200'] = ta.ema(df['Close'], length=200) # 牛熊分界線
        
        # 波動率與趨勢強度
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        adx = ta.adx(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx['ADX_14']
        
        # SuperTrend (作為動態止損)
        st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        # 處理不同版本的 pandas_ta 返回列名可能不同的問題
        st_col = [c for c in st_data.columns if "SUPERT_" in c][0]
        st_dir = [c for c in st_data.columns if "SUPERTd_" in c][0]
        df['SuperTrend'] = st_data[st_col]
        df['Trend_Dir'] = st_data[st_dir]
        
        # Bollinger Bands & Keltner Channels (用於偵測盤整擠壓)
        bb = ta.bbands(df['Close'], length=20, std=2)
        kc = ta.kc(df['High'], df['Low'], df['Close'], length=20, scalar=1.5)
        df['BB_Upper'] = bb['BBU_20_2.0']
        df['BB_Lower'] = bb['BBL_20_2.0']
        df['KC_Upper'] = kc['KCUe_20_1.5']
        df['KC_Lower'] = kc['KCLe_20_1.5']
        
        # Squeeze Logic: 當布林帶跑進 Keltner 通道內，代表極度壓縮 (變盤前兆)
        df['Squeeze_On'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])

        # WaveTrend (動能)
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        esa = ta.ema(tp, length=10)
        d = ta.ema((tp - esa).abs(), length=10)
        ci = (tp - esa) / (0.015 * d)
        df['WT1'] = ta.ema(ci, length=21)
        df['WT2'] = ta.sma(df['WT1'], length=4)
        
        # Volume
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']
        
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(e)
        return None

# --- 4. 智能分析模組 (Quant Filters) ---
def analyze_market_regime(df):
    last = df.iloc[-1]
    
    # 1. 判斷市場狀態 (Regime)
    if last['Squeeze_On']:
        regime = "😴 壓縮盤整 (變盤前兆)"
        status_color = "orange"
        can_trade = False
        advice = "市場波動極低，正在蓄力。**嚴禁追高殺低**，等待布林帶開口。"
    elif last['ADX'] < 20:
        regime = "☁️ 無趨勢震盪"
        status_color = "gray"
        can_trade = False
        advice = "ADX 低於 20，缺乏動能。適合區間低吸高拋，不宜做突破。"
    else:
        regime = "🔥 強趨勢行情"
        status_color = "green" if last['Trend_Dir'] == 1 else "red"
        can_trade = True
        advice = "動能充足。順著 SuperTrend 方向操作，尋找回調買點。"
        
    return regime, status_color, can_trade, advice

def get_valid_signals(df, can_trade):
    signals = []
    if not can_trade: return signals # 如果市場狀態不好，直接不給信號 (保護用戶)
    
    start = max(0, len(df)-60)
    for i in range(start, len(df)):
        curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
        
        # 1. 趨勢跟隨信號 (Trend Pullback)
        if curr['Trend_Dir'] == 1 and curr['WT1'] < -40 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
             signals.append({"date": date, "price": curr['Low'], "text": "💎趨勢回調買點", "color": "#00ff00", "ay": 30})

        # 2. 關鍵均線突破 (只看 EMA 50)
        if curr['Close'] > curr['EMA_50'] and prev['Close'] <= prev['EMA_50'] and curr['ADX'] > 20:
             signals.append({"date": date, "price": curr['Low'], "text": "🚀站上生命線", "color": "white", "ay": 40})
             
    return signals

def get_whale_zones(df):
    recent = df.tail(60).copy()
    recent['Body_Size'] = (recent['Close'] - recent['Open']).abs()
    recent['Total_Size'] = recent['High'] - recent['Low']
    
    mask = (recent['Volume'] > recent['Vol_SMA'] * 1.5) & \
           (recent['Body_Size'] > recent['Total_Size'] * 0.6) & \
           (recent['Close'] > recent['Open'])
           
    whales = recent[mask]
    
    zones = []
    if not whales.empty:
        last_whale = whales.iloc[-1]
        zones.append({
            "price": last_whale['Low'], 
            "top": last_whale['High'],
            "date": last_whale.name,
            "vol_ratio": last_whale['Vol_Ratio']
        })
    return zones

# --- 5. SMC 結構 ---
def get_smc_structure(df):
    last_fvg = None
    start = max(0, len(df)-40)
    for i in range(start, len(df)):
        if df['Low'].iloc[i] > df['High'].iloc[i-2] and df['Close'].iloc[i-1] > df['Open'].iloc[i-1]:
            last_fvg = {"top": df['Low'].iloc[i], "bottom": df['High'].iloc[i-2], "date": df.index[i-1]}
            
    swing_high = df['High'].tail(60).max()
    swing_low = df['Low'].tail(60).min()
    fib = swing_low + 0.618 * (swing_high - swing_low)
    
    return last_fvg, fib

# --- 6. V14 回測引擎 (Backtest Engine) ---
def run_backtest(df):
    st.markdown("## 💰 V14 策略回測報告")
    st.info("模擬條件：初始資金 $100,000 | 交易成本 0% | 依據 V14 嚴格信號執行")
    
    initial_capital = 100000.0
    equity = initial_capital
    position = 0
    entry_price = 0
    
    equity_curve = []
    trade_log = []
    
    # 預先計算每日是否可交易
    regime_list = []
    for i in range(len(df)):
        row = df.iloc[i]
        squeeze = (row['BB_Upper'] < row['KC_Upper']) and (row['BB_Lower'] > row['KC_Lower'])
        adx_ok = row['ADX'] > 20
        # 必須 ADX 強度夠，且沒有 Squeeze
        regime_list.append(adx_ok and not squeeze)
    
    df['Can_Trade'] = regime_list
    
    # 回測迴圈 (只測最近 2 年，避免數據過舊)
    start_idx = max(50, len(df) - 500) 
    
    for i in range(start_idx, len(df)-1):
        curr = df.iloc[i]
        nxt = df.iloc[i+1] # 用隔日開盤價成交
        date = df.index[i]
        
        # --- 賣出邏輯 ---
        if position > 0:
            # 止損條件: 跌破 SuperTrend 或 EMA 50
            stop_condition = (curr['Close'] < curr['SuperTrend']) or (curr['Close'] < curr['EMA_50'])
            
            if stop_condition:
                sell_price = nxt['Open']
                revenue = position * sell_price
                profit = revenue - (position * entry_price)
                profit_pct = (sell_price - entry_price) / entry_price * 100
                
                equity = revenue
                position = 0
                
                trade_log.append({
                    "Date": nxt.name, "Type": "SELL 🔴", 
                    "Price": sell_price, "Profit($)": profit, "Return(%)": profit_pct,
                    "Equity": equity
                })
        
        # --- 買入邏輯 ---
        elif position == 0 and curr['Can_Trade']:
            # 信號 A: WT 黃金交叉
            wt_signal = (curr['Trend_Dir'] == 1) and (curr['WT1'] < -40) and (curr['WT1'] > curr['WT2']) and (df.iloc[i-1]['WT1'] <= df.iloc[i-1]['WT2'])
            # 信號 B: 站上 EMA 50
            ema_signal = (curr['Close'] > curr['EMA_50']) and (df.iloc[i-1]['Close'] <= df.iloc[i-1]['EMA_50'])
            
            if wt_signal or ema_signal:
                buy_price = nxt['Open']
                position = equity / buy_price
                entry_price = buy_price
                equity = 0
                
                trade_log.append({
                    "Date": nxt.name, "Type": "BUY 🟢", 
                    "Price": buy_price, "Profit($)": 0, "Return(%)": 0,
                    "Equity": entry_price * position
                })
        
        # 紀錄淨值
        current_equity = equity if position == 0 else position * curr['Close']
        equity_curve.append({"Date": date, "Equity": current_equity})

    # 結算
    final_equity = equity if position == 0 else position * df.iloc[-1]['Close']
    total_return = (final_equity - initial_capital) / initial_capital * 100
    
    c1, c2, c3 = st.columns(3)
    c1.metric("初始本金", f"${initial_capital:,.0f}")
    c2.metric("最終淨值", f"${final_equity:,.0f}", f"{total_return:.2f}%")
    c3.metric("總交易次數", f"{len(trade_log)//2}")
    
    # 畫圖
    if equity_curve:
        ec_df = pd.DataFrame(equity_curve).set_index("Date")
        st.area_chart(ec_df)
    
    if trade_log:
        with st.expander("查看詳細交易紀錄"):
            st.dataframe(pd.DataFrame(trade_log))
    else:
        st.warning("在此期間內策略未觸發任何交易 (可能市場一直處於過濾狀態)")


# --- 主程式 UI ---
st.title(f"🦈 {symbol} 量化戰術終端 V14")
df = get_data(symbol)

if df is not None:
    
    # 1. 市場狀態儀表板
    regime, color, can_trade, advice = analyze_market_regime(df)
    
    with st.container():
        st.markdown("### 📡 Market Regime (市場狀態)")
        c1, c2, c3 = st.columns([1, 2, 1])
        c1.metric("當前狀態", regime, delta="可交易" if can_trade else "觀望", delta_color="normal" if can_trade else "off")
        c2.info(f"💡 **AI 戰術顧問**：{advice}")
        c3.metric("趨勢強度 (ADX)", f"{df['ADX'].iloc[-1]:.1f}")
        
    st.divider()

    # 定義 Tab (關鍵：tab1 在這裡定義)
    tab1, tab2 = st.tabs(["🚀 戰術圖表 (Tactical)", "🏛️ 機構數據 (Institutional)"])
    
    # --- Tab 1: 戰術圖表 ---
    with tab1:
        signals = get_valid_signals(df, can_trade)
        whale_zones = get_whale_zones(df)
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.03)
        
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange', width=2), name="EMA 50"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_200'], line=dict(color='blue', width=2), name="EMA 200"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], line=dict(color='gray', dash='dot', width=1), name="Trailing Stop"), row=1, col=1)
        
        if whale_zones:
            w = whale_zones[-1]
            fig.add_shape(type="rect", x0=w['date'], y0=w['price'], x1=df.index[-1], y1=w['top'], 
                         line=dict(width=0), fillcolor="rgba(128,0,128,0.2)", layer="below", row=1, col=1)
            fig.add_annotation(x=df.index[-1], y=w['top'], text=f"🐳 Whale Support", showarrow=False, xanchor="left", font=dict(color="purple"), row=1, col=1)

        annotations = []
        for s in signals:
            annotations.append(dict(x=s['date'], y=s['price'], text=s['text'], showarrow=True, arrowhead=2, ay=s['ay'], font=dict(color=s['color'], size=11, family="Arial Black")))
        
        colors = ['red' if s else 'gray' for s in df['Squeeze_On']]
        fig.add_trace(go.Bar(x=df.index, y=df['ADX'], marker_color=colors, name="ADX / Squeeze"), row=2, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="white", row=2, col=1)
        
        fig.update_layout(height=700, xaxis_rangeslider_visible=False, template="plotly_dark", annotations=annotations, title=f"{symbol} 量化戰術圖表")
        st.plotly_chart(fig, use_container_width=True)
        
        # --- 回測按鈕放在這裡 (正確的縮排) ---
        st.divider()
        st.markdown("### 📊 策略驗證")
        if st.button("🚀 執行 V14 模擬回測 ($100k Challenge)"):
            run_backtest(df)

    # --- Tab 2: 機構數據 ---
    with tab2:
        fvg, fib = get_smc_structure(df)
        last_close = df['Close'].iloc[-1]
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🧱 訂單流結構")
            if fvg:
                st.success(f"發現 Bull FVG")
                st.metric("買入區間", f"${fvg['top']:.2f} - ${fvg['bottom']:.2f}")
            else:
                st.warning("近期無明顯 FVG")
        with c2:
            st.subheader("📐 Fibonacci")
            st.metric("0.618 回調位", f"${fib:.2f}")

else:
    st.error("無法取得數據，請確認代號正確或稍後再試")
