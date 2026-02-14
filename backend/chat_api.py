#!/usr/bin/env python3
"""
MyOrg Migration Agentic Chat — FastAPI backend
Powers the dashboard chat panel using Grok 4 via OCI GenAI
Connects to ADB for live data queries
"""
import json, os, time, traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import oci
import oracledb

app = FastAPI(title="Migration Assessment Chat")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# === OCI GenAI Config ===
OCI_CONFIG = oci.config.from_file("~/.oci/config", "DEFAULT")
COMPARTMENT = os.getenv("OCI_COMPARTMENT_ID", "")
GENAI_ENDPOINT = os.getenv("OCI_GENAI_ENDPOINT", "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com")
MODEL_ID = os.getenv("OCI_GENAI_MODEL", "xai.grok-4")

genai_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
    OCI_CONFIG, service_endpoint=GENAI_ENDPOINT
)

# === ADB Config ===
ADB_USER = "ADMIN"
ADB_PASS = os.getenv("ADB_PASS", "")
ADB_DSN = os.getenv("ADB_DSN", "")
ADB_WALLET = os.getenv("ADB_WALLET_DIR", "")
ADB_WALLET_PW = os.getenv("ADB_WALLET_PASSWORD", "")

def get_adb_connection():
    return oracledb.connect(
        user=ADB_USER, password=ADB_PASS, dsn=ADB_DSN,
        config_dir=ADB_WALLET, wallet_location=ADB_WALLET, wallet_password=ADB_WALLET_PW
    )

def run_adb_query(sql, params=None):
    """Execute a read-only query against ADB and return results as list of dicts."""
    try:
        conn = get_adb_connection()
        cur = conn.cursor()
        cur.execute(sql, params or {})
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        return [{"error": str(e)}]

