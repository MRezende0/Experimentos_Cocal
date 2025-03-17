import os
import ssl
import time
from datetime import datetime, timedelta
from random import uniform

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
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
    "Compatibilidades": "0",
    "Biologicos": "1440941690",
    "Quimicos": "885876195",
    "Solicitacoes": "1408097520"
}

COLUNAS_ESPERADAS = {
    "Biologicos": ["Nome", "Classe", "IngredienteAtivo", "Formulacao", "Dose", "Concentracao", "Fabricante"],
    "Quimicos": ["Nome", "Classe", "Fabricante", "Dose"],
    "Compatibilidades": ["Data", "Quimico", "Biologico", "Tempo", "Resultado"],
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
                "Biologicos": ["Nome", "Classe"],
                "Quimicos": ["Nome", "Classe"],
                "Compatibilidades": ["Quimico", "Biologico"],
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
            futures = {executor.submit(load_sheet, name): name for name in ["Quimicos", "Biologicos", "Compatibilidades", "Solicitacoes"]}
            
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
        if sheet_name in ["Biologicos", "Quimicos"] and "Nome" not in df.columns:
            st.error(f"Coluna 'Nome' não encontrada em {sheet_name}")
            return pd.DataFrame()
            
        # Remover linhas com Nome vazio para planilhas que exigem Nome
        if sheet_name in ["Biologicos", "Quimicos"] and "Nome" in df.columns:
            df = df[df["Nome"].notna()]
        
        # Converter colunas de data
        if sheet_name in ["Compatibilidades", "Solicitacoes"] and "Data" in df.columns:
            df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
        
        return df
        
    except Exception as e:
        st.error(f"Falha crítica ao carregar {sheet_name}: {str(e)}")
        return pd.DataFrame()

def convert_scientific_to_float(value):
    """Converte notação científica em string para float"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        # Remove espaços e substitui vírgula por ponto
        value = str(value).replace(' ', '').replace(',', '.')
        # Trata notação com 'E' ou 'e'
        if 'e' in value.lower():
            return float(value)
        # Trata notação com ×10^
        if '×10^' in value:
            base, exponent = value.split('×10^')
            return float(base) * (10 ** float(exponent))
        return float(value)
    except:
        return 0.0

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
        biologico = st.selectbox(
            "Produto Biológico",
            options=sorted(dados["biologicos"]['Nome'].unique()) if not dados["biologicos"].empty and 'Nome' in dados["biologicos"].columns else [],
            index=None,
            key="compatibilidade_biologico"
        )

    with col2:
        quimico = st.selectbox(
            "Produto Químico",
            options=sorted(dados["quimicos"]['Nome'].unique()) if not dados["quimicos"].empty and 'Nome' in dados["quimicos"].columns else [],
            index=None,
            key="compatibilidade_quimico"
        )
    
    if quimico and biologico:
        # Procurar na planilha de Resultados usando os nomes
        resultado_existente = dados["compatibilidades"][
            (dados["compatibilidades"]["Quimico"] == quimico) & 
            (dados["compatibilidades"]["Biologico"] == biologico)
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
                st.write(f"**Tempo:** {resultado_existente.iloc[0]['Tempo']} horas")
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
            "Biologico": biologico_input,
            "Quimico": quimico_input,
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
            st.text_input("Nome do Produto Biológico", value=default_biologico, key="biologico_input")
            st.text_input("Nome do solicitante", key="solicitante")
        
        with col2:
            st.text_input("Nome do Produto Químico", value=default_quimico, key="quimico_input")
            st.date_input("Data da Solicitação", value=datetime.now(), key="data_solicitacao", format="DD/MM/YYYY")
            
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

    # Inicializar dados locais
    if 'local_data' not in st.session_state:
        st.session_state.local_data = load_all_data()
    
    if 'edited_data' not in st.session_state:
        st.session_state.edited_data = {
            "biologicos": False,
            "quimicos": False,
            "resultados": False,
            "solicitacoes": False
        }
    
    # Usar dados da sessão em vez de recarregar a cada interação
    dados = st.session_state.local_data
    
    aba_selecionada = st.radio(
        "Selecione a aba:",
        ["Biologicos", "Quimicos", "Compatibilidades", "Solicitações"],
        key="management_tabs",
        horizontal=True,
        label_visibility="collapsed"
    )
    st.session_state.current_management_tab = aba_selecionada

    # Conteúdo da tab Biologicos
    if aba_selecionada == "Biologicos":
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
                    classe = st.session_state.classe_biologico
                    ingrediente_ativo = st.session_state.biologico_ingrediente
                    formulacao = st.session_state.biologico_formulacao
                    fabricante = st.session_state.biologico_fabricante
                    dose = st.session_state.biologico_dose
                    concentracao = st.session_state.biologico_concentracao
                    
                    if nome:
                        novo_produto = {
                            "Nome": nome,
                            "Classe": classe,
                            "IngredienteAtivo": ingrediente_ativo,
                            "Formulacao": formulacao,
                            "Dose": dose,
                            "Concentracao": concentracao,
                            "Fabricante": fabricante
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
                        st.selectbox("Classe", options=["Bioestimulante", "Biofungicida", "Bionematicida", "Bioinseticida", "Inoculante"], key="classe_biologico")
                        st.text_input("Ingrediente Ativo", key="biologico_ingrediente")
                    with col2:
                        st.selectbox("Formulação", options=["Suspensão concentrada", "Formulação em óleo", "Pó molhável", "Formulação em pó", "Granulado dispersível"], key="biologico_formulacao")
                        st.number_input("Dose (kg/ha ou litro/ha)", value=0.0, step=1.0, key="biologico_dose")
                        st.text_input("Concentração em bula (UFC/g ou UFC/ml)", help="Digite em notação científica (ex: 1e9)", required=True, value="", key="biologico_concentracao")
                    st.text_input("Fabricante", key="biologico_fabricante")
                    
                    submitted = st.form_submit_button("Adicionar Produto", on_click=submit_biologico_form)
                
                # Mostrar mensagens de sucesso ou erro abaixo do formulário
                if st.session_state.biologico_form_submitted:
                    if st.session_state.biologico_form_success:
                        st.success(f"Produto {st.session_state.biologico_nome} adicionado com sucesso!")
                        st.session_state.biologico_form_submitted = False
                        st.session_state.biologico_form_success = False
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
                    filtro_classe = st.selectbox(
                        "🔍 Filtrar por Classe",
                        options=["Todos", "Bioestimulante", "Biofungicida", "Bionematicida", "Bioinseticida", "Inoculante"],
                        index=0,
                        key="filtro_classe_biologicos"
                    )

                # Aplicar filtro
                df_filtrado = dados["biologicos"].copy()
                if filtro_nome != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
                if filtro_classe != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Classe"] == filtro_classe]
                
                # Garantir colunas esperadas
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Biologicos"]].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"])
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    hide_index=True,
                    num_rows="dynamic",
                    key="biologicos_editor",
                    column_config={
                        "Nome": st.column_config.TextColumn("Produto Biológico", required=True),
                        "Classe": st.column_config.SelectboxColumn("Classe", options=["Bioestimulante", "Biofungicida", "Bionematicida", "Bioinseticida", "Inoculante"]),
                        "IngredienteAtivo": st.column_config.TextColumn("Ingrediente Ativo", required=True),
                        "Formulacao": st.column_config.SelectboxColumn("Formulação", options=["Suspensão concentrada", "Formulação em óleo", "Pó molhável", "Formulação em pó", "Granulado dispersível"]),
                        "Dose": st.column_config.NumberColumn("Dose (kg/ha ou litro/ha)", min_value=0.0, step=1.0, required=True),
                        "Concentracao": st.column_config.TextColumn("Concentração em bula (UFC/g ou UFC/ml)", required=True),
                        "Fabricante": st.column_config.TextColumn("Fabricante", required=True)
                    },
                    use_container_width=True,
                    height=400,
                    column_order=COLUNAS_ESPERADAS["Biologicos"],
                    on_change=lambda: st.session_state.edited_data.update({"biologicos": True}),
                    disabled=False
                )

                if not edited_df.equals(df_biologicos):
                    # Converter a coluna de concentração para float
                    edited_df['Concentracao'] = edited_df['Concentracao'].apply(convert_scientific_to_float)
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_biologicos", use_container_width=True):
                    with st.spinner("Salvando dados..."):
                        try:
                            df_completo = st.session_state.local_data["biologicos"].copy()
                            
                            if filtro_nome != "Todos" or filtro_classe != "Todos":
                                mask = (
                                    (df_completo["Nome"].isin(edited_df["Nome"])) &
                                    (df_completo["Classe"] == filtro_classe if filtro_classe != "Todos" else True)
                                )
                            else:
                                mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                            
                            df_completo = df_completo[~mask]
                            df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                            df_final = df_final.drop_duplicates(subset=["Nome"], keep="last")
                            df_final = df_final.sort_values(by="Nome").reset_index(drop=True)
                            
                            st.session_state.local_data["biologicos"] = df_final
                            if update_sheet(df_final, "Biologicos"):
                                st.session_state.edited_data["biologicos"] = False
                                st.success("Dados salvos com sucesso!")
                                st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar alterações: {str(e)}")

    # Conteúdo da tab Quimicos
    elif aba_selecionada == "Quimicos":
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
                    classe = st.session_state.quimico_classe
                    fabricante = st.session_state.quimico_fabricante
                    dose = st.session_state.quimico_dose
                    
                    if nome:
                        novo_produto = {
                            "Nome": nome,
                            "Classe": classe,
                            "Fabricante": fabricante,
                            "Dose": dose
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
                        st.selectbox("Classe", options=["Herbicida", "Fungicida", "Inseticida", "Adjuvante", "Nutricional"], key="quimico_classe")
                    with col2:
                        st.number_input("Dose (kg/ha ou litro/ha)", value=0.0, step=1.0, key="quimico_dose")
                        st.text_input("Fabricante", key="quimico_fabricante")
                    
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
                    filtro_classe = st.selectbox(
                        "🔍 Filtrar por Classe",
                        options=["Todos", "Herbicida", "Fungicida", "Inseticida", "Adjuvante", "Nutricional"],
                        index=0,
                        key="filtro_classe_quimicos"
                    )

                # Aplicar filtro
                df_filtrado = dados["quimicos"].copy()
                if filtro_nome != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Nome"] == filtro_nome]
                if filtro_classe != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Classe"] == filtro_classe]
                
                # Garantir colunas esperadas
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Quimicos"]].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Quimicos"])
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    hide_index=True,
                    key="quimicos_editor",
                    column_config={
                        "Nome": st.column_config.TextColumn("Nome do Produto", required=True),
                        "Classe": st.column_config.SelectboxColumn("Classe", options=["Herbicida", "Fungicida", "Inseticida", "Adjuvante", "Nutricional"]),
                        "Fabricante": st.column_config.TextColumn("Fabricante", required=True),
                        "Dose": st.column_config.NumberColumn("Dose (kg/ha ou litro/ha)", min_value=0.0, step=1.0, required=True)
                    },
                    use_container_width=True,
                    height=400,
                    column_order=COLUNAS_ESPERADAS["Quimicos"],
                    on_change=lambda: st.session_state.edited_data.update({"quimicos": True}),
                    disabled=False
                )
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_quimicos", use_container_width=True):
                    with st.spinner("Salvando dados..."):
                        try:
                            df_completo = st.session_state.local_data["quimicos"].copy()
                            
                            if filtro_nome != "Todos" or filtro_classe != "Todos":
                                mask = (
                                    (df_completo["Nome"].isin(edited_df["Nome"])) &
                                    (df_completo["Classe"] == filtro_classe if filtro_classe != "Todos" else True)
                                )
                            else:
                                mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                            
                            df_completo = df_completo[~mask]
                            df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                            df_final = df_final.drop_duplicates(subset=["Nome"], keep="last")
                            df_final = df_final.sort_values(by="Nome").reset_index(drop=True)
                            
                            st.session_state.local_data["quimicos"] = df_final
                            if update_sheet(df_final, "Quimicos"):
                                st.session_state.edited_data["quimicos"] = False
                                st.success("Dados salvos com sucesso!")
                                st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Erro: {str(e)}")

    # Conteúdo da tab Compatibilidades
    elif aba_selecionada == "Compatibilidades":
        st.subheader("Resultados de Compatibilidade")
        
        if "compatibilidades" not in dados or dados["compatibilidades"].empty:
            st.error("Erro ao carregar dados das compatibilidades!")
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

                    if 'quimico_nome' not in st.session_state:
                        st.session_state.quimico_nome = ""
                    if 'biologico_nome' not in st.session_state:
                        st.session_state.biologico_nome = ""
                    if 'compatibilidade_form_submitted' not in st.session_state:
                        st.session_state.compatibilidade_form_submitted = False
                    if 'compatibilidade_form_success' not in st.session_state:
                        st.session_state.compatibilidade_form_success = False
                    if 'compatibilidade_form_error' not in st.session_state:
                        st.session_state.compatibilidade_form_error = ""

                    # Obter valores do formulário
                    biologico = st.session_state.resultado_biologico
                    quimico = st.session_state.resultado_quimico
                    data_teste = st.session_state.resultado_data
                    tempo = st.session_state.resultado_tempo
                    resultado = st.session_state.resultado_status
                    
                    if quimico and biologico:
                        nova_compatibilidade = {
                            "Data": data_teste.strftime("%Y-%m-%d"),
                            "Biologico": biologico,
                            "Quimico": quimico,
                            "Tempo": tempo,
                            "Resultado": resultado
                        }
                        
                        # Verificar se a combinação já existe
                        combinacao_existente = dados["compatibilidades"][
                            (dados["compatibilidades"]["Quimico"] == quimico) & 
                            (dados["compatibilidades"]["Biologico"] == biologico)
                        ]
                        
                        if not combinacao_existente.empty:
                            st.session_state.compatibilidade_form_submitted = True
                            st.session_state.compatibilidade_form_success = False
                            st.session_state.compatibilidade_form_error = f"Combinação {biologico} e {quimico} já existe!"
                        else:
                            # Adicionar à planilha
                            if append_to_sheet(nova_compatibilidade, "Compatibilidades"):
                                # Atualizar dados locais
                                nova_linha = pd.DataFrame([nova_compatibilidade])
                                st.session_state.local_data["compatibilidades"] = pd.concat([st.session_state.local_data["compatibilidades"], nova_linha], ignore_index=True)
                                
                                st.session_state.compatibilidade_form_submitted = True
                                st.session_state.compatibilidade_form_success = True
                                st.session_state.compatibilidade_form_error = ""

                            else:
                                st.session_state.compatibilidade_form_submitted = True
                                st.session_state.compatibilidade_form_success = False
                                st.session_state.compatibilidade_form_error = "Falha ao adicionar compatibilidade"
                    else:
                        st.session_state.compatibilidade_form_submitted = True
                        st.session_state.compatibilidade_form_success = False
                        st.session_state.compatibilidade_form_error = "Selecione os produtos biológico e químico"
                
                with st.form("nova_compatibilidade_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.selectbox(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]["Nome"].unique().tolist()),
                            key="biologico"
                        )
                        st.date_input("Data do Teste", key="data_teste", format="DD/MM/YYYY")
                    with col2:
                        st.selectbox(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]["Nome"].unique().tolist()),
                            key="quimico"
                        )
                        st.number_input("Tempo máximo testado em calda (horas)", min_value=0, value=0, key="tempo_teste")
                    st.selectbox("Resultado", options=["Compatível", "Incompatível"], key="status")
                    
                    submitted = st.form_submit_button("Adicionar Compatibilidade", on_click=submit_compatibilidade_form)
                
                # Mostrar mensagens de sucesso ou erro abaixo do formulário
                if st.session_state.compatibilidade_form_submitted:
                    if st.session_state.compatibilidade_form_success:
                        st.success(f"Compatibilidade entre '{st.session_state.biologico}' e '{st.session_state.quimico}' adicionada com sucesso!")
                        st.session_state.compatibilidade_form_submitted = False
                        st.session_state.compatibilidade_form_success = False
                        st.session_state.compatibilidade_just_submitted = False
                    else:
                        st.error(st.session_state.compatibilidade_form_error)
            
            else:  # Visualizar compatibilidades cadastradas
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_biologico = st.selectbox(
                        "🔍 Filtrar por Produto Biológico",
                        options=["Todos"] + sorted(dados["compatibilidades"]["Biologico"].unique().tolist()),
                        index=0,
                        key="filtro_biologico_compatibilidades"
                    )
                with col2:
                    filtro_quimico = st.selectbox(
                        "🔍 Filtrar por Produto Químico",
                        options=["Todos"] + sorted(dados["compatibilidades"]["Quimico"].unique().tolist()),
                        index=0,
                        key="filtro_quimico_compatibilidades"
                    )
                
                # Aplicar filtros
                df_filtrado = dados["compatibilidades"].copy()
                if filtro_biologico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
                if filtro_quimico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
                
                # Garantir colunas esperadas
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Compatibilidades"]].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Compatibilidades"])
                
                # Garantir que a coluna Data seja do tipo correto
                if 'Data' in df_filtrado.columns:
                    # Converter para string para evitar problemas de compatibilidade
                    df_filtrado['Data'] = df_filtrado['Data'].astype(str)
                
                # Tabela editável
                edited_df = st.data_editor(
                    df_filtrado,
                    hide_index=True,
                    num_rows="dynamic",
                    key="compatibilidades_editor",
                    column_config={
                        "Data": st.column_config.TextColumn("Data do Teste", required=True),
                        "Biologico": st.column_config.SelectboxColumn("Produto Biológico", options=sorted(dados["biologicos"]["Nome"].unique().tolist()), required=True),
                        "Quimico": st.column_config.SelectboxColumn("Produto Químico", options=sorted(dados["quimicos"]["Nome"].unique().tolist()), required=True),
                        "Tempo": st.column_config.NumberColumn("Tempo (horas)", min_value=0, default=0),
                        "Resultado": st.column_config.SelectboxColumn("Resultado", options=["Compatível", "Incompatível"], required=True)
                    },
                    use_container_width=True,
                    height=400,
                    column_order=COLUNAS_ESPERADAS["Compatibilidades"],
                    on_change=lambda: st.session_state.edited_data.update({"compatibilidades": True}),
                    disabled=False
                )
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_compatibilidades", use_container_width=True):
                    with st.spinner("Salvando dados..."):
                        try:
                            df_completo = st.session_state.local_data["compatibilidades"].copy()
                            
                            if filtro_quimico != "Todos" or filtro_biologico != "Todos":
                                mask = (
                                    (df_completo["Quimico"] == filtro_quimico) &
                                    (df_completo["Biologico"] == filtro_biologico)
                                )
                            else:
                                mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                            
                            df_completo = df_completo[~mask]
                            df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                            df_final = df_final.drop_duplicates(subset=["Biologico", "Quimico"], keep="last")
                            df_final = df_final.sort_values(by=["Biologico", "Quimico"]).reset_index(drop=True)
                            
                            st.session_state.local_data["compatibilidades"] = df_final
                            if update_sheet(df_final, "Compatibilidades"):
                                st.session_state.edited_data["compatibilidades"] = False
                                st.success("Dados salvos com sucesso!")
                                st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar alterações: {str(e)}")
    
    # Conteúdo da tab Solicitações
    elif aba_selecionada == "Solicitações":
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
                    st.success("Solicitação de novo teste registrada com sucesso!")
                    
                    # Mostrar detalhes da solicitação
                    st.info("**Detalhes da solicitação:**")
                    st.write(f"**Data:** {st.session_state.gerenciamento_last_submission.get('Data', '')}")
                    st.write(f"**Solicitante:** {st.session_state.gerenciamento_last_submission.get('Solicitante', '')}")
                    st.write(f"**Produto Biológico:** {st.session_state.gerenciamento_last_submission.get('Biologico', '')}")
                    st.write(f"**Produto Químico:** {st.session_state.gerenciamento_last_submission.get('Quimico', '')}")
                    
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
                    biologico = st.session_state.gerenciamento_biologico
                    quimico = st.session_state.gerenciamento_quimico
                    observacoes = st.session_state.gerenciamento_observacoes
                    
                    # Validar campos obrigatórios
                    if not solicitante or not quimico or not biologico:
                        st.warning("Preencha todos os campos obrigatórios")
                        return
                    
                    # Preparar dados da solicitação
                    nova_solicitacao = {
                        "Data": data.strftime("%Y-%m-%d"),
                        "Solicitante": solicitante,
                        "Biologico": biologico,
                        "Quimico": quimico,
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
                        st.text_input("Produto Biológico", key="gerenciamento_biologico")
                        st.text_input("Nome do solicitante", key="gerenciamento_solicitante")
                        
                    with col2:
                        st.text_input("Produto Químico", key="gerenciamento_quimico")
                        st.date_input("Data da Solicitação", value=datetime.now(), key="gerenciamento_data", format="DD/MM/YYYY")
                    
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
                    filtro_biologico = st.selectbox(
                        "🔍 Filtrar por Produto Biológico",
                        options=["Todos"] + sorted(dados["solicitacoes"]["Biologico"].unique().tolist()),
                        index=0,
                        key="filtro_biologico_solicitacoes"
                    )
                with col3:
                    filtro_quimico = st.selectbox(
                        "🔍 Filtrar por Produto Químico",
                        options=["Todos"] + sorted(dados["solicitacoes"]["Quimico"].unique().tolist()),
                        index=0,
                        key="filtro_quimico_solicitacoes"
                    )
                
                # Aplicar filtros
                if not dados["solicitacoes"].empty:
                    df_filtrado = dados["solicitacoes"].copy()
                else:
                    df_filtrado = pd.DataFrame()

                if filtro_status != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]
                if filtro_biologico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
                if filtro_quimico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
                
                # Garantir colunas esperadas
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
                
                # Garantir que a coluna Data seja do tipo correto
                if 'Data' in df_filtrado.columns:
                    # Converter para string para evitar problemas de compatibilidade
                    df_filtrado['Data'] = df_filtrado['Data'].astype(str)
                
                # Tabela editável com ordenação por Data
                if not df_filtrado.empty:
                    df_filtrado = df_filtrado.sort_values(by="Data", ascending=False).reset_index(drop=True)
                
                edited_df = st.data_editor(
                    df_filtrado,
                    hide_index=True,
                    num_rows="dynamic",
                    key="solicitacoes_editor",
                    column_config={
                        "Data": st.column_config.TextColumn("Data da Solicitação", required=True),
                        "Solicitante": st.column_config.TextColumn("Solicitante", required=True),
                        "Biologico": st.column_config.SelectboxColumn("Produto Biológico", options=sorted(dados["biologicos"]["Nome"].unique().tolist()), required=True),
                        "Quimico": st.column_config.SelectboxColumn("Produto Químico", options=sorted(dados["quimicos"]["Nome"].unique().tolist()), required=True),
                        "Observacoes": st.column_config.TextColumn("Observações", required=True),
                        "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Análise", "Concluído", "Cancelado"])
                    },
                    use_container_width=True,
                    height=400,
                    column_order=COLUNAS_ESPERADAS["Solicitacoes"],
                    on_change=lambda: st.session_state.edited_data.update({"solicitacoes": True}),
                    disabled=False
                )
                
                # Botão para salvar alterações
                if st.button("Salvar Alterações", key="save_solicitacoes", use_container_width=True):
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
                            
                            st.session_state.local_data["solicitacoes"] = df_final
                            if update_sheet(df_final, "Solicitacoes"):
                                st.session_state.edited_data["solicitacoes"] = False
                                st.success("Dados salvos com sucesso!")
                                st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar dados: {str(e)}")

    # Removendo o componente JavaScript para evitar conflitos
    def fix_table_buttons():
        pass

########################################## CÁLCULOS ##########################################

def calculos():
    st.title("🧮 Cálculos de Concentração")
    
    if 'concentracao_obtida' not in st.session_state:
        st.session_state.concentracao_obtida = 0.0
    if 'concentracao_esperada' not in st.session_state:
        st.session_state.concentracao_esperada = 0.0
    
    st.header("Concentração Obtida")
    st.markdown("Fórmula: Média das placas (colônias) × Diluição × 10")
    
    col1, col2 = st.columns(2)
    with col1:
        placa1 = st.number_input("Placa 1 (colônias)", min_value=0, step=1, value=st.session_state.get('placa1', 0), key="placa1")
        placa2 = st.number_input("Placa 2 (colônias)", min_value=0, step=1, value=st.session_state.get('placa2', 0), key="placa2")
        placa3 = st.number_input("Placa 3 (colônias)", min_value=0, step=1, value=st.session_state.get('placa3', 0), key="placa3")
    
    with col2:
        diluicao = st.number_input("Diluição", min_value=0.0, format="%.2e", value=st.session_state.get('diluicao', 1e-6), key="diluicao")
        
    media_placas = (placa1 + placa2 + placa3) / 3
    concentracao_obtida = media_placas * diluicao * 10
    st.session_state.concentracao_obtida = concentracao_obtida
    
    st.info(f"Concentração Obtida: {concentracao_obtida:.2e} UFC/mL")
    
    st.markdown("---")
    
    st.header("Concentração Esperada")
    st.markdown("Fórmula: (Concentração do ativo × Dose) ÷ Volume de calda")
    
    col1, col2 = st.columns(2)
    with col1:
        conc_ativo = st.number_input("Concentração do ativo (UFC/mL)", min_value=0.0, format="%.2e", value=st.session_state.get('conc_ativo', 1e9), key="conc_ativo")
        dose = st.number_input("Dose (L/ha ou kg/ha)", min_value=0.0, step=0.1, value=st.session_state.get('dose', 1.0), key="dose")
    
    with col2:
        volume_calda = st.number_input("Volume de calda (L/ha)", min_value=0.1, step=1.0, value=st.session_state.get('volume_calda', 200.0), key="volume_calda")
    
    concentracao_esperada = (conc_ativo * dose) / volume_calda
    st.session_state.concentracao_esperada = concentracao_esperada
    
    st.info(f"Concentração Esperada: {concentracao_esperada:.2e} UFC/mL")
    
    st.markdown("---")
    
    st.header("Resultado Final")
    
    if st.session_state.concentracao_obtida > 0 and st.session_state.concentracao_esperada > 0:
        razao = st.session_state.concentracao_obtida / st.session_state.concentracao_esperada
        
        st.write("**Detalhamento dos Cálculos:**")
        st.write(f"""
        **1. Concentração Obtida**
        - Média das placas = ({placa1} + {placa2} + {placa3}) ÷ 3 = {media_placas:.1f}
        - Diluição = {diluicao:.2e}
        - Concentração Obtida = {media_placas:.1f} × {diluicao:.2e} × 10 = {concentracao_obtida:.2e} UFC/mL
        
        **2. Concentração Esperada**
        - Concentração do ativo = {conc_ativo:.2e} UFC/mL
        - Dose = {dose:.1f} L/ha
        - Volume de calda = {volume_calda:.1f} L/ha
        - Concentração Esperada = ({conc_ativo:.2e} × {dose:.1f}) ÷ {volume_calda:.1f} = {concentracao_esperada:.2e} UFC/mL
        
        **3. Compatibilidade**
        - Razão (Obtida/Esperada) = {concentracao_obtida:.2e} ÷ {concentracao_esperada:.2e} = {razao:.2f}
        """)
        
        if 0.8 <= razao <= 1.5:
            st.success("✅ COMPATÍVEL - A razão está dentro do intervalo ideal (0,8 a 1,5)")
        elif razao > 1.5:
            st.warning("⚠️ ATENÇÃO - A razão está acima de 1,5")
        else:
            st.error("❌ INCOMPATÍVEL - A razão está abaixo de 0,8")
    else:
        st.info("Preencha os valores acima para ver o resultado da compatibilidade.")

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
        ("Compatibilidade", "Gerenciamento", "Cálculos"),
        index=0 if st.session_state.current_page == "Compatibilidade" else 1 if st.session_state.current_page == "Gerenciamento" else 2
    )
    
    # Atualizar o estado da página atual
    st.session_state.current_page = menu_option

    st.sidebar.markdown("---")

    if menu_option == "Compatibilidade":
        compatibilidade()
    elif menu_option == "Gerenciamento":
        gerenciamento()
    elif menu_option == "Cálculos":
        calculos()

########################################## EXECUÇÃO ##########################################

if __name__ == "__main__":
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = True

    try:
        if st.session_state["logged_in"]:
            main()
    except Exception as e:
        st.error(f"Erro ao iniciar a sessão: {str(e)}")