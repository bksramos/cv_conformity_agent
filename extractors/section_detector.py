# ============================================================
# Detecta e rotula seções do CV para melhorar a extração
# ============================================================
from __future__ import annotations
import re
from dataclasses import dataclass


# Padrões de cabeçalho de seção — PT e EN
SECTION_PATTERNS = {
    "summary": re.compile(
        r"(resumo|objetivo|perfil|sobre mim|summary|objective|profile|about me)",
        re.IGNORECASE
    ),
    "experience": re.compile(
        r"(experi[eê]ncia|hist[oó]rico profissional|atua[cç][aã]o|experience|work history|employment)",
        re.IGNORECASE
    ),
    "education": re.compile(
        r"(educa[cç][aã]o|forma[cç][aã]o|gradua[cç][aã]o|academic|education|degree)",
        re.IGNORECASE
    ),
    "skills": re.compile(
        r"(habilidades|compet[eê]ncias|tecnologias|conhecimentos|skills|competencies|technologies|stack)",
        re.IGNORECASE
    ),
    "certifications": re.compile(
        r"(certifica[cç][oõ]es|cursos|treinamentos|certifications|courses|training)",
        re.IGNORECASE
    ),
    "languages": re.compile(
        r"(idiomas|l[ií]nguas|languages)",
        re.IGNORECASE
    ),
    "projects": re.compile(
        r"(projetos|portf[oó]lio|projects|portfolio)",
        re.IGNORECASE
    ),
}


@dataclass
class CVSection:
    name: str         # "experience", "education", etc.
    content: str
    start_line: int
    end_line: int


class CVSectionDetector:
    """
    Detecta e extrai seções do CV para estruturar o input do LLM.
    Melhora a precisão da extração ao contextualizar cada parte do texto.
    """

    def detect(self, text: str) -> dict[str, str]:
        """
        Retorna dicionário {nome_secao: conteudo}.
        Se não detectar seções, retorna o texto completo em "full_text".
        """
        lines = text.split("\n")
        sections: dict[str, list[str]] = {}
        current_section = "header"
        sections[current_section] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            detected = self._detect_section(stripped)
            if detected and len(stripped) < 60:   # cabeçalhos são curtos
                current_section = detected
                if current_section not in sections:
                    sections[current_section] = []
            else:
                sections[current_section].append(line)

        # Converte listas de linhas em texto
        result = {
            name: "\n".join(lines).strip()
            for name, lines in sections.items()
            if "\n".join(lines).strip()
        }

        # Se não detectou nenhuma seção relevante, retorna tudo
        relevant = {k: v for k, v in result.items() if k != "header"}
        if not relevant:
            return {"full_text": text}

        return result

    def _detect_section(self, line: str) -> str | None:
        for section_name, pattern in SECTION_PATTERNS.items():
            if pattern.search(line):
                return section_name
        return None

    def build_structured_input(self, sections: dict[str, str]) -> str:
        """
        Monta o texto estruturado para o LLM com seções rotuladas.
        Ajuda o modelo a saber exatamente onde encontrar cada informação.
        """
        if "full_text" in sections:
            return sections["full_text"]

        parts = []
        section_labels = {
            "header":         "DADOS PESSOAIS / CONTATO",
            "summary":        "RESUMO / OBJETIVO",
            "experience":     "EXPERIÊNCIA PROFISSIONAL",
            "education":      "FORMAÇÃO ACADÊMICA",
            "skills":         "HABILIDADES / TECNOLOGIAS",
            "certifications": "CERTIFICAÇÕES / CURSOS",
            "languages":      "IDIOMAS",
            "projects":       "PROJETOS / PORTFÓLIO",
        }
        for key, label in section_labels.items():
            if key in sections and sections[key]:
                parts.append(f"=== {label} ===\n{sections[key]}")

        return "\n\n".join(parts)