from dataclasses import dataclass
from json import loads
from os import linesep
from pathlib import PurePath
from typing import AbstractSet, Iterable, Iterator, Mapping, Sequence, Tuple, Union

from std2.pickle import new_decoder

from ..types import ParsedSnippet


@dataclass
class _Unit:
    prefix: Union[str, Sequence[str]]
    body: Union[str, Sequence[str]]
    description: str = ""


_FMT = Mapping[str, _Unit]
_DECODER = new_decoder(_FMT, strict=False)


def _prefix(prefix: Union[str, Sequence[str]]) -> AbstractSet[str]:
    if isinstance(prefix, str):
        return {prefix}
    elif isinstance(prefix, Sequence):
        return {*prefix}
    else:
        raise ValueError(prefix)


def _body(body: Union[str, Sequence[str]]) -> str:
    if isinstance(body, str):
        return body
    elif isinstance(body, Sequence):
        return linesep.join(body)
    else:
        raise ValueError(body)


def parse(
    path: PurePath, lines: Iterable[Tuple[int, str]]
) -> Tuple[str, AbstractSet[str], Sequence[ParsedSnippet]]:
    filetype = path.stem.strip()

    text = linesep.join(line.rstrip() for _, line in lines)
    json = loads(text)
    fmt: _FMT = _DECODER(json)

    def cont() -> Iterator[ParsedSnippet]:
        for label, values in fmt.items():
            content = _body(values.body)
            snippet = ParsedSnippet(
                source=path,
                grammar="lsp",
                filetype=filetype,
                content=content,
                doc=values.description,
                label=label,
                matches=_prefix(values.prefix),
            )
            yield snippet

    return filetype, set(), tuple(cont())
