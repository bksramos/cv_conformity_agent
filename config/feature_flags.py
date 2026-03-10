from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FeatureFlags:
    """
    Feature flags que controlam o comportamento do CV Conformity Agent.
    Cada dimensão de validação pode ser ligada/desligada independentemente,
    """

    # ----------------------------------------------------------
    # DIMENSÕES DE VALIDAÇÃO
    # ----------------------------------------------------------

    # Valida cobertura de hard skills obrigatórias e desejáveis
    VALIDATE_HARD_SKILLS: bool = True

    # Valida anos de experiência total vs. mínimo requerido
    VALIDATE_EXPERIENCE_YEARS: bool = True

    # Valida senioridade inferida do CV vs. requerida pela vaga
    VALIDATE_SENIORITY: bool = True

    # Valida formação acadêmica e certificações
    VALIDATE_EDUCATION: bool = True

    # Valida idiomas requeridos e níveis
    VALIDATE_LANGUAGES: bool = True

    # Valida soft skills mencionadas no CV vs. JD (Fase 2)
    VALIDATE_SOFT_SKILLS: bool = False

    # Valida fit de domínio (fintech, healthtech, etc.) (Fase 2)
    VALIDATE_DOMAIN_FIT: bool = False

    # ----------------------------------------------------------
    # COMPORTAMENTO DO SCORING
    # ----------------------------------------------------------

    # Se True: ausência de qualquer skill OBRIGATÓRIA = REPROVADO imediato
    # Análogo ao ENFORCE_VERSION_PROGRESSION do Feito/Conferido
    ENFORCE_REQUIRED_SKILLS: bool = True

    # Se True: skill correlata/equivalente conta como match parcial
    # Ex: candidato tem FastAPI mas vaga pede Django → 50% de match
    ALLOW_PARTIAL_SKILL_MATCH: bool = True

    # Se True: infere skills a partir das descrições de experiências
    # Ex: "desenvolveu APIs REST em Python" → infere Python, REST API
    INFER_SKILLS_FROM_EXPERIENCE: bool = True

    # Se True: considera anos de experiência específica em cada skill
    # (não apenas experiência total)
    WEIGHT_SKILL_DEPTH: bool = True

    # ----------------------------------------------------------
    # EXTRAÇÃO DE CV
    # ----------------------------------------------------------

    # Usa pdfplumber como fallback se PyMuPDF falhar
    USE_PDF_FALLBACK_EXTRACTOR: bool = True

    # Usa Llama 3 para re-extração quando confiança < threshold
    USE_LLM_FALLBACK_EXTRACTION: bool = True

    # Threshold de confiança abaixo do qual aciona fallback
    EXTRACTION_CONFIDENCE_THRESHOLD: float = 0.7

    # ----------------------------------------------------------
    # CACHE
    # ----------------------------------------------------------

    # Cache L1 (memória) + L2 (Redis) para resultados já calculados
    USE_VALIDATION_CACHE: bool = True

    # ChromaDB: embeddings de CVs já processados (evita re-extração)
    USE_EMBEDDING_CACHE: bool = True

    # TTL do cache em segundos (24h por padrão)
    CACHE_TTL_SECONDS: int = 86400

    # ----------------------------------------------------------
    # OUTPUT / REPORT
    # ----------------------------------------------------------

    # Gera parecer em PT e EN
    GENERATE_BILINGUAL_REPORT: bool = True

    # Exibe score numérico (0-100) no output
    SHOW_NUMERIC_SCORE: bool = True

    # Exibe breakdown por dimensão no output
    SHOW_DIMENSION_BREAKDOWN: bool = True

    # Inclui lista de pontos fortes do candidato no parecer
    SHOW_CANDIDATE_STRENGTHS: bool = True

    # Inclui lista de gaps críticos no parecer
    SHOW_CRITICAL_GAPS: bool = True

    # ----------------------------------------------------------
    # SUBAGENTS DE DOMÍNIO (Fase 2)
    # ----------------------------------------------------------

    # Ativa roteamento para subagent especialista por domínio
    USE_DOMAIN_SPECIALIST_AGENT: bool = False

    # Domínios disponíveis quando USE_DOMAIN_SPECIALIST_AGENT = True
    ENABLED_DOMAIN_AGENTS: list = field(default_factory=lambda: [
        "TECH",   # Engenharia de Software
        "DATA",   # Data Science / ML / BI
        # "BUSINESS",  # Marketing, Gestão, Comercial (Fase 2)
        # "CREATIVE",  # Design, UX, Comunicação (Fase 2)
    ])

    # ----------------------------------------------------------
    # SCRAPER
    # ----------------------------------------------------------

    # Fontes de scraping ativas
    ENABLED_SCRAPERS: list = field(default_factory=lambda: [
        "gupy",       # API pública — mais estável
        "remoteok",   # JSON API — tech/remote
        # "vagas",    # HTML scraping — ativar depois
        # "programathor",
    ])

    # Persiste JDs mesmo com baixa confiança de extração
    PERSIST_LOW_CONFIDENCE_JDS: bool = False

    def is_scraper_enabled(self, name: str) -> bool:
        return name in self.ENABLED_SCRAPERS

    def is_domain_agent_enabled(self, domain: str) -> bool:
        return self.USE_DOMAIN_SPECIALIST_AGENT and domain in self.ENABLED_DOMAIN_AGENTS

    def summary(self) -> dict:
        """Retorna resumo das flags ativas — útil para logging."""
        return {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_")
        }


# Instância global (importada pelos agents)
flags = FeatureFlags()