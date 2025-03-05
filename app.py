import os
import ssl
import time
from datetime import datetime, timedelta
from random import uniform

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

COLUNAS_ESPERADAS = {
    "Quimicos": ["Nome", "Tipo", "Fabricante", "Concentracao", "Classe", "ModoAcao"],
    "Biologicos": ["Nome", "Tipo", "IngredienteAtivo", "Formulacao", "Aplicacao", "Validade"],
    "Resultados": ["Data", "Quimico", "Biologico", "Duracao", "Tipo", "Resultado"],
    "Solicitacoes": ["Data", "Solicitante", "Quimico", "Biologico", "Observacoes", "Status"]
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

def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    def _load():
        try:
            worksheet = get_worksheet(sheet_name)
            if worksheet is None:
                st.warning(f"Planilha {sheet_name} não encontrada")
                return pd.DataFrame()
            
            try:
                data = worksheet.get_all_records()
                if not data:
                    st.warning(f"A planilha {sheet_name} está vazia")
                    return pd.DataFrame()
            except gspread.exceptions.APIError as e:
                st.error(f"Erro na API: {str(e)}")
                return pd.DataFrame()

            # Converter para DataFrame com tratamento de erros
            df = pd.DataFrame(data)
            
            # Verificar colunas essenciais
            required_columns = {
                "Quimicos": ["Nome", "Tipo"],
                "Biologicos": ["Nome", "Tipo"],
                "Resultados": ["Quimico", "Biologico"],
                "Solicitacoes": ["Quimico", "Biologico"]
            }
            
            if sheet_name in required_columns:
                for col in required_columns[sheet_name]:
                    if col not in df.columns:
                        st.error(f"Coluna obrigatória '{col}' não encontrada em {sheet_name}")
                        return pd.DataFrame()
            return df

        except Exception as e:
            st.error(f"Erro crítico ao carregar {sheet_name}: {str(e)}")
            return pd.DataFrame()
        
    return retry_with_backoff(_load)

def update_sheet(df: pd.DataFrame, sheet_name: str) -> bool:
    def _update():
        try:
            # Verificar se o DataFrame é válido
            if df.empty:
                raise ValueError("DataFrame vazio recebido para atualização")
                
            # Verificar colunas obrigatórias
            required_columns = COLUNAS_ESPERADAS.get(sheet_name, [])
            missing = [col for col in required_columns if col not in df.columns]
            if missing:
                raise ValueError(f"Colunas faltando: {', '.join(missing)}")
                
            # Manter apenas colunas relevantes
            df = df[required_columns].copy()
            
            # Converter colunas de data somente se existirem
            if 'Data' in df.columns:
                df['Data'] = pd.to_datetime(df['Data'], errors='coerce').dt.strftime("%Y-%m-%d")
            
            # Preencher valores NaN
            df = df.fillna("")
                
            worksheet = get_worksheet(sheet_name)
            if worksheet is None:
                return False
                
            worksheet.clear()
            data = [df.columns.tolist()] + df.values.tolist()
            worksheet.update(data)
            
            st.cache_data.clear()
            return True
            
        except Exception as e:
            st.error(f"Erro ao atualizar planilha {sheet_name}: {str(e)}")
            return False

    return retry_with_backoff(_update, initial_delay=2)

def update_worksheet(df_editado: pd.DataFrame, worksheet_name: str):
    """Função genérica para atualizar worksheet"""
    try:
        worksheet = get_worksheet(worksheet_name)
        if worksheet is not None:
            # Identificar as linhas alteradas
            df_original = pd.DataFrame(worksheet.get_all_records())
            df_alterado = df_editado.copy()
            
            # Remover colunas de controle antes de salvar
            if 'DELETE' in df_alterado.columns:
                df_alterado = df_alterado.drop(columns=['DELETE'])
            
            # Limpar a planilha e reescrever os dados
            worksheet.clear()
            headers = df_alterado.columns.tolist()
            worksheet.append_row(headers)
            worksheet.append_rows(df_alterado.values.tolist())
            
            st.cache_data.clear()
            st.success("Dados atualizados com sucesso!")
            st.rerun()
    except Exception as e:
        st.error(f"Erro ao atualizar planilha: {str(e)}")

@st.cache_data(ttl=3600)
def load_all_data():
    """
    Carrega todos os dados das planilhas com cache para melhorar o desempenho.
    O cache expira após 1 hora (3600 segundos).
    """
    # Verificar se já temos dados na sessão
    if 'local_data' in st.session_state and all(key in st.session_state.local_data for key in ["quimicos", "biologicos", "resultados", "solicitacoes"]):
        return st.session_state.local_data
    
    # Inicializar dicionário de dados
    dados = {}
    
    # Carregar dados com tratamento de erros e delays para evitar sobrecarga
    dados["quimicos"] = _load_sheet_with_delay("Quimicos")
    dados["biologicos"] = _load_sheet_with_delay("Biologicos")
    dados["resultados"] = _load_sheet_with_delay("Resultados")
    dados["solicitacoes"] = _load_sheet_with_delay("Solicitacoes")
    
    # Validar dados carregados
    for sheet_name in ["quimicos", "biologicos", "resultados", "solicitacoes"]:
        dados[sheet_name] = _load_and_validate_sheet(sheet_name) if dados[sheet_name].empty else dados[sheet_name]
    
    # Armazenar na sessão para acesso rápido
    st.session_state.local_data = dados
    
    return dados

def _load_sheet_with_delay(sheet_name):
    try:
        # Adicionar pequeno delay para evitar sobrecarga da API
        time.sleep(uniform(0.2, 0.5))
        return load_sheet_data(sheet_name)
    except Exception as e:
        st.error(f"Erro ao carregar {sheet_name}: {str(e)}")
        return pd.DataFrame()

def _load_and_validate_sheet(sheet_name):
    try:
        df = load_sheet_data(sheet_name)
        
        if df.empty:
            return pd.DataFrame()
        
        # Verificar coluna Nome
        if sheet_name in ["Quimicos", "Biologicos"] and "Nome" not in df.columns:
            st.error(f"Coluna 'Nome' não encontrada em {sheet_name}")
            return pd.DataFrame()
            
        # Remover linhas com Nome vazio para planilhas que exigem Nome
        if sheet_name in ["Quimicos", "Biologicos"] and "Nome" in df.columns:
            df = df[df["Nome"].notna()]
        
        # Converter colunas de data
        if sheet_name in ["Resultados", "Solicitacoes"] and "Data" in df.columns:
            df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
        
        return df
        
    except Exception as e:
        st.error(f"Falha crítica ao carregar {sheet_name}: {str(e)}")
        return pd.DataFrame()

########################################## COMPATIBILIDADE ##########################################

def compatibilidade():
    st.title("🧪 Compatibilidade")
    
    dados = load_all_data()
    
    # Verificação detalhada dos dados
    if dados["quimicos"].empty:
        st.warning("""
            **Nenhum produto químico cadastrado!**
            Por favor:
            1. Verifique a planilha 'Quimicos' no Google Sheets
            2. Confira se há dados na planilha
            3. Verifique as permissões de acesso
        """)
        return

    if dados["biologicos"].empty:
        st.warning("""
            **Nenhum produto biológico cadastrado!**
            Por favor:
            1. Verifique a planilha 'Biologicos' no Google Sheets
            2. Confira se há dados na planilha
            3. Verifique as permissões de acesso
        """)
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
        st.session_state.edited_data = {
            "quimicos": False,
            "biologicos": False,
            "resultados": False,
            "solicitacoes": False
        }
    
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
                
                # Garantir que apenas as colunas esperadas estejam presentes
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Quimicos"]].copy()
                
                # Tabela editável
                st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key="quimicos_editor",
                    on_change=lambda: st.session_state.edited_data.update({"quimicos": True}),
                    disabled=["Nome"],
                    column_config={
                        "Nome": st.column_config.TextColumn("Nome do Produto", required=True),
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
                            try:
                                # Atualizar dados locais primeiro
                                edited_df = st.session_state.quimicos_editor
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Quimicos"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Atualizar dados na sessão
                                st.session_state.local_data["quimicos"] = edited_df
                                
                                # Depois enviar para o Google Sheets
                                if update_sheet(edited_df, "Quimicos"):
                                    st.session_state.edited_data["quimicos"] = False
                                    st.success("Dados salvos com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {str(e)}")
    
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
                    df_filtrado[COLUNAS_ESPERADAS["Biologicos"]],
                    num_rows="dynamic",
                    key="biologicos_editor",
                    on_change=lambda: st.session_state.edited_data.update({"biologicos": True}),
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
                            try:
                                # Atualizar dados locais primeiro
                                edited_df = st.session_state.biologicos_editor
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Biologicos"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Atualizar dados na sessão
                                st.session_state.local_data["biologicos"] = edited_df
                                
                                # Depois enviar para o Google Sheets
                                if update_sheet(edited_df, "Biologicos"):
                                    st.session_state.edited_data["biologicos"] = False
                                    st.success("Dados salvos com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {str(e)}")
    
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
                    df_filtrado[COLUNAS_ESPERADAS["Resultados"]],
                    num_rows="dynamic",
                    key="resultados_editor",
                    on_change=lambda: st.session_state.edited_data.update({"resultados": True}),
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
                            try:
                                # Atualizar dados locais primeiro
                                edited_df = st.session_state.resultados_editor
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Resultados"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Atualizar dados na sessão
                                st.session_state.local_data["resultados"] = edited_df
                                
                                # Depois enviar para o Google Sheets
                                if update_sheet(edited_df, "Resultados"):
                                    st.session_state.edited_data["resultados"] = False
                                    st.success("Dados salvos com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {str(e)}")
    
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
                    df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]],
                    num_rows="dynamic",
                    key="solicitacoes_editor",
                    on_change=lambda: st.session_state.edited_data.update({"solicitacoes": True}),
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
                            try:
                                # Atualizar dados locais primeiro
                                edited_df = st.session_state.solicitacoes_editor
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Solicitacoes"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Atualizar dados na sessão
                                st.session_state.local_data["solicitacoes"] = edited_df
                                
                                # Depois enviar para o Google Sheets
                                if update_sheet(edited_df, "Solicitacoes"):
                                    st.session_state.edited_data["solicitacoes"] = False
                                    st.success("Dados salvos com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {str(e)}")

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