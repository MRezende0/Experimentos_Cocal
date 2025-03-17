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

# CSS minimalista apenas para estilização básica, sem interferir nos botões
def local_css():
    st.markdown("""
        <style>
            /* Estilos básicos para a interface */
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
            .naotestado {
                background-color: #fffce8;
                color: #916c04;
            }
        </style>
    """, unsafe_allow_html=True)

local_css()

# Inicialização dos dados locais
if 'local_data' not in st.session_state:
    st.session_state.local_data = {
        "quimicos": pd.DataFrame(),
        "biologicos": pd.DataFrame(),
        "resultados": pd.DataFrame(),
        "solicitacoes": pd.DataFrame()
    }

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

def get_sheet(sheet_name: str):
    def _get_sheet():
        try:
            client = get_google_sheets_client()
            if client is None:
                st.error("Erro ao conectar com Google Sheets. Tente novamente mais tarde.")
                return None
                
            spreadsheet = client.open_by_key(SHEET_ID)
            sheet = spreadsheet.worksheet(sheet_name)
            return sheet
        except Exception as e:
            st.error(f"Erro ao acessar planilha {sheet_name}: {str(e)}")
            return None
            
    return retry_with_backoff(_get_sheet, max_retries=5, initial_delay=2)

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
    """
    Adiciona uma nova linha de dados à planilha especificada.
    
    Args:
        data_dict (dict): Dicionário com os dados a serem adicionados
        sheet_name (str): Nome da planilha onde adicionar os dados
        
    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário
    """
    def _append(data_dict=data_dict, sheet_name=sheet_name):
        try:
            # Obter a planilha
            sheet = get_sheet(sheet_name)
            if not sheet:
                st.error(f"Planilha '{sheet_name}' não encontrada.")
                return False
            
            # Verificar se há dados para adicionar
            if not data_dict:
                st.error("Nenhum dado para adicionar.")
                return False
            
            # Adicionar os dados à planilha
            sheet.append_row(list(data_dict.values()))
            
            # Atualizar os dados locais também
            nova_linha = pd.DataFrame([data_dict])
            if sheet_name.lower() in st.session_state.local_data:
                st.session_state.local_data[sheet_name.lower()] = pd.concat(
                    [st.session_state.local_data[sheet_name.lower()], nova_linha], 
                    ignore_index=True
                )
            
            return True
            
        except Exception as e:
            st.error(f"Erro ao adicionar dados: {str(e)}")
            return False
            
    return retry_with_backoff(_append, max_retries=5, initial_delay=2)

def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    def _load(sheet_name=sheet_name):
        try:
            worksheet = get_sheet(sheet_name)
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
    try:
        worksheet = get_sheet(sheet_name)
        if worksheet is None:
            return False
            
        # Converter todas as datas para string ISO
        df_copy = df.copy()
        for col in df_copy.columns:
            if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
                df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d')
                
        # Garantir a ordem das colunas
        df_copy = df_copy[COLUNAS_ESPERADAS[sheet_name]]
        
        # Atualizar toda a planilha
        worksheet.clear()
        worksheet.update(
            [df_copy.columns.values.tolist()] + df_copy.values.tolist(),
            value_input_option='USER_ENTERED'  # Adicionado para preservar formatos
        )
        
        # Atualizar cache local
        st.session_state.local_data[sheet_name.lower()] = df
        return True
        
    except Exception as e:
        st.error(f"Erro ao atualizar planilha: {str(e)}")
        return False