# === Preload summary context for Grok ===
def load_migration_context():
    """Build a concise summary of the migration state for Grok's system prompt."""
    try:
        conn = get_adb_connection()
        cur = conn.cursor()

        # Summary stats
        cur.execute("SELECT COUNT(*) FROM RVTOOLS_VINFO")
        vm_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM APP_INVENTORY")
        app_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM APP_MIGRATION_PLAN")
        plan_count = cur.fetchone()[0]

        # Migration target distribution
        cur.execute("""
            SELECT MIGRATION_TARGET, COUNT(*) cnt, SUM(VM_COUNT) vms
            FROM APP_MIGRATION_PLAN
            WHERE MIGRATION_TARGET IS NOT NULL
            GROUP BY MIGRATION_TARGET ORDER BY cnt DESC
        """)
        targets = [{"target": r[0], "apps": r[1], "vms": r[2]} for r in cur.fetchall()]

        # Wave distribution
        cur.execute("""
            SELECT MIGRATION_WAVE, COUNT(*) cnt, SUM(VM_COUNT) vms
            FROM APP_MIGRATION_PLAN
            WHERE MIGRATION_WAVE IS NOT NULL
            GROUP BY MIGRATION_WAVE ORDER BY MIGRATION_WAVE
        """)
        waves = [{"wave": r[0], "apps": r[1], "vms": r[2]} for r in cur.fetchall()]

        # Category breakdown
        cur.execute("""
            SELECT APP_CATEGORY, COUNT(*) cnt
            FROM APP_MIGRATION_PLAN
            GROUP BY APP_CATEGORY ORDER BY cnt DESC FETCH FIRST 10 ROWS ONLY
        """)
        categories = [{"category": r[0], "count": r[1]} for r in cur.fetchall()]

        # Top apps by VM count
        cur.execute("""
            SELECT APPLICATION, VM_COUNT, MIGRATION_TARGET, MIGRATION_WAVE, COMPLEXITY, RISK_LEVEL, NOTES
            FROM APP_MIGRATION_PLAN
            WHERE VM_COUNT > 0
            ORDER BY VM_COUNT DESC FETCH FIRST 25 ROWS ONLY
        """)
        top_apps = []
        for r in cur.fetchall():
            top_apps.append({"name": r[0], "vms": r[1], "target": r[2], "wave": r[3],
                           "complexity": r[4], "risk": r[5], "notes": r[6]})

        # Cluster breakdown
        cur.execute("""
            SELECT CLUSTER_NAME, COUNT(*) cnt
            FROM RVTOOLS_VINFO
            WHERE CLUSTER_NAME IS NOT NULL
            GROUP BY CLUSTER_NAME ORDER BY cnt DESC
        """)
        clusters = [{"cluster": r[0], "vms": r[1]} for r in cur.fetchall()]

        # OS distribution
        cur.execute("""
            SELECT
              CASE
                WHEN OS_CONFIG LIKE '%2016%' OR OS_CONFIG LIKE '%2019%' OR OS_CONFIG LIKE '%2022%' THEN 'Win 2016+'
                WHEN OS_CONFIG LIKE '%2012%' THEN 'Win 2012'
                WHEN OS_CONFIG LIKE '%2008%' THEN 'Win 2008R2'
                WHEN OS_CONFIG LIKE '%Red Hat%' OR OS_CONFIG LIKE '%RHEL%' THEN 'RHEL'
                WHEN OS_CONFIG LIKE '%SUSE%' THEN 'SUSE'
                WHEN OS_CONFIG LIKE '%Ubuntu%' THEN 'Ubuntu'
                ELSE 'Other'
              END os_group, COUNT(*) cnt
            FROM RVTOOLS_VINFO
            GROUP BY
              CASE
                WHEN OS_CONFIG LIKE '%2016%' OR OS_CONFIG LIKE '%2019%' OR OS_CONFIG LIKE '%2022%' THEN 'Win 2016+'
                WHEN OS_CONFIG LIKE '%2012%' THEN 'Win 2012'
                WHEN OS_CONFIG LIKE '%2008%' THEN 'Win 2008R2'
                WHEN OS_CONFIG LIKE '%Red Hat%' OR OS_CONFIG LIKE '%RHEL%' THEN 'RHEL'
                WHEN OS_CONFIG LIKE '%SUSE%' THEN 'SUSE'
                WHEN OS_CONFIG LIKE '%Ubuntu%' THEN 'Ubuntu'
                ELSE 'Other'
              END
            ORDER BY cnt DESC
        """)
        os_dist = [{"os": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.close()
        conn.close()

        return {
            "vm_count": vm_count, "app_count": app_count, "plan_count": plan_count,
            "targets": targets, "waves": waves, "categories": categories,
            "top_apps": top_apps, "clusters": clusters, "os_distribution": os_dist,
            "cost": {
                "onprem_annual": 2290000, "oci_optimized_annual": 899000,
                "savings_pct": 60.66,
                "breakdown": {
                    "compute_oci": 773000, "mysql_heatwave": 4300,
                    "mongodb_ajd": 9500, "oracle_db": 24500, "block_volume": 88000
                }
            }
        }
    except Exception as e:
        return {"error": str(e)}

# Cache the context (refresh every 5 min)
_ctx_cache = {"data": None, "ts": 0}
def get_context():
    if time.time() - _ctx_cache["ts"] > 300:
        _ctx_cache["data"] = load_migration_context()
        _ctx_cache["ts"] = time.time()
    return _ctx_cache["data"]

# === SQL Generator for live queries ===
SAFE_TABLES = {
    "RVTOOLS_VINFO": ["VM_NAME","POWERSTATE","DNS_NAME","CLUSTER_NAME","PRIMARY_IP","APPLICATION",
                      "CPUS","MEMORY_MB","TOTAL_DISK_MIB","OS_CONFIG","MIGRATION_TARGET",
                      "MIGRATION_WAVE","DATACENTER","HOST_NAME","VM_CRITICALITY","VM_ENVIRONMENT"],
    "APP_MIGRATION_PLAN": ["PLAN_ID","APPLICATION","VM_COUNT","TOTAL_CPUS","TOTAL_MEM_GB",
                          "TOTAL_DISK_TB","APP_CATEGORY","MIGRATION_TARGET","TARGET_SERVICE",
                          "MIGRATION_WAVE","COMPLEXITY","RISK_LEVEL","ESTIMATED_DAYS","STATUS","NOTES"],
    "APP_INVENTORY": ["APP_ID","APP_NAME","VENDOR","CATEGORY","ENVIRONMENT","CRITICALITY",
                        "MIGRATION_STRATEGY","TARGET_OCI_SERVICE","MIGRATION_WAVE",
                        "MIGRATION_COMPLEXITY","ESTIMATED_EFFORT_DAYS",
                        "MONTHLY_COST_CURRENT","MONTHLY_COST_OCI"]
}

def build_schema_desc():
    lines = []
    for tbl, cols in SAFE_TABLES.items():
        lines.append(f"Table: {tbl} — Columns: {', '.join(cols)}")
    return "\n".join(lines)

SYSTEM_PROMPT = """You are the MyOrg OCI Migration Analyst, an expert AI assistant embedded in the migration dashboard.
You help IT leadership, infrastructure teams, and app owners understand their cloud migration plan.

CONTEXT — MyOrg (AC) is a healthcare organization migrating from on-prem VMware to Oracle Cloud Infrastructure (OCI).
The migration has 3 target options:
- OCI-Native: Full cloud-native on OCI (compute, DB services, storage) — best cost savings (~60%)
- OCVS: Oracle Cloud VMware Solution — lift-and-shift VMware workloads to OCI-managed VMware — moderate savings (~45%)
- Stay-OnPrem: Remains on-prem — for device-connected, latency-sensitive, or patient-safety-critical systems

Migration waves:
- Wave 1 (Q2-Q3 2026): Quick wins — low-risk, web-based apps, analytics
- Wave 2 (Q4 2026): Core systems — revenue cycle, patient engagement
- Wave 3 (Q1 2027): Complex/OCVS — VMware-dependent, device integrations

Cost baseline (from Matilda TCO analysis):
- Current on-prem: $2.29M/year
- OCI Optimized: $899K/year (60.66% savings)
- Breakdown: Compute $773K, MySQL HeatWave $4.3K, Autonomous JSON DB $9.5K, Oracle DB $24.5K, Block Volume $88K

Key concerns for healthcare administrators:
- Critical care systems must not be disrupted by network issues
- Critical systems close to operational facilities (latency < 10ms)
- Regulatory compliance mandatory for all sensitive data
- VMware licensing costs are the primary driver for migration

DATABASE SCHEMA (you can generate SQL to query these):
{schema}

CURRENT STATE:
{context}

RULES:
1. When asked about specific apps, VMs, clusters, or counts — generate a SQL query, execute it, and report results.
2. Only generate SELECT queries. Never INSERT, UPDATE, DELETE, DROP, or ALTER.
3. When answering cost questions, use the Matilda TCO numbers as baseline.
4. Be concise but thorough. Use numbers from the data, not guesses.
5. If asked to change a migration target or wave, explain that write-back requires admin approval.
6. Format numbers with commas and dollar signs where appropriate.
7. When unsure, say so — don't hallucinate data.
8. If the question needs a SQL query, wrap it in <SQL>...</SQL> tags in your response.
9. IMPORTANT: This is an Oracle Autonomous Database. Use Oracle SQL syntax:
   - Use FETCH FIRST N ROWS ONLY instead of LIMIT N
   - Use NVL() instead of IFNULL() or COALESCE()
   - String comparisons are case-sensitive; use UPPER() or LOWER() for flexible matching
   - Use || for string concatenation, not CONCAT()
   - Date functions: SYSDATE, TO_DATE(), TO_CHAR()
"""

# === Chat Models ===
class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    run_sql: Optional[bool] = True

class ChatResponse(BaseModel):
    reply: str
    sql_executed: Optional[str] = None
    sql_results: Optional[list] = None

# === Call Grok 4 ===
def call_grok4(messages_list, max_tokens=4096, temperature=0.3):
    """Call Grok 4 via OCI GenAI and return the text response."""
    oci_messages = []
    for msg in messages_list:
        role = msg["role"].upper()
        if role == "SYSTEM":
            oci_messages.append(
                oci.generative_ai_inference.models.SystemMessage(
                    content=[oci.generative_ai_inference.models.TextContent(text=msg["content"])]
                )
            )
        elif role == "USER":
            oci_messages.append(
                oci.generative_ai_inference.models.UserMessage(
                    content=[oci.generative_ai_inference.models.TextContent(text=msg["content"])]
                )
            )
        elif role == "ASSISTANT":
            oci_messages.append(
                oci.generative_ai_inference.models.AssistantMessage(
                    content=[oci.generative_ai_inference.models.TextContent(text=msg["content"])]
                )
            )

    chat_detail = oci.generative_ai_inference.models.ChatDetails(
        compartment_id=COMPARTMENT,
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(model_id=MODEL_ID),
        chat_request=oci.generative_ai_inference.models.GenericChatRequest(
            api_format="GENERIC",
            messages=oci_messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
    )

    response = genai_client.chat(chat_detail)
    # Extract text
    text_parts = []
    for choice in response.data.chat_response.choices:
        for part in choice.message.content:
            if hasattr(part, 'text'):
                text_parts.append(part.text)
    return "\n".join(text_parts)

# === Extract and execute SQL from Grok response ===
import re

def extract_sql(text):
    """Extract SQL from <SQL>...</SQL> tags."""
    match = re.search(r'<SQL>(.*?)</SQL>', text, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
        # Safety: only allow SELECT
        if not sql.upper().startswith("SELECT"):
            return None
        # Block dangerous keywords
        dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "MERGE", "CREATE", "GRANT"]
        upper = sql.upper()
        for d in dangerous:
            if d in upper.split():
                return None
        return sql
    return None

# === API Endpoints ===
@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        ctx = get_context()
        schema = build_schema_desc()
        sys_prompt = SYSTEM_PROMPT.format(schema=schema, context=json.dumps(ctx, indent=2, default=str))

        # Build conversation
        conversation = [{"role": "system", "content": sys_prompt}]
        for msg in req.messages:
            conversation.append({"role": msg.role, "content": msg.content})

        # Call Grok 4
        reply_text = call_grok4(conversation)

        # Check for SQL in response
        sql = extract_sql(reply_text) if req.run_sql else None
        sql_results = None

        if sql:
            sql_results = run_adb_query(sql)
            # If we got results, call Grok again with the data to formulate a final answer
            if sql_results and not (len(sql_results) == 1 and "error" in sql_results[0]):
                # Truncate large results
                results_text = json.dumps(sql_results[:50], default=str)
                if len(results_text) > 8000:
                    results_text = results_text[:8000] + "... (truncated)"

                followup = conversation + [
                    {"role": "assistant", "content": reply_text},
                    {"role": "user", "content": f"Here are the SQL query results:\n{results_text}\n\nPlease analyze these results and provide a clear, concise answer to the original question. Format numbers nicely. Do not include SQL tags in this response."}
                ]
                reply_text = call_grok4(followup)

        # Clean SQL tags from final response
        reply_text = re.sub(r'<SQL>.*?</SQL>', '', reply_text, flags=re.DOTALL).strip()

        return ChatResponse(reply=reply_text, sql_executed=sql,
                          sql_results=sql_results[:20] if sql_results else None)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/context")
def get_migration_context():
    """Return current migration context (for debugging)."""
    return get_context()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
