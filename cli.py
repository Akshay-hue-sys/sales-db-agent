"""Interactive CLI for the Sales Database Agent."""

import sys
from sales_agent.agent import run_agent

def main():
    print("=" * 50)
    print("🤖 Sales Database Agent CLI (Type 'exit' or 'quit' to end)")
    print("=" * 50)

    while True:
        try:
            # 1. Capture user input
            question = input("\nUser > ").strip()
            
            # 2. Exit conditions
            if question.lower() in ['exit', 'quit']:
                print("Shutting down...")
                break
            if not question:
                continue

            # 3. Execute agent loop
            print("Agent is thinking (this may take a few seconds)...\n")
            response = run_agent(question)
            
            # 4. Display result
            print(f"Agent > {response}")

        except KeyboardInterrupt:
            print("\nShutting down...")
            break
        except Exception as e:
            print(f"\n[!] System Error: {e}")

if __name__ == "__main__":
    # Ensure stdout flushes immediately for responsive CLI feel
    sys.stdout.reconfigure(line_buffering=True)
    main()