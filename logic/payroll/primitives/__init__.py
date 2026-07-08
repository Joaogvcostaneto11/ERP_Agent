# Importing these submodules has the side-effect of firing their @register
# decorators, populating DEFAULT_REGISTRY whenever any code touches the
# `logic.payroll.primitives` package (which Python does eagerly the first time
# anything under it is imported — including `logic.payroll.primitives.base`).
from logic.payroll.primitives.base import (  # noqa: F401
    DEFAULT_REGISTRY, Primitive, PrimitiveRegistry, PrimitiveResult,
    ExecutionContext, register,
)
from logic.payroll.primitives import basesalary, tsu  # noqa: F401
