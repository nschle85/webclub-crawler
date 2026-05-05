from dataclasses import dataclass


@dataclass(frozen=True)
class CourseVariant:
    key: str
    label: str
    list_value: int
    filename: str

    def __getitem__(self, item):
        return getattr(self, item)

    def get(self, item, default=None):
        return getattr(self, item, default)


BEST_TIME_VARIANTS = [
    CourseVariant("kurzbahn", "Kurzbahn", 0, "bestzeiten_turbo_kurzbahn.csv"),
    CourseVariant("langbahn", "Langbahn", 1, "bestzeiten_turbo_langbahn.csv"),
]
