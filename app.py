import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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
    # TODO: Implementar a conexão com Google Sheets
    # Por enquanto, usando dados de exemplo
    dados = {
        'Químico': ['a', 'b', 'c'],
        'Biológico': ['x', 'y', 'z'],
        'Resultado': ['Compatível', 'Incompatível', 'Compatível']
    }
    return pd.DataFrame(dados)

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
        
        df = carregar_dados()
        produtos_quimicos = sorted(df['Químico'].unique())
        produtos_biologicos = sorted(df['Biológico'].unique())
        
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
            resultado = df[
                (df['Químico'] == quimico) & 
                (df['Biológico'] == biologico)
            ]['Resultado'].values
            
            if len(resultado) > 0:
                resultado = resultado[0]
                classe_css = "compativel" if resultado == "Compatível" else "incompativel"
                st.markdown(f"""
                    <div class="resultado {classe_css}">
                        {resultado}
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("Combinação não encontrada no banco de dados.")
    
    elif pagina == "Produtos":
        st.info("Página em desenvolvimento")
    elif pagina == "Histórico":
        st.info("Página em desenvolvimento")
    elif pagina == "Configurações":
        st.info("Página em desenvolvimento")

if __name__ == "__main__":
    main()
