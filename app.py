import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import plotly.graph_objects as go

# --- 1. 網頁設定 ---
st.set_page_config(page_title="VIP 全方位戰術系統 V8.0", layout="wide")

# --- 2. 密碼鎖 (維持不變) ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.markdown("## 🔒 VIP 全方位戰術系統")
        st.caption("含：全形態識別 + VH 爆量 + 精準點位")
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
st.sidebar.title("💎 戰術控制台")
symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()
st.sidebar.markdown("---")
st.sidebar.markdown("""
**圖表標註圖例：**
- 🔥 **VH**: 爆量異動
- 🐂 **Bull**: 看漲吞沒
- 🐻 **Bear**: 看跌吞沒
- 🔨 **Ham**: 錘頭線 (底)
- 🧣 **Hang**: 上吊線 (頂)
- ☄️ **Shoot**: 射擊之星 (頂)
- 🌤️ **InvHam**: 倒錘頭 (底)
- 🌅 **M-Star**: 晨星
- 🌃 **E-Star**: 黃昏之星
- ➕ **Doji**: 十字星
""")

# --- 3. 核心數據處理 ---
def get_data(ticker):
    try:
        df = yf.download(ticker, period="1y", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        # 成交量
        df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
        df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']

        df.dropna(inplace=True)
        return df
    except:
        return None

# --- 4. 全形態識別引擎 (核心升級) ---
def detect_all_patterns(df):
    signals = [] 
    
    # 為了計算平均實體大小 (判斷十字星用)
    df['Body'] = abs(df['Close'] - df['Open'])
    avg_body = df['Body'].rolling(20).mean()
    
    # 遍歷最後 60 天 (保持圖表清晰)
    start_idx = max(2, len(df) - 60)
    
    for i in range(start_idx, len(df)):
        curr = df.iloc[i]     # 今天
        prev = df.iloc[i-1]   # 昨天
        prev2 = df.iloc[i-2]  # 前天
        date = df.index[i]
        
        # K線特徵
        body = curr['Body']
        upper_shadow = curr['High'] - max(curr['Close'], curr['Open'])
        lower_shadow = min(curr['Close'], curr['Open']) - curr['Low']
        mean_body = avg_body.iloc[i]
        
        # --- A. 成交量異動 (VH) ---
        if curr['Vol_Ratio'] >= 2.0:
            signals.append({
                "date": date, "price": curr['High'], "type": "VH", 
                "text": "🔥VH", "color": "red", "desc": f"🔥 爆量異動 ({curr['Vol_Ratio']:.1f}x)"
            })

        # --- B. 吞沒形態 (Engulfing) ---
        # 1. 看漲吞沒
        if curr['Close'] > curr['Open'] and prev['Close'] < prev['Open']:
            if curr['Close'] > prev['Open'] and curr['Open'] < prev['Close']:
                signals.append({
                    "date": date, "price": curr['Low'], "type": "Bull_Engulf", 
                    "text": "🐂吞沒", "color": "green", "desc": "🐂 看漲吞沒 (Bullish Engulfing)"
                })
        
        # 2. 看跌吞沒
        if curr['Close'] < curr['Open'] and prev['Close'] > prev['Open']:
            if curr['Close'] < prev['Open'] and curr['Open'] > prev['Close']:
                signals.append({
                    "date": date, "price": curr['High'], "type": "Bear_Engulf", 
                    "text": "🐻吞沒", "color": "red", "desc": "🐻 看跌吞沒 (Bearish Engulfing)"
                })

        # --- C. 錘頭與上吊 (Hammer / Hanging Man) ---
        # 特徵：實體小，下影線長 (>2倍實體)，上影線短
        if lower_shadow > 2 * body and upper_shadow < 0.5 * body and body > 0.1:
            if curr['RSI'] < 45: # 低位 -> 錘頭
                signals.append({
                    "date": date, "price": curr['Low'], "type": "Hammer", 
                    "text": "🔨錘頭", "color": "green", "desc": "🔨 錘頭線 (Hammer) - 底部支撐"
                })
            elif curr['RSI'] > 60: # 高位 -> 上吊
                signals.append({
                    "date": date, "price": curr['High'], "type": "Hanging", 
                    "text": "🧣上吊", "color": "red", "desc": "🧣 上吊線 (Hanging Man) - 頂部風險"
                })

        # --- D. 倒錘頭與射擊之星 (Inverted Hammer / Shooting Star) ---
        # 特徵：實體小，上影線長 (>2倍實體)，下影線短
        if upper_shadow > 2 * body and lower_shadow < 0.5 * body and body > 0.1:
            if curr['RSI'] < 45: # 低位 -> 倒錘頭
                signals.append({
                    "date": date, "price": curr['Low'], "type": "Inv_Hammer", 
                    "text": "🌤️倒錘", "color": "green", "desc": "🌤️ 倒錘頭 (Inverted Hammer)"
                })
            elif curr['RSI'] > 60: # 高位 -> 射擊之星
                signals.append({
                    "date": date, "price": curr['High'], "type": "Shooting", 
                    "text": "☄️射星", "color": "red", "desc": "☄️ 射擊之星 (Shooting Star) - 拋壓重"
                })

        # --- E. 十字星 (Doji) ---
        # 特徵：實體極小
        if body < 0.15 * mean_body:
            signals.append({
                "date": date, "price": curr['High'], "type": "Doji", 
                "text": "➕十字", "color": "gray", "desc": "➕ 十字星 (Doji) - 多空僵持"
            })

        # --- F. 三日形態 (星型) ---
        # 1. 晨星 (Morning Star): 陰 -> 十字/小實體 -> 陽
        if prev2['Close'] < prev2['Open'] and abs(prev['Close']-prev['Open']) < mean_body * 0.5 and curr['Close'] > curr['Open']:
            if curr['Close'] > (prev2['Open'] + prev2['Close'])/2: # 深入第一根實體一半
                 signals.append({
                    "date": date, "price": curr['Low'], "type": "M_Star", 
                    "text": "🌅晨星", "color": "green", "desc": "🌅 晨星 (Morning Star) - 底部反轉"
                })
        
        # 2. 黃昏之星 (Evening Star): 陽 -> 十字/小實體 -> 陰
        if prev2['Close'] > prev2['Open'] and abs(prev['Close']-prev['Open']) < mean_body * 0.5 and curr['Close'] < curr['Open']:
            if curr['Close'] < (prev2['Open'] + prev2['Close'])/2:
                 signals.append({
                    "date": date, "price": curr['High'], "type": "E_Star", 
                    "text": "🌃夜星", "color": "red", "desc": "🌃 黃昏之星 (Evening Star) - 頂部反轉"
                })

    return signals

# --- 5. 交易計劃與邏輯 (維持不變) ---
def generate_trade_plan(df):
    last = df.iloc[-1]
    atr = last['ATR']
    close = last['Close']
    
    plan = {}
    reasons = []
    
    # 阻力位
    recent_high = df['High'].tail(20).max()
    if recent_high > close:
        plan['res'] = recent_high
        plan['res_reason'] = "前波高點壓力"
    else:
        plan['res'] = (int(close / 10) + 1) * 10
        plan['res_reason'] = "整數心理關口"

    # 止損位
    if close > last['EMA_20']:
        plan['stop'] = last['EMA_20']
        plan['stop_reason'] = "跌穿 20MA (趨勢轉弱)"
    else:
        plan['stop'] = close - (1.5 * atr)
        plan['stop_reason'] = f"1.5倍 ATR 波動防守"
        
    # 目標價
    risk = close - plan['stop']
    if risk > 0:
        plan['target'] = close + (risk * 2)
        plan['target_reason'] = "風險回報比 2:1 推算"
    else:
        plan['target'] = close + (2 * atr)
        plan['target_reason'] = "2倍 ATR 波段獲利"

    # 趨勢原因
    if close > last['EMA_20']: reasons.append("✅ **趨勢**：價格位於 20MA 之上，短線偏多。")
    else: reasons.append("⚠️ **趨勢**：價格跌破 20MA，注意回調。")
    
    # 加入最後兩天的形態原因
    recent_signals = detect_all_patterns(df[-3:]) # 檢查最近3天
    added_desc = set()
    for s in recent_signals:
        if s['desc'] not in added_desc:
            reasons.append(f"🕯️ **形態**：{s['desc']}")
            added_desc.add(s['desc'])

    return plan, reasons

# --- 主畫面 UI ---
st.title(f"⚔️ {symbol} 全方位戰術地圖")
st.caption("自動標註：吞沒 / 錘頭 / 星形 / 爆量 (VH)")

df = get_data(symbol)

if df is not None:
    plan, reasons = generate_trade_plan(df)
    chart_signals = detect_all_patterns(df)
    last_price = df['Close'].iloc[-1]
    
    # --- 戰術面板 ---
    st.subheader("📋 交易作戰計劃")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("現價", f"${last_price:.2f}")
    c2.metric("🎯 目標獲利", f"${plan['target']:.2f}")
    c3.metric("🛡️ 止損防守", f"${plan['stop']:.2f}")
    c4.metric("🚧 關鍵壓力", f"${plan['res']:.2f}")
    
    st.info(f"**點位邏輯**：止損 ({plan['stop_reason']}) | 目標 ({plan['target_reason']}) | 壓力 ({plan['res_reason']})")

    # --- 訊號分析區 ---
    with st.expander("🔍 查看今日技術與形態分析", expanded=True):
        if reasons:
            for r in reasons: st.write(r)
        else:
            st.write("今日走勢平穩，無特殊形態訊號。")

    st.divider()

    # --- 專業圖表 ---
    st.subheader("📊 多重形態標註圖 (Patterns Chart)")
    
    fig = go.Figure()

    # K線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="K線"))
    
    # 均線
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], line=dict(color='orange', width=1), name='20 EMA'))
    fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], line=dict(color='blue', width=1), name='50 EMA'))
    
    # 畫線
    fig.add_hline(y=plan['target'], line_dash="dash", line_color="green", annotation_text="Target")
    fig.add_hline(y=plan['stop'], line_dash="dash", line_color="red", annotation_text="Stop")
    fig.add_hline(y=plan['res'], line_dash="dot", line_color="gray", annotation_text="Res")

    # --- 形態標註 (Annotations) ---
    annotations = []
    
    # 避免文字重疊的簡單處理：
    # 同一天如果有多個訊號，我們稍微錯開位置，或者合併
    # 這裡採用直接堆疊的方式，Plotly 會自動處理一些，但太多還是會疊
    
    for sig in chart_signals:
        # 決定顯示位置：看漲/底部形態在 Low 下方，看跌/頂部/爆量在 High 上方
        if sig['type'] in ['Bull_Engulf', 'Hammer', 'Inv_Hammer', 'M_Star']:
            y_pos = sig['price']
            ay_offset = 40 # 箭頭向下指
            y_anchor = "top"
        else: # Bear, Shooting, Hanging, E_Star, VH, Doji (Doji 預設上方)
            y_pos = sig['price']
            ay_offset = -40 # 箭頭向上指
            y_anchor = "bottom"
            
        annotations.append(dict(
            x=sig['date'],
            y=y_pos,
            xref="x", yref="y",
            text=sig['text'], # 顯示簡短文字如 "🔨錘頭"
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=ay_offset,
            font=dict(color=sig['color'], size=11, family="Arial Black")
        ))
    
    fig.update_layout(
        height=750, 
        xaxis_rangeslider_visible=False,
        annotations=annotations,
        title=f"{symbol} 價格行為與形態分析"
    )
    
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("無法獲取數據")
