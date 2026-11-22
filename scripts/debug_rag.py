import streamlit as st

from app import (
    CLAIMS_PATH,
    RISK_PATH,
    build_claims_dataframe,
    inject_custom_css,
    initialize_session_state,
    load_mapped_claims,
    load_risk_assessment,
    render_app_header,
    render_audit_workspace,
    render_domain_bar_chart,
    render_enterprise_console,
    render_requirement_scorecard,
    render_status_pie_chart,
    set_active_tab,
)


def render_grc_dashboard(df_claims, risk_assessment: dict) -> None:
    render_requirement_scorecard(risk_assessment.get("requirement_results", {}))
    st.write("")
    left_column, right_column = st.columns(2, gap="medium")

    with left_column:
        with st.container(border=True):
            st.markdown('<p class="grc-section-title">Risk by domain</p>', unsafe_allow_html=True)
            domain_scores = risk_assessment.get("domain_scores", {})
            if not domain_scores:
                st.info("No domain scores were provided by the risk-assessment pipeline.")
            else:
                render_domain_bar_chart(domain_scores)

    with right_column:
        with st.container(border=True):
            st.markdown('<p class="grc-section-title">Claim outcomes</p>', unsafe_allow_html=True)
            render_status_pie_chart(df_claims)


def main() -> None:
    st.set_page_config(
        page_title="GRC Console (Debug)",
        page_icon="???",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    inject_custom_css()
    initialize_session_state()

    claims_records = load_mapped_claims(str(CLAIMS_PATH))
    risk_assessment = load_risk_assessment(str(RISK_PATH))
    df_claims = build_claims_dataframe(claims_records)

    render_app_header()
    active_tab = st.session_state.active_tab

    if active_tab == "Enterprise Console":
        render_enterprise_console(df_claims, risk_assessment)
    elif active_tab == "Audit Workspace":
        render_audit_workspace(df_claims)
    elif active_tab == "GRC Dashboard":
        render_grc_dashboard(df_claims, risk_assessment)
    else:
        set_active_tab("Enterprise Console")
        st.rerun()


if __name__ == "__main__":
    main()
