"""Converte o transcript exportado do Claude (zip com transcript.jsonl) num Markdown legivel:
mensagens do usuario, respostas do Claude e uma linha por ferramenta usada.
Uso: python ferramentas/conversa_para_md.py historico/conversa_completa_....zip historico/conversa_legivel.md"""
import json, re, sys, zipfile

src, out = sys.argv[1], sys.argv[2]
lines = zipfile.ZipFile(src).read("transcript.jsonl").decode("utf-8").splitlines()

# Senhas que NUNCA podem ir para o Markdown (o repositorio no GitHub e publico):
# todas as senhas do cam/src/wifi_redes.h local sao trocadas por [senha removida].
import os
_wf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cam", "src", "wifi_redes.h")
SECRETS = re.findall(r'\{\s*"[^"]*"\s*,\s*"([^"]+)"\s*\}', open(_wf, encoding="utf-8").read()) if os.path.exists(_wf) else []
SECRETS = [s for s in SECRETS if s and s != "SENHA_DA_REDE"]


def scrub(t):
    for s in SECRETS:
        t = t.replace(s, "[senha removida]")
    return t


def clean_user_text(t):
    t = re.sub(r"<system-reminder>.*?</system-reminder>", "", t, flags=re.S)
    t = re.sub(r"<(command|local-command)[^>]*>.*?</\1[^>]*>", "", t, flags=re.S)
    return t.strip()


md = ["# Conversa completa — Robô ESP32-S3 com o Claude como cérebro",
      "",
      "Versão legível do transcript exportado (`conversa_completa_*.zip`). Mostra as mensagens do usuário,",
      "as respostas do Claude e uma linha por ferramenta usada (sem as saídas das ferramentas).",
      "O resumo organizado do projeto está em `RELATORIO_CONTINUIDADE.md`.",
      ""]
seen = set()
for l in lines:
    try:
        j = json.loads(l)
    except ValueError:
        continue
    typ, msg = j.get("type"), j.get("message")
    if typ not in ("user", "assistant") or not isinstance(msg, dict):
        continue
    uid = j.get("uuid")
    if uid in seen:
        continue
    seen.add(uid)
    content = msg.get("content")
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
    ts = (j.get("timestamp") or "")[:16].replace("T", " ")
    if typ == "user":
        texts = [clean_user_text(b.get("text", "")) for b in blocks if b.get("type") == "text"]
        texts = [t for t in texts if t]
        if texts:
            md += ["", "---", "", f"## 🧑 Usuário ({ts})", "", *texts, ""]
    else:
        for b in blocks:
            if b.get("type") == "text" and b.get("text", "").strip():
                md += ["", f"**🤖 Claude:**", "", b["text"].strip(), ""]
            elif b.get("type") == "tool_use":
                inp = b.get("input") or {}
                desc = inp.get("description") or inp.get("command") or inp.get("file_path") or inp.get("pattern") or ""
                desc = str(desc).replace("\n", " ")[:160]
                name = b.get("name", "").replace("mcp__ccd_turn__", "").replace("mcp__", "")
                if name in ("update_plan",):
                    continue
                md.append(f"- 🔧 `{name}`: {desc}")
open(out, "w", encoding="utf-8").write(scrub("\n".join(md)) + "\n")
print(f"{out}: {len(md)} linhas, {len(SECRETS)} senhas removidas do texto")
