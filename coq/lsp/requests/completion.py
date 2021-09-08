from collections.abc import Sized
from pathlib import Path
from typing import AsyncIterator, cast

from pynvim.api.nvim import Nvim
from pynvim_pp.logging import log

from ...consts import DEBUG
from ...registry import atomic
from ...shared.types import UTF16, Context
from ..parse import parse
from ..types import CompletionResponse, LSPcomp
from .request import async_request

_LUA = (Path(__file__).resolve().parent / "completion.lua").read_text("UTF-8")

atomic.exec_lua(_LUA, ())


async def request(
    nvim: Nvim,
    short_name: str,
    weight_adjust: float,
    context: Context,
) -> AsyncIterator[LSPcomp]:
    row, c = context.position
    col = len(context.line_before[:c].encode(UTF16)) // 2

    async for client, reply in async_request(nvim, "COQlsp_comp", (row, col)):
        resp = cast(CompletionResponse, reply)
        if DEBUG:
            thing = len(resp) if isinstance(resp, Sized) else resp
            msg = f"{client} {thing}"
            log.info("%s", msg)
        yield parse(short_name, weight_adjust=weight_adjust, resp=resp)
