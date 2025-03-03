import os
import ssl
import time
from datetime import datetime, timedelta
from random import uniform
import warnings
import httplib2
import requests
import certifi

import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2 import service_account
import streamlit.components.v1 as components

# Configurações iniciais
st.set_page_config(
    page_title="Experimentos",
    page_icon="🧪",
    layout="wide"
)

# Estilos CSS personalizados
def local_css():
    st.markdown("""
        <style>
            [data-testid="stSidebar"] {
                background-color: #f8f9fa;
                padding: 20px;
            }
            h1, h2, h3 {
                color: #2c3e50;
                font-weight: bold;
            }
            .card {
                background-color: #ffffff;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                margin: 10px;
                text-align: center;
            }
            .resultado {
                padding: 20px;
                border-radius: 5px;
                margin: 20px 0;
                text-align: center;
                font-size: 24px;
            }
            .compativel {
                background-color: #90EE90;
                color: #006400;
            }
            .incompativel {
                background-color: #FFB6C1;
                color: #8B0000;
            }
        </style>
    """, unsafe_allow_html=True)

local_css()

########################################## CONEXÃO GOOGLE SHEETS ##########################################

SHEET_ID = "1lILLXICVkVekkm2EZ-20cLnkYFYvHnb14NL_Or7132U"
SHEET_GIDS = {
    "Resultados": "0",
    "Quimicos": "885876195",
    "Biologicos": "1440941690",
    "Solicitacoes": "1408097520"
}

@st.cache_resource
def get_google_sheets_client():
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        client = gspread.authorize(creds)
        
        if hasattr(client, 'session'):
            client.session.verify = False
            
        return client
    except Exception as e:
        st.error(f"Erro na conexão: {str(e)}")
        return None

def retry_with_backoff(func, max_retries=5, initial_delay=1):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if "Quota exceeded" not in str(e):
                st.error(f"Erro inesperado: {str(e)}")
                return None
                
            if attempt == max_retries - 1:
                st.error("Limite de tentativas excedido. Tente novamente mais tarde.")
                return None
                
            delay = initial_delay * (2 ** attempt) + uniform(0, 1)
            time.sleep(delay)
            st.warning(f"Tentando novamente em {delay:.1f} segundos...")
    return None

def get_worksheet(sheet_name: str):
    def _get_worksheet():
        try:
            client = get_google_sheets_client()
            spreadsheet = client.open_by_key(SHEET_ID)
            worksheet = spreadsheet.worksheet(sheet_name)
            return worksheet
        except Exception as e:
            st.error(f"Erro ao acessar planilha {sheet_name}: {str(e)}")
            return None
    return retry_with_backoff(_get_worksheet)

@st.cache_data(ttl=300)
def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    def _load():
        worksheet = get_worksheet(sheet_name)
        if worksheet:
            return pd.DataFrame(worksheet.get_all_records())
        return pd.DataFrame()  # Retorna DataFrame vazio se worksheet for None
    
    result = retry_with_backoff(_load)
    
    # Verificação explícita para None ou DataFrame vazio
    if result is None or result.empty:
        return pd.DataFrame()
    return result

def append_to_sheet(data_dict, sheet_name):
    try:
        worksheet = get_worksheet(sheet_name)
        if worksheet:
            worksheet.append_row(list(data_dict.values()))
            return True
        return False
    except Exception as e:
        st.error(f"Erro ao adicionar dados: {str(e)}")
        return False

def update_sheet(df: pd.DataFrame, sheet_name: str) -> bool:
    def _update():
        try:
            worksheet = get_worksheet(sheet_name)
            worksheet.clear()
            worksheet.update([df.columns.tolist()] + df.values.tolist())
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"Erro ao atualizar {sheet_name}: {str(e)}")
            return False
    return retry_with_backoff(_update)

########################################## CARREGAMENTO DE DADOS ##########################################

@st.cache_data
def load_all_data():
    return {
        "resultados": load_sheet_data("Resultados"),
        "quimicos": load_sheet_data("Quimicos"),
        "biologicos": load_sheet_data("Biologicos"),
        "solicitacoes": load_sheet_data("Solicitacoes")
    }

def get_product_id(df, product_name, product_type):
    try:
        return df[df['Nome'] == product_name]['ID'].values[0]
    except IndexError:
        st.error(f"{product_type} não encontrado: {product_name}")
        return None

########################################## PÁGINA PRINCIPAL ##########################################

