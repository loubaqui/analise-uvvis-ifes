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
    pdf.cell(190, 10, "IFES - Instituto Federal do Espírito Santo", ln=True, align='C')
    pdf.set_font("Arial", "I", 11)
    pdf.cell(190, 10, "Relatorio de Iniciação Científica - Física", ln=True, align='C')

    pdf.set_font("Arial", size=10)
    pdf.ln(5)
    pdf.cell(100, 7, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
    pdf.cell(100, 7, f"Amostra Analisada: {target_name}", ln=True)
    pdf.ln(5)

    # --- INSERÇÃO DO GRÁFICO NO PDF ---
    # Convertendo o gráfico Plotly em imagem (PNG) em memória
    img_bytes = fig_plotly.to_image(format="png", width=800, height=450)
    img_stream = io.BytesIO(img_bytes)

    # Posiciona a imagem no PDF (x, y, largura)
    pdf.image(img_stream, x=15, y=50, w=180)
    pdf.ln(95)  # Pula espaço para não escrever em cima da imagem

    # Tabela de Resultados
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(80, 10, "Referência", border=1, fill=True)
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
        pdf.cell(190, 10, "Observações:", ln=True)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(190, 7, user_comments)

    pdf.ln(10)
    pdf.set_font("Arial", "B", 10)
    pdf.cell(190, 10, "Instituição: IFES", align='C', ln=True)

    return bytes(pdf.output())


# --- INTERFACE ---
st.title("🧪 Analisador UV-Vis IFES")

st.sidebar.header("1. Dados")
target_file = st.sidebar.file_uploader("Amostra Alvo", type=["csv"])
reference_files = st.sidebar.file_uploader("Referências", type=["csv"], accept_multiple_files=True)
threshold = st.sidebar.slider("Limiar de Atividade", 0.0, 0.1, 0.01)
user_notes = st.sidebar.text_area("Notas do Pesquisador:")

if target_file and reference_files:
    try:
        df_target_full = load_data(target_file)
        results = []
        fig = go.Figure()

        # Linha principal da amostra
        fig.add_trace(go.Scatter(x=df_target_full['nm'], y=df_target_full['abs'],
                                 name="AMOSTRA", line=dict(width=3, color='black')))

        for ref_file in reference_files:
            df_ref = load_data(ref_file)
            active_ref = df_ref[df_ref['abs'] > threshold]

            if not active_ref.empty:
                nm_min, nm_max = active_ref['nm'].min(), active_ref['nm'].max()
                mask_target = (df_target_full['nm'] >= nm_min) & (df_target_full['nm'] <= nm_max)
                df_target_window = df_target_full[mask_target]

                if not df_target_window.empty:
                    f_interp = interp1d(df_ref['nm'], df_ref['abs'], bounds_error=False, fill_value=0)
                    abs_ref_aligned = f_interp(df_target_window['nm'])
                    correlation = np.corrcoef(df_target_window['abs'], abs_ref_aligned)[0, 1]

                    results.append({
                        "Arquivo": ref_file.name,
                        "Janela (nm)": f"{int(nm_min)}-{int(nm_max)}",
                        "Correlação": round(correlation, 4)
                    })
                    # Adiciona referência ao gráfico (visível por padrão para o PDF)
                    fig.add_trace(go.Scatter(x=df_ref['nm'], y=df_ref['abs'],
                                             name=f"Ref: {ref_file.name}", opacity=0.6))

        fig.update_layout(xaxis_title="Comprimento de Onda (nm)", yaxis_title="Absorbância",
                          template="plotly_white", legend=dict(orientation="h", y=-0.2))

        col1, col2 = st.columns([2, 1])
        res_df = pd.DataFrame(results).sort_values(by="Correlação", ascending=False)

        with col1:
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Análise")
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            if not res_df.empty:
                st.divider()
                # Geração do PDF passando o objeto 'fig'
                with st.spinner('Gerando PDF com gráfico...'):
                    pdf_bytes = generate_pdf(res_df, target_file.name, user_notes, fig)
                    st.download_button("Baixar Relatório Completo (PDF)",
                                       data=pdf_bytes,
                                       file_name="relatório_correlação.pdf",
                                       mime="application/pdf",
                                       use_container_width=True)

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
else:
    st.info("Aguardando arquivos para gerar análise e gráfico...")
