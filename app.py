import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Konoha Ops Pro", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    .main { padding: 0rem 0rem; }
    .map-container { display: grid; grid-template-columns: 3.5fr 1fr; gap: 10px; padding: 10px; }
    @media (max-width: 768px) {
        .map-container { grid-template-columns: 1fr; }
        .legend-col { display: none !important; }
    }
    .legend-col { background-color: #f8f9fa; padding: 15px; border-radius: 12px; border: 1px solid #ddd; }
    .stMultiSelect label, .stSelectbox label { font-weight: bold; color: #333; }
    [data-testid="stMetricValue"] { font-size: 24px; color: #1f77b4; }
    </style>
    """, unsafe_allow_html=True)

# IDs
SHEET_ID_MASTER = '1Ov3nggLzpDQPkMyfoJtT8i4Goe1MLJ2t6AFRFspi_X8'
SHEET_ID_SO = '1mjjDF1ETjOB_eTI6ChI6dqvg0wf9aCa7cJwx0x2K3No'

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=300)
def load_data_pro():
    try:
        # Load Sheets
        df_master = pd.read_csv(f'https://docs.google.com/spreadsheets/d/{SHEET_ID_MASTER}/gviz/tq?tqx=out:csv&sheet=Master_Lokasi')
        df_peta = pd.read_csv(f'https://docs.google.com/spreadsheets/d/{SHEET_ID_MASTER}/gviz/tq?tqx=out:csv&sheet=Peta_Lantai')
        df_items = pd.read_csv(f'https://docs.google.com/spreadsheets/d/{SHEET_ID_MASTER}/gviz/tq?tqx=out:csv&sheet=Data')
        df_so_raw = pd.read_csv(f'https://docs.google.com/spreadsheets/d/{SHEET_ID_SO}/gviz/tq?tqx=out:csv&sheet=database_stokopname')
        df_stat_lok = pd.read_csv(f'https://docs.google.com/spreadsheets/d/{SHEET_ID_SO}/gviz/tq?tqx=out:csv&sheet=stat_lok')

        # --- EXPLICIT RENAMING & CLEANING ---
        def fix_master(df):
            df.columns = df.columns.str.strip()
            for col in df.columns:
                if col.upper() == 'URL': df.rename(columns={col: 'FOTO_RAK'}, inplace=True)
                if col.upper() in ['LOKASI', 'KODE LOKASI']: df.rename(columns={col: 'Lokasi'}, inplace=True)
                if col.upper() == 'NAMA_LOKASI': df.rename(columns={col: 'nama_lokasi'}, inplace=True)
            return df

        def fix_peta(df):
            df.columns = df.columns.str.strip()
            for col in df.columns:
                if col.upper() == 'URL': df.rename(columns={col: 'URL_PETA'}, inplace=True)
            return df

        def fix_common(df):
            df.columns = df.columns.str.strip()
            for col in df.columns:
                c_up = col.upper()
                if c_up in ['LOKASI', 'KODE LOKASI', 'KODE_LOKASI']: df.rename(columns={col: 'Lokasi'}, inplace=True)
                if c_up in ['DESKRIPSI', 'NAMA_BARANG', 'NAMA BARANG']: df.rename(columns={col: 'Nama_Barang'}, inplace=True)
                if c_up == 'STATUS': df.rename(columns={col: 'STATUS'}, inplace=True)
            return df

        df_master = fix_master(df_master)
        df_peta = fix_peta(df_peta)
        df_items = fix_common(df_items)
        df_so_raw = fix_common(df_so_raw)
        df_stat_lok = fix_common(df_stat_lok)

        df_master['X'] = pd.to_numeric(df_master['X'], errors='coerce')
        df_master['Y'] = pd.to_numeric(df_master['Y'], errors='coerce')
        df_master = df_master.dropna(subset=['X', 'Y'])
        df_master['Y_Visual'] = 1000 - df_master['Y']
        
        df_items['Weight'] = df_items['Kategori'].astype(str).apply(lambda x: 1 if 'FAST' in x.upper() else (-1 if 'SLOW' in x.upper() else 0))
        rak_resume = df_items.groupby('Lokasi').agg(Total_Barang=('Nama_Barang', 'count'), Speed_Score=('Weight', 'mean')).reset_index()

        df_full = pd.merge(df_master, rak_resume, on='Lokasi', how='left')
        df_items_full = pd.merge(df_items, df_master[['Lokasi', 'Lantai']], on='Lokasi', how='inner')
        
        return df_full, df_peta, df_stat_lok, df_items, df_so_raw, df_items_full
    except Exception as e:
        st.error(f"Gagal Sinkronisasi Data: {e}")
        return None, None, None, None, None, None

df_full, df_peta, df_stat_lok, df_items, df_so_raw, df_items_full = load_data_pro()

# --- 3. FILTER & SEARCH SIDEBAR ---
if df_full is not None:
    st.sidebar.header("⚙️ Filter & Navigasi")
    
    list_lantai = sorted(df_full['Lantai'].unique().tolist())
    sel_lantai = st.sidebar.selectbox("Pilih Lantai", options=list_lantai)
    
    list_nama_lok = sorted(df_full[df_full['Lantai'] == sel_lantai]['nama_lokasi'].dropna().unique().tolist())
    sel_nama_lok = st.sidebar.multiselect("Filter Nama Lokasi", options=list_nama_lok)
    
    list_status = sorted(df_stat_lok['STATUS'].dropna().unique().tolist()) if 'STATUS' in df_stat_lok.columns else []
    sel_status = st.sidebar.multiselect("Filter Status SO", options=list_status)

    list_suggest = sorted(df_items_full['Nama_Barang'].unique().tolist() + df_full['Lokasi'].unique().tolist())
    search_q = st.selectbox("🔍 Cari Barang / Rak", options=[""] + list_suggest, 
                            format_func=lambda x: "Ketik nama barang atau kode rak..." if x == "" else x).upper()

    menu = st.radio("Mode:", ["📦 STOK OPNAME", "🔥 HEATMAP"], horizontal=True)

    # --- 4. DATA FILTERING ---
    viz_df_base = pd.merge(df_full, df_stat_lok[['Lokasi', 'STATUS']], on='Lokasi', how='left')
    viz_df_base['STATUS'] = viz_df_base['STATUS'].fillna('BELUM')
    
    mask = (viz_df_base['Lantai'] == sel_lantai)
    if sel_nama_lok: mask &= viz_df_base['nama_lokasi'].isin(sel_nama_lok)
    if sel_status: mask &= viz_df_base['STATUS'].isin(sel_status)
    filtered_viz = viz_df_base[mask].copy()

    # --- 4.5 DASHBOARD METRICS & CHART ---
    total_rak = len(filtered_viz)
    done_rak = len(filtered_viz[filtered_viz['STATUS'] == 'DONE'])
    progress_rak = len(filtered_viz[filtered_viz['STATUS'] == 'ON PROGRESS'])
    persentase = (done_rak / total_rak * 100) if total_rak > 0 else 0

    # Achievement Chart (Sidebar)
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Pencapaian SO")
    fig_achieve = go.Figure(data=[go.Pie(labels=['Done', 'Sisa'], 
                                        values=[done_rak, total_rak - done_rak], 
                                        hole=.7, 
                                        marker_colors=['#28a745', '#eeeeee'],
                                        showlegend=False)])
    fig_achieve.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=180, 
                             annotations=[dict(text=f'{persentase:.1f}%', x=0.5, y=0.5, font_size=20, showarrow=False)])
    st.sidebar.plotly_chart(fig_achieve, use_container_width=True, config={'displayModeBar': False})

    # Metric Cards Utama
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Rak", f"{total_rak} Titik")
    m2.metric("Selesai (DONE)", f"{done_rak} Titik")
    m3.metric("On Progress", f"{progress_rak} Titik")

    h_locations = []
    if search_q != "":
        match = df_items_full[(df_items_full['Nama_Barang'].str.contains(search_q, na=False, case=False)) | 
                             (df_items_full['Lokasi'].str.contains(search_q, na=False, case=False))]
        h_locations = match['Lokasi'].unique().tolist()

    # --- 5. VISUALIZATION ---
    fig = go.Figure()
    if menu == "📦 STOK OPNAME":
        colors = {'DONE': '#28a745', 'ON PROGRESS': '#ffc107', 'PENDING': '#dc3545', 'BELUM': '#6c757d'}
        for status, color in colors.items():
            sub = filtered_viz[filtered_viz['STATUS'] == status]
            fig.add_trace(go.Scatter(x=sub['X'], y=sub['Y_Visual'], mode='markers+text', name=status, text=sub['Lokasi'] if not h_locations else "",
                marker=dict(size=12, color=color, line=dict(width=1, color='white')), customdata=sub['Lokasi'], hovertemplate="<b>Rak: %{customdata}</b><extra></extra>"))
    else:
        fig.add_trace(go.Scatter(x=filtered_viz['X'], y=filtered_viz['Y_Visual'], mode='markers+text', text=filtered_viz['Lokasi'],
            marker=dict(size=filtered_viz['Total_Barang'].fillna(0)*5, sizemode='area', color=filtered_viz['Speed_Score'].fillna(0), colorscale='RdBu_r'),
            customdata=filtered_viz['Lokasi'], hovertemplate="<b>Rak: %{customdata}</b><extra></extra>"))

    if h_locations:
        h_df = viz_df_base[viz_df_base['Lokasi'].isin(h_locations) & (viz_df_base['Lantai'] == sel_lantai)]
        fig.add_trace(go.Scatter(x=h_df['X'], y=h_df['Y_Visual'], mode='markers', marker=dict(size=35, color="rgba(255, 0, 0, 0.2)", line=dict(width=4, color="#FF0000")), name="Target", hoverinfo='skip'))

    # Background Peta
    map_row = df_peta[df_peta['Lantai'] == sel_lantai]
    bg_url = ""
    if not map_row.empty and 'URL_PETA' in map_row.columns:
        bg_url = f"https://lh3.googleusercontent.com/d/{map_row['URL_PETA'].values[0]}"
    
    fig.update_layout(images=[dict(source=bg_url, xref="x", yref="y", x=0, y=1000, sizex=1000, sizey=1000, sizing="stretch", opacity=0.6, layer="below")],
        xaxis=dict(range=[0, 1000], visible=False), yaxis=dict(range=[0, 1000], visible=False), height=600, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)

    # --- 6. RENDER MAP & LEGEND ---
    st.markdown('<div class="map-container">', unsafe_allow_html=True)
    st.markdown('<div class="map-col">', unsafe_allow_html=True)
    selected_points = st.plotly_chart(fig, use_container_width=True, on_select="rerun", config={'displayModeBar': False})
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('<div class="legend-col">', unsafe_allow_html=True)
    st.markdown('<h3 style="margin-top:0;">🏷️ Status</h3>', unsafe_allow_html=True)
    for s, c in {'DONE': '#28a745', 'ON PROGRESS': '#ffc107', 'PENDING': '#dc3545', 'BELUM': '#6c757d'}.items():
        st.markdown(f'<div style="display:flex; align-items:center; margin-bottom:8px;"><div style="width:14px; height:14px; background:{c}; border-radius:50%; margin-right:12px;"></div><b>{s}</b></div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    # --- 7. DETAIL TABEL & FOTO ---
    clicked_lokasi = None
    if selected_points and "selection" in selected_points and "points" in selected_points["selection"]:
        points = selected_points["selection"]["points"]
        if points: clicked_lokasi = points[0].get("customdata")

    if clicked_lokasi:
        st.markdown(f"## 📄 Detail: {clicked_lokasi}")
        
        lokasi_info = df_full[df_full['Lokasi'] == clicked_lokasi]
        if not lokasi_info.empty:
            row_data = lokasi_info.iloc[0]
            if 'FOTO_RAK' in row_data and pd.notna(row_data['FOTO_RAK']):
                st.image(str(row_data['FOTO_RAK']), caption=f"Foto Kondisi Rak {clicked_lokasi}", use_container_width=True)

        if menu == "🔥 HEATMAP":
            detail = df_items[df_items['Lokasi'] == clicked_lokasi][['Nama_Barang', 'Kategori', 'Satuan']]
            st.dataframe(detail, use_container_width=True, hide_index=True)
        else:
            so_filtered = df_so_raw[df_so_raw['Lokasi'] == clicked_lokasi].copy()
            if not so_filtered.empty:
                cols_u = {c.upper(): c for c in so_filtered.columns}
                p_col = next((cols_u[k] for k in ['NAMA_PETUGAS', 'PETUGAS'] if k in cols_u), None)
                if p_col:
                    list_p = so_filtered[p_col].dropna().unique().tolist()
                    st.info(f"👤 **Petugas:** {', '.join(list_p) if list_p else '-'}")
                
                q_teori = next((cols_u[k] for k in ['QTYTEORI', 'QTY TEORI', 'TEORI'] if k in cols_u), 'QTYTEORI')
                j_hitung = next((cols_u[k] for k in ['JENIS_PENGHITUNG', 'JENIS PENGHITUNG', 'JENIS'] if k in cols_u), 'JENIS_PENGHITUNG')
                q_fisik = next((cols_u[k] for k in ['QTYFISIK', 'QTY FISIK', 'FISIK'] if k in cols_u), 'QTYFISIK')
                q_selisih = next((cols_u[k] for k in ['QTYSELISIH', 'QTY SELISIH', 'SELISIH'] if k in cols_u), 'QTYSELISIH')
                
                so_filtered.rename(columns={q_teori:'QTYTEORI', j_hitung:'JENIS_PENGHITUNG', q_fisik:'QTYFISIK', q_selisih:'QTYSELISIH'}, inplace=True)
                
                pivot_so = so_filtered.pivot_table(index=['Nama_Barang', 'QTYTEORI'], columns='JENIS_PENGHITUNG', values=['QTYFISIK', 'QTYSELISIH'], aggfunc='sum').reset_index()
                pivot_so.columns = [f"{col[0]}_{col[1]}".strip('_') for col in pivot_so.columns.values]
                st.dataframe(pivot_so, use_container_width=True, hide_index=True)
            else:
                st.warning("Belum ada data scan.")
    else:
        st.info("💡 Klik lokasi pada peta untuk melihat foto dan detail.")
