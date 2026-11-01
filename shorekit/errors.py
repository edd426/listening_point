"""One error type for every rejection, carrying a code and a message that names the spot."""


class ShoreError(Exception):
    """A rejection. `code` is an E_... code; `text` names the spot."""

    def __init__(self, code, text):
        Exception.__init__(self, code + " " + text)
        self.code = code
        self.text = text

    def line(self):
        return self.code + " " + self.text
