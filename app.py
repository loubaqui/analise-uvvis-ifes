import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.interpolate import interp1d
import io
from fpdf import FPDF
from datetime import datetime

st.set_page_config(page_title="IC Física - IFES", layout="wide")

# --- FUNÇÃO DE CARREGAMENTO ---
def load_data(file):
    try:
        content = file.read()
        try:
            decoded_content = content.decode('utf-8')
        except UnicodeDecodeError:
            decoded_content = content.decode('iso-8859-1')

        df = pd.read_csv(io.StringIO(decoded_content), sep=None, engine='python')
        df = df.iloc[:, [0, 1]]
        df.columns = ['nm', 'abs']

        for col in ['nm', 'abs']:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.dropna()
        return df
    except Exception as e:
        raise Exception(f"Erro ao processar {file.name}: {e}")

# --- FUNÇÃO DO PDF COM GRÁFICO ---
def generate_pdf(results_df, target_name, user_comments, fig_plotly):
    pdf = FPDF()
    pdf.add_page()

    # Cabeçalho
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 10, "IFES - Instituto Federal do Espirito Santo", ln=True, align='C')
    pdf.set_font("Arial", "I", 11)
    pdf.cell(190, 10, "Relatorio de Iniciacao Cientifica - Fisica", ln=True, align='C')

    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    pdf.cell(100, 7, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
    pdf.cell(100, 7, f"Amostra Analisada: {target_name}", ln=True)
    pdf.ln(5)

    # --- INSERÇÃO DO GRÁFICO NO PDF ---
    img_bytes = fig_plotly.to_image(format="png", width=800, height=450)
    img_stream = io.BytesIO(img_bytes)

    pdf.image(img_stream, x=15, y=50, w=180)
    pdf.ln(95)  

    # Tabela de Resultados
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(80, 10, "Referencia", border=1, fill=True)
    pdf.cell(55, 10, "Janela (nm)", border=1, fill=True)
    pdf.cell(45, 10, "Correlacao (r)", border=1, fill=True)
    pdf.ln()

    pdf.set_font("Arial", size=10)
    for _, row in results_df.iterrows():
        pdf.cell(80, 10, str(row['Arquivo'])[:40], border=1)
        pdf.cell(55, 10, str(row['Janela (nm)']), border=1)
        pdf.cell(45, 10, str(row['Correlação']), border=1)
        pdf.ln()

    if user_comments:
        pdf.ln(5)
        pdf.set_font("Arial", "B", 11)
        pdf.cell(190, 10, "Observacoes:", ln=True)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(190, 7, user_comments)

    pdf.ln(10)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(190, 10, "Instituicao: IFES", align='C', ln=True)

    return bytes(pdf.output())

# --- INTERFACE ---
st.title("🧪 Analisador UV-Vis IFES")

st.sidebar.header("1. Dados")
target_file = st.sidebar.file_uploader("Amostra Alvo", type=["csv"])
reference_files = st.sidebar.file_uploader("Referências", type=["csv"], accept_multiple_files=True)

st.sidebar.divider()
st.sidebar.header("2. Configurações")
threshold = st.sidebar.slider("Limiar de Atividade", 0.0, 0.1, 0.01)
normalizar = st.sidebar.checkbox("Normalizar Absorbância (Visual)", value=True, help="Desloca e estica a curva de referência para o mesmo range da amostra alvo, facilitando a comparação visual.")

user_notes = st.sidebar.text_area("Notas do Pesquisador:")

if target_file:
    try:
        df_target_full = load_data(target_file)
        results = []
        fig = go.Figure()

        # Pegamos os valores max e min da amostra alvo
        tgt_min = df_target_full['abs'].min()
        tgt_max = df_target_full['abs'].max()

        # Plota a Amostra Alvo imediatamente
        fig.add_trace(go.Scatter(x=df_target_full['nm'], y=df_target_full['abs'],
                                 name="AMOSTRA ALVO", line=dict(width=3, color='black')))

        # Se houver referências, faz o processamento delas
        if reference_files:
            for ref_file in reference_files:
                df_ref = load_data(ref_file)
                
                local_threshold = threshold
                if df_ref['abs'].max() <= threshold:
                    local_threshold = df_ref['abs'].min()
                    st.toast(f"Limiar de {ref_file.name} ajustado automaticamente.")
                    
                active_ref = df_ref[df_ref['abs'] > local_threshold]

                if not active_ref.empty:
                    nm_min, nm_max = active_ref['nm'].min(), active_ref['nm'].max()
                    
                    if nm_min > df_target_full['nm'].max() or nm_max < df_target_full['nm'].min():
                        st.warning(f"⚠️ Ignorado: A amostra e a referência '{ref_file.name}' não possuem cruzamento na faixa de nm.")
                        continue
                    
                    nm_min_inter = max(nm_min, df_target_full['nm'].min())
                    nm_max_inter = min(nm_max, df_target_full['nm'].max())
                    
                    mask_target = (df_target_full['nm'] >= nm_min_inter) & (df_target_full['nm'] <= nm_max_inter)
                    df_target_window = df_target_full[mask_target]

                    if not df_target_window.empty:
                        if normalizar:
                            ref_min = df_ref['abs'].min()
                            ref_max = df_ref['abs'].max()
                            if ref_max > ref_min: 
                                df_ref['abs_plot'] = (df_ref['abs'] - ref_min) / (ref_max - ref_min) * (tgt_max - tgt_min) + tgt_min
                            else:
                                df_ref['abs_plot'] = df_ref['abs']
                        else:
                            df_ref['abs_plot'] = df_ref['abs']

                        f_interp = interp1d(df_ref['nm'], df_ref['abs'], bounds_error=False, fill_value=0)
                        abs_ref_aligned = f_interp(df_target_window['nm'])
                        correlation = np.corrcoef(df_target_window['abs'], abs_ref_aligned)[0, 1]

                        results.append({
                            "Arquivo": ref_file.name,
                            "Janela (nm)": f"{int(nm_min_inter)}-{int(nm_max_inter)}",
                            "Correlação": round(correlation, 4)
                        })
                        
                        fig.add_trace(go.Scatter(x=df_ref['nm'], y=df_ref['abs_plot'],
                                                 name=f"Ref: {ref_file.name}", opacity=0.6))

        fig.update_layout(xaxis_title="Comprimento de Onda (nm)", yaxis_title="Absorbância",
                          template="plotly_white", legend=dict(orientation="h", y=-0.2))

        # --- LÓGICA DE EXIBIÇÃO DA INTERFACE ---
        if reference_files:
            if len(results) > 0:
                col1, col2 = st.columns([2, 1])
                res_df = pd.DataFrame(results).sort_values(by="Correlação", ascending=False)

                with col1:
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    st.subheader("Análise")
                    st.dataframe(res_df, use_container_width=True, hide_index=True)
                    if not res_df.empty:
                        st.divider()
                        with st.spinner('Gerando PDF com gráfico...'):
                            pdf_bytes = generate_pdf(res_df, target_file.name, user_notes, fig)
                            st.download_button("Baixar Relatório Completo (PDF)",
                                               data=pdf_bytes,
                                               file_name="relatorio_correlacao.pdf",
                                               mime="application/pdf",
                                               use_container_width=True)
            else:
                st.plotly_chart(fig, use_container_width=True)
                st.error("⚠️ Não foi possível calcular a correlação. Verifique se os dados das referências são válidos na faixa da amostra.")
        else:
            # Mostra apenas o gráfico da Amostra Alvo caso ainda não haja referências
            st.subheader("Visualização da Amostra")
            st.plotly_chart(fig, use_container_width=True)
            st.info("💡 Insira os arquivos de Referência na barra lateral para calcular a correlação e gerar o relatório.")

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
else:
    st.info("Faça o upload da Amostra Alvo para visualizar o gráfico inicial.")
