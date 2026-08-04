import pkgutil
import sys

from ht_manager.db import models


def test_all_model_modules_are_imported_in_init() -> None:
    discovered = {
        module_info.name
        for module_info in pkgutil.iter_modules(models.__path__)
        if not module_info.ispkg
    }

    for name in discovered:
        full_name = f"{models.__name__}.{name}"
        assert full_name in sys.modules, (
            f"{full_name} exists but is not imported in db/models/__init__.py — "
            "it will be invisible to Alembic autogenerate."
        )
