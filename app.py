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
import numpy as np
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
            /* Estabilizar tabelas */
            [data-testid="stDataFrame"], [data-testid="stTable"] {
                width: 100% !important;
                min-height: 400px;
                height: auto !important;
            }
            /* Evitar que tabelas "tremam" */
            [data-testid="StyledFullScreenFrame"] {
                position: static !important;
                transform: none !important;
                transition: none !important;
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

def get_worksheet(sheet_name: str):
    def _get_worksheet():
        try:
            client = get_google_sheets_client()
            if client is None:
                st.error("Erro ao conectar com Google Sheets. Tente novamente mais tarde.")
                return None
                
            spreadsheet = client.open_by_key(SHEET_ID)
            worksheet = spreadsheet.worksheet(sheet_name)
            return worksheet
        except Exception as e:
            if "Quota exceeded" in str(e):
                raise e  # Re-raise quota errors to trigger retry
            st.error(f"Erro ao acessar planilha {sheet_name}: {str(e)}")
            return None
            
    return retry_with_backoff(_get_worksheet, max_retries=5, initial_delay=2)

def retry_with_backoff(func, max_retries=5, initial_delay=1):
    """
    Executa uma função com retry e exponential backoff
    
    Args:
        func: Função a ser executada
        max_retries: Número máximo de tentativas
        initial_delay: Delay inicial em segundos
        
    Returns:
        Resultado da função ou None se falhar
    """
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
                
            # Exponential backoff com jitter
            delay = initial_delay * (2 ** attempt) + uniform(0, 1)
            time.sleep(delay)
            
            # Informar usuário sobre retry
            st.warning(f"Limite de requisições atingido. Tentando novamente em {delay:.1f} segundos...")
            
    return None

@st.cache_data(ttl=3600, show_spinner=False, hash_funcs={pd.DataFrame: lambda _: None})
def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    def _load():
        worksheet = get_worksheet(sheet_name)
        if worksheet:
            try:
                # Adicionar tratamento de erro específico para quota excedida
                return pd.DataFrame(worksheet.get_all_records())
            except Exception as e:
                if "Quota exceeded" in str(e):
                    st.warning(f"Limite de requisições excedido para {sheet_name}. Usando dados em cache.")
                    # Retornar DataFrame vazio mas não mostrar erro
                    return pd.DataFrame()
                else:
                    st.error(f"Erro ao carregar dados de {sheet_name}: {str(e)}")
                    return pd.DataFrame()
        return pd.DataFrame()  # Retorna DataFrame vazio se worksheet for None
    
    result = retry_with_backoff(_load)
    
    # Verificação explícita para None ou DataFrame vazio
    if result is None or result.empty:
        return pd.DataFrame()
    return result

def append_to_sheet(data_dict, sheet_name):
    def _append():
        try:
            worksheet = get_worksheet(sheet_name)
            if worksheet is None:
                return False
                
            # Converter objetos datetime para strings
            for key in data_dict:
                if isinstance(data_dict[key], (datetime, pd.Timestamp)):
                    data_dict[key] = data_dict[key].strftime("%Y-%m-%d")
                    
            # Get headers from worksheet
            headers = worksheet.row_values(1)
            
            # Create new row based on headers
            row = [data_dict.get(header, "") for header in headers]
            
            # Append row to worksheet
            worksheet.append_row(row)
            
            # Clear cache to force data reload
            st.cache_data.clear()
            return True
            
        except Exception as e:
            if "Quota exceeded" in str(e):
                raise e  # Re-raise quota errors to trigger retry
            st.error(f"Erro ao adicionar dados: {str(e)}")
            return False
            
    return retry_with_backoff(_append, initial_delay=2)

def update_sheet(df, sheet_name: str) -> bool:
    def _update():
        try:
            # Corrigir escopo da variável e conversão
            df_converted = pd.DataFrame(df) if not isinstance(df, pd.DataFrame) else df
            
            if df_converted.empty:
                st.error("Erro: DataFrame vazio!")
                return False
                
            # Restante do código original...
            worksheet = get_worksheet(sheet_name)
            if worksheet is None:
                return False
                
            # Converter datas para string
            date_columns = df_converted.select_dtypes(include=['datetime64[ns]']).columns.tolist()
            for col in date_columns:
                df_converted[col] = df_converted[col].dt.strftime("%Y-%m-%d")
                
            # Atualizar planilha
            worksheet.clear()
            data = [df_converted.columns.tolist()] + df_converted.values.tolist()
            worksheet.update(data)
            
            return True
            
        except Exception as e:
            st.error(f"Erro ao atualizar planilha: {str(e)}")
            return False

    return retry_with_backoff(_update, initial_delay=2)

@st.cache_data(ttl=3600)
def load_all_data():
    """
    Carrega todos os dados das planilhas com cache para melhorar o desempenho.
    O cache expira após 1 hora (3600 segundos).
    """
    try:
        # Carregar dados com um pequeno atraso entre as requisições para evitar exceder a quota
        resultados = _load_sheet_with_delay("Resultados")
        # Converter coluna de data para datetime apenas se não estiver vazia
        if not resultados.empty and 'Data' in resultados.columns:
            resultados["Data"] = pd.to_datetime(resultados["Data"], format="%Y-%m-%d", errors="coerce")
        
        time.sleep(0.5)  # Reduzir o delay para melhorar o desempenho
        quimicos = _load_sheet_with_delay("Quimicos")
        
        time.sleep(0.5)  # Reduzir o delay para melhorar o desempenho
        biologicos = _load_sheet_with_delay("Biologicos")
        
        time.sleep(0.5)  # Reduzir o delay para melhorar o desempenho
        solicitacoes = _load_sheet_with_delay("Solicitacoes")
        # Converter coluna de data para datetime apenas se não estiver vazia
        if not solicitacoes.empty and 'Data' in solicitacoes.columns:
            solicitacoes["Data"] = pd.to_datetime(solicitacoes["Data"], format="%Y-%m-%d", errors="coerce")
        
        return {
            "resultados": resultados,
            "quimicos": quimicos,
            "biologicos": biologicos,
            "solicitacoes": solicitacoes
        }
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        # Retornar DataFrames vazios em caso de erro
        return {
            "resultados": pd.DataFrame(),
            "quimicos": pd.DataFrame(),
            "biologicos": pd.DataFrame(),
            "solicitacoes": pd.DataFrame()
        }

def _load_sheet_with_delay(sheet_name):
    try:
        return load_sheet_data(sheet_name)
    except Exception as e:
        st.error(f"Erro ao carregar {sheet_name}: {str(e)}")
        return pd.DataFrame()

########################################## COMPATIBILIDADE ##########################################

def compatibilidade():
    st.title("🧪 Compatibilidade")
    
    # Inicializar dados locais se não existirem na sessão
    if 'local_data' not in st.session_state:
        st.session_state.local_data = load_all_data()
        
    # Usar dados da sessão em vez de recarregar a cada interação
    dados = st.session_state.local_data
    
    # Verificar se os dados foram carregados corretamente
    if dados["quimicos"].empty or dados["biologicos"].empty:
        st.error("Erro ao carregar dados dos produtos!")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        quimico = st.selectbox(
            "Produto Químico",
            options=sorted(dados["quimicos"]['Nome'].unique()) if not dados["quimicos"].empty and 'Nome' in dados["quimicos"].columns else [],
            index=None,
            key="quimico_compat"
        )
    
    with col2:
        biologico = st.selectbox(
            "Produto Biológico",
            options=sorted(dados["biologicos"]['Nome'].unique()) if not dados["biologicos"].empty and 'Nome' in dados["biologicos"].columns else [],
            index=None,
            key="biologico_compat"
        )
    
    if quimico and biologico:
        # Procurar na planilha de Resultados usando os nomes
        resultado_existente = dados["resultados"][
            (dados["resultados"]["Quimico"] == quimico) &
            (dados["resultados"]["Biologico"] == biologico)
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
                st.write(f"**Quimico:** {resultado_existente.iloc[0]['Quimico']}")
                st.write(f"**Biologico:** {resultado_existente.iloc[0]['Biologico']}")
                st.write(f"**Tipo:** {resultado_existente.iloc[0]['Tipo']}")
                st.write(f"**Duração:** {resultado_existente.iloc[0]['Duracao']} horas")
                st.write(f"**Resultado:** {resultado_existente.iloc[0]['Resultado']}")
        
        else:
            st.warning("Combinação ainda não testada")
            
            # Solicitar novo teste - Corrigindo o formulário para incluir o botão de submit
            with st.form(key="solicitar_teste_form"):
                data_solicitacao = st.date_input("Data da Solicitação")
                solicitante = st.text_input("Nome do solicitante")
                observacoes = st.text_area("Observações")
                
                # Botão de submit dentro do formulário
                submit_button = st.form_submit_button(label="Solicitar Teste")
                
                # Processar o formulário quando enviado
                if submit_button:
                    nova_solicitacao = {
                        "Data": data_solicitacao.strftime("%Y-%m-%d"),
                        "Solicitante": solicitante,
                        "Quimico": quimico,
                        "Biologico": biologico,
                        "Observacoes": observacoes,
                        "Status": "Pendente"
                    }
                    
                    with st.spinner("Registrando solicitação..."):
                        if append_to_sheet(nova_solicitacao, "Solicitacoes"):
                            st.success("Solicitação registrada com sucesso!")
                            
                            # Atualizar dados locais
                            if "solicitacoes" in st.session_state.local_data:
                                nova_linha = pd.DataFrame([nova_solicitacao])
                                st.session_state.local_data["solicitacoes"] = pd.concat(
                                    [st.session_state.local_data["solicitacoes"], nova_linha], 
                                    ignore_index=True
                                )
                        else:
                            st.error("Falha ao registrar solicitação")

########################################## GERENCIAMENTO ##########################################

def gerenciamento():
    st.title("📦 Gerenciamento")

    if 'edited_data' not in st.session_state:
        st.session_state.edited_data = {}
    
    # Inicializar dados locais se não existirem na sessão
    if 'local_data' not in st.session_state:
        st.session_state.local_data = load_all_data()
    
    # Usar dados da sessão em vez de recarregar a cada interação
    dados = st.session_state.local_data
    
    tab1, tab2, tab3, tab4 = st.tabs(["Quimicos", "Biologicos", "Compatibilidades", "Solicitações"])
    
    with tab1:
        st.subheader("Produtos Químicos")
        if "quimicos" not in dados or dados["quimicos"].empty:
            st.error("Erro ao carregar dados dos produtos químicos!")
        else:
            # Opções para o usuário escolher entre registrar ou visualizar
            opcao = st.radio("Escolha uma opção:", ["Novo produto", "Produtos cadastrados"], key="opcao_quimicos")
            
            if opcao == "Novo produto":
                with st.form("novo_quimico_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        nome = st.text_input("Nome do Produto")
                        tipo = st.selectbox("Tipo", options=["Herbicida", "Fungicida", "Inseticida"])
                        fabricante = st.text_input("Fabricante")
                    with col2:
                        concentracao = st.number_input("Concentração", value=0.0, step=1.0)
                        classe = st.text_input("Classe")
                        modo_acao = st.text_input("Modo de Ação")
                    
                    submitted = st.form_submit_button("Adicionar Produto")
                    if submitted:
                        if nome:
                            novo_produto = {
                                "Nome": nome,
                                "Tipo": tipo,
                                "Fabricante": fabricante,
                                "Concentracao": concentracao,
                                "Classe": classe,
                                "ModoAcao": modo_acao
                            }
                            
                            # Verificar se o produto já existe
                            if nome in dados["quimicos"]["Nome"].values:
                                st.warning(f"Produto '{nome}' já existe!")
                            else:
                                # Adicionar à planilha
                                with st.spinner("Salvando novo produto..."):
                                    if append_to_sheet(novo_produto, "Quimicos"):
                                        st.success("Produto adicionado com sucesso!")
                                        # Atualizar dados locais
                                        nova_linha = pd.DataFrame([novo_produto])
                                        st.session_state.local_data["quimicos"] = pd.concat([st.session_state.local_data["quimicos"], nova_linha], ignore_index=True)
                                    else:
                                        st.error("Falha ao adicionar produto")
                        else:
                            st.warning("Nome do produto é obrigatório")
            
            else:  # Visualizar produtos cadastrados
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_nome = st.selectbox(
                        "🔍 Filtrar por Produto",
                        options=["Todos"] + sorted(dados["quimicos"]['Nome'].unique().tolist()),
                        index=0
                    )
                with col2:
                    filtro_tipo = st.selectbox(
                        "🔍 Filtrar por Tipo",
                        options=["Todos"] + sorted(dados["quimicos"]["Tipo"].unique().tolist()),
                        index=0
                    )

                # Aplicar filtro
                df_filtrado = dados["quimicos"].copy()
                if filtro_nome != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
                if filtro_tipo != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Tipo"] == filtro_tipo]
                
                # Tabela editável
                st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key="quimicos_editor",
                    on_change=lambda: st.session_state.update(edited_data=True),
                    column_config={
                        "Nome": "Nome",
                        "Tipo": st.column_config.SelectboxColumn(options=["Herbicida", "Fungicida", "Inseticida"]),
                        "Fabricante": "Fabricante",
                        "Concentracao": "Concentração",
                        "Classe": "Classe",
                        "ModoAcao": "Modo de Ação"
                    },
                    use_container_width=True
                )
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_quimicos"):
                    with st.spinner("Salvando dados..."):
                        if 'quimicos_editor' in st.session_state:
                            # Atualizar dados locais primeiro
                            st.session_state.local_data["quimicos"] = st.session_state.quimicos_editor
                            
                            # Depois enviar para o Google Sheets
                            if update_sheet(st.session_state.quimicos_editor, "Quimicos"):
                                st.session_state.edited_data = False
                                st.success("Dados salvos com sucesso!")
    
    with tab2:
        st.subheader("Produtos Biológicos")
        if "biologicos" not in dados or dados["biologicos"].empty:
            st.error("Erro ao carregar dados dos produtos biológicos!")
        else:
            # Opções para o usuário escolher entre registrar ou visualizar
            opcao = st.radio("Escolha uma opção:", ["Novo produto", "Produtos cadastrados"], key="opcao_biologicos")
            
            if opcao == "Novo produto":
                with st.form("novo_biologico_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        nome = st.text_input("Nome do Produto")
                        tipo = st.selectbox("Tipo", options=["Bioestimulante", "Controle Biológico"])
                        ingrediente_ativo = st.text_input("Ingrediente Ativo")
                    with col2:
                        formulacao = st.text_input("Formulação")
                        aplicacao = st.text_input("Aplicação")
                        validade = st.text_input("Validade")
                    
                    submitted = st.form_submit_button("Adicionar Produto")
                    if submitted:
                        if nome:
                            novo_produto = {
                                "Nome": nome,
                                "Tipo": tipo,
                                "IngredienteAtivo": ingrediente_ativo,
                                "Formulacao": formulacao,
                                "Aplicacao": aplicacao,
                                "Validade": validade
                            }
                            
                            # Verificar se o produto já existe
                            if nome in dados["biologicos"]["Nome"].values:
                                st.warning(f"Produto '{nome}' já existe!")
                            else:
                                # Adicionar à planilha
                                with st.spinner("Salvando novo produto..."):
                                    if append_to_sheet(novo_produto, "Biologicos"):
                                        st.success("Produto adicionado com sucesso!")
                                        # Atualizar dados locais
                                        nova_linha = pd.DataFrame([novo_produto])
                                        st.session_state.local_data["biologicos"] = pd.concat([st.session_state.local_data["biologicos"], nova_linha], ignore_index=True)
                                    else:
                                        st.error("Falha ao adicionar produto")
                        else:
                            st.warning("Nome do produto é obrigatório")
            
            else:  # Visualizar produtos cadastrados
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_nome = st.selectbox(
                        "🔍 Filtrar por Produto",
                        options=["Todos"] + sorted(dados["biologicos"]["Nome"].unique().tolist()),
                        index=0
                    )
                with col2:
                    filtro_tipo = st.selectbox(
                        "🔍 Filtrar por Tipo",
                        options=["Todos"] + sorted(dados["biologicos"]["Tipo"].unique().tolist()),
                        index=0
                    )

                # Aplicar filtro
                df_filtrado = dados["biologicos"].copy()
                if filtro_nome != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
                if filtro_tipo != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Tipo"] == filtro_tipo]
                
                # Tabela editável
                st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key="biologicos_editor",
                    on_change=lambda: st.session_state.update(edited_data=True),
                    column_config={
                        "Nome": "Produto Biológico",
                        "Tipo": st.column_config.SelectboxColumn(options=["Bioestimulante", "Controle Biológico"]),
                        "IngredienteAtivo": "Ingrediente Ativo",
                        "Formulacao": "Formulação",
                        "Aplicacao": "Aplicação",
                        "Validade": "Validade"
                    },
                    use_container_width=True
                )
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_biologicos"):
                    with st.spinner("Salvando dados..."):
                        if 'biologicos_editor' in st.session_state:
                            # Atualizar dados locais primeiro
                            st.session_state.local_data["biologicos"] = st.session_state.biologicos_editor
                            
                            # Depois enviar para o Google Sheets
                            if update_sheet(st.session_state.biologicos_editor, "Biologicos"):
                                st.session_state.edited_data = False
                                st.success("Dados salvos com sucesso!")
    
    with tab3:
        st.subheader("Resultados de Compatibilidade")
        if "resultados" not in dados or dados["resultados"].empty:
            st.error("Erro ao carregar dados dos resultados!")
        else:
            # Opções para o usuário escolher entre registrar ou visualizar
            opcao = st.radio("Escolha uma opção:", ["Nova compatibilidade", "Compatibilidades cadastradas"], key="opcao_compat")
            
            if opcao == "Nova compatibilidade":
                with st.form("nova_compatibilidade_form"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        quimico = st.selectbox(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]["Nome"].unique().tolist()),
                            index=None
                        )
                        data_teste = st.date_input("Data do Teste")
                        tipo = st.selectbox("Tipo de Teste", options=["Simples", "Composto"])
                    with col_b:
                        biologico = st.selectbox(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]["Nome"].unique().tolist()),
                            index=None
                        )
                        duracao = st.number_input("Duração (horas)", min_value=0, value=0)
                        resultado = st.selectbox("Resultado", options=["Compatível", "Incompatível", "Não testado"])
                    
                    submitted = st.form_submit_button("Adicionar Compatibilidade")
                    if submitted:
                        if quimico and biologico:
                            nova_compatibilidade = {
                                "Data": data_teste.strftime("%Y-%m-%d"),
                                "Quimico": quimico,
                                "Biologico": biologico,
                                "Duracao": duracao,
                                "Tipo": tipo,
                                "Resultado": resultado
                            }
                            
                            # Verificar se a combinação já existe
                            combinacao_existente = dados["resultados"][
                                (dados["resultados"]["Quimico"] == quimico) & 
                                (dados["resultados"]["Biologico"] == biologico)
                            ]
                            
                            if not combinacao_existente.empty:
                                st.warning(f"Combinação '{quimico} x {biologico}' já existe!")
                            else:
                                # Adicionar à planilha
                                with st.spinner("Salvando nova compatibilidade..."):
                                    if append_to_sheet(nova_compatibilidade, "Resultados"):
                                        st.success("Compatibilidade adicionada com sucesso!")
                                        # Atualizar dados locais
                                        nova_linha = pd.DataFrame([nova_compatibilidade])
                                        st.session_state.local_data["resultados"] = pd.concat([st.session_state.local_data["resultados"], nova_linha], ignore_index=True)
                                    else:
                                        st.error("Falha ao adicionar compatibilidade")
                        else:
                            st.warning("Selecione os produtos químico e biológico")
            
            else:  # Visualizar compatibilidades cadastradas
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_quimico = st.selectbox(
                        "🔍 Filtrar por Produto Químico",
                        options=["Todos"] + sorted(dados["resultados"]["Quimico"].unique().tolist()),
                        index=0
                    )
                with col2:
                    filtro_biologico = st.selectbox(
                        "🔍 Filtrar por Produto Biológico",
                        options=["Todos"] + sorted(dados["resultados"]["Biologico"].unique().tolist()),
                        index=0
                    )
                
                # Aplicar filtros
                df_filtrado = dados["resultados"].copy()
                if filtro_quimico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
                if filtro_biologico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
                
                # Tabela editável
                st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key="resultados_editor",
                    on_change=lambda: st.session_state.update(edited_data=True),
                    column_config={
                        "Data": st.column_config.DateColumn(
                            "Data do Teste",
                            format="YYYY-MM-DD",
                            required=True
                        ),
                        "Quimico": st.column_config.SelectboxColumn(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]["Nome"].unique().tolist()),
                            required=True
                        ),
                        "Biologico": st.column_config.SelectboxColumn(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]["Nome"].unique().tolist()),
                            required=True
                        ),
                        "Duracao": st.column_config.NumberColumn(
                            "Duração (horas)",
                            min_value=0,
                            default=0
                        ),
                        "Tipo": st.column_config.SelectboxColumn(
                            "Tipo de Teste",
                            options=["Simples", "Composto"],
                            required=True
                        ),
                        "Resultado": st.column_config.SelectboxColumn(
                            "Resultado",
                            options=["Compatível", "Incompatível", "Não testado"],
                            required=True
                        )
                    },
                    use_container_width=True
                )
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_resultados"):
                    with st.spinner("Salvando dados..."):
                        if 'resultados_editor' in st.session_state:
                            # Atualizar dados locais primeiro
                            st.session_state.local_data["resultados"] = st.session_state.resultados_editor
                            
                            # Depois enviar para o Google Sheets
                            if update_sheet(st.session_state.resultados_editor, "Resultados"):
                                st.session_state.edited_data = False
                                st.success("Dados salvos com sucesso!")
    
    with tab4:
        st.subheader("Solicitações")
        if "solicitacoes" not in dados or dados["solicitacoes"].empty:
            st.warning("Sem solicitações para exibir")
        else:
            # Opções para o usuário escolher entre registrar ou visualizar
            opcao = st.radio("Escolha uma opção:", ["Registrar nova solicitação", "Visualizar solicitações cadastradas"], key="opcao_solicitacoes")
            
            if opcao == "Registrar nova solicitação":
                with st.form("nova_solicitacao_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        solicitante = st.text_input("Nome do Solicitante")
                        quimico = st.selectbox(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]["Nome"].unique().tolist()),
                            index=None
                        )
                    with col2:
                        data = st.date_input("Data da Solicitação")
                        biologico = st.selectbox(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]["Nome"].unique().tolist()),
                            index=None
                        )
                    
                    observacoes = st.text_area("Observações")
                    
                    submitted = st.form_submit_button("Adicionar Solicitação")
                    if submitted:
                        if solicitante and quimico and biologico:
                            nova_solicitacao = {
                                "Data": data.strftime("%Y-%m-%d"),
                                "Solicitante": solicitante,
                                "Quimico": quimico,
                                "Biologico": biologico,
                                "Observacoes": observacoes,
                                "Status": "Pendente"
                            }
                            
                            # Adicionar à planilha
                            with st.spinner("Salvando nova solicitação..."):
                                if append_to_sheet(nova_solicitacao, "Solicitacoes"):
                                    st.success("Solicitação adicionada com sucesso!")
                                    # Atualizar dados locais
                                    nova_linha = pd.DataFrame([nova_solicitacao])
                                    st.session_state.local_data["solicitacoes"] = pd.concat([st.session_state.local_data["solicitacoes"], nova_linha], ignore_index=True)
                                else:
                                    st.error("Falha ao adicionar solicitação")
                        else:
                            st.warning("Preencha todos os campos obrigatórios")
            
            else:  # Visualizar solicitações cadastradas
                # Filtros para a tabela
                col1, col2, col3 = st.columns(3)
                with col1:
                    filtro_status = st.selectbox(
                        "🔍 Filtrar por Status",
                        options=["Todos", "Pendente", "Aprovado", "Rejeitado"],
                        index=0
                    )
                with col2:
                    filtro_quimico = st.selectbox(
                        "🔍 Filtrar por Produto Químico",
                        options=["Todos"] + sorted(dados["solicitacoes"]["Quimico"].unique().tolist()),
                        index=0
                    )
                with col3:
                    filtro_biologico = st.selectbox(
                        "🔍 Filtrar por Produto Biológico",
                        options=["Todos"] + sorted(dados["solicitacoes"]["Biologico"].unique().tolist()),
                        index=0
                    )
                
                # Aplicar filtros
                if not dados["solicitacoes"].empty:
                    df_filtrado = dados["solicitacoes"].copy()
                else:
                    df_filtrado = pd.DataFrame()

                if filtro_status != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]
                if filtro_quimico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
                if filtro_biologico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
                
                # Tabela editável
                st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key="solicitacoes_editor",
                    on_change=lambda: st.session_state.update(edited_data=True),
                    column_config={
                        "Data": st.column_config.DateColumn(
                            "Data da Solicitação",
                            format="YYYY-MM-DD",
                            required=True
                        ),
                        "Solicitante": "Nome do Solicitante",
                        "Quimico": st.column_config.SelectboxColumn(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]["Nome"].unique().tolist()),
                            required=True
                        ),
                        "Biologico": st.column_config.SelectboxColumn(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]["Nome"].unique().tolist()),
                            required=True
                        ),
                        "Observacoes": "Observações",
                        "Status": st.column_config.SelectboxColumn(
                            "Status",
                            options=["Pendente", "Aprovado", "Rejeitado"],
                            required=True
                        )
                    },
                    use_container_width=True
                )
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_solicitacoes"):
                    with st.spinner("Salvando dados..."):
                        if 'solicitacoes_editor' in st.session_state:
                            # Atualizar dados locais primeiro
                            st.session_state.local_data["solicitacoes"] = st.session_state.solicitacoes_editor
                            
                            # Depois enviar para o Google Sheets
                            if update_sheet(st.session_state.solicitacoes_editor, "Solicitacoes"):
                                st.session_state.edited_data = False
                                st.success("Dados salvos com sucesso!")

