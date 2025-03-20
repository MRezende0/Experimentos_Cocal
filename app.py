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

# Inicialização das variáveis de sessão
def inicializar_sessao():
    """
    Inicializa as variáveis de sessão necessárias para o funcionamento do aplicativo
    """
    # Inicializar variáveis de sessão se não existirem
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
        
    # Variáveis para a página de compatibilidade
    if 'compatibilidade_biologico' not in st.session_state:
        st.session_state.compatibilidade_biologico = None
    
    if 'compatibilidade_quimico' not in st.session_state:
        st.session_state.compatibilidade_quimico = None
        
    # Variáveis para a página de cálculos
    if 'calculo_biologico' not in st.session_state:
        st.session_state.calculo_biologico = None
    
    if 'calculo_quimicos' not in st.session_state:
        st.session_state.calculo_quimicos = []
    
    if 'calculo_volume_calda' not in st.session_state:
        st.session_state.calculo_volume_calda = 100.0
        
    # Variáveis para a aba ativa no gerenciamento
    if 'aba_ativa' not in st.session_state:
        st.session_state.aba_ativa = "Biologicos"
        
    # Variáveis para cache de dados
    if 'data_timestamp' not in st.session_state:
        st.session_state.data_timestamp = None
    
    # Inicialização dos dados locais
# Inicialização dos dados locais
if 'local_data' not in st.session_state:
    # Inicializar com DataFrames vazios com as colunas esperadas
    st.session_state.local_data = {
        "quimicos": pd.DataFrame(columns=COLUNAS_ESPERADAS["Quimicos"]),
        "biologicos": pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"]),
        "calculos": pd.DataFrame(columns=COLUNAS_ESPERADAS["Calculos"]),
        "solicitacoes": pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
    }
        
    # Variáveis para controle de formulários no gerenciamento
    if 'biologico_form_submitted' not in st.session_state:
        st.session_state.biologico_form_submitted = False
    
    if 'biologico_form_success' not in st.session_state:
        st.session_state.biologico_form_success = False
    
    if 'biologico_form_error' not in st.session_state:
        st.session_state.biologico_form_error = ""
        
    if 'quimico_form_submitted' not in st.session_state:
        st.session_state.quimico_form_submitted = False
    
    if 'quimico_form_success' not in st.session_state:
        st.session_state.quimico_form_success = False
    
    if 'quimico_form_error' not in st.session_state:
        st.session_state.quimico_form_error = ""
        
    if 'calculo_form_submitted' not in st.session_state:
        st.session_state.calculo_form_submitted = False
    
    if 'calculo_form_success' not in st.session_state:
        st.session_state.calculo_form_success = False
    
    if 'calculo_form_error' not in st.session_state:
        st.session_state.calculo_form_error = ""
        
    if 'gerenciamento_form_submitted' not in st.session_state:
        st.session_state.gerenciamento_form_submitted = False
        
    if 'biologicos_saved' not in st.session_state:
        st.session_state.biologicos_saved = False
    
    if 'quimicos_saved' not in st.session_state:
        st.session_state.quimicos_saved = False
    
    if 'solicitacoes_saved' not in st.session_state:
        st.session_state.solicitacoes_saved = False

inicializar_sessao()

########################################## CONEXÃO GOOGLE SHEETS ##########################################

SHEET_ID = "1lILLXICVkVekkm2EZ-20cLnkYFYvHnb14NL_Or7132U"
SHEET_GIDS = {
    "Calculos": "0",
    "Biologicos": "1440941690",
    "Quimicos": "885876195",
    "Solicitacoes": "1408097520",
}

