"""Both installed console commands delegate to the same CLI."""


def main() -> None:
    from sales_agent.cli import main as cli_main

    cli_main()
