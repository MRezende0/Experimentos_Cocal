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

def retry_with_backoff(func, max_retries=3, initial_delay=5):
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
                
            delay = initial_delay * (2 ** attempt) + uniform(2, 5)
            st.warning(f"Limite temporário excedido. Tentando novamente em {delay:.1f} segundos...")
            time.sleep(delay)
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
    try:
        # Converter valores para tipos nativos do Python
        converted_data = {
            k: int(v) if isinstance(v, (np.int64, np.int32)) else 
               str(v) if isinstance(v, (np.str_, pd.Timestamp)) else 
               v for k, v in data_dict.items()
        }
        
        worksheet = get_worksheet(sheet_name)
        if worksheet:
            # Converter para lista mantendo a ordem das colunas
            headers = worksheet.row_values(1)
            row = [converted_data.get(header, "") for header in headers]
            
            # Adicionar com retry para lidar com limites de quota
            def _append():
                worksheet.append_row(row)
                return True
                
            return retry_with_backoff(_append)
        return False
    except Exception as e:
        st.error(f"Erro ao adicionar dados: {str(e)}")
        return False

def update_sheet(df, sheet_name: str) -> bool:
    def _update():
        try:
            worksheet = get_worksheet(sheet_name)
            if not worksheet:
                return False
                
            # Garantir que df seja um DataFrame
            if not isinstance(df, pd.DataFrame):
                st.error(f"Erro: O objeto passado para atualização não é um DataFrame válido")
                return False
                
            # Atualizar apenas células modificadas
            current_data = worksheet.get_all_records()
            current_df = pd.DataFrame(current_data)
            
            # Verificar se há diferenças significativas antes de atualizar
            if not current_df.empty and len(current_df) == len(df):
                # Se o número de linhas for o mesmo, verificar se há mudanças
                if current_df.equals(df):
                    st.info("Nenhuma mudança detectada. Não é necessário salvar.")
                    return True
            
            # Limitar o número de atualizações
            with st.spinner(f"Atualizando {sheet_name}..."):
                worksheet.clear()
                worksheet.update([df.columns.tolist()] + df.values.tolist())
                
            return True
        except Exception as e:
            if "Quota exceeded" in str(e):
                st.warning("Limite de requisições excedido. Tente novamente em alguns minutos.")
            else:
                st.error(f"Erro ao atualizar {sheet_name}: {str(e)}")
            return False
    return retry_with_backoff(_update)

