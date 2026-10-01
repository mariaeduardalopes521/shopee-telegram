import os
import time
import json
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("SHOPEE_APP_ID")
SECRET = os.getenv("SHOPEE_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SHOPEE_URL = "https://open-api.affiliate.shopee.com.br/graphql"

ARQUIVO_PUBLICADOS = "publicados.json"

# Quantas páginas serão analisadas por execução
MAX_PAGINAS_POR_EXECUCAO = 8

# Quantos produtos podem ser publicados por execução
MAX_PUBLICACOES = 10


def carregar_publicados():
    if not os.path.exists(ARQUIVO_PUBLICADOS):
        return set()

    try:
        with open(ARQUIVO_PUBLICADOS, "r", encoding="utf-8") as arquivo:
            return set(json.load(arquivo))
    except Exception:
        return set()


def salvar_publicados(publicados):
    with open(ARQUIVO_PUBLICADOS, "w", encoding="utf-8") as arquivo:
        json.dump(
            list(publicados),
            arquivo,
            ensure_ascii=False,
            indent=2
        )


publicados = carregar_publicados()


def pagina_inicial():

    # Alterna automaticamente entre blocos de páginas.
    # Isso evita consultar sempre as mesmas primeiras páginas.
    minuto_atual = int(time.time() / 300)

    total_paginas_estimadas = 45

    bloco = minuto_atual % total_paginas_estimadas

    return bloco + 1


def buscar_ofertas():

    todas_ofertas = []

    inicio = pagina_inicial()

    print(f"Página inicial desta execução: {inicio}")
    print(
        f"Analisando até {MAX_PAGINAS_POR_EXECUCAO} páginas."
    )

    for tentativa in range(MAX_PAGINAS_POR_EXECUCAO):

        pagina = ((inicio - 1 + tentativa) % 45) + 1

        query = f"""
        {{
            productOfferV2(
                listType: 0
                sortType: 1
                page: {pagina}
                limit: 50
            ) {{
                nodes {{
                    itemId
                    productName
                    priceMin
                    priceMax
                    priceDiscountRate
                    imageUrl
                    offerLink
                    productLink
                    shopName
                    sales
                    ratingStar
                }}

                pageInfo {{
                    page
                    limit
                    hasNextPage
                }}
            }}
        }}
        """

        payload = {
            "query": query
        }

        body = json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False
        )

        timestamp = str(int(time.time()))

        assinatura = hashlib.sha256(
            (
                APP_ID
                + timestamp
                + body
                + SECRET
            ).encode("utf-8")
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "Authorization": (
                f"SHA256 Credential={APP_ID},"
                f"Timestamp={timestamp},"
                f"Signature={assinatura}"
            )
        }

        try:

            resposta = requests.post(
                SHOPEE_URL,
                data=body.encode("utf-8"),
                headers=headers,
                timeout=20
            )

            resposta.raise_for_status()

            dados = resposta.json()

        except requests.RequestException as erro:

            print(
                f"Erro ao consultar Shopee na página "
                f"{pagina}: {erro}"
            )

            continue

        if "errors" in dados:

            print("Erro retornado pela Shopee:")
            print(dados["errors"])

            continue

        try:

            resultado = dados["data"]["productOfferV2"]

            ofertas = resultado["nodes"]

        except Exception as erro:

            print(
                f"Resposta inesperada da Shopee "
                f"na página {pagina}: {erro}"
            )

            continue

        print(
            f"Página {pagina}: "
            f"{len(ofertas)} produtos"
        )

        todas_ofertas.extend(ofertas)

        # Pequena pausa para evitar excesso de requisições
        time.sleep(0.5)

    return todas_ofertas


def converter_preco(valor):

    if valor is None:
        return 0

    try:
        return float(
            str(valor).replace(",", ".")
        )

    except Exception:
        return 0


def publicar_telegram(produto):

    produto_id = str(
        produto.get("itemId")
    )

    if (
        not produto_id
        or produto_id == "None"
        or produto_id in publicados
    ):
        return False

    nome = produto.get(
        "productName",
        "Produto"
    )

    preco = converter_preco(
        produto.get("priceMin")
    )

    preco_max = converter_preco(
        produto.get("priceMax")
    )

    desconto = produto.get(
        "priceDiscountRate",
        0
    )

    imagem = produto.get(
        "imageUrl"
    )

    link = (
        produto.get("offerLink")
        or produto.get("productLink")
    )

    if preco <= 0:

        print(
            f"Preço não encontrado: {nome}"
        )

        return False

    if not imagem:

        print(
            f"Imagem não encontrada: {nome}"
        )

        return False

    if not link:

        print(
            f"Link não encontrado: {nome}"
        )

        return False

    texto = (
        f"🔥 OFERTA SHOPEE\n\n"
        f"📦 {nome}\n\n"
        f"💰 Agora: R$ {preco:.2f}\n"
    )

    if preco_max > preco:

        texto += (
            f"🏷️ Até: R$ "
            f"{preco_max:.2f}\n"
        )

    if desconto:

        texto += (
            f"🔥 Desconto: "
            f"{desconto}%\n"
        )

    texto += (
        f"\n🛒 COMPRAR AGORA:\n"
        f"{link}\n\n"
        f"⚡ Compra Certa"
    )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendPhoto"
    )

    try:

        resposta = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": imagem,
                "caption": texto
            },
            timeout=20
        )

        resposta.raise_for_status()

    except requests.RequestException as erro:

        print(
            f"Erro ao publicar no Telegram: "
            f"{erro}"
        )

        return False

    publicados.add(produto_id)

    salvar_publicados(publicados)

    print(
        f"Publicado: {nome} | "
        f"R$ {preco:.2f}"
    )

    return True


def ciclo():

    print("\n==============================")
    print("BUSCANDO NOVAS OFERTAS")
    print("==============================")

    ofertas = buscar_ofertas()

    print(
        f"Ofertas encontradas: "
        f"{len(ofertas)}"
    )

    novas = 0

    # Primeiro tenta ofertas ainda não publicadas
    for produto in ofertas:

        if novas >= MAX_PUBLICACOES:
            break

        produto_id = str(
            produto.get("itemId")
        )

        if (
            not produto_id
            or produto_id == "None"
            or produto_id in publicados
        ):
            continue

        if publicar_telegram(produto):

            novas += 1

            # Pequena pausa entre publicações
            time.sleep(1)

    print(
        f"Novas ofertas publicadas: "
        f"{novas}"
    )

    print(
        f"Total de produtos já publicados: "
        f"{len(publicados)}"
    )


if __name__ == "__main__":

    try:

        ciclo()

    except Exception as erro:

        print(
            "ERRO:",
            erro
        )

        raise
