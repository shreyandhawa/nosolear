import threading

from nosolear.adapters.lazy_model import LazyModel


class FakeTimer:
    def __init__(self, seconds, callback):
        self.seconds = seconds
        self.callback = callback
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback()


def test_loads_once_unloads_when_idle_and_reloads():
    loads, timers = [], []

    def timer(seconds, callback):
        timers.append(FakeTimer(seconds, callback))
        return timers[-1]

    m = LazyModel(lambda: loads.append(1) or object(), timer=timer)
    m.get()
    m.get()
    assert len(loads) == 1 and timers[-1].seconds == 600.0
    assert timers[-1].daemon and timers[-1].started
    timers[-1].fire()
    assert not m.loaded
    m.get()
    assert len(loads) == 2 and m.loaded


def test_a_superseded_timer_does_not_unload():
    timers = []

    def timer(seconds, callback):
        timers.append(FakeTimer(seconds, callback))
        return timers[-1]

    m = LazyModel(object, timer=timer)
    m.get()
    m.get()
    assert timers[0].cancelled
    timers[0].fire()
    assert m.loaded


def test_unload_drops_the_model_and_cancels_the_timer():
    timers = []

    def timer(seconds, callback):
        timers.append(FakeTimer(seconds, callback))
        return timers[-1]

    m = LazyModel(object, timer=timer)
    m.get()
    m.unload()
    assert not m.loaded and timers[-1].cancelled


def test_concurrent_first_use_loads_once():
    loads = []
    start = threading.Barrier(8)
    results = []

    def slow_load():
        loads.append(1)
        threading.Event().wait(0.02)
        return object()

    m = LazyModel(slow_load, timer=lambda s, cb: FakeTimer(s, cb))

    def use():
        start.wait()
        results.append(m.get())

    threads = [threading.Thread(target=use) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(loads) == 1
    assert len({id(r) for r in results}) == 1 and len(results) == 8
