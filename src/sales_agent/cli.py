"""Interactive Command-Line Interface (REPL) for the Sales DB Autonomous Agent."""
import sys
from sales_agent.agent import SalesAgent

def main():
    print("=" * 60)
    print("  Sales DB Autonomous Agent (Stage 3 REPL)")
    print("  Type your natural language query, or 'exit' / 'quit' to close.")
    print("=" * 60)

    try:
        # Initialize the agent once to avoid repeated runtime discovery overhead
        agent = SalesAgent()
        print(f"[*] Agent online. Target model: {agent.model}\n")
    except Exception as err:
        print(f"[!] Initialization error: {err}")
        sys.exit(1)

    # One-shot mode: if arguments were passed directly on the command line
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"Query: {query}\n" + "-" * 40)
        answer = agent.run(query)
        print("\nAgent Answer:\n" + answer)
        return

    # Interactive REPL mode
    while True:
        try:
            query = input("Ask a question > ").strip()
            if not query:
                continue

            if query.lower() in ("exit", "quit", "q"):
                print("Shutting down agent session. Goodbye.")
                break

            print("\n[Thinking & Executing Tools...]")
            answer = agent.run(query)
            print("\nAgent Answer:")
            print(answer)
            print("-" * 60 + "\n")

        except (KeyboardInterrupt, EOFError):
            print("\nSession interrupted. Exiting.")
            break
        except Exception as err:
            print(f"\n[Error during execution]: {err}\n")

if __name__ == "__main__":
    main()
