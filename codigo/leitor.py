"""
leitor.py
Lê uma instância do problema de programação de sessões técnicas de conferências
(formato do repositório github.com/tbulhoes/conference_scheduling)
e organiza os dados nos conjuntos usados pela formulação F1 da dissertação.

Uso no terminal:
    python3 codigo/leitor.py instancias/lars_30_1.txt
"""

import math
import sys


class Instancia:
    """Guarda todos os dados de uma instância (um 'congresso')."""

    def __init__(self):
        self.nome = ""                 # nome do arquivo, ex.: lars_30_1
        self.n = 0                     # número de trabalhos |P|
        self.b = []                    # matriz de benefícios b[i][j]

        self.sessoes = []              # lista de sessões (cada uma é um dicionário)
        self.num_dias = 0              # |D|
        self.paralelas = {}            # (dia, horario) -> lista de sessões nesse horário

        self.num_temas = 0             # |T|
        self.temas_do_trabalho = []    # temas_do_trabalho[i] = temas do trabalho i
        self.trabalhos_do_tema = []    # trabalhos_do_tema[t] = P_t
        self.limite_tema_dia = []      # limite_tema_dia[t] = MD_t

        self.num_autores = 0           # |A|
        self.autores_do_trabalho = []  # autores_do_trabalho[i] = autores do trabalho i
        self.trabalhos_do_autor = []   # trabalhos_do_autor[a] = P_a


def ler_instancia(caminho):
    """Lê o arquivo da instância e devolve um objeto Instancia."""

    # ------------------------------------------------------------------
    # Passo 1: ler o arquivo inteiro como uma sequência de números inteiros.
    # Não importa como os números estão quebrados em linhas: lemos um por um.
    # ------------------------------------------------------------------
    with open(caminho) as arquivo:
        numeros = [int(x) for x in arquivo.read().split()]
    proximo = iter(numeros)            # next(proximo) devolve o próximo número

    inst = Instancia()
    inst.nome = caminho.split("/")[-1].replace(".txt", "")

    # ------------------------------------------------------------------
    # Passo 2: número de trabalhos e matriz de benefícios (n x n)
    # ------------------------------------------------------------------
    inst.n = next(proximo)
    inst.b = [[next(proximo) for j in range(inst.n)] for i in range(inst.n)]

    # ------------------------------------------------------------------
    # Passo 3: tipos de sessão.
    # ATENÇÃO: a ordem real no arquivo é  MÁXIMO, QUANTIDADE, MÍNIMO
    # (o arquivo 'format' do repositório diz outra ordem, mas o Data.cpp
    # dos autores lê assim).
    # Guardamos: tamanho máximo -> tamanho mínimo, para usar nas sessões.
    # ------------------------------------------------------------------
    num_tipos = next(proximo)
    minimo_por_tamanho = {}
    for _ in range(num_tipos):
        tam_max = next(proximo)
        _quantidade = next(proximo)
        tam_min = next(proximo)
        minimo_por_tamanho[tam_max] = tam_min

    # ------------------------------------------------------------------
    # Passo 4: dias, horários e sessões.
    # Para cada dia: (número de horários, número de sessões),
    # depois uma linha (horário, tamanho) para cada sessão.
    # No arquivo os horários começam em 1; aqui passamos a contar de 0.
    # ------------------------------------------------------------------
    inst.num_dias = next(proximo)
    for dia in range(inst.num_dias):
        _num_horarios = next(proximo)
        num_sessoes_dia = next(proximo)
        for _ in range(num_sessoes_dia):
            horario = next(proximo) - 1
            tamanho = next(proximo)
            sessao = {
                "id": len(inst.sessoes),
                "dia": dia,
                "horario": horario,
                "max": tamanho,                        # M_s
                "min": minimo_por_tamanho[tamanho],    # m_s
            }
            inst.sessoes.append(sessao)
            # agrupa as sessões que acontecem no mesmo dia e horário (S_d^h)
            inst.paralelas.setdefault((dia, horario), []).append(sessao["id"])

    # ------------------------------------------------------------------
    # Passo 5: temas de cada trabalho.
    # Cabeçalho: n |T|. Depois, para cada trabalho: quantidade de temas
    # seguida dos temas.
    # ------------------------------------------------------------------
    _n_de_novo = next(proximo)
    inst.num_temas = next(proximo)
    inst.trabalhos_do_tema = [[] for _ in range(inst.num_temas)]
    for i in range(inst.n):
        qtd = next(proximo)
        temas = [next(proximo) for _ in range(qtd)]
        inst.temas_do_trabalho.append(temas)
        for t in temas:
            inst.trabalhos_do_tema[t].append(i)

    # ------------------------------------------------------------------
    # Passo 6: autores de cada trabalho (mesmo formato dos temas).
    # Consideramos TODOS os autores, como no código dos autores.
    # ------------------------------------------------------------------
    _n_de_novo = next(proximo)
    inst.num_autores = next(proximo)
    inst.trabalhos_do_autor = [[] for _ in range(inst.num_autores)]
    for i in range(inst.n):
        qtd = next(proximo)
        autores = [next(proximo) for _ in range(qtd)]
        inst.autores_do_trabalho.append(autores)
        for a in autores:
            inst.trabalhos_do_autor[a].append(i)

    # ------------------------------------------------------------------
    # Passo 7: limite de trabalhos de um tema por dia (MD_t), com a mesma
    # regra do código dos autores (getThemeLimitPerDay):
    #   - evento de 1 dia            -> sem limite (n_t)
    #   - tema com mais de 20 trab.  -> ceil(n_t / 2)
    #   - caso contrário             -> sem limite (n_t)
    # ------------------------------------------------------------------
    for t in range(inst.num_temas):
        n_t = len(inst.trabalhos_do_tema[t])
        if inst.num_dias > 1 and n_t > 20:
            inst.limite_tema_dia.append(math.ceil(n_t / 2))
        else:
            inst.limite_tema_dia.append(n_t)

    verificar(inst)
    return inst


