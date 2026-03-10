from enum import Enum

class Verdict(str, Enum):
    APROVADO = "APROVADO"
    APROVADO_COM_RESSALVAS = "APROVADO_COM_RESSALVAS"
    REPROVADO = "REPROVADO"
    PENDENTE = "PENDENTE"           # extração incompleta / erro
    NAO_ANALISADO = "NAO_ANALISADO"


class SeniorityLevel(str, Enum):
    ESTAGIO = "ESTAGIO"
    JUNIOR = "JUNIOR"
    PLENO = "PLENO"
    SENIOR = "SENIOR"
    ESPECIALISTA = "ESPECIALISTA"
    LIDERANCA = "LIDERANCA"         # Tech Lead, Manager, Principal
    NAO_INFORMADO = "NAO_INFORMADO"


class JobDomain(str, Enum):
    TECH = "TECH"               # Engenharia de Software, DevOps, Infra
    DATA = "DATA"               # Data Science, ML, BI, Analytics
    BUSINESS = "BUSINESS"       # Marketing, Comercial, Gestão, RH
    CREATIVE = "CREATIVE"       # Design, UX, Comunicação
    LEGAL = "LEGAL"
    FINANCE = "FINANCE"
    HEALTH = "HEALTH"
    OTHER = "OTHER"


class SkillLevel(str, Enum):
    BASICO = "BASICO"
    INTERMEDIARIO = "INTERMEDIARIO"
    AVANCADO = "AVANCADO"
    ESPECIALISTA = "ESPECIALISTA"
    NAO_INFORMADO = "NAO_INFORMADO"


class LanguageProficiency(str, Enum):
    BASICO = "BASICO"
    INTERMEDIARIO = "INTERMEDIARIO"
    AVANCADO = "AVANCADO"
    FLUENTE = "FLUENTE"
    NATIVO = "NATIVO"