COLUNAS_ESPERADAS = {
    "Biologicos": ["Nome", "Classe", "IngredienteAtivo", "Formulacao", "Dose", "Concentracao", "Fabricante"],
    "Quimicos": ["Nome", "Classe", "Fabricante", "Dose"],
    "Solicitacoes": ["Data", "Solicitante", "Biologico", "Quimico", "Observacoes", "Status"],
    "Calculos": ["Biologico", "Quimico", "Placa1", "Placa2", "Placa3", "MédiaPlacas", "Diluicao", "ConcObtida", "Dose", "ConcAtivo", "VolumeCalda", "ConcEsperada", "Razao", "Resultado"]
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
        
        # Desabilitar verificação SSL para contornar possíveis problemas de rede corporativa
        if hasattr(client, 'session'):
            client.session.verify = False
            
        # Configurar o contexto SSL para ignorar verificações
        ssl._create_default_https_context = ssl._create_unverified_context
            
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
    try:
        # Obter a planilha
        sheet = retry_with_backoff(lambda: get_sheet(sheet_name))
        if not sheet:
            st.error(f"Não foi possível acessar a planilha {sheet_name}")
            return False
            
        # Verificar se as colunas esperadas existem
        if sheet_name in COLUNAS_ESPERADAS:
            colunas_esperadas = COLUNAS_ESPERADAS[sheet_name]
            
            # Verificar se todas as colunas esperadas estão no dicionário
            for col in colunas_esperadas:
                if col not in data_dict:
                    data_dict[col] = None  # Preencher com None se não existir
            
            # Ordenar o dicionário conforme as colunas esperadas
            data_ordenado = [data_dict.get(col, None) for col in colunas_esperadas]
            
            # Adicionar a nova linha
            sheet.append_row(data_ordenado)
            
            # Atualizar os dados na sessão para evitar recarregamento
            if 'local_data' in st.session_state and sheet_name.lower() in st.session_state.local_data:
                # Converter para DataFrame e concatenar
                novo_df = pd.DataFrame([data_dict])
                st.session_state.local_data[sheet_name.lower()] = pd.concat(
                    [st.session_state.local_data[sheet_name.lower()], novo_df], 
                    ignore_index=True
                )
            
            return True
        else:
            st.error(f"Configuração de colunas não encontrada para {sheet_name}")
            return False
    except Exception as e:
        st.error(f"Erro ao adicionar dados à planilha {sheet_name}: {str(e)}")
        return False

def load_sheet_data(sheet_name: str) -> pd.DataFrame:
    def _load(sheet_name=sheet_name):
        try:
            # Obter a planilha
            sheet = get_sheet(sheet_name)
            if not sheet:
                st.error(f"Planilha '{sheet_name}' não encontrada.")
                return pd.DataFrame(columns=COLUNAS_ESPERADAS[sheet_name])
            
            # Obter todos os dados da planilha
            data = sheet.get_all_records()
            
            # Verificar se há dados
            if not data:
                return pd.DataFrame(columns=COLUNAS_ESPERADAS[sheet_name])
            
            # Converter para DataFrame
            df = pd.DataFrame(data)
            
            # Verificar se as colunas esperadas estão presentes
            colunas_faltantes = [col for col in COLUNAS_ESPERADAS[sheet_name] if col not in df.columns]
            if colunas_faltantes:
                # Adicionar colunas faltantes
                for col in colunas_faltantes:
                    df[col] = None
            
            return df
        except Exception as e:
            st.error(f"Erro ao carregar dados da planilha '{sheet_name}': {str(e)}")
            return pd.DataFrame(columns=COLUNAS_ESPERADAS[sheet_name])
    
    return retry_with_backoff(_load, max_retries=3, initial_delay=1)

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
        
        # Substituir valores NaN por None para compatibilidade com JSON
        df_copy = df_copy.replace({np.nan: None})
                
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
    Carrega todos os dados necessários das planilhas.
    
    Returns:
        dict: Dicionário com todos os dados carregados
    """
    # Verificar se já temos dados na sessão que ainda são válidos
    if ('local_data' in st.session_state and 
        'data_timestamp' in st.session_state and 
        st.session_state.data_timestamp is not None and
        (datetime.now() - st.session_state.data_timestamp).total_seconds() < 300):  # 5 minutos
        return st.session_state.local_data
    
    # Inicializar dicionário para armazenar os dados
    dados = {}
    
    # Tentar carregar cada planilha com tratamento de erro
    try:
        dados["biologicos"] = load_sheet_data("Biologicos")
        if dados["biologicos"].empty:
            st.warning("A planilha de Biológicos está vazia.")
    except Exception as e:
        st.error(f"Erro ao carregar dados de Biológicos: {str(e)}")
        dados["biologicos"] = pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"])
    
    try:
        dados["quimicos"] = load_sheet_data("Quimicos")
        if dados["quimicos"].empty:
            st.warning("A planilha de Químicos está vazia.")
    except Exception as e:
        st.error(f"Erro ao carregar dados de Químicos: {str(e)}")
        dados["quimicos"] = pd.DataFrame(columns=COLUNAS_ESPERADAS["Quimicos"])
    
    try:
        dados["calculos"] = load_sheet_data("Calculos")
        # Não mostrar aviso se a planilha de cálculos estiver vazia, pois isso é normal no início
    except Exception as e:
        st.error(f"Erro ao carregar dados de Cálculos: {str(e)}")
        dados["calculos"] = pd.DataFrame(columns=COLUNAS_ESPERADAS["Calculos"])
    
    try:
        dados["solicitacoes"] = load_sheet_data("Solicitacoes")
        # Não mostrar aviso se a planilha de solicitações estiver vazia
    except Exception as e:
        st.error(f"Erro ao carregar dados de Solicitações: {str(e)}")
        dados["solicitacoes"] = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
    
    # Atualizar a sessão
    st.session_state.local_data = dados
    st.session_state.data_timestamp = datetime.now()
    
    return dados

def _load_and_validate_sheet(sheet_name: str) -> pd.DataFrame:
    """
    Carrega e valida os dados de uma planilha específica
    """
    try:
        df = load_sheet_data(sheet_name)
        
        # Verificar se o DataFrame está vazio
        if df.empty:
            st.warning(f"A planilha {sheet_name} está vazia ou não foi carregada corretamente.")
            return pd.DataFrame()
            
        # Validações específicas para cada tipo de planilha
        if sheet_name == "Biologicos":
            if "Nome" not in df.columns:
                st.error(f"Coluna 'Nome' não encontrada na planilha {sheet_name}")
                return pd.DataFrame()
                
            # Verificar se há dados na coluna Nome
            if df["Nome"].isna().all() or (df["Nome"] == "").all():
                st.warning(f"Nenhum produto biológico cadastrado na planilha {sheet_name}")
                return pd.DataFrame()
                
        elif sheet_name == "Quimicos":
            if "Nome" not in df.columns:
                st.error(f"Coluna 'Nome' não encontrada na planilha {sheet_name}")
                return pd.DataFrame()
                
            # Verificar se há dados na coluna Nome
            if df["Nome"].isna().all() or (df["Nome"] == "").all():
                st.warning(f"Nenhum produto químico cadastrado na planilha {sheet_name}")
                return pd.DataFrame()
                
        elif sheet_name == "Calculos":
            required_cols = ["Biologico", "Quimico", "Resultado"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                # Tentar encontrar colunas com nomes similares
                for col in missing_cols[:]:
                    similar_cols = [c for c in df.columns if c.lower() == col.lower()]
                    if similar_cols:
                        # Renomear a coluna para o nome esperado
                        df = df.rename(columns={similar_cols[0]: col})
                        missing_cols.remove(col)
                
                if missing_cols:
                    st.error(f"Colunas obrigatórias não encontradas na planilha {sheet_name}: {', '.join(missing_cols)}")
                    return pd.DataFrame()
        
        return df
        
    except Exception as e:
        st.error(f"Erro ao carregar e validar a planilha {sheet_name}: {str(e)}")
        return pd.DataFrame()

def convert_scientific_to_float(value):
    """Converte notação científica em string para float"""
    try:
        # Se o valor for vazio ou None, retorna None
        if pd.isna(value) or value == '' or value is None:
            return None
            
        if isinstance(value, (int, float)):
            return float(value)
            
        # Remove espaços e substitui vírgula por ponto
        value = str(value).strip().replace(' ', '').replace(',', '.')
        
        # Trata notação com 'E' ou 'e'
        if 'e' in value.lower():
            try:
                return float(value)
            except ValueError:
                raise ValueError(f"Formato inválido para notação científica: {value}")
                
        # Trata notação com ×10^
        if '×10^' in value:
            try:
                base, exponent = value.split('×10^')
                return float(base) * (10 ** float(exponent))
            except ValueError:
                raise ValueError(f"Formato inválido para notação com ×10^: {value}")
                
        # Tenta converter diretamente para float
        try:
            return float(value)
        except ValueError:
            raise ValueError(f"Valor não pode ser convertido para número: {value}")
            
    except Exception as e:
        # Propaga o erro para ser tratado pelo chamador
        raise ValueError(f"Erro ao converter valor '{value}': {str(e)}")

########################################## COMPATIBILIDADE ##########################################

def compatibilidade():
    # As variáveis de sessão já são inicializadas pela função inicializar_sessao()
    
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
    
    # Carregar dados
    try:
        # Usar dados da sessão em vez de recarregar a cada interação
        if 'local_data' not in st.session_state or not st.session_state.local_data:
            dados = load_all_data()
        else:
            dados = st.session_state.local_data
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return
    
    # Verificar se a chave 'biologicos' existe no dicionário de dados
    if "biologicos" not in dados or dados["biologicos"].empty:
        st.warning("""
            **Nenhum produto biológico cadastrado!**
            Por favor:
            1. Verifique a planilha 'Biologicos' no Google Sheets
            2. Confira se há dados na planilha
            3. Verifique as permissões de acesso
        """)
        
        # Forçar recarregamento dos dados
        if st.button("Recarregar dados", key="btn_reload_data"):
            # Limpar o cache de dados
            if 'data_timestamp' in st.session_state:
                st.session_state.data_timestamp = None
            if 'local_data' in st.session_state:
                st.session_state.local_data = {}
            st.rerun()
            
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
        # Garantir que a chave compatibilidade_biologico esteja inicializada
        if "compatibilidade_biologico" not in st.session_state:
            st.session_state.compatibilidade_biologico = None
            
        # Verificar se a chave 'biologicos' existe e se a coluna 'Nome' existe no DataFrame
        if "biologicos" not in dados:
            st.error("Erro: Não foi possível carregar os dados de produtos biológicos.")
            return
            
        if 'Nome' not in dados["biologicos"].columns:
            st.error("Erro: A coluna 'Nome' não foi encontrada na planilha de produtos biológicos.")
            return
            
        biologico = st.selectbox(
            "Produto Biológico",
            options=sorted(dados["biologicos"]['Nome'].unique().tolist()) if not dados["biologicos"].empty else [],
            index=None,
            key="compatibilidade_biologico"
        )
        
        # Atualizar o estado após a seleção
        if biologico is not None:
            st.session_state.compatibilidade_quimico = None

    # Filtrar os químicos que já foram testados com o biológico selecionado
    quimicos_disponiveis = []
    if biologico:
        try:
            # Verificar se a chave 'calculos' existe
            if "calculos" not in dados or dados["calculos"].empty:
                st.info(f"Nenhum cálculo encontrado para o biológico '{biologico}'.")
                quimicos_disponiveis = []
                return
            
            # Verificar se a coluna "Biologico" existe no DataFrame
            if "Biologico" not in dados["calculos"].columns:
                colunas_similares = [col for col in dados["calculos"].columns if col.lower() == "biologico"]
                if colunas_similares:
                    coluna_biologico = colunas_similares[0]
                else:
                    st.error("Erro: Não foi possível encontrar a coluna 'Biologico' na planilha de cálculos.")
                    return
            else:
                coluna_biologico = "Biologico"
            
            # Obter todos os químicos que já foram testados com este biológico
            calculos_biologico = dados["calculos"][
                dados["calculos"][coluna_biologico] == biologico
            ]
            
            # Verificar se a coluna "Quimico" existe
            if "Quimico" not in dados["calculos"].columns:
                colunas_similares = [col for col in dados["calculos"].columns if col.lower() == "quimico"]
                if colunas_similares:
                    coluna_quimico = colunas_similares[0]
                else:
                    st.error("Erro: Não foi possível encontrar a coluna 'Quimico' na planilha de cálculos.")
                    return
            else:
                coluna_quimico = "Quimico"
            
            # Extrair todos os químicos das combinações (pode conter múltiplos químicos separados por +)
            quimicos_testados = []
            for quimico_combinado in calculos_biologico[coluna_quimico].unique():
                if quimico_combinado and isinstance(quimico_combinado, str):
                    # Dividir cada entrada que pode conter múltiplos químicos
                    for quimico_individual in quimico_combinado.split("+"):
                        quimico_individual = quimico_individual.strip()
                        if quimico_individual and quimico_individual not in quimicos_testados:
                            quimicos_testados.append(quimico_individual)
            
            quimicos_disponiveis = sorted(quimicos_testados)
            
            # Mostrar informação sobre químicos encontrados
            if not quimicos_disponiveis:
                st.info(f"Nenhum produto químico encontrado para o biológico '{biologico}'.")
                
        except Exception as e:
            st.error(f"Erro ao filtrar químicos: {str(e)}")
            # Mostrar informações de debug para ajudar na resolução do problema
            if "calculos" in dados:
                st.error(f"Colunas disponíveis na planilha de cálculos: {', '.join(dados['calculos'].columns.tolist())}")
            quimicos_disponiveis = []
    
    with col2:
        # Garantir que a chave compatibilidade_quimico esteja inicializada
        if "compatibilidade_quimico" not in st.session_state:
            st.session_state.compatibilidade_quimico = None
            
        quimico = st.selectbox(
            "Produto Químico",
            options=quimicos_disponiveis if quimicos_disponiveis else [],
            index=None,
            key="compatibilidade_quimico",
            disabled=not biologico
        )
    
    if quimico and biologico:
        try:
            # Determinar quais colunas usar (considerando possíveis diferenças de maiúsculas/minúsculas)
            coluna_biologico = "Biologico"
            if "Biologico" not in dados["calculos"].columns:
                colunas_similares = [col for col in dados["calculos"].columns if col.lower() == "biologico"]
                if colunas_similares:
                    coluna_biologico = colunas_similares[0]
                else:
                    st.error("Erro: Não foi possível encontrar a coluna 'Biologico' na planilha de cálculos.")
                    return
                    
            coluna_quimico = "Quimico"
            if "Quimico" not in dados["calculos"].columns:
                colunas_similares = [col for col in dados["calculos"].columns if col.lower() == "quimico"]
                if colunas_similares:
                    coluna_quimico = colunas_similares[0]
                else:
                    st.error("Erro: Não foi possível encontrar a coluna 'Quimico' na planilha de cálculos.")
                    return
            
            # Procurar na planilha de Cálculos usando os nomes
            resultado_existente = pd.DataFrame()
            
            # Tentar encontrar o químico como parte de uma combinação
            for idx, row in dados["calculos"].iterrows():
                if row[coluna_biologico] == biologico and isinstance(row[coluna_quimico], str):
                    # Dividir a combinação de químicos
                    quimicos_combinados = [q.strip() for q in str(row[coluna_quimico]).split("+")]
                    # Verificar se o químico selecionado está na lista
                    if quimico.strip() in quimicos_combinados:
                        resultado_existente = dados["calculos"].iloc[[idx]]
                        break
            
            if not resultado_existente.empty:
                # Verificar se a coluna "Resultado" existe
                coluna_resultado = "Resultado"
                if "Resultado" not in resultado_existente.columns:
                    colunas_similares = [col for col in resultado_existente.columns if col.lower() == "resultado"]
                    if colunas_similares:
                        coluna_resultado = colunas_similares[0]
                    else:
                        st.error("Erro: Não foi possível encontrar a coluna 'Resultado' na planilha de cálculos.")
                        return
                
                # Mostrar resultado de compatibilidade
                compativel = resultado_existente.iloc[0][coluna_resultado].lower() == "compatível"
                
                if compativel:
                    st.markdown("""
                        <div class="resultado compativel">
                        ✅ Compatível
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                        <div class="resultado incompativel">
                        ❌ Incompatível
                        </div>
                        """, unsafe_allow_html=True)
                
                # Mostrar detalhes do teste
                with st.expander("Ver detalhes do teste", expanded=True):
                    # Criar uma tabela para mostrar os detalhes de forma mais organizada
                    colunas_exibir = ["Biologico", "Quimico", "MédiaPlacas", "Diluicao", "ConcObtida", 
                                    "Dose", "ConcAtivo", "VolumeCalda", "ConcEsperada", "Razao", "Resultado"]
                    
                    # Mapear os nomes de colunas para os nomes reais no DataFrame
                    colunas_mapeadas = {}
                    for col in colunas_exibir:
                        if col in resultado_existente.columns:
                            colunas_mapeadas[col] = col
                        else:
                            # Tentar encontrar coluna com nome similar
                            colunas_similares = [c for c in resultado_existente.columns if c.lower() == col.lower()]
                            if colunas_similares:
                                colunas_mapeadas[col] = colunas_similares[0]
                    
                    # Verificar quais colunas existem no DataFrame
                    colunas_disponiveis = list(colunas_mapeadas.values())
                    
                    if colunas_disponiveis:
                        detalhes_df = resultado_existente[colunas_disponiveis].copy()
                        
                        # Renomear colunas para exibição
                        colunas_renomeadas = {v: k for k, v in colunas_mapeadas.items()}
                        detalhes_df = detalhes_df.rename(columns=colunas_renomeadas)
                        
                        # Formatar a tabela para melhor visualização
                        st.dataframe(
                            detalhes_df,
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.warning("Não foi possível encontrar colunas para exibir os detalhes do teste.")
            else:
                st.warning(f"Não foi encontrado nenhum teste de compatibilidade entre {biologico} e {quimico}.")
                
                # Botão para solicitar novo teste
                if st.button("Solicitar teste de compatibilidade", key="btn_solicitar_teste"):
                    st.session_state.solicitar_novo_teste = True
                    st.session_state.pre_selecionado_biologico = biologico
                    st.session_state.pre_selecionado_quimico = quimico
                    st.rerun()
        except Exception as e:
            st.error(f"Erro ao buscar resultados de compatibilidade: {str(e)}")
            # Mostrar informações de debug
            if "calculos" in dados:
                st.error(f"Colunas disponíveis na planilha de cálculos: {', '.join(dados['calculos'].columns.tolist())}")
    
    # Exibir mensagem de sucesso se acabou de enviar uma solicitação
    if st.session_state.form_submitted_successfully:
        st.success("Solicitação de novo teste enviada com sucesso!")
        time.sleep(3) # Aguarda 3 segundos antes de limpar a mensagem
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

    # Carregar dados
    try:
        # Usar dados da sessão em vez de recarregar a cada interação
        if 'local_data' not in st.session_state or not st.session_state.local_data:
            dados = load_all_data()
        else:
            dados = st.session_state.local_data
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return
    
    # Função para processar o envio do formulário
    def submit_form():
        # Obter valores do formulário
        data = st.session_state.data_solicitacao
        solicitante = st.session_state.solicitante
        quimicos_input = st.session_state.quimicos_input
        biologico_input = st.session_state.biologico_input
        observacoes = st.session_state.observacoes
        
        if not all([solicitante, quimicos_input, biologico_input]):
            st.error("""
            Por favor, preencha todos os campos obrigatórios:
            - Nome do solicitante
            - Nome do produto químico
            - Nome do produto biológico
            """)
            return

        # Preparar dados da solicitação
        # Se houver múltiplos químicos, concatenar com "+"
        quimicos_str = " + ".join(quimicos_input) if isinstance(quimicos_input, list) else quimicos_input
        
        nova_solicitacao = {
            "Data": data.strftime("%Y-%m-%d"),
            "Solicitante": solicitante,
            "Biologico": biologico_input,
            "Quimico": quimicos_str,
            "Observacoes": observacoes,
            "Status": "Pendente"
        }

        # Verificar se já existe uma solicitação similar
        solicitacoes_existentes = dados["solicitacoes"]
        solicitacao_similar = solicitacoes_existentes[
            (solicitacoes_existentes["Biologico"] == biologico_input) & 
            (solicitacoes_existentes["Quimico"].str.contains(quimicos_str, regex=False))
        ]
        
        # Verificar se já existe um cálculo para esta combinação
        calculos_existentes = dados["calculos"]
        calculo_existente = calculos_existentes[
            (calculos_existentes["Biologico"] == biologico_input) & 
            (calculos_existentes["Quimico"].str.contains(quimicos_str, regex=False))
        ]
        
        if not solicitacao_similar.empty:
            st.warning(f"Já existe uma solicitação para {biologico_input} e {quimicos_str}. Status: {solicitacao_similar.iloc[0]['Status']}")
            return
            
        if not calculo_existente.empty:
            st.warning(f"Já existe um cálculo para {biologico_input} e {quimicos_str}. Resultado: {calculo_existente.iloc[0]['Resultado']}")
            return

        if append_to_sheet(nova_solicitacao, "Solicitacoes"):
            st.session_state.form_submitted_successfully = True
            st.session_state.solicitar_novo_teste = False
            st.session_state.last_submission = nova_solicitacao
        else:
            st.error("Erro ao enviar solicitação. Tente novamente.")
    
    # Mostrar o formulário para entrada de dados
    st.subheader("Solicitar Novo Teste")
    
    # Valores iniciais para os campos
    default_quimico = quimico if quimico else None
    default_biologico = biologico if biologico else ""

    with st.form("solicitacao_form", clear_on_submit=True):
        # Campos do formulário
        col1, col2 = st.columns(2)
        
        with col1:
            st.date_input("Data", value=datetime.now(), key="data_solicitacao", format="DD/MM/YYYY")
            st.text_input("Nome do Solicitante", key="solicitante")
            
            # Multiselect para permitir selecionar múltiplos químicos
            st.multiselect(
                "Produtos Químicos",
                options=sorted(dados["quimicos"]["Nome"].unique().tolist()),
                default=[default_quimico] if default_quimico else [],
                key="quimicos_input"
            )
        
        with col2:
            st.selectbox(
                "Produto Biológico",
                options=sorted(dados["biologicos"]["Nome"].unique().tolist()),
                index=sorted(dados["biologicos"]["Nome"].unique().tolist()).index(default_biologico) if default_biologico in dados["biologicos"]["Nome"].unique() else 0,
                key="biologico_input"
            )
            
            st.text_area("Observações", key="observacoes", height=100)
        
        # Botões de ação
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Enviar Solicitação", use_container_width=True):
                submit_form()
        
        with col2:
            if st.form_submit_button("Cancelar", use_container_width=True):
                st.session_state.solicitar_novo_teste = False
                st.rerun()

########################################## GERENCIAMENTO ##########################################

def gerenciamento():
    st.title("⚙️ Gerenciamento")

    # Inicialização dos dados locais
    if 'local_data' not in st.session_state or not st.session_state.local_data:
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
        ["Biológicos", "Químicos", "Cálculos", "Solicitações"],
        key="management_tabs",
        horizontal=True,
        label_visibility="collapsed"
    )
    st.session_state.current_management_tab = aba_selecionada

    # Conteúdo da tab Biologicos
    if aba_selecionada == "Biológicos":
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
                    
                    if not nome:
                        st.session_state.biologico_form_error = "Nome do produto é obrigatório"
                        return
                        
                    try:
                        # Validar e converter a concentração
                        concentracao_float = convert_scientific_to_float(concentracao) if concentracao else None
                        
                        novo_produto = {
                            "Nome": nome,
                            "Classe": classe,
                            "IngredienteAtivo": ingrediente_ativo,
                            "Formulacao": formulacao,
                            "Dose": dose,
                            "Concentracao": concentracao_float,
                            "Fabricante": fabricante
                        }
                        
                        # Verificar se o produto já existe
                        if nome in dados["biologicos"]["Nome"].values:
                            st.session_state.biologico_form_error = f"Produto '{nome}' já existe!"
                            return
                            
                        # Adicionar à planilha
                        if append_to_sheet(novo_produto, "Biologicos"):
                            # Não precisamos adicionar novamente aos dados locais, pois isso já é feito em append_to_sheet
                            st.session_state.biologico_form_success = True
                            st.session_state.biologico_form_message = f"Produto {nome} adicionado com sucesso!"
                        else:
                            st.session_state.biologico_form_error = "Falha ao adicionar produto"
                            
                    except ValueError as e:
                        st.session_state.biologico_form_error = f"Concentração inválida: {str(e)}"
                    except Exception as e:
                        st.session_state.biologico_form_error = f"Erro ao processar dados: {str(e)}"
                
                with st.form("novo_biologico_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("Nome do Produto", key="biologico_nome")
                        st.selectbox("Classe", options=["Bioestimulante", "Biofungicida", "Bionematicida", "Bioinseticida", "Inoculante"], key="classe_biologico")
                        st.text_input("Ingrediente Ativo", key="biologico_ingrediente")
                    with col2:
                        st.selectbox(
                            "Formulação", 
                            options=["Suspensão concentrada", "Formulação em óleo", "Pó molhável", "Formulação em pó", "Granulado dispersível"],
                            key="biologico_formulacao"
                        )
                        st.number_input("Dose (kg/ha ou litro/ha)", value=0.0, step=1.0, key="biologico_dose")
                        st.text_input(
                            "Concentração em bula (UFC/g ou UFC/ml)", 
                            help="Digite em notação científica (ex: 1e9)",
                            key="biologico_concentracao"
                        )
                    st.text_input("Fabricante", key="biologico_fabricante")
                    
                    submitted = st.form_submit_button("Adicionar Produto")
                    
                    if submitted:
                        submit_biologico_form()
                
                # Mostrar mensagens de sucesso ou erro abaixo do formulário
                if "biologico_form_success" in st.session_state and st.session_state.biologico_form_success:
                    st.success(st.session_state.biologico_form_message)
                    st.session_state.biologico_form_success = False
                    
                if "biologico_form_error" in st.session_state and st.session_state.biologico_form_error:
                    st.error(st.session_state.biologico_form_error)
                    st.session_state.biologico_form_error = ""
            
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
                
                # Garantir colunas esperadas e tipos de dados
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Biologicos"]].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Biologicos"])
                else:
                    # Garantir tipo numérico para Dose
                    df_filtrado['Dose'] = pd.to_numeric(df_filtrado['Dose'], errors='coerce')
                    df_filtrado['Concentracao'] = pd.to_numeric(df_filtrado['Concentracao'], errors='coerce')
                
                # Converter a coluna de concentração para notação científica
                df_filtrado['Concentracao'] = df_filtrado['Concentracao'].apply(lambda x: f"{float(x):.2e}" if pd.notna(x) else '')
                
                # Tabela editável
                with st.form("biologicos_form", clear_on_submit=False):
                    edited_df = st.data_editor(
                        df_filtrado,
                        hide_index=True,
                        num_rows="dynamic",
                        key="biologicos_editor",
                        column_config={
                            "Nome": st.column_config.TextColumn("Produto Biológico"),
                            "Classe": st.column_config.SelectboxColumn("Classe", options=["Bioestimulante", "Biofungicida", "Bionematicida", "Bioinseticida", "Inoculante"]),
                            "IngredienteAtivo": st.column_config.TextColumn("Ingrediente Ativo"),
                            "Formulacao": st.column_config.SelectboxColumn("Formulação", options=["Suspensão concentrada", "Formulação em óleo", "Pó molhável", "Formulação em pó", "Granulado dispersível"]),
                            "Dose": st.column_config.NumberColumn("Dose (kg/ha ou litro/ha)", min_value=0.0, step=0.1, format="%.2f"),
                            "Concentracao": st.column_config.TextColumn(
                                "Concentração em bula (UFC/g ou UFC/ml)",
                                help="Digite em notação científica (ex: 1e9)",
                                validate=r"^[0-9]+\.?[0-9]*[eE][-+]?[0-9]+$"
                            ),
                            "Fabricante": st.column_config.TextColumn("Fabricante")
                        },
                        use_container_width=True,
                        height=400,
                        column_order=COLUNAS_ESPERADAS["Biologicos"],
                        disabled=False
                    )

                    # Converter e validar dados antes de salvar
                    if not edited_df.equals(df_filtrado):
                        try:
                            edited_df_copy = edited_df.copy()
                            
                            # Validar concentrações
                            invalid_rows = []
                            for idx, row in edited_df_copy.iterrows():
                                if pd.notna(row['Concentracao']) and row['Concentracao'] != '':
                                    try:
                                        float(row['Concentracao'])
                                    except ValueError:
                                        invalid_rows.append(row['Nome'])
                            
                            if invalid_rows:
                                st.error(f"Concentração inválida nos produtos: {', '.join(invalid_rows)}. Use notação científica (ex: 1e9)")
                                return
                            
                            # Converter concentrações válidas
                            edited_df_copy['Concentracao'] = edited_df_copy['Concentracao'].apply(
                                lambda x: convert_scientific_to_float(x) if pd.notna(x) and x != '' else None
                            )
                            
                            # Garantir tipo numérico para Dose
                            edited_df_copy['Dose'] = pd.to_numeric(edited_df_copy['Dose'], errors='coerce')
                            
                            edited_df = edited_df_copy
                        except Exception as e:
                            st.error(f"Erro ao processar dados: {str(e)}")
                            return
                
                    # Botão de submit do form
                    submitted = st.form_submit_button("Salvar Alterações", use_container_width=True)
                    
                    if submitted:
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
                                    st.session_state.biologicos_saved = True
                            except Exception as e:
                                st.error(f"Erro ao salvar alterações: {str(e)}")
                
                # Mostrar mensagem de sucesso fora do formulário
                if st.session_state.get("biologicos_saved", False):
                    st.success("Dados salvos com sucesso!")
                    st.session_state.biologicos_saved = False

    # Conteúdo da tab Químicos
    elif aba_selecionada == "Químicos":
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
                                # Não precisamos adicionar novamente aos dados locais, pois isso já é feito em append_to_sheet
                                st.session_state.quimico_form_success = True
                                st.session_state.quimico_form_message = f"Produto {nome} adicionado com sucesso!"
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
                    
                    submitted = st.form_submit_button("Adicionar Produto")
                    
                    if submitted:
                        submit_quimico_form()
                
                # Mostrar mensagens de sucesso ou erro abaixo do formulário
                if "quimico_form_success" in st.session_state and st.session_state.quimico_form_success:
                    st.success(st.session_state.quimico_form_message)
                    st.session_state.quimico_form_success = False
                    
                if "quimico_form_error" in st.session_state and st.session_state.quimico_form_error:
                    st.error(st.session_state.quimico_form_error)
                    st.session_state.quimico_form_error = ""
            
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
                with st.form("quimicos_form"):
                    edited_df = st.data_editor(
                        df_filtrado,
                        num_rows="dynamic",
                        hide_index=True,
                        key="quimicos_editor",
                        column_config={
                            "Nome": st.column_config.TextColumn("Nome do Produto"),
                            "Classe": st.column_config.SelectboxColumn("Classe", options=["Herbicida", "Fungicida", "Inseticida", "Adjuvante", "Nutricional"]),
                            "Fabricante": st.column_config.TextColumn("Fabricante"),
                            "Dose": st.column_config.NumberColumn("Dose (kg/ha ou litro/ha)", min_value=0.0, step=0.1)
                        },
                        use_container_width=True,
                        height=400,
                        column_order=COLUNAS_ESPERADAS["Quimicos"],
                        disabled=False
                    )
                    
                    # Botão para salvar alterações
                    if st.form_submit_button("Salvar Alterações", use_container_width=True):
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
                                    st.session_state.quimicos_saved = True
                            except Exception as e:
                                st.error(f"Erro: {str(e)}")
                
                # Mostrar mensagem de sucesso fora do formulário
                if st.session_state.get("quimicos_saved", False):
                    st.success("Dados salvos com sucesso!")
                    st.session_state.quimicos_saved = False

    # Conteúdo da tab Cálculos
    elif aba_selecionada == "Cálculos":
        st.subheader("Cálculos de Compatibilidade")
        
        if "calculos" not in dados or dados["calculos"].empty:
            st.error("Erro ao carregar dados dos cálculos!")
        else:
            # Opções para o usuário escolher entre registrar ou visualizar
            opcao = st.radio("Escolha uma opção:", ["Novo cálculo", "Cálculos cadastrados"], key="opcao_calc")
            
            if opcao == "Novo cálculo":
                # Inicializar variáveis de estado se não existirem
                if 'calculo_form_submitted' not in st.session_state:
                    st.session_state.calculo_form_submitted = False
                if 'calculo_form_success' not in st.session_state:
                    st.session_state.calculo_form_success = False
                if 'calculo_form_error' not in st.session_state:
                    st.session_state.calculo_form_error = ""
                if 'calculo_quimicos' not in st.session_state:
                    st.session_state.calculo_quimicos = []
                
                # Função para processar o envio do formulário
                def submit_calculo_form():
                    # Obter valores do formulário
                    biologico = st.session_state.calculo_biologico
                    quimicos = st.session_state.calculo_quimicos
                    placa1 = st.session_state.calculo_placa1
                    placa2 = st.session_state.calculo_placa2
                    placa3 = st.session_state.calculo_placa3
                    diluicao = st.session_state.calculo_diluicao
                    dose_registrada = st.session_state.calculo_dose
                    conc_ativo = st.session_state.calculo_conc_ativo
                    volume_calda = st.session_state.calculo_volume_calda
                    
                    if not quimicos or not biologico:
                        st.session_state.calculo_form_submitted = True
                        st.session_state.calculo_form_success = False
                        st.session_state.calculo_form_error = "Selecione os produtos biológico e químico"
                        return
                    
                    # Verificar se quimicos é uma lista ou um único valor
                    if isinstance(quimicos, list):
                        # Concatenar múltiplos químicos com "+"
                        quimicos_str = " + ".join(quimicos)
                    else:
                        quimicos_str = quimicos
                    
                    # Calcular média das placas
                    media_placas = (placa1 + placa2 + placa3) / 3
                    
                    # Calcular concentração obtida
                    conc_obtida = media_placas * diluicao
                    
                    # Calcular concentração esperada
                    conc_esperada = (conc_ativo * dose_registrada) / volume_calda
                    
                    # Calcular razão
                    razao = conc_obtida / conc_esperada if conc_esperada != 0 else 0
                    
                    # Determinar resultado
                    resultado = "Compatível" if razao >= 0.8 else "Incompatível"
                    
                    novo_calculo = {
                        "Biologico": biologico,
                        "Quimico": quimicos_str,
                        "Placa1": placa1,
                        "Placa2": placa2,
                        "Placa3": placa3,
                        "MédiaPlacas": media_placas,
                        "Diluicao": diluicao,
                        "ConcObtida": conc_obtida,
                        "Dose": dose_registrada,
                        "ConcAtivo": conc_ativo,
                        "VolumeCalda": volume_calda,
                        "ConcEsperada": conc_esperada,
                        "Razao": razao,
                        "Resultado": resultado
                    }
                    
                    # Verificar se a combinação já existe
                    combinacao_existente = dados["calculos"][
                        (dados["calculos"]["Biologico"] == biologico) & 
                        (dados["calculos"]["Quimico"].str.contains(quimicos_str, regex=False, na=False))
                    ]
                    
                    if not combinacao_existente.empty:
                        st.session_state.calculo_form_submitted = True
                        st.session_state.calculo_form_success = False
                        st.session_state.calculo_form_error = f"Combinação {biologico} e {quimicos_str} já existe!"
                    else:
                        # Adicionar à planilha
                        if append_to_sheet(novo_calculo, "Calculos"):
                            # Adicionar aos dados locais para evitar recarregamento
                            if "calculos" in st.session_state.local_data:
                                novo_df = pd.DataFrame([novo_calculo])
                                st.session_state.local_data["calculos"] = pd.concat([st.session_state.local_data["calculos"], novo_df], ignore_index=True)
                            
                            st.session_state.calculo_form_submitted = True
                            st.session_state.calculo_form_success = True
                            st.session_state.calculo_form_message = f"Cálculo para '{biologico}' e '{quimicos_str}' adicionado com sucesso!"
                        else:
                            st.session_state.calculo_form_submitted = True
                            st.session_state.calculo_form_success = False
                            st.session_state.calculo_form_error = "Erro ao adicionar cálculo. Tente novamente."
                
                # Formulário para adicionar novo cálculo
                with st.form("calculo_form", clear_on_submit=True):
                    st.subheader("Adicionar Novo Cálculo")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.selectbox(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]['Nome'].unique().tolist()),
                            key="calculo_biologico"
                        )
                        
                        st.number_input("Placa 1", min_value=0.0, format="%.2f", key="calculo_placa1")
                        st.number_input("Placa 2", min_value=0.0, format="%.2f", key="calculo_placa2")
                        st.number_input("Placa 3", min_value=0.0, format="%.2f", key="calculo_placa3")
                        st.number_input("Diluição", min_value=1.0, format="%.2f", key="calculo_diluicao")
                    
                    with col2:
                        # Substituir selectbox por multiselect para permitir múltiplos químicos
                        st.multiselect(
                            "Produtos Químicos",
                            options=sorted(dados["quimicos"]['Nome'].unique().tolist()),
                            default=[],
                            key="calculo_quimicos"
                        )
                        
                        st.number_input("Dose (L/ha)", min_value=0.0, format="%.2f", key="calculo_dose")
                        st.number_input("Concentração do Ativo (%)", min_value=0.0, max_value=100.0, format="%.2f", key="calculo_conc_ativo")
                        st.number_input("Volume de Calda (L/ha)", min_value=0.0, format="%.2f", key="calculo_volume_calda")
                    
                    # Botão de envio
                    submitted = st.form_submit_button("Adicionar Cálculo", on_click=submit_calculo_form)
                
                # Mostrar mensagens de erro ou sucesso
                if st.session_state.get('calculo_form_submitted', False):
                    if st.session_state.get('calculo_form_success', False):
                        st.success(st.session_state.calculo_form_message)
                        # Limpar o estado após exibir a mensagem
                        st.session_state.calculo_form_submitted = False
                        st.session_state.calculo_form_success = False
                    else:
                        st.error(st.session_state.calculo_form_error)
            
            else:  # Visualizar cálculos cadastrados
                # Opções de filtro
                col1, col2 = st.columns(2)
                
                with col1:
                    filtro_biologico = st.selectbox(
                        "Filtrar por Biológico",
                        options=["Todos"] + sorted(dados["calculos"]["Biologico"].unique().tolist()),
                        index=0
                    )
                
                with col2:
                    resultado_options = ["Todos", "Compatível", "Incompatível"]
                    filtro_resultado = st.selectbox(
                        "Filtrar por Resultado",
                        options=resultado_options,
                        index=0
                    )
                
                # Aplicar filtros
                df_filtrado = dados["calculos"].copy()
                
                if filtro_biologico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
                
                if filtro_resultado != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Resultado"] == filtro_resultado]
                
                # Exibir dados filtrados
                if not df_filtrado.empty:
                    # Ordenar por Biologico e Quimico
                    df_filtrado = df_filtrado.sort_values(by=["Biologico", "Quimico"])
                    
                    # Selecionar colunas para exibição
                    colunas_exibir = ["Biologico", "Quimico", "MédiaPlacas", "Razao", "Resultado"]
                    colunas_disponiveis = [col for col in colunas_exibir if col in df_filtrado.columns]
                    
                    # Exibir tabela com os dados filtrados
                    st.dataframe(
                        df_filtrado[colunas_disponiveis],
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Opção para visualizar detalhes
                    with st.expander("Ver Todos os Detalhes"):
                        st.dataframe(
                            df_filtrado,
                            use_container_width=True,
                            hide_index=True
                        )
                else:
                    st.info("Nenhum cálculo encontrado com os filtros selecionados.")

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
                
                # Mostrar o formulário para entrada de dados
                st.subheader("Nova Solicitação de Teste")
                
                # Usar st.form para evitar recarregamentos
                with st.form(key="gerenciamento_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.text_input("Produto Biológico", key="solicitacao_biologico")
                        st.text_input("Nome do solicitante", key="solicitacao_solicitante")
                        
                    with col2:
                        st.text_input("Produto Químico", key="solicitacao_quimico")
                        st.date_input("Data da Solicitação", value=datetime.now(), key="solicitacao_data", format="DD/MM/YYYY")
                    
                    st.text_area("Observações", key="solicitacao_observacoes")
                    
                    # Botão de submit
                    if st.form_submit_button("Adicionar Solicitação", use_container_width=True):
                        # Obter valores do formulário
                        data = st.session_state.solicitacao_data
                        solicitante = st.session_state.solicitacao_solicitante
                        biologico = st.session_state.solicitacao_biologico
                        quimico = st.session_state.solicitacao_quimico
                        observacoes = st.session_state.solicitacao_observacoes
                        
                        # Validar campos obrigatórios
                        if not solicitante or not quimico or not biologico:
                            st.warning("Preencha todos os campos obrigatórios")
                        else:
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
                                    st.session_state.gerenciamento_form_submitted = True
                                    st.session_state.gerenciamento_last_submission = nova_solicitacao
                                    st.experimental_rerun()
                                else:
                                    st.error("Falha ao adicionar solicitação")
            
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
                    df_filtrado = df_filtrado[df_filtrado["Quimico"].str.contains(filtro_quimico, regex=False)]
                
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
                
                with st.form("solicitacoes_form"):
                    edited_df = st.data_editor(
                        df_filtrado,
                        hide_index=True,
                        num_rows="dynamic",
                        key="solicitacoes_editor",
                        column_config={
                            "Data": st.column_config.TextColumn("Data da Solicitação"),
                            "Solicitante": st.column_config.TextColumn("Solicitante"),
                            "Biologico": st.column_config.SelectboxColumn("Produto Biológico", options=sorted(dados["biologicos"]["Nome"].unique().tolist())),
                            "Quimico": st.column_config.SelectboxColumn("Produto Químico", options=sorted(dados["quimicos"]["Nome"].unique().tolist())),
                            "Observacoes": st.column_config.TextColumn("Observações"),
                            "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Análise", "Concluído", "Cancelado"])
                        },
                        use_container_width=True,
                        height=400,
                        column_order=COLUNAS_ESPERADAS["Solicitacoes"],
                        disabled=False
                    )
                    
                    # Botão para salvar alterações
                    if st.form_submit_button("Salvar Alterações", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                df_completo = st.session_state.local_data["solicitacoes"].copy()
                                
                                if filtro_status != "Todos" or filtro_quimico != "Todos" or filtro_biologico != "Todos":
                                    mask = (
                                        (df_completo["Status"] == filtro_status if filtro_status != "Todos" else True) &
                                        (df_completo["Quimico"].str.contains(filtro_quimico, regex=False) if filtro_quimico != "Todos" else True) &
                                        (df_completo["Biologico"] == filtro_biologico if filtro_biologico != "Todos" else True)
                                    )
                                else:
                                    mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                                
                                df_completo = df_completo[~mask]
                                df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                                df_final = df_final.drop_duplicates(subset=["Data", "Solicitante", "Biologico", "Quimico"], keep="last")
                                df_final = df_final.sort_values(by="Data").reset_index(drop=True)
                                
                                st.session_state.local_data["solicitacoes"] = df_final
                                if update_sheet(df_final, "Solicitacoes"):
                                    st.session_state.solicitacoes_saved = True
                            except Exception as e:
                                st.error(f"Erro ao salvar dados: {str(e)}")
                
                # Mostrar mensagem de sucesso fora do formulário
                if st.session_state.get("solicitacoes_saved", False):
                    st.success("Dados salvos com sucesso!")
                    st.session_state.solicitacoes_saved = False

    # Conteúdo da tab Cálculos
    elif aba_selecionada == "Cálculos":
        calculos()

    # Removendo o componente JavaScript para evitar conflitos
    def fix_table_buttons():
        pass

########################################## CÁLCULOS ##########################################

def calculos():
    st.title("🧮 Cálculos de Concentração")
    
    # Carregar dados se não estiverem na session_state
    if 'local_data' not in st.session_state:
        st.session_state.local_data = load_all_data()
    
    # Inicializar variáveis de estado
    if 'concentracao_obtida' not in st.session_state:
        st.session_state.concentracao_obtida = 0.0
    if 'concentracao_esperada' not in st.session_state:
        st.session_state.concentracao_esperada = 0.0
    
    # Seleção de produtos
    st.header("Seleção de Produtos")
    col1, col2 = st.columns([1, 1])

    with col1:
        biologico_selecionado = st.selectbox(
            "Selecione o Produto Biológico",
            options=sorted(st.session_state.local_data["biologicos"]["Nome"].unique()),
            key="calc_biologico"
        )

        # Obter a dose registrada do biológico
        dose_registrada = st.session_state.local_data["biologicos"][
            st.session_state.local_data["biologicos"]["Nome"] == biologico_selecionado
        ]["Dose"].iloc[0]
        
        st.info(f"Dose registrada: {dose_registrada} L/ha ou kg/ha")
    
    with col2:
        quimicos_selecionados = st.multiselect(
            "Selecione os Produtos Químicos",
            options=sorted(st.session_state.local_data["quimicos"]["Nome"].unique()),
            key="calc_quimicos"
        )
    
    if not quimicos_selecionados:
        st.warning("Selecione pelo menos um produto químico para continuar")
        return
    
    st.markdown("---")
    
    st.header("Concentração Obtida")
    st.markdown("Fórmula: Média das placas (colônias) × Diluição × 10")
    
    col1, col2 = st.columns(2)
    with col1:
        placa1 = st.number_input("Placa 1 (colônias)", min_value=0.0, step=1.0, value=float(st.session_state.get('placa1', 0)), key="placa1")
        placa2 = st.number_input("Placa 2 (colônias)", min_value=0.0, step=1.0, value=float(st.session_state.get('placa2', 0)), key="placa2")
        placa3 = st.number_input("Placa 3 (colônias)", min_value=0.0, step=1.0, value=float(st.session_state.get('placa3', 0)), key="placa3")
    
    with col2:
        diluicao = st.number_input("Diluição", min_value=0.0, format="%.2e", value=float(st.session_state.get('diluicao', 1e+6)), key="diluicao")
        
    media_placas = (placa1 + placa2 + placa3) / 3
    concentracao_obtida = media_placas * diluicao * 10
    
    st.session_state.concentracao_obtida = concentracao_obtida
    
    st.info(f"Concentração Obtida: {concentracao_obtida:.2e} UFC/mL")
    
    st.markdown("---")
    
    st.header("Concentração Esperada")
    st.markdown("Fórmula: (Concentração do ativo × Dose) ÷ Volume de calda")
    
    col1, col2 = st.columns(2)
    with col1:
        conc_ativo = st.number_input("Concentração do ativo (UFC/mL)", min_value=0.0, format="%.2e", value=float(st.session_state.get('conc_ativo', 1e+9)), key="conc_ativo")
    
    with col2:
        volume_calda = st.number_input("Volume de calda (L/ha)", min_value=0.1, step=1.0, value=float(st.session_state.get('volume_calda', 100.0)), key="volume_calda")
    
    if volume_calda <= 0:
        st.warning("O Volume de calda deve ser maior que 0 para calcular a Concentração Esperada.")
        return
    
    if biologico_selecionado and volume_calda > 0:
        # Obter a dose registrada do produto biológico
        dose_registrada = st.session_state.local_data["biologicos"][
            st.session_state.local_data["biologicos"]["Nome"] == biologico_selecionado
        ]["Dose"].values[0] if not st.session_state.local_data["biologicos"][
            st.session_state.local_data["biologicos"]["Nome"] == biologico_selecionado
        ].empty else 0
        
        # Calcular concentração esperada
        concentracao_esperada = (conc_ativo * dose_registrada) / volume_calda
        st.session_state.concentracao_esperada = concentracao_esperada
    else:
        concentracao_esperada = 0
        st.session_state.concentracao_esperada = 0
    
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
        - Dose = {dose_registrada:.1f} L/ha (registrada para {biologico_selecionado})
        - Volume de calda = {volume_calda:.1f} L/ha
        - Concentração Esperada = ({conc_ativo:.2e} × {dose_registrada:.1f}) ÷ {volume_calda:.1f} = {concentracao_esperada:.2e} UFC/mL
        
        **3. Compatibilidade**
        - Razão (Obtida/Esperada) = {concentracao_obtida:.2e} ÷ {concentracao_esperada:.2e} = {razao:.2f}
        """)
        
        if 0.8 <= razao <= 1.5:
            st.success(f"✅ COMPATÍVEL - A razão está dentro do intervalo ideal (0,8 a 1,5)")
            st.write("• Siga as recomendações de dosagem de cada produto.")
            st.write(f"• A razão de compatibilidade é {razao}, o que indica boa compatibilidade.")
        elif razao > 1.5:
            st.warning(f"⚠️ ATENÇÃO - A razão está acima de 1,5")
            st.write("• Considere aplicar os produtos separadamente.")
            st.write("• Consulte um agrônomo para alternativas compatíveis.")
            st.write(f"• A razão de compatibilidade é {razao}, o que indica interação positiva.")
        else:
            st.error(f"❌ INCOMPATÍVEL - A razão está abaixo de 0,8")
            st.write("• Considere aplicar os produtos separadamente.")
            st.write("• Consulte um agrônomo para alternativas compatíveis.")
            st.write(f"• A razão de compatibilidade é {razao}, o que indica incompatibilidade.")
    else:
        st.info("Preencha os valores acima para ver o resultado da compatibilidade.")

