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


def carregar_publicados():
    if not os.path.exists(ARQUIVO_PUBLICADOS):
        return set()
    try:
        with open(ARQUIVO_PUBLICADOS, "r", encoding="utf-8") as arquivo:
            return set(json.load(arquivo))
    except:
        return set()


def salvar_publicados(publicados):
    with open(ARQUIVO_PUBLICADOS, "w", encoding="utf-8") as arquivo:
        json.dump(list(publicados), arquivo, ensure_ascii=False)


publicados = carregar_publicados()


def buscar_ofertas():

    todas_ofertas = []
    pagina = 1

    while True:

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
            (APP_ID + timestamp + body + SECRET).encode("utf-8")
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "Authorization": (
                f"SHA256 Credential={APP_ID},"
                f"Timestamp={timestamp},"
                f"Signature={assinatura}"
            )
        }

        resposta = requests.post(
            SHOPEE_URL,
            data=body.encode("utf-8"),
            headers=headers,
            timeout=30
        )

        resposta.raise_for_status()

        dados = resposta.json()

        if "errors" in dados:
            print("Erro da Shopee:")
            print(dados["errors"])
            break

        resultado = dados["data"]["productOfferV2"]

        ofertas = resultado["nodes"]

        print(
            f"Página {pagina}: "
            f"{len(ofertas)} produtos"
        )

        todas_ofertas.extend(ofertas)

        if not resultado["pageInfo"]["hasNextPage"]:
            print("Última página alcançada.")
            break

        pagina += 1

        time.sleep(1)

    return todas_ofertas

def converter_preco(valor):
    if valor is None:
        return 0
    try:
        return float(str(valor).replace(",", "."))
    except:
        return 0


def publicar_telegram(produto):
    produto_id = str(produto.get("itemId"))

    if not produto_id or produto_id == "None" or produto_id in publicados:
        return False

    nome = produto.get("productName", "Produto")
    preco = converter_preco(produto.get("priceMin"))
    preco_max = converter_preco(produto.get("priceMax"))
    desconto = produto.get("priceDiscountRate", 0)
    imagem = produto.get("imageUrl")
    link = produto.get("offerLink") or produto.get("productLink")

    if preco <= 0:
        print(f"Preço não encontrado: {nome}")
        return False

    texto = (
        f"🔥 OFERTA SHOPEE\n\n"
        f"📦 {nome}\n\n"
        f"💰 Agora: R$ {preco:.2f}\n"
    )

    if preco_max > preco:
        texto += f"🏷️ Até: R$ {preco_max:.2f}\n"
    if desconto:
        texto += f"🔥 Desconto: {desconto}%\n"

    texto += f"\n🛒 COMPRAR AGORA:\n{link}\n\n⚡ Compra Certa"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    resposta = requests.post(
        url,
        json={"chat_id": TELEGRAM_CHAT_ID, "photo": imagem, "caption": texto},
        timeout=30
    )
    resposta.raise_for_status()

    publicados.add(produto_id)
    salvar_publicados(publicados)
    print(f"Publicado: {nome} | R$ {preco:.2f}")
    return True


def ciclo():
    print("\n==============================")
    print("BUSCANDO NOVAS OFERTAS")
    print("==============================")

    ofertas = buscar_ofertas()
    print(f"Ofertas encontradas: {len(ofertas)}")

    novas = 0
    for produto in ofertas:
        if novas >= 10:
            break
        if publicar_telegram(produto):
            novas += 1
        time.sleep(2)

    print(f"Novas ofertas publicadas: {novas}")
    print(f"Total de produtos já publicados: {len(publicados)}")


while True:
    try:
        ciclo()
    except Exception as erro:
        print("ERRO:", erro)

    print("\nAguardando 5 minutos...")
    time.sleep(300)
