"""The museum's two entrances as coroutines, for a server that runs them on its event loop.

`ON_VIEW` is for the recording script, as in views.py, except that what it holds are
coroutine functions: each view awaits each of them with the request before it answers.
"""
from django.http import HttpResponse

ON_VIEW = []


async def answer(request, text):
    for ask in ON_VIEW:
        await ask(request)
    return HttpResponse(text)


async def entrance(request):
    return await answer(request, "the entrance")


async def members(request):
    return await answer(request, "the members' entrance")
