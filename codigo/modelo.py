"""
modelo.py
=========

Formulação F1 da dissertação de Rubens Correia (UFPB, 2019),
"Formulações matemáticas e algoritmo híbrido para o problema de programação
de sessões técnicas de conferências", implementada com a biblioteca mip e
resolvida pelo solver CBC.

O PROBLEMA EM UMA FRASE
-----------------------
Distribuir os trabalhos de um congresso em sessões, juntando na mesma sessão
os trabalhos com temas parecidos (para maximizar o "benefício"), sem que um
autor tenha trabalhos em duas sessões que acontecem ao mesmo tempo.

NOTAÇÃO (a mesma da dissertação)
--------------------------------
    i, j  -> trabalhos (papers).  No código vão de 0 a n-1.
    s     -> sessões.             No código vão de 0 a |S|-1.
    a     -> autores.
    t     -> temas.
    d     -> dias.
    h     -> horários.

    b_ij   -> benefício de colocar os trabalhos i e j na MESMA sessão
              (1, 10 ou 100 conforme tenham 1, 2 ou 3 temas em comum; 0 se nenhum)
    m_s    -> número mínimo de trabalhos da sessão s (se ela for usada)
    M_s    -> número máximo de trabalhos da sessão s
    P_a    -> conjunto dos trabalhos do autor a
    P_t    -> conjunto dos trabalhos que têm o tema t
    S_d    -> conjunto das sessões do dia d
    S_d^h  -> conjunto das sessões do dia d no horário h (sessões PARALELAS)
    MD_t   -> máximo de trabalhos do tema t num mesmo dia

RESTRIÇÕES USADAS (numeração da dissertação)
--------------------------------------------
    (3.1)  função objetivo: maximizar a soma dos benefícios
    (3.2)  cada trabalho fica em exatamente uma sessão
    (3.3)  cada sessão usada respeita os tamanhos mínimo e máximo
    (3.4)  se um trabalho do autor está na sessão, o autor "está presente" nela
    (3.5)  um autor está presente em no máximo uma das sessões paralelas
    (3.7)  limite de trabalhos de um mesmo tema num mesmo dia
    (3.8)  x_ij^s <= y_i^s   (o par i-j só está na sessão s se i estiver nela)
    (3.9)  x_ij^s <= y_j^s   (o par i-j só está na sessão s se j estiver nela)

RESTRIÇÕES REMOVIDAS (com justificativa)
----------------------------------------
    (3.6)  limite de tema por horário: desligada no código dos próprios autores
           (o bloco está comentado no arquivo lazyCut.cpp do repositório).
    (3.10) x_ij^s >= y_i^s + y_j^s - 1: redundante neste problema. Como estamos
           MAXIMIZANDO e todo b_ij >= 0, o solver já "quer" colocar x_ij^s = 1
           sempre que os dois trabalhos estão na sessão; não é preciso obrigá-lo.

SIMPLIFICAÇÕES QUE NÃO MUDAM A RESPOSTA
---------------------------------------
    - x_ij^s só é criada para pares com b_ij > 0 (pares com benefício 0
      não alteram a função objetivo).
    - v_a^s só é criada para autores com mais de um trabalho (um autor com um
      único trabalho nunca consegue estar em duas sessões ao mesmo tempo).

USO NO TERMINAL
---------------
    python3 codigo/modelo.py instancias/lars_30_1.txt          # limite de 1800 s
    python3 codigo/modelo.py instancias/lars_30_1.txt 600      # limite de 600 s
"""

import sys
import time

from mip import BINARY, CBC, MAXIMIZE, Model, OptimizationStatus, xsum

from leitor import ler_instancia


