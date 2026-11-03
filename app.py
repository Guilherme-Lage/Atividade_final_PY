import json
import urllib.request
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Crescimento Demográfico", layout="wide")


@st.cache_data
def carregar_dados():
    df = pd.read_excel(Path(__file__).parent / "populacao_2010_2022.xlsx", engine="calamine")
    regioes = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}
    df["REGIAO"] = (df["COD_UF"] // 10).map(regioes)
    df["CRESCIMENTO"] = (df["POP_2022"] / df["POP_2010_COMPAT"] - 1) * 100
    return df


@st.cache_data
def carregar_mapa():
    url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson"
    with urllib.request.urlopen(url) as resposta:
        return json.load(resposta)


@st.cache_data
def carregar_idades():

    url = "https://apisidra.ibge.gov.br/values/t/9514/n3/all/v/93/p/2022/c2/4,5/c287/all"
    dados = pd.read_json(url)
    dados.columns = dados.iloc[0]
    dados = dados[1:]
    dados = dados[dados["Idade"].str.contains(r"^\d+ a \d+ anos$|100 anos ou mais")].copy()
    dados["INICIO"] = dados["Idade"].str.extract(r"^(\d+)")[0].astype(int)
    dados["FIM"] = dados["Idade"].str.extract(r"a (\d+) anos")[0].fillna(104).astype(int)
    dados = dados[(dados["FIM"] - dados["INICIO"] == 4) & (dados["INICIO"] % 5 == 0)].copy()
    dados["POP"] = pd.to_numeric(dados["Valor"], errors="coerce").fillna(0)
    dados = dados.rename(columns={"Unidade da Federação (Código)": "COD_UF"})
    dados["COD_UF"] = dados["COD_UF"].astype(int)
    return dados[["COD_UF", "Sexo", "Idade", "INICIO", "POP"]]


df = carregar_dados()

st.sidebar.header("Filtros")

regiao = st.sidebar.multiselect("Região", df["REGIAO"].unique(), default=df["REGIAO"].unique())
ufs = df[df["REGIAO"].isin(regiao)]["UF"].unique()
uf = st.sidebar.multiselect("Unidade da Federação", ufs, default=ufs)
faixa = st.sidebar.slider("Faixa etária", 0, 100, (0, 100), step=5)
anos = st.sidebar.multiselect("Anos de Censo", [2010, 2022], default=[2010, 2022])

filtrado = df[df["UF"].isin(uf)]

if filtrado.empty or not anos:
    st.warning("Selecione pelo menos uma UF e um ano.")
    st.stop()


st.title("População e Crescimento Demográfico")
st.write("Dados do IBGE (Censos 2010 e 2022) para apoiar a revisão dos Planos Diretores das capitais.")

pop_2010 = filtrado["POP_2010_COMPAT"].sum()
pop_2022 = filtrado["POP_2022"].sum()
crescimento_total = (pop_2022 / pop_2010 - 1) * 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("População 2010", f"{pop_2010:,}".replace(",", "."))
col2.metric("População 2022", f"{pop_2022:,}".replace(",", "."))
col3.metric("Crescimento total", f"{crescimento_total:.2f}%")
col4.metric("Média por cidade", f"{filtrado['CRESCIMENTO'].mean():.2f}%")


st.header("Qual é a taxa média de crescimento acumulada por cidade?")
st.write(
    f"A média é **{filtrado['CRESCIMENTO'].mean():.2f}%** e a mediana é "
    f"**{filtrado['CRESCIMENTO'].median():.2f}%**. "
    f"{(filtrado['CRESCIMENTO'] < 0).sum()} de {len(filtrado)} cidades perderam população."
)
fig = px.histogram(filtrado, x="CRESCIMENTO", nbins=50, color="REGIAO",
                   labels={"CRESCIMENTO": "Crescimento 2010-2022 (%)"})
st.plotly_chart(fig)

st.header("Onde estão os outliers de crescimento?")
q1 = filtrado["CRESCIMENTO"].quantile(0.25)
q3 = filtrado["CRESCIMENTO"].quantile(0.75)
iqr = q3 - q1
limite_baixo = q1 - 1.5 * iqr
limite_alto = q3 + 1.5 * iqr

fig = px.box(filtrado, x="REGIAO", y="CRESCIMENTO", hover_name="NOME_MUNICIPIO",
             labels={"CRESCIMENTO": "Crescimento (%)"})
st.plotly_chart(fig)

colunas = ["NOME_MUNICIPIO", "UF", "POP_2010_COMPAT", "POP_2022", "CRESCIMENTO"]
c1, c2 = st.columns(2)
c1.subheader("Cresceram muito")
c1.dataframe(filtrado[filtrado["CRESCIMENTO"] > limite_alto]
             .sort_values("CRESCIMENTO", ascending=False)[colunas], hide_index=True)
c2.subheader("Encolheram muito")
c2.dataframe(filtrado[filtrado["CRESCIMENTO"] < limite_baixo]
             .sort_values("CRESCIMENTO")[colunas], hide_index=True)

st.header("Mapa do crescimento por UF")
por_uf = filtrado.groupby("UF")[["POP_2010_COMPAT", "POP_2022"]].sum().reset_index()
por_uf["CRESCIMENTO"] = (por_uf["POP_2022"] / por_uf["POP_2010_COMPAT"] - 1) * 100

fig = px.choropleth(por_uf, geojson=carregar_mapa(), locations="UF",
                    featureidkey="properties.sigla", color="CRESCIMENTO",
                    color_continuous_scale="RdYlGn")
fig.update_geos(fitbounds="locations", visible=False)
st.plotly_chart(fig)

st.header("Evolução e projeção da população")
taxa_anual = (pop_2022 / pop_2010) ** (1 / 12) - 1

linha = []
if 2010 in anos:
    linha.append({"Ano": 2010, "População": pop_2010, "Tipo": "Censo"})
if 2022 in anos:
    linha.append({"Ano": 2022, "População": pop_2022, "Tipo": "Censo"})
for ano in [2022, 2030, 2040, 2050]:
    linha.append({"Ano": ano, "População": pop_2022 * (1 + taxa_anual) ** (ano - 2022), "Tipo": "Projeção"})

fig = px.line(pd.DataFrame(linha), x="Ano", y="População", color="Tipo", markers=True)
st.plotly_chart(fig)
st.caption(f"Projeção usando a mesma taxa de 2010-2022 ({taxa_anual * 100:.2f}% ao ano).")

st.header("Pirâmide etária (Censo 2022)")
try:
    idades = carregar_idades()
    piramide = idades[idades["COD_UF"].isin(filtrado["COD_UF"].unique())]
    piramide = piramide[piramide["INICIO"].between(faixa[0], faixa[1])]
    piramide = piramide.groupby(["INICIO", "Idade", "Sexo"])["POP"].sum().reset_index()
    piramide.loc[piramide["Sexo"] == "Homens", "POP"] *= -1  # homens para a esquerda

    fig = px.bar(piramide, x="POP", y="Idade", color="Sexo", orientation="h",
                 labels={"POP": "População", "Idade": "Faixa etária"})
    fig.update_layout(barmode="relative")
    st.plotly_chart(fig)
except Exception:
    st.warning("Não foi possível buscar os dados de idade no IBGE agora.")


st.header("Notícias")
st.markdown("""
- [IBGE: Censo 2022 - população por idade e sexo](https://agenciadenoticias.ibge.gov.br/agencia-noticias/2012-agencia-denoticias/noticias/38186-)
- [Gazeta do Povo: Brasil tem envelhecimento recorde](https://www.gazetadopovo.com.br/vida-e-cidadania/novo-censo-brasil-tem-envelhecimento-recorde-e-idosos-ja-somam-quase-11-da-populacao/)
- [IBGE: Panorama do Censo 2022](https://censo2022.ibge.gov.br/panorama/)
""")

st.header("Expansão urbana")
