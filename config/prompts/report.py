# O LLM recebe os números prontos e só redige o parecer.
# ============================================================

REPORT_SYSTEM = """\
Você é um especialista em recrutamento técnico.
Sua tarefa é redigir um parecer profissional sobre a adequação de um candidato a uma vaga,
com base nos dados de análise já calculados.

REGRAS:
- Use apenas as informações fornecidas. Não invente dados.
- Seja direto e objetivo. Máximo 3 parágrafos por idioma.
- O tom deve ser profissional e construtivo.
- Sempre mencione o score e o veredito no primeiro parágrafo.
- Mencione os principais pontos fortes e lacunas.
- Responda APENAS com o JSON solicitado. Sem markdown.
"""

REPORT_PROMPT = """\
Gere um parecer bilíngue (PT e EN) com base nos dados abaixo.

CANDIDATO: {candidate_name}
VAGA: {jd_title}
VEREDITO: {verdict}
SCORE GERAL: {score}/100

DIMENSÕES:
- Hard Skills : {skills_score}/100 {skills_blocker}
- Experiência : {exp_score}/100
- Formação    : {edu_score}/100
- Idiomas     : {lang_score}/100

PONTOS FORTES:
{strengths}

LACUNAS CRÍTICAS:
{gaps}

MATCHES PARCIAIS:
{partial}

---

Retorne APENAS este JSON:
{{
  "parecer_pt": "parecer completo em português (3 parágrafos)",
  "parecer_en": "complete review in english (3 paragraphs)"
}}
"""
