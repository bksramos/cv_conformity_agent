# ============================================================
# Converte PDF de currículo → CVProfile estruturado via Llama 3
# Análogo ao vt_extraction_agent do Feito/Conferido
# ============================================================
from __future__ import annotations
import json
import re
from datetime import date, datetime
from typing import Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from config.feature_flags import flags
from config.prompts.cv_extraction import CV_EXTRACTION_SYSTEM, CV_EXTRACTION_PROMPT
from extractors.pdf_extractor import PDFExtractor, RawCVText
from extractors.text_cleaner import CVTextCleaner
from extractors.section_detector import CVSectionDetector
from models.cv_model import CVProfile, Skill, WorkExperience, Education, Language
from models.verdict import SeniorityLevel, SkillLevel, LanguageProficiency


class CVExtractionAgent:

    def __init__(self):
        self._pdf_extractor    = PDFExtractor()
        self._text_cleaner     = CVTextCleaner()
        self._section_detector = CVSectionDetector()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=settings.ollama_timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    # ── Entry point ───────────────────────────────────────────────────────

    async def extract_from_bytes(self, pdf_bytes: bytes) -> CVProfile:
        logger.debug(f"[CVExtraction] Iniciando extração — PDF size={len(pdf_bytes)} bytes")

        # 1. Extração do PDF
        raw: RawCVText = self._pdf_extractor.extract(pdf_bytes)
        logger.info(
            f"[CVExtraction] PDF extraído | "
            f"estratégia={raw.strategy} | páginas={raw.num_pages} | chars={len(raw.text)}"
        )
        if raw.warnings:
            logger.warning(f"[CVExtraction] Avisos PDF: {raw.warnings}")

        if raw.strategy == "failed":
            logger.error("[CVExtraction] ❌ Falha total na extração do PDF")
            return self._empty_profile(raw.pdf_hash, raw.warnings)

        # 2. Limpeza
        contact_hints = self._text_cleaner.extract_contact_hints(raw.text)
        cleaned_text  = self._text_cleaner.clean(raw.text)
        logger.debug(
            f"[CVExtraction] Texto limpo | chars={len(cleaned_text)} | "
            f"emails_detectados={contact_hints['emails']}"
        )

        # 3. Seções
        sections         = self._section_detector.detect(cleaned_text)
        structured_input = self._section_detector.build_structured_input(sections)
        logger.debug(f"[CVExtraction] Seções detectadas: {list(sections.keys())}")

        # 4. LLM
        logger.debug("[CVExtraction] Chamando LLM...")
        raw_response = await self._call_llm(structured_input)

        if not raw_response and flags.USE_LLM_FALLBACK_EXTRACTION:
            logger.warning("[CVExtraction] Resposta vazia — tentando fallback com texto completo")
            raw_response = await self._call_llm(cleaned_text)

        if not raw_response:
            logger.error("[CVExtraction] ❌ LLM não retornou resposta após retries")
            return self._empty_profile(raw.pdf_hash, raw.warnings + ["LLM falhou"])

        logger.debug(f"[CVExtraction] Resposta LLM (primeiros 500 chars): {raw_response[:500]}")

        # 5. Parse
        parsed = self._parse_llm_response(raw_response)
        if not parsed:
            logger.error("[CVExtraction] ❌ JSON inválido na resposta do LLM")
            return self._empty_profile(raw.pdf_hash, raw.warnings + ["JSON inválido"])

        self._log_parsed_json(parsed)

        # Injeta hints de contato se o LLM não encontrou
        if not parsed.get("email") and contact_hints["emails"]:
            parsed["email"] = contact_hints["emails"][0]
            logger.debug(f"[CVExtraction] Email injetado via hint: {parsed['email']}")

        # 6. Constrói perfil
        profile = self._build_profile(parsed, raw)
        profile.extraction_warnings.extend(raw.warnings)

        self._log_profile_contract(profile)

        if (
            flags.USE_LLM_FALLBACK_EXTRACTION
            and profile.extraction_confidence < flags.EXTRACTION_CONFIDENCE_THRESHOLD
        ):
            logger.warning(
                f"[CVExtraction] ⚠ Baixa confiança geral: {profile.extraction_confidence:.2f} "
                f"(threshold={flags.EXTRACTION_CONFIDENCE_THRESHOLD})"
            )

        logger.info(
            f"[CVExtraction] ✅ Extração concluída | "
            f"candidato='{profile.candidate_name}' | "
            f"skills={len(profile.hard_skills)} | "
            f"exp_years={profile.total_experience_years} | "
            f"exp_source={profile.experience_source} | "
            f"seniority={profile.seniority_inferred.value} | "
            f"seniority_source={profile.seniority_source} | "
            f"seniority_conf={profile.seniority_confidence:.2f} | "
            f"overall_conf={profile.extraction_confidence:.2f}"
        )
        if profile.extraction_warnings:
            logger.warning(f"[CVExtraction] Warnings: {profile.extraction_warnings}")

        return profile

    # ── LLM ───────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=False,
    )
    async def _call_llm(self, cv_text: str) -> Optional[str]:
        prompt = CV_EXTRACTION_PROMPT.format(cv_text=cv_text)
        logger.debug(f"[CVExtraction] Prompt size: {len(prompt)} chars")
        try:
            resp = await self._client.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                        "num_ctx": 8192,
                    },
                    "messages": [
                        {"role": "system", "content": CV_EXTRACTION_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            logger.debug(f"[CVExtraction] LLM respondeu | chars={len(content)}")
            return content
        except httpx.TimeoutException:
            logger.warning("[CVExtraction] Timeout — tentando novamente...")
            raise
        except Exception as e:
            logger.error(f"[CVExtraction] Erro ao chamar LLM: {e}")
            return None

    def _parse_llm_response(self, raw: str) -> Optional[dict]:
        """
        Pipeline de 4 tentativas para extrair JSON da resposta do LLM.

        1. Bloco markdown explícito  → ```json ... ```
        2. Bloco markdown sem tipo   → ``` { ... } ```
        3. Primeiro objeto JSON      → { ... }  (modo guloso — pega o maior match)
        4. Reparo de truncamento     → fecha chaves/colchetes abertos e tenta parsear
        """
        if not raw:
            logger.warning("[CVExtraction] Resposta do LLM vazia")
            return None

        # ── Tentativa 1: bloco ```json ... ``` (aceita sufixos como ```jsonc, ```json title=) ──
        json_str = self._extract_markdown_block(raw, "json")
        if json_str:
            result = self._try_parse(json_str, source="markdown_block")
            if result is not None:
                return result

        # ── Tentativa 2: bloco genérico ``` { ... } ``` ──────────────────────────────────────
        block_match = re.search(r"```\s*(\{[\s\S]*?\})\s*```", raw, re.DOTALL)
        if block_match:
            result = self._try_parse(block_match.group(1), source="generic_code_block")
            if result is not None:
                return result

        # ── Tentativa 3: primeiro objeto JSON bruto no texto ─────────────────────────────────
        json_match = re.search(r"\{[\s\S]*\}", raw, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result   = self._try_parse(json_str, source="raw_object")
            if result is not None:
                return result

            # ── Tentativa 4: JSON estava presente mas truncado — tenta reparar ──────────────
            logger.warning(
                f"[CVExtraction] JSON encontrado mas inválido — "
                f"tentando reparar truncamento (chars={len(json_str)})..."
            )
            repaired = self._repair_truncated_json(json_str)
            if repaired:
                logger.info(
                    f"[CVExtraction] ✅ JSON recuperado via reparo | "
                    f"campos: {list(repaired.keys())}"
                )
                return repaired

        logger.error(
            f"[CVExtraction] ❌ Todas as tentativas de extração falharam | "
            f"raw (primeiros 300 chars): {raw[:300]}"
        )
        return None

    # ── Helpers de parsing ────────────────────────────────────────────────

    @staticmethod
    def _extract_markdown_block(text: str, file_type: str) -> Optional[str]:
        """
        Extrai conteúdo de ```<file_type>[sufixos opcionais]\n...\n```.
        Aceita: ```json, ```jsonc, ```json title="x", etc.
        """
        pattern = rf"```{re.escape(file_type)}[^\n]*\n(.*?)\n```"
        match   = re.search(pattern, text, flags=re.DOTALL)
        return match.group(1).rstrip() if match else None

    def _try_parse(self, json_str: str, source: str) -> Optional[dict]:
        """Tenta json.loads e loga o resultado."""
        try:
            result = json.loads(json_str)
            logger.debug(f"[CVExtraction] JSON parseado via '{source}' | campos: {list(result.keys())}")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"[CVExtraction] '{source}' falhou: {e.msg} (pos={e.pos})")
            return None

    def _repair_truncated_json(self, json_str: str) -> Optional[dict]:
        """
        Recupera JSON truncado pelo limite de tokens do LLM.

        Retrocede até o último campo completo antes do ponto de falha
        e fecha as chaves/colchetes abertos que sobraram.
        """
        # Localiza o ponto exato de falha para limitar o fragmento
        try:
            json.loads(json_str)
            return None   # não estava truncado — outro problema
        except json.JSONDecodeError as e:
            error_pos = e.pos

        fragment = json_str[:error_pos]

        # Encontra o último campo completo (termina com vírgula precedida de valor fechado)
        last_valid = max(
            fragment.rfind('",'),
            fragment.rfind('],'),
            fragment.rfind('},'),
            fragment.rfind('true,'),
            fragment.rfind('false,'),
            fragment.rfind('null,'),
        )

        if last_valid == -1:
            logger.debug("[CVExtraction] _repair: nenhum campo completo encontrado antes do erro")
            return None

        truncated = fragment[:last_valid + 1].rstrip(",").rstrip()

        # Fecha estruturas abertas na ordem inversa
        open_braces   = max(truncated.count("{") - truncated.count("}"), 0)
        open_brackets = max(truncated.count("[") - truncated.count("]"), 0)
        closing       = ("]" * open_brackets) + ("}" * open_braces)

        for candidate in (truncated + closing, truncated + "}"):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        logger.debug("[CVExtraction] _repair: não foi possível fechar o JSON")
        return None

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_profile(self, data: dict, raw: RawCVText) -> CVProfile:

        def safe_seniority(v) -> SeniorityLevel:
            try:   return SeniorityLevel(v.upper()) if v else SeniorityLevel.NAO_INFORMADO
            except ValueError: return SeniorityLevel.NAO_INFORMADO

        def safe_skill_level(v) -> SkillLevel:
            try:   return SkillLevel(v.upper()) if v else SkillLevel.NAO_INFORMADO
            except ValueError: return SkillLevel.NAO_INFORMADO

        def safe_proficiency(v) -> LanguageProficiency:
            try:   return LanguageProficiency(v.upper()) if v else LanguageProficiency.BASICO
            except ValueError: return LanguageProficiency.BASICO

        def parse_date(v) -> Optional[date]:
            if not v:
                return None
            s = str(v).strip()

            # "Present", "Atual", "Presente", "Current", "Now" → None (emprego atual)
            if s.lower() in ("present", "atual", "presente", "current", "now", "–", "-", ""):
                return None

            # Normaliza separadores: "2022/09" → "2022-09", "09.2022" → "2022-09"
            s = re.sub(r"(\d{4})[/.](\d{1,2})$", r"\1-\2", s)
            s = re.sub(r"^(\d{1,2})[/.](\d{4})$", r"\2-\1", s)

            # Mapeia meses em português para inglês
            _PT_MONTHS = {
                "jan": "Jan", "fev": "Feb", "mar": "Mar", "abr": "Apr",
                "mai": "May", "jun": "Jun", "jul": "Jul", "ago": "Aug",
                "set": "Sep", "out": "Oct", "nov": "Nov", "dez": "Dec",
                "janeiro": "January", "fevereiro": "February", "março": "March",
                "abril": "April", "maio": "May", "junho": "June",
                "julho": "July", "agosto": "August", "setembro": "September",
                "outubro": "October", "novembro": "November", "dezembro": "December",
            }
            s_lower = s.lower()
            for pt, en in _PT_MONTHS.items():
                if s_lower.startswith(pt):
                    s = en + s[len(pt):]
                    break

            formats = [
                "%Y-%m",        # 2022-09
                "%Y",           # 2022       → dia 1 de janeiro → tratado como Jan do ano
                "%b %Y",        # Sep 2022   → dia 1 do mês
                "%B %Y",        # September 2022
                "%m/%Y",        # 09/2022
                "%m-%Y",        # 09-2022
                "%d %b %Y",     # 01 Sep 2022
                "%d %B %Y",     # 01 September 2022
                "%Y-%m-%d",     # 2022-09-01
            ]
            for fmt in formats:
                try:
                    # Sempre normaliza para o dia 1 do mês — o cálculo inclusivo
                    # de duração trata o mês inteiro independente do dia
                    return datetime.strptime(s, fmt).date().replace(day=1)
                except ValueError:
                    continue

            logger.debug(f"[CVExtraction] parse_date falhou para: {v!r} (normalizado: {s!r})")
            return None

        # ── Hard Skills — split de skills agrupadas ──────────────────────
        # Separadores usados pelo LLM para agrupar: '/', '+', ' and ', ' & '
        _SKILL_SPLIT_RE = re.compile(r"\s*/\s*|\s*\+\s*|\s+and\s+|\s*&\s*")
        # Tamanho mínimo para uma substring ser uma skill válida
        _MIN_SKILL_LEN = 2

        skills = []
        for s in (data.get("hard_skills") or []):
            if not s.get("name"):
                continue
            raw_name = s["name"].strip()

            # Decide se deve dividir: só divide se houver separador explícito
            # E se cada parte tiver comprimento mínimo (evita dividir "C/C++")
            parts = _SKILL_SPLIT_RE.split(raw_name)
            names_to_add = (
                [p.strip() for p in parts if len(p.strip()) >= _MIN_SKILL_LEN]
                if len(parts) > 1
                else [raw_name]
            )

            # "C/C++" não deve ser dividido — reune se alguma parte for <= 3 chars
            # e o original continha "C" ou "C++"
            if len(parts) > 1 and any(len(p.strip()) <= 3 for p in parts):
                names_to_add = [raw_name]

            for skill_name in names_to_add:
                skill = Skill(
                    name                    = skill_name,
                    level                   = safe_skill_level(s.get("level")),
                    years_of_use            = s.get("years_of_use"),
                    mentioned_in_experience = bool(s.get("mentioned_in_experience", False)),
                    aliases                 = [a.strip() for a in (s.get("aliases") or []) if a],
                    confidence              = float(s.get("confidence", 1.0)),
                    source                  = s.get("source", "explicit"),
                )
                logger.debug(
                    f"[CVExtraction]   skill: '{skill.name}' | "
                    f"level={skill.level.value} | conf={skill.confidence:.2f} | src={skill.source}"
                    + (f" [split de '{raw_name}']" if skill_name != raw_name else "")
                )
                skills.append(skill)

        # ── Experiências — mapeia campos do contrato ──────────────────────
        experiences = []
        for e in (data.get("experiences") or []):
            if not e.get("company") and not e.get("role"):
                continue
            start = parse_date(e.get("start_date"))
            end   = None if e.get("is_current") else parse_date(e.get("end_date"))
            exp = WorkExperience(
                company             = e.get("company", "").strip(),
                role                = e.get("role", "").strip(),
                start_date          = start,
                end_date            = end,
                duration_months     = e.get("duration_months"),
                description         = e.get("description", ""),
                technologies        = e.get("technologies") or [],
                domain              = e.get("domain"),
                # ── Contrato de confiança ─────────────────────────────────
                duration_confidence = float(e.get("duration_confidence", 1.0 if start else 0.7)),
                duration_source     = e.get("duration_source", "calculated" if start else "stated"),
            )
            logger.debug(
                f"[CVExtraction]   exp: '{exp.role}' @ '{exp.company}' | "
                f"start={exp.start_date} end={exp.end_date} | "
                f"duration={exp.duration_months}m | dur_conf={exp.duration_confidence:.2f}"
            )
            experiences.append(exp)

        # ── Formação ──────────────────────────────────────────────────────
        education = []
        for ed in (data.get("education") or []):
            if not ed.get("institution"):
                continue
            education.append(Education(
                degree           = ed.get("degree") or "",
                field_of_study   = ed.get("field_of_study") or "",
                institution      = (ed.get("institution") or "").strip(),
                graduation_year  = ed.get("graduation_year"),
                is_complete      = bool(ed.get("is_complete", True)),
            ))

        # ── Idiomas — normaliza nomes EN→PT e vice-versa ─────────────────
        _LANG_NORMALIZE: dict[str, str] = {
            # Inglês → Português
            "portuguese": "Português", "english": "Inglês", "spanish": "Espanhol",
            "french": "Francês", "german": "Alemão", "italian": "Italiano",
            "chinese": "Chinês", "japanese": "Japonês", "korean": "Coreano",
            "arabic": "Árabe", "russian": "Russo", "dutch": "Holandês",
            "mandarin": "Chinês (Mandarim)", "hindi": "Hindi",
            # Variações em PT já corretas (passam direto)
            "português": "Português", "inglês": "Inglês", "espanhol": "Espanhol",
            "francês": "Francês", "alemão": "Alemão",
        }
        languages = []
        for lang in (data.get("languages") or []):
            if not lang.get("name"):
                continue
            raw_lang_name = lang["name"].strip()
            normalized    = _LANG_NORMALIZE.get(raw_lang_name.lower(), raw_lang_name)
            if normalized != raw_lang_name:
                logger.debug(
                    f"[CVExtraction]   idioma normalizado: '{raw_lang_name}' → '{normalized}'"
                )
            languages.append(Language(
                name        = normalized,
                proficiency = safe_proficiency(lang.get("proficiency")),
                certified   = bool(lang.get("certified", False)),
            ))

        logger.debug(
            f"[CVExtraction] _build_profile | "
            f"skills={len(skills)} | exp={len(experiences)} | "
            f"edu={len(education)} | lang={len(languages)} | "
            f"llm_total_years={data.get('total_experience_years')} | "
            f"llm_seniority={data.get('seniority_inferred')} | "
            f"llm_seniority_conf={data.get('seniority_confidence')}"
        )

        # ── CVProfile — model_validator recalcula campos derivados ────────
        profile = CVProfile(
            pdf_hash               = raw.pdf_hash,
            candidate_name         = data.get("candidate_name") or "Desconhecido",
            email                  = data.get("email"),
            phone                  = data.get("phone"),
            location               = data.get("location"),
            linkedin_url           = data.get("linkedin_url"),
            summary                = data.get("summary"),
            hard_skills            = skills,
            soft_skills            = data.get("soft_skills") or [],
            experiences            = experiences,
            education              = education,
            certifications         = data.get("certifications") or [],
            languages              = languages,
            # LLM-provided — model_validator pode sobrescrever com lógica determinística
            seniority_inferred     = safe_seniority(data.get("seniority_inferred")),
            total_experience_years = float(data.get("total_experience_years") or 0),
            extraction_confidence  = float(data.get("extraction_confidence") or 0.5),
            extraction_strategy    = raw.strategy,
        )
        # Nota: model_validator já rodou. NÃO chamar calc_total_experience() aqui —
        # _recalc_experience() do validator já fez isso com a lógica de fallback.

        # Marca skills que aparecem nas experiências (cross-reference)
        exp_techs = {t.lower() for exp in profile.experiences for t in exp.technologies}
        for skill in profile.hard_skills:
            if skill.name.lower() in exp_techs and not skill.mentioned_in_experience:
                skill.mentioned_in_experience = True
                logger.debug(f"[CVExtraction]   skill '{skill.name}' marcada via exp_techs")

        return profile

    # ── Logging helpers ───────────────────────────────────────────────────

    def _log_parsed_json(self, parsed: dict):
        logger.debug(
            f"[CVExtraction] JSON parseado | "
            f"candidate={parsed.get('candidate_name')} | "
            f"skills_count={len(parsed.get('hard_skills') or [])} | "
            f"exp_count={len(parsed.get('experiences') or [])} | "
            f"edu_count={len(parsed.get('education') or [])} | "
            f"lang_count={len(parsed.get('languages') or [])} | "
            f"total_years={parsed.get('total_experience_years')} | "
            f"seniority={parsed.get('seniority_inferred')} | "
            f"seniority_conf={parsed.get('seniority_confidence')} | "
            f"extraction_conf={parsed.get('extraction_confidence')}"
        )
        if parsed.get("extraction_warnings"):
            logger.debug(f"[CVExtraction] Warnings do LLM: {parsed['extraction_warnings']}")

    def _log_profile_contract(self, profile: CVProfile):
        logger.debug(
            f"[CVExtraction] Contrato de confiança do CVProfile | "
            f"overall_conf={profile.extraction_confidence:.2f} | "
            f"skills_conf={profile.skills_confidence:.2f} | "
            f"exp_conf={profile.experience_confidence:.2f} (src={profile.experience_source}) | "
            f"seniority_conf={profile.seniority_confidence:.2f} (src={profile.seniority_source}) | "
            f"total_years={profile.total_experience_years} | "
            f"seniority={profile.seniority_inferred.value}"
        )
        if profile.has_low_confidence_warning():
            logger.warning(
                f"[CVExtraction] ⚠ Campos com baixa confiança | "
                f"exp_conf={profile.experience_confidence:.2f} | "
                f"seniority_conf={profile.seniority_confidence:.2f} | "
                f"skills_conf={profile.skills_confidence:.2f}"
            )

    # ── Empty ─────────────────────────────────────────────────────────────

    def _empty_profile(self, pdf_hash: str, warnings: list[str]) -> CVProfile:
        logger.error(f"[CVExtraction] Retornando perfil vazio | warnings={warnings}")
        return CVProfile(
            pdf_hash              = pdf_hash,
            candidate_name        = "Desconhecido",
            extraction_confidence = 0.0,
            extraction_strategy   = "failed",
            extraction_warnings   = warnings,
        )