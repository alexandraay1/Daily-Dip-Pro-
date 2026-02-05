# --- 3. 數據引擎 (V14 修復版) ---
@st.cache_data(ttl=1800)
def get_data(ticker):
    try:
        # 1. 下載數據
        # auto_adjust=True 可以解決很多價格除權息的問題
        df = yf.download(ticker, period="5y", progress=False, auto_adjust=False)
        
        # 2. 數據清洗 (關鍵修復)
        if df.empty:
            st.error(f"⚠️ 找不到 {ticker} 的數據，可能是代號錯誤或 Yahoo 暫時封鎖。")
            return None

        # 處理 MultiIndex (Yahoo 常見問題)
        # 如果欄位是 ('Close', 'TSLA') 這種格式，強制轉為 'Close'
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 確保索引是 Datetime
        df.index = pd.to_datetime(df.index)
        # 移除時區信息 (Pandas_ta 討厭時區)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # --- 3. 技術指標計算 ---
        # 基礎均線
        df['EMA_50'] = ta.ema(df['Close'], length=50)
        df['EMA_200'] = ta.ema(df['Close'], length=200)
        
        # 波動率
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        
        # ADX (處理 NaN)
        adx = ta.adx(df['High'], df['Low'], df['Close'])
        if adx is not None and not adx.empty:
            df['ADX'] = adx['ADX_14']
        else:
            df['ADX'] = 0 # 避免計算失敗
        
        # SuperTrend
        st_data = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=3)
        if st_data is not None:
            st_col = [c for c in st_data.columns if "SUPERT_" in c][0]
            st_dir = [c for c in st_data.columns if "SUPERTd_" in c][0]
            df['SuperTrend'] = st_data[st_col]
            df['Trend_Dir'] = st_data[st_dir]
        
        # Bollinger Bands & Keltner Channels
        bb = ta.bbands(df['Close'], length=20, std=2)
        kc = ta.kc(df['High'], df['Low'], df['Close'], length=20, scalar=1.5)
        
        if bb is not None and kc is not None:
            df['BB_Upper'] = bb['BBU_20_2.0']
            df['BB_Lower'] = bb['BBL_20_2.0']
            df['KC_Upper'] = kc['KCUe_20_1.5']
            df['KC_Lower'] = kc['KCLe_20_1.5']
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
        
        # 清除 NaN
        df.dropna(inplace=True)
        
        if len(df) < 50:
            st.error("⚠️ 數據量不足，無法計算指標 (可能是新上市股票)")
            return None
            
        return df

    except Exception as e:
        # 這裡會顯示真正的錯誤原因！
        st.error(f"💥 程式崩潰，錯誤代碼: {str(e)}")
        # 建議打開下面這行來看詳細追蹤 (Traceback)
        # st.exception(e) 
        return None