def resolver(inst, tempo_limite=1800, mostrar_log=False):
    """
    Monta e resolve a formulação F1 para uma instância.

    Parâmetros:
        inst         -> objeto Instancia devolvido por ler_instancia()
        tempo_limite -> tempo máximo, em segundos, que o CBC pode gastar
        mostrar_log  -> True para ver o log do CBC no terminal

    Devolve um dicionário com status, valor, limitante, gap, tempo e a
    programação encontrada (lista de trabalhos de cada sessão).
    """

    # ==================================================================
    # CONJUNTOS
    # range(k) gera 0, 1, ..., k-1. Cada conjunto é só a lista de índices.
    # ==================================================================
    P = range(inst.n)                  # trabalhos:  0 .. n-1
    S = range(len(inst.sessoes))       # sessões:    0 .. |S|-1
    A = range(inst.num_autores)        # autores
    T = range(inst.num_temas)          # temas
    D = range(inst.num_dias)           # dias

    # Lista dos pares de trabalhos (i, j), com i < j, que têm benefício > 0.
    # Exigimos i < j para não contar o mesmo par duas vezes
    # (o par (3, 7) é o mesmo que o par (7, 3)).
    # Na lars_30_1 são 163 pares, de 325 possíveis.
    pares = [(i, j) for i in P for j in P if i < j and inst.b[i][j] > 0]

    # Autores com mais de um trabalho: só eles podem "estar em dois lugares
    # ao mesmo tempo", então só eles precisam das restrições (3.4) e (3.5).
    autores_relevantes = [a for a in A if len(inst.trabalhos_do_autor[a]) > 1]

    # Cria o modelo: problema de MAXIMIZAÇÃO resolvido pelo CBC.
    modelo = Model("conference_scheduling_F1", sense=MAXIMIZE, solver_name=CBC)
    modelo.verbose = 1 if mostrar_log else 0

    # ==================================================================
    # VARIÁVEIS DE DECISÃO
    # Todas são binárias (só podem valer 0 ou 1). Isso corresponde às
    # restrições de domínio (3.11) a (3.14) da dissertação.
    # ==================================================================

    # ------------------------------------------------------------------
    # y_i^s  ->  y[i][s]                                          (3.12)
    #   y[i][s] = 1  se o trabalho i foi colocado na sessão s
    #   y[i][s] = 0  caso contrário
    # É a decisão PRINCIPAL do problema: "em qual sessão fica cada trabalho".
    # Exemplo: y[4][2] = 1 significa "o trabalho 4 está na sessão 2".
    # Total: n x |S| variáveis (26 x 6 = 156 na lars_30_1).
    # ------------------------------------------------------------------
    y = [[modelo.add_var(var_type=BINARY, name=f"y_{i}_{s}") for s in S] for i in P]

    # ------------------------------------------------------------------
    # x_ij^s  ->  x[i, j, s]                                      (3.11)
    #   x[i, j, s] = 1  se os trabalhos i e j estão JUNTOS na sessão s
    #   x[i, j, s] = 0  caso contrário
    # É a variável que "recebe" o benefício b_ij na função objetivo.
    # Ela é necessária porque o solver não aceita multiplicar variáveis:
    # o ideal seria escrever b_ij * y[i][s] * y[j][s], mas isso não é linear.
    # Então criamos x para representar esse produto, e as restrições
    # (3.8) e (3.9) garantem que x só vale 1 quando os dois estão na sessão.
    # Exemplo: x[4, 24, 1] = 1 significa "os trabalhos 4 e 24 estão juntos
    # na sessão 1".
    # Só criamos x para os pares com benefício > 0 (lista 'pares').
    # x é um dicionário: a chave é a tupla (i, j, s).
    # ------------------------------------------------------------------
    x = {(i, j, s): modelo.add_var(var_type=BINARY, name=f"x_{i}_{j}_{s}")
         for (i, j) in pares for s in S}

    # ------------------------------------------------------------------
    # u^s  ->  u[s]                                               (3.13)
    #   u[s] = 1  se a sessão s é usada (tem pelo menos um trabalho)
    #   u[s] = 0  se a sessão s fica vazia
    # Serve para a restrição (3.3): o tamanho mínimo só vale se a sessão
    # for usada. Uma sessão vazia é permitida; uma sessão com 1 trabalho, não.
    # ------------------------------------------------------------------
    u = [modelo.add_var(var_type=BINARY, name=f"u_{s}") for s in S]

    # ------------------------------------------------------------------
    # v_a^s  ->  v[a, s]                                          (3.14)
    #   v[a, s] = 1  se o autor a tem algum trabalho na sessão s
    #               (o autor "precisa estar presente" na sessão s)
    #   v[a, s] = 0  caso contrário
    # Serve para as restrições (3.4) e (3.5), que impedem um autor de estar
    # em duas sessões que acontecem ao mesmo tempo.
    # Só criamos v para autores com mais de um trabalho.
    # ------------------------------------------------------------------
    v = {(a, s): modelo.add_var(var_type=BINARY, name=f"v_{a}_{s}")
         for a in autores_relevantes for s in S}

    # ==================================================================
    # (3.1) FUNÇÃO OBJETIVO
    #
    #     max   soma_s  soma_{i<j}  b_ij * x_ij^s
    #
    # Para cada sessão s e cada par (i, j): se os dois estão juntos na sessão
    # (x = 1), ganhamos b_ij pontos; se não estão (x = 0), não ganhamos nada.
    # O solver procura a distribuição que dá o MAIOR total.
    # xsum(...) é a soma da biblioteca mip (mais rápida que o sum do Python).
    # ==================================================================
    modelo.objective = xsum(inst.b[i][j] * x[i, j, s] for (i, j) in pares for s in S)

    # ==================================================================
    # (3.2) CADA TRABALHO EM EXATAMENTE UMA SESSÃO
    #
    #     soma_s  y_i^s  =  1        para todo trabalho i
    #
    # Para o trabalho i, somamos y[i][s] em todas as sessões. Como cada y
    # vale 0 ou 1, a soma conta em quantas sessões o trabalho i foi colocado.
    # Exigir "= 1" significa: nenhum trabalho fica de fora (soma 0) e
    # nenhum trabalho aparece em duas sessões (soma 2 ou mais).
    # ==================================================================
    for i in P:
        modelo += xsum(y[i][s] for s in S) == 1, f"r3_2_trab{i}"

    # ==================================================================
    # (3.3) TAMANHO DA SESSÃO
    #
    #     m_s * u^s  <=  soma_i y_i^s  <=  M_s * u^s     para toda sessão s
    #
    # soma_i y_i^s = quantos trabalhos foram colocados na sessão s.
    # A desigualdade dupla vira duas restrições no código:
    #   - se u[s] = 1 (sessão usada): m_s <= quantidade <= M_s
    #   - se u[s] = 0 (sessão vazia): 0 <= quantidade <= 0, ou seja, vazia
    # Exemplo (lars_30_1): sessões com mínimo 3 e máximo 4 ou 6 trabalhos.
    # ==================================================================
    for s in S:
        tamanho = xsum(y[i][s] for i in P)       # quantidade de trabalhos na sessão s
        modelo += tamanho >= inst.sessoes[s]["min"] * u[s], f"r3_3_min_s{s}"
        modelo += tamanho <= inst.sessoes[s]["max"] * u[s], f"r3_3_max_s{s}"

    # ==================================================================
    # (3.4) TRABALHO DO AUTOR NA SESSÃO => AUTOR PRESENTE NA SESSÃO
    #
    #     |P_a| * v_a^s  >=  soma_{i em P_a} y_i^s     para todo autor a e sessão s
    #
    # O lado direito conta quantos trabalhos do autor a estão na sessão s.
    #   - Se for 0, a restrição não obriga nada.
    #   - Se for 1 ou mais, o lado esquerdo precisa ser positivo, o que só
    #     acontece com v[a, s] = 1. Ou seja: o autor fica "marcado" como
    #     presente na sessão s.
    # Por que multiplicar por |P_a| (número de trabalhos do autor)?
    # Para permitir que VÁRIOS trabalhos do mesmo autor fiquem na MESMA
    # sessão: se o autor tem 2 trabalhos e os dois estão na sessão s, o lado
    # direito vale 2, e 2 * v[a, s] = 2 continua satisfazendo a restrição.
    # ==================================================================
    for a in autores_relevantes:
        Pa = inst.trabalhos_do_autor[a]           # trabalhos do autor a
        for s in S:
            modelo += len(Pa) * v[a, s] >= xsum(y[i][s] for i in Pa), f"r3_4_a{a}_s{s}"

    # ==================================================================
    # (3.5) AUTOR EM NO MÁXIMO UMA SESSÃO PARALELA
    #
    #     soma_{s em S_d^h} v_a^s  <=  1     para todo autor a, dia d e horário h
    #
    # S_d^h são as sessões que acontecem no MESMO dia e MESMO horário.
    # Somamos v[a, s] nessas sessões: o resultado é em quantas delas o autor
    # precisaria estar ao mesmo tempo. Exigir "<= 1" impede que ele esteja
    # em duas salas simultaneamente.
    # Junto com a (3.4), isso garante: dois trabalhos de um mesmo autor podem
    # ficar na mesma sessão ou em horários diferentes, mas nunca em sessões
    # paralelas.
    # Só criamos a restrição onde há 2 ou mais sessões no mesmo horário
    # (na lars_30_1, apenas no dia 2, horário 1: sessões 4 e 5).
    # ==================================================================
    for (dia, horario), sessoes_paralelas in inst.paralelas.items():
        if len(sessoes_paralelas) < 2:
            continue                              # sessão sozinha no horário: nada a impedir
        for a in autores_relevantes:
            modelo += xsum(v[a, s] for s in sessoes_paralelas) <= 1, \
                f"r3_5_a{a}_d{dia}_h{horario}"

    # ==================================================================
    # (3.7) LIMITE DE TRABALHOS DE UM TEMA NUM MESMO DIA
    #
    #     soma_{i em P_t}  soma_{s em S_d}  y_i^s  <=  MD_t
    #                                           para todo tema t e dia d
    #
    # Conta quantos trabalhos do tema t foram colocados em sessões do dia d
    # e limita esse número a MD_t. A ideia é espalhar os temas ao longo do
    # evento, para não concentrar um assunto inteiro num único dia.
    # MD_t foi calculado no leitor.py com a regra do código dos autores:
    #   - tema com mais de 20 trabalhos (e evento com mais de 1 dia):
    #     MD_t = metade dos trabalhos do tema, arredondada para cima
    #   - caso contrário: MD_t = número de trabalhos do tema (sem limite real)
    # Nas instâncias de 26 trabalhos, nenhum tema passa de 20 trabalhos,
    # então esta restrição existe mas nunca "aperta".
    # ==================================================================
    for t in T:
        Pt = inst.trabalhos_do_tema[t]            # trabalhos que têm o tema t
        for d in D:
            Sd = [s for s in S if inst.sessoes[s]["dia"] == d]   # sessões do dia d
            modelo += xsum(y[i][s] for i in Pt for s in Sd) <= inst.limite_tema_dia[t], \
                f"r3_7_t{t}_d{d}"

    # ==================================================================
    # (3.8)  x_ij^s  <=  y_i^s
    # (3.9)  x_ij^s  <=  y_j^s          para todo par (i, j) e sessão s
    #
    # Estas duas restrições LIGAM a variável do par (x) às variáveis dos
    # trabalhos (y). Elas impedem o solver de "trapacear":
    #   - Se o trabalho i NÃO está na sessão s (y[i][s] = 0), a (3.8) obriga
    #     x[i, j, s] = 0: o par não pode contar como junto nessa sessão.
    #   - Se o trabalho j NÃO está na sessão s (y[j][s] = 0), a (3.9) obriga
    #     x[i, j, s] = 0, pelo mesmo motivo.
    #   - Só quando os DOIS estão na sessão (y[i][s] = y[j][s] = 1) o x pode
    #     valer 1 e o benefício b_ij entra na função objetivo.
    # Sem elas, o solver colocaria x = 1 em todos os pares e "ganharia"
    # benefícios falsos.
    #
    # Tabela-verdade (o que x pode valer):
    #     y_i^s   y_j^s   |   x_ij^s permitido
    #       0       0     |   só 0
    #       0       1     |   só 0      <- (3.8) impede
    #       1       0     |   só 0      <- (3.9) impede
    #       1       1     |   0 ou 1    <- o solver escolhe 1, porque aumenta o objetivo
    #
    # A última linha é o motivo de a (3.10) ser dispensável: ela só serviria
    # para forçar x = 1 nesse caso, mas a maximização já faz isso sozinha.
    # ==================================================================
    for (i, j) in pares:
        for s in S:
            modelo += x[i, j, s] <= y[i][s], f"r3_8_{i}_{j}_s{s}"
            modelo += x[i, j, s] <= y[j][s], f"r3_9_{i}_{j}_s{s}"

    # ==================================================================
    # RESOLVER
    # O CBC roda até provar o ótimo ou até estourar o tempo limite.
    # ==================================================================
    inicio = time.time()
    status = modelo.optimize(max_seconds=tempo_limite)
    tempo = time.time() - inicio

    # ------------------------------------------------------------------
    # Significado dos campos do resultado:
    #   status     -> OPTIMAL: ótimo encontrado E provado
    #                 FEASIBLE: encontrou solução, mas o tempo acabou antes
    #                           de provar que é a melhor
    #                 INFEASIBLE: não existe solução que respeite as restrições
    #   valor      -> valor da melhor solução encontrada (limitante INFERIOR)
    #   limitante  -> o ótimo verdadeiro é no máximo este valor
    #                 (limitante SUPERIOR, vindo da relaxação linear)
    #   gap        -> distância percentual entre os dois; 0% = ótimo provado
    # ------------------------------------------------------------------
    resultado = {
        "instancia": inst.nome,
        "trabalhos": inst.n,
        "variaveis": modelo.num_cols,
        "restricoes": modelo.num_rows,
        "status": status.name,
        "valor": None,
        "limitante": modelo.objective_bound,
        "gap": None,
        "tempo": round(tempo, 2),
        "sessoes": None,
    }

    if status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE):
        valor = modelo.objective_value
        resultado["valor"] = round(valor)
        if valor > 0:
            resultado["gap"] = round(100 * (modelo.objective_bound - valor) / valor, 2)
        # Lê a solução: para cada sessão s, quais trabalhos têm y[i][s] = 1.
        # (usamos >= 0.5 em vez de == 1 por causa de pequenos erros numéricos)
        resultado["sessoes"] = [[i for i in P if y[i][s].x >= 0.5] for s in S]

    return resultado