@st.cache_data(ttl=3600)
def load_all_data():
    # Carregar dados com um pequeno atraso entre as requisições para evitar exceder a quota
    resultados = _load_sheet_with_delay("Resultados")
    resultados["Data"] = pd.to_datetime(resultados["Data"], format="%Y-%m-%d", errors="coerce")
    time.sleep(1)  # Delay para evitar exceder limites de quota
    quimicos = _load_sheet_with_delay("Quimicos")
    time.sleep(1)  # Delay para evitar exceder limites de quota
    biologicos = _load_sheet_with_delay("Biologicos")
    time.sleep(1)  # Delay para evitar exceder limites de quota
    solicitacoes = _load_sheet_with_delay("Solicitacoes")
    
    return {
        "resultados": resultados,
        "quimicos": quimicos,
        "biologicos": biologicos,
        "solicitacoes": solicitacoes
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
            options=sorted(dados["quimicos"]['Nome'].unique()),
            index=None,
            key="quimico_compat"
        )
    
    with col2:
        biologico = st.selectbox(
            "Produto Biológico",
            options=sorted(dados["biologicos"]['Nome'].unique()),
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
            
            # Solicitar novo teste
            with st.form("solicitar_teste"):
                data_solicitacao = st.date_input("Data da Solicitação")
                solicitante = st.text_input("Nome do solicitante")
                observacoes = st.text_area("Observações")
                
                if st.form_submit_button("Solicitar Teste"):
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

def management():
    st.title("📦 Gerenciamento")

    if 'edited_data' not in st.session_state:
        st.session_state.edited_data = {}
    
    # Inicializar dados locais se não existirem na sessão
    if 'local_data' not in st.session_state:
        st.session_state.local_data = load_all_data()
        
    # Usar dados da sessão em vez de recarregar a cada interação
    dados = st.session_state.local_data
    
    tab1, tab2, tab3 = st.tabs(["Quimicos", "Biologicos", "Compatibilidades"])
    
    with tab1:
        st.subheader("Produtos Químicos")
        if dados["quimicos"].empty:
            st.error("Erro ao carregar dados dos produtos químicos!")
        else:
            with st.form("novo_quimico_form"):
                nome = st.text_input("Nome do Produto")
                tipo = st.selectbox("Tipo", options=["Herbicida", "Fungicida", "Inseticida"])
                fabricante = st.text_input("Fabricante")
                concentracao = st.text_input("Concentração")
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
            
            with st.expander("Tabela de Químicos"):
                # Filtro para a tabela
                filtro_nome = st.text_input("🔍 Filtrar por nome", key="filtro_quimicos")
                
                # Aplicar filtro
                if filtro_nome:
                    df_filtrado = dados["quimicos"][dados["quimicos"]["Nome"].str.contains(filtro_nome, case=False)]
                else:
                    df_filtrado = dados["quimicos"]
                
                # Tabela editável
                st.data_editor(
                    df_filtrado,
                    num_rows="dynamic",
                    key="quimicos_editor",
                    on_change=lambda: st.session_state.update(edited_data=True),
                    column_config={
                        "Nome": "Produto Químico",
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
        if dados["biologicos"].empty:
            st.error("Erro ao carregar dados dos produtos biológicos!")
        else:            
            with st.form("novo_biologico_form"):
                nome = st.text_input("Nome do Produto")
                tipo = st.selectbox("Tipo", options=["Bioestimulante", "Controle Biológico"])
                ingrediente_ativo = st.text_input("Ingrediente Ativo")
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
            
            with st.expander("Tabela de Produtos Biológicos"):
                # Filtro para a tabela
                filtro_nome = st.text_input("🔍 Filtrar por nome", key="filtro_biologicos")
                
                # Aplicar filtro
                if filtro_nome:
                    df_filtrado = dados["biologicos"][dados["biologicos"]["Nome"].str.contains(filtro_nome, case=False)]
                else:
                    df_filtrado = dados["biologicos"]
                
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
        if dados["resultados"].empty:
            st.error("Erro ao carregar dados dos resultados!")
        else:
            with st.expander("Adicionar Nova Compatibilidade"):
                # Formulário para adicionar nova compatibilidade
                st.subheader("Adicionar Nova Compatibilidade")
                with st.form("nova_compatibilidade_form"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        quimico = st.selectbox(
                            "Produto Químico",
                            options=sorted(dados["quimicos"]['Nome'].unique()),
                            index=None
                        )
                    with col_b:
                        biologico = st.selectbox(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]['Nome'].unique()),
                            index=None
                        )
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        data_teste = st.date_input("Data do Teste")
                        duracao = st.number_input("Duração (horas)", min_value=0, value=0)
                    with col_b:
                        tipo = st.selectbox("Tipo de Teste", options=["Simples", "Composto"])
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
            
            with st.expander("Tabela de Resultados"):
                # Filtros para a tabela
                col_a, col_b = st.columns(2)
                with col_a:
                    filtro_quimico = st.selectbox(
                        "🔍 Filtrar por Produto Químico",
                        options=["Todos"] + sorted(dados["resultados"]["Quimico"].unique().tolist()),
                        index=0
                    )
                with col_b:
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
                            options=sorted(dados["quimicos"]['Nome'].unique()),
                            required=True
                        ),
                        "Biologico": st.column_config.SelectboxColumn(
                            "Produto Biológico",
                            options=sorted(dados["biologicos"]['Nome'].unique()),
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

########################################## HISTÓRICO E RELATÓRIOS ##########################################

def history_reports():
    st.title("📊 Histórico e Relatórios")
    
    # Inicializar dados locais se não existirem na sessão
    if 'local_data' not in st.session_state:
        st.session_state.local_data = load_all_data()
        
    # Botão para recarregar dados manualmente
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Recarregar Dados", key="reload_history"):
            with st.spinner("Recarregando dados..."):
                st.cache_data.clear()
                st.session_state.local_data = load_all_data()
                st.success("Dados recarregados com sucesso!")
    
    # Usar dados da sessão em vez de recarregar a cada interação
    dados = st.session_state.local_data
    
    # Criar abas para diferentes relatórios
    tab1, tab2, tab3 = st.tabs(["Estatísticas", "Testes Realizados", "Solicitações Pendentes"])
    
    with tab1:
        st.subheader("Estatísticas de Compatibilidade")
        if not dados["resultados"].empty:
            # Criar estatísticas de compatibilidade
            df_stats = dados["resultados"].value_counts("Resultado").reset_index()
            fig = px.pie(df_stats, names="Resultado", values="count", 
                        title="Distribuição de Resultados de Compatibilidade",
                        color_discrete_map={'Compatível':'#90EE90', 'Incompatível':'#FFB6C1', 'Não testado':'#ADD8E6'})
            st.plotly_chart(fig, use_container_width=True)
            
            # Adicionar mais estatísticas
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total de Testes", len(dados["resultados"]))
                st.metric("Compatíveis", len(dados["resultados"][dados["resultados"]["Resultado"] == "Compatível"]))
            with col2:
                st.metric("Incompatíveis", len(dados["resultados"][dados["resultados"]["Resultado"] == "Incompatível"]))
                st.metric("Não testados", len(dados["resultados"][dados["resultados"]["Resultado"] == "Não testado"]))
        else:
            st.warning("Sem dados de resultados para exibir estatísticas")
    
    with tab2:
        st.subheader("Últimos Testes Realizados")
        if not dados["resultados"].empty:
            # Adicionar filtros
            col1, col2 = st.columns(2)
            with col1:
                filtro_quimico = st.multiselect(
                    "Filtrar por Produto Químico",
                    options=sorted(dados["resultados"]["Quimico"].unique()),
                    default=None
                )
            with col2:
                filtro_biologico = st.multiselect(
                    "Filtrar por Produto Biológico",
                    options=sorted(dados["resultados"]["Biologico"].unique()),
                    default=None
                )
            
            # Aplicar filtros
            df_filtrado = dados["resultados"].copy()
            if filtro_quimico:
                df_filtrado = df_filtrado[df_filtrado["Quimico"].isin(filtro_quimico)]
            if filtro_biologico:
                df_filtrado = df_filtrado[df_filtrado["Biologico"].isin(filtro_biologico)]
            
            # Mostrar dados filtrados
            st.dataframe(
                df_filtrado.sort_values("Data", ascending=False),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("Sem dados de testes para exibir")
    
    with tab3:
        st.subheader("Solicitações Pendentes")
        if not dados["solicitacoes"].empty:
            # Filtrar apenas solicitações pendentes
            solicitacoes_pendentes = dados["solicitacoes"][dados["solicitacoes"]["Status"] == "Pendente"]
            
            if not solicitacoes_pendentes.empty:
                st.dataframe(
                    solicitacoes_pendentes.sort_values("Data", ascending=False),
                    hide_index=True,
                    use_container_width=True
                )
                
                # Adicionar opção para aprovar/rejeitar solicitações
                with st.expander("Gerenciar Solicitações", expanded=False):
                    st.info("Selecione uma solicitação para atualizar seu status")
                    
                    # Criar lista de solicitações para seleção
                    solicitacoes_list = [f"{row['Data']} - {row['Quimico']} x {row['Biologico']} ({row.get('Solicitante', 'N/A')})" 
                                        for _, row in solicitacoes_pendentes.iterrows()]
                    
                    if solicitacoes_list:
                        selecionada = st.selectbox("Selecione uma solicitação", solicitacoes_list)
                        
                        if selecionada:
                            idx = solicitacoes_list.index(selecionada)
                            solicitacao = solicitacoes_pendentes.iloc[idx]
                            
                            st.write(f"**Solicitante:** {solicitacao.get('Solicitante', 'N/A')}")
                            st.write(f"**Data:** {solicitacao['Data']}")
                            st.write(f"**Produtos:** {solicitacao['Quimico']} x {solicitacao['Biologico']}")
                            st.write(f"**Observações:** {solicitacao['Observacoes']}")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("✅ Aprovar", key="aprovar_sol"):
                                    # Lógica para aprovar solicitação
                                    st.success("Solicitação aprovada!")
                            with col2:
                                if st.button("❌ Rejeitar", key="rejeitar_sol"):
                                    # Lógica para rejeitar solicitação
                                    st.error("Solicitação rejeitada!")
            else:
                st.success("Não há solicitações pendentes!")
        else:
            st.warning("Sem solicitações para exibir")

########################################## CONFIGURAÇÕES ##########################################

def settings_page():
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

########################################## SIDEBAR E ROTEAMENTO ##########################################

def main():
    st.sidebar.image("imagens/logo-cocal.png", width=150)
    st.sidebar.title("Navegação")
    
    pages = {
        "Compatibilidade": compatibilidade,
        "Gerenciamento de Produtos": management,
        "Histórico e Relatórios": history_reports,
        "Configurações": settings_page
    }
    
    selected_page = st.sidebar.radio("Selecione a página", tuple(pages.keys()))
    
    with st.spinner("Carregando dados..."):
        pages[selected_page]()

if __name__ == "__main__":
    main()