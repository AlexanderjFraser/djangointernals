from django.conf import settings
from django.core.checks import Error, Warning, register


@register("trees")
def check_trees_per_row(app_configs, **kwargs):
    """A row holds twelve trees comfortably, sixteen at a squeeze, and no more than twenty."""
    per_row = settings.TREES_PER_ROW
    if per_row > 20:
        return [
            Error(
                f"TREES_PER_ROW is {per_row}, and a row has room for 20.",
                hint="Plant another row.",
                id="trees.E001",
            )
        ]
    if per_row > 16:
        return [Warning(f"TREES_PER_ROW is {per_row}: the trees will be crowded.", id="trees.W001")]
    return []
