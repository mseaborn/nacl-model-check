

# The model checking driver comes from my blog post:
# http://lackingrhoticity.blogspot.com/2009/08/how-to-do-model-checking-of-python-code.html


# If anyone catches and handles this, it will break the checking model.
class ModelCheckEscape(Exception):
    pass


class Chooser(object):

    def __init__(self, chosen, queue):
        self._so_far = chosen
        self._index = 0
        self._queue = queue

    def choose(self, choices):
        assert len(choices) > 0
        if self._index < len(self._so_far):
            choice = self._so_far[self._index]
            if choice not in choices:
                raise Exception("Program is not deterministic")
            self._index += 1
            return choice
        else:
            for choice in choices:
                self._queue.append(self._so_far + [choice])
            raise ModelCheckEscape()


def check(func):
    seen = set()

    queue = [[]]
    while len(queue) > 0:
        chosen = queue.pop(0)
        try:
            got = tuple(func(Chooser(chosen, queue)))
            if got not in seen:
                seen.add(got)
                print '\n%i:' % len(seen)
                for x in got:
                    print x
        except ModelCheckEscape:
            pass
        # Can catch other exceptions here and report the failure
        # - along with the choices that caused it - and then carry on.


# Add a prefix to each string in the sequence.
def Wrap(prefix, seq):
    for x in seq:
        yield '%s: %s' % (prefix, x)


def Run(ch):
    class Lock(object):
        def __init__(self):
            self.locked = None
            self.waiters = []
        def lock(self, thread):
            while self.locked:
                runnable.remove(thread)
                self.waiters.append(thread)
                yield 'lock: (waiting)'
            self.locked = thread
            yield 'lock: acquired'
        def unlock_quiet(self, thread):
            assert self.locked == thread, (self.locked, thread)
            for i in self.waiters:
                run_thread(i)
            self.locked = None
            self.waiters = []
        def unlock(self, thread):
            self.unlock_quiet(thread)
            yield 'unlock'

    lck = Lock()

    UNTRUSTED = 1
    TRUSTED = 2
    SUSPENDING = 4

    lock_around_resume = 1
    suspend_is_deferred = 1

    class State:
        state = UNTRUSTED
    st = State()

    def asserteq(a, b):
        if a != b:
            yield 'FAIL: %r != %r' % (a, b)

    def SuspendThread(thread):
        if suspend_is_deferred:
            suspend_pending.append(thread)
            yield 'SuspendThread(%s) pending' % thread
        else:
            suspended.add(thread)
            yield 'SuspendThread(%s)' % thread

    def ResumeThread(thread):
        if thread in suspend_pending:
            suspend_pending.remove(thread)
        else:
            suspended.remove(thread)
        yield 'ResumeThread(%s)' % thread

    def A(thread):
        ### NaClUntrustedThreadsSuspend()
        for x in lck.lock(thread): yield x

        old_state = st.state
        yield 'read state'

        for x in asserteq(old_state & SUSPENDING, 0): yield x
        st.state = old_state | SUSPENDING
        yield 'state |= suspend'

        for x in SuspendThread('B'): yield x

        for x in lck.unlock(thread): yield x

        ### NaClUntrustedThreadsResume()
        if lock_around_resume:
            for x in lck.lock(thread): yield x

        old_state = st.state
        yield 'read state (got %r)' % old_state
        for x in asserteq(old_state & SUSPENDING, SUSPENDING): yield x

        for x in ResumeThread('B'): yield x

        st.state = old_state & ~SUSPENDING
        yield 'change state back'

        # Doing the same assignment again is not OK, because the first
        # assignment unblocked the thread from running.  The other thread
        # could have changed the state, and we would be overwriting that
        # change.
        # st.state = old_state & ~SUSPENDING
        # yield 'change state back (again)'

        # CondVarSignal
        wake = ('B' not in runnable and
                'B' not in suspended and
                'B' in threads)
        if wake:
            runnable.append('B')
        yield 'wake(B) -> %r' % wake

        if lock_around_resume:
            for x in lck.unlock(thread): yield x

    # Based on NaClAppThreadSetSuspendState()
    def SetSuspendState(thread, old_state, new_state):
        for x in lck.lock(thread): yield x
        while 1:
            state = st.state
            yield 'read state (got %r)' % state
            if (state & SUSPENDING) == 0:
                break
            # CondVarWait
            lck.unlock_quiet(thread)
            runnable.remove(thread)
            yield 'wait (unlocks)'
            for x in lck.lock(thread): yield x

        for x in asserteq(st.state, old_state): yield x

        st.state = new_state
        yield 'state := trusted'
        for x in lck.unlock(thread): yield x

    def B(thread):
        for x in SetSuspendState(thread, UNTRUSTED, TRUSTED): yield x
        for x in SetSuspendState(thread, TRUSTED, UNTRUSTED): yield x

    def run_thread(thr):
        if thr not in runnable and thr in threads:
            runnable.append(thr)

    threads = {'A': Wrap('A', A('A')),
               'B': Wrap('    B', B('B'))}
    runnable = sorted(threads.keys())
    suspended = set()
    suspend_pending = []
    got = []
    while True:
        # Process pending SuspendThread() calls
        while suspend_pending and ch.choose((0, 1)):
            i = suspend_pending.pop(0)
            suspended.add(i)
            got.append('SuspendThread(%s) kicked in' % i)

        runnable2 = [i for i in runnable if i not in suspended]
        if len(runnable2) == 0:
            break
        i = ch.choose(runnable2)
        try:
            item = threads[i].next()
            if i in suspend_pending:
                item += ' (borrowed time)'
            got.append(item)
        except StopIteration:
            threads.pop(i)
            runnable.remove(i)
    for i in sorted(threads.keys()):
        got.append('DEADLOCK: %s' % i)
    return got


if __name__ == '__main__':
    check(Run)
