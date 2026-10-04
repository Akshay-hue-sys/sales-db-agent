import marimo

__generated_with = "0.25.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import duckdb
    import altair as alt
    from pathlib import Path

    db_path = Path(__file__).resolve().parents[1] / "sales-db-agent.duckdb"
    return alt, db_path, duckdb, mo


@app.cell
def _(mo):
    mo.md("""
    # 🔍 Sales DB Agent: Observability & Trace Console
    Reactive telemetry dashboard powered by **DuckDB**, **dlt**, and **Marimo**.
    """)
    return


@app.cell
def _(db_path, duckdb):
    # Establish connection and pull sessions
    conn = duckdb.connect(str(db_path), read_only=True)
    sessions_df = conn.execute("""
        SELECT DISTINCT session_id 
        FROM traces.log_records 
        WHERE session_id IS NOT NULL 
        ORDER BY session_id
    """).df()
    session_list = ["ALL"] + list(sessions_df["session_id"])
    return conn, session_list


@app.cell
def _(mo, session_list):
    session_dropdown = mo.ui.dropdown(
        options=session_list,
        value="ALL",
        label="Filter by Session ID:"
    )
    session_dropdown  # noqa: B018 - Marimo renders the final cell expression.
    return (session_dropdown,)


@app.cell
def _(conn, session_dropdown):
    # Query summary metrics based on selection
    session_filter = ""
    if session_dropdown.value != "ALL":
        session_filter = "WHERE session_id = ?"

    session_params = [] if session_dropdown.value == "ALL" else [session_dropdown.value]
    summary_df = conn.execute(f"""
        SELECT 
            count(*) as total_events,
            count(DISTINCT session_id) as total_sessions,
            count(CASE WHEN type = 'tool_use' THEN 1 END) as tool_calls,
            COALESCE(MAX(data__total_tokens), 0) as peak_tokens
        FROM traces.log_records
        {session_filter}
    """, session_params).df()
    return session_filter, session_params, summary_df


@app.cell
def _(mo, summary_df):
    rec = summary_df.iloc[0]
    mo.hstack(
        [
            mo.stat(value=str(int(rec["total_events"])), label="Total Events"),
            mo.stat(value=str(int(rec["total_sessions"])), label="Active Sessions"),
            mo.stat(value=str(int(rec["tool_calls"])), label="Tool Invocations"),
            mo.stat(value=str(int(rec["peak_tokens"])), label="Peak Request Tokens"),
        ],
        justify="space-around",
    )
    return


@app.cell
def _(alt, conn, mo, session_filter, session_params):
    # Tool breakdown chart
    tool_df = conn.execute(f"""
        SELECT 
            COALESCE(data__name, 'unknown') as tool_name,
            count(*) as invocations
        FROM traces.log_records
        WHERE type = 'tool_use'
        {session_filter.replace('WHERE', 'AND') if session_filter else ''}
        GROUP BY tool_name
        ORDER BY invocations DESC
    """, session_params).df()

    if not tool_df.empty:
        chart = (
            alt.Chart(tool_df)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("tool_name:N", title="Tool Name", sort="-y"),
                y=alt.Y("invocations:Q", title="Invocations"),
                color=alt.Color("tool_name:N", legend=None)
            )
            .properties(title="Tool Invocation Frequency", width=550, height=260)
        )
        tool_view = mo.ui.altair_chart(chart)
    else:
        tool_view = mo.md("_No tool use records found for current selection._")

    tool_view  # noqa: B018 - Marimo renders the final cell expression.
    return


@app.cell
def _(conn, mo, session_filter, session_params):
    # Raw event table
    events_df = conn.execute(f"""
        SELECT 
            timestamp,
            session_id,
            type,
            COALESCE(data__name, data__reason, type) as payload_summary
        FROM traces.log_records
        {session_filter}
        ORDER BY timestamp DESC
        LIMIT 50
    """, session_params).df()

    mo.md("### Recent Trace Events")
    return (events_df,)


@app.cell
def _(events_df, mo):
    mo.ui.table(events_df)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
