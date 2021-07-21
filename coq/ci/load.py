from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from subprocess import check_call
from typing import Any, MutableMapping, MutableSequence, MutableSet, Tuple
from urllib.parse import urlparse

from std2.pickle import new_decoder, new_encoder
from yaml import safe_load

from ..consts import COMPILATION_YML, TMP_DIR
from ..shared.context import EMPTY_CONTEXT
from ..shared.types import SnippetEdit
from ..snippets.loaders.load import load as load_from_paths
from ..snippets.parse import parse
from ..snippets.parsers.parser import ParseError
from ..snippets.types import ASnips, ParsedSnippet
from .types import Compilation


def _p_name(uri: str) -> Path:
    return TMP_DIR / Path(urlparse(uri).path).name


def _git_pull(uri: str) -> None:
    location = _p_name(uri)
    if location.is_dir():
        check_call(("git", "pull", "--recurse-submodules"), cwd=location)
    else:
        check_call(
            (
                "git",
                "clone",
                "--depth=1",
                "--recurse-submodules",
                "--shallow-submodules",
                uri,
                str(location),
            ),
            cwd=TMP_DIR,
        )


def load() -> ASnips:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    yaml = safe_load(COMPILATION_YML.read_bytes())
    specs: Compilation = new_decoder(Compilation)(yaml)
    with ThreadPoolExecutor() as pool:
        tuple(pool.map(_git_pull, specs.git))

    parsed = load_from_paths(
        lsp={str(path): TMP_DIR / path for path in specs.paths.lsp},
        neosnippet={str(path): TMP_DIR / path for path in specs.paths.neosnippet},
        ultisnip={str(path): TMP_DIR / path for path in specs.paths.ultisnip},
    )
    return parsed


def load_parsable() -> Any:
    specs = load()
    meta: MutableMapping[
        str,
        Tuple[
            MutableMapping[str, MutableSet[str]],
            MutableMapping[str, MutableSequence[ParsedSnippet]],
        ],
    ] = {}

    for label, (exts, snippets) in specs.items():
        _, good_snips = meta.setdefault(label, ({k: {*v} for k, v in exts.items()}, {}))
        for ext, snips in snippets.items():
            acc = good_snips.setdefault(ext, [])
            for snip in snips:
                edit = SnippetEdit(
                    new_text=snip.content,
                    grammar=snip.grammar,
                )
                with suppress(ParseError):
                    parse(
                        set(),
                        context=EMPTY_CONTEXT,
                        snippet=edit,
                        sort_by="",
                        visual="",
                    )
                    acc.append(snip)

    coder = new_encoder(ASnips)
    return coder(meta)

