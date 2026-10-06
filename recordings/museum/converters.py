"""A converter of the museum's own: a month, written in a URL as two digits."""


class MonthConverter:
    regex = "[0-9]{2}"

    def to_python(self, value):
        month = int(value)
        if not 1 <= month <= 12:
            raise ValueError(f"{value} is not a month")
        return month

    def to_url(self, value):
        if not 1 <= int(value) <= 12:
            raise ValueError(f"{value} is not a month")
        return "%02d" % int(value)