def compatibilidade():
    st.title("🧪 Compatibilidade")
    
    dados = load_all_data()
    
    # Verificar se os dados foram carregados corretamente
    if dados["quimicos"].empty or dados["biologicos"].empty:
        st.error("Erro ao carregar dados dos produtos!")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        quimico = st.selectbox(
            "Produto Químico",
            options=sorted(dados["quimicos"]['Nome'].unique()),
            index=None
        )
    
    with col2:
        biologico = st.selectbox(
            "Produto Biológico",
            options=sorted(dados["biologicos"]['Nome'].unique()),
            index=None
        )
    
    if quimico and biologico:
        # Obter IDs
        id_quimico = get_product_id(dados["quimicos"], quimico, "Químico")
        id_biologico = get_product_id(dados["biologicos"], biologico, "Biológico")
        
        if id_quimico and id_biologico:
            # Procurar na planilha de Resultados
            resultado_existente = dados["resultados"][
                (dados["resultados"]["Químico"] == id_quimico) &
                (dados["resultados"]["Biológico"] == id_biologico)
            ]
            
            if not resultado_existente.empty:
                resultado = resultado_existente.iloc[0]['Resultado']
                classe = "compativel" if resultado == "Compatível" else "incompativel"
                st.markdown(f"""
                    <div class="resultado {classe}">
                        {resultado}
                    </div>
                """, unsafe_allow_html=True)
                
                # Mostrar detalhes do teste
                with st.expander("Ver detalhes do teste"):
                    st.write(f"**Data:** {resultado_existente.iloc[0]['Data']}")
                    st.write(f"**Tipo:** {resultado_existente.iloc[0]['Tipo']}")
                    st.write(f"**Duração:** {resultado_existente.iloc[0]['Duracao']} dias")
            
            else:
                st.warning("Combinação ainda não testada")
                
                # Solicitar novo teste
                with st.form("solicitar_teste"):
                    data_solicitacao = st.date_input("Data desejada para o teste")
                    observacoes = st.text_area("Observações")
                    
                    if st.form_submit_button("Solicitar Teste"):
                        nova_solicitacao = {
                            "Data": data_solicitacao.strftime("%Y-%m-%d"),
                            "Químico": id_quimico,
                            "Biológico": id_biologico,
                            "Observações": observacoes,
                            "Status": "Pendente"
                        }
                        
                        # Adicionar à planilha de Solicitações
                        try:
                            worksheet = get_worksheet("Solicitacoes")
                            worksheet.append_row(list(nova_solicitacao.values()))
                            st.success("Solicitação registrada com sucesso!")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Erro ao registrar solicitação: {str(e)}")

########################################## GERENCIAMENTO DE PRODUTOS ##########################################

def product_management():
    st.title("📦 Gerenciamento de Produtos")
    
    dados = load_all_data()
    tab1, tab2, tab3 = st.tabs(["Quimicos", "Biologicos", "Compatibilidades"])
    
    with tab1:
        df_edit = st.data_editor(
            dados["quimicos"],
            num_rows="dynamic",
            column_config={
                "ID": st.column_config.NumberColumn(format="%d"),
                "Nome": "Produto Químico",
                "Tipo": st.column_config.SelectboxColumn(options=["Herbicida", "Fungicida", "Inseticida"])
            }
        )
        if st.button("Salvar Quimicos"):
            update_sheet(df_edit, "Quimicos")
    
    with tab2:
        df_edit = st.data_editor(
            dados["biologicos"],
            num_rows="dynamic",
            column_config={
                "ID": st.column_config.NumberColumn(format="%d"),
                "Nome": "Produto Biológico",
                "Tipo": st.column_config.SelectboxColumn(options=["Bioestimulante", "Controle Biológico"])
            }
        )
        if st.button("Salvar Biológicos"):
            update_sheet(df_edit, "Biologicos")
    
    with tab3:
        df_edit = st.data_editor(
            dados["resultados"],
            num_rows="dynamic",
            column_config={
                "Quimico": st.column_config.NumberColumn(format="%d"),
                "Biologico": st.column_config.NumberColumn(format="%d"),
                "Resultado": st.column_config.SelectboxColumn(options=["Compatível", "Incompatível", "Não testado"])
            }
        )
        if st.button("Salvar Resultados"):
            update_sheet(df_edit, "Resultados")

########################################## HISTÓRICO E RELATÓRIOS ##########################################

def history_reports():
    st.title("📊 Histórico e Relatórios")
    
    dados = load_all_data()
    
    st.subheader("Estatísticas de Compatibilidade")
    df_stats = dados["resultados"].value_counts("Resultado").reset_index()
    fig = px.pie(df_stats, names="Resultado", values="count")
    st.plotly_chart(fig)
    
    st.subheader("Últimos Testes Realizados")
    st.dataframe(
        dados["resultados"].merge(
            dados["quimicos"], left_on="Químico", right_on="ID"
        ).merge(
            dados["biologicos"], left_on="Biológico", right_on="ID"
        )[["Nome_x", "Nome_y", "Resultado"]],
        hide_index=True,
        column_config={
            "Nome_x": "Químico",
            "Nome_y": "Biológico"
        }
    )

########################################## CONFIGURAÇÕES ##########################################

def settings_page():
    st.title("⚙️ Configurações")
    
    st.subheader("Conectividade com Google Sheets")
    if st.button("Testar Conexão"):
        try:
            client = get_google_sheets_client()
            if client:
                st.success("Conexão bem-sucedida!")
        except Exception as e:
            st.error(f"Erro na conexão: {str(e)}")
    
    st.subheader("Gerenciamento de Cache")
    if st.button("Limpar Cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.success("Cache limpo com sucesso!")

########################################## SIDEBAR E ROTEAMENTO ##########################################

def main():
    st.sidebar.image("imagens/logo-cocal.png", width=150)
    st.sidebar.title("Navegação")
    
    pages = {
        "Compatibilidade": compatibilidade,
        "Gerenciamento de Produtos": product_management,
        "Histórico e Relatórios": history_reports,
        "Configurações": settings_page
    }
    
    selected_page = st.sidebar.radio("Selecione a página", tuple(pages.keys()))
    
    with st.spinner("Carregando dados..."):
        pages[selected_page]()

if __name__ == "__main__":
    main()