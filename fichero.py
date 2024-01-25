import typer


def main(source: str, 
        prompt: str, 
        output: str,
        config: str = "",
        llm: str = "ollama", 
        model: str = "mistral:instruct",
        tempreature: int = 0.5,
        max_tokens: int = 2000,
        verbose: bool = True,
        debug: bool = True
        ):
    """
    Doesn't do anything yet.
    """
    print(f"Loading source {name}")


if __name__ == "__main__":
    typer.run(main)