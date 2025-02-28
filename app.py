import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import ssl

st.set_page_config(
    page_title="Compatibilidade de Produtos",
    page_icon="imagens/icone-cocal.png",
    layout="wide"
)

# Função para estilizar a página
def local_css():
    st.markdown("""
        <style>
        .main {
            padding: 2rem;
        }
        .stButton>button {
            width: 100%;
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

def carregar_dados():
    try:
        # Configurar o contexto SSL (pode precisar para algumas redes corporativas)
        ssl._create_default_https_context = ssl._create_unverified_context

        # Definir os escopos necessários
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]

        # Carregar as credenciais do arquivo JSON
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            'auth.json', 
            scope
        )

        # Autorizar o cliente
        client = gspread.authorize(creds)

        # Acessar a planilha (substitua pela sua URL)
        sheet = client.open_by_url(
            'https://docs.google.com/spreadsheets/d/1lILLXICVkVekkm2EZ-20cLnkYFYvHnb14NL_Or7132U/edit#gid=0'
        )

        # Exemplo: Carregar dados da primeira aba
        worksheet = sheet.get_worksheet(0)
        dados = worksheet.get_all_records()

        return pd.DataFrame(dados)

    except Exception as e:
        st.error(f"Erro na conexão: {str(e)}")
        return pd.DataFrame()

def main():
    local_css()
    
    # Sidebar
    with st.sidebar:
        st.image("imagens/logo-cocal.png", width=50)
        st.title("Menu")
        st.markdown("---")
        pagina = st.radio(
            "Navegação",
            ["Compatibilidade", "Produtos", "Histórico", "Configurações"]
        )
    
    # Página principal
    st.title("🌱 Análise de Compatibilidade")
    st.markdown("---")
    
    if pagina == "Compatibilidade":
        # Layout em duas colunas
        col1, col2 = st.columns(2)
        
        dados = carregar_dados()
        produtos_quimicos = sorted(dados['quimicos']['Químico'].unique())
        produtos_biologicos = sorted(dados['biologicos']['Biológico'].unique())
        
        with col1:
            quimico = st.selectbox(
                "Selecione o Produto Químico",
                options=produtos_quimicos,
                index=None,
                placeholder="Escolha um produto..."
            )
            
        with col2:
            biologico = st.selectbox(
                "Selecione o Produto Biológico",
                options=produtos_biologicos,
                index=None,
                placeholder="Escolha um produto..."
            )
        
        if quimico and biologico:
            # Encontrar IDs dos produtos selecionados
            id_quimico = dados['quimicos'].loc[
                dados['quimicos']['Nome'] == quimico, 'ID'].values[0]
            
            id_biologico = dados['biologicos'].loc[
                dados['biologicos']['Nome'] == biologico, 'ID'].values[0]
            
            # Verificar compatibilidade
            resultado = dados['compatibilidades'][
                (dados['compatibilidades']['Químico'] == id_quimico) &
                (dados['compatibilidades']['Biológico'] == id_biologico)
            ]
            
            if not resultado.empty:
                status = resultado['Resultado'].values[0]
                resultado = resultado[0]
                classe_css = "compativel" if status == "Compatível" else "incompativel"
                st.markdown(f"""
                    <div class="resultado {classe_css}">
                        {resultado}
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("Combinação não testada. Deseja solicitar um teste?")
                if st.button("Solicitar Teste"):
                    # Adicione lógica para atualizar a planilha
                    st.success("Solicitação registrada!")
    
    elif pagina == "Produtos":
        dados = carregar_dados()
        st.subheader("Produtos Químicos")
        st.dataframe(dados['quimicos'])
        
        st.subheader("Produtos Biológicos")
        st.dataframe(dados['biologicos'])

    elif pagina == "Histórico":
        st.info("Página em desenvolvimento")
    elif pagina == "Configurações":
        st.info("Página em desenvolvimento")

if __name__ == "__main__":
    main()
