# Copyright 2023 Mark T. Tomczak
# License at https://github.com/fixermark/brilliant-monocle-driver-python/blob/main/LICENSE

class LineReader:
    """
    Reads a stream of text broken into arbitrary chunks and yields each line of the stream.
    """

    def __init__(self, sep="\n"):
        """
        Constructor. Sep is the separator sequence for lines.
        """
        self.current_line = ""
        self.lines = []
        self.sep = sep

    def input(self, newtext):
        """
        Insert new text into the LineReader.
        """
        newlines = newtext.split(self.sep)

        newlines[0] = self.current_line + newlines[0]
        new_current_line = newlines[-1]
        new_emittable_lines = newlines[0:-1]

        self.current_line = new_current_line
        self.lines += new_emittable_lines

    def get_lines(self):
        """
        Get available lines as an iterable. Note that there may be no available lines
        at this time.
        """
        emitting_lines = self.lines
        self.lines = []
        return emitting_lines
