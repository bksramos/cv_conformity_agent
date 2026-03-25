# ============================================================
# Motor de diagnóstico e melhoria de clareza de currículos
# ============================================================
from __future__ import annotations
import json
import re
from typing import Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from models.cv_model import CVProfile
from models.jd_model import JobDescription
from models.cv_improvement import (
    CVDiagnosis, CVImprovementResult, DiagnosticIssue,
    ImprovedSection, Severity, SEVERITY_SCORE_PENALTY,
)

# ── Prompts ───────────────────────────────────────────────────────────────────

_IMPROVEMENT_SYSTEM = """\
Você é um especialista em redação de currículos profissionais.
Sua missão é REESCREVER (nunca inventar) partes de currículos para torná-las mais \
impactantes, claras e alinhadas com o mercado.

═══ REGRAS ABSOLUTAS ═══
- NUNCA adicione habilidades, responsabilidades ou conquistas que não estejam no texto original
- NUNCA mude datas, nomes de empresas ou títulos de cargo
- NUNCA invente certificações, projetos ou resultados numéricos que não existam
- APENAS melhore vocabulário, use verbos de ação mais fortes e reorganize para clareza
- Se uma keyword da vaga alvo já existe implicitamente no texto, PODE torná-la explícita
- Responda APENAS com JSON válido, sem markdown

═══ OPERAÇÕES PERMITIDAS ═══
✅ Substituir verbos fracos por verbos de ação ("fiz" → "desenvolvi", "ajudei" → "colaborei")
✅ Destacar resultados que já existem ("melhorei o sistema" → "otimizei o sistema reduzindo X" SE X já estava mencionado)
✅ Tornar responsabilidades implícitas explícitas se estavam claramente subentendidas
✅ Adicionar keywords da vaga SE a competência já está descrita no texto original
✅ Dividir parágrafos longos em bullets concisos
❌ Adicionar qualquer informação nova
❌ Inflar resultados ou responsabilidades além do que está escrito
"""

_SUMMARY_PROMPT = """\
Reescreva o sumário profissional abaixo para ser mais impactante e claro.
NÃO adicione experiências, skills ou conquistas que não estejam no original.

Sumário original:
{summary}

Contexto do candidato (use apenas para calibrar tom):
- Senioridade: {seniority}
- Anos de experiência: {years}
- Top skills: {skills}
{jd_context}

Retorne APENAS este JSON:
{{
  "improved": "sumário reescrito",
  "changes_made": ["descrição de cada mudança feita"],
  "keywords_added": ["keywords da vaga inseridas, se houver"]
}}
"""

_EXPERIENCE_PROMPT = """\
Reescreva a descrição desta experiência profissional para ser mais impactante.
NÃO adicione responsabilidades, projetos ou resultados que não estejam no texto original.

Cargo: {role}
Empresa: {company}
Descrição original:
{description}

Tecnologias mencionadas: {technologies}
{jd_context}

Retorne APENAS este JSON:
{{
  "improved": "descrição reescrita",
  "changes_made": ["descrição de cada mudança feita"],
  "keywords_added": ["keywords da vaga inseridas, se houver"]
}}
"""


