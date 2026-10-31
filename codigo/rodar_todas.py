"""
rodar_todas.py
==============

Roda a formulação F1 (modelo.py) em várias instâncias, UMA DE CADA VEZ,
e grava os resultados numa tabela CSV, já ao lado dos valores obtidos pelos
autores do artigo (F1 resolvida com CPLEX).

USO NO TERMINAL (a partir da pasta do projeto, com o .venv ativado)
-------------------------------------------------------------------
    python3 codigo/rodar_todas.py                      # 1800 s por instância, lars_30_*
    python3 codigo/rodar_todas.py 600                  # 600 s por instância
    python3 codigo/rodar_todas.py 1800 "instancias/lars_40_*.txt"

O QUE ELE GERA
--------------
    resultados/resultados.csv     -> uma linha por instância (abre no LibreOffice/Excel)
    resultados/solucoes/*.txt     -> a programação encontrada para cada instância

SE FOR INTERROMPIDO
-------------------
O CSV é gravado depois de CADA instância. Se o computador desligar ou você
apertar Ctrl+C, basta rodar o mesmo comando de novo: as instâncias que já
estão no CSV são puladas. Para recomeçar do zero, apague resultados/resultados.csv.
"""

import csv
import glob
import os
import sys

from leitor import ler_instancia
from modelo import resolver

# ----------------------------------------------------------------------
# Valores de referência: F1 dos autores, resolvida com CPLEX 12.7.
# Fonte: arquivos logs/lars.zip -> lars/F1/<instancia>.txt.log_exato.txt
# do repositório github.com/tbulhoes/conference_scheduling
# (linhas ">>> Total value" e ">>> Total time", tempo convertido de ms para s).
# Todos esses valores são ÓTIMOS: o CPLEX terminou antes do limite de 3 horas.
# ----------------------------------------------------------------------
REFERENCIA = {
    # instância:   (ótimo, tempo do CPLEX em segundos)
    "lars_30_1": (311, 50.36),
    "lars_30_2": (517, 12.67),
    "lars_30_3": (282, 22.69),
    "lars_30_4": (203, 20.43),
    "lars_30_5": (269, 71.56),
    "lars_40_1": (497, 94.66),
    "lars_40_2": (556, 55.95),
    "lars_40_3": (409, 146.22),
    "lars_40_4": (515, 3076.32),
    "lars_40_5": (514, 95.86),
}

ARQUIVO_CSV = "resultados/resultados.csv"
PASTA_SOLUCOES = "resultados/solucoes"

# Colunas da tabela, na ordem em que aparecem no CSV.
COLUNAS = [
    "instancia",        # nome do arquivo, ex.: lars_30_1
    "trabalhos",        # número de trabalhos
    "variaveis",        # tamanho do modelo
    "restricoes",
    "status",           # OPTIMAL (ótimo provado) ou FEASIBLE (tempo acabou)
    "valor_cbc",        # melhor solução encontrada pelo CBC
    "limitante_cbc",    # limitante superior do CBC
    "gap_cbc_pct",      # gap do CBC em %
    "tempo_cbc_s",      # tempo do CBC em segundos
    "otimo_autores",    # ótimo da F1 dos autores (CPLEX)
    "tempo_cplex_s",    # tempo do CPLEX nos autores
    "diferenca",        # otimo_autores - valor_cbc (0 = achou o ótimo)
]


def ja_resolvidas():
    """Devolve o conjunto de instâncias que já estão no CSV."""
    if not os.path.exists(ARQUIVO_CSV):
        return set()
    with open(ARQUIVO_CSV, newline="") as f:
        return {linha["instancia"] for linha in csv.DictReader(f)}


