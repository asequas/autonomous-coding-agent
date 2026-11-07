from wordcount import main

TEXT = "The cat -- the DOG, the bird. A cat!"


def run(tmp_path, capsys, *args):
    path = tmp_path / "in.txt"
    path.write_text(TEXT)
    assert main([str(path), *args]) == 0
    rows = [line.split("\t") for line in capsys.readouterr().out.splitlines()]
    return {word: int(count) for count, word in rows}


def test_default_counts_everything_but_empty_tokens(tmp_path, capsys):
    counts = run(tmp_path, capsys)
    assert counts == {"the": 3, "cat": 2, "dog": 1, "bird": 1, "a": 1}


def test_min_length(tmp_path, capsys):
    counts = run(tmp_path, capsys, "--min-length", "4")
    assert counts == {"bird": 1}
