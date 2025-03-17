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
        st.session_state.local_data[data_key.lower()] = df_final
        if update_sheet(df_final, sheet_name):
            st.session_state.edited_data[data_key.lower()] = False
            return True
        return False

    # Função para criar tabela editável com estilo consistente
    def create_data_editor(df, key_prefix, columns_config, height=400):
        return st.data_editor(
            df,
            num_rows="dynamic",
            hide_index=True,
            key=f"{key_prefix}_{int(time.time())}",
            column_config=columns_config,
            use_container_width=True,
            height=height,
            column_order=COLUNAS_ESPERADAS[key_prefix.capitalize()],
            disabled=False
        )

    # Função para mostrar detalhes de compatibilidade
    def show_compatibility_details(quimico, biologico):
        if quimico and biologico:
            resultados = dados["resultados"]
            match = resultados[
                (resultados["ProdutoQuimico"] == quimico) & 
                (resultados["ProdutoBiologico"] == biologico)
            ]
            
            if not match.empty:
                status = match.iloc[0]["Compatibilidade"]
                obs = match.iloc[0]["Observacoes"]
                
                if status == "Compatível":
                    st.success(f"✅ {quimico} é compatível com {biologico}")
                elif status == "Incompatível":
                    st.error(f"❌ {quimico} é incompatível com {biologico}")
                else:
                    st.warning(f"⚠️ Compatibilidade entre {quimico} e {biologico} não foi testada")
                
                if obs and obs.strip():
                    st.info(f"📝 Observações: {obs}")
                
                # Mostrar detalhes dos produtos
                with st.expander("Ver detalhes dos produtos"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Produto Químico")
                        quim_data = dados["quimicos"][dados["quimicos"]["Nome"] == quimico].iloc[0]
                        st.write(f"**Tipo:** {quim_data['Tipo']}")
                        st.write(f"**Fabricante:** {quim_data['Fabricante']}")
                        st.write(f"**Concentração:** {quim_data['Concentracao']}")
                        st.write(f"**Classe:** {quim_data['Classe']}")
                        st.write(f"**Modo de Ação:** {quim_data['ModoAcao']}")
                    
                    with col2:
                        st.subheader("Produto Biológico")
                        bio_data = dados["biologicos"][dados["biologicos"]["Nome"] == biologico].iloc[0]
                        st.write(f"**Fabricante:** {bio_data['Fabricante']}")
                        st.write(f"**Concentração:** {bio_data['Concentracao']}")
                        st.write(f"**Tipo de Organismo:** {bio_data['TipoOrganismo']}")
                        st.write(f"**Modo de Ação:** {bio_data['ModoAcao']}")

    # Conteúdo das tabs
    if tab1:
        st.session_state.active_tab = 0
        st.subheader("Produtos Químicos")
        if "quimicos" not in dados or dados["quimicos"].empty:
            st.error("Erro ao carregar dados dos produtos químicos!")
        else:
            # Opções para o usuário escolher entre registrar ou visualizar
            opcao = st.radio("Escolha uma opção:", ["Novo produto", "Produtos cadastrados"], key="opcao_quimicos")
            
            if opcao == "Novo produto":
                # Inicializar variáveis de estado se não existirem
                if 'quimico_form_submitted' not in st.session_state:
                    st.session_state.quimico_form_submitted = False
                if 'quimico_form_success' not in st.session_state:
                    st.session_state.quimico_form_success = False
                if 'quimico_form_error' not in st.session_state:
                    st.session_state.quimico_form_error = ""
                
                # Função para processar o envio do formulário
                def submit_quimico_form():
                    nome = st.session_state.quimico_nome
                    tipo = st.session_state.tipo_quimico
                    fabricante = st.session_state.quimico_fabricante
                    concentracao = st.session_state.quimico_concentracao
                    classe = st.session_state.quimico_classe
                    modo_acao = st.session_state.quimico_modo_acao
                    
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
                            st.session_state.quimico_form_submitted = True
                            st.session_state.quimico_form_success = False
                            st.session_state.quimico_form_error = f"Produto '{nome}' já existe!"
                        else:
                            # Adicionar à planilha
                            if append_to_sheet(novo_produto, "Quimicos"):
                                # Atualizar dados locais
                                nova_linha = pd.DataFrame([novo_produto])
                                st.session_state.local_data["quimicos"] = pd.concat(
                                    [st.session_state.local_data["quimicos"], nova_linha], 
                                    ignore_index=True
                                )
                                
                                st.session_state.quimico_form_submitted = True
                                st.session_state.quimico_form_success = True
                                st.session_state.quimico_form_error = ""
                            else:
                                st.session_state.quimico_form_submitted = True
                                st.session_state.quimico_form_success = False
                                st.session_state.quimico_form_error = "Falha ao adicionar produto"
                    else:
                        st.session_state.quimico_form_submitted = True
                        st.session_state.quimico_form_success = False
                        st.session_state.quimico_form_error = "Nome do produto é obrigatório"
                
                with st.form("novo_quimico_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("Nome do Produto", key="quimico_nome")
                        st.selectbox("Tipo", options=["Herbicida", "Fungicida", "Inseticida"], key="tipo_quimico")
                        st.text_input("Fabricante", key="quimico_fabricante")
                    with col2:
                        st.number_input("Concentração", value=0.0, step=1.0, key="quimico_concentracao")
                        st.text_input("Classe", key="quimico_classe")
                        st.text_input("Modo de Ação", key="quimico_modo_acao")
                    
                    submitted = st.form_submit_button("Adicionar Produto", on_click=submit_quimico_form)
                
                # Mostrar mensagens de sucesso ou erro abaixo do formulário
                if st.session_state.quimico_form_submitted:
                    if st.session_state.quimico_form_success:
                        st.success(f"Produto {st.session_state.quimico_nome} adicionado com sucesso!")
                        st.session_state.quimico_form_submitted = False
                        st.session_state.quimico_form_success = False
                    else:
                        st.error(st.session_state.quimico_form_error)
            
            else:  # Visualizar produtos cadastrados
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_nome = st.selectbox(
                        "🔍 Filtrar por Nome",
                        options=["Todos"] + sorted(dados["quimicos"]['Nome'].unique().tolist()),
                        index=0,
                        key="filtro_nome_quimicos"
                    )
                with col2:
                    filtro_tipo = st.selectbox(
                        "🔍 Filtrar por Tipo",
                        options=["Todos", "Herbicida", "Fungicida", "Inseticida"],
                        index=0,
                        key="filtro_tipo_quimicos"
                    )

                # Aplicar filtro
                df_filtrado = dados["quimicos"].copy()
                if filtro_nome != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
                if filtro_tipo != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Tipo"] == filtro_tipo]
                
                # Garantir que apenas as colunas esperadas estejam presentes
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Quimicos"]].copy()
                
                # Garantir que o DataFrame tenha pelo menos uma linha vazia para adição
                if df_filtrado.empty:
                    df_vazio = pd.DataFrame(columns=COLUNAS_ESPERADAS["Quimicos"])
                    df_filtrado = df_vazio
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    hide_index=True,
                    key=f"quimicos_editor_{filtro_nome}_{filtro_tipo}_{int(time.time())}",
                    column_config={
                        "Nome": st.column_config.TextColumn("Nome do Produto", required=True),
                        "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Herbicida", "Fungicida", "Inseticida"]),
                        "Fabricante": "Fabricante",
                        "Concentracao": st.column_config.TextColumn("Concentração", required=True),
                        "Classe": "Classe",
                        "ModoAcao": "Modo de Ação",
                    },
                    use_container_width=True,
                    height=400,
                    on_change=lambda: st.session_state.edited_data.update({"quimicos": True}),
                    disabled=False,
                    column_order=COLUNAS_ESPERADAS["Quimicos"]
                )
                
                # Botão para salvar alterações
                col_btn = st.container()
                with col_btn:
                    if st.button("Salvar Alterações", key="save_quimicos", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                # Obter dados completos originais
                                df_completo = st.session_state.local_data["quimicos"].copy()
                                
                                # Criar máscara para identificar registros filtrados
                                if filtro_nome != "Todos" or filtro_tipo != "Todos":
                                    mask = (
                                        (df_completo["Nome"].isin(edited_df["Nome"])) &
                                        (df_completo["Tipo"] == filtro_tipo)
                                    )
                                else:
                                    mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                                
                                # Remover registros antigos que correspondem ao filtro
                                df_completo = df_completo[~mask]
                                
                                # Adicionar dados editados
                                df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                                
                                # Remover duplicatas mantendo a última ocorrência
                                df_final = df_final.drop_duplicates(
                                    subset=["Nome", "Tipo"], 
                                    keep="last"
                                )
                                
                                # Ordenar e resetar índice
                                df_final = df_final.sort_values(by="Nome").reset_index(drop=True)
                                
                                # Atualizar dados sem recarregar a página
                                if save_data(df_final, "Quimicos", "quimicos"):
                                    st.success("Dados salvos com sucesso!")
                            except Exception as e:
                                st.error(f"Erro: {str(e)}")
    
    elif tab2:
        st.session_state.active_tab = 1
        st.subheader("Produtos Biológicos")
        if "biologicos" not in dados or dados["biologicos"].empty:
            st.error("Erro ao carregar dados dos produtos biológicos!")
        else:
            opcao = st.radio("Escolha uma opção:", ["Novo produto", "Produtos cadastrados"], key="opcao_biologicos")
            
            if opcao == "Novo produto":
                # Inicializar variáveis de estado
                if 'biologico_form_submitted' not in st.session_state:
                    st.session_state.biologico_form_submitted = False
                if 'biologico_form_success' not in st.session_state:
                    st.session_state.biologico_form_success = False
                if 'biologico_form_error' not in st.session_state:
                    st.session_state.biologico_form_error = ""
                
                def submit_biologico_form():
                    nome = st.session_state.biologico_nome
                    fabricante = st.session_state.biologico_fabricante
                    concentracao = st.session_state.biologico_concentracao
                    tipo_organismo = st.session_state.tipo_organismo
                    modo_acao = st.session_state.biologico_modo_acao
                    
                    if nome:
                        novo_produto = {
                            "Nome": nome,
                            "Fabricante": fabricante,
                            "Concentracao": concentracao,
                            "TipoOrganismo": tipo_organismo,
                            "ModoAcao": modo_acao
                        }
                        
                        if nome in dados["biologicos"]["Nome"].values:
                            st.session_state.biologico_form_submitted = True
                            st.session_state.biologico_form_success = False
                            st.session_state.biologico_form_error = f"Produto '{nome}' já existe!"
                        else:
                            if append_to_sheet(novo_produto, "Biologicos"):
                                nova_linha = pd.DataFrame([novo_produto])
                                st.session_state.local_data["biologicos"] = pd.concat([st.session_state.local_data["biologicos"], nova_linha], ignore_index=True)
                                st.session_state.biologico_form_submitted = True
                                st.session_state.biologico_form_success = True
                                st.session_state.biologico_form_error = ""
                            else:
                                st.session_state.biologico_form_submitted = True
                                st.session_state.biologico_form_success = False
                                st.session_state.biologico_form_error = "Falha ao adicionar produto"
                    else:
                        st.session_state.biologico_form_submitted = True
                        st.session_state.biologico_form_success = False
                        st.session_state.biologico_form_error = "Nome do produto é obrigatório"
                
                with st.form("novo_biologico_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("Nome do Produto", key="biologico_nome")
                        st.text_input("Fabricante", key="biologico_fabricante")
                        st.number_input("Concentração", value=0.0, step=1.0, key="biologico_concentracao")
                    with col2:
                        st.text_input("Tipo de Organismo", key="tipo_organismo")
                        st.text_input("Modo de Ação", key="biologico_modo_acao")
                    
                    submitted = st.form_submit_button("Adicionar Produto", on_click=submit_biologico_form)
                
                if st.session_state.biologico_form_submitted:
                    if st.session_state.biologico_form_success:
                        st.success(f"Produto {st.session_state.biologico_nome} adicionado com sucesso!")
                        st.session_state.biologico_form_submitted = False
                        st.session_state.biologico_form_success = False
                    else:
                        st.error(st.session_state.biologico_form_error)
            
            else:  # Visualizar produtos cadastrados
                # Filtros para a tabela
                filtro_nome = st.selectbox(
                    "🔍 Filtrar por Nome",
                    options=["Todos"] + sorted(dados["biologicos"]['Nome'].unique().tolist()),
                    index=0,
                    key="filtro_nome_biologicos"
                )

                # Aplicar filtro
                df_filtrado = dados["biologicos"].copy()
                if filtro_nome != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
                
                # Garantir colunas esperadas
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Biologicos"]].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"])
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    hide_index=True,
                    key=f"biologicos_editor_{filtro_nome}_{int(time.time())}",
                    column_config={
                        "Nome": st.column_config.TextColumn("Nome do Produto", required=True),
                        "Fabricante": "Fabricante",
                        "Concentracao": st.column_config.TextColumn("Concentração", required=True),
                        "TipoOrganismo": "Tipo de Organismo",
                        "ModoAcao": "Modo de Ação"
                    },
                    use_container_width=True,
                    height=400,
                    on_change=lambda: st.session_state.edited_data.update({"biologicos": True}),
                    disabled=False,
                    column_order=COLUNAS_ESPERADAS["Biologicos"]
                )
                
                # Botão para salvar alterações
                col_btn = st.container()
                with col_btn:
                    if st.button("Salvar Alterações", key="save_biologicos", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                df_completo = st.session_state.local_data["biologicos"].copy()
                                
                                if filtro_nome != "Todos":
                                    mask = df_completo["Nome"].isin(edited_df["Nome"])
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
        st.session_state.active_tab = 2
        st.subheader("Resultados de Compatibilidade")
        if "resultados" not in dados or dados["resultados"].empty:
            st.error("Erro ao carregar dados dos resultados de compatibilidade!")
        else:
            # Filtros para a tabela
            col1, col2 = st.columns(2)
            with col1:
                filtro_quimico = st.selectbox(
                    "🔍 Filtrar por Produto Químico",
                    options=["Todos"] + sorted(dados["resultados"]['ProdutoQuimico'].unique().tolist()),
                    index=0,
                    key="filtro_quimico_resultados"
                )
            with col2:
                filtro_biologico = st.selectbox(
                    "🔍 Filtrar por Produto Biológico",
                    options=["Todos"] + sorted(dados["resultados"]['ProdutoBiologico'].unique().tolist()),
                    index=0,
                    key="filtro_biologico_resultados"
                )

            # Mostrar detalhes de compatibilidade se ambos os produtos estiverem selecionados
            if filtro_quimico != "Todos" and filtro_biologico != "Todos":
                show_compatibility_details(filtro_quimico, filtro_biologico)
                st.divider()

            # Aplicar filtros
            df_filtrado = dados["resultados"].copy()
            if filtro_quimico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["ProdutoQuimico"] == filtro_quimico]
            if filtro_biologico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["ProdutoBiologico"] == filtro_biologico]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Resultados"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Resultados"])
            
            # Configuração das colunas
            column_config = {
                "ProdutoQuimico": st.column_config.SelectboxColumn(
                    "Produto Químico",
                    options=sorted(dados["quimicos"]["Nome"].unique()),
                    required=True,
                    help="Selecione o produto químico para testar compatibilidade"
                ),
                "ProdutoBiologico": st.column_config.SelectboxColumn(
                    "Produto Biológico",
                    options=sorted(dados["biologicos"]["Nome"].unique()),
                    required=True,
                    help="Selecione o produto biológico para testar compatibilidade"
                ),
                "Compatibilidade": st.column_config.SelectboxColumn(
                    "Compatibilidade",
                    options=["Compatível", "Incompatível", "Não testado"],
                    required=True,
                    help="Indique o resultado do teste de compatibilidade"
                ),
                "Observacoes": st.column_config.TextColumn(
                    "Observações",
                    help="Adicione notas sobre o teste, condições especiais ou restrições"
                )
            }
            
            # Tabela editável com nova função helper
            edited_df = create_data_editor(
                df_filtrado,
                "resultados",
                column_config,
                height=400
            )
            
            # Atualizar estado quando houver mudanças
            if edited_df is not None:
                st.session_state.edited_data["resultados"] = True
            
            # Botão para salvar alterações
            col_btn = st.container()
            with col_btn:
                if st.button("Salvar Alterações", key="save_resultados", use_container_width=True):
                    with st.spinner("Salvando dados..."):
                        try:
                            df_completo = st.session_state.local_data["resultados"].copy()
                            
                            if filtro_quimico != "Todos" or filtro_biologico != "Todos":
                                mask = (
                                    (df_completo["ProdutoQuimico"].isin(edited_df["ProdutoQuimico"])) &
                                    (df_completo["ProdutoBiologico"].isin(edited_df["ProdutoBiologico"]))
                                )
                            else:
                                mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                            
                            df_completo = df_completo[~mask]
                            df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                            df_final = df_final.drop_duplicates(
                                subset=["ProdutoQuimico", "ProdutoBiologico"],
                                keep="last"
                            )
                            df_final = df_final.sort_values(by=["ProdutoQuimico", "ProdutoBiologico"]).reset_index(drop=True)
                            
                            if save_data(df_final, "Resultados", "resultados"):
                                st.success("Dados salvos com sucesso!")
                        except Exception as e:
                            st.error(f"Erro: {str(e)}")
            
            # Mostrar estatísticas de compatibilidade
            with st.expander("📊 Estatísticas de Compatibilidade"):
                stats_df = dados["resultados"].copy()
                total = len(stats_df)
                compativeis = len(stats_df[stats_df["Compatibilidade"] == "Compatível"])
                incompativeis = len(stats_df[stats_df["Compatibilidade"] == "Incompatível"])
                nao_testados = len(stats_df[stats_df["Compatibilidade"] == "Não testado"])
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Compatíveis", f"{compativeis} ({(compativeis/total*100):.1f}%)")
                with col2:
                    st.metric("Incompatíveis", f"{incompativeis} ({(incompativeis/total*100):.1f}%)")
                with col3:
                    st.metric("Não Testados", f"{nao_testados} ({(nao_testados/total*100):.1f}%)")
    elif tab4:
        st.session_state.active_tab = 3
        st.subheader("Solicitações de Teste")
        if "solicitacoes" not in dados or dados["solicitacoes"].empty:
            st.error("Erro ao carregar dados das solicitações!")
        else:
            # Filtros para a tabela
            col1, col2 = st.columns(2)
            with col1:
                filtro_status = st.selectbox(
                    "🔍 Filtrar por Status",
                    options=["Todos", "Pendente", "Em análise", "Concluído"],
                    index=0,
                    key="filtro_status_solicitacoes"
                )
            with col2:
                filtro_solicitante = st.selectbox(
                    "🔍 Filtrar por Solicitante",
                    options=["Todos"] + sorted(dados["solicitacoes"]['Solicitante'].unique().tolist()),
                    index=0,
                    key="filtro_solicitante_solicitacoes"
                )

            # Aplicar filtros
            df_filtrado = dados["solicitacoes"].copy()
            if filtro_status != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]
            if filtro_solicitante != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Solicitante"] == filtro_solicitante]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
            
            # Tabela editável
            edited_df = st.data_editor(
                df_filtrado,
                num_rows="dynamic",
                hide_index=True,
                key=f"solicitacoes_editor_{filtro_status}_{filtro_solicitante}_{int(time.time())}",
                column_config={
                    "DataSolicitacao": st.column_config.DateColumn(
                        "Data da Solicitação",
                        format="DD/MM/YYYY",
                        required=True
                    ),
                    "Solicitante": st.column_config.TextColumn("Solicitante", required=True),
                    "ProdutoQuimico": st.column_config.SelectboxColumn(
                        "Produto Químico",
                        options=sorted(dados["quimicos"]["Nome"].unique()),
                        required=True
                    ),
                    "ProdutoBiologico": st.column_config.SelectboxColumn(
                        "Produto Biológico",
                        options=sorted(dados["biologicos"]["Nome"].unique()),
                        required=True
                    ),
                    "Status": st.column_config.SelectboxColumn(
                        "Status",
                        options=["Pendente", "Em análise", "Concluído"],
                        required=True
                    ),
                    "Observacoes": "Observações"
                },
                use_container_width=True,
                height=400,
                on_change=lambda: st.session_state.edited_data.update({"solicitacoes": True}),
                disabled=False,
                column_order=COLUNAS_ESPERADAS["Solicitacoes"]
            )
            
            # Botão para salvar alterações
            col_btn = st.container()
            with col_btn:
                if st.button("Salvar Alterações", key="save_solicitacoes", use_container_width=True):
                    with st.spinner("Salvando dados..."):
                        try:
                            df_completo = st.session_state.local_data["solicitacoes"].copy()
                            
                            if filtro_status != "Todos" or filtro_solicitante != "Todos":
                                mask = (
                                    (df_completo["Status"] == filtro_status if filtro_status != "Todos" else True) &
                                    (df_completo["Solicitante"] == filtro_solicitante if filtro_solicitante != "Todos" else True)
                                )
                            else:
                                mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                            
                            df_completo = df_completo[~mask]
                            df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                            df_final = df_final.sort_values(by=["DataSolicitacao", "Solicitante"]).reset_index(drop=True)
                            
                            if save_data(df_final, "Solicitacoes", "solicitacoes"):
                                st.success("Dados salvos com sucesso!")
                        except Exception as e:
                            st.error(f"Erro: {str(e)}")
            
            # Mostrar estatísticas
            with st.expander("📊 Estatísticas"):
                stats_df = dados["solicitacoes"].copy()
                total = len(stats_df)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total de Solicitações", total)
                    status_counts = stats_df["Status"].value_counts()
                    st.write("**Por Status:**")
                    for status, count in status_counts.items():
                        if status == "Pendente":
                            st.warning(f"⏳ {count} ({(count/total*100):.1f}%)")
                        elif status == "Em análise":
                            st.info(f"🔄 {count} ({(count/total*100):.1f}%)")
                        else:  # Concluído
                            st.success(f"✅ {count} ({(count/total*100):.1f}%)")
                
                with col2:
                    solicitantes = stats_df["Solicitante"].nunique()
                    st.metric("Solicitantes Únicos", solicitantes)
                    
                    # Tempo médio de conclusão
                    concluidos = stats_df[stats_df["Status"] == "Concluído"]
                    if not concluidos.empty:
                        tempo_medio = (
                            concluidos["DataSolicitacao"]
                            .apply(lambda x: (datetime.now() - x).days)
                            .mean()
                        )
                        st.metric("Tempo Médio (dias)", f"{tempo_medio:.1f}")

    # Função para mostrar detalhes do produto
    def show_product_details(produto, tipo):
        if not produto:
            return
        
        if tipo == "quimico":
            data = dados["quimicos"][dados["quimicos"]["Nome"] == produto]
            if not data.empty:
                data = data.iloc[0]
                with st.container():
                    st.write(f"**Tipo:** {data['Tipo']}")
                    st.write(f"**Fabricante:** {data['Fabricante']}")
                    st.write(f"**Concentração:** {data['Concentracao']}")
                    st.write(f"**Classe:** {data['Classe']}")
                    st.write(f"**Modo de Ação:** {data['ModoAcao']}")
                
                # Mostrar compatibilidades conhecidas
                compatibilidades = dados["resultados"][dados["resultados"]["ProdutoQuimico"] == produto]
                if not compatibilidades.empty:
                    st.divider()
                    st.subheader("Compatibilidades Conhecidas")
                    for _, row in compatibilidades.iterrows():
                        status = row["Compatibilidade"]
                        bio = row["ProdutoBiologico"]
                        if status == "Compatível":
                            st.success(f"✅ Compatível com {bio}")
                        elif status == "Incompatível":
                            st.error(f"❌ Incompatível com {bio}")
                        else:
                            st.warning(f"⚠️ Não testado com {bio}")
        
        else:  # tipo == "biologico"
            data = dados["biologicos"][dados["biologicos"]["Nome"] == produto]
            if not data.empty:
                data = data.iloc[0]
                with st.container():
                    st.write(f"**Fabricante:** {data['Fabricante']}")
                    st.write(f"**Concentração:** {data['Concentracao']}")
                    st.write(f"**Tipo de Organismo:** {data['TipoOrganismo']}")
                    st.write(f"**Modo de Ação:** {data['ModoAcao']}")
                
                # Mostrar compatibilidades conhecidas
                compatibilidades = dados["resultados"][dados["resultados"]["ProdutoBiologico"] == produto]
                if not compatibilidades.empty:
                    st.divider()
                    st.subheader("Compatibilidades Conhecidas")
                    for _, row in compatibilidades.iterrows():
                        status = row["Compatibilidade"]
                        quim = row["ProdutoQuimico"]
                        if status == "Compatível":
                            st.success(f"✅ Compatível com {quim}")
                        elif status == "Incompatível":
                            st.error(f"❌ Incompatível com {quim}")
                        else:
                            st.warning(f"⚠️ Não testado com {quim}")

    if tab1:
        st.session_state.active_tab = 0
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
                    key="filtro_nome_quimicos"
                )
            with col2:
                filtro_tipo = st.selectbox(
                    "🔍 Filtrar por Tipo",
                    options=["Todos", "Herbicida", "Fungicida", "Inseticida"],
                    index=0,
                    key="filtro_tipo_quimicos"
                )

            # Mostrar detalhes do produto se selecionado
            if filtro_nome != "Todos":
                with st.expander("Ver detalhes do produto"):
                    show_product_details(filtro_nome, "quimico")

            # Aplicar filtros
            df_filtrado = dados["quimicos"].copy()
            if filtro_nome != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
            if filtro_tipo != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Tipo"] == filtro_tipo]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Quimicos"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Quimicos"])
            
            # Configuração das colunas
            column_config = {
                "Nome": st.column_config.TextColumn(
                    "Nome do Produto",
                    required=True,
                    help="Nome único do produto químico"
                ),
                "Tipo": st.column_config.SelectboxColumn(
                    "Tipo",
                    options=["Herbicida", "Fungicida", "Inseticida"],
                    required=True,
                    help="Categoria do produto"
                ),
                "Fabricante": st.column_config.TextColumn(
                    "Fabricante",
                    help="Nome do fabricante do produto"
                ),
                "Concentracao": st.column_config.NumberColumn(
                    "Concentração",
                    required=True,
                    help="Concentração do princípio ativo"
                ),
                "Classe": st.column_config.TextColumn(
                    "Classe",
                    help="Classe do produto"
                ),
                "ModoAcao": st.column_config.TextColumn(
                    "Modo de Ação",
                    help="Como o produto atua"
                )
            }
            
            # Tabela editável
            edited_df = create_data_editor(
                df_filtrado,
                "quimicos",
                column_config,
                height=400
            )
            
            if edited_df is not None:
                st.session_state.edited_data["quimicos"] = True
            
            # Botão para salvar alterações
            if st.button("Salvar Alterações", key="save_quimicos", use_container_width=True):
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
            
            # Mostrar estatísticas
            with st.expander("📊 Estatísticas"):
                stats_df = dados["quimicos"].copy()
                total = len(stats_df)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total de Produtos", total)
                    tipos = stats_df["Tipo"].value_counts()
                    st.write("**Por Tipo:**")
                    for tipo, count in tipos.items():
                        st.write(f"- {tipo}: {count} ({(count/total*100):.1f}%)")
                
                with col2:
                    fabricantes = stats_df["Fabricante"].nunique()
                    st.metric("Fabricantes", fabricantes)
                    
                    # Compatibilidades
                    comp_stats = dados["resultados"][
                        dados["resultados"]["ProdutoQuimico"].isin(stats_df["Nome"])
                    ]["Compatibilidade"].value_counts()
                    
                    st.write("**Compatibilidades:**")
                    total_comp = comp_stats.sum()
                    if total_comp > 0:
                        for status, count in comp_stats.items():
                            if status == "Compatível":
                                st.success(f"✅ {count} ({(count/total_comp*100):.1f}%)")
                            elif status == "Incompatível":
                                st.error(f"❌ {count} ({(count/total_comp*100):.1f}%)")
                            else:
                                st.warning(f"⚠️ {count} ({(count/total_comp*100):.1f}%)")

    elif tab2:
        st.session_state.active_tab = 1
        st.subheader("Produtos Biológicos")
        if "biologicos" not in dados or dados["biologicos"].empty:
            st.error("Erro ao carregar dados dos produtos biológicos!")
        else:
            # Filtros para a tabela
            filtro_nome = st.selectbox(
                "🔍 Filtrar por Nome",
                options=["Todos"] + sorted(dados["biologicos"]['Nome'].unique().tolist()),
                index=0,
                key="filtro_nome_biologicos"
            )

            # Mostrar detalhes do produto se selecionado
            if filtro_nome != "Todos":
                with st.expander("Ver detalhes do produto"):
                    show_product_details(filtro_nome, "biologico")

            # Aplicar filtro
            df_filtrado = dados["biologicos"].copy()
            if filtro_nome != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Biologicos"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"])
            
            # Configuração das colunas
            column_config = {
                "Nome": st.column_config.TextColumn(
                    "Nome do Produto",
                    required=True,
                    help="Nome único do produto biológico"
                ),
                "Fabricante": st.column_config.TextColumn(
                    "Fabricante",
                    help="Nome do fabricante do produto"
                ),
                "Concentracao": st.column_config.NumberColumn(
                    "Concentração",
                    required=True,
                    help="Concentração do organismo ativo"
                ),
                "TipoOrganismo": st.column_config.TextColumn(
                    "Tipo de Organismo",
                    help="Tipo do organismo presente no produto"
                ),
                "ModoAcao": st.column_config.TextColumn(
                    "Modo de Ação",
                    help="Como o produto atua"
                )
            }
            
            # Tabela editável
            edited_df = create_data_editor(
                df_filtrado,
                "biologicos",
                column_config,
                height=400
            )
            
            if edited_df is not None:
                st.session_state.edited_data["biologicos"] = True
            
            # Botão para salvar alterações
            if st.button("Salvar Alterações", key="save_biologicos", use_container_width=True):
                with st.spinner("Salvando dados..."):
                    try:
                        df_completo = st.session_state.local_data["biologicos"].copy()
                        
                        if filtro_nome != "Todos":
                            mask = df_completo["Nome"].isin(edited_df["Nome"])
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
            
            # Mostrar estatísticas
            with st.expander("📊 Estatísticas"):
                stats_df = dados["biologicos"].copy()
                total = len(stats_df)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total de Produtos", total)
                    organismos = stats_df["TipoOrganismo"].value_counts()
                    st.write("**Por Tipo de Organismo:**")
                    for org, count in organismos.items():
                        st.write(f"- {org}: {count} ({(count/total*100):.1f}%)")
                
                with col2:
                    fabricantes = stats_df["Fabricante"].nunique()
                    st.metric("Fabricantes", fabricantes)
                    
                    # Compatibilidades
                    comp_stats = dados["resultados"][
                        dados["resultados"]["ProdutoBiologico"].isin(stats_df["Nome"])
                    ]["Compatibilidade"].value_counts()
                    
                    st.write("**Compatibilidades:**")
                    total_comp = comp_stats.sum()
                    if total_comp > 0:
                        for status, count in comp_stats.items():
                            if status == "Compatível":
                                st.success(f"✅ {count} ({(count/total_comp*100):.1f}%)")
                            elif status == "Incompatível":
                                st.error(f"❌ {count} ({(count/total_comp*100):.1f}%)")
                            else:
                                st.warning(f"⚠️ {count} ({(count/total_comp*100):.1f}%)")

    elif tab3:
        st.session_state.active_tab = 2
        st.subheader("Resultados de Compatibilidade")
        if "resultados" not in dados or dados["resultados"].empty:
            st.error("Erro ao carregar dados dos resultados de compatibilidade!")
        else:
            # Filtros para a tabela
            col1, col2 = st.columns(2)
            with col1:
                filtro_quimico = st.selectbox(
                    "🔍 Filtrar por Produto Químico",
                    options=["Todos"] + sorted(dados["resultados"]['ProdutoQuimico'].unique().tolist()),
                    index=0,
                    key="filtro_quimico_resultados"
                )
            with col2:
                filtro_biologico = st.selectbox(
                    "🔍 Filtrar por Produto Biológico",
                    options=["Todos"] + sorted(dados["resultados"]['ProdutoBiologico'].unique().tolist()),
                    index=0,
                    key="filtro_biologico_resultados"
                )

            # Mostrar detalhes de compatibilidade se ambos os produtos estiverem selecionados
            if filtro_quimico != "Todos" and filtro_biologico != "Todos":
                show_compatibility_details(filtro_quimico, filtro_biologico)
                st.divider()

            # Aplicar filtros
            df_filtrado = dados["resultados"].copy()
            if filtro_quimico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["ProdutoQuimico"] == filtro_quimico]
            if filtro_biologico != "Todos":
                df_filtrado = df_filtrado[df_filtrado["ProdutoBiologico"] == filtro_biologico]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Resultados"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Resultados"])
            
            # Configuração das colunas
            column_config = {
                "ProdutoQuimico": st.column_config.SelectboxColumn(
                    "Produto Químico",
                    options=sorted(dados["quimicos"]["Nome"].unique()),
                    required=True,
                    help="Selecione o produto químico para testar compatibilidade"
                ),
                "ProdutoBiologico": st.column_config.SelectboxColumn(
                    "Produto Biológico",
                    options=sorted(dados["biologicos"]["Nome"].unique()),
                    required=True,
                    help="Selecione o produto biológico para testar compatibilidade"
                ),
                "Compatibilidade": st.column_config.SelectboxColumn(
                    "Compatibilidade",
                    options=["Compatível", "Incompatível", "Não testado"],
                    required=True,
                    help="Indique o resultado do teste de compatibilidade"
                ),
                "Observacoes": st.column_config.TextColumn(
                    "Observações",
                    help="Adicione notas sobre o teste, condições especiais ou restrições"
                )
            }
            
            # Tabela editável com nova função helper
            edited_df = create_data_editor(
                df_filtrado,
                "resultados",
                column_config,
                height=400
            )
            
            # Atualizar estado quando houver mudanças
            if edited_df is not None:
                st.session_state.edited_data["resultados"] = True
            
            # Botão para salvar alterações
            col_btn = st.container()
            with col_btn:
                if st.button("Salvar Alterações", key="save_resultados", use_container_width=True):
                    with st.spinner("Salvando dados..."):
                        try:
                            df_completo = st.session_state.local_data["resultados"].copy()
                            
                            if filtro_quimico != "Todos" or filtro_biologico != "Todos":
                                mask = (
                                    (df_completo["ProdutoQuimico"].isin(edited_df["ProdutoQuimico"])) &
                                    (df_completo["ProdutoBiologico"].isin(edited_df["ProdutoBiologico"]))
                                )
                            else:
                                mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                            
                            df_completo = df_completo[~mask]
                            df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                            df_final = df_final.drop_duplicates(
                                subset=["ProdutoQuimico", "ProdutoBiologico"],
                                keep="last"
                            )
                            df_final = df_final.sort_values(by=["ProdutoQuimico", "ProdutoBiologico"]).reset_index(drop=True)
                            
                            if save_data(df_final, "Resultados", "resultados"):
                                st.success("Dados salvos com sucesso!")
                        except Exception as e:
                            st.error(f"Erro: {str(e)}")
            
            # Mostrar estatísticas de compatibilidade
            with st.expander("📊 Estatísticas de Compatibilidade"):
                stats_df = dados["resultados"].copy()
                total = len(stats_df)
                compativeis = len(stats_df[stats_df["Compatibilidade"] == "Compatível"])
                incompativeis = len(stats_df[stats_df["Compatibilidade"] == "Incompatível"])
                nao_testados = len(stats_df[stats_df["Compatibilidade"] == "Não testado"])
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Compatíveis", f"{compativeis} ({(compativeis/total*100):.1f}%)")
                with col2:
                    st.metric("Incompatíveis", f"{incompativeis} ({(incompativeis/total*100):.1f}%)")
                with col3:
                    st.metric("Não Testados", f"{nao_testados} ({(nao_testados/total*100):.1f}%)")
    elif tab4:
        st.session_state.active_tab = 3
        st.subheader("Solicitações de Teste")
        if "solicitacoes" not in dados or dados["solicitacoes"].empty:
            st.error("Erro ao carregar dados das solicitações!")
        else:
            # Filtros para a tabela
            col1, col2 = st.columns(2)
            with col1:
                filtro_status = st.selectbox(
                    "🔍 Filtrar por Status",
                    options=["Todos", "Pendente", "Em análise", "Concluído"],
                    index=0,
                    key="filtro_status_solicitacoes"
                )
            with col2:
                filtro_solicitante = st.selectbox(
                    "🔍 Filtrar por Solicitante",
                    options=["Todos"] + sorted(dados["solicitacoes"]['Solicitante'].unique().tolist()),
                    index=0,
                    key="filtro_solicitante_solicitacoes"
                )

            # Aplicar filtros
            df_filtrado = dados["solicitacoes"].copy()
            if filtro_status != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]
            if filtro_solicitante != "Todos":
                df_filtrado = df_filtrado[df_filtrado["Solicitante"] == filtro_solicitante]
            
            # Garantir colunas esperadas
            df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]].copy()
            
            if df_filtrado.empty:
                df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
            
            # Tabela editável
            edited_df = st.data_editor(
                df_filtrado,
                num_rows="dynamic",
                hide_index=True,
                key=f"solicitacoes_editor_{filtro_status}_{filtro_solicitante}_{int(time.time())}",
                column_config={
                    "DataSolicitacao": st.column_config.DateColumn(
                        "Data da Solicitação",
                        format="DD/MM/YYYY",
                        required=True
                    ),
                    "Solicitante": st.column_config.TextColumn("Solicitante", required=True),
                    "ProdutoQuimico": st.column_config.SelectboxColumn(
                        "Produto Químico",
                        options=sorted(dados["quimicos"]["Nome"].unique()),
                        required=True
                    ),
                    "ProdutoBiologico": st.column_config.SelectboxColumn(
                        "Produto Biológico",
                        options=sorted(dados["biologicos"]["Nome"].unique()),
                        required=True
                    ),
                    "Status": st.column_config.SelectboxColumn(
                        "Status",
                        options=["Pendente", "Em análise", "Concluído"],
                        required=True
                    ),
                    "Observacoes": "Observações"
                },
                use_container_width=True,
                height=400,
                on_change=lambda: st.session_state.edited_data.update({"solicitacoes": True}),
                disabled=False,
                column_order=COLUNAS_ESPERADAS["Solicitacoes"]
            )
            
            # Botão para salvar alterações
            col_btn = st.container()
            with col_btn:
                if st.button("Salvar Alterações", key="save_solicitacoes", use_container_width=True):
                    with st.spinner("Salvando dados..."):
                        try:
                            df_completo = st.session_state.local_data["solicitacoes"].copy()
                            
                            if filtro_status != "Todos" or filtro_solicitante != "Todos":
                                mask = (
                                    (df_completo["Status"] == filtro_status if filtro_status != "Todos" else True) &
                                    (df_completo["Solicitante"] == filtro_solicitante if filtro_solicitante != "Todos" else True)
                                )
                            else:
                                mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                            
                            df_completo = df_completo[~mask]
                            df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                            df_final = df_final.sort_values(by=["DataSolicitacao", "Solicitante"]).reset_index(drop=True)
                            
                            if save_data(df_final, "Solicitacoes", "solicitacoes"):
                                st.success("Dados salvos com sucesso!")
                        except Exception as e:
                                st.error(f"Erro ao salvar dados: {str(e)}")

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