class CVImprovementAgent:

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=settings.ollama_timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    # ── Entry points ──────────────────────────────────────────────────────────

    def diagnose(self, profile: CVProfile) -> CVDiagnosis:
        """
        Análise puramente determinística baseada no contrato de confiança.
        Não chama LLM — é instantânea.
        """
        logger.info(
            f"[CVImprovement] Diagnosticando '{profile.candidate_name}' | "
            f"overall_conf={profile.extraction_confidence:.2f}"
        )
        issues = []
        issues.extend(self._diagnose_experience(profile))
        issues.extend(self._diagnose_skills(profile))
        issues.extend(self._diagnose_seniority(profile))
        issues.extend(self._diagnose_languages(profile))
        issues.extend(self._diagnose_general(profile))

        # Ordena: CRITICAL → WARNING → INFO
        severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
        issues.sort(key=lambda i: severity_order[i.severity])

        score    = self._calc_quality_score(issues, profile)
        is_ready = not any(i.severity == Severity.CRITICAL for i in issues) \
                   and profile.extraction_confidence >= 0.60

        n_crit = sum(1 for i in issues if i.severity == Severity.CRITICAL)
        n_warn = sum(1 for i in issues if i.severity == Severity.WARNING)
        n_info = sum(1 for i in issues if i.severity == Severity.INFO)

        if n_crit > 0:
            summary = (
                f"Currículo com {n_crit} problema(s) crítico(s) que impedem uma análise "
                f"precisa de conformidade. Corrija-os antes de usar o sistema de matching."
            )
        elif n_warn > 0:
            summary = (
                f"Currículo funcional mas com {n_warn} ponto(s) de atenção que reduzem "
                f"a precisão da análise. Melhorias recomendadas."
            )
        else:
            summary = (
                f"Currículo bem estruturado com {n_info} sugestão(ões) de melhoria. "
                f"Pronto para análise de conformidade."
            )

        logger.info(
            f"[CVImprovement] Diagnóstico concluído | score={score:.0f} | "
            f"críticos={n_crit} | avisos={n_warn} | info={n_info} | "
            f"pronto_matching={is_ready}"
        )
        return CVDiagnosis(
            issues=issues,
            cv_quality_score=score,
            is_ready_for_matching=is_ready,
            summary=summary,
        )

    async def improve_clarity(
        self,
        profile: CVProfile,
        jd: Optional[JobDescription] = None,
    ) -> CVImprovementResult:
        """
        Melhora clareza das descrições via LLM.
        Opera apenas sobre o que já existe — nunca inventa conteúdo.
        """
        logger.info(
            f"[CVImprovement] Melhorando clareza de '{profile.candidate_name}' | "
            f"jd='{jd.title if jd else 'sem vaga alvo'}'"
        )
        diagnosis         = self.diagnose(profile)
        improved_sections = []
        jd_context        = self._build_jd_context(jd)

        # 1. Sumário
        if profile.summary and len(profile.summary) > 20:
            section = await self._improve_summary(profile, jd_context)
            if section:
                improved_sections.append(section)

        # 2. Experiências com descrição
        for exp in profile.experiences:
            if not exp.description or len(exp.description.strip()) < 30:
                logger.debug(
                    f"[CVImprovement] Pulando exp '{exp.role}' — "
                    f"descrição muito curta ou ausente"
                )
                continue
            section = await self._improve_experience(exp, jd_context)
            if section:
                improved_sections.append(section)

        # 3. Dicas gerais baseadas no diagnóstico
        tips = self._general_tips(diagnosis, jd)

        logger.info(
            f"[CVImprovement] Melhoria concluída | "
            f"seções melhoradas={len(improved_sections)}"
        )
        return CVImprovementResult(
            diagnosis         = diagnosis,
            improved_sections = improved_sections,
            jd_title          = jd.title if jd else None,
            general_tips      = tips,
        )

    # ── Diagnóstico por seção ─────────────────────────────────────────────────

    def _diagnose_experience(self, p: CVProfile) -> list[DiagnosticIssue]:
        issues = []

        if not p.experiences:
            issues.append(DiagnosticIssue(
                section="experience", severity=Severity.CRITICAL,
                title="Nenhuma experiência profissional identificada",
                description="O agent não conseguiu extrair nenhuma experiência do currículo.",
                action="Verifique se as experiências estão em uma seção claramente identificada "
                       "(ex: 'Experiência Profissional', 'Work Experience') e se empresa e cargo estão presentes.",
            ))
            return issues

        if p.experience_source == "no_data":
            issues.append(DiagnosticIssue(
                section="experience", severity=Severity.CRITICAL,
                title="Datas e durações de experiências ausentes",
                description=f"Nenhuma das {len(p.experiences)} experiência(s) tem datas ou "
                            f"duração informada. O cálculo de senioridade fica impossibilitado.",
                action="Adicione período de início e fim em cada experiência (ex: Jan 2020 – Mar 2023). "
                       "Para emprego atual, use 'Presente' ou 'Atual'.",
                affected_items=[f"{e.role} @ {e.company}" for e in p.experiences],
            ))

        elif p.experience_source == "stated_only":
            affected = [
                f"{e.role} @ {e.company}"
                for e in p.experiences
                if e.duration_source == "stated"
            ]
            issues.append(DiagnosticIssue(
                section="experience", severity=Severity.WARNING,
                title="Durações declaradas sem datas completas",
                description="Algumas experiências informam duração (ex: '2 anos') mas sem datas "
                            "de início e fim. Isso reduz a confiabilidade do cálculo de experiência.",
                action="Substitua '2 anos' por datas reais (ex: Jan 2021 – Dez 2022). "
                       "Datas completas aumentam a confiança da análise de 0.7 para 1.0.",
                affected_items=affected,
            ))

        elif p.experience_source == "partial_dated":
            undated = [
                f"{e.role} @ {e.company}"
                for e in p.experiences
                if not e.start_date and not e.duration_months
            ]
            if undated:
                issues.append(DiagnosticIssue(
                    section="experience", severity=Severity.WARNING,
                    title=f"{len(undated)} experiência(s) sem datas ou duração",
                    description="Algumas experiências não têm nenhuma informação temporal, "
                                "sendo ignoradas no cálculo total de anos.",
                    action="Adicione pelo menos o período aproximado (ex: 2019 – 2020).",
                    affected_items=undated,
                ))

        # Experiências com descrição muito curta
        short_desc = [
            f"{e.role} @ {e.company}"
            for e in p.experiences
            if len((e.description or "").strip()) < 30
        ]
        if short_desc:
            issues.append(DiagnosticIssue(
                section="experience", severity=Severity.INFO,
                title=f"{len(short_desc)} experiência(s) com descrição insuficiente",
                description="Descrições curtas reduzem a capacidade do sistema de inferir "
                            "skills e fazer matches com vagas.",
                action="Adicione 2–4 bullets descrevendo responsabilidades e tecnologias usadas.",
                affected_items=short_desc,
            ))

        # Experiências sem tecnologias
        no_tech = [
            f"{e.role} @ {e.company}"
            for e in p.experiences
            if not e.technologies and len((e.description or "").strip()) > 30
        ]
        if no_tech:
            issues.append(DiagnosticIssue(
                section="experience", severity=Severity.INFO,
                title=f"{len(no_tech)} experiência(s) sem tecnologias mencionadas",
                description="Mencionar tecnologias nas descrições de experiência aumenta "
                            "significativamente o score de skills no matching.",
                action="Inclua as ferramentas e tecnologias usadas em cada experiência.",
                affected_items=no_tech,
            ))

        return issues

    def _diagnose_skills(self, p: CVProfile) -> list[DiagnosticIssue]:
        issues = []

        if not p.hard_skills:
            issues.append(DiagnosticIssue(
                section="skills", severity=Severity.CRITICAL,
                title="Nenhuma hard skill identificada",
                description="O agent não encontrou nenhuma skill técnica no currículo.",
                action="Adicione uma seção explícita de competências técnicas "
                       "(ex: 'Skills', 'Tecnologias', 'Competências') com as ferramentas que você domina.",
            ))
            return issues

        if len(p.hard_skills) < 5:
            issues.append(DiagnosticIssue(
                section="skills", severity=Severity.WARNING,
                title=f"Apenas {len(p.hard_skills)} skill(s) identificada(s)",
                description="Poucos skills detectados. Isso pode indicar que a seção de "
                            "competências está ausente ou muito informal.",
                action="Liste explicitamente suas principais tecnologias em uma seção dedicada.",
            ))

        # Skills só inferidas (não declaradas explicitamente)
        only_inferred = [
            s.name for s in p.hard_skills
            if s.source in ("inferred_from_context",) and not s.mentioned_in_experience
        ]
        if only_inferred:
            issues.append(DiagnosticIssue(
                section="skills", severity=Severity.INFO,
                title=f"{len(only_inferred)} skill(s) apenas inferida(s) por contexto",
                description="Essas skills foram detectadas pelo agente mas não estão "
                            "listadas explicitamente, o que reduz a confiança da extração.",
                action="Adicione essas skills explicitamente na seção de competências.",
                affected_items=only_inferred,
            ))

        if p.skills_confidence < 0.6:
            issues.append(DiagnosticIssue(
                section="skills", severity=Severity.WARNING,
                title=f"Confiança baixa na extração de skills ({p.skills_confidence:.0%})",
                description="O agente teve dificuldade para extrair skills com confiança. "
                            "Isso pode indicar que as skills estão misturadas no texto.",
                action="Crie uma seção dedicada com cada skill em uma linha separada ou em lista.",
            ))

        return issues

    def _diagnose_seniority(self, p: CVProfile) -> list[DiagnosticIssue]:
        issues = []

        if p.seniority_source == "no_data":
            issues.append(DiagnosticIssue(
                section="seniority", severity=Severity.WARNING,
                title="Senioridade não pôde ser determinada",
                description="Sem datas de experiência nem indicadores de nível no currículo, "
                            "a senioridade fica como NAO_INFORMADO, prejudicando o matching.",
                action="Adicione datas às experiências ou inclua o nível (ex: 'Sênior') "
                       "no título do cargo.",
            ))
        elif p.seniority_source == "title_only":
            issues.append(DiagnosticIssue(
                section="seniority", severity=Severity.INFO,
                title="Senioridade inferida apenas pelo título do cargo",
                description=f"'{p.seniority_inferred.value}' foi inferido pelo título, mas sem "
                            f"datas de experiência para validar (confiança: {p.seniority_confidence:.0%}).",
                action="Adicione datas às experiências para aumentar a confiança da senioridade de "
                       f"{p.seniority_confidence:.0%} para ~95%.",
            ))
        elif p.seniority_confidence < 0.65:
            issues.append(DiagnosticIssue(
                section="seniority", severity=Severity.INFO,
                title=f"Senioridade com confiança reduzida ({p.seniority_confidence:.0%})",
                description=f"Inferida como '{p.seniority_inferred.value}' via '{p.seniority_source}', "
                            f"mas título e anos de experiência divergem.",
                action="Verifique se o título do cargo e o tempo de experiência estão alinhados.",
            ))

        return issues

    def _diagnose_languages(self, p: CVProfile) -> list[DiagnosticIssue]:
        if not p.languages:
            return [DiagnosticIssue(
                section="languages", severity=Severity.INFO,
                title="Nenhum idioma identificado",
                description="A seção de idiomas não foi encontrada ou está ausente.",
                action="Adicione uma seção de idiomas com o nível de cada um "
                       "(ex: 'Inglês — Avançado', 'Espanhol — Básico').",
            )]
        return []

    def _diagnose_general(self, p: CVProfile) -> list[DiagnosticIssue]:
        issues = []

        if not p.summary:
            issues.append(DiagnosticIssue(
                section="general", severity=Severity.INFO,
                title="Sumário profissional ausente",
                description="Um sumário bem escrito aumenta o contexto disponível para o agente "
                            "e para recrutadores.",
                action="Adicione 3–5 linhas resumindo sua especialidade, anos de experiência "
                       "e principais competências.",
            ))

        if not p.education:
            issues.append(DiagnosticIssue(
                section="general", severity=Severity.INFO,
                title="Formação acadêmica não identificada",
                description="A seção de formação não foi encontrada.",
                action="Adicione uma seção de formação com grau, curso, instituição e ano de conclusão.",
            ))

        if p.extraction_warnings:
            for w in p.extraction_warnings:
                issues.append(DiagnosticIssue(
                    section="general", severity=Severity.WARNING,
                    title="Aviso da extração",
                    description=w,
                    action="Revise a seção correspondente do currículo para clareza estrutural.",
                ))

        return issues

    # ── Score de qualidade ────────────────────────────────────────────────────

    def _calc_quality_score(
        self, issues: list[DiagnosticIssue], p: CVProfile
    ) -> float:
        score = 100.0
        for issue in issues:
            score -= SEVERITY_SCORE_PENALTY[issue.severity]
        # Bonus por campos com alta confiança
        if p.experience_confidence >= 0.9:
            score = min(score + 5, 100)
        if p.skills_confidence >= 0.9:
            score = min(score + 3, 100)
        return max(round(score, 1), 0.0)

    # ── Melhoria de clareza ───────────────────────────────────────────────────

    async def _improve_summary(
        self, profile: CVProfile, jd_context: str
    ) -> Optional[ImprovedSection]:
        top_skills = ", ".join(s.name for s in profile.hard_skills[:8])
        prompt = _SUMMARY_PROMPT.format(
            summary   = profile.summary,
            seniority = profile.seniority_inferred.value,
            years     = profile.total_experience_years,
            skills    = top_skills or "não informado",
            jd_context= jd_context,
        )
        result = await self._call_llm(prompt)
        if not result:
            return None
        return ImprovedSection(
            section       = "summary",
            role          = "Sumário Profissional",
            original      = profile.summary or "",
            improved      = result.get("improved", ""),
            changes_made  = result.get("changes_made", []),
            keywords_added= result.get("keywords_added", []),
        )

    async def _improve_experience(
        self, exp, jd_context: str
    ) -> Optional[ImprovedSection]:
        prompt = _EXPERIENCE_PROMPT.format(
            role        = exp.role,
            company     = exp.company,
            description = exp.description,
            technologies= ", ".join(exp.technologies) if exp.technologies else "não informado",
            jd_context  = jd_context,
        )
        result = await self._call_llm(prompt)
        if not result:
            return None
        return ImprovedSection(
            section       = "experience",
            role          = f"{exp.role} @ {exp.company}",
            original      = exp.description,
            improved      = result.get("improved", ""),
            changes_made  = result.get("changes_made", []),
            keywords_added= result.get("keywords_added", []),
        )

    # ── Dicas gerais ──────────────────────────────────────────────────────────

    def _general_tips(
        self, diagnosis: CVDiagnosis, jd: Optional[JobDescription]
    ) -> list[str]:
        tips = []
        sections = diagnosis.by_section

        if "experience" in sections and any(
            i.severity == Severity.CRITICAL for i in sections["experience"]
        ):
            tips.append(
                "Priorize adicionar datas completas às experiências — "
                "isso é o fator que mais impacta a precisão do matching."
            )
        if "skills" in sections:
            tips.append(
                "Mantenha uma seção de skills separada das experiências, "
                "com cada tecnologia em item próprio."
            )
        if jd:
            jd_req = {s.name.lower() for s in jd.required_skills if s.is_required}
            cv_ski = {s.name.lower() for s in diagnosis.issues}  # placeholder
            if jd_req:
                tips.append(
                    f"Para a vaga '{jd.title}', certifique-se de que as skills obrigatórias "
                    f"estão explicitamente listadas no currículo."
                )
        if diagnosis.cv_quality_score < 60:
            tips.append(
                "Um currículo bem estruturado com datas, descrições detalhadas e seções "
                "claras aumenta significativamente a precisão da análise de conformidade."
            )
        return tips

    def _build_jd_context(self, jd: Optional[JobDescription]) -> str:
        if not jd:
            return ""
        req_skills = [s.name for s in jd.required_skills if s.is_required][:8]
        return (
            f"\nVaga alvo: {jd.title}\n"
            f"Skills requeridas: {', '.join(req_skills) or 'não informado'}\n"
            f"Senioridade esperada: {jd.seniority.value}\n"
            f"Use essas keywords APENAS se a competência já existe no texto original."
        )

    # ── LLM ───────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=6), reraise=False)
    async def _call_llm(self, prompt: str) -> Optional[dict]:
        try:
            resp = await self._client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 1024, "num_ctx": 4096},
                    "messages": [
                        {"role": "system", "content": _IMPROVEMENT_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
            return self._parse_response(raw)
        except Exception as e:
            logger.error(f"[CVImprovement] Erro LLM: {e}")
            return None

    def _parse_response(self, raw: str) -> Optional[dict]:
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        match   = re.search(r"\{[\s\S]*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None