def imprimir(resultado, inst):
    """Mostra o resultado e a programação encontrada no terminal."""
    print(f"Instância: {resultado['instancia']}  ({resultado['trabalhos']} trabalhos)")
    print(f"  Variáveis: {resultado['variaveis']}   Restrições: {resultado['restricoes']}")
    print(f"  Status: {resultado['status']}")
    print(f"  Valor da solução: {resultado['valor']}")
    print(f"  Limitante superior: {resultado['limitante']:.2f}")
    print(f"  Gap: {resultado['gap']}%")
    print(f"  Tempo: {resultado['tempo']} s")

    if resultado["sessoes"] is None:
        return
    # Mostra cada sessão com seus trabalhos (numerados a partir de 1, como
    # no arquivo da instância) e o benefício que ela gerou.
    print("  Programação (trabalhos numerados a partir de 1):")
    for s, trabalhos in enumerate(resultado["sessoes"]):
        sessao = inst.sessoes[s]
        beneficio = sum(inst.b[i][j] for i in trabalhos for j in trabalhos if i < j)
        lista = ", ".join(str(i + 1) for i in trabalhos)
        print(f"    sessão {s} (dia {sessao['dia'] + 1}, horário {sessao['horario'] + 1}): "
              f"[{lista}]  benefício {beneficio}")


if __name__ == "__main__":
    # Lê os argumentos da linha de comando:
    #   sys.argv[1] -> caminho da instância
    #   sys.argv[2] -> (opcional) tempo limite em segundos
    if len(sys.argv) < 2:
        print("Uso: python3 codigo/modelo.py instancias/lars_30_1.txt [tempo_limite_em_segundos]")
        sys.exit(1)
    limite = int(sys.argv[2]) if len(sys.argv) > 2 else 1800
    inst = ler_instancia(sys.argv[1])
    imprimir(resolver(inst, tempo_limite=limite), inst)