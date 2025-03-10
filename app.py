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

if 'local_data' not in st.session_state:
    st.session_state.local_data = {
        "quimicos": pd.DataFrame(),
        "biologicos": pd.DataFrame(),
        "resultados": pd.DataFrame(),
        "solicitacoes": pd.DataFrame()
    }

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
            [data-testid="stDataFrame"], [data-testid="stTable"], [data-testid="stDataEditor"] {
                width: 100% !important;
                min-height: 400px;
                height: auto !important;
                max-height: none !important;
                transform: none !important;
                transition: none !important;
            }
            /* Reduzir espaço entre tabelas e botões */
            .stButton {
                margin-top: 0px;
            }
            /* Corrigir problemas de renderização em tabelas editáveis */
            [data-testid="stDataEditor"] [data-testid="column"] {
                overflow: visible !important;
            }
            [data-testid="stDataEditor"] [data-testid="dataframe-cell-input"] {
                min-height: 32px !important;
            }
            [data-testid="stDataEditor"] [data-testid="dataframe-add-rows"] {
                margin-top: 8px !important;
            }
            /* Otimizações de performance */
            .stApp {
                background-color: #ffff;
            }
            /* Reduzir animações para melhorar performance */
            * {
                transition-duration: 0s !important;
                animation-duration: 0s !important;
            }
            /* Melhorar performance de tabelas grandes */
            .stDataFrame {
                max-height: 600px;
                overflow-y: auto;
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
            sheet = get_worksheet(sheet_name)
            if not sheet:
                st.error(f"Planilha '{sheet_name}' não encontrada.")
                return False
            
            # Verificar se há dados para adicionar
            if not data_dict:
                st.error("Nenhum dado para adicionar.")
                return False
            
            # Adicionar os dados à planilha
            sheet.append_row(list(data_dict.values()))
            return True
            
        except Exception as e:
            st.error(f"Erro ao adicionar dados: {str(e)}")
            return False
            
    return retry_with_backoff(_append, max_retries=3, initial_delay=2)

def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    def _load(sheet_name=sheet_name):
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
    """
    Atualiza uma planilha no Google Sheets e também atualiza o cache local
    """
    try:
        worksheet = get_worksheet(sheet_name)
        if worksheet is None:
            st.error(f"Não foi possível acessar a planilha {sheet_name}")
            return False
            
        # Verificar se o DataFrame está vazio
        if df.empty:
            st.error(f"DataFrame vazio para {sheet_name}")
            return False
            
        # Converter colunas datetime para string
        df_copy = df.copy()
        for col in df_copy.columns:
            if df_copy[col].dtype == 'datetime64[ns]':
                df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d')
                
        # Preparar dados para atualização
        header = df_copy.columns.tolist()
        values = df_copy.values.tolist()
        all_values = [header] + values
        
        # Usar batch_update para melhorar a performance
        worksheet.clear()
        # Corrigir o erro de atualização especificando a célula inicial 'A1'
        worksheet.update('A1', all_values)
        
        # Atualizar o cache local
        st.session_state.local_data[sheet_name.lower()] = df
        
        return True
    except Exception as e:
        st.error(f"Erro ao atualizar planilha {sheet_name}: {str(e)}")
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
    if 'solicitar_novo_teste' in st.session_state and st.session_state.solicitar_novo_teste:
        st.session_state.solicitar_novo_teste = False
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
            # Mostrar aviso de que não existe compatibilidade cadastrada
            st.warning(f"""
                **Teste não realizado!**
                
                Solicite um novo teste.
            """)
            
    # Função auxiliar para mostrar o formulário de solicitação
def mostrar_formulario_solicitacao(quimico=None, biologico=None):
    # Inicializar variáveis de estado se não existirem
    if 'form_submitted' not in st.session_state:
        st.session_state.form_submitted = False
    if 'form_success' not in st.session_state:
        st.session_state.form_success = False
    if 'last_submission' not in st.session_state:
        st.session_state.last_submission = None
    if 'just_submitted' not in st.session_state:
        st.session_state.just_submitted = False
    
    # Função para processar o envio do formulário
    def submit_form():
        # Obter valores do formulário
        data = st.session_state.data_solicitacao
        solicitante = st.session_state.solicitante
        quimico_input = st.session_state.quimico_input
        biologico_input = st.session_state.biologico_input
        observacoes = st.session_state.observacoes
        
        # Validar campos obrigatórios
        if not quimico_input or not biologico_input or not solicitante:
            st.session_state.form_submitted = True
            st.session_state.form_success = False
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
        
        # Tentar salvar no Google Sheets
        if append_to_sheet(nova_solicitacao, "Solicitacoes"):
            st.session_state.last_submission = nova_solicitacao
            st.session_state.just_submitted = True  # Ativa flag
            return
        else:
            st.session_state.form_submitted = True
            st.session_state.form_success = False
    
    # Mostrar o formulário para entrada de dados
    st.subheader("Solicitar Novo Teste")
    
    # Valores iniciais para os campos
    default_quimico = quimico if quimico else ""
    default_biologico = biologico if biologico else ""
    
    # Usar st.form para evitar recarregamentos
    with st.form(key="solicitar_teste_form"):
        st.date_input("Data da Solicitação", value=datetime.now(), key="data_solicitacao")
        st.text_input("Nome do solicitante", key="solicitante")
        
        # Usar campos de texto para permitir novos produtos
        st.text_input("Nome do Produto Químico", value=default_quimico, key="quimico_input")
        st.text_input("Nome do Produto Biológico", value=default_biologico, key="biologico_input")
        
        st.text_area("Observações", key="observacoes")
        
        # Botão de submit
        submitted = st.form_submit_button("Solicitar Teste", on_click=submit_form)
    
    # Exibir mensagem de sucesso se acabou de enviar uma solicitação
    if st.session_state.just_submitted and st.session_state.last_submission:
        success_container = st.container()
        with success_container:
            st.success("Solicitação de novo teste registrada com sucesso!")
        
        # Mostrar detalhes da última submissão
        with st.expander("Ver detalhes da solicitação"):
            for key, value in st.session_state.last_submission.items():
                st.write(f"**{key}:** {value}")
        
        # Limpar o estado após exibir a mensagem
        if st.button("Fechar", key="btn_fechar_mensagem_sucesso"):
            st.session_state.just_submitted = False
            st.session_state.last_submission = None
            st.experimental_rerun()
    else:
        st.error("Por favor, preencha todos os campos obrigatórios: Produto Químico, Produto Biológico e Solicitante.")

########################################## GERENCIAMENTO ##########################################

def gerenciamento():
    st.title("⚙️ Gerenciamento")

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
                # Inicializar variáveis de estado se não existirem
                if 'quimico_form_submitted' not in st.session_state:
                    st.session_state.quimico_form_submitted = False
                if 'quimico_form_success' not in st.session_state:
                    st.session_state.quimico_form_success = False
                if 'quimico_form_error' not in st.session_state:
                    st.session_state.quimico_form_error = ""
                if 'quimico_just_submitted' not in st.session_state:
                    st.session_state.quimico_just_submitted = False
                
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
                                st.session_state.local_data["quimicos"] = pd.concat([st.session_state.local_data["quimicos"], nova_linha], ignore_index=True)
                                
                                st.session_state.quimico_form_submitted = True
                                st.session_state.quimico_form_success = True
                                st.session_state.quimico_form_error = ""
                                st.session_state.quimico_just_submitted = True
                                # Garantir que permanecemos na página atual
                                st.session_state.current_page = "Gerenciamento"
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
                        # Usar um container para destacar a mensagem de sucesso
                        success_container = st.container()
                        with success_container:
                            st.markdown("---")
                            st.success("### Produto adicionado com sucesso! ✅")
                            st.markdown("---")
                        
                        # Botão para limpar o formulário e adicionar outro produto
                        if st.button("Adicionar outro produto", key="btn_add_outro_quimico"):
                            st.session_state.quimico_form_submitted = False
                            st.session_state.quimico_form_success = False
                            st.session_state.quimico_just_submitted = False
                            st.experimental_rerun()
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
                    # Adicionar uma linha vazia para facilitar a adição de novos dados
                    df_filtrado = df_vazio
                
                # Definir função para marcar dados como editados
                def marcar_como_editado(tabela):
                    st.session_state.edited_data[tabela] = True
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key=f"quimicos_editor_{filtro_nome}_{filtro_tipo}",
                    hide_index=True,
                    on_change=lambda: st.session_state.edited_data.update({"quimicos": True}),
                    disabled=["Nome"] if not df_filtrado.empty else [],
                    column_config={
                        "Nome": st.column_config.TextColumn("Nome do Produto", required=True),
                        "Tipo": st.column_config.SelectboxColumn(options=["Herbicida", "Fungicida", "Inseticida"]),
                        "Fabricante": "Fabricante",
                        "Concentracao": "Concentração",
                        "Classe": "Classe",
                        "ModoAcao": "Modo de Ação"
                    },
                    use_container_width=True,
                    height=400
                )
                
                # Botão para salvar alterações
                col_btn = st.container()
                with col_btn:
                    if st.button("Salvar Alterações", key="save_quimicos", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                # Verificar se é um DataFrame
                                if not isinstance(edited_df, pd.DataFrame):
                                    st.error("Erro: Os dados editados não são um DataFrame válido")
                                    st.stop()
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Quimicos"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Remover linhas vazias
                                edited_df = edited_df.dropna(subset=["Nome"], how="all").reset_index(drop=True)
                                
                                # Verificar se há dados para salvar
                                if edited_df.empty:
                                    st.warning("Não há dados para salvar")
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
                # Inicializar variáveis de estado se não existirem
                if 'biologico_form_submitted' not in st.session_state:
                    st.session_state.biologico_form_submitted = False
                if 'biologico_form_success' not in st.session_state:
                    st.session_state.biologico_form_success = False
                if 'biologico_form_error' not in st.session_state:
                    st.session_state.biologico_form_error = ""
                
                # Função para processar o envio do formulário
                def submit_biologico_form():
                    nome = st.session_state.biologico_nome
                    tipo = st.session_state.tipo_biologico
                    ingrediente_ativo = st.session_state.biologico_ingrediente
                    formulacao = st.session_state.biologico_formulacao
                    aplicacao = st.session_state.biologico_aplicacao
                    validade = st.session_state.biologico_validade
                    
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
                            st.session_state.biologico_form_submitted = True
                            st.session_state.biologico_form_success = False
                            st.session_state.biologico_form_error = f"Produto '{nome}' já existe!"
                        else:
                            # Adicionar à planilha
                            if append_to_sheet(novo_produto, "Biologicos"):
                                # Atualizar dados locais
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
                        st.selectbox("Tipo", options=["Bioestimulante", "Controle Biológico"], key="tipo_biologico")
                        st.text_input("Ingrediente Ativo", key="biologico_ingrediente")
                    with col2:
                        st.text_input("Formulação", key="biologico_formulacao")
                        st.text_input("Aplicação", key="biologico_aplicacao")
                        st.text_input("Validade", key="biologico_validade")
                    
                    submitted = st.form_submit_button("Adicionar Produto", on_click=submit_biologico_form)
                
                # Mostrar mensagens de sucesso ou erro abaixo do formulário
                if st.session_state.biologico_form_submitted:
                    if st.session_state.biologico_form_success:
                        # Usar um container para destacar a mensagem de sucesso
                        success_container = st.container()
                        with success_container:
                            st.markdown("---")
                            st.success("### Produto biológico adicionado com sucesso! ✅")
                            st.markdown("---")
                    else:
                        st.error(st.session_state.biologico_form_error)
            
            else:  # Visualizar produtos cadastrados
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_nome = st.selectbox(
                        "🔍 Filtrar por Nome",
                        options=["Todos"] + sorted(dados["biologicos"]['Nome'].unique().tolist()),
                        index=0,
                        key="filtro_nome_biologicos"
                    )
                with col2:
                    filtro_tipo = st.selectbox(
                        "🔍 Filtrar por Tipo",
                        options=["Todos", "Bioestimulante", "Controle Biológico"],
                        index=0,
                        key="filtro_tipo_biologicos"
                    )

                # Aplicar filtro
                df_filtrado = dados["biologicos"].copy()
                if filtro_nome != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
                if filtro_tipo != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Tipo"] == filtro_tipo]
                
                # Garantir que apenas as colunas esperadas estejam presentes
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Biologicos"]].copy()
                
                # Garantir que o DataFrame tenha pelo menos uma linha vazia para adição
                if df_filtrado.empty:
                    df_vazio = pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"])
                    # Adicionar uma linha vazia para facilitar a adição de novos dados
                    df_filtrado = df_vazio
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key=f"biologicos_editor_{filtro_nome}_{filtro_tipo}",
                    hide_index=True,
                    on_change=lambda: st.session_state.edited_data.update({"biologicos": True}),
                    column_config={
                        "Nome": "Produto Biológico",
                        "Tipo": st.column_config.SelectboxColumn(options=["Bioestimulante", "Controle Biológico"]),
                        "IngredienteAtivo": "Ingrediente Ativo",
                        "Formulacao": "Formulação",
                        "Aplicacao": "Aplicação",
                        "Validade": "Validade"
                    },
                    use_container_width=True,
                    height=400
                )
                
                # Botão para salvar alterações
                col_btn = st.container()
                with col_btn:
                    if st.button("Salvar Alterações", key="save_biologicos", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                # Verificar se é um DataFrame
                                if not isinstance(edited_df, pd.DataFrame):
                                    st.error("Erro: Os dados editados não são um DataFrame válido")
                                    st.stop()
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Biologicos"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Remover linhas vazias
                                edited_df = edited_df.dropna(subset=["Nome"], how="all").reset_index(drop=True)
                                
                                # Verificar se há dados para salvar
                                if edited_df.empty:
                                    st.warning("Não há dados para salvar")
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
                # Inicializar variáveis de estado se não existirem
                if 'compatibilidade_form_submitted' not in st.session_state:
                    st.session_state.compatibilidade_form_submitted = False
                if 'compatibilidade_form_success' not in st.session_state:
                    st.session_state.compatibilidade_form_success = False
                if 'compatibilidade_form_error' not in st.session_state:
                    st.session_state.compatibilidade_form_error = ""
                
                # Função para processar o envio do formulário
                def submit_compatibilidade_form():
                    quimico = st.session_state.resultado_quimico
                    biologico = st.session_state.resultado_biologico
                    data_teste = st.session_state.resultado_data
                    duracao = st.session_state.resultado_duracao
                    tipo = st.session_state.resultado_tipo
                    resultado = st.session_state.resultado_status
                    
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
                            st.session_state.compatibilidade_form_submitted = True
                            st.session_state.compatibilidade_form_success = False
                            st.session_state.compatibilidade_form_error = f"Combinação {quimico} e {biologico} já existe!"
                        else:
                            # Adicionar à planilha
                            if append_to_sheet(nova_compatibilidade, "Resultados"):
                                # Atualizar dados locais
                                nova_linha = pd.DataFrame([nova_compatibilidade])
                                st.session_state.local_data["resultados"] = pd.concat([st.session_state.local_data["resultados"], nova_linha], ignore_index=True)
                                
                                st.session_state.compatibilidade_form_submitted = True
                                st.session_state.compatibilidade_form_success = True
                                st.session_state.compatibilidade_form_error = ""
                                # Garantir que permanecemos na página atual
                                st.session_state.current_page = "Gerenciamento"
                            else:
                                st.session_state.compatibilidade_form_submitted = True
                                st.session_state.compatibilidade_form_success = False
                                st.session_state.compatibilidade_form_error = "Falha ao adicionar compatibilidade"
                    else:
                        st.session_state.compatibilidade_form_submitted = True
                        st.session_state.compatibilidade_form_success = False
                        st.session_state.compatibilidade_form_error = "Selecione os produtos químico e biológico"
                
                with st.form("nova_compatibilidade_form"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.selectbox(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]["Nome"].unique().tolist()),
                            key="resultado_quimico"
                        )
                        st.date_input("Data do Teste", key="resultado_data")
                        st.selectbox("Tipo de Teste", options=["Simples", "Composto"], key="resultado_tipo")
                    with col_b:
                        st.selectbox(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]["Nome"].unique().tolist()),
                            key="resultado_biologico"
                        )
                        st.number_input("Duração (horas)", min_value=0, value=0, key="resultado_duracao")
                        st.selectbox("Resultado", options=["Compatível", "Incompatível"], key="resultado_status")
                    
                    submitted = st.form_submit_button("Adicionar Compatibilidade", on_click=submit_compatibilidade_form)
                
                # Mostrar mensagens de sucesso ou erro abaixo do formulário
                if st.session_state.compatibilidade_form_submitted:
                    if st.session_state.compatibilidade_form_success:
                        st.success("Compatibilidade adicionada com sucesso!")
                    else:
                        st.error(st.session_state.compatibilidade_form_error)
            
            else:  # Visualizar compatibilidades cadastradas
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_quimico = st.selectbox(
                        "🔍 Filtrar por Produto Químico",
                        options=["Todos"] + sorted(dados["resultados"]["Quimico"].unique().tolist()),
                        index=0,
                        key="filtro_quimico_resultados"
                    )
                with col2:
                    filtro_biologico = st.selectbox(
                        "🔍 Filtrar por Produto Biológico",
                        options=["Todos"] + sorted(dados["resultados"]["Biologico"].unique().tolist()),
                        index=0,
                        key="filtro_biologico_resultados"
                    )
                
                # Aplicar filtros
                df_filtrado = dados["resultados"].copy()
                if filtro_quimico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
                if filtro_biologico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
                
                # Garantir que apenas as colunas esperadas estejam presentes
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Resultados"]].copy()
                
                # Garantir que o DataFrame tenha pelo menos uma linha vazia para adição
                if df_filtrado.empty:
                    df_vazio = pd.DataFrame(columns=COLUNAS_ESPERADAS["Resultados"])
                    # Adicionar uma linha vazia para facilitar a adição de novos dados
                    df_filtrado = df_vazio
                
                # Garantir que a coluna Data seja do tipo correto
                if 'Data' in df_filtrado.columns:
                    # Converter para string para evitar problemas de compatibilidade
                    df_filtrado['Data'] = df_filtrado['Data'].astype(str)
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key=f"resultados_editor_{filtro_quimico}_{filtro_biologico}",
                    hide_index=True,
                    on_change=lambda: st.session_state.edited_data.update({"resultados": True}),
                    column_config={
                        "Data": st.column_config.TextColumn(
                            "Data do Teste",
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
                            options=["Compatível", "Incompatível"],
                            required=True
                        )
                    },
                    use_container_width=True,
                    height=400
                )
                
                # Botão para salvar alterações
                col_btn = st.container()
                with col_btn:
                    if st.button("Salvar Alterações", key="save_resultados", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                # Verificar se é um DataFrame
                                if not isinstance(edited_df, pd.DataFrame):
                                    st.error("Erro: Os dados editados não são um DataFrame válido")
                                    st.stop()
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Resultados"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Remover linhas vazias
                                edited_df = edited_df.dropna(subset=["Quimico", "Biologico"], how="all").reset_index(drop=True)
                                
                                # Verificar se há dados para salvar
                                if edited_df.empty:
                                    st.warning("Não há dados para salvar")
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
            opcao = st.radio("Escolha uma opção:", ["Nova solicitação", "Solicitações cadastradas"], key="opcao_solicitacoes")
            
            if opcao == "Nova solicitação":
                # Inicializar variáveis de estado se não existirem
                if 'gerenciamento_form_submitted' not in st.session_state:
                    st.session_state.gerenciamento_form_submitted = False
                
                # Se o formulário foi enviado com sucesso, mostrar mensagem e detalhes
                if st.session_state.gerenciamento_form_submitted and 'gerenciamento_last_submission' in st.session_state:
                    st.success("Solicitação adicionada com sucesso!")
                    
                    # Mostrar detalhes da solicitação
                    st.info("**Detalhes da solicitação:**")
                    st.write(f"**Data:** {st.session_state.gerenciamento_last_submission.get('Data', '')}")
                    st.write(f"**Solicitante:** {st.session_state.gerenciamento_last_submission.get('Solicitante', '')}")
                    st.write(f"**Produto Químico:** {st.session_state.gerenciamento_last_submission.get('Quimico', '')}")
                    st.write(f"**Produto Biológico:** {st.session_state.gerenciamento_last_submission.get('Biologico', '')}")
                    
                    if st.button("Fazer nova solicitação", key="btn_nova_solicitacao_gerenciamento"):
                        st.session_state.gerenciamento_form_submitted = False
                        if 'gerenciamento_last_submission' in st.session_state:
                            del st.session_state.gerenciamento_last_submission
                    return
                
                # Função para processar o envio do formulário
                def submit_gerenciamento_form():
                    # Obter valores do formulário
                    data = st.session_state.gerenciamento_data
                    solicitante = st.session_state.gerenciamento_solicitante
                    quimico = st.session_state.gerenciamento_quimico
                    biologico = st.session_state.gerenciamento_biologico
                    observacoes = st.session_state.gerenciamento_observacoes
                    
                    # Validar campos obrigatórios
                    if not solicitante or not quimico or not biologico:
                        st.warning("Preencha todos os campos obrigatórios")
                        return
                    
                    # Preparar dados da solicitação
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
                            # Atualizar dados locais
                            nova_linha = pd.DataFrame([nova_solicitacao])
                            st.session_state.local_data["solicitacoes"] = pd.concat([st.session_state.local_data["solicitacoes"], nova_linha], ignore_index=True)
                            
                            # Salvar a última submissão para exibir detalhes
                            st.session_state.gerenciamento_last_submission = nova_solicitacao
                            # Marcar como enviado com sucesso
                            st.session_state.gerenciamento_form_submitted = True
                            # Garantir que permanecemos na página atual
                            st.session_state.current_page = "Gerenciamento"
                        else:
                            st.error("Falha ao adicionar solicitação")
                            return False
                
                # Mostrar o formulário para entrada de dados
                st.subheader("Nova Solicitação de Teste")
                
                # Usar st.form para evitar recarregamentos
                with st.form(key="gerenciamento_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("Nome do solicitante", key="gerenciamento_solicitante")
                        st.text_input("Produto Químico", key="gerenciamento_quimico")
                    with col2:
                        st.date_input("Data da Solicitação", value=datetime.now(), key="gerenciamento_data")
                        st.text_input("Produto Biológico", key="gerenciamento_biologico")
                    
                    st.text_area("Observações", key="gerenciamento_observacoes")
                    
                    # Botão de submit
                    submitted = st.form_submit_button("Adicionar Solicitação", on_click=submit_gerenciamento_form)
            
            else:  # Solicitações cadastradas
                # Filtros para a tabela
                col1, col2, col3 = st.columns(3)
                with col1:
                    filtro_status = st.selectbox(
                        "🔍 Filtrar por Status",
                        options=["Todos", "Pendente", "Em andamento", "Concluído", "Cancelado"],
                        index=0,
                        key="filtro_status_solicitacoes"
                    )
                with col2:
                    filtro_quimico = st.selectbox(
                        "🔍 Filtrar por Produto Químico",
                        options=["Todos"] + sorted(dados["solicitacoes"]["Quimico"].unique().tolist()),
                        index=0,
                        key="filtro_quimico_solicitacoes"
                    )
                with col3:
                    filtro_biologico = st.selectbox(
                        "🔍 Filtrar por Produto Biológico",
                        options=["Todos"] + sorted(dados["solicitacoes"]["Biologico"].unique().tolist()),
                        index=0,
                        key="filtro_biologico_solicitacoes"
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
                
                # Garantir que apenas as colunas esperadas estejam presentes
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]].copy()
                
                # Garantir que o DataFrame tenha pelo menos uma linha vazia para adição
                if df_filtrado.empty:
                    df_vazio = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
                    # Adicionar uma linha vazia para facilitar a adição de novos dados
                    df_filtrado = df_vazio
                
                # Garantir que a coluna Data seja do tipo correto
                if 'Data' in df_filtrado.columns:
                    # Converter para string para evitar problemas de compatibilidade
                    df_filtrado['Data'] = df_filtrado['Data'].astype(str)
                
                # Tabela editável com ordenação por Data
                if not df_filtrado.empty:
                    df_filtrado = df_filtrado.sort_values(by="Data", ascending=False).reset_index(drop=True)
                
                edited_df = st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key=f"solicitacoes_editor_{filtro_status}_{filtro_quimico}_{filtro_biologico}",
                    hide_index=True,
                    on_change=lambda: st.session_state.edited_data.update({"solicitacoes": True}),
                    column_config={
                        "Data": st.column_config.TextColumn("Data da Solicitação"),
                        "Solicitante": "Solicitante",
                        "Quimico": st.column_config.SelectboxColumn(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]["Nome"].unique().tolist())
                        ),
                        "Biologico": st.column_config.SelectboxColumn(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]["Nome"].unique().tolist())
                        ),
                        "Observacoes": "Observações",
                        "Status": st.column_config.SelectboxColumn(
                            "Status",
                            options=["Pendente", "Em Análise", "Concluído", "Cancelado"]
                        )
                    },
                    use_container_width=True,
                    height=400
                )
                
                # Botão para salvar alterações
                col_btn = st.container()
                with col_btn:
                    if st.button("Salvar Alterações", key="save_solicitacoes", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                # Verificar se é um DataFrame
                                if not isinstance(edited_df, pd.DataFrame):
                                    st.error("Erro: Os dados editados não são um DataFrame válido")
                                    st.stop()
                                
                                # Garantir que todas as colunas necessárias estejam presentes
                                for col in COLUNAS_ESPERADAS["Solicitacoes"]:
                                    if col not in edited_df.columns:
                                        st.error(f"Coluna obrigatória '{col}' não encontrada nos dados editados")
                                        st.stop()
                                
                                # Remover linhas vazias
                                edited_df = edited_df.dropna(subset=["Solicitante"], how="all").reset_index(drop=True)
                                
                                # Verificar se há dados para salvar
                                if edited_df.empty:
                                    st.warning("Não há dados para salvar")
                                    st.stop()
                                
                                # Atualizar dados na sessão
                                st.session_state.local_data["solicitacoes"] = edited_df
                                
                                # Depois enviar para o Google Sheets
                                if update_sheet(edited_df, "Solicitacoes"):
                                    st.session_state.edited_data["solicitacoes"] = False
                                    st.success("Dados salvos com sucesso!")
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {str(e)}")

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