def load_all_data():
    """
    Carrega todos os dados das planilhas e armazena na session_state
    Usa cache de sessão para minimizar requisições ao Google Sheets
    """
    # Verificar se os dados já estão na sessão e se foram carregados há menos de 5 minutos
    if 'data_timestamp' in st.session_state and 'local_data' in st.session_state:
        elapsed_time = (datetime.now() - st.session_state.data_timestamp).total_seconds()
        # Usar dados em cache se foram carregados há menos de 5 minutos
        if elapsed_time < 300:  # 5 minutos em segundos
            return st.session_state.local_data
    
    # Carregar dados com paralelismo para melhorar a performance
    with st.spinner("Carregando dados..."):
        # Inicializar dicionário de dados
        dados = {}
        
        # Definir função para carregar uma planilha específica
        def load_sheet(sheet_name):
            return sheet_name, _load_and_validate_sheet(sheet_name)
        
        # Usar threads para carregar as planilhas em paralelo
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Submeter tarefas para carregar cada planilha
            futures = {executor.submit(load_sheet, name): name for name in ["Quimicos", "Biologicos", "Resultados", "Solicitacoes"]}
            
            # Coletar resultados à medida que ficam disponíveis
            for future in concurrent.futures.as_completed(futures):
                sheet_name, df = future.result()
                dados[sheet_name.lower()] = df
    
    # Armazenar dados na sessão com timestamp
    st.session_state.local_data = dados
    st.session_state.data_timestamp = datetime.now()
    
    return dados

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
    # Inicializar variável de estado para controle do formulário
    if 'solicitar_novo_teste' not in st.session_state:
        st.session_state.solicitar_novo_teste = False
    if 'pre_selecionado_quimico' not in st.session_state:
        st.session_state.pre_selecionado_quimico = None
    if 'pre_selecionado_biologico' not in st.session_state:
        st.session_state.pre_selecionado_biologico = None
    if 'just_submitted' not in st.session_state:
        st.session_state.just_submitted = False
    if 'last_submission' not in st.session_state:
        st.session_state.last_submission = None
    if 'success_message_time' not in st.session_state:
        st.session_state.success_message_time = None
    if 'form_submitted_successfully' not in st.session_state:
        st.session_state.form_submitted_successfully = False

    col1, col2 = st.columns([4, 1])  # 4:1 ratio para alinhamento direito

    with col1:
        st.title("🧪 Compatibilidade")

    with col2:
        # Container com alinhamento à direita
        st.markdown(
            """
            <div style='display: flex;
                        justify-content: flex-end;
                        align-items: center;
                        height: 100%;'>
            """,
            unsafe_allow_html=True
        )
        
        if st.button("Solicitar Novo Teste", key="btn_novo_teste", use_container_width=True):
            # Limpar estados anteriores para garantir um novo formulário
            if 'form_submitted' in st.session_state:
                st.session_state.form_submitted = False
            if 'form_success' in st.session_state:
                st.session_state.form_success = False
            if 'last_submission' in st.session_state:
                st.session_state.last_submission = None
            st.session_state.solicitar_novo_teste = True
            st.session_state.pre_selecionado_quimico = None
            st.session_state.pre_selecionado_biologico = None
            
        st.markdown("</div>", unsafe_allow_html=True)
    
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
    
    # Verificar se o botão de novo teste foi pressionado
    if st.session_state.get('solicitar_novo_teste', False):
        mostrar_formulario_solicitacao(
            quimico=st.session_state.pre_selecionado_quimico,
            biologico=st.session_state.pre_selecionado_biologico
        )
        return  # Importante: retornar para não mostrar o restante da interface
    
    # Interface de consulta de compatibilidade
    col1, col2 = st.columns([1, 1])
    with col1:
        quimico = st.selectbox(
            "Produto Químico",
            options=sorted(dados["quimicos"]['Nome'].unique()) if not dados["quimicos"].empty and 'Nome' in dados["quimicos"].columns else [],
            index=None,
            key="compatibilidade_quimico"
        )
    
    with col2:
        biologico = st.selectbox(
            "Produto Biológico",
            options=sorted(dados["biologicos"]['Nome'].unique()) if not dados["biologicos"].empty and 'Nome' in dados["biologicos"].columns else [],
            index=None,
            key="compatibilidade_biologico"
        )
    
    if quimico and biologico:
        # Procurar na planilha de Resultados usando os nomes
        resultado_existente = dados["resultados"][
            (dados["resultados"]["Quimico"] == quimico) & 
            (dados["resultados"]["Biologico"] == biologico)
        ]
        
        if not resultado_existente.empty:
            # Mostrar resultado de compatibilidade
            compativel = resultado_existente.iloc[0]["Resultado"] == "Compatível"
            
            if compativel:
                st.markdown("""
                    <div class="resultado compativel">
                    Compatível
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div class="resultado incompativel">
                    Incompatível
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
            # Mostrar aviso de que não existe compatibilidade cadastrada
            st.markdown("""
                    <div class="resultado naotestado">
                    Teste não realizado!
                    Solicite um novo teste.
                </div>
                """, unsafe_allow_html=True)
    
    # Exibir mensagem de sucesso se acabou de enviar uma solicitação
    if st.session_state.form_submitted_successfully:
        st.success("Solicitação de novo teste enviada com sucesso!")
        st.session_state.form_submitted_successfully = False  # Reseta o estado

    # Função auxiliar para mostrar o formulário de solicitação
def mostrar_formulario_solicitacao(quimico=None, biologico=None):
    # Inicializar variáveis de estado se não existirem
    if 'form_submitted' not in st.session_state:
        st.session_state.form_submitted = False
    if 'form_success' not in st.session_state:
        st.session_state.form_success = False
    if 'just_submitted' not in st.session_state:
        st.session_state.just_submitted = False
    if 'last_submission' not in st.session_state:
        st.session_state.last_submission = None
    if 'success_message_time' not in st.session_state:
        st.session_state.success_message_time = None
    if 'form_submitted_successfully' not in st.session_state:
        st.session_state.form_submitted_successfully = False

    # Função para processar o envio do formulário
    def submit_form():
        # Obter valores do formulário
        data = st.session_state.data_solicitacao
        solicitante = st.session_state.solicitante
        quimico_input = st.session_state.quimico_input
        biologico_input = st.session_state.biologico_input
        observacoes = st.session_state.observacoes
        
        if not all([solicitante, quimico_input, biologico_input]):
            st.error("""
            Por favor, preencha todos os campos obrigatórios:
            - Nome do solicitante
            - Nome do produto químico
            - Nome do produto biológico
            """)
            return

        # Preparar dados da solicitação
        nova_solicitacao = {
            "Data": data.strftime("%Y-%m-%d"),
            "Solicitante": solicitante,
            "Quimico": quimico_input,
            "Biologico": biologico_input,
            "Observacoes": observacoes,
            "Status": "Pendente"
        }

        if append_to_sheet(nova_solicitacao, "Solicitacoes"):
            st.session_state.form_submitted_successfully = True
            st.session_state.solicitar_novo_teste = False
            st.session_state.last_submission = nova_solicitacao
        else:
            st.error("Erro ao enviar solicitação. Tente novamente.")
    
    # Mostrar o formulário para entrada de dados
    st.subheader("Solicitar Novo Teste")
    
    # Valores iniciais para os campos
    default_quimico = quimico if quimico else ""
    default_biologico = biologico if biologico else ""
    
    # Usar st.form para evitar recarregamentos
    with st.form(key="solicitar_teste_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.date_input("Data da Solicitação", value=datetime.now(), key="data_solicitacao", format="DD/MM/YYYY")
            st.text_input("Nome do solicitante", key="solicitante")
        
        with col2:
            # Usar campos de texto para permitir novos produtos
            st.text_input("Nome do Produto Químico", value=default_quimico, key="quimico_input")
            st.text_input("Nome do Produto Biológico", value=default_biologico, key="biologico_input")
        
        st.text_area("Observações", key="observacoes")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.form_submit_button("Enviar Solicitação", on_click=submit_form):
                st.session_state.form_submitted = True
        with col2:
            if st.form_submit_button("Cancelar"):
                st.session_state.solicitar_novo_teste = False

########################################## GERENCIAMENTO ##########################################

def gerenciamento():
    st.title("⚙️ Gerenciamento")

    # Inicializar estado das tabs se não existir
    if 'active_tab' not in st.session_state:
        st.session_state.active_tab = 0

    if 'edited_data' not in st.session_state:
        st.session_state.edited_data = {
            "quimicos": False,
            "biologicos": False,
            "resultados": False,
            "solicitacoes": False
        }
    
    # Inicializar dados locais
    if 'local_data' not in st.session_state:
        st.session_state.local_data = load_all_data()
    
    # Usar dados da sessão em vez de recarregar a cada interação
    dados = st.session_state.local_data
    
    # Criar tabs mantendo o estado ativo
    tabs = ["Quimicos", "Biologicos", "Compatibilidades", "Solicitações"]
    tab1, tab2, tab3, tab4 = st.tabs(tabs)

    # Função para atualizar dados sem recarregar a página
    def save_data(df_final, sheet_name, data_key):
        try:
            st.session_state.local_data[data_key.lower()] = df_final
            if update_sheet(df_final, sheet_name):
                st.session_state.edited_data[data_key.lower()] = False
                return True
            return False
        except Exception as e:
            st.error(f"Erro ao salvar dados: {str(e)}")
            return False

    # Função para criar tabela editável com estilo consistente
    def create_data_editor(df, key_prefix, columns_config, height=400):
        return st.data_editor(
            df,
            num_rows="dynamic",
            hide_index=True,
            key=f"{key_prefix}_{st.session_state.active_tab}_{int(time.time())}",
            column_config=columns_config,
            use_container_width=True,
            height=height,
            column_order=COLUNAS_ESPERADAS[key_prefix.capitalize()],
            disabled=False,
            on_change=lambda: st.session_state.edited_data.update({key_prefix.lower(): True})
        )

    # Atualizar o estado da tab ativa sem recarregar
    if tab1:
        st.session_state.active_tab = 0
    elif tab2:
        st.session_state.active_tab = 1
    elif tab3:
        st.session_state.active_tab = 2
    elif tab4:
        st.session_state.active_tab = 3

    # Conteúdo das tabs
    if tab1:
        st.subheader("Produtos Químicos")
        if "quimicos" not in dados or dados["quimicos"].empty:
            st.error("Erro ao carregar dados dos produtos químicos!")
        else:
            # Filtros para a tabela
            col1, col2 = st.columns(2)
            with col1:
                filtro_nome = st.selectbox(
                    "🔍 Filtrar por Nome",
                    options=["Todos"] + sorted(dados["quimicos"]['Nome'].unique().tolist()),
                    index=0,
                    key=f"filtro_nome_quimicos_{st.session_state.active_tab}"
                )
            with col2:
                filtro_tipo = st.selectbox(
                    "🔍 Filtrar por Tipo",
                    options=["Todos", "Herbicida", "Fungicida", "Inseticida"],
                    index=0,
                    key=f"filtro_tipo_quimicos_{st.session_state.active_tab}"
                )

            # Aplicar filtro
            df_filtrado = dados["quimicos"].copy()
            if filtro_nome != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
            if filtro_tipo != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Tipo"] == filtro_tipo]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Quimicos"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Quimicos"])
            
            # Tabela editável
            edited_df = create_data_editor(
                df_filtrado,
                "quimicos",
                {
                    "Nome": st.column_config.TextColumn("Nome do Produto", required=True),
                    "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Herbicida", "Fungicida", "Inseticida"]),
                    "Fabricante": "Fabricante",
                    "Concentracao": st.column_config.TextColumn("Concentração", required=True),
                    "Classe": "Classe",
                    "ModoAcao": "Modo de Ação"
                }
            )
            
            # Botão para salvar alterações
            if st.button("Salvar Alterações", key=f"save_quimicos_{st.session_state.active_tab}", use_container_width=True):
                with st.spinner("Salvando dados..."):
                    try:
                        df_completo = st.session_state.local_data["quimicos"].copy()
                        
                        if filtro_nome != "Todos" or filtro_tipo != "Todos":
                            mask = (
                                (df_completo["Nome"].isin(edited_df["Nome"])) &
                                (df_completo["Tipo"] == filtro_tipo if filtro_tipo != "Todos" else True)
                            )
                        else:
                            mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                        
                        df_completo = df_completo[~mask]
                        df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                        df_final = df_final.drop_duplicates(subset=["Nome"], keep="last")
                        df_final = df_final.sort_values(by="Nome").reset_index(drop=True)
                        
                        if save_data(df_final, "Quimicos", "quimicos"):
                            st.success("Dados salvos com sucesso!")
                    except Exception as e:
                        st.error(f"Erro: {str(e)}")
    
    elif tab2:
        st.subheader("Produtos Biológicos")
        if "biologicos" not in dados or dados["biologicos"].empty:
            st.error("Erro ao carregar dados dos produtos biológicos!")
        else:
            # Filtros para a tabela
            col1, col2 = st.columns(2)
            with col1:
                filtro_nome = st.selectbox(
                    "🔍 Filtrar por Nome",
                    options=["Todos"] + sorted(dados["biologicos"]['Nome'].unique().tolist()),
                    index=0,
                    key=f"filtro_nome_biologicos_{st.session_state.active_tab}"
                )
            with col2:
                filtro_tipo = st.selectbox(
                    "🔍 Filtrar por Tipo",
                    options=["Todos", "Bioestimulante", "Controle Biológico"],
                    index=0,
                    key=f"filtro_tipo_biologicos_{st.session_state.active_tab}"
                )

            # Aplicar filtro
            df_filtrado = dados["biologicos"].copy()
            if filtro_nome != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
            if filtro_tipo != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Tipo"] == filtro_tipo]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Biologicos"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"])
            
            # Tabela editável
            edited_df = create_data_editor(
                df_filtrado,
                "biologicos",
                {
                    "Nome": st.column_config.TextColumn("Produto Biológico", required=True),
                    "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Bioestimulante", "Controle Biológico"]),
                    "IngredienteAtivo": st.column_config.TextColumn("Ingrediente Ativo", required=True),
                    "Formulacao": st.column_config.TextColumn("Formulação", required=True),
                    "Aplicacao": st.column_config.TextColumn("Aplicação", required=True),
                    "Validade": st.column_config.TextColumn("Validade", required=True)
                }
            )
            
            # Botão para salvar alterações
            if st.button("Salvar Alterações", key=f"save_biologicos_{st.session_state.active_tab}", use_container_width=True):
                with st.spinner("Salvando dados..."):
                    try:
                        df_completo = st.session_state.local_data["biologicos"].copy()
                        
                        if filtro_nome != "Todos" or filtro_tipo != "Todos":
                            mask = (
                                (df_completo["Nome"].isin(edited_df["Nome"])) &
                                (df_completo["Tipo"] == filtro_tipo if filtro_tipo != "Todos" else True)
                            )
                        else:
                            mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                        
                        df_completo = df_completo[~mask]
                        df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                        df_final = df_final.drop_duplicates(subset=["Nome"], keep="last")
                        df_final = df_final.sort_values(by="Nome").reset_index(drop=True)
                        
                        if save_data(df_final, "Biologicos", "biologicos"):
                            st.success("Dados salvos com sucesso!")
                    except Exception as e:
                        st.error(f"Erro: {str(e)}")
    
    elif tab3:
        st.subheader("Resultados de Compatibilidade")
        if "resultados" not in dados or dados["resultados"].empty:
            st.error("Erro ao carregar dados dos resultados!")
        else:
            # Filtros para a tabela
            col1, col2 = st.columns(2)
            with col1:
                filtro_quimico = st.selectbox(
                    "🔍 Filtrar por Produto Químico",
                    options=["Todos"] + sorted(dados["resultados"]["Quimico"].unique().tolist()),
                    index=0,
                    key=f"filtro_quimico_resultados_{st.session_state.active_tab}"
                )
            with col2:
                filtro_biologico = st.selectbox(
                    "🔍 Filtrar por Produto Biológico",
                    options=["Todos"] + sorted(dados["resultados"]["Biologico"].unique().tolist()),
                    index=0,
                    key=f"filtro_biologico_resultados_{st.session_state.active_tab}"
                )
            
            # Aplicar filtro
            df_filtrado = dados["resultados"].copy()
            if filtro_quimico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
            if filtro_biologico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Resultados"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Resultados"])
            
            # Tabela editável
            edited_df = create_data_editor(
                df_filtrado,
                "resultados",
                {
                    "Data": st.column_config.TextColumn("Data do Teste", required=True),
                    "Quimico": st.column_config.SelectboxColumn("Produto Químico", options=sorted(dados["quimicos"]["Nome"].unique().tolist()), required=True),
                    "Biologico": st.column_config.SelectboxColumn("Produto Biológico", options=sorted(dados["biologicos"]["Nome"].unique().tolist()), required=True),
                    "Duracao": st.column_config.NumberColumn("Duração (horas)", min_value=0, default=0),
                    "Tipo": st.column_config.SelectboxColumn("Tipo de Teste", options=["Simples", "Composto"], required=True),
                    "Resultado": st.column_config.SelectboxColumn("Resultado", options=["Compatível", "Incompatível"], required=True)
                }
            )
            
            # Botão para salvar alterações
            if st.button("Salvar Alterações", key=f"save_resultados_{st.session_state.active_tab}", use_container_width=True):
                with st.spinner("Salvando dados..."):
                    try:
                        df_completo = st.session_state.local_data["resultados"].copy()
                        
                        if filtro_quimico != "Todos" or filtro_biologico != "Todos":
                            mask = (
                                (df_completo["Quimico"] == filtro_quimico) |
                                (df_completo["Biologico"] == filtro_biologico)
                            )
                        else:
                            mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                        
                        df_completo = df_completo[~mask]
                        df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                        df_final = df_final.drop_duplicates(subset=["Quimico", "Biologico"], keep="last")
                        df_final = df_final.sort_values(by="Quimico").reset_index(drop=True)
                        
                        if save_data(df_final, "Resultados", "resultados"):
                            st.success("Dados salvos com sucesso!")
                    except Exception as e:
                        st.error(f"Erro: {str(e)}")
    
    elif tab4:
        st.subheader("Solicitações")
        if "solicitacoes" not in dados or dados["solicitacoes"].empty:
            st.warning("Sem solicitações para exibir")
        else:
            # Filtros para a tabela
            col1, col2, col3 = st.columns(3)
            with col1:
                filtro_status = st.selectbox(
                    "🔍 Filtrar por Status",
                    options=["Todos", "Pendente", "Em andamento", "Concluído", "Cancelado"],
                    index=0,
                    key=f"filtro_status_solicitacoes_{st.session_state.active_tab}"
                )
            with col2:
                filtro_quimico = st.selectbox(
                    "🔍 Filtrar por Produto Químico",
                    options=["Todos"] + sorted(dados["solicitacoes"]["Quimico"].unique().tolist()),
                    index=0,
                    key=f"filtro_quimico_solicitacoes_{st.session_state.active_tab}"
                )
            with col3:
                filtro_biologico = st.selectbox(
                    "🔍 Filtrar por Produto Biológico",
                    options=["Todos"] + sorted(dados["solicitacoes"]["Biologico"].unique().tolist()),
                    index=0,
                    key=f"filtro_biologico_solicitacoes_{st.session_state.active_tab}"
                )
            
            # Aplicar filtro
            df_filtrado = dados["solicitacoes"].copy()
            if filtro_status != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]
            if filtro_quimico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
            if filtro_biologico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
            
            # Tabela editável
            edited_df = create_data_editor(
                df_filtrado,
                "solicitacoes",
                {
                    "Data": st.column_config.TextColumn("Data da Solicitação", required=True),
                    "Solicitante": st.column_config.TextColumn("Solicitante", required=True),
                    "Quimico": st.column_config.SelectboxColumn("Produto Químico", options=sorted(dados["quimicos"]["Nome"].unique().tolist()), required=True),
                    "Biologico": st.column_config.SelectboxColumn("Produto Biológico", options=sorted(dados["biologicos"]["Nome"].unique().tolist()), required=True),
                    "Observacoes": st.column_config.TextColumn("Observações", required=True),
                    "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Análise", "Concluído", "Cancelado"])
                }
            )
            
            # Botão para salvar alterações
            if st.button("Salvar Alterações", key=f"save_solicitacoes_{st.session_state.active_tab}", use_container_width=True):
                with st.spinner("Salvando dados..."):
                    try:
                        df_completo = st.session_state.local_data["solicitacoes"].copy()
                        
                        if filtro_status != "Todos" or filtro_quimico != "Todos" or filtro_biologico != "Todos":
                            mask = (
                                (df_completo["Status"] == filtro_status) |
                                (df_completo["Quimico"] == filtro_quimico) |
                                (df_completo["Biologico"] == filtro_biologico)
                            )
                        else:
                            mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                        
                        df_completo = df_completo[~mask]
                        df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                        df_final = df_final.drop_duplicates(subset=["Solicitante"], keep="last")
                        df_final = df_final.sort_values(by="Data").reset_index(drop=True)
                        
                        if save_data(df_final, "Solicitacoes", "solicitacoes"):
                            st.success("Dados salvos com sucesso!")
                    except Exception as e:
                        st.error(f"Erro: {str(e)}")

    # Removendo o componente JavaScript para evitar conflitos
    def fix_table_buttons():
        pass

########################################## SIDEBAR ##########################################

def main():
    if 'local_data' not in st.session_state:
        st.session_state.local_data = {
            "quimicos": pd.DataFrame(),
            "biologicos": pd.DataFrame(),
            "resultados": pd.DataFrame(),
            "solicitacoes": pd.DataFrame()
        }
    
    # Inicializar a página atual se não existir
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "Compatibilidade"

    st.sidebar.image("imagens/logo-cocal.png")
    st.sidebar.title("Menu")
    
    # Usar o estado atual para definir o valor padrão do radio
    menu_option = st.sidebar.radio(
        "Selecione a funcionalidade:",
        ("Compatibilidade", "Gerenciamento"),
        index=0 if st.session_state.current_page == "Compatibilidade" else 1
    )
    
    # Atualizar o estado da página atual
    st.session_state.current_page = menu_option

    st.sidebar.markdown("---")

    if menu_option == "Compatibilidade":
        compatibilidade()
    elif menu_option == "Gerenciamento":
        gerenciamento()

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