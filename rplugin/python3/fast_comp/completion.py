from asyncio import Queue, gather, wait
from itertools import chain
from traceback import format_exc
from typing import (
    Awaitable,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from pynvim import Nvim

from .cache import make_cache
from .fuzzy import fuzzer, normalize
from .nvim import VimCompletion, call, print
from .types import (
    Factory,
    Notification,
    Position,
    Context,
    Settings,
    SourceFactory,
    SourceFeed,
    Step,
)

StepFunction = Callable[[SourceFeed], Awaitable[Sequence[Step]]]



def gen_context(line: str, col: int) -> Context:
    def is_sym(char: str) -> bool:
        return not char.isalnum() and not char.isspace()

    line_before = line[:col]
    line_after = line[col:]

    lit = reversed(line_before)
    l_alnums: List[str] = []
    l_syms: List[str] = []
    for c in lit:
        if c.isalnum():
            l_alnums.append(c)
        else:
            if is_sym(c):
                l_syms.append(c)
            break

    for c in lit:
        if is_sym(c):
            l_syms.append(c)
        else:
            break

    rit = iter(line_after)
    r_alnums: List[str] = []
    r_syms: List[str] = []
    for c in rit:
        if c.isalnum():
            r_alnums.append(c)
        else:
            if is_sym(c):
                r_syms.append(c)
            break

    for c in rit:
        if is_sym(c):
            r_syms.append(c)
        else:
            break

    alnums_before = "".join(reversed(l_alnums))
    alnums_after = "".join(r_alnums)
    alnums = alnums_before + alnums_after

    syms_before = "".join(reversed(l_syms))
    syms_after = "".join(r_syms)
    syms = syms_before + syms_after

    normalized_alnums = normalize(alnums)

    return Context(
        line=line,
        line_before=line_before,
        line_after=line_after,
        alnums=alnums,
        alnums_before=alnums_before,
        alnums_after=alnums_after,
        syms=syms,
        syms_before=syms_before,
        syms_after=syms_after,
        normalized_alnums=normalized_alnums,
    )


async def gen_feed(nvim: Nvim) -> SourceFeed:
    def fed() -> SourceFeed:
        buffer = nvim.api.get_current_buf()
        filename = nvim.api.buf_get_name(buffer)
        filetype = nvim.api.buf_get_option(buffer, "filetype")
        window = nvim.api.get_current_win()
        row, col = nvim.api.win_get_cursor(window)
        line = nvim.api.get_current_line()
        position = Position(row=row, col=col)
        context = gen_context(line, col)
        return SourceFeed(
            filename=filename, filetype=filetype, position=position, context=context
        )

    return await call(nvim, fed)


def p_alnums(prefix: str, suffix: str) -> str:
    def p1() -> Iterator[str]:
        for c in reversed(prefix):
            if c.isalnum():
                yield c
            else:
                break

    def p2() -> Iterator[str]:
        for c in suffix:
            if c.isalnum():
                yield c
            else:
                break

    return "".join(chain(reversed(tuple(p1())), p2()))


async def manufacture(nvim: Nvim, factory: SourceFactory) -> Tuple[StepFunction, Queue]:
    chan: Queue = Queue()
    fact = cast(Factory, factory.manufacture)
    src = await fact(nvim, chan, factory.seed)

    async def source(feed: SourceFeed) -> Sequence[Step]:
        name = factory.name
        timeout = factory.timeout
        acc: List[Step] = []

        async def cont() -> None:
            async for comp in src(feed):
                text = comp.new_prefix + comp.new_suffix
                alnums = p_alnums(comp.new_prefix, comp.new_suffix)
                normalized_alnums = normalize(alnums)
                completion = Step(
                    source=name,
                    source_shortname=factory.short_name,
                    priority=factory.priority,
                    text=text,
                    alnums=alnums,
                    normalized_alnums=normalized_alnums,
                    comp=comp,
                )
                acc.append(completion)

        done, pending = await wait((cont(),), timeout=timeout)
        await gather(*done)
        for p in pending:
            p.cancel()
        if pending:
            timeout_fmt = round(timeout * 1000)
            msg = (
                f"async completion source timed out - {name}, exceeded {timeout_fmt}ms"
            )
            await print(nvim, msg)
        return acc

    return source, chan


async def osha(
    nvim: Nvim, factory: SourceFactory
) -> Tuple[str, StepFunction, Optional[Queue]]:
    async def nil_steps(_: SourceFeed) -> Sequence[Step]:
        return ()

    try:
        step_fn, chan = await manufacture(nvim, factory=factory)
    except Exception as e:
        stack = format_exc()
        message = f"Error in source {factory.name}\n{stack}{e}"
        await print(nvim, message, error=True)
        return factory.name, nil_steps, None
    else:

        async def o_step(feed: SourceFeed) -> Sequence[Step]:
            try:
                return await step_fn(feed)
            except Exception as e:
                stack = format_exc()
                message = f"Error in source {factory.name}\n{stack}{e}"
                await print(nvim, message, error=True)
                return ()

        return factory.name, o_step, chan


async def merge(
    nvim: Nvim, chan: Queue, factories: Iterator[SourceFactory], settings: Settings
) -> Tuple[
    Callable[[bool], Awaitable[Tuple[Position, Iterator[VimCompletion]]]],
    Callable[[], Awaitable[None]],
]:
    facts = tuple(factories)
    limits = {fact.name: fact.limit for fact in facts}
    fuzzy = fuzzer(settings.fuzzy, limits=limits)
    src_gen = await gather(*(osha(nvim, factory=factory) for factory in facts))
    chans: Dict[str, Optional[Queue]] = {name: chan for name, _, chan in src_gen}
    sources = tuple(source for _, source, _ in src_gen)

    push, retrieve = make_cache(settings.fuzzy)

    async def gen(force: bool) -> Tuple[Position, Iterator[VimCompletion]]:
        feed = await gen_feed(nvim)
        position = feed.position
        go = feed.context.line_before.isspace()
        if go or force:
            cached, *comps = await gather(
                retrieve(feed), *(source(feed) for source in sources)
            )
            steps: Sequence[Step] = tuple((c for co in comps for c in co))
            push(feed, steps)
            completions = chain(steps)
            return position, fuzzy(feed, completions)
        else:
            return position, iter(())

    async def listen() -> None:
        while True:
            notif: Notification = await chan.get()
            source = notif.source
            ch = chans.get(source)
            if ch:
                await ch.put(notif.body)
            elif source in chans:
                await print(
                    nvim, f"Notification to uknown source - {source}", error=True
                )

    return gen, listen
