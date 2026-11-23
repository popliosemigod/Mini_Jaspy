"""Repertorio local do robo: respostas prontas que NAO dependem do Claude.

Duas funcoes:
  1. atalho   - frases simples (oi, obrigado, que horas sao, tchau...) respondidas na hora, de graca e sem
                esperar o Claude (que leva alguns segundos). So vale para fala curta e inequivoca.
  2. reserva  - quando o Claude falha (limite de uso, sem internet, travou), o robo continua conversando com
                o que tem aqui, em vez de so pedir desculpas.

Cada resposta e um dict no mesmo formato do Claude: {"fala", "gesto", "olhar"}.
Para ampliar o repertorio basta acrescentar uma linha em REGRAS (ou, com a autoprogramacao, pedir ao robo).
"""
import random
import re
import time

DIAS = ["segunda-feira", "terca-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sabado", "domingo"]
MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]

# (expressao, [respostas possiveis], gesto). {hora} {data} {dia} {nome} {periodo} sao preenchidos na hora.
REGRAS = [
    (r"\b(bom\s+dia|boa\s+tarde|boa\s+noite)\b",
     ["{periodo}{nome}! Que bom te ver.", "{periodo}{nome}! Como voce esta?"], "sim"),
    (r"^\W*(oi+|ol[aá]|e\s+a[ií]|opa|eae|fala|salve|hey|hello)\b",
     ["Oi{nome}! Tudo bem?", "Olá{nome}! Estou por aqui.", "E aí{nome}! Pode falar."], "sim"),
    (r"\b(tudo\s+bem|como\s+(?:voc[eê]\s+)?(?:vai|est[aá]s?)|como\s+c[eê]\s+t[aá])\b",
     ["Tudo bem, obrigado por perguntar! E você?", "Estou ótimo, de mesa e funcionando. E você, como está?"],
     "sim"),
    (r"\b(obrigad[oa]|valeu|brigad[oa]|muito\s+obrigad[oa])\b",
     ["De nada!", "Por nada, é um prazer.", "Disponha!"], "sim"),
    (r"\b(tchau|at[eé]\s+(?:logo|mais|amanh[aã])|falou|at[eé]\s+a\s+pr[oó]xima|vou\s+embora)\b",
     ["Tchau{nome}! Até a próxima.", "Até mais! Volte logo."], "sim"),
    (r"\bque\s+horas?\s+s[aã]o\b|\bque\s+hora\s+[eé]\b|\bhoras?\s+s[aã]o\b|\bme\s+diz\s+as?\s+horas?\b",
     ["Agora são {hora}."], "nenhum"),
    (r"\b(que\s+dia\s+[eé]\s+hoje|qual\s+[eé]\s+a\s+data|que\s+data|dia\s+da\s+semana|hoje\s+[eé]\s+que\s+dia)\b",
     ["Hoje é {dia}, {data}."], "nenhum"),
    (r"\b(qual\s+(?:[eé]\s+)?(?:o\s+)?seu\s+nome|como\s+(?:voc[eê]\s+)?se\s+chama|quem\s+[eé]\s+voc[eê]|quem\s+te\s+criou)\b",
     ["Eu sou o Jaspy, um robô de mesa. Fui criado pelo meu dono, usando o Claude, da Anthropic."], "curioso"),
    (r"\b(o\s+que\s+(?:voc[eê]\s+)?(?:sabe|pode|consegue)\s+fazer|para\s+que\s+voc[eê]\s+serve|me\s+ajuda|"
     r"o\s+que\s+voc[eê]\s+faz)\b",
     ["Eu converso, enxergo pela câmera, reconheço rostos, mexo o pescoço e toco músicas. "
      "Se alguém me chamar pelo nome, eu obedeço na hora."], "curioso"),
    (r"\b(conta\s+uma?\s+piada|me\s+faz\s+rir|piada)\b",
     ["Por que o computador foi ao médico? Porque estava com vírus!",
      "O que o zero disse para o oito? Que cinto bonito!",
      "Por que o livro de matemática ficou triste? Porque tinha muitos problemas."], "sim"),
    (r"\b(voc[eê]\s+[eé]\s+(?:legal|lindo|incr[ií]vel|[oó]timo|inteligente|esperto)|gosto\s+de\s+voc[eê]|"
     r"parab[eé]ns)\b",
     ["Que gentileza! Fico feliz de ouvir isso.", "Obrigado, você também é ótimo!"], "sim"),
    (r"\b(voc[eê]\s+est[aá]\s+me\s+ouvindo|est[aá]\s+me\s+ouvindo|me\s+escuta|voc[eê]\s+me\s+ouve)\b",
     ["Estou te ouvindo sim!", "Ouvindo cada palavra."], "sim"),
    (r"\b(teste|testando|um\s+dois\s+tr[eê]s)\b",
     ["Recebi, está tudo funcionando.", "Teste ok, estou te ouvindo bem."], "sim"),
    # Sem regras para "sim"/"nao": sao respostas a uma pergunta do Claude (ex.: "posso gravar?") e so ele tem o contexto.
]
_REGRAS = [(re.compile(r, re.I), resp, g) for r, resp, g in REGRAS]

