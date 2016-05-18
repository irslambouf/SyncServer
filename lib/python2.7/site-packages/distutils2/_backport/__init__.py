"""Things that will land in the Python 3.3 std lib but which we must drag along
with us for now to support 2.x."""

def any(seq):
    for elem in seq:
        if elem:
            return True
    return False
