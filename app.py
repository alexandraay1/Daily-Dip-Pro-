# --- 3. 數據引擎 (法醫驗屍修復版) ---
@st.cache_data(ttl=1800)
def get_data(ticker):
    st.write(f"正在嘗試下載 {ticker} 的數據...") # Debug 訊息
    
    try:
        # 1. 下載數據 (嘗試強制單層索引)
        # 移除 progress bar 防止干擾
        df = yf.download(ticker, period="2y", progress=False, auto_adjust=False, multi_level_index=False)
        
        # 2. 檢查是否真的下載到了
        if df is None or df.empty:
            st.error(f"❌ Yahoo 回傳空數據。原因可能是：1. 代號錯了 2. IP 被鎖 3. 該股票已下市")
            return None

        # --- 關鍵修復：暴力破解 MultiIndex ---
        # 把欄位印出來檢查 (這一行會顯示在網頁上，讓你看到真實結構)
        # st.write("原始欄位格式:", df.columns) 
        
        # 如果欄位是多層的 (例如: ('Close', 'TSLA'))，強制取第一層
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            # st.success("已自動修復 MultiIndex 格式")
        
        # 再次確認是否有 'Close' 欄位，如果沒有，嘗試修復大小寫
        if 'Close' not in df.columns:
            # 有時候 Yahoo 回傳 'close' 小寫
            df.columns = [c.capitalize() for c in df.columns]
        
        if 'Close' not in df.columns:
            st.error(f"❌ 數據格式異常，找不到 'Close' 欄位。現有欄位: {df.columns}")
            return None

        # 3. 處理時區 (Pandas_ta 討厭時區)
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # --- 4. 技術指標計算 (這裡最容易報錯) ---
        try:
            # 基礎指標
            df['EMA_50'] = ta.ema(df['Close'], length=50)
            df['EMA_200'] = ta.ema(df['Close'], length=200)
            df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
            
            # ADX
            adx = ta.adx(df['High'], df['Low'], df['Close'])
            # 確保 ADX 存在
            if adx is not None and not adx.empty:
                df['ADX'] = adx[adx.columns[0]] # 取第一欄通常是 ADX_14
            else:
                df['ADX'] = 0

            # SuperTrend (最常崩潰的地方)
            st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
            if st_data is not None:
                # 動態抓取欄位名稱，防止名稱變更
                df['SuperTrend'] = st_data.iloc[:, 0] # 第一欄是趨勢線
                df['Trend_Dir'] = st_data.iloc[:, 1]  # 第二欄是方向
            else:
                # 如果計算失敗，給預設值防止程式崩潰
                df['SuperTrend'] = df['Close']
                df['Trend_Dir'] = 1

            # Bollinger / Keltner / Squeeze
            bb = ta.bbands(df['Close'], length=20, std=2)
            kc = ta.kc(df['High'], df['Low'], df['Close'], length=20, scalar=1.5)
            
            if bb is not None and kc is not None:
                df['BB_Upper'] = bb.iloc[:, 0] # BBL
                df['BB_Lower'] = bb.iloc[:, 2] # BBU (注意 pandas_ta 返回順序)
                # 重新校正上下軌 (pandas_ta 有時順序不同)
                if df['BB_Upper'].iloc[-1] < df['BB_Lower'].iloc[-1]:
                    df['BB_Upper'], df['BB_Lower'] = df['BB_Lower'], df['BB_Upper']

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
            
            # Volume
            df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
            df['Vol_Ratio'] = df['Volume'] / df['Vol_SMA']
            
            df.dropna(inplace=True)
            return df

        except Exception as e:
            st.error(f"💥 指標計算失敗: {e}")
            st.write("這是哪一步錯了？通常是 pandas_ta 與 numpy 不相容，或是數據不足。")
            return None

    except Exception as e:
        st.error(f"💥 下載或處理數據時發生致命錯誤: {e}")
        st.exception(e) # 這會印出紅色的詳細錯誤追蹤
        return None
