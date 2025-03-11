import streamlit as st
import pandas as pd
import streamlit.components.v1 as components

# Configuração da página
st.set_page_config(page_title="Teste de Botões em Tabelas", layout="wide")

# Componente personalizado para garantir a visibilidade dos botões de ação nas tabelas
def fix_table_buttons():
    components.html(
        """
        <script>
        // Função para garantir que os botões de ação nas tabelas estejam visíveis
        function fixTableButtons() {
            // Aguardar o carregamento completo da página
            setTimeout(function() {
                // Selecionar todos os botões dentro das tabelas editáveis
                const buttons = document.querySelectorAll('[data-testid="stDataEditor"] button');
                const rowActions = document.querySelectorAll('[data-testid="dataframe-row-actions"]');
                const addRowsButtons = document.querySelectorAll('[data-testid="dataframe-add-rows"]');
                
                // Aplicar estilos para garantir visibilidade
                buttons.forEach(button => {
                    button.style.visibility = 'visible';
                    button.style.opacity = '1';
                    button.style.display = 'inline-flex';
                    button.style.pointerEvents = 'auto';
                    button.style.zIndex = '999';
                });
                
                rowActions.forEach(action => {
                    action.style.visibility = 'visible';
                    action.style.opacity = '1';
                    action.style.display = 'flex';
                    action.style.pointerEvents = 'auto';
                    action.style.zIndex = '999';
                });
                
                addRowsButtons.forEach(button => {
                    button.style.visibility = 'visible';
                    button.style.opacity = '1';
                    button.style.display = 'flex';
                    button.style.pointerEvents = 'auto';
                    button.style.zIndex = '999';
                });
                
                // Verificar se há SVGs (ícones) que precisam ser visíveis
                const svgs = document.querySelectorAll('[data-testid="stDataEditor"] svg');
                svgs.forEach(svg => {
                    svg.style.visibility = 'visible';
                    svg.style.opacity = '1';
                    svg.style.display = 'inline-block';
                    svg.style.pointerEvents = 'auto';
                    svg.style.zIndex = '999';
                });
                
                // Garantir que os contêineres não cortem os botões
                const containers = document.querySelectorAll('[data-testid="stDataEditor"]');
                containers.forEach(container => {
                    container.style.overflow = 'visible';
                    container.style.position = 'relative';
                    container.style.zIndex = '1';
                });
                
                // Executar novamente após algum tempo para garantir que funcione após atualizações dinâmicas
                setTimeout(fixTableButtons, 2000);
            }, 1000);
        }
        
        // Iniciar a função quando a página carregar
        document.addEventListener('DOMContentLoaded', fixTableButtons);
        // Também executar quando o script for carregado
        fixTableButtons();
        </script>
        """,
        height=0,
        width=0
    )

# CSS personalizado para garantir a visibilidade dos botões
st.markdown("""
<style>
    /* Garantir que os botões de ação nas tabelas sejam visíveis */
    [data-testid="stDataEditor"] button,
    [data-testid="stDataEditor"] svg,
    [data-testid="stDataEditor"] [data-testid="baseButton-secondary"],
    [data-testid="stDataEditor"] [data-testid="baseButton-primary"] {
        opacity: 1 !important;
        visibility: visible !important;
        display: inline-flex !important;
        pointer-events: auto !important;
        z-index: 100 !important;
    }
    
    /* Garantir que os ícones de edição e exclusão sejam visíveis */
    [data-testid="stDataEditor"] [data-testid="dataframe-row-actions"],
    [data-testid="stDataEditor"] [data-testid="dataframe-actions"] {
        visibility: visible !important;
        opacity: 1 !important;
        display: flex !important;
        pointer-events: auto !important;
        z-index: 100 !important;
    }
    
    /* Garantir que o botão de adicionar linhas seja visível */
    [data-testid="stDataEditor"] [data-testid="dataframe-add-rows"] {
        visibility: visible !important;
        opacity: 1 !important;
        display: flex !important;
        pointer-events: auto !important;
        z-index: 100 !important;
    }
    
    /* Corrigir problema de sobreposição que pode esconder botões */
    .stDataEditor {
        position: relative !important;
        z-index: 1 !important;
    }
    
    /* Garantir que os botões de ação não sejam cortados */
    .stDataEditor [data-testid="dataEditor-container"] {
        overflow: visible !important;
    }
    
    /* Forçar visibilidade dos botões de edição e exclusão */
    .stDataEditor [data-testid="dataEditor-addRows"],
    .stDataEditor [data-testid="dataEditor-deleteRows"],
    .stDataEditor [data-testid="dataEditor-saveButton"],
    .stDataEditor [data-testid="dataEditor-editCell"] {
        display: inline-flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        z-index: 999 !important;
    }
    
    /* Garantir que os botões não sejam escondidos por outros elementos */
    .stDataEditor [data-testid="dataEditor-container"] button {
        position: relative !important;
        z-index: 999 !important;
    }
</style>
""", unsafe_allow_html=True)

# Aplicar a correção para garantir que os botões nas tabelas sejam visíveis
fix_table_buttons()

st.title("Teste de Botões em Tabelas Editáveis")

# Criar dados de exemplo
data = {
    "Nome": ["Produto A", "Produto B", "Produto C"],
    "Tipo": ["Herbicida", "Fungicida", "Inseticida"],
    "Fabricante": ["Fabricante X", "Fabricante Y", "Fabricante Z"],
    "Concentracao": [10.0, 20.0, 30.0],
    "Classe": ["Classe A", "Classe B", "Classe C"],
    "ModoAcao": ["Modo 1", "Modo 2", "Modo 3"]
}

df = pd.DataFrame(data)

# Tabela editável com configurações otimizadas para mostrar os botões
st.subheader("Tabela Editável com Botões Visíveis")
edited_df = st.data_editor(
    df,
    num_rows="dynamic",
    hide_index=True,
    key="teste_editor",
    column_config={
        "Nome": st.column_config.TextColumn("Nome do Produto", required=True),
        "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Herbicida", "Fungicida", "Inseticida"]),
        "Fabricante": "Fabricante",
        "Concentracao": st.column_config.NumberColumn("Concentração", required=True),
        "Classe": "Classe",
        "ModoAcao": "Modo de Ação",
    },
    use_container_width=True,
    height=400,
    disabled=False,
    column_order=["Nome", "Tipo", "Fabricante", "Concentracao", "Classe", "ModoAcao"],
    key_column="Nome"
)

# Mostrar instruções
st.info("""
### Instruções para verificar os botões:
1. Passe o mouse sobre as linhas da tabela acima
2. Os botões de edição e exclusão devem aparecer à direita de cada linha
3. O botão "Adicionar linha" deve estar visível abaixo da tabela
""")

# Mostrar dados editados
if st.button("Mostrar dados editados"):
    st.write("Dados atuais da tabela:")
    st.write(edited_df)
