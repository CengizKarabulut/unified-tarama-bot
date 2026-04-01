import os
import mplfinance as mpf
import pandas as pd
import logging

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def make_candle_chart(df, out_png: str, title: str):
    """
    Verilen DataFrame'den mum grafiği, MA200, SMI ve MACD içeren profesyonel bir görsel oluşturur.
    """
    try:
        # 1. Klasör Kontrolü
        os.makedirs(os.path.dirname(out_png), exist_ok=True)

        # 2.mplfinance DatetimeIndex bekler, kontrol et ve düzelt
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        addplots = []
        
        # 3. MA200 Plot (Ana Grafik Üzerinde)
        if 'MA200' in df.columns and not df['MA200'].dropna().empty:
            addplots.append(mpf.make_addplot(df['MA200'], color='#2962FF', width=1.2))

        # 4. SMI Paneli (Panel 2)
        if 'SMI' in df.columns and 'SMI_EMA' in df.columns:
            # SMI verisinin boş olmadığını kontrol et
            if not df['SMI'].dropna().empty:
                addplots.append(mpf.make_addplot(df['SMI'], panel=2, color='#00C853', width=1.0, ylabel='SMI'))
                addplots.append(mpf.make_addplot(df['SMI_EMA'], panel=2, color='#FF5252', width=1.0))

        # 5. MACD Paneli (Panel 3)
        if 'MACD' in df.columns and 'Signal' in df.columns:
            if not df['MACD'].dropna().empty:
                addplots.append(mpf.make_addplot(df['MACD'], panel=3, color='#2196F3', width=1.0, ylabel='MACD'))
                addplots.append(mpf.make_addplot(df['Signal'], panel=3, color='#FF9800', width=1.0))
                if 'Hist' in df.columns:
                    # Histogram renklerini (Pozitif/Negatif) ayarla
                    colors = ['#26a69a' if x >= 0 else '#ef5350' for x in df['Hist']]
                    addplots.append(mpf.make_addplot(df['Hist'], panel=3, type='bar', color=colors, alpha=0.7))

        # 6. Panel Oranlarını Hesapla
        # Mum Grafiği (0), Hacim (1), SMI (2), MACD (3)
        num_panels = 2 # Varsayılan: Grafik + Hacim
        if 'SMI' in df.columns: num_panels += 1
        if 'MACD' in df.columns: num_panels += 1

        ratios = [4, 1] # Ana Grafik, Hacim
        if 'SMI' in df.columns: ratios.append(1.5)
        if 'MACD' in df.columns: ratios.append(1.5)

        # 7. Görsel Stil Ayarları (Modern ve Karanlık Tema Seçeneği)
        custom_style = mpf.make_mpf_style(
            base_mpf_style='charles', 
            gridcolor='#e0e0e0',
            facecolor='white',
            edgecolor='black',
            rc={'font.size': 8}
        )

        # 8. Grafiği Çiz ve Kaydet
        mpf.plot(
            df,
            type="candle",
            volume=True,
            title=f"\n{title}",
            style=custom_style,
            savefig=dict(fname=out_png, dpi=150, bbox_inches='tight'),
            addplot=addplots,
            panel_ratios=ratios,
            tight_layout=True,
            datetime_format='%d/%m', # Eksen tarih formatı
            xrotation=0
        )
        
        logging.info(f"✅ Grafik başarıyla oluşturuldu: {out_png}")
        return True

    except Exception as e:
        logging.error(f"❌ Grafik oluşturma hatası: {e}")
        return False