########################################## SIDEBAR ##########################################

def check_login():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.failed_attempts = 0

    if not st.session_state.authenticated:
        st.title("🔒 Login")
        st.write("É necessário o login para acessar a página de gerenciamento.")
        
        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
            
            if submitted:
                # Aqui você pode adicionar mais usuários e senhas conforme necessário
                valid_credentials = {
                    "adm": "cocal"
                }
                
                if username in valid_credentials and password == valid_credentials[username]:
                    st.session_state.authenticated = True
                    st.session_state.failed_attempts = 0
                    st.success("Login realizado com sucesso!")
                    st.experimental_rerun()
                else:
                    st.session_state.failed_attempts += 1
                    remaining_attempts = 3 - st.session_state.failed_attempts
                    
                    if remaining_attempts > 0:
                        st.error(f"Usuário ou senha incorretos. Você tem mais {remaining_attempts} tentativas.")
                    else:
                        st.error("Número máximo de tentativas excedido. Por favor, tente novamente mais tarde.")
                        st.session_state.failed_attempts = 0
        
        return False
    return True

########################################## EXECUÇÃO ##########################################

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
    
    # Determinar o índice inicial com base na página atual
    current_index = 0 if st.session_state.current_page == "Compatibilidade" else 1
    
    # Usar uma chave única para o radio button para evitar problemas de estado
    menu_option = st.sidebar.radio(
        "Selecione a funcionalidade:",
        ("Compatibilidade", "Gerenciamento"),
        index=current_index,
        key="menu_option_sidebar"
    )
    
    # Atualizar o estado da página atual somente se houver mudança
    if st.session_state.current_page != menu_option:
        st.session_state.current_page = menu_option
        # Forçar recarregamento para aplicar a mudança imediatamente
        st.rerun()

    st.sidebar.markdown("---")
    
    # Adicionar botão de logout se estiver autenticado
    if st.session_state.get('authenticated', False):
        if st.sidebar.button("Sair", key="logout_button"):
            st.session_state.authenticated = False
            st.session_state.current_page = "Compatibilidade"
            st.rerun()

    if menu_option == "Compatibilidade":
        compatibilidade()
    elif menu_option == "Gerenciamento":
        if not st.session_state.get('authenticated', False):
            check_login()
        else:
            gerenciamento()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"Erro ao iniciar a sessão: {str(e)}")