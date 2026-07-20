import os
import time
import subprocess
import glob

LOG_FILE = "../remedies.txt"
AGENTS_DIR = "./agents"

def tail_logs(filename, lines=20):
    try:
        with open(filename, "r") as f:
            lines_list = f.readlines()
            return "".join(lines_list[-lines:])
    except FileNotFoundError:
        return ""

def identify_agent_for_error(error_text):
    # Basic keyword matching to select an appropriate agent persona
    if "sqlalchemy" in error_text.lower() or "psycopg2" in error_text.lower() or "database" in error_text.lower():
        return "database_engineer"
    elif "react" in error_text.lower() or "ui" in error_text.lower():
        return "frontend_architect"
    elif "timeout" in error_text.lower() or "ssl" in error_text.lower():
        return "infrastructure_architect"
    return "general_debugger"

def trigger_remediation():
    print(f"Monitoring {LOG_FILE} for new errors...")
    last_size = 0
    
    while True:
        try:
            current_size = os.path.getsize(LOG_FILE) if os.path.exists(LOG_FILE) else 0
            if current_size > last_size:
                print("New log entries detected. Analyzing...")
                error_context = tail_logs(LOG_FILE)
                
                if "error" in error_context.lower() or "exception" in error_context.lower():
                    agent = identify_agent_for_error(error_context)
                    print(f"[REMEDIATOR] Detected failure. Triggering agent: {agent}")
                    # In a fully autonomous loop, you would pass `error_context` to the LLM
                    # using the persona defined in `./agents/{agent}.md` and auto-apply the diffs.
                    # This is the entrypoint hook.
                    
                last_size = current_size
                
        except Exception as e:
            print(f"Remediator internal error: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    # Ensure working directory is Orchestrator
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    trigger_remediation()
