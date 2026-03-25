from __future__ import annotations
import sys
import datetime
from pathlib import Path

import httpx
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

API_BASE = "http://localhost:8000/api/v1"

# ============================================================
# Config da página
# ============================================================
st.set_page_config(
    page_title="CV Conformity Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Inicializa session_state — persiste entre navegações
# ============================================================
DEFAULTS = {
    # Análise 1x1
    "analysis_result":    None,
    "analysis_running":   False,
    "analysis_error":     None,
    "analysis_pdf_name":  None,
    "analysis_pdf_bytes": None,
    "analysis_jd_id":     None,
    "analysis_jd_text":   None,
    "analysis_jd_label":  None,
    # Batch
    "batch_result":       None,
    "batch_running":      False,
    "batch_error":        None,
    "batch_pdf_name":     None,
    "batch_pdf_bytes":    None,
    "batch_top_k":        10,
    "batch_domain":       None,
    "batch_seniority":    None,
    # Análise do CV
    "cv_profile_result":    None,
    "cv_profile_running":   False,
    "cv_profile_error":     None,
    "cv_profile_pdf_name":  None,
    "cv_profile_pdf_bytes": None,
    # Melhoria do CV
    "improvement_result":    None,
    "improvement_running":   False,
    "improvement_error":     None,
    "improvement_pdf_name":  None,
    "improvement_pdf_bytes": None,
    "improvement_jd_id":     None,
    "improvement_mode":      "diagnose",  # "diagnose" | "improve"
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# Helpers
# ============================================================
VERDICT_CONFIG = {
    "APROVADO":               {"icon": "✅", "color": "#28a745", "label": "Aprovado"},
    "APROVADO_COM_RESSALVAS": {"icon": "⚠️", "color": "#ffc107", "label": "Aprovado com Ressalvas"},
    "REPROVADO":              {"icon": "❌", "color": "#dc3545", "label": "Reprovado"},
}

def verdict_badge(verdict: str) -> str:
    cfg = VERDICT_CONFIG.get(verdict, {"icon": "❓", "color": "#6c757d", "label": verdict})
    return (
        f'<span style="background:{cfg["color"]};color:white;padding:4px 12px;'
        f'border-radius:12px;font-weight:bold;">{cfg["icon"]} {cfg["label"]}</span>'
    )

def score_color(score: float) -> str:
    if score >= 70: return "#28a745"
    if score >= 50: return "#ffc107"
    return "#dc3545"

def api_get(path: str, params: dict | None = None) -> dict | None:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{API_BASE}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        st.error("❌ API não está rodando. Execute: `make api`")
        return None
    except Exception as e:
        st.error(f"Erro na API: {e}")
        return None

def api_post_form(path: str, data: dict, files: dict) -> dict | None:
    try:
        with httpx.Client(timeout=300) as client:
            resp = client.post(f"{API_BASE}{path}", data=data, files=files)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        return {"__error__": "❌ API não está rodando. Execute: `make api`"}
    except httpx.HTTPStatusError as e:
        return {"__error__": f"Erro {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        return {"__error__": str(e)}

# ============================================================
# Componentes reutilizáveis
# ============================================================
def render_score_card(label: str, score: float, weight: float):
    color = score_color(score)
    st.markdown(
        f"""
        <div style="border:1px solid #ddd;border-radius:8px;padding:12px;
                    text-align:center;margin:4px">
            <div style="font-size:0.8rem;color:#666">{label}</div>
            <div style="font-size:1.8rem;font-weight:bold;color:{color}">{score:.0f}</div>
            <div style="font-size:0.7rem;color:#999">peso {int(weight*100)}%</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_result(result: dict):
    verdict   = result.get("verdict", "")
    score     = result.get("overall_score", 0)
    cfg       = VERDICT_CONFIG.get(verdict, {"icon": "❓", "color": "#6c757d"})
    cache_hit = result.get("cache_hit", False)
    dims      = result.get("dimensions", {})

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"### {result.get('candidate_name', '')} → {result.get('jd_title', '')}")
        st.markdown(verdict_badge(verdict), unsafe_allow_html=True)
        if cache_hit:
            st.caption("⚡ Resultado do cache")
        if result.get("has_absolute_blocker"):
            st.error("⛔ Bloqueador absoluto ativo — skill obrigatória ausente")
    with col2:
        st.markdown(
            f'<div style="text-align:center;font-size:3rem;font-weight:bold;'
            f'color:{score_color(score)}">{score:.1f}</div>'
            f'<div style="text-align:center;color:#666;font-size:0.8rem">/ 100</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    if dims:
        cols = st.columns(5)
        dim_labels = {
            "hard_skills": "🔧 Skills",
            "experience":  "⏱ Exp",
            "education":   "🎓 Formação",
            "languages":   "🌐 Idiomas",
            "soft_skills": "🤝 Soft Skills",
        }
        for col, (key, label) in zip(cols, dim_labels.items()):
            with col:
                dim = dims.get(key, {})
                render_score_card(label, dim.get("score", 0), dim.get("weight", 0))

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📋 Detalhes", "📝 Parecer PT", "📝 Parecer EN"])

    with tab1:
        col_left, col_right = st.columns(2)
        with col_left:
            if result.get("strengths"):
                st.markdown("**💪 Pontos Fortes**")
                for s in result["strengths"]:
                    st.markdown(f"- {s}")
            if result.get("partial_matches"):
                st.markdown("**🟡 Matches Parciais**")
                for p in result["partial_matches"]:
                    st.markdown(f"- {p}")
        with col_right:
            if result.get("critical_gaps"):
                st.markdown("**⛔ Lacunas Críticas**")
                for g in result["critical_gaps"]:
                    st.markdown(f"- {g}")

        if dims:
            st.markdown("**📊 Breakdown por Dimensão**")
            for key, label in {
                "hard_skills": "🔧 Hard Skills",
                "experience":  "⏱ Experiência",
                "education":   "🎓 Formação",
                "languages":   "🌐 Idiomas",
            }.items():
                dim = dims.get(key, {})
                if not dim:
                    continue
                with st.expander(f"{label} — {dim.get('score', 0):.0f}/100"):
                    c1, c2 = st.columns(2)
                    with c1:
                        if dim.get("matched"):
                            st.markdown("✅ **Encontrado**")
                            for m in dim["matched"]:
                                st.markdown(f"  - {m}")
                    with c2:
                        if dim.get("missing"):
                            st.markdown("❌ **Ausente**")
                            for m in dim["missing"]:
                                st.markdown(f"  - {m}")
                    for n in dim.get("notes", []):
                        st.caption(f"ℹ️ {n}")

    with tab2:
        st.markdown(result.get("parecer_final_pt") or "_Parecer não disponível_")
    with tab3:
        st.markdown(result.get("parecer_final_en") or "_Report not available_")


# ============================================================
# Banner de análise em andamento — aparece em TODAS as páginas
# ============================================================
def render_global_status():
    if st.session_state.analysis_running:
        st.info(
            f"⏳ **Análise em andamento...** "
            f"CV: `{st.session_state.analysis_pdf_name}` × "
            f"`{st.session_state.analysis_jd_label}` — "
            f"Você pode navegar normalmente. O resultado aparecerá aqui quando pronto.",
            icon="🔄",
        )

    if st.session_state.batch_running:
        st.info(
            f"⏳ **Batch Match em andamento...** "
            f"CV: `{st.session_state.batch_pdf_name}` — "
            f"Você pode navegar normalmente.",
            icon="🔄",
        )

    if st.session_state.analysis_error:
        st.error(f"❌ Erro na análise: {st.session_state.analysis_error}")
        if st.button("Limpar erro", key="clear_analysis_error"):
            st.session_state.analysis_error = None
            st.rerun()

    if st.session_state.batch_error:
        st.error(f"❌ Erro no batch: {st.session_state.batch_error}")
        if st.button("Limpar erro", key="clear_batch_error"):
            st.session_state.batch_error = None
            st.rerun()


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/resume.png", width=64)
    st.title("CV Conformity Agent")
    st.caption("Multi-agent AI • LangGraph • Llama 3")

    if st.session_state.analysis_running:
        st.warning("⏳ Análise 1×1 em andamento...")
    elif st.session_state.analysis_result:
        st.success("✅ Resultado disponível — Análise 1×1")

    if st.session_state.batch_running:
        st.warning("⏳ Batch Match em andamento...")
    elif st.session_state.batch_result:
        st.success("✅ Resultado disponível — Batch Match")

    if st.session_state.cv_profile_running:
        st.warning("⏳ Análise do CV em andamento...")
    elif st.session_state.cv_profile_result:
        st.success("✅ CV analisado")

    if st.session_state.improvement_running:
        mode = st.session_state.improvement_mode
        label = "Diagnóstico" if mode == "diagnose" else "Melhoria"
        st.warning(f"⏳ {label} em andamento...")
    elif st.session_state.improvement_result:
        st.success("✅ Diagnóstico/Melhoria disponível")

    st.divider()
    page = st.radio(
        "Navegação",
        ["🔍 Análise 1×1", "🏆 Batch Match", "🧠 Análise do CV",
         "🛠️ Melhoria de CV", "📋 Vagas Disponíveis", "❤️ Health"],
        label_visibility="collapsed",
    )

    render_global_status()

    if st.session_state.cv_profile_error:
        st.error(f"❌ Erro na análise do CV: {st.session_state.cv_profile_error}")
        if st.button("Limpar erro", key="clear_cv_error"):
            st.session_state.cv_profile_error = None
            st.rerun()

    if st.session_state.improvement_error:
        st.error(f"❌ Erro na melhoria: {st.session_state.improvement_error}")
        if st.button("Limpar erro", key="clear_improvement_error"):
            st.session_state.improvement_error = None
            st.rerun()

# ============================================================
# PÁGINA: Análise 1×1
# ============================================================
if page == "🔍 Análise 1×1":
    st.title("🔍 Análise CV × Vaga")
    st.caption("Faça upload de um currículo e selecione uma vaga para analisar a conformidade.")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📄 Currículo")
        pdf_file = st.file_uploader("Upload do PDF", type=["pdf"], key="uploader_1x1")

    with col2:
        st.subheader("📋 Vaga")
        input_mode = st.radio("Fonte da vaga", ["Banco de Dados", "Texto Livre"], horizontal=True)
        jd_id, jd_text, jd_label = None, None, "vaga manual"

        if input_mode == "Banco de Dados":
            jobs_data = api_get("/jobs", params={"limit": 100})
            if jobs_data and jobs_data.get("jobs"):
                options = {
                    f"{j['title']} — {j.get('company', '')} [{j.get('seniority', '')}]": j["id"]
                    for j in jobs_data["jobs"]
                }
                selected = st.selectbox("Selecione a vaga", list(options.keys()))
                jd_id    = options[selected] if selected else None
                jd_label = selected or "vaga selecionada"
            else:
                st.warning("Nenhuma vaga no banco. Rode o scraper primeiro.")
        else:
            jd_text  = st.text_area(
                "Cole o texto da vaga", height=200,
                placeholder="Título, requisitos, responsabilidades...",
            )
            jd_label = "vaga (texto livre)"

    btn_disabled = st.session_state.analysis_running or not pdf_file
    if st.button("🚀 Analisar", type="primary", disabled=btn_disabled):
        if not jd_id and not jd_text:
            st.warning("Selecione ou cole uma vaga.")
        else:
            # ── FIX: lê e persiste os bytes ANTES do rerun ──────────────────
            st.session_state.analysis_pdf_bytes = pdf_file.read()
            st.session_state.analysis_jd_id     = jd_id
            st.session_state.analysis_jd_text   = jd_text
            # ────────────────────────────────────────────────────────────────
            st.session_state.analysis_running    = True
            st.session_state.analysis_result     = None
            st.session_state.analysis_error      = None
            st.session_state.analysis_pdf_name   = pdf_file.name
            st.session_state.analysis_jd_label   = jd_label
            st.rerun()

    # Executa a chamada bloqueante — usa bytes do session_state, não do uploader
    if st.session_state.analysis_running and st.session_state.analysis_result is None:
        pdf_bytes = st.session_state.analysis_pdf_bytes  # ← FIX: fonte correta
        if pdf_bytes:
            with st.spinner(
                f"Analisando `{st.session_state.analysis_pdf_name}` × "
                f"`{st.session_state.analysis_jd_label}`..."
            ):
                result = api_post_form(
                    "/analyze",
                    data={k: v for k, v in {
                        "jd_id":   st.session_state.analysis_jd_id,   # ← FIX
                        "jd_text": st.session_state.analysis_jd_text, # ← FIX
                    }.items() if v},
                    files={"pdf": (
                        st.session_state.analysis_pdf_name,
                        pdf_bytes,
                        "application/pdf",
                    )},
                )

            if result and "__error__" in result:
                st.session_state.analysis_error   = result["__error__"]
                st.session_state.analysis_running = False
            elif result:
                st.session_state.analysis_result  = result
                st.session_state.analysis_running = False
                # Libera memória — bytes não são mais necessários
                st.session_state.analysis_pdf_bytes = None
            else:
                st.session_state.analysis_error   = "Resposta vazia da API"
                st.session_state.analysis_running = False
            st.rerun()

    if st.session_state.analysis_result:
        st.success("✅ Análise concluída!")
        col_info, col_clear = st.columns([5, 1])
        with col_clear:
            if st.button("🗑 Limpar", key="clear_1x1"):
                st.session_state.analysis_result    = None
                st.session_state.analysis_pdf_bytes = None
                st.rerun()
        render_result(st.session_state.analysis_result)

# ============================================================
# PÁGINA: Batch Match
# ============================================================
elif page == "🏆 Batch Match":
    st.title("🏆 Batch Match — CV × Melhores Vagas")
    st.caption("Faça upload do currículo e encontre as vagas mais compatíveis no banco.")

    pdf_file = st.file_uploader("Upload do PDF", type=["pdf"], key="uploader_batch")

    col1, col2, col3 = st.columns(3)
    with col1:
        top_k = st.number_input("Nº de vagas", min_value=1, max_value=50, value=10)
    with col2:
        domain = st.selectbox("Domínio", ["Todos", "TECH", "DATA", "BUSINESS", "CREATIVE", "FINANCE"])
    with col3:
        seniority = st.selectbox("Senioridade", ["Todas", "JUNIOR", "PLENO", "SENIOR", "ESPECIALISTA", "LIDERANCA"])

    btn_disabled = st.session_state.batch_running or not pdf_file
    if st.button("🔍 Buscar Melhores Vagas", type="primary", disabled=btn_disabled):
        # ── FIX: lê e persiste os bytes ANTES do rerun ──────────────────────
        st.session_state.batch_pdf_bytes  = pdf_file.read()
        st.session_state.batch_top_k      = top_k
        st.session_state.batch_domain     = None if domain    == "Todos"  else domain
        st.session_state.batch_seniority  = None if seniority == "Todas" else seniority
        # ────────────────────────────────────────────────────────────────────
        st.session_state.batch_running    = True
        st.session_state.batch_result     = None
        st.session_state.batch_error      = None
        st.session_state.batch_pdf_name   = pdf_file.name
        st.rerun()

    if st.session_state.batch_running and st.session_state.batch_result is None:
        pdf_bytes = st.session_state.batch_pdf_bytes  # ← FIX: fonte correta
        if pdf_bytes:
            data = {"top_k": str(st.session_state.batch_top_k)}
            if st.session_state.batch_domain:    data["domain"]    = st.session_state.batch_domain
            if st.session_state.batch_seniority: data["seniority"] = st.session_state.batch_seniority

            with st.spinner(
                f"Analisando `{st.session_state.batch_pdf_name}` contra "
                f"{st.session_state.batch_top_k} vagas..."
            ):
                result = api_post_form(
                    "/analyze/batch",
                    data=data,
                    files={"pdf": (
                        st.session_state.batch_pdf_name,
                        pdf_bytes,
                        "application/pdf",
                    )},
                )

            if result and "__error__" in result:
                st.session_state.batch_error   = result["__error__"]
                st.session_state.batch_running = False
            elif result:
                st.session_state.batch_result  = result
                st.session_state.batch_running = False
                # Libera memória
                st.session_state.batch_pdf_bytes = None
            else:
                st.session_state.batch_error   = "Resposta vazia da API"
                st.session_state.batch_running = False
            st.rerun()

    if st.session_state.batch_result:
        result = st.session_state.batch_result
        col_info, col_clear = st.columns([5, 1])
        with col_clear:
            if st.button("🗑 Limpar", key="clear_batch"):
                st.session_state.batch_result    = None
                st.session_state.batch_pdf_bytes = None
                st.rerun()

        st.success(
            f"✅ {result['total_analyzed']} vagas analisadas para **{result['candidate_name']}**"
        )

        import pandas as pd
        rows = []
        for r in result["results"]:
            cfg = VERDICT_CONFIG.get(r["verdict"], {"icon": "❓"})
            rows.append({
                "Rank":     len(rows) + 1,
                "Veredito": f"{cfg['icon']} {r['verdict']}",
                "Score":    r["overall_score"],
                "Vaga":     r["jd_title"],
                "Skills":   r.get("dimensions", {}).get("hard_skills", {}).get("score", 0),
                "Exp":      r.get("dimensions", {}).get("experience",  {}).get("score", 0),
                "Bloq":     "⛔" if r.get("has_absolute_blocker") else "",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📋 Detalhes por Vaga")
        for i, r in enumerate(result["results"]):
            cfg = VERDICT_CONFIG.get(r["verdict"], {"icon": "❓"})
            with st.expander(
                f"#{i+1} {cfg['icon']} [{r['overall_score']:.1f}/100] {r['jd_title']}"
            ):
                render_result(r)

# ============================================================
# PÁGINA: Análise do CV
# ============================================================
elif page == "🧠 Análise do CV":
    st.title("🧠 Análise do Currículo")
    st.caption("Extração completa do CV via LLM — visualize tudo que foi interpretado pelo agente.")

    pdf_file = st.file_uploader("Upload do PDF", type=["pdf"], key="uploader_cv_profile")

    btn_disabled = st.session_state.cv_profile_running or not pdf_file
    if st.button("🔬 Analisar CV", type="primary", disabled=btn_disabled):
        st.session_state.cv_profile_pdf_bytes = pdf_file.read()
        st.session_state.cv_profile_pdf_name  = pdf_file.name
        st.session_state.cv_profile_running   = True
        st.session_state.cv_profile_result    = None
        st.session_state.cv_profile_error     = None
        st.rerun()

    if st.session_state.cv_profile_running and st.session_state.cv_profile_result is None:
        pdf_bytes = st.session_state.cv_profile_pdf_bytes
        if pdf_bytes:
            with st.spinner(f"Analisando `{st.session_state.cv_profile_pdf_name}`..."):
                result = api_post_form(
                    "/cv/analyze",
                    data={},
                    files={"pdf": (st.session_state.cv_profile_pdf_name, pdf_bytes, "application/pdf")},
                )
            if result and "__error__" in result:
                st.session_state.cv_profile_error   = result["__error__"]
                st.session_state.cv_profile_running = False
            elif result:
                st.session_state.cv_profile_result  = result
                st.session_state.cv_profile_running = False
                st.session_state.cv_profile_pdf_bytes = None
            else:
                st.session_state.cv_profile_error   = "Resposta vazia da API"
                st.session_state.cv_profile_running = False
            st.rerun()

    if st.session_state.cv_profile_result:
        p = st.session_state.cv_profile_result
        col_title, col_clear = st.columns([5, 1])
        with col_clear:
            if st.button("🗑 Limpar", key="clear_cv_profile"):
                st.session_state.cv_profile_result = None
                st.rerun()

        # ── Header do candidato ────────────────────────────────────────
        st.divider()
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.markdown(f"## {p.get('candidate_name', '—')}")
            if p.get("email"):
                st.caption(f"✉️ {p['email']}")
            if p.get("phone"):
                st.caption(f"📞 {p['phone']}")
            if p.get("location"):
                st.caption(f"📍 {p['location']}")
            if p.get("linkedin_url"):
                st.caption(f"🔗 {p['linkedin_url']}")
        with col2:
            if p.get("summary"):
                st.markdown("**Resumo profissional:**")
                st.markdown(f"_{p['summary']}_")
        with col3:
            sen = p.get("seniority_inferred", "—")
            years = p.get("total_experience_years", 0)
            sen_colors = {
                "ESTAGIO": "#6c757d", "JUNIOR": "#17a2b8", "PLENO": "#28a745",
                "SENIOR": "#ffc107", "ESPECIALISTA": "#fd7e14", "LIDERANCA": "#dc3545",
            }
            color = sen_colors.get(sen, "#6c757d")
            st.markdown(
                f'<div style="border:1px solid {color};border-radius:8px;padding:12px;text-align:center">'
                f'<div style="font-size:0.8rem;color:#666">Senioridade</div>'
                f'<div style="font-size:1.4rem;font-weight:bold;color:{color}">{sen}</div>'
                f'<div style="font-size:1.1rem;color:#333">{years} anos</div>'
                f'</div>', unsafe_allow_html=True,
            )

        # ── Contrato de confiança ──────────────────────────────────────
        st.divider()
        st.subheader("📊 Contrato de Confiança da Extração")
        contract = p.get("contract", {})

        def _conf_color(v: float) -> str:
            return "#28a745" if v >= 0.8 else ("#ffc107" if v >= 0.6 else "#dc3545")

        def _conf_card(label: str, value: float, source: str = ""):
            color = _conf_color(value)
            pct   = int(value * 100)
            st.markdown(
                f'<div style="border:1px solid {color};border-radius:8px;padding:10px;text-align:center">'
                f'<div style="font-size:0.75rem;color:#666">{label}</div>'
                f'<div style="font-size:1.6rem;font-weight:bold;color:{color}">{pct}%</div>'
                f'<div style="font-size:0.65rem;color:#999">{source}</div>'
                f'</div>', unsafe_allow_html=True,
            )

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: _conf_card("Overall", contract.get("overall_confidence", 0))
        with c2: _conf_card("Skills",  contract.get("skills_confidence", 0))
        with c3: _conf_card("Experiência", contract.get("experience_confidence", 0), contract.get("experience_source", ""))
        with c4: _conf_card("Senioridade", contract.get("seniority_confidence", 0), contract.get("seniority_source", ""))
        with c5:
            strat = p.get("extraction_strategy", "—")
            st.markdown(
                f'<div style="border:1px solid #dee2e6;border-radius:8px;padding:10px;text-align:center">'
                f'<div style="font-size:0.75rem;color:#666">Estratégia</div>'
                f'<div style="font-size:1rem;font-weight:bold;color:#495057">{strat}</div>'
                f'<div style="font-size:0.65rem;color:#999">extração PDF</div>'
                f'</div>', unsafe_allow_html=True,
            )

        if contract.get("has_low_confidence_warning"):
            st.warning("⚠️ Um ou mais campos críticos têm baixa confiança — os resultados de conformidade podem ser imprecisos.")
        if p.get("extraction_warnings"):
            with st.expander(f"⚠️ {len(p['extraction_warnings'])} aviso(s) da extração"):
                for w in p["extraction_warnings"]:
                    st.caption(f"• {w}")

        # ── Tabs de conteúdo ───────────────────────────────────────────
        st.divider()
        tab_skills, tab_exp, tab_edu, tab_lang, tab_soft = st.tabs([
            "🔧 Hard Skills", "⏱ Experiências", "🎓 Formação", "🌐 Idiomas", "🤝 Soft Skills & Certs"
        ])

        # ── Hard Skills ────────────────────────────────────────────────
        with tab_skills:
            skills = p.get("hard_skills", [])
            if not skills:
                st.info("Nenhuma hard skill extraída.")
            else:
                st.caption(f"{len(skills)} skill(s) extraída(s)")
                # Agrupa por source para mostrar explícitas x inferidas
                source_order = ["explicit", "inferred_from_exp", "inferred_from_context"]
                source_labels = {
                    "explicit":               "✅ Explícitas (seção de skills)",
                    "inferred_from_exp":      "🔍 Inferidas das experiências",
                    "inferred_from_context":  "💡 Inferidas por contexto",
                }
                grouped: dict[str, list] = {}
                for s in skills:
                    src = s.get("source", "explicit")
                    grouped.setdefault(src, []).append(s)

                for src in source_order:
                    group = grouped.get(src, [])
                    if not group:
                        continue
                    st.markdown(f"**{source_labels.get(src, src)}**")
                    cols = st.columns(2)
                    for i, s in enumerate(group):
                        with cols[i % 2]:
                            conf  = s.get("confidence", 1.0)
                            color = _conf_color(conf)
                            level = s.get("level", "NAO_INFORMADO")
                            years = f" · {s['years_of_use']}a" if s.get("years_of_use") else ""
                            in_exp = " · 📌exp" if s.get("mentioned_in_experience") else ""
                            bar_w  = int(conf * 100)
                            st.markdown(
                                f'<div style="border:1px solid #e9ecef;border-radius:6px;'
                                f'padding:8px 12px;margin-bottom:6px">'
                                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                                f'<span style="font-weight:600">{s["name"]}</span>'
                                f'<span style="font-size:0.75rem;color:{color};font-weight:bold">{int(conf*100)}%</span>'
                                f'</div>'
                                f'<div style="font-size:0.72rem;color:#6c757d">{level}{years}{in_exp}</div>'
                                f'<div style="background:#e9ecef;border-radius:3px;height:4px;margin-top:4px">'
                                f'<div style="background:{color};width:{bar_w}%;height:4px;border-radius:3px"></div>'
                                f'</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

        # ── Experiências ───────────────────────────────────────────────
        with tab_exp:
            exps = p.get("experiences", [])
            if not exps:
                st.info("Nenhuma experiência extraída.")
            else:
                st.caption(f"{len(exps)} experiência(s) · {p.get('total_experience_years', 0)} anos total")
                for i, e in enumerate(exps):
                    dur    = e.get("duration_months")
                    dur_str = f"{dur}m ({dur//12}a {dur%12}m)" if dur else "duração não identificada"
                    d_conf  = e.get("duration_confidence", 0)
                    d_src   = e.get("duration_source", "—")
                    d_color = _conf_color(d_conf)
                    start   = e.get("start_date") or "?"
                    end     = e.get("end_date") or "atual"

                    with st.expander(
                        f"**{e.get('role', '?')}** @ {e.get('company', '?')}  ·  {start} → {end}  ·  {dur_str}",
                        expanded=(i == 0),
                    ):
                        col_a, col_b = st.columns([3, 1])
                        with col_a:
                            if e.get("description"):
                                st.markdown(e["description"])
                            if e.get("technologies"):
                                st.markdown("**Tecnologias mencionadas:**")
                                st.markdown(" · ".join(f"`{t}`" for t in e["technologies"]))
                            if e.get("domain"):
                                st.caption(f"🏢 Domínio: {e['domain']}")
                        with col_b:
                            st.markdown(
                                f'<div style="border:1px solid {d_color};border-radius:6px;'
                                f'padding:8px;text-align:center">'
                                f'<div style="font-size:0.7rem;color:#666">Conf. duração</div>'
                                f'<div style="font-size:1.2rem;font-weight:bold;color:{d_color}">'
                                f'{int(d_conf*100)}%</div>'
                                f'<div style="font-size:0.65rem;color:#999">{d_src}</div>'
                                f'</div>', unsafe_allow_html=True,
                            )

        # ── Formação ───────────────────────────────────────────────────
        with tab_edu:
            edu_list = p.get("education", [])
            certs    = p.get("certifications", [])
            if not edu_list and not certs:
                st.info("Nenhuma formação extraída.")
            for e in edu_list:
                status = "✅" if e.get("is_complete") else "🔄 Em andamento"
                year   = f" · {e['graduation_year']}" if e.get("graduation_year") else ""
                st.markdown(
                    f'<div style="border-left:3px solid #0d6efd;padding:8px 16px;margin-bottom:8px">'
                    f'<div style="font-weight:600">{e.get("degree", "—")} em {e.get("field_of_study", "—")}</div>'
                    f'<div style="color:#495057">{e.get("institution", "—")}{year}</div>'
                    f'<div style="font-size:0.75rem;color:#6c757d">{status}</div>'
                    f'</div>', unsafe_allow_html=True,
                )
            if certs:
                st.markdown("**📜 Certificações:**")
                for c in certs:
                    st.markdown(f"- {c}")

        # ── Idiomas ────────────────────────────────────────────────────
        with tab_lang:
            langs = p.get("languages", [])
            if not langs:
                st.info("Nenhum idioma extraído.")
            else:
                prof_order = ["NATIVO", "FLUENTE", "AVANCADO", "INTERMEDIARIO", "BASICO"]
                prof_colors = {
                    "NATIVO": "#198754", "FLUENTE": "#0d6efd",
                    "AVANCADO": "#6f42c1", "INTERMEDIARIO": "#fd7e14", "BASICO": "#6c757d",
                }
                prof_widths = {
                    "NATIVO": 100, "FLUENTE": 85, "AVANCADO": 65, "INTERMEDIARIO": 45, "BASICO": 25,
                }
                cols = st.columns(min(len(langs), 4))
                for col, lang in zip(cols, langs):
                    prof  = lang.get("proficiency", "BASICO")
                    color = prof_colors.get(prof, "#6c757d")
                    width = prof_widths.get(prof, 25)
                    cert  = " 🏅" if lang.get("certified") else ""
                    with col:
                        st.markdown(
                            f'<div style="border:1px solid {color};border-radius:8px;'
                            f'padding:12px;text-align:center">'
                            f'<div style="font-size:1.1rem;font-weight:bold">{lang["name"]}{cert}</div>'
                            f'<div style="font-size:0.8rem;color:{color};font-weight:600;margin:4px 0">'
                            f'{prof}</div>'
                            f'<div style="background:#e9ecef;border-radius:3px;height:6px">'
                            f'<div style="background:{color};width:{width}%;height:6px;border-radius:3px"></div>'
                            f'</div></div>', unsafe_allow_html=True,
                        )

        # ── Soft Skills & Certs ────────────────────────────────────────
        with tab_soft:
            soft = p.get("soft_skills", [])
            if soft:
                st.markdown("**🤝 Soft Skills:**")
                st.markdown(" · ".join(f"`{s}`" for s in soft))
            else:
                st.info("Nenhuma soft skill extraída.")

# ============================================================
# PÁGINA: Melhoria de CV
# ============================================================
elif page == "🛠️ Melhoria de CV":
    st.title("🛠️ Melhoria de CV")
    st.caption("Diagnóstico estrutural e sugestões de clareza — sem inventar conteúdo.")

    col_upload, col_jd = st.columns([1, 1])
    with col_upload:
        pdf_file = st.file_uploader("Upload do PDF", type=["pdf"], key="uploader_improvement")
    with col_jd:
        st.markdown("**Vaga alvo (opcional)**")
        st.caption("Informar uma vaga alinha as melhorias com as keywords da posição.")
        jobs_data = api_get("/jobs", params={"limit": 100})
        jd_options = {"Nenhuma (diagnóstico geral)": None}
        if jobs_data and jobs_data.get("jobs"):
            for j in jobs_data["jobs"]:
                label = f"{j['title']} — {j.get('company', '')} [{j.get('seniority', '')}]"
                jd_options[label] = j["id"]
        selected_jd = st.selectbox("Selecione a vaga", list(jd_options.keys()))
        jd_id_selected = jd_options[selected_jd]

    col_btn1, col_btn2, _ = st.columns([1, 1, 2])
    with col_btn1:
        btn_diagnose = st.button(
            "🔍 Apenas Diagnosticar",
            disabled=st.session_state.improvement_running or not pdf_file,
            help="Rápido — sem LLM de melhoria",
        )
    with col_btn2:
        btn_improve = st.button(
            "✨ Diagnosticar + Melhorar",
            type="primary",
            disabled=st.session_state.improvement_running or not pdf_file,
            help="Mais lento — usa LLM para reescrever descrições",
        )

    if (btn_diagnose or btn_improve) and pdf_file:
        mode = "diagnose" if btn_diagnose else "improve"
        st.session_state.improvement_pdf_bytes = pdf_file.read()
        st.session_state.improvement_pdf_name  = pdf_file.name
        st.session_state.improvement_jd_id     = jd_id_selected
        st.session_state.improvement_mode      = mode
        st.session_state.improvement_running   = True
        st.session_state.improvement_result    = None
        st.session_state.improvement_error     = None
        st.rerun()

    if st.session_state.improvement_running and st.session_state.improvement_result is None:
        pdf_bytes = st.session_state.improvement_pdf_bytes
        mode      = st.session_state.improvement_mode
        jd_id_val = st.session_state.improvement_jd_id
        label     = "Diagnosticando" if mode == "diagnose" else "Diagnosticando e melhorando"

        if pdf_bytes:
            with st.spinner(f"{label} `{st.session_state.improvement_pdf_name}`..."):
                endpoint = "/cv/diagnose" if mode == "diagnose" else "/cv/improve"
                data     = {}
                if mode == "improve" and jd_id_val:
                    data["jd_id"] = jd_id_val
                result = api_post_form(
                    endpoint,
                    data=data,
                    files={"pdf": (
                        st.session_state.improvement_pdf_name,
                        pdf_bytes,
                        "application/pdf",
                    )},
                )
            if result and "__error__" in result:
                st.session_state.improvement_error   = result["__error__"]
                st.session_state.improvement_running = False
            elif result:
                st.session_state.improvement_result  = result
                st.session_state.improvement_running = False
                st.session_state.improvement_pdf_bytes = None
            else:
                st.session_state.improvement_error   = "Resposta vazia da API"
                st.session_state.improvement_running = False
            st.rerun()

    if st.session_state.improvement_result:
        res = st.session_state.improvement_result
        mode = st.session_state.improvement_mode

        col_h, col_clr = st.columns([5, 1])
        with col_clr:
            if st.button("🗑 Limpar", key="clear_improvement"):
                st.session_state.improvement_result = None
                st.rerun()

        # ── Extrai diagnosis (presente em ambos os modos) ──────────────
        diag = res.get("diagnosis") or res  # /cv/diagnose retorna direto
        if "diagnosis" in res:
            diag = res["diagnosis"]

        name  = res.get("candidate_name") or "Candidato"
        score = diag.get("cv_quality_score", 0)
        ready = diag.get("is_ready_for_matching", False)
        crit  = diag.get("critical_count", 0)
        warn  = diag.get("warning_count", 0)
        info  = diag.get("info_count", 0)

        # ── Score header ────────────────────────────────────────────────
        st.divider()
        score_color = "#28a745" if score >= 75 else ("#ffc107" if score >= 50 else "#dc3545")
        col_score, col_meta = st.columns([1, 3])
        with col_score:
            st.markdown(
                f'<div style="border:2px solid {score_color};border-radius:12px;'
                f'padding:16px;text-align:center">'
                f'<div style="font-size:0.8rem;color:#666">Qualidade do CV</div>'
                f'<div style="font-size:2.8rem;font-weight:bold;color:{score_color}">'
                f'{score:.0f}</div>'
                f'<div style="font-size:0.75rem;color:#999">/ 100</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with col_meta:
            st.markdown(f"### {name}")
            ready_badge = (
                '✅ Pronto para matching' if ready
                else '⚠️ Requer correções antes do matching'
            )
            st.markdown(ready_badge)
            st.markdown(
                f'<span style="background:#dc3545;color:white;padding:3px 10px;'
                f'border-radius:10px;margin-right:6px;font-size:0.8rem">'
                f'🔴 {crit} crítico(s)</span>'
                f'<span style="background:#ffc107;color:white;padding:3px 10px;'
                f'border-radius:10px;margin-right:6px;font-size:0.8rem">'
                f'🟡 {warn} aviso(s)</span>'
                f'<span style="background:#0d6efd;color:white;padding:3px 10px;'
                f'border-radius:10px;font-size:0.8rem">'
                f'🔵 {info} info(s)</span>',
                unsafe_allow_html=True,
            )
            st.caption(diag.get("summary", ""))

        # ── Tabs ────────────────────────────────────────────────────────
        tabs = ["🔍 Diagnóstico"]
        if mode == "improve":
            tabs.append("✨ Melhorias de Clareza")
        tab_objs = st.tabs(tabs)

        # ── Tab: Diagnóstico ────────────────────────────────────────────
        with tab_objs[0]:
            issues = diag.get("issues", [])
            if not issues:
                st.success("✅ Nenhum problema estrutural encontrado!")
            else:
                SEV_CONFIG = {
                    "critical": {"icon": "🔴", "color": "#dc3545", "label": "Crítico"},
                    "warning":  {"icon": "🟡", "color": "#ffc107", "label": "Aviso"},
                    "info":     {"icon": "🔵", "color": "#0d6efd", "label": "Info"},
                }
                SECTION_LABELS = {
                    "experience": "⏱ Experiência",
                    "skills":     "🔧 Skills",
                    "seniority":  "📈 Senioridade",
                    "languages":  "🌐 Idiomas",
                    "general":    "📋 Geral",
                }
                # Agrupa por seção
                by_section: dict[str, list] = {}
                for issue in issues:
                    by_section.setdefault(issue["section"], []).append(issue)

                section_order = ["experience", "skills", "seniority", "languages", "general"]
                for section in section_order:
                    section_issues = by_section.get(section, [])
                    if not section_issues:
                        continue
                    st.markdown(f"**{SECTION_LABELS.get(section, section)}**")
                    for issue in section_issues:
                        sev    = issue["severity"]
                        cfg    = SEV_CONFIG.get(sev, SEV_CONFIG["info"])
                        items  = issue.get("affected_items", [])
                        with st.expander(
                            f"{cfg['icon']} **{issue['title']}**",
                            expanded=(sev == "critical"),
                        ):
                            st.markdown(issue["description"])
                            st.markdown(
                                f'<div style="background:#f8f9fa;border-left:3px solid '
                                f'{cfg["color"]};padding:8px 12px;border-radius:0 4px 4px 0;'
                                f'margin-top:8px">'
                                f'<strong>✅ O que fazer:</strong> {issue["action"]}'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            if items:
                                st.caption("Itens afetados: " + " · ".join(items[:5]))

            # Dicas gerais (modo improve)
            tips = res.get("general_tips", [])
            if tips:
                st.divider()
                st.markdown("**💡 Dicas Gerais**")
                for tip in tips:
                    st.info(tip)

        # ── Tab: Melhorias de Clareza ───────────────────────────────────
        if mode == "improve" and len(tab_objs) > 1:
            with tab_objs[1]:
                sections = res.get("improved_sections", [])
                jd_title = res.get("jd_title")

                if jd_title:
                    st.caption(f"🎯 Melhorias alinhadas com a vaga: **{jd_title}**")

                if not sections:
                    st.info(
                        "Nenhuma seção foi melhorada. "
                        "Isso pode ocorrer quando as descrições já estão bem escritas "
                        "ou estão muito curtas para reescrita."
                    )
                else:
                    st.caption(
                        "⚠️ Revise cada melhoria antes de aplicar. "
                        "O agente reescreve apenas o que já existe — nunca inventa conteúdo."
                    )
                    for sec in sections:
                        section_label = (
                            "📝 Sumário Profissional"
                            if sec["section"] == "summary"
                            else f"⏱ {sec['role']}"
                        )
                        keywords = sec.get("keywords_added", [])
                        kw_badge = (
                            f" · 🏷️ {len(keywords)} keyword(s) da vaga inserida(s)"
                            if keywords else ""
                        )
                        with st.expander(f"**{section_label}**{kw_badge}", expanded=True):
                            col_orig, col_impr = st.columns(2)
                            with col_orig:
                                st.markdown(
                                    '<div style="background:#f8f9fa;border:1px solid #dee2e6;'
                                    'border-radius:6px;padding:10px">'
                                    '<div style="font-size:0.75rem;color:#6c757d;'
                                    'margin-bottom:6px">ORIGINAL</div>',
                                    unsafe_allow_html=True,
                                )
                                st.markdown(sec.get("original", "_vazio_"))
                                st.markdown('</div>', unsafe_allow_html=True)
                            with col_impr:
                                st.markdown(
                                    '<div style="background:#f0fff4;border:1px solid #28a745;'
                                    'border-radius:6px;padding:10px">'
                                    '<div style="font-size:0.75rem;color:#28a745;'
                                    'margin-bottom:6px">MELHORADO</div>',
                                    unsafe_allow_html=True,
                                )
                                st.markdown(sec.get("improved", "_sem melhoria_"))
                                st.markdown('</div>', unsafe_allow_html=True)

                            changes = sec.get("changes_made", [])
                            if changes:
                                st.markdown("**🔧 Mudanças realizadas:**")
                                for c in changes:
                                    st.caption(f"• {c}")
                            if keywords:
                                st.markdown(
                                    "**🏷️ Keywords da vaga inseridas:** "
                                    + " · ".join(f"`{k}`" for k in keywords)
                                )
                            # Botão de copiar
                            improved_text = sec.get("improved", "")
                            if improved_text:
                                st.code(improved_text, language=None)

# ============================================================
# PÁGINA: Vagas Disponíveis
# ============================================================
elif page == "📋 Vagas Disponíveis":
    st.title("📋 Vagas Disponíveis")

    # ── Stats bar ─────────────────────────────────────────────────────────
    stats = api_get("/jobs/stats")
    if stats:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("✅ Vagas Ativas", stats.get("active", 0),
                      help="Extraídas nos últimos 14 dias")
        with c2:
            st.metric("🗄️ Arquivadas", stats.get("archived", 0),
                      help="Extraídas há mais de 14 dias")
        with c3:
            st.metric("📦 Total no Banco", stats.get("total", 0))
        with c4:
            last = stats.get("last_scraped_at")
            if last:
                try:
                    from datetime import timezone
                    dt  = datetime.fromisoformat(last)
                    ago = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
                    h, m = divmod(int(ago.total_seconds() // 60), 60)
                    ago_str = f"{h}h {m}m atrás" if h else f"{m}m atrás"
                except Exception:
                    ago_str = last[:16]
                st.metric("🕐 Último Scraping", ago_str)
            else:
                st.metric("🕐 Último Scraping", "Nunca")

    st.divider()

    # ── Painel do Scraper ──────────────────────────────────────────────────
    with st.expander("⚙️ Executar Scraper", expanded=False):
        st.caption("Coleta novas vagas das fontes configuradas e salva no banco.")

        scraper_status = api_get("/scraper/status")
        is_running = scraper_status.get("running", False) if scraper_status else False

        col_src, col_btn = st.columns([2, 1])
        with col_src:
            source = st.selectbox(
                "Fonte",
                ["all", "gupy", "remoteok"],
                format_func=lambda x: {"all": "🌐 Todas as fontes", "gupy": "🟣 Gupy", "remoteok": "🟢 RemoteOK"}[x],
            )
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            run_btn = st.button(
                "▶️ Executar" if not is_running else "⏳ Executando...",
                type="primary",
                disabled=is_running,
                use_container_width=True,
            )

        if run_btn:
            result = api_post_form("/scraper/run", data={"source": source}, files={})
            if result and "__error__" not in result:
                st.success(f"✅ {result.get('message', 'Scraper iniciado!')}")
                st.rerun()
            elif result:
                st.error(result.get("__error__", "Erro ao iniciar scraper"))

        if scraper_status:
            if is_running:
                st.info("⏳ Scraper em execução — atualize a página para ver o progresso.")
            if scraper_status.get("last_run"):
                st.caption(f"Último run: {scraper_status['last_run'][:19].replace('T', ' ')}")
            if scraper_status.get("last_error"):
                st.error(f"Último erro: {scraper_status['last_error']}")
            if scraper_status.get("last_result"):
                with st.expander("📋 Output do último run"):
                    st.code(scraper_status["last_result"])

    st.divider()

    # ── Filtros ────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        f_domain = st.selectbox("Domínio", ["Todos", "TECH", "DATA", "BUSINESS", "CREATIVE"])
    with col2:
        f_seniority = st.selectbox("Senioridade", ["Todas", "JUNIOR", "PLENO", "SENIOR", "ESPECIALISTA"])
    with col3:
        f_limit = st.number_input("Limite", min_value=10, max_value=500, value=50)
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        show_archived = st.checkbox("Incluir arquivadas", value=False,
                                    help="Mostra vagas extraídas há mais de 14 dias")

    params = {"limit": f_limit, "show_archived": str(show_archived).lower()}
    if f_domain    != "Todos":  params["domain"]    = f_domain
    if f_seniority != "Todas": params["seniority"] = f_seniority

    data = api_get("/jobs", params=params)
    if data:
        active_c   = data.get("active_count", data.get("total", 0))
        archived_c = data.get("archived_count", 0)
        total_c    = data.get("total", 0)

        if show_archived:
            st.caption(
                f"**{total_c}** vagas encontradas — "
                f"✅ {active_c} ativas · 🗄️ {archived_c} arquivadas"
            )
        else:
            st.caption(f"**{active_c}** vagas ativas encontradas (últimos 14 dias)")

        jobs = data.get("jobs", [])
        if jobs:
            import pandas as pd
            from datetime import timezone as _tz
            cutoff_str = data.get("cutoff", "")
            rows = []
            for j in jobs:
                scraped = j.get("scraped_at") or ""
                # is_active_window pode vir da API ou ser derivado localmente
                if "is_active_window" in j:
                    is_active = j["is_active_window"]
                elif scraped:
                    try:
                        dt = datetime.fromisoformat(scraped)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=_tz.utc)
                        is_active = dt >= datetime.fromisoformat(cutoff_str) if cutoff_str else True
                    except Exception:
                        is_active = True
                else:
                    is_active = False
                status = "✅ Ativa" if is_active else "🗄️ Arquivada"
                rows.append({
                    "Status":      status,
                    "Título":      j["title"],
                    "Empresa":     j.get("company", ""),
                    "Domínio":     j.get("domain", ""),
                    "Senioridade": j.get("seniority", ""),
                    "Fonte":       j.get("source", ""),
                    "Exp. mín.":   j.get("min_experience_years", ""),
                    "Confiança":   f"{j.get('extraction_confidence', 0):.0%}",
                    "Extraída em": scraped[:10] if scraped else "—",
                    "ID":          j["id"],
                })
            df = pd.DataFrame(rows)
            def _row_style(row):
                if row["Status"].startswith("🗄️"):
                    return ["color: #adb5bd"] * len(row)
                return [""] * len(row)
            st.dataframe(
                df.style.apply(_row_style, axis=1),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma vaga encontrada. Use o painel acima para executar o scraper.")

# ============================================================
# PÁGINA: Health
# ============================================================
elif page == "❤️ Health":
    st.title("❤️ Status dos Serviços")
    data = api_get("/health")
    if data:
        overall = data.get("status", "unknown")
        if overall == "healthy":
            st.success("✅ Todos os serviços operacionais")
        else:
            st.warning("⚠️ Um ou mais serviços com problema")

        services = data.get("services", {})
        icons = {"postgres": "🐘", "redis": "🔴", "ollama": "🦙", "chromadb": "🔵"}
        cols  = st.columns(len(services))
        for col, (name, status) in zip(cols, services.items()):
            with col:
                ok = status == "ok"
                st.markdown(
                    f'<div style="border:1px solid {"#28a745" if ok else "#dc3545"};'
                    f'border-radius:8px;padding:16px;text-align:center;">'
                    f'<div style="font-size:2rem">{icons.get(name, "⚙️")}</div>'
                    f'<div style="font-weight:bold">{name}</div>'
                    f'<div style="color:{"#28a745" if ok else "#dc3545"}">'
                    f'{"✅ ok" if ok else "❌ " + status}</div></div>',
                    unsafe_allow_html=True,
                )