def gravar_linha(linha):
    """Acrescenta uma linha ao CSV (cria o arquivo com cabeçalho se não existir)."""
    novo = not os.path.exists(ARQUIVO_CSV)
    with open(ARQUIVO_CSV, "a", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        if novo:
            escritor.writeheader()
        escritor.writerow(linha)


def gravar_solucao(resultado, inst):
    """Salva a programação encontrada num arquivo de texto, para conferência."""
    os.makedirs(PASTA_SOLUCOES, exist_ok=True)
    caminho = os.path.join(PASTA_SOLUCOES, f"{inst.nome}.txt")
    with open(caminho, "w") as f:
        f.write(f"Instância: {inst.nome}\n")
        f.write(f"Status: {resultado['status']}   Valor: {resultado['valor']}\n")
        if resultado["sessoes"] is None:
            f.write("Nenhuma solução encontrada.\n")
            return
        for s, trabalhos in enumerate(resultado["sessoes"]):
            sessao = inst.sessoes[s]
            beneficio = sum(inst.b[i][j] for i in trabalhos for j in trabalhos if i < j)
            lista = ", ".join(str(i + 1) for i in trabalhos)   # numeração a partir de 1
            f.write(f"sessão {s} (dia {sessao['dia'] + 1}, horário {sessao['horario'] + 1}): "
                    f"[{lista}]  benefício {beneficio}\n")


def main():
    # ------------------------------------------------------------------
    # Argumentos: tempo limite (padrão 1800 s) e padrão de arquivos
    # (padrão: as 5 instâncias de 26 trabalhos).
    # ------------------------------------------------------------------
    tempo_limite = int(sys.argv[1]) if len(sys.argv) > 1 else 1800
    padrao = sys.argv[2] if len(sys.argv) > 2 else "instancias/lars_30_*.txt"

    arquivos = sorted(glob.glob(padrao))
    if not arquivos:
        print(f"Nenhum arquivo encontrado com o padrão: {padrao}")
        sys.exit(1)

    os.makedirs("resultados", exist_ok=True)
    feitas = ja_resolvidas()

    print(f"{len(arquivos)} instância(s), limite de {tempo_limite} s cada.\n")

    for caminho in arquivos:
        inst = ler_instancia(caminho)

        if inst.nome in feitas:
            print(f"{inst.nome}: já está no CSV, pulando.")
            continue

        print(f"{inst.nome}: resolvendo ({inst.n} trabalhos)...", flush=True)
        resultado = resolver(inst, tempo_limite=tempo_limite)

        otimo, tempo_cplex = REFERENCIA.get(inst.nome, (None, None))
        diferenca = None
        if otimo is not None and resultado["valor"] is not None:
            diferenca = otimo - resultado["valor"]

        gravar_linha({
            "instancia": inst.nome,
            "trabalhos": inst.n,
            "variaveis": resultado["variaveis"],
            "restricoes": resultado["restricoes"],
            "status": resultado["status"],
            "valor_cbc": resultado["valor"],
            "limitante_cbc": round(resultado["limitante"], 2),
            "gap_cbc_pct": resultado["gap"],
            "tempo_cbc_s": resultado["tempo"],
            "otimo_autores": otimo,
            "tempo_cplex_s": tempo_cplex,
            "diferenca": diferenca,
        })
        gravar_solucao(resultado, inst)

        print(f"    status {resultado['status']}, valor {resultado['valor']} "
              f"(ótimo dos autores: {otimo}), gap {resultado['gap']}%, "
              f"tempo {resultado['tempo']} s", flush=True)

    # ------------------------------------------------------------------
    # Resumo final: mostra a tabela inteira (inclusive de execuções anteriores).
    # ------------------------------------------------------------------
    print("\nResumo (resultados/resultados.csv):")
    print(f"{'instância':<11}{'status':<10}{'CBC':>6}{'ótimo':>7}{'gap%':>8}{'tempo CBC':>11}{'tempo CPLEX':>13}")
    with open(ARQUIVO_CSV, newline="") as f:
        for l in csv.DictReader(f):
            print(f"{l['instancia']:<11}{l['status']:<10}{l['valor_cbc']:>6}{l['otimo_autores']:>7}"
                  f"{l['gap_cbc_pct']:>8}{l['tempo_cbc_s']:>11}{l['tempo_cplex_s']:>13}")


if __name__ == "__main__":
    main()