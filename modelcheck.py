
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
