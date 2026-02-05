# --- 6. V14 回測引擎 (Backtest Engine) ---
def run_backtest(df):
    st.markdown("## 💰 V14 策略回測報告 (Tesla 專用)")
    
    # 1. 初始設定
    initial_capital = 100000.0  # 10萬美金
    equity = initial_capital
    position = 0  # 持倉股數
    entry_price = 0
    
    # 記錄資金曲線
    equity_curve = []
    trade_log = []
    
    # 2. 獲取信號源 (重用 V14 邏輯)
    regime_list = []
    for i in range(len(df)):
        # 模擬逐日判斷市場狀態
        row = df.iloc[i]
        squeeze = (row['BB_Upper'] < row['KC_Upper']) and (row['BB_Lower'] > row['KC_Lower'])
        adx_ok = row['ADX'] > 20
        regime_list.append(adx_ok and not squeeze) # True = 可交易, False = 過濾
        
    df['Can_Trade'] = regime_list
    
    # 3. 逐日回測 (Loop)
    # 從第 50 天開始 (讓均線生成)
    for i in range(50, len(df)-1):
        curr = df.iloc[i]
        nxt = df.iloc[i+1] # 用隔日開盤價成交
        date = df.index[i]
        
        # --- 賣出邏輯 (止損/止盈) ---
        if position > 0:
            # 條件 A: 跌破 SuperTrend (止損)
            # 條件 B: 跌破 EMA 50 (趨勢改變)
            stop_condition = (curr['Close'] < curr['SuperTrend']) or (curr['Close'] < curr['EMA_50'])
            
            if stop_condition:
                # 執行賣出
                sell_price = nxt['Open'] # 隔日開盤賣出
                revenue = position * sell_price
                profit = revenue - (position * entry_price)
                profit_pct = (sell_price - entry_price) / entry_price * 100
                
                equity = revenue # 全部資金回籠
                position = 0
                
                trade_log.append({
                    "Date": nxt.name, "Type": "SELL 🔴", 
                    "Price": sell_price, "Profit($)": profit, "Return(%)": profit_pct,
                    "Equity": equity
                })
        
        # --- 買入邏輯 ---
        elif position == 0 and curr['Can_Trade']: # 空手且市場狀態健康
            # 信號 A: WT 黃金交叉 (趨勢回調)
            wt_signal = (curr['Trend_Dir'] == 1) and (curr['WT1'] < -40) and (curr['WT1'] > curr['WT2']) and (df.iloc[i-1]['WT1'] <= df.iloc[i-1]['WT2'])
            # 信號 B: 站上 EMA 50
            ema_signal = (curr['Close'] > curr['EMA_50']) and (df.iloc[i-1]['Close'] <= df.iloc[i-1]['EMA_50'])
            
            if wt_signal or ema_signal:
                # 執行買入 (全倉 All-in)
                buy_price = nxt['Open']
                position = equity / buy_price # 計算股數
                entry_price = buy_price
                equity = 0 # 資金轉為股票
                
                trade_log.append({
                    "Date": nxt.name, "Type": "BUY 🟢", 
                    "Price": buy_price, "Profit($)": 0, "Return(%)": 0,
                    "Equity": entry_price * position
                })
        
        # 每日更新淨值 (Mark to Market)
        current_equity = equity if position == 0 else position * curr['Close']
        equity_curve.append({"Date": date, "Equity": current_equity})

    # 4. 結算
    final_equity = equity if position == 0 else position * df.iloc[-1]['Close']
    total_return = (final_equity - initial_capital) / initial_capital * 100
    
    # 5. 顯示結果
    c1, c2, c3 = st.columns(3)
    c1.metric("初始本金", f"${initial_capital:,.0f}")
    c2.metric("最終淨值", f"${final_equity:,.0f}", f"{total_return:.2f}%")
    c3.metric("總交易次數", f"{len(trade_log)//2}")
    
    # 繪製資金曲線
    ec_df = pd.DataFrame(equity_curve).set_index("Date")
    st.line_chart(ec_df)
    
    # 交易明細表
    with st.expander("查看詳細交易紀錄"):
        st.dataframe(pd.DataFrame(trade_log))

# --- 在主程式 Tab 加入回測按鈕 ---
# 請將這段放在 tabs 定義之後
with tab1:
    st.divider()
    if st.button("🚀 執行 V14 模擬回測 ($100k Challenge)"):
        run_backtest(df)
