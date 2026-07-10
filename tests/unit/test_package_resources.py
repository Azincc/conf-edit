from importlib.resources import files


def test_frontend_resources_are_packaged() -> None:
    root = files("conf_edit")

    assert (root / "templates" / "index.html").is_file()
    assert (root / "static" / "css" / "app.css").is_file()
    assert (
        root
        / "static"
        / "vendor"
        / "codemirror"
        / "lib"
        / "codemirror.min.js"
    ).is_file()
