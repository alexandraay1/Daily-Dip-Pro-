import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import traceback # 用來抓出真正的兇手

# --- 0. 全局設定與防崩潰機制 ---
st.set_page_config(page_title="Trend Catchers V14.1", layout="wide", page_icon="🦈")

# 這裡捕捉所有頂層錯誤，防止 "Oh no" 藍屏
try:
    # --- 1. 核心邏輯區 ---

    # 密碼驗證
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    def check_password():
        if not st.session_state.password_correct:
            st.markdown("## 🦈 Trend Catchers V14 (Quant Edition)")
            st.caption("系統重置完成 | 數據源：YFinance API | 引擎：Pandas-TA")
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
    symbol = st.sidebar.text_input("美股代號", value="TSLA").upper()
    
    st.sidebar.info("""
    **V14.1 系統狀態：**
    ✅ Numpy 版本兼容模式
    ✅ Yahoo 數據結構自動修復
    ✅ 錯誤追蹤開啟
    """)

    # --- 2. 數據引擎 (最強容錯版) ---
    @st.cache_data(ttl=1800)
    def get_data(ticker):
        # 1. 下載數據 (強制關閉自動調整，手動處理)
        # 這是最原始、最不容易出錯的下載方式
        data = yf.download(ticker, period="2y", progress=False, auto_adjust=False)
        
        # 2. 數據結構暴力清洗 (解決 MultiIndex 問題)
        if data is None or data.empty:
            return None, "Yahoo 回傳空數據 (可能代號錯誤或 IP 限制)"

        # 如果欄位是多層索引 (MultiIndex)，強制取第一層
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        
        # 確保必要的欄位都在 (不區分大小寫)
        data.columns = [c.capitalize() for c in data.columns]
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in data.columns for col in required_cols):
             return None, f"數據缺少必要欄位，現有欄位: {list(data.columns)}"

        # 移除時區 (Pandas-TA 痛點)
        data.index = pd.to_datetime(data.index)
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        # 3. 指標計算 (分開 try-catch 以便定位)
        try:
            df = data.copy()
            # 均線
            df['EMA_50'] = ta.ema(df['Close'], length=50)
            df['EMA_200'] = ta.ema(df['Close'], length=200)
            
            # ADX
            adx = ta.adx(df['High'], df['Low'], df['Close'])
            df['ADX'] = adx['ADX_14'] if adx is not None else 0
            
            # SuperTrend (最常報錯的地方)
            st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
            if st_data is not None:
                # 抓取第一欄(趨勢線)和第二欄(方向)
                df['SuperTrend'] = st_data.iloc[:, 0]
                df['Trend_Dir'] = st_data.iloc[:, 1]
            else:
                df['SuperTrend'] = df['Close']
                df['Trend_Dir'] = 1

            # Squeeze (BB + KC)
            bb = ta.bbands(df['Close'], length=20, std=2)
            kc = ta.kc(df['High'], df['Low'], df['Close'], length=20, scalar=1.5)
            
            if bb is not None and kc is not None:
                df['BB_Upper'] = bb.iloc[:, 0] # BBL
                df['BB_Lower'] = bb.iloc[:, 2] # BBU
                # 校正順序
                if df['BB_Upper'].iloc[-1] < df['BB_Lower'].iloc[-1]:
                     temp = df['BB_Upper']
                     df['BB_Upper'] = df['BB_Lower']
                     df['BB_Lower'] = temp
                     
                df['KC_Upper'] = kc.iloc[:, 0]
                df['KC_Lower'] = kc.iloc[:, 2]
                df['Squeeze_On'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])
            else:
                df['Squeeze_On'] = False

            # WaveTrend
            tp = (df['High'] + df['Low'] + df['Close']) / 3
            esa = ta.ema(tp, length=10)
            d = ta.ema((tp - esa).abs(), length=10)
            ci = (tp - esa) / (0.015 * d)
            df['WT1'] = ta.ema(ci, length=21)
            df['WT2'] = ta.sma(df['WT1'], length=4)
            
            df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
            
            df.dropna(inplace=True)
            return df, None # 成功回傳

        except Exception as e:
            return None, f"指標計算失敗: {str(e)}"

    # --- 3. 輔助函數 ---
    def analyze_market_regime(df):
        last = df.iloc[-1]
        if last['Squeeze_On']:
            return "😴 壓縮盤整", "orange", False, "市場蓄力中，嚴禁追高殺低。"
        elif last['ADX'] < 20:
            return "☁️ 無趨勢震盪", "gray", False, "動能不足，適合區間操作。"
        else:
            return "🔥 強趨勢行情", "green", True, "動能充足，順勢操作。"

    def get_valid_signals(df, can_trade):
        signals = []
        if not can_trade: return signals
        for i in range(max(0, len(df)-60), len(df)):
            curr = df.iloc[i]; prev = df.iloc[i-1]; date = df.index[i]
            # 趨勢回調
            if curr['Trend_Dir'] == 1 and curr['WT1'] < -40 and curr['WT1'] > curr['WT2'] and prev['WT1'] <= prev['WT2']:
                signals.append({"date": date, "price": curr['Low'], "text": "💎回調買點", "color": "#00ff00", "ay": 30})
            # 突破 EMA50
            if curr['Close'] > curr['EMA_50'] and prev['Close'] <= prev['EMA_50'] and curr['ADX'] > 20:
                signals.append({"date": date, "price": curr['Low'], "text": "🚀突破", "color": "white", "ay": 40})
        return signals

    def run_backtest(df):
        initial = 100000
        equity = initial
        position = 0
        entry_price = 0
        log = []
        
        # 簡單計算可交易日
        df['Can_Trade'] = (df['ADX'] > 20) & (~df['Squeeze_On'])
        
        for i in range(50, len(df)-1):
            curr = df.iloc[i]; nxt = df.iloc[i+1]
            
            # 賣出
            if position > 0:
                if curr['Close'] < curr['SuperTrend']: # 簡單止損
                    profit = (nxt['Open'] - entry_price) * position
                    equity = nxt['Open'] * position
                    log.append({"Date": nxt.name, "Type": "SELL", "Equity": equity})
                    position = 0
            
            # 買入
            elif position == 0 and curr['Can_Trade']:
                if curr['Close'] > curr['EMA_50'] and df.iloc[i-1]['Close'] <= df.iloc[i-1]['EMA_50']:
                    position = equity / nxt['Open']
                    entry_price = nxt['Open']
                    equity = 0
                    log.append({"Date": nxt.name, "Type": "BUY", "Equity": initial}) # 暫存

        final_val = equity if position == 0 else position * df.iloc[-1]['Close']
        ret = (final_val - initial) / initial * 100
        st.success(f"回測結果: 最終淨值 ${final_val:,.0f} ({ret:.2f}%)")
        if log: st.dataframe(pd.DataFrame(log))

    # --- 4. UI 主程式 ---
    st.title(f"🦈 {symbol} 量化戰術終端 V14.1")
    
    # 執行數據下載
    df, error_msg = get_data(symbol)
    
    if df is None:
        st.error(f"⚠️ 無法顯示圖表")
        st.code(error_msg, language="text") # 顯示具體錯誤
        st.warning("建議：如果是 Render/Cloud 環境，嘗試重新整理或稍後再試。")
    else:
        # 顯示儀表板
        regime, color, can_trade, advice = analyze_market_regime(df)
        st.markdown(f"### 📡 狀態：:{color}[{regime}]")
        st.info(advice)
        
        # 繪圖
        tab1, tab2 = st.tabs(["戰術圖表", "回測數據"])
        
        with tab1:
            signals = get_valid_signals(df, can_trade)
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='orange'), name="EMA 50"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['SuperTrend'], line=dict(color='blue', dash='dot'), name="SuperTrend"), row=1, col=1)
            
            # 信號
            annotations = []
            for s in signals:
                annotations.append(dict(x=s['date'], y=s['price'], text=s['text'], showarrow=True, ay=s['ay']))
            
            fig.add_trace(go.Bar(x=df.index, y=df['ADX'], name="ADX"), row=2, col=1)
            fig.update_layout(height=600, xaxis_rangeslider_visible=False, annotations=annotations)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            if st.button("執行 V14 回測"):
                run_backtest(df)

except Exception as e:
    # 這是最後的防線：捕捉所有未知的錯誤
    st.error("💣 程式發生嚴重錯誤 (Fatal Error)")
    st.markdown(f"**錯誤類型:** `{type(e).__name__}`")
    st.markdown(f"**錯誤訊息:** `{str(e)}`")
    st.markdown("### 詳細追蹤 (Traceback):")
    st.code(traceback.format_exc())