def verificar(inst):
    """Testes simples para pegar erros de leitura."""
    for i in range(inst.n):
        assert inst.b[i][i] == 0, f"diagonal da matriz deveria ser 0 (trabalho {i})"
        for j in range(inst.n):
            assert inst.b[i][j] == inst.b[j][i], f"matriz não é simétrica em ({i},{j})"
    capacidade = sum(s["max"] for s in inst.sessoes)
    assert capacidade >= inst.n, "as sessões não comportam todos os trabalhos"


def resumo(inst):
    """Imprime um resumo legível da instância."""
    print(f"Instância: {inst.nome}")
    print(f"  Trabalhos: {inst.n}")
    print(f"  Temas: {inst.num_temas}   Autores: {inst.num_autores}")
    print(f"  Dias: {inst.num_dias}   Sessões: {len(inst.sessoes)}")
    for s in inst.sessoes:
        print(f"    sessão {s['id']}: dia {s['dia'] + 1}, horário {s['horario'] + 1}, "
              f"tamanho entre {s['min']} e {s['max']}")
    print("  Horários com sessões paralelas:")
    for (dia, horario), ids in inst.paralelas.items():
        if len(ids) > 1:
            print(f"    dia {dia + 1}, horário {horario + 1}: sessões {ids}")
    pares_positivos = sum(1 for i in range(inst.n) for j in range(i + 1, inst.n) if inst.b[i][j] > 0)
    print(f"  Pares com benefício > 0: {pares_positivos} de {inst.n * (inst.n - 1) // 2}")
    maior_tema = max(len(p) for p in inst.trabalhos_do_tema)
    print(f"  Maior tema tem {maior_tema} trabalhos (limite por dia só vale acima de 20)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 codigo/leitor.py instancias/lars_30_1.txt")
        sys.exit(1)
    resumo(ler_instancia(sys.argv[1]))