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
        
        <script>
            // Função para prevenir o envio de formulários ao pressionar Enter
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && e.target.tagName.toLowerCase() !== 'textarea') {
                    // Previne o comportamento padrão apenas se não for um textarea
                    e.preventDefault();
                    return false;
                }
            }, true);
        </script>
    """, unsafe_allow_html=True)

local_css()

# Inicialização dos dados locais
if 'local_data' not in st.session_state:
    st.session_state.local_data = {
        "quimicos": pd.DataFrame(),
        "biologicos": pd.DataFrame(),
        "resultados": pd.DataFrame(),
        "solicitacoes": pd.DataFrame(),
        "calculos": pd.DataFrame()
    }

########################################## CONEXÃO GOOGLE SHEETS ##########################################

SHEET_ID = "1lILLXICVkVekkm2EZ-20cLnkYFYvHnb14NL_Or7132U"
SHEET_GIDS = {
    "Biologicos": "1440941690",
    "Quimicos": "885876195",
    "Solicitacoes": "1408097520",
    "Calculos": "0"
}

COLUNAS_ESPERADAS = {
    "Biologicos": ["Nome", "Classe", "IngredienteAtivo", "Formulacao", "Dose", "Concentracao", "Fabricante"],
    "Quimicos": ["Nome", "Classe", "Fabricante", "Dose"],
    "Solicitacoes": ["Data", "Solicitante", "Biologico", "DoseBiologico", "Quimico", "DoseQuimico", "VolumeCalda", "Aplicacao", "Observacoes", "Status"],
    "Calculos": ["Data", "Biologico", "Quimico", "Tempo", "Placa1", "Placa2", "Placa3", "MédiaPlacas", "Diluicao", "ConcObtida", "Dose", "ConcAtivo", "VolumeCalda", "ConcEsperada", "Razao", "Resultado", "Observacao"]
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
                print(f"Erro: Não foi possível conectar ao Google Sheets para a planilha {sheet_name}")
                return None
                
            try:
                spreadsheet = client.open_by_key(SHEET_ID)
                
                # Verificar se a planilha existe usando o GID
                if sheet_name in SHEET_GIDS:
                    gid = SHEET_GIDS[sheet_name]
                    try:
                        sheet = spreadsheet.get_worksheet_by_id(int(gid))
                        if sheet is None:
                            print(f"Erro: Planilha {sheet_name} com GID {gid} não encontrada")
                            return None
                        return sheet
                    except Exception as e:
                        print(f"Erro ao acessar planilha {sheet_name} com GID {gid}: {str(e)}")
                        # Tentar acessar pelo nome como fallback
                        try:
                            sheet = spreadsheet.worksheet(sheet_name)
                            return sheet
                        except:
                            print(f"Erro: Não foi possível acessar a planilha {sheet_name} nem pelo GID nem pelo nome")
                            return None
                else:
                    # Se não tiver GID, tenta acessar pelo nome
                    try:
                        sheet = spreadsheet.worksheet(sheet_name)
                        return sheet
                    except Exception as e:
                        print(f"Erro: Planilha {sheet_name} não encontrada: {str(e)}")
                        return None
                        
            except Exception as e:
                print(f"Erro ao acessar planilha {sheet_name}: {str(e)}")
                return None
                
        except Exception as e:
            print(f"Erro ao conectar com Google Sheets para {sheet_name}: {str(e)}")
            return None
            
    return retry_with_backoff(_get_sheet, max_retries=3, initial_delay=1)

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
                print(f"Erro inesperado: {str(e)}")
                return None
                
            if attempt == max_retries - 1:
                print("Limite de tentativas excedido. Tente novamente mais tarde.")
                return None
                
            # Exponential backoff com jitter
            delay = initial_delay * (2 ** attempt) + uniform(0, 1)
            time.sleep(delay)
            
            # Informar usuário sobre retry
            print(f"Limite de requisições atingido. Tentando novamente em {delay:.1f} segundos...")
            
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
            
            # Tratamento específico para colunas de data
            if 'Data' in df.columns and not df.empty:
                # Tentar converter para o formato padrão DD/MM/YYYY
                try:
                    # Primeiro verificar se já está no formato datetime
                    if pd.api.types.is_datetime64_any_dtype(df['Data']):
                        df['Data'] = df['Data'].dt.strftime('%d/%m/%Y')
                    else:
                        # Tentar diferentes formatos de data
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                            try:
                                temp_dates = pd.to_datetime(df['Data'], format=fmt, errors='coerce')
                                if not temp_dates.isna().all():  # Se conseguiu converter algumas datas
                                    df['Data'] = temp_dates.dt.strftime('%d/%m/%Y')
                                    break
                            except:
                                continue
                except Exception as e:
                    st.warning(f"Erro ao processar datas na planilha {sheet_name}: {str(e)}")
            
            # Verificar colunas essenciais
            required_columns = {
                "Biologicos": ["Nome", "Classe"],
                "Quimicos": ["Nome", "Classe"],
                "Compatibilidades": ["Biologico", "Quimico"],
                "Solicitacoes": ["Quimico", "Biologico"],
                "Calculos": ["Biologico", "Quimico"]
            }
            
            if sheet_name in required_columns:
                for col in required_columns[sheet_name]:
                    if col not in df.columns:
                        st.error(f"Coluna obrigatória '{col}' não encontrada em {sheet_name}")
                        return pd.DataFrame()
                        
            # Garantir que todas as colunas esperadas existam no DataFrame
            if sheet_name in COLUNAS_ESPERADAS:
                for coluna in COLUNAS_ESPERADAS[sheet_name]:
                    if coluna not in df.columns:
                        df[coluna] = ""
                
                # Garantir que o DataFrame tenha apenas as colunas esperadas e na ordem correta
                df = df.reindex(columns=COLUNAS_ESPERADAS[sheet_name])
                        
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Submeter tarefas para carregar cada planilha
            futures = {executor.submit(load_sheet, name): name for name in ["Quimicos", "Biologicos", "Compatibilidades", "Solicitacoes", "Calculos"]}
            
            # Coletar resultados à medida que ficam disponíveis
            for future in concurrent.futures.as_completed(futures):
                sheet_name, df = future.result()
                dados[sheet_name.lower()] = df
    
    # Armazenar dados na sessão com timestamp
    st.session_state.local_data = dados
    st.session_state.data_timestamp = datetime.now()
    
    return dados

def _load_and_validate_sheet(sheet_name):
    """Carrega uma planilha específica e valida suas colunas"""
    try:
        # Usar a função original para carregar os dados
        df = load_sheet_data(sheet_name)
        
        # Verificar se o DataFrame está vazio
        if df is None or df.empty:
            print(f"Aviso: Planilha '{sheet_name}' está vazia ou não pôde ser carregada.")
            # Criar um DataFrame vazio com as colunas esperadas
            if sheet_name in COLUNAS_ESPERADAS:
                return pd.DataFrame(columns=COLUNAS_ESPERADAS[sheet_name])
            return pd.DataFrame()
        
        # Verificar coluna Nome
        if sheet_name in ["Biologicos", "Quimicos"] and "Nome" not in df.columns:
            print(f"Aviso: Coluna 'Nome' não encontrada em {sheet_name}")
            # Criar um DataFrame vazio com as colunas esperadas
            if sheet_name in COLUNAS_ESPERADAS:
                return pd.DataFrame(columns=COLUNAS_ESPERADAS[sheet_name])
            return pd.DataFrame()
            
        # Remover linhas com Nome vazio para planilhas que exigem Nome
        if sheet_name in ["Biologicos", "Quimicos"] and "Nome" in df.columns:
            df = df[df["Nome"].notna()]
        
        # Converter colunas de data
        if sheet_name in ["Compatibilidades", "Solicitacoes", "Calculos"] and "Data" in df.columns:
            try:
                df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
                df["Data"] = df["Data"].dt.strftime('%d/%m/%Y')
            except Exception as e:
                print(f"Aviso: Erro ao processar datas na planilha {sheet_name}: {str(e)}")
        
        # Garantir que todas as colunas esperadas existam no DataFrame
        if sheet_name in COLUNAS_ESPERADAS:
            for coluna in COLUNAS_ESPERADAS[sheet_name]:
                if coluna not in df.columns:
                    df[coluna] = ""
            
            # Garantir que o DataFrame tenha apenas as colunas esperadas e na ordem correta
            df = df.reindex(columns=COLUNAS_ESPERADAS[sheet_name])
            
            # Garantir que não há valores None/NaN nas colunas de texto
            for col in df.columns:
                df[col] = df[col].fillna("")
        
        return df
    except Exception as e:
        print(f"Erro ao carregar planilha {sheet_name}: {str(e)}")
        # Criar um DataFrame vazio com as colunas esperadas
        if sheet_name in COLUNAS_ESPERADAS:
            return pd.DataFrame(columns=COLUNAS_ESPERADAS[sheet_name])
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

    # Obter dados da planilha de cálculos
    biologicos_unicos = []
    quimicos_por_biologico = {}
    
    # Verificar se a planilha de cálculos tem dados
    if "calculos" in dados and not dados["calculos"].empty:
        # Verificar se a coluna "Biologico" existe
        if "Biologico" in dados["calculos"].columns:
            # Obter lista de biológicos únicos
            biologicos_unicos = sorted(dados["calculos"]["Biologico"].unique())
            
            # Para cada biológico, obter os químicos testados
            for bio in biologicos_unicos:
                # Filtrar os resultados de cálculos para o biológico selecionado
                resultados_bio = dados["calculos"][
                    dados["calculos"]["Biologico"] == bio
                ]
                
                # Extrair todos os químicos testados com este biológico
                if not resultados_bio.empty and "Quimico" in resultados_bio.columns:
                    quimicos_testados = []
                    for quimico_entry in resultados_bio["Quimico"]:
                        # Lidar com entradas que podem ter formato "quimico1 + quimico2"
                        if isinstance(quimico_entry, str):
                            quimicos_testados.append(quimico_entry)
                    
                    # Remover duplicatas e ordenar
                    quimicos_por_biologico[bio] = sorted(set(quimicos_testados))

    with col1:
        biologico = st.selectbox(
            "Produto Biológico",
            options=biologicos_unicos if biologicos_unicos else sorted(dados["biologicos"]['Nome'].unique()),
            index=None,
            key="compatibilidade_biologico"
        )

    # Filtrar químicos com base no biológico selecionado
    quimicos_disponiveis = []
    if biologico and biologico in quimicos_por_biologico:
        quimicos_disponiveis = quimicos_por_biologico[biologico]
    
    with col2:
        quimico = st.selectbox(
            "Produto Químico",
            options=quimicos_disponiveis if biologico and quimicos_disponiveis else [],
            index=None,
            key="compatibilidade_quimico"
        )
    
    if biologico and quimico:
        # Verificar se a planilha de cálculos tem dados
        if "calculos" in dados and not dados["calculos"].empty and "Biologico" in dados["calculos"].columns and "Quimico" in dados["calculos"].columns:
            # Procurar na planilha de Resultados usando os nomes
            resultado_existente = dados["calculos"][
                (dados["calculos"]["Biologico"] == biologico) & 
                (dados["calculos"]["Quimico"] == quimico)
            ]
            
            if not resultado_existente.empty:
                # Ordenar por data (mais recente primeiro)
                resultado_existente['Data'] = pd.to_datetime(resultado_existente['Data'], format='%d/%m/%Y', errors='coerce')
                resultado_existente = resultado_existente.sort_values('Data', ascending=False)
                
                # Mostrar apenas o resultado mais recente
                resultado = resultado_existente.iloc[0]
                compativel = "Compatível" in str(resultado["Resultado"])
                
                if compativel:
                    st.markdown(f"""
                        <div class="resultado compativel">
                        {resultado["Resultado"]}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                        <div class="resultado incompativel">
                        {resultado["Resultado"]}
                        </div>
                        """, unsafe_allow_html=True)
                
                # Mostrar detalhes do teste
                with st.expander("Ver detalhes do teste"):
                    def formatar(valor, tipo="float"):
                        if pd.isna(valor) or valor == "":
                            return "-"
                        try:
                            valor = float(valor)  # Converte string para número, se necessário
                        except ValueError:
                            return valor  # Retorna o próprio valor se não for um número

                        if tipo == "int":
                            return f"{int(valor)}"
                        elif tipo == "cientifico":
                            return f"{valor:.2e}"
                        # Garantir que valores pequenos como 0.05 sejam exibidos corretamente
                        return f"{valor:.2f}"
                    
                    # Exibir campos na ordem especificada com unidades de medida
                    st.write(f"**Data:** {resultado['Data'].strftime('%d/%m/%Y')}")
                    st.write(f"**Biologico:** {resultado['Biologico']}")
                    st.write(f"**Quimico:** {resultado['Quimico']}")
                    st.write(f"**Tempo:** {resultado['Tempo']} horas")
                    
                    # Razão
                    if "Razao" in resultado:
                        st.write(f"**Razao:** {formatar(resultado['Razao'], 'float')}")                 
                    # Resultado final
                    st.write(f"**Resultado:** {resultado['Resultado']}")
                    
                    # Observação (se existir)
                    if "Observacao" in resultado and not pd.isna(resultado['Observacao']) and str(resultado['Observacao']).strip() != "":
                        st.write(f"**Observação:** {resultado['Observacao']}")
                    
            else:
                # Mostrar aviso de que não existe compatibilidade cadastrada
                st.markdown("""
                        <div class="resultado naotestado">
                        Teste não realizado!
                        Solicite um novo teste.
                    </div>
                    """, unsafe_allow_html=True)
        else:
            # Mostrar aviso de que não existem dados de compatibilidade
            st.markdown("""
                    <div class="resultado naotestado">
                    Não há dados de compatibilidade disponíveis.
                    Solicite um novo teste.
                </div>
                """, unsafe_allow_html=True)
    
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

    # Função para processar o envio do formulário
    def submit_form():
        # Obter valores do formulário
        data = st.session_state.data_solicitacao
        solicitante = st.session_state.solicitante
        biologico_input = st.session_state.biologico_input
        dose_biologico = st.session_state.dose_biologico
        quimico_input = st.session_state.quimico_input
        dose_quimico = st.session_state.dose_quimico
        volume_calda = st.session_state.volume_calda
        aplicacao = st.session_state.aplicacao
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
            "Data": data.strftime("%d/%m/%Y"),
            "Solicitante": solicitante,
            "Biologico": biologico_input,
            "DoseBiologico": dose_biologico,
            "Quimico": quimico_input,
            "DoseQuimico": dose_quimico,
            "VolumeCalda": volume_calda,
            "Aplicacao": aplicacao,
            "Observacoes": observacoes,
            "Status": "Pendente"
        }

        if append_to_sheet(nova_solicitacao, "Solicitacoes"):
            st.session_state.form_submitted_successfully = True
            st.session_state.solicitar_novo_teste = False
            st.session_state.last_submission = nova_solicitacao
            
            # Recarregar os dados diretamente do Google Sheets para evitar duplicações
            load_all_data()
            
            # Mostrar mensagem de sucesso imediatamente
            st.success("Solicitação de novo teste enviada com sucesso!")
            # Forçar recarregamento da página para atualizar os dados
            st.rerun()
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
            st.text_input("Dose do Produto Biológico (kg/ha ou L/ha)", key="dose_biologico")
            st.text_input("Nome do solicitante", key="solicitante")
            st.text_input("Volume de Calda (L/ha)", key="volume_calda")
        
        with col2:
            st.text_input("Nome do Produto Químico", value=default_quimico, key="quimico_input")
            st.text_input("Dose do Produto Químico (kg/ha ou L/ha)", key="dose_quimico")
            st.date_input("Data da Solicitação", value=datetime.now(), key="data_solicitacao", format="DD/MM/YYYY")
            st.text_input("Aplicação", key="aplicacao")
            
        st.text_area("Observações", key="observacoes")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.form_submit_button("Enviar Solicitação"):
                submit_form()
        with col2:
            if st.form_submit_button("Cancelar"):
                st.session_state.solicitar_novo_teste = False

########################################## GERENCIAMENTO ##########################################

def gerenciamento():
    st.title("⚙️ Gerenciamento")

    # Inicialização dos dados locais
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
                            options=["Suspensão concentrada", "Formulação em óleo", "Pó molhável", "Granulado dispersível"],
                            key="biologico_formulacao"
                        )
                        st.number_input("Dose (kg/ha ou litro/ha)", value=0.0, step=0.01, format="%.3f", key="biologico_dose")
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
                    # Garantir que todas as colunas numéricas são do tipo correto
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
                            "Formulacao": st.column_config.SelectboxColumn("Formulação", options=["Suspensão concentrada", "Formulação em óleo", "Pó molhável", "Granulado dispersível"]),
                            "Dose": st.column_config.NumberColumn("Dose (kg/ha ou litro/ha)", min_value=0.0, step=0.01, format="%.3f"),
                            "Concentracao": st.column_config.TextColumn(
                                "Concentração em bula (UFC/g ou UFC/ml)",
                                help="Digite em notação científica (ex: 1e9)",
                                validate="^[0-9]+\\.?[0-9]*[eE][-+]?[0-9]+$"
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
                        st.number_input("Dose (kg/ha ou litro/ha)", value=0.0, step=0.1, format="%.2f", key="quimico_dose")
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
                            "Dose": st.column_config.NumberColumn("Dose (kg/ha ou litro/ha)", min_value=0.0, step=0.01, format="%.3f")
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
                    st.write(f"**Dose do Produto Biológico:** {st.session_state.gerenciamento_last_submission.get('DoseBiologico', '')}")
                    st.write(f"**Produto Químico:** {st.session_state.gerenciamento_last_submission.get('Quimico', '')}")
                    st.write(f"**Dose do Produto Químico:** {st.session_state.gerenciamento_last_submission.get('DoseQuimico', '')}")
                    st.write(f"**Volume de Calda:** {st.session_state.gerenciamento_last_submission.get('VolumeCalda', '')}")
                    st.write(f"**Aplicação:** {st.session_state.gerenciamento_last_submission.get('Aplicacao', '')}")
                    
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
                        st.text_input("Dose do Produto Biológico", key="solicitacao_dose_biologico")
                        st.text_input("Nome do solicitante", key="solicitacao_solicitante")
                        st.text_input("Volume de Calda", key="solicitacao_volume_calda")
                        
                    with col2:
                        st.text_input("Produto Químico", key="solicitacao_quimico")
                        st.text_input("Dose do Produto Químico", key="solicitacao_dose_quimico")
                        st.date_input("Data da Solicitação", value=datetime.now(), key="solicitacao_data", format="DD/MM/YYYY")
                        st.text_input("Aplicação", key="solicitacao_aplicacao")
                    
                    st.text_area("Observações", key="solicitacao_observacoes")
                    
                    # Botão de submit
                    if st.form_submit_button("Adicionar Solicitação", use_container_width=True):
                        # Obter valores do formulário
                        data = st.session_state.solicitacao_data
                        solicitante = st.session_state.solicitacao_solicitante
                        biologico = st.session_state.solicitacao_biologico
                        dose_biologico = st.session_state.solicitacao_dose_biologico
                        quimico = st.session_state.solicitacao_quimico
                        dose_quimico = st.session_state.solicitacao_dose_quimico
                        volume_calda = st.session_state.solicitacao_volume_calda
                        aplicacao = st.session_state.solicitacao_aplicacao
                        observacoes = st.session_state.solicitacao_observacoes
                        
                        # Validar campos obrigatórios
                        if not solicitante or not quimico or not biologico:
                            st.warning("Preencha todos os campos obrigatórios")
                        else:
                            # Preparar dados da solicitação
                            nova_solicitacao = {
                                "Data": data.strftime("%d/%m/%Y"),
                                "Solicitante": solicitante,
                                "Biologico": biologico,
                                "DoseBiologico": dose_biologico,
                                "Quimico": quimico,
                                "DoseQuimico": dose_quimico,
                                "VolumeCalda": volume_calda,
                                "Aplicacao": aplicacao,
                                "Observacoes": observacoes,
                                "Status": "Pendente"
                            }
                            
                            # Adicionar à planilha
                            with st.spinner("Salvando nova solicitação..."):
                                if append_to_sheet(nova_solicitacao, "Solicitacoes"):
                                    st.session_state.gerenciamento_form_submitted = True
                                    st.session_state.gerenciamento_last_submission = nova_solicitacao
                                    st.rerun()
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
                    df_filtrado = df_filtrado[df_filtrado["Quimico"] == filtro_quimico]
                
                # Garantir colunas esperadas
                df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
                else:
                    # Garantir que todas as colunas existam no DataFrame
                    for coluna in COLUNAS_ESPERADAS["Solicitacoes"]:
                        if coluna not in df_filtrado.columns:
                            df_filtrado[coluna] = ""
                
                # Garantir que a coluna Data seja do tipo correto
                if 'Data' in df_filtrado.columns:
                    # Converter a coluna de data para datetime
                    try:
                        df_filtrado["Data"] = pd.to_datetime(df_filtrado["Data"], format="%d/%m/%Y", errors='coerce')
                    except Exception as e:
                        st.warning(f"Alguns valores de data podem não estar no formato correto: {str(e)}")
                
                # Tabela editável com ordenação por Data
                if not df_filtrado.empty:
                    df_filtrado = df_filtrado.sort_values(by="Data", ascending=False).reset_index(drop=True)
                
                with st.form("solicitacoes_form"):
                    # Garantir que todas as colunas estejam presentes antes de exibir
                    for col in COLUNAS_ESPERADAS["Solicitacoes"]:
                        if col not in df_filtrado.columns:
                            df_filtrado[col] = ""
                    
                    # Garantir que o DataFrame tenha apenas as colunas esperadas e na ordem correta
                    df_filtrado = df_filtrado[COLUNAS_ESPERADAS["Solicitacoes"]]
                    
                    # Definir ordem explícita das colunas para exibição
                    column_order = ["Data", "Solicitante", "Biologico", "DoseBiologico", "Quimico", "DoseQuimico", "VolumeCalda", "Aplicacao", "Observacoes", "Status"]
                    
                    edited_df = st.data_editor(
                        df_filtrado,
                        hide_index=True,
                        num_rows="dynamic",
                        key="solicitacoes_editor",
                        column_config={
                            "Data": st.column_config.DateColumn("Data da Solicitação", format="DD/MM/YYYY"),
                            "Solicitante": st.column_config.TextColumn("Solicitante"),
                            "Biologico": st.column_config.TextColumn("Produto Biológico"),
                            "DoseBiologico": st.column_config.TextColumn("Dose do Produto Biológico"),
                            "Quimico": st.column_config.TextColumn("Produto Químico"),
                            "DoseQuimico": st.column_config.TextColumn("Dose do Produto Químico"),
                            "VolumeCalda": st.column_config.TextColumn("Volume de Calda"),
                            "Aplicacao": st.column_config.TextColumn("Aplicação"),
                            "Observacoes": st.column_config.TextColumn("Observações"),
                            "Status": st.column_config.SelectboxColumn("Status", options=["Pendente", "Em Análise", "Concluído", "Cancelado"])
                        },
                        use_container_width=True,
                        height=400,
                        column_order=column_order,
                        disabled=False
                    )
                    
                    # Botão para salvar alterações
                    if st.form_submit_button("Salvar Alterações", use_container_width=True):
                        with st.spinner("Salvando dados..."):
                            try:
                                # Garantir que todas as colunas no DataFrame editado estão preenchidas
                                for col in COLUNAS_ESPERADAS["Solicitacoes"]:
                                    if col not in edited_df.columns:
                                        edited_df[col] = ""
                                
                                # Garantir que o DataFrame editado tenha as colunas na ordem correta
                                edited_df = edited_df[COLUNAS_ESPERADAS["Solicitacoes"]]
                                
                                # Recarregar os dados mais recentes do Google Sheets
                                load_all_data()
                                df_completo = st.session_state.local_data["solicitacoes"].copy()
                                
                                # Remover os registros que foram editados para evitar duplicações
                                if filtro_status != "Todos" or filtro_quimico != "Todos" or filtro_biologico != "Todos":
                                    mask = (
                                        (df_completo["Status"] == filtro_status if filtro_status != "Todos" else True) &
                                        (df_completo["Quimico"] == filtro_quimico if filtro_quimico != "Todos" else True) &
                                        (df_completo["Biologico"] == filtro_biologico if filtro_biologico != "Todos" else True)
                                    )
                                    df_completo = df_completo[~mask]
                                else:
                                    # Se não há filtros, substituir completamente os dados
                                    df_completo = pd.DataFrame(columns=COLUNAS_ESPERADAS["Solicitacoes"])
                                
                                # Combinar os dados originais com os editados
                                df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                                df_final = df_final.drop_duplicates(subset=["Data", "Solicitante", "Biologico", "Quimico"], keep="last")
                                df_final = df_final.sort_values(by="Data").reset_index(drop=True)
                                
                                # Atualizar os dados locais e no Google Sheets
                                if update_sheet(df_final, "Solicitacoes"):
                                    st.session_state.local_data["solicitacoes"] = df_final
                                    st.success("Dados salvos com sucesso!")
                                    # Recarregar a página para mostrar os dados atualizados
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao salvar dados: {str(e)}")
                
                # Mostrar mensagem de sucesso fora do formulário
                if st.session_state.get("solicitacoes_saved", False):
                    st.success("Dados salvos com sucesso!")
                    st.session_state.solicitacoes_saved = False

    # Conteúdo da tab Cálculos
    elif aba_selecionada == "Cálculos":
        st.subheader("Cálculos de Compatibilidade")
        
        if "calculos" not in dados or dados["calculos"].empty:
            st.error("Erro ao carregar dados dos cálculos!")
        else:
            # Opções para o usuário escolher entre realizar cálculos ou visualizar
            opcao = st.radio("Escolha uma opção:", ["Novo cálculo", "Testes realizados"], key="opcao_calculos")
            
            if opcao == "Novo cálculo":
                calculos()
            else:  # Visualizar cálculos realizados
                # Filtros para a tabela
                col1, col2 = st.columns(2)
                with col1:
                    filtro_biologico = st.selectbox(
                        "🔍 Filtrar por Biológico",
                        options=["Todos"] + sorted(dados["calculos"]['Biologico'].unique().tolist()),
                        index=0,
                        key="filtro_biologico_calculos"
                    )
                with col2:
                    filtro_resultado = st.selectbox(
                        "🔍 Filtrar por Resultado",
                        options=["Todos", "Compatível", "Compatível (Interação Positiva)", "Incompatível"],
                        index=0,
                        key="filtro_resultado_calculos"
                    )

                # Aplicar filtro
                df_filtrado = dados["calculos"].copy()
                if filtro_biologico != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Biologico"] == filtro_biologico]
                if filtro_resultado != "Todos":
                    df_filtrado = df_filtrado[df_filtrado["Resultado"] == filtro_resultado]
                
                # Garantir colunas esperadas
                colunas_calculos = ["Data", "Biologico", "Quimico", "Tempo", "Placa1", "Placa2", "Placa3", 
                                   "MédiaPlacas", "Diluicao", "ConcObtida", "Dose", "ConcAtivo", 
                                   "VolumeCalda", "ConcEsperada", "Razao", "Resultado", "Observacao"]
                
                # Garantir que todas as colunas existam no DataFrame
                for coluna in colunas_calculos:
                    if coluna not in df_filtrado.columns:
                        df_filtrado[coluna] = ""
                
                df_filtrado = df_filtrado[colunas_calculos].copy()
                
                if df_filtrado.empty:
                    df_filtrado = pd.DataFrame(columns=colunas_calculos)
                else:
                    # Garantir que todas as colunas numéricas são do tipo correto
                    for col in ["Placa1", "Placa2", "Placa3", "MédiaPlacas", "Diluicao", 
                               "ConcObtida", "Dose", "ConcAtivo", "VolumeCalda", "ConcEsperada", "Razao"]:
                        if col in df_filtrado.columns:
                            df_filtrado[col] = pd.to_numeric(df_filtrado[col], errors='coerce')
                
                # Converter a coluna de data para datetime
                if "Data" in df_filtrado.columns and not df_filtrado["Data"].empty:
                    try:
                        df_filtrado["Data"] = pd.to_datetime(df_filtrado["Data"], format="%d/%m/%Y", errors='coerce')
                    except Exception as e:
                        st.warning(f"Alguns valores de data podem não estar no formato correto: {str(e)}")
                
                # Tabela editável
                with st.form("calculos_form", clear_on_submit=False):
                    edited_df = st.data_editor(
                        df_filtrado,
                        hide_index=True,
                        num_rows="dynamic",
                        key="calculos_editor",
                        column_config={
                            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                            "Biologico": st.column_config.TextColumn("Produto Biológico"),
                            "Quimico": st.column_config.TextColumn("Produto Químico"),
                            "Tempo": st.column_config.NumberColumn("Tempo (horas)", min_value=0, step=1),
                            "Placa1": st.column_config.NumberColumn("Placa 1", min_value=0, format="%d"),
                            "Placa2": st.column_config.NumberColumn("Placa 2", min_value=0, format="%d"),
                            "Placa3": st.column_config.NumberColumn("Placa 3", min_value=0, format="%d"),
                            "MédiaPlacas": st.column_config.NumberColumn("Média Placas", min_value=0, format="%.1f"),
                            "Diluicao": st.column_config.NumberColumn("Diluição", format="%.2e"),
                            "ConcObtida": st.column_config.NumberColumn("Conc. Obtida", format="%.2e"),
                            "Dose": st.column_config.NumberColumn("Dose", min_value=0, format="%.2f"),
                            "ConcAtivo": st.column_config.NumberColumn("Conc. Ativo", format="%.2e"),
                            "VolumeCalda": st.column_config.NumberColumn("Volume Calda", min_value=0, format="%.1f"),
                            "ConcEsperada": st.column_config.NumberColumn("Conc. Esperada", format="%.2e"),
                            "Razao": st.column_config.NumberColumn("Razão", format="%.2f"),
                            "Resultado": st.column_config.SelectboxColumn(
                                "Resultado", 
                                options=["Compatível", "Compatível (Interação Positiva)", "Incompatível"]
                            ),
                            "Observacao": st.column_config.TextColumn("Observação")
                        },
                        use_container_width=True,
                        height=400,
                        column_order=colunas_calculos,
                        disabled=False
                    )
                    
                    # Botão de submit do form
                    submitted = st.form_submit_button("Salvar Alterações", use_container_width=True)
                    
                    if submitted:
                        with st.spinner("Salvando dados..."):
                            try:
                                df_completo = st.session_state.local_data["calculos"].copy()
                                
                                # Identificar registros a serem atualizados com base nos filtros
                                if filtro_biologico != "Todos" or filtro_resultado != "Todos":
                                    mask = (
                                        (df_completo["Biologico"] == filtro_biologico if filtro_biologico != "Todos" else True) &
                                        (df_completo["Resultado"] == filtro_resultado if filtro_resultado != "Todos" else True)
                                    )
                                else:
                                    mask = pd.Series([True]*len(df_completo), index=df_completo.index)
                                
                                # Remover registros que serão substituídos
                                df_completo = df_completo[~mask]
                                
                                # Concatenar com os novos registros editados
                                df_final = pd.concat([df_completo, edited_df], ignore_index=True)
                                
                                # Atualizar a planilha
                                sucesso = update_sheet(df_final, "Calculos")
                                
                                if sucesso:
                                    # Atualizar dados locais
                                    st.session_state.local_data["calculos"] = df_final
                                    st.success("Dados salvos com sucesso!")
                                else:
                                    st.error("Erro ao registrar o resultado. Tente novamente.")
                            except Exception as e:
                                st.error(f"Erro ao processar dados: {str(e)}")
    else:
        st.info("Preencha os valores acima para ver o resultado da compatibilidade.")

########################################## CÁLCULOS ##########################################

def calculos():
    # Carregar dados se não estiverem na session_state
    dados = load_all_data()
    
    # Inicializar variáveis de estado
    if 'concentracao_obtida' not in st.session_state:
        st.session_state.concentracao_obtida = 0.0
    if 'concentracao_esperada' not in st.session_state:
        st.session_state.concentracao_esperada = 0.0
    if 'calculo_resultado' not in st.session_state:
        st.session_state.calculo_resultado = None
    if 'observacao_calculo' not in st.session_state:
        st.session_state.observacao_calculo = ""
    
    # Seleção de produtos
    st.subheader("Seleção de Produtos")
    col1, col2 = st.columns(2)
    
    with col1:
        biologico_selecionado = st.selectbox(
            "Selecione o Produto Biológico",
            options=sorted(dados["biologicos"]["Nome"].unique()),
            key="calc_biologico"
        )

        # Obter a dose registrada do biológico
        dose_registrada = dados["biologicos"][
            dados["biologicos"]["Nome"] == biologico_selecionado
        ]["Dose"].iloc[0]
        
        st.info(f"Dose registrada: {dose_registrada} L/ha ou kg/ha")
    
    with col2:
        # Limitar a seleção a no máximo 3 produtos químicos
        quimicos_selecionados = st.multiselect(
            "Selecione os Produtos Químicos (máximo 3)",
            options=sorted(dados["quimicos"]["Nome"].unique()),
            key="calc_quimicos",
            max_selections=3
        )
    
    if not quimicos_selecionados:
        st.warning("Selecione pelo menos um produto químico para continuar")
        return
    
    if len(quimicos_selecionados) > 3:
        st.warning("Selecione no máximo 3 produtos químicos")
        return
    
    # Verificar se já existe um cálculo com o mesmo biológico e químicos
    calculos_existentes = dados["calculos"]
    if not calculos_existentes.empty:
        # Formatar os químicos selecionados como uma string para comparação
        quimicos_texto = " + ".join(quimicos_selecionados)
        
        # Filtrar por biológico e químico
        filtro_biologico = calculos_existentes["Biologico"] == biologico_selecionado
        filtro_quimico = calculos_existentes["Quimico"] == quimicos_texto
        registros_duplicados = calculos_existentes[filtro_biologico & filtro_quimico]
        
        if not registros_duplicados.empty:
            st.error(f"Já existe um registro de cálculo para {biologico_selecionado} com os mesmos produtos químicos. Selecione outros produtos para continuar.")
            return
    
    # Adicionar campos de Data e Tempo
    st.markdown("---")
    st.subheader("Informações")
    
    col1, col2 = st.columns(2)
    with col1:
        data_teste = st.date_input(
            "Data do Teste", 
            value=datetime.now(), 
            key="data_teste", 
            format="DD/MM/YYYY"
        )
    
    with col2:
        tempo_exposicao = st.number_input(
            "Tempo máximo testado em calda (horas)", 
            min_value=0, 
            step=1, 
            value=0, 
            key="tempo_exposicao"
        )
    
    st.markdown("---")
    
    st.header("Concentração Obtida")
    st.markdown("Fórmula: Média das placas (colônias) × Diluição × 10")
    
    col1, col2 = st.columns(2)
    with col1:
        placa1 = st.number_input("Placa 1 (colônias)", min_value=0, step=1, value=int(st.session_state.get('placa1', 0)), key="placa1")
        placa2 = st.number_input("Placa 2 (colônias)", min_value=0, step=1, value=int(st.session_state.get('placa2', 0)), key="placa2")
        placa3 = st.number_input("Placa 3 (colônias)", min_value=0, step=1, value=int(st.session_state.get('placa3', 0)), key="placa3")
    
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
        volume_calda = st.number_input("Volume de calda (L/ha)", min_value=0, step=1, value=int(st.session_state.get('volume_calda', 100)), key="volume_calda")
    
    if volume_calda <= 0:
        st.warning("O Volume de calda deve ser maior que 0 para calcular a Concentração Esperada.")
        return
    
    concentracao_esperada = (conc_ativo * float(dose_registrada)) / volume_calda
    st.session_state.concentracao_esperada = concentracao_esperada
    
    st.info(f"Concentração Esperada: {concentracao_esperada:.2e} UFC/mL")
    
    st.markdown("---")
    
    # Campo para observações
    observacao = st.text_area("Observação", key="observacao_calculo")
    
    st.markdown("---")
    
    st.header("Resultado Final")
    
    if st.session_state.concentracao_obtida > 0 and st.session_state.concentracao_esperada > 0:
        razao = st.session_state.concentracao_obtida / st.session_state.concentracao_esperada
        
        razao_formatada = round(razao, 2)  # Arredondar para 2 casas decimais
        
        st.write("**Detalhamento dos Cálculos:**")
        st.write(f"""
        **1. Concentração Obtida**
        - Média das placas = ({placa1} + {placa2} + {placa3}) ÷ 3 = {media_placas:.1f}
        - Diluição = {diluicao:.2e}
        - Concentração Obtida = {media_placas:.1f} × {diluicao:.2e} × 10 = {concentracao_obtida:.2e} UFC/mL
        
        **2. Concentração Esperada**
        - Concentração do ativo = {conc_ativo:.2e} UFC/mL
        - Dose = {dose_registrada} L/ha (registrada para {biologico_selecionado})
        - Volume de calda = {volume_calda:.1f} L/ha
        - Concentração Esperada = ({conc_ativo:.2e} × {dose_registrada}) ÷ {volume_calda:.1f} = {concentracao_esperada:.2e} UFC/mL
        
        **3. Compatibilidade**
        - Razão (Obtida/Esperada) = {concentracao_obtida:.2e} ÷ {concentracao_esperada:.2e} = {razao_formatada:.2f}
        """)
        
        resultado_texto = ""
        if 0.8 <= razao <= 1.5:
            resultado_texto = "Compatível"
            st.success(f"✅ COMPATÍVEL - A razão está dentro do intervalo ideal (0,8 a 1,5)")

        elif razao > 1.5:
            resultado_texto = "Incompatível"
            st.warning(f"⚠️ INCOMPATÍVEL - A razão está acima de 1,5")

        else:
            resultado_texto = "Incompatível"
            st.error(f"❌ INCOMPATÍVEL - A razão está abaixo de 0,8")

        st.session_state.calculo_resultado = resultado_texto
        
        # Botão para registrar o resultado na planilha
        if st.button("Registrar Resultado na Planilha", key="registrar_resultado"):
            # Formatar a data no formato DD/MM/YYYY
            data_formatada = data_teste.strftime("%d/%m/%Y")
            
            # Formatar os químicos selecionados como uma string
            quimicos_texto = " + ".join(quimicos_selecionados)
            
            # Registrar na planilha de cálculos
            novo_registro = {
                "Data": data_formatada,
                "Biologico": biologico_selecionado,
                "Quimico": quimicos_texto,
                "Tempo": int(tempo_exposicao),
                "Placa1": int(placa1),
                "Placa2": int(placa2),
                "Placa3": int(placa3),
                "MédiaPlacas": round(float(media_placas), 2),
                "Diluicao": "{:.2e}".format(float(diluicao)),
                "ConcObtida": "{:.2e}".format(float(concentracao_obtida)),
                "Dose": round(float(dose_registrada), 2),
                "ConcAtivo": "{:.2e}".format(float(conc_ativo)),
                "VolumeCalda": int(volume_calda),
                "ConcEsperada": "{:.2e}".format(float(concentracao_esperada)),
                "Razao": round(float(razao), 2),
                "Resultado": resultado_texto,
                "Observacao": st.session_state.get('observacao_calculo', "")
            }
            
            # Adicionar à planilha
            sucesso = append_to_sheet(novo_registro, "Calculos")
            
            if sucesso:
                st.success("Resultado registrado com sucesso na planilha de cálculos!")
                # Recarregar dados para atualizar a interface
                load_all_data()
            else:
                st.error("Erro ao registrar o resultado. Tente novamente.")
    else:
        st.warning("Preencha os valores acima para ver o resultado da compatibilidade.")

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
                    st.rerun()
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
            "solicitacoes": pd.DataFrame(),
            "calculos": pd.DataFrame()
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
        st.error(f"Erro ao processar dados: {str(e)}")