# Palavras que mostram que a pessoa quer algo que so o Claude resolve (ver, programar, musica, ensinar...).
# Se aparecerem, o atalho NAO responde sozinho.
PRECISA_DO_CLAUDE = re.compile(
    r"\b(v[eê]|ver|olh[ae]|c[aâ]mera|foto|rosto|apren[dz]|memoriz|esquec|programa|grav[ae]|toca|m[uú]sica|"
    r"a\s+partir\s+de\s+agora|quando\s+eu\s+disser|mexe|vira|gira|olha\s+para)\b", re.I)

# Quando nao ha regra e o Claude esta fora do ar.
SEM_CLAUDE = [
    "Meu cérebro está sem conexão agora, então só consigo respostas simples. Posso dizer as horas, a data e contar uma piada.",
    "Estou sem acesso ao meu cérebro principal no momento. Pergunte as horas, a data, ou peça uma piada.",
    "Não consegui pensar nisso agora, meu cérebro está fora do ar. Tente de novo daqui a pouco.",
]


def _periodo():
    h = time.localtime().tm_hour
    return "Bom dia" if h < 12 else ("Boa tarde" if h < 18 else "Boa noite")


def _nome(faces):
    if faces and faces.get("list"):
        nomes = [f.get("name") for f in faces["list"] if f.get("name") and f.get("name") != "?"]
        if nomes:
            return ", " + nomes[0]
    return ""


def _preenche(txt, faces):
    t = time.localtime()
    hora = f"{t.tm_hour} horas e {t.tm_min} minutos" if t.tm_min else f"{t.tm_hour} horas em ponto"
    if t.tm_hour == 1:
        hora = hora.replace("1 horas", "1 hora")
    return (txt.replace("{hora}", hora)
            .replace("{dia}", DIAS[t.tm_wday])
            .replace("{data}", f"{t.tm_mday} de {MESES[t.tm_mon - 1]} de {t.tm_year}")
            .replace("{periodo}", _periodo())
            .replace("{nome}", _nome(faces)))


_ultima = {}


def _escolhe(idx, opcoes):
    """Nao repete a mesma frase duas vezes seguidas."""
    pool = [o for o in opcoes if o != _ultima.get(idx)] or opcoes
    r = random.choice(pool)
    _ultima[idx] = r
    return r


def procura(heard, faces=None, max_palavras=8):
    """Resposta pronta para fala curta e inequivoca; None se for coisa para o Claude."""
    t = (heard or "").strip()
    if not t or len(t.split()) > max_palavras or PRECISA_DO_CLAUDE.search(t):
        return None
    for i, (rx, resp, gesto) in enumerate(_REGRAS):
        if rx.search(t):
            return {"fala": _preenche(_escolhe(i, resp), faces), "gesto": gesto, "olhar": None, "local": True}
    return None


def reserva(heard, faces=None):
    """Claude fora do ar: tenta o repertorio (sem limite de palavras) e, se nao houver regra, avisa."""
    t = (heard or "").strip()
    if t and not PRECISA_DO_CLAUDE.search(t):
        for i, (rx, resp, gesto) in enumerate(_REGRAS):
            if rx.search(t):
                return {"fala": _preenche(_escolhe(i, resp), faces), "gesto": gesto, "olhar": None, "local": True}
    return {"fala": _escolhe(-1, SEM_CLAUDE), "gesto": "curioso", "olhar": None, "local": True, "generica": True}


if __name__ == "__main__":  # python repertorio.py "que horas sao"
    import sys
    for f in sys.argv[1:] or ["oi", "que horas sao", "conta uma piada", "obrigado", "qual o sentido da vida"]:
        print(f"{f!r:32} ->", procura(f) or reserva(f))
