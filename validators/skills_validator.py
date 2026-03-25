from __future__ import annotations
from dataclasses import dataclass, field
from models.cv_model import CVProfile, Skill
from models.jd_model import JobDescription, RequiredSkill
from config.feature_flags import flags


@dataclass
class SkillMatchDetail:
    skill_name: str
    is_required: bool
    match_type: str       # "exact" | "partial" | "inferred" | "missing"
    score: float          # 0.0 - 1.0


class SkillsValidator:
    """
    Cruza hard skills do CV com as da JD.
    Três tipos de match:
      - exact   : skill encontrada com nome igual ou alias (score 1.0)
      - partial : skill correlata/família tecnológica    (score 0.5)
      - inferred: skill mencionada nas experiências      (score 0.7)
      - missing : não encontrada                         (score 0.0)
    """

    # Mapa de skills correlatas — se a JD pede X e o CV tem Y, conta como partial
    SKILL_FAMILIES: dict[str, set[str]] = {
        "django":    {"flask", "fastapi", "pyramid", "tornado"},
        "fastapi":   {"flask", "django", "starlette"},
        "flask":     {"fastapi", "django"},
        "react":     {"vue", "angular", "svelte", "nextjs", "next.js"},
        "vue":       {"react", "angular", "svelte"},
        "angular":   {"react", "vue"},
        "postgres":  {"mysql", "mariadb", "sqlite", "oracle"},
        "mysql":     {"postgres", "mariadb", "sqlite"},
        "mongodb":   {"couchdb", "dynamodb", "firestore"},
        "redis":     {"memcached", "elasticache"},
        "docker":    {"podman", "containerd"},
        "kubernetes":{"docker swarm", "nomad", "ecs"},
        "aws":       {"gcp", "azure", "digitalocean"},
        "gcp":       {"aws", "azure"},
        "azure":     {"aws", "gcp"},
        "tensorflow":{"pytorch", "keras", "jax"},
        "pytorch":   {"tensorflow", "keras"},
        "spark":     {"flink", "hadoop", "hive"},
        "airflow":   {"prefect", "dagster", "luigi"},
        "kafka":     {"rabbitmq", "pubsub", "sqs", "kinesis"},
        "rabbitmq":  {"kafka", "activemq", "sqs"},
    }

    def validate(self, cv: CVProfile, jd: JobDescription) -> dict:
        cv_skill_names = cv.get_skill_names()
        exp_techs = self._get_exp_technologies(cv)
        details: list[SkillMatchDetail] = []

        for jd_skill in jd.required_skills:
            detail = self._match_skill(jd_skill, cv_skill_names, exp_techs)
            details.append(detail)

        required = [d for d in details if d.is_required]
        desired  = [d for d in details if not d.is_required]

        # Score de obrigatórias (peso maior)
        req_score = self._calc_score(required) if required else 1.0
        # Score de desejáveis
        des_score = self._calc_score(desired) if desired else 1.0
        # Score combinado: 70% obrigatórias, 30% desejáveis
        combined = (req_score * 0.7 + des_score * 0.3) * 100

        # Bloqueador absoluto: skill obrigatória totalmente ausente
        has_blocker = (
            flags.ENFORCE_REQUIRED_SKILLS
            and any(d.match_type == "missing" and d.is_required for d in details)
        )

        matched = [d.skill_name for d in details if d.match_type != "missing"]
        missing = [d.skill_name for d in details if d.match_type == "missing" and d.is_required]
        partial = [d.skill_name for d in details if d.match_type == "partial"]

        return {
            "score": round(combined, 1),
            "has_blocker": has_blocker,
            "matched": matched,
            "missing": missing,
            "partial": partial,
            "details": details,
        }

    def _match_skill(
        self,
        jd_skill: RequiredSkill,
        cv_names: set[str],
        exp_techs: set[str],
    ) -> SkillMatchDetail:
        name = jd_skill.name.lower()
        aliases = {a.lower() for a in jd_skill.aliases}
        all_names = {name} | aliases

        # 1. Match exato
        if all_names & cv_names:
            return SkillMatchDetail(jd_skill.name, jd_skill.is_required, "exact", 1.0)

        # 2. Match inferido das experiências
        if flags.INFER_SKILLS_FROM_EXPERIENCE and all_names & exp_techs:
            return SkillMatchDetail(jd_skill.name, jd_skill.is_required, "inferred", 0.7)

        # 3. Match parcial (família tecnológica)
        if flags.ALLOW_PARTIAL_SKILL_MATCH:
            correlatas = self.SKILL_FAMILIES.get(name, set())
            if correlatas & cv_names:
                return SkillMatchDetail(jd_skill.name, jd_skill.is_required, "partial", 0.5)

        return SkillMatchDetail(jd_skill.name, jd_skill.is_required, "missing", 0.0)

    def _calc_score(self, details: list[SkillMatchDetail]) -> float:
        if not details:
            return 1.0
        return sum(d.score for d in details) / len(details)

    def _get_exp_technologies(self, cv: CVProfile) -> set[str]:
        techs = set()
        for exp in cv.experiences:
            techs.update(t.lower() for t in exp.technologies)
        return techs