########################################## CONFIGURAÇÕES ##########################################

def configuracoes():
    st.title("⚙️ Configurações")
    
    # Criar abas para diferentes configurações
    tab1, tab2, tab3 = st.tabs(["Conectividade", "Cache", "Informações"])
    
    with tab1:
        st.subheader("Conectividade com Google Sheets")
        if st.button("Testar Conexão", key="test_connection"):
            with st.spinner("Testando conexão..."):
                try:
                    client = get_google_sheets_client()
                    if client:
                        st.success("✅ Conexão bem-sucedida!")
                        
                        # Mostrar informações adicionais
                        st.info("Planilha conectada: Experimentos Cocal")
                        st.code(f"ID da Planilha: {SHEET_ID}")
                        
                        # Testar acesso a cada planilha
                        st.subheader("Status das Planilhas")
                        col1, col2 = st.columns(2)
                        
                        for sheet_name in ["Resultados", "Quimicos", "Biologicos", "Solicitacoes"]:
                            try:
                                worksheet = client.open_by_key(SHEET_ID).worksheet(sheet_name)
                                with col1:
                                    st.write(f"📊 {sheet_name}")
                                with col2:
                                    st.write("✅ Acessível")
                            except Exception as e:
                                with col1:
                                    st.write(f"📊 {sheet_name}")
                                with col2:
                                    st.write("❌ Erro de acesso")
                except Exception as e:
                    st.error(f"❌ Erro na conexão: {str(e)}")
    
    with tab2:
        st.subheader("Gerenciamento de Cache")
        
        # Mostrar informações sobre o cache
        if 'local_data' in st.session_state:
            st.info("Status dos dados em cache:")
            
            for key, df in st.session_state.local_data.items():
                if not df.empty:
                    st.success(f"✅ {key.capitalize()}: {len(df)} registros carregados")
                else:
                    st.warning(f"⚠️ {key.capitalize()}: Sem dados")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🧹 Limpar Cache", key="clear_cache"):
                st.cache_data.clear()
                st.cache_resource.clear()
                
                # Limpar dados da sessão
                if 'local_data' in st.session_state:
                    del st.session_state['local_data']
                
                st.success("✅ Cache limpo com sucesso!")
                st.info("Os dados serão recarregados na próxima interação.")
        
        with col2:
            if st.button("🔄 Recarregar Todos os Dados", key="reload_all"):
                with st.spinner("Recarregando todos os dados..."):
                    st.cache_data.clear()
                    st.session_state.local_data = load_all_data()
                    st.success("✅ Dados recarregados com sucesso!")
    
    with tab3:
        st.subheader("Informações do Sistema")
        
        # Mostrar informações sobre o aplicativo
        st.info("Aplicativo de Experimentos Cocal")
        st.write("**Versão:** 1.0.0")
        st.write("**Desenvolvido por:** Matheus Rezende - Analista de Geotecnologia")
        
        # Mostrar informações sobre o ambiente
        st.subheader("Ambiente de Execução")
        
        # Adicionar link para documentação
        st.markdown("[Documentação do Google Sheets API](https://developers.google.com/sheets/api/guides/concepts)")

########################################## SIDEBAR ##########################################

def main():
    st.sidebar.image("imagens/logo-cocal.png")
    st.sidebar.title("Menu")
    menu_option = st.sidebar.radio(
        "Selecione a funcionalidade:",
        ("Compatibilidade", "Gerenciamento", "Configurações")
    )

    st.sidebar.markdown("---")  # Linha separadora

    if menu_option == "Compatibilidade":
        compatibilidade()
    elif menu_option == "Gerenciamento":
        gerenciamento()
    elif menu_option == "Configurações":
        configuracoes()

########################################## EXECUÇÃO ##########################################

if __name__ == "__main__":
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = True

    try:
        if st.session_state["logged_in"]:
            main()
    except Exception as e:
        st.error(f"Erro ao executar a aplicação: {e}")
        st.stop()