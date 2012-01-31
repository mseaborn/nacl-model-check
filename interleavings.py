

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
    WAITING = 8

    lock_around_resume = 1
    suspend_is_deferred = 1

    class State:
        state = UNTRUSTED
    st = State()

    def asserteq(a, b):
        if a != b:
            yield 'FAIL: %r != %r' % (a, b)

    def SuspendThread(thread):
        assert thread not in suspended
        assert thread not in suspend_pending
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

    def Wake(thread):
        wake = (thread not in runnable and
                thread not in suspended and
                thread in threads)
        if wake:
            runnable.append(thread)
        yield 'wake(%s) -> %r' % (thread, wake)

    def A(thread):
        ### NaClUntrustedThreadsSuspend()
        while True:
            prev_state = st.state
            yield 'read state (got %r)' % prev_state
            if st.state == prev_state:
                st.state = prev_state | SUSPENDING
                break

        if prev_state & UNTRUSTED:
            for x in SuspendThread('B'): yield x

        ### NaClUntrustedThreadsResume()
        yield 'resume phase'

        while True:
            prev_state = st.state
            yield 'read state (got %r)' % prev_state
            if (prev_state & SUSPENDING) == 0:
                yield 'FAIL: not suspended'
                return
            if st.state != prev_state:
                if (prev_state & WAITING) != 0:
                    # The state should no longer be changed concurrently.
                    # Check this.
                    yield 'FAIL: state changed'
                    return
                continue
            st.state = prev_state &~ (SUSPENDING | WAITING)
            if (prev_state & UNTRUSTED) != 0:
                for x in ResumeThread('B'): yield x
            if (prev_state & WAITING) != 0:
                for x in Wake('B'): yield x
            break

    # Based on NaClAppThreadSetSuspendState()
    def SetSuspendState(thread, old_state, new_state):
        while True:
            prev_state = st.state
            yield 'read state (got %r)' % prev_state
            if prev_state == old_state:
                if st.state == prev_state:
                    st.state = new_state
                    yield 'set state; done'
                    break
            elif prev_state == (old_state | SUSPENDING):
                if st.state == prev_state:
                    st.state = prev_state | WAITING
                    # Wait
                    runnable.remove(thread)
                    yield 'set state; waiting'
                    # SUSPENDING and WAITING flags will have been
                    # removed, but SUSPENDING could have got set
                    # again, so we need to restart.
            else:
                yield 'FAIL: bad state'
                break

    def B(thread):
        for x in SetSuspendState(thread, UNTRUSTED, TRUSTED): yield x
        for x in SetSuspendState(thread, TRUSTED, UNTRUSTED): yield x

    def CheckFinalCondition():
        assert st.state == UNTRUSTED

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
        got.append('FAIL: DEADLOCK: %s' % i)
    if len(threads) == 0:
        CheckFinalCondition()
    return got


if __name__ == '__main__':
    check